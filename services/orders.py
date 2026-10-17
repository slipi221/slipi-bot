# -*- coding: utf-8 -*-
"""
SLIPI — логика заказов
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Order, OrderItem, CartItem, Product, Shop, Client, Courier,
    CourierDailyStat, Transaction, Payment, Promo, PromoUse,
    DeliveryOrder, DeliveryPayment, ChangeLog,
)
from utils import helpers
from services import notify

# ═══════════════════════════════════════════
#   РАСЧЁТЫ
# ═══════════════════════════════════════════
def calculate_cart_total(items: list, distance_km: float = 0) -> dict:
    items_total = Decimal("0")
    bouquets_count = 0

    for item in items:
        product = item["product"]
        qty = item["quantity"]
        price = Decimal(str(product.client_price))
        items_total += price * qty
        if product.category == "bouquets":
            bouquets_count += qty

    discount = Decimal("0")
    if bouquets_count >= config.BULK_DISCOUNT_MIN_BOUQUETS:
        discount = (items_total * Decimal(str(config.BULK_DISCOUNT_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))

    zone = config.get_delivery_zone(distance_km)
    delivery = Decimal("0") if zone is None else Decimal(str(zone["client_pays"]))

    total = items_total - discount + delivery

    return {
        "items_total": items_total, "discount": discount, "delivery": delivery,
        "total": total.quantize(Decimal("0.01")), "bouquets_count": bouquets_count, "zone": zone,
    }

def calculate_platform_income(items: list, distance_km: float, discount: Decimal) -> Decimal:
    """
    ИСПРАВЛЕНО (Баг #5): Платформа берет на себя скидку клиенту.
    Мы вычитаем скидку из дохода платформы, чтобы баланс сходился.
    """
    markup_total = Decimal("0")
    for item in items:
        markup_total += Decimal(str(item["product"].markup)) * item["quantity"]

    zone = config.get_delivery_zone(distance_km)
    delivery_income = Decimal(str(zone["platform_gets"])) if zone else Decimal("0")

    # Доход = (Наценка + Доставка платформы) - Скидка клиенту
    income = markup_total + delivery_income - discount
    return max(income, Decimal("0")).quantize(Decimal("0.01"))

# ═══════════════════════════════════════════
#   ПРОМОКОД
# ═══════════════════════════════════════════
async def check_promo(session: AsyncSession, code: str) -> Promo | None:
    result = await session.execute(select(Promo).where(Promo.code == code, Promo.is_active == True))
    return result.scalar_one_or_none()

async def calc_promo_discount(session: AsyncSession, promo: Promo, total: Decimal, client_id: int) -> Decimal:
    if promo.valid_until and promo.valid_until < date.today(): return Decimal("0")
    if promo.max_uses > 0 and promo.used_count >= promo.max_uses: return Decimal("0")
    if total < promo.min_order: return Decimal("0")

    used = await session.execute(select(PromoUse).where(PromoUse.promo_id == promo.id, PromoUse.client_id == client_id))
    if used.scalar_one_or_none(): return Decimal("0")

    if promo.discount_type == "percent":
        return (total * promo.discount_value / Decimal("100")).quantize(Decimal("0.01"))
    return promo.discount_value

# ═══════════════════════════════════════════
#   СОЗДАНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
async def create_order_from_cart(
    session: AsyncSession,
    client_id: int,
    address: str,
    client_name: str,
    client_phone: str,
    delivery_date: date,
    delivery_slot: str,
    comment: str = None,
    promo_code: str = None,
    need_photo: bool = True,
    distance_km: float = 0,
) -> Order | None:
    existing = await session.execute(
        select(Order).where(Order.client_id == client_id, Order.status == "pending").order_by(Order.id.desc()).limit(1)
    )
    last = existing.scalar_one_or_none()
    if last: return last

    result = await session.execute(select(CartItem).where(CartItem.client_id == client_id))
    cart_items = result.scalars().all()
    if not cart_items: return None

    shop_ids = {ci.shop_id for ci in cart_items}
    if len(shop_ids) > 1: return None
    shop_id = shop_ids.pop()

    items = []
    for ci in cart_items:
        p_result = await session.execute(select(Product).where(Product.id == ci.product_id))
        product = p_result.scalar_one_or_none()
        if product and product.is_active:
            items.append({"product": product, "quantity": ci.quantity})

    if not items: return None

    totals = calculate_cart_total(items, distance_km)
    if totals["zone"] is None: return None

    promo_discount = Decimal("0")
    promo_obj = None
    if promo_code:
        promo_obj = await check_promo(session, promo_code)
        if promo_obj:
            promo_discount = await calc_promo_discount(session, promo_obj, totals["total"], client_id)

    final_total = totals["total"] - promo_discount
    total_discount = totals["discount"] + promo_discount

    platform_income = calculate_platform_income(items, distance_km, total_discount)
    is_preorder = delivery_date > date.today()

    # Статус "pending" = ожидает оплаты
    order = Order(
        client_id=client_id, shop_id=shop_id, status="pending", payment_status="pending",
        address=address, client_name=client_name, client_phone=client_phone, comment=comment,
        delivery_date=delivery_date, delivery_slot=delivery_slot, is_preorder=is_preorder,
        items_total=totals["items_total"], delivery_price=totals["delivery"],
        discount=total_discount, total_price=final_total, platform_income=platform_income,
        courier_fee=Decimal(str(totals["zone"]["courier_gets"])),
        need_delivery_photo=need_photo, promo_code=promo_code,
    )
    session.add(order)
    await session.flush()

    for item in items:
        product = item["product"]
        qty = item["quantity"]
        session.add(OrderItem(
            order_id=order.id, product_id=product.id, title=product.title, category=product.category,
            shop_price=product.shop_price, markup=product.markup, client_price=product.client_price,
            quantity=qty, total=Decimal(str(product.client_price)) * qty,
            photo_id=product.photo_id, # ИСПРАВЛЕНО (Баг #12)
        ))
        product.order_count += qty

    for ci in cart_items:
        await session.delete(ci)

    session.add(Payment(order_id=order.id, client_id=client_id, amount=final_total, status="pending"))

    if promo_obj:
        promo_obj.used_count += 1
        session.add(PromoUse(promo_id=promo_obj.id, client_id=client_id, order_id=order.id))

    await session.commit()
    return order

# ═══════════════════════════════════════════
#   ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
# ═══════════════════════════════════════════
async def confirm_payment(session: AsyncSession, order_id: int, admin_id: int):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order: return None

    order.payment_status = "confirmed"
    order.status = "new" 
    order.wait_started_at = datetime.now() 

    p_result = await session.execute(select(Payment).where(Payment.order_id == order_id))
    payment = p_result.scalar_one_or_none()
    if payment:
        payment.status = "confirmed"
        payment.admin_id = admin_id
        payment.confirmed_at = datetime.now()

    shop_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = shop_result.scalar_one_or_none()
    if shop:
        shop.total_orders += 1

    await session.commit()

    # ИСПРАВЛЕНО (Баг #4): Уведомление магазину
    if shop:
        from keyboards import shop_order_new
        
        is_shop_awake = shop.is_on_shift and not shop.is_paused
        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ #{order.id}</b>\n\n"
            f"📍 {order.address}\n👤 {order.client_name}, {order.client_phone}\n"
            f"📅 {helpers.format_date(order.delivery_date)} | 🕒 {order.delivery_slot or '—'}\n"
            f"💰 {helpers.money(order.total_price)}"
        )
        await notify.send_notification(
            session=session, recipient_type="shop", recipient_id=shop.id, text=text,
            reply_markup=shop_order_new(order.id).model_dump(exclude_none=True),
            force_outbox=not is_shop_awake
        )
    return order

# ═══════════════════════════════════════════
#   ВЗЯТИЕ И СМЕНА СТАТУСА
# ═══════════════════════════════════════════
async def take_order(session: AsyncSession, order_id: int, courier_id: int) -> bool:
    c_result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = c_result.scalar_one_or_none()
    if not courier or courier.courier_state != "on": return False

    result = await session.execute(
        update(Order).where(Order.id == order_id, Order.status == "wait", Order.courier_id.is_(None))
        .values(courier_id=courier_id, status="going", taken_at=datetime.now())
    )
    await session.commit()
    return result.rowcount == 1

async def update_order_status(session: AsyncSession, order_id: int, new_status: str):
    await session.execute(update(Order).where(Order.id == order_id).values(status=new_status))
    await session.commit()

# ═══════════════════════════════════════════
#   ЗАВЕРШЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
async def complete_order(session: AsyncSession, order_id: int):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.status == "done": return None

    order.status = "done"
    order.delivered_at = datetime.now()

    # Курьеру (с учетом буста)
    courier_fee = Decimal(str(order.courier_fee or 0))
    courier_fee += Decimal(str(order.boost_amount or 0))

    items_result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    order_items = items_result.scalars().all()
    shop_sum = sum(Decimal(str(oi.shop_price)) * oi.quantity for oi in order_items)

    await session.execute(update(Shop).where(Shop.id == order.shop_id).values(balance=Shop.balance + shop_sum))

    if order.courier_id:
        await session.execute(
            update(Courier).where(Courier.id == order.courier_id)
            .values(balance=Courier.balance + courier_fee, total_orders=Courier.total_orders + 1)
        )
        today_stat = await session.execute(
            select(CourierDailyStat).where(CourierDailyStat.courier_id == order.courier_id, CourierDailyStat.date == date.today())
        )
        stat = today_stat.scalar_one_or_none()
        if stat:
            stat.completed_orders += 1
            stat.earned += courier_fee
        else:
            session.add(CourierDailyStat(courier_id=order.courier_id, date=date.today(), completed_orders=1, earned=courier_fee))

    session.add(Transaction(user_type="shop", user_id=order.shop_id, amount=shop_sum, type="order_payment", order_id=order_id))
    if order.courier_id:
        session.add(Transaction(user_type="courier", user_id=order.courier_id, amount=courier_fee, type="order_payment", order_id=order_id))
    session.add(Transaction(user_type="platform", user_id=0, amount=order.platform_income, type="order_income", order_id=order_id))

    await session.commit()
    return order

# ═══════════════════════════════════════════
#   ОТМЕНА И РЕДАКТИРОВАНИЕ
# ═══════════════════════════════════════════
async def cancel_order(session: AsyncSession, order_id: int, reason: str = None, cancelled_by: str = "shop", refund: bool = True):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.status in ("picked", "delivering", "at_client", "done"): return None

    order.status = "cancel"
    order.cancel_reason = reason
    order.cancelled_by = cancelled_by

    if refund and order.payment_status == "confirmed":
        await session.execute(update(Client).where(Client.id == order.client_id).values(balance=Client.balance + order.total_price))
        session.add(Transaction(user_type="client", user_id=order.client_id, amount=order.total_price, type="refund", order_id=order_id))
        order.payment_status = "refunded"

    if cancelled_by == "shop":
        await session.execute(update(Shop).where(Shop.id == order.shop_id).values(rejected_count=Shop.rejected_count + 1))

    await session.commit()
    return order

async def edit_order_field(session: AsyncSession, order_id: int, field: str, new_value, changed_by: str, changed_by_id: int) -> bool:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.status in ("picked", "delivering", "at_client", "done", "cancel"): return False

    old_value = getattr(order, field, None)
    setattr(order, field, new_value)
    session.add(ChangeLog(object_type="order", object_id=order_id, field=field, old_value=str(old_value) if old_value else None, new_value=str(new_value), changed_by=changed_by, changed_by_id=changed_by_id))
    await session.commit()
    return True

async def edit_delivery_field(session: AsyncSession, delivery_id: int, field: str, new_value, changed_by: str, changed_by_id: int) -> bool:
    result = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
    d = result.scalar_one_or_none()
    if not d or d.status in ("picked", "at_client", "done", "cancel"): return False

    old_value = getattr(d, field, None)
    setattr(d, field, new_value)
    session.add(ChangeLog(object_type="delivery", object_id=delivery_id, field=field, old_value=str(old_value) if old_value else None, new_value=str(new_value), changed_by=changed_by, changed_by_id=changed_by_id))
    await session.commit()
    return True

# ═══════════════════════════════════════════
#   ПОЛУЧЕНИЕ ЗАКАЗОВ
# ═══════════════════════════════════════════
async def get_client_orders(session: AsyncSession, client_id: int, limit: int = 20):
    result = await session.execute(select(Order).where(Order.client_id == client_id).order_by(Order.id.desc()).limit(limit))
    return result.scalars().all()

async def get_shop_orders(session: AsyncSession, shop_id: int, limit: int = 50):
    result = await session.execute(select(Order).where(Order.shop_id == shop_id).order_by(Order.id.desc()).limit(limit))
    return result.scalars().all()

async def get_free_orders(session: AsyncSession, limit: int = 20):
    result = await session.execute(
        select(Order).where(Order.status == "wait", Order.payment_status == "confirmed", Order.courier_id.is_(None))
        .order_by(Order.id.asc()).limit(limit)
    )
    return result.scalars().all()

async def get_courier_active_orders(session: AsyncSession, courier_id: int):
    result = await session.execute(
        select(Order).where(Order.courier_id == courier_id, Order.status.in_(["going", "picked", "delivering", "at_client"])).order_by(Order.id.desc())
    )
    return result.scalars().all()

# ═══════════════════════════════════════════
#   ПОВТОРИТЬ ЗАКАЗ
# ═══════════════════════════════════════════
async def repeat_order(session: AsyncSession, order_id: int, client_id: int) -> dict:
    await session.execute(delete(CartItem).where(CartItem.client_id == client_id))
    items_result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = items_result.scalars().all()

    added, skipped = 0, 0
    for oi in items:
        p_result = await session.execute(select(Product).where(Product.id == oi.product_id, Product.is_active == True))
        product = p_result.scalar_one_or_none()
        if not product:
            skipped += 1
            continue
        session.add(CartItem(client_id=client_id, product_id=product.id, shop_id=product.shop_id, quantity=oi.quantity))
        added += 1

    await session.commit()
    return {"ok": added > 0, "added": added, "skipped": skipped}
