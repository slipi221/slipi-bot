# -*- coding: utf-8 -*-
"""
SLIPI — платежи и выплаты
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Payment, Payout, Transaction, Order, Client, Shop, Courier,
    DeliveryPayment, DeliveryOrder,
)

# ═══════════════════════════════════════════
#   ВХОДЯЩИЕ ПЛАТЕЖИ (заказы)
# ═══════════════════════════════════════════
async def get_pending_payments(session: AsyncSession) -> list:
    result = await session.execute(
        select(Payment).where(Payment.status == "pending").order_by(Payment.created_at.asc())
    )
    return result.scalars().all()

async def mark_payment_rejected(session: AsyncSession, order_id: int, admin_id: int):
    result = await session.execute(select(Payment).where(Payment.order_id == order_id))
    payment = result.scalar_one_or_none()
    if not payment: return False
    payment.status = "rejected"
    payment.admin_id = admin_id
    payment.confirmed_at = datetime.now()
    await session.commit()
    return True

# ═══════════════════════════════════════════
#   ВХОДЯЩИЕ ПЛАТЕЖИ (свои доставки)
# ═══════════════════════════════════════════
async def get_pending_delivery_payments(session: AsyncSession) -> list:
    result = await session.execute(
        select(DeliveryPayment).where(DeliveryPayment.status == "pending").order_by(DeliveryPayment.created_at.asc())
    )
    return result.scalars().all()

async def confirm_delivery_payment(session: AsyncSession, delivery_id: int, admin_id: int):
    d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
    d = d_r.scalar_one_or_none()
    if not d: return None

    d.payment_status = "confirmed"
    d.status = "confirmed"

    p_r = await session.execute(select(DeliveryPayment).where(DeliveryPayment.delivery_id == delivery_id))
    p = p_r.scalar_one_or_none()
    if p:
        p.status = "confirmed"
        p.admin_id = admin_id
        p.confirmed_at = datetime.now()

    await session.commit()
    return d

async def reject_delivery_payment(session: AsyncSession, delivery_id: int, admin_id: int):
    d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
    d = d_r.scalar_one_or_none()
    if d:
        d.status = "cancel"
        d.payment_status = "rejected"

    p_r = await session.execute(select(DeliveryPayment).where(DeliveryPayment.delivery_id == delivery_id))
    p = p_r.scalar_one_or_none()
    if p:
        p.status = "rejected"
        p.admin_id = admin_id
        p.confirmed_at = datetime.now()

    await session.commit()
    return d

# ═══════════════════════════════════════════
#   ВЫПЛАТЫ (курьерам, магазинам, клиентам)
# ═══════════════════════════════════════════
async def create_payout(
    session: AsyncSession,
    user_type: str,
    user_id: int,
    amount: Decimal,
    method: str = "card",
    card_number: str = None,
    bank_name: str = None,
    card_holder: str = None,
    holder_name: str = None,
    sbp_phone: str = None,
) -> Payout | None:
    """
    Создаёт заявку на выплату.
    ИСПРАВЛЕНО (Баг #8): Замораживает средства на балансе, чтобы нельзя было вывести больше, чем есть.
    """
    # 1. Проверка баланса и заморозка
    if user_type == "courier":
        res = await session.execute(select(Courier).where(Courier.id == user_id))
        user = res.scalar_one_or_none()
    elif user_type == "shop":
        res = await session.execute(select(Shop).where(Shop.id == user_id))
        user = res.scalar_one_or_none()
    elif user_type == "client":
        res = await session.execute(select(Client).where(Client.id == user_id))
        user = res.scalar_one_or_none()
    else:
        return None

    if not user or user.balance < amount:
        return None # Недостаточно средств

    # Списываем (замораживаем) средства
    user.balance -= amount

    # 2. Расчет комиссии
    commission = Decimal("0")
    if user_type == "client":
        commission = (amount * Decimal(str(config.CLIENT_WITHDRAW_COMMISSION)) / Decimal("100")).quantize(Decimal("0.01"))

    amount_to_pay = amount - commission

    if method == "sbp":
        target = sbp_phone
    else:
        target = card_number

    payout = Payout(
        user_type=user_type, user_id=user_id,
        amount=amount, commission=commission, amount_to_pay=amount_to_pay,
        method=method, target=target,
        card_number=card_number, bank_name=bank_name, card_holder=card_holder or holder_name,
        status="pending",
    )
    session.add(payout)
    
    # Записываем транзакцию заморозки
    session.add(Transaction(
        user_type=user_type, user_id=user_id, amount=-amount,
        type="payout_freeze", comment=f"Заявка на выплату (заморозка)"
    ))
    
    await session.commit()
    return payout

async def get_pending_payouts(session: AsyncSession) -> list:
    result = await session.execute(
        select(Payout).where(Payout.status == "pending").order_by(Payout.created_at.asc())
    )
    return result.scalars().all()

async def mark_payout_transferred(session: AsyncSession, payout_id: int, admin_id: int):
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout: return None
    payout.status = "processing"
    payout.admin_id = admin_id
    await session.commit()
    return payout

async def mark_payout_done(session: AsyncSession, payout_id: int, admin_id: int):
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout: return None

    # Деньги уже списаны при создании, поэтому просто меняем статус
    payout.status = "done"
    payout.paid_at = datetime.now()
    payout.admin_id = admin_id
    await session.commit()
    return payout

async def mark_payout_rejected(session: AsyncSession, payout_id: int, admin_id: int):
    """Отклонение выплаты. Возвращаем замороженные средства обратно."""
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout: return None

    # Возврат средств на баланс
    if payout.user_type == "courier":
        await session.execute(update(Courier).where(Courier.id == payout.user_id).values(balance=Courier.balance + payout.amount))
    elif payout.user_type == "shop":
        await session.execute(update(Shop).where(Shop.id == payout.user_id).values(balance=Shop.balance + payout.amount))
    elif payout.user_type == "client":
        await session.execute(update(Client).where(Client.id == payout.user_id).values(balance=Client.balance + payout.amount))

    payout.status = "rejected"
    payout.admin_id = admin_id
    
    # Записываем транзакцию возврата
    session.add(Transaction(
        user_type=payout.user_type, user_id=payout.user_id, amount=payout.amount,
        type="payout_rejected", comment=f"Возврат заявки на выплату #{payout.id}"
    ))
    await session.commit()
    return payout

# ═══════════════════════════════════════════
#   ВОЗВРАТЫ И СВОДКА
# ═══════════════════════════════════════════
async def refund_to_balance(session: AsyncSession, client_id: int, amount: Decimal, order_id: int = None):
    await session.execute(update(Client).where(Client.id == client_id).values(balance=Client.balance + amount))
    session.add(Transaction(
        user_type="client", user_id=client_id, amount=amount,
        type="refund", order_id=order_id, comment="Возврат на баланс",
    ))
    await session.commit()

async def get_finance_summary(session: AsyncSession) -> dict:
    total_result = await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed"))
    total_income = Decimal(str(total_result.scalar() or 0))

    orders_result = await session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.platform_income), 0)).where(Order.status == "done")
    )
    row = orders_result.first()
    done_orders = row[0] or 0
    platform_income = Decimal(str(row[1] or 0))

    shops_result = await session.execute(select(func.coalesce(func.sum(Shop.balance), 0)).where(Shop.balance > 0))
    shops_balance = Decimal(str(shops_result.scalar() or 0))

    couriers_result = await session.execute(select(func.coalesce(func.sum(Courier.balance), 0)).where(Courier.balance > 0))
    couriers_balance = Decimal(str(couriers_result.scalar() or 0))

    pending_result = await session.execute(select(func.coalesce(func.sum(Payout.amount_to_pay), 0)).where(Payout.status == "pending"))
    pending_payouts = Decimal(str(pending_result.scalar() or 0))

    return {
        "total_income": total_income, "platform_income": platform_income, "done_orders": done_orders,
        "shops_balance": shops_balance, "couriers_balance": couriers_balance, "pending_payouts": pending_payouts,
    }

async def get_orders_in_work(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(Order.id)).where(Order.status.in_(["new", "pending", "wait", "going", "picked", "delivering", "at_client"]))
    )
    return result.scalar() or 0

async def get_user_transactions(session: AsyncSession, user_type: str, user_id: int, limit: int = 30) -> list:
    result = await session.execute(
        select(Transaction).where(Transaction.user_type == user_type, Transaction.user_id == user_id)
        .order_by(Transaction.id.desc()).limit(limit)
    )
    return result.scalars().all()

async def topup_shop_balance(session: AsyncSession, shop_id: int, amount: Decimal):
    await session.execute(update(Shop).where(Shop.id == shop_id).values(balance=Shop.balance + amount))
    session.add(Transaction(user_type="shop", user_id=shop_id, amount=amount, type="topup", comment="Пополнение админом"))
    await session.commit()

async def topup_courier_balance(session: AsyncSession, courier_id: int, amount: Decimal):
    await session.execute(update(Courier).where(Courier.id == courier_id).values(balance=Courier.balance + amount))
    session.add(Transaction(user_type="courier", user_id=courier_id, amount=amount, type="topup", comment="Пополнение админом"))
    await session.commit()
