# -*- coding: utf-8 -*-
"""
Flowers Express — платежи и выплаты

FIX bug5: datetime.now() → helpers.now_moscow() (4 места).
FIX (P0 race): create_payout — атомарное списание через UPDATE WHERE balance >= amount.
FIX: mark_payout_done — только из статуса "pending" (а не "done").
FIX: mark_payment_rejected — заказ в «Ожидает оплаты» (можно переоплатить).
FIX: create_payout — проверка min_withdraw и наличия реквизитов.
NEW: уведомления пользователю при payout done/rejected и payment rejected.
"""
import logging
from decimal import Decimal
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Payment, Payout, Transaction, Order, Client, Shop, Courier,
    DeliveryPayment, DeliveryOrder,
)
from utils import helpers
from services import notify

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#   ВХОДЯЩИЕ ПЛАТЕЖИ (заказы)
# ═══════════════════════════════════════════
async def get_pending_payments(session: AsyncSession) -> list:
    result = await session.execute(
        select(Payment).where(Payment.status == "pending").order_by(Payment.created_at.asc())
    )
    return result.scalars().all()


async def mark_payment_rejected(session: AsyncSession, order_id: int, admin_id: int):
    """
    FIX: отклонение оплаты возвращает заказ в «Ожидает оплаты».
    FIX bug5: now_moscow.
    Уведомляет клиента.
    """
    result = await session.execute(select(Payment).where(Payment.order_id == order_id))
    payment = result.scalar_one_or_none()
    if not payment or payment.status != "pending":
        return False

    payment.status = "rejected"
    payment.admin_id = admin_id
    payment.confirmed_at = helpers.now_moscow()

    # Заказ — обратно в «Ожидает оплаты» (не отменяем, клиент может переоплатить)
    o_r = await session.execute(select(Order).where(Order.id == order_id))
    order = o_r.scalar_one_or_none()
    if order:
        order.payment_status = "pending"
        order.status = "pending"

    await session.commit()

    # Уведомление клиента
    if order:
        try:
            c_r = await session.execute(select(Client).where(Client.id == order.client_id))
            client = c_r.scalar_one_or_none()
            if client and client.tg_id:
                text = (
                    f"❌ <b>Оплата по заказу #{order_id} не подтверждена.</b>\n\n"
                    f"Проверьте комментарий к переводу и попробуйте снова.\n"
                    f"🆘 Поддержка: {config.SUPPORT_TG}"
                )
                await notify.send_notification(
                    session=session, recipient_type="client",
                    recipient_id=order.client_id, text=text,
                )
        except Exception as e:
            log.error(f"Уведомление клиента #{order.client_id}: {e}")

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
    if not d or d.payment_status == "confirmed":
        return None

    d.payment_status = "confirmed"
    d.status = "confirmed"

    p_r = await session.execute(select(DeliveryPayment).where(DeliveryPayment.delivery_id == delivery_id))
    p = p_r.scalar_one_or_none()
    if p and p.status == "pending":
        p.status = "confirmed"
        p.admin_id = admin_id
        p.confirmed_at = helpers.now_moscow()  # FIX bug5

    await session.commit()
    return d


async def reject_delivery_payment(session: AsyncSession, delivery_id: int, admin_id: int):
    d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
    d = d_r.scalar_one_or_none()
    if not d or d.status == "cancel":
        return None

    d.status = "cancel"
    d.payment_status = "rejected"

    p_r = await session.execute(select(DeliveryPayment).where(DeliveryPayment.delivery_id == delivery_id))
    p = p_r.scalar_one_or_none()
    if p and p.status == "pending":
        p.status = "rejected"
        p.admin_id = admin_id
        p.confirmed_at = helpers.now_moscow()  # FIX bug5

    await session.commit()
    return d


# ═══════════════════════════════════════════
#   ВЫПЛАТЫ
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
    FIX (P0 race): атомарное списание через UPDATE WHERE balance >= amount.
    FIX: проверка min_withdraw и наличия реквизитов.
    """
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        return None

    # FIX: проверка минимальной суммы
    if user_type == "courier":
        min_w = Decimal(str(config.COURIER_MIN_WITHDRAW))
    elif user_type == "client":
        min_w = Decimal(str(config.CLIENT_MIN_WITHDRAW))
    else:
        min_w = Decimal("0")
    if amount < min_w:
        return None

    # FIX: проверка реквизитов
    target = sbp_phone if method == "sbp" else card_number
    if not target:
        return None

    # FIX (P0 race): атомарное списание
    if user_type == "courier":
        res = await session.execute(
            update(Courier).where(Courier.id == user_id, Courier.balance >= amount)
            .values(balance=Courier.balance - amount)
        )
    elif user_type == "shop":
        res = await session.execute(
            update(Shop).where(Shop.id == user_id, Shop.balance >= amount)
            .values(balance=Shop.balance - amount)
        )
    elif user_type == "client":
        res = await session.execute(
            update(Client).where(Client.id == user_id, Client.balance >= amount)
            .values(balance=Client.balance - amount)
        )
    else:
        return None

    if res.rowcount != 1:
        await session.rollback()
        return None

    # Комиссия
    commission = Decimal("0.00")
    if user_type == "client":
        commission = (amount * Decimal(str(config.CLIENT_WITHDRAW_COMMISSION)) / Decimal("100")).quantize(Decimal("0.01"))
    # курьер/магазин — 0% (config.COURIER/SHOP_WITHDRAW_COMMISSION = 0)

    amount_to_pay = amount - commission

    payout = Payout(
        user_type=user_type, user_id=user_id,
        amount=amount, commission=commission, amount_to_pay=amount_to_pay,
        method=method, target=target,
        card_number=card_number, bank_name=bank_name, card_holder=card_holder or holder_name,
        status="pending",
    )
    session.add(payout)

    session.add(Transaction(
        user_type=user_type, user_id=user_id, account_type="main",
        amount=-amount, type="payout_freeze", comment="Заявка на выплату (заморозка)",
    ))

    await session.commit()
    return payout


async def get_pending_payouts(session: AsyncSession) -> list:
    result = await session.execute(
        select(Payout).where(Payout.status == "pending").order_by(Payout.created_at.asc())
    )
    return result.scalars().all()


async def mark_payout_done(session: AsyncSession, payout_id: int, admin_id: int):
    """
    FIX: только из "pending" (раньше можно было «выплатить» отклонённую).
    FIX bug5: now_moscow.
    """
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()

    if not payout or payout.status != "pending":
        return None

    payout.status = "done"
    payout.paid_at = helpers.now_moscow()  # FIX bug5
    payout.admin_id = admin_id
    await session.commit()

    # Уведомление получателю
    try:
        _text = f"✅ <b>Выплата {helpers.money(payout.amount_to_pay)} зачислена!</b>"
        await notify.send_notification(
            session=session, recipient_type=payout.user_type,
            recipient_id=payout.user_id, text=_text,
        )
    except Exception as e:
        log.error(f"Уведомление о выплате #{payout_id}: {e}")

    return payout


async def mark_payout_rejected(session: AsyncSession, payout_id: int, admin_id: int):
    result = await session.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()

    if not payout or payout.status in ("rejected", "done"):
        return None

    # Возврат на баланс (атомарно)
    if payout.user_type == "courier":
        await session.execute(update(Courier).where(Courier.id == payout.user_id).values(balance=Courier.balance + payout.amount))
    elif payout.user_type == "shop":
        await session.execute(update(Shop).where(Shop.id == payout.user_id).values(balance=Shop.balance + payout.amount))
    elif payout.user_type == "client":
        await session.execute(update(Client).where(Client.id == payout.user_id).values(balance=Client.balance + payout.amount))

    payout.status = "rejected"
    payout.admin_id = admin_id
    session.add(Transaction(
        user_type=payout.user_type, user_id=payout.user_id, account_type="main",
        amount=payout.amount, type="payout_rejected", comment=f"Возврат заявки на выплату #{payout.id}",
    ))
    await session.commit()

    # Уведомление
    try:
        _text = (
            f"❌ <b>Выплата {helpers.money(payout.amount)} отклонена.</b>\n\n"
            f"Средства возвращены на баланс."
        )
        await notify.send_notification(
            session=session, recipient_type=payout.user_type,
            recipient_id=payout.user_id, text=_text,
        )
    except Exception as e:
        log.error(f"Уведомление об отклонении выплаты #{payout_id}: {e}")

    return payout


# ═══════════════════════════════════════════
#   ВОЗВРАТЫ И СВОДКА
# ═══════════════════════════════════════════
async def refund_to_balance(session: AsyncSession, client_id: int, amount: Decimal, order_id: int = None):
    await session.execute(update(Client).where(Client.id == client_id).values(balance=Client.balance + amount))
    session.add(Transaction(
        user_type="client", user_id=client_id, account_type="main",
        amount=amount, type="refund", order_id=order_id, comment="Возврат на баланс",
    ))
    await session.commit()


async def get_finance_summary(session: AsyncSession) -> dict:
    # Общая касса (оплаченные заказы)
    total_result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")
    )
    total_income = Decimal(str(total_result.scalar() or 0))

    # Доход платформы (только выполненные заказы + чаевые)
    orders_result = await session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.platform_income), 0))
        .where(Order.status == "done")
    )
    row = orders_result.first()
    done_orders = row[0] or 0
    platform_income = Decimal(str(row[1] or 0))

    # Долг магазинам
    shops_result = await session.execute(select(func.coalesce(func.sum(Shop.balance), 0)).where(Shop.balance > 0))
    shops_balance = Decimal(str(shops_result.scalar() or 0))

    # Долг курьерам
    couriers_result = await session.execute(select(func.coalesce(func.sum(Courier.balance), 0)).where(Courier.balance > 0))
    couriers_balance = Decimal(str(couriers_result.scalar() or 0))

    # Ожидают выплаты
    pending_result = await session.execute(
        select(func.coalesce(func.sum(Payout.amount_to_pay), 0)).where(Payout.status == "pending")
    )
    pending_payouts = Decimal(str(pending_result.scalar() or 0))

    return {
        "total_income": total_income,
        "platform_income": platform_income,
        "done_orders": done_orders,
        "shops_balance": shops_balance,
        "couriers_balance": couriers_balance,
        "pending_payouts": pending_payouts,
    }


async def get_orders_in_work(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(Order.id)).where(
            Order.status.in_(["new", "pending", "wait", "going", "picked", "delivering", "at_client"])
        )
    )
    return result.scalar() or 0


async def get_user_transactions(session: AsyncSession, user_type: str, user_id: int, limit: int = 30) -> list:
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_type == user_type, Transaction.user_id == user_id,
        ).order_by(Transaction.id.desc()).limit(limit)
    )
    return result.scalars().all()


# ═══════════════════════════════════════════
#   ПОПОЛНЕНИЕ БАЛАНСА (админом)
# ═══════════════════════════════════════════
async def topup_shop_balance(session: AsyncSession, shop_id: int, amount: Decimal):
    if amount <= 0:
        return
    await session.execute(update(Shop).where(Shop.id == shop_id).values(balance=Shop.balance + amount))
    session.add(Transaction(
        user_type="shop", user_id=shop_id, account_type="main",
        amount=amount, type="topup", comment="Пополнение админом",
    ))
    await session.commit()


async def topup_courier_balance(session: AsyncSession, courier_id: int, amount: Decimal):
    if amount <= 0:
        return
    await session.execute(update(Courier).where(Courier.id == courier_id).values(balance=Courier.balance + amount))
    session.add(Transaction(
        user_type="courier", user_id=courier_id, account_type="main",
        amount=amount, type="topup", comment="Пополнение админом",
    ))
    await session.commit()


# ═══════════════════════════════════════════
#   ЭКСПОРТ CSV (магазин)
# ═══════════════════════════════════════════
async def export_shop_orders_csv(session: AsyncSession, shop_id: int) -> str:
    """CSV с BOM для Excel. FIX: ; в полях заменяем на , чтобы не ломать."""
    orders = await session.execute(
        select(Order).where(Order.shop_id == shop_id).order_by(Order.id.desc())
    )
    orders = orders.scalars().all()

    lines = ["\ufeff№;Дата;Клиент;Телефон;Адрес;Сумма;Статус"]
    for o in orders:
        name = (o.client_name or "").replace('"', '""').replace(";", ",")
        address = (o.address or "").replace('"', '""').replace(";", ",")
        lines.append(
            f'{o.id};{o.created_at.strftime("%d.%m.%Y")};'
            f'"{name}";{o.client_phone};"{address}";'
            f'{o.total_price};{o.status}'
        )
    return "\n".join(lines)
