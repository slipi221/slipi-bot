# -*- coding: utf-8 -*-
"""
SLIPI — платежи, выплаты, возвраты
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Payment, Payout, Transaction, Order, Client, Shop, Courier,
)
from utils import helpers


# ═══════════════════════════════════════════
#   ВХОДЯЩИЕ ПЛАТЕЖИ (от клиентов)
# ═══════════════════════════════════════════
async def get_pending_payments(session: AsyncSession) -> list:
    """Все неподтверждённые платежи от клиентов."""
    result = await session.execute(
        select(Payment).where(Payment.status == "pending")
        .order_by(Payment.created_at.asc())
    )
    return result.scalars().all()


async def get_payment_by_order(session: AsyncSession, order_id: int) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.order_id == order_id)
    )
    return result.scalar_one_or_none()


async def mark_payment_rejected(
    session: AsyncSession,
    order_id: int,
    admin_id: int,
    reason: str = None,
):
    """Админ отклонил платёж — клиент не оплатил."""
    result = await session.execute(
        select(Payment).where(Payment.order_id == order_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return False

    payment.status = "rejected"
    payment.admin_id = admin_id
    payment.confirmed_at = datetime.now()
    if reason:
        payment.comment = (payment.comment or "") + f" | Отказ: {reason}"

    await session.commit()
    return True


# ═══════════════════════════════════════════
#   ВЫПЛАТЫ (курьерам, магазинам, клиентам)
# ═══════════════════════════════════════════
async def create_payout(
    session: AsyncSession,
    user_type: str,
    user_id: int,
    amount: Decimal,
    card_number: str = None,
    holder_name: str = None,
) -> Payout:
    """
    Создаёт заявку на выплату.
    user_type: shop / courier / client
    """
    # Для клиента — комиссия 5%
    commission = Decimal("0")
    if user_type == "client":
        commission = (amount * Decimal(str(config.CLIENT_WITHDRAW_COMMISSION)) / Decimal("100")).quantize(Decimal("0.01"))

    amount_to_pay = amount - commission

    payout = Payout(
        user_type=user_type,
        user_id=user_id,
        amount=amount,
        commission=commission,
        amount_to_pay=amount_to_pay,
        card_number=card_number,
        holder_name=holder_name,
        status="pending",
    )
    session.add(payout)
    await session.commit()
    return payout


async def get_pending_payouts(session: AsyncSession, user_type: str = None) -> list:
    """Все неподтверждённые выплаты."""
    q = select(Payout).where(Payout.status == "pending")
    if user_type:
        q = q.where(Payout.user_type == user_type)
    q = q.order_by(Payout.created_at.asc())
    result = await session.execute(q)
    return result.scalars().all()


async def mark_payout_transferred(
    session: AsyncSession,
    payout_id: int,
    admin_id: int,
):
    """Админ нажал «Перевести» — деньги отправлены."""
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        return None

    payout.status = "processing"
    payout.admin_id = admin_id
    await session.commit()
    return payout


async def mark_payout_done(
    session: AsyncSession,
    payout_id: int,
    admin_id: int,
):
    """Админ подтвердил — деньги дошли до получателя. Списываем баланс."""
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        return None

    # Списываем баланс в зависимости от роли
    if payout.user_type == "courier":
        await session.execute(
            update(Courier).where(Courier.id == payout.user_id)
            .values(balance=Courier.balance - payout.amount)
        )
    elif payout.user_type == "shop":
        await session.execute(
            update(Shop).where(Shop.id == payout.user_id)
            .values(balance=Shop.balance - payout.amount)
        )
    elif payout.user_type == "client":
        await session.execute(
            update(Client).where(Client.id == payout.user_id)
            .values(balance=Client.balance - payout.amount)
        )

    payout.status = "done"
    payout.paid_at = datetime.now()
    payout.admin_id = admin_id

    # Транзакция
    session.add(Transaction(
        user_type=payout.user_type,
        user_id=payout.user_id,
        amount=-payout.amount,
        type="payout",
        comment=f"Выплата #{payout.id}",
    ))

    await session.commit()
    return payout


async def mark_payout_rejected(
    session: AsyncSession,
    payout_id: int,
    admin_id: int,
    reason: str = None,
):
    """Админ отклонил выплату."""
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        return None

    payout.status = "rejected"
    payout.admin_id = admin_id
    await session.commit()
    return payout


# ═══════════════════════════════════════════
#   ВОЗВРАТЫ
# ═══════════════════════════════════════════
async def refund_to_balance(session: AsyncSession, client_id: int, amount: Decimal, order_id: int = None):
    """Возврат клиенту на баланс в боте."""
    await session.execute(
        update(Client).where(Client.id == client_id)
        .values(balance=Client.balance + amount)
    )
    session.add(Transaction(
        user_type="client",
        user_id=client_id,
        amount=amount,
        type="refund",
        order_id=order_id,
        comment="Возврат на баланс",
    ))
    await session.commit()


async def refund_to_card(
    session: AsyncSession,
    client_id: int,
    amount: Decimal,
    order_id: int = None,
):
    """
    Возврат клиенту на карту (вручную админом).
    Создаёт запись в payouts типа client.
    """
    payout = await create_payout(
        session=session,
        user_type="client",
        user_id=client_id,
        amount=amount,
        card_number=None,
    )
    return payout


# ═══════════════════════════════════════════
#   ФИНАНСОВАЯ СТАТИСТИКА (для админа)
# ═══════════════════════════════════════════
async def get_finance_summary(session: AsyncSession) -> dict:
    """Общая финансовая сводка."""
    # Общая касса (все подтверждённые платежи)
    total_result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.status == "confirmed")
    )
    total_income = Decimal(str(total_result.scalar() or 0))

    # Комиссия платформы с доставки
    orders_result = await session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.platform_income), 0))
        .where(Order.status == "done")
    )
    row = orders_result.first()
    done_orders = row[0] or 0
    platform_income = Decimal(str(row[1] or 0))

    # Долг магазинам
    shops_result = await session.execute(
        select(func.coalesce(func.sum(Shop.balance), 0))
        .where(Shop.balance > 0)
    )
    shops_balance = Decimal(str(shops_result.scalar() or 0))

    # Долг курьерам
    couriers_result = await session.execute(
        select(func.coalesce(func.sum(Courier.balance), 0))
        .where(Courier.balance > 0)
    )
    couriers_balance = Decimal(str(couriers_result.scalar() or 0))

    # Ожидают выплаты
    pending_payouts_result = await session.execute(
        select(func.coalesce(func.sum(Payout.amount_to_pay), 0))
        .where(Payout.status == "pending")
    )
    pending_payouts = Decimal(str(pending_payouts_result.scalar() or 0))

    return {
        "total_income": total_income,
        "platform_income": platform_income,
        "done_orders": done_orders,
        "shops_balance": shops_balance,
        "couriers_balance": couriers_balance,
        "pending_payouts": pending_payouts,
    }


async def get_orders_in_work(session: AsyncSession) -> int:
    """Количество заказов в работе."""
    result = await session.execute(
        select(func.count(Order.id)).where(
            Order.status.in_(["new", "wait", "going", "picked", "delivering", "at_client"])
        )
    )
    return result.scalar() or 0


# ═══════════════════════════════════════════
#   ИСТОРИЯ ТРАНЗАКЦИЙ
# ═══════════════════════════════════════════
async def get_user_transactions(
    session: AsyncSession,
    user_type: str,
    user_id: int,
    limit: int = 30,
) -> list:
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_type == user_type,
            Transaction.user_id == user_id,
        ).order_by(Transaction.id.desc()).limit(limit)
    )
    return result.scalars().all()
