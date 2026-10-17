# -*- coding: utf-8 -*-
"""
Flowers Express — логика заказов
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
from services import bonuses as bonuses_service
from utils import helpers
from services import notify

# ═══════════════════════════════════════════
#   РАСЧЁТЫ
# ═══════════════════════════════════════════
def calculate_cart_total(items: list, distance_km: float = 0) -> dict:
    items_total = Decimal("0.00")
    bouquets_count = 0

    for item in items:
        product = item["product"]
        qty = item["quantity"]
        price = Decimal(str(product.client_price))
        items_total += price * qty
        if product.category == "bouquets":
            bouquets_count += qty

    discount = Decimal("0.00")
    if bouquets_count >= config.BULK_DISCOUNT_MIN_BOUQUETS:
        discount = (items_total * Decimal(str(config.BULK_DISCOUNT_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))

    zone = config.get_delivery_zone(distance_km)
    delivery = Decimal("0.00") if zone is None else Decimal(str(zone["client_pays"]))

    total = items_total - discount + delivery

    return {
        "items_total": items_total, 
        "discount": discount, 
        "delivery": delivery,
        "total": total.quantize(Decimal("0.01")), 
        "bouquets_count": bouquets_count, 
        "zone": zone,
    }

def calculate_platform_income(items: list, distance_km: float, discount: Decimal) -> Decimal:
    markup_total = Decimal("0.00")
    for item in items:
        markup_total += Decimal(str(item["product"].markup)) * item["quantity"]

    zone = config.get_delivery_zone(distance_km)
    delivery_income = Decimal(str(zone["platform_gets"])) if zone else Decimal("0.00")

    income = markup_total + delivery_income - discount
    return max(income, Decimal("0.00")).quantize(Decimal("0.01"))

# ═══════════════════════════════════════════
#   ПРОМОКОД
# ═══════════════════════════════════════════
async def check_promo(session: AsyncSession, code: str) -> Promo | None:
    result = await session.execute(select(Promo).where(Promo.code == code, Promo.is_active == True))
    return result.scalar_one_or_none()

async def calc_promo_discount(session: AsyncSession, promo: Promo, items_total: Decimal, client_id: int) -> Decimal:
    if promo.valid_until and promo.valid_until < helpers.today_moscow(): 
        return Decimal("0.00")
    if promo.max_uses > 0 and promo.used_count >= promo.max_uses: 
        return Decimal("0.00")
    if items_total < promo.min_order: 
        return Decimal("0.00")

    used = await session.execute(select(PromoUse).where(PromoUse.promo_id == promo.id, PromoUse.client_id == client_id))
    if used.scalar_one_or_none(): 
        return Decimal("0.00")

    if promo.discount_type == "percent":
        return (items_total * promo.discount_value / Decimal("100")).quantize(Decimal("0.01"))
    return promo.discount_value.quantize(Decimal("0.01"))

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
    if not address or not address.strip():
        return None
        
    today = helpers.today_moscow()
    if delivery_date < today:
        return None
    if (delivery_date - today).days > config.PREORDER_DAYS_AHEAD:
        return None
        
    valid_slots = []
    for period in config.DELIVERY_SLOTS.values():
        valid_slots.extend(period["slots"])
    if delivery_slot not in valid_slots:
        return None

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

    shop_res = await session.execute(select(Shop).where(Shop.id == shop_id))
    shop = shop_res.scalar_one_or_none()
    if not shop or shop.status != "active" or shop.is_paused:
        return None

    items = []
    for ci in cart_items:
        p_result = await session.execute(select(Product).where(Product.id == ci.product_id))
        product = p_result.scalar_one_or_none()
        if product and product.is_active:
            items.append({"product": product, "quantity": ci.quantity})

    if not items: return None

    totals = calculate_cart_total(items, distance_km)
    if totals["zone"] is None: return None

    promo_discount = Decimal("0.00")
    promo_obj = None
    if promo_code:
        promo_obj = await check_promo(session, promo_code)
        if promo_obj:
            promo_discount = await calc_promo_discount(session, promo_obj, totals["items_total"], client_id)

    final_total = totals["total"] - promo_discount
    total_discount = totals["discount"] + promo_discount

    platform_income = calculate_platform_income(items, distance_km, total_discount)
    is_preorder = delivery_date > today

    order = Order(
        client_id=client_id, shop_id=shop_id, status="pending", payment_status="pending",
        address=address.strip(), client_name=client_name.strip(), client_phone=client_phone, comment=comment,
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
            photo_id=product.photo_id,
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
