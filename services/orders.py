# -*- coding: utf-8 -*-
"""
SLIPI — логика работы с заказами
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Order, OrderItem, CartItem, Product, Shop, Client,
    Courier, CourierDailyStat, Transaction, Payment,
)
from utils import helpers


# ═══════════════════════════════════════════
#   РАСЧЁТЫ
# ═══════════════════════════════════════════
def calculate_cart_total(items: list) -> dict:
    """
    Считает итоги корзины.
    items — список dict {product, quantity}
    """
    items_total = Decimal("0")
    bouquets_count = 0

    for item in items:
        product = item["product"]
        qty = item["quantity"]
        price = Decimal(str(product.client_price))
        items_total += price * qty
        if product.category == "bouquets":
            bouquets_count += qty

    # Скидка 3% если 3+ букетов
    discount = Decimal("0")
    if bouquets_count >= config.BULK_DISCOUNT_MIN_BOUQUETS:
        discount = (items_total * Decimal(str(config.BULK_DISCOUNT_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))

    delivery = Decimal(str(config.DELIVERY_PRICE))
    total = items_total - discount + delivery

    return {
        "items_total": items_total,
        "discount": discount,
        "delivery": delivery,
        "total": total.quantize(Decimal("0.01")),
        "bouquets_count": bouquets_count,
    }


def calculate_platform_income(items: list) -> Decimal:
    """Считает доход платформы (наценки + комиссия с доставки)."""
    markup_total = Decimal("0")
    for item in items:
        product = item["product"]
        qty = item["quantity"]
        markup_total += Decimal(str(product.markup)) * qty

    delivery_commission = Decimal(str(config.get_platform_fee()))
    return (markup_total + delivery_commission).quantize(Decimal("0.01"))


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
) -> Order | None:
    """Создаёт заказ из корзины клиента. Возвращает Order или None."""
    # Берём корзину
    result = await session.execute(
        select(CartItem).where(CartItem.client_id == client_id)
    )
    cart_items = result.scalars().all()
    if not cart_items:
        return None

    # Проверяем, что все товары из одного магазина
    shop_ids = {ci.shop_id for ci in cart_items}
    if len(shop_ids) > 1:
        return None
    shop_id = shop_ids.pop()

    # Загружаем товары
    items = []
    for ci in cart_items:
        p_result = await session.execute(
            select(Product).where(Product.id == ci.product_id)
        )
        product = p_result.scalar_one_or_none()
        if product:
            items.append({"product": product, "quantity": ci.quantity})

    if not items:
        return None

    # Считаем итоги
    totals = calculate_cart_total(items)
    platform_income = calculate_platform_income(items)

    # Скидка от промокода
    promo_discount = Decimal("0")
    if promo_code:
        promo_discount = await apply_promo(session, promo_code, totals["total"], client_id)

    final_total = totals["total"] - promo_discount

    is_preorder = delivery_date > date.today()

    order = Order(
        client_id=client_id,
        shop_id=shop_id,
        status="new",
        payment_status="pending",
        address=address,
        client_name=client_name,
        client_phone=client_phone,
        comment=comment,
        delivery_date=delivery_date,
        delivery_slot=delivery_slot,
        is_preorder=is_preorder,
        items_total=totals["items_total"],
        delivery_price=totals["delivery"],
        discount=totals["discount"] + promo_discount,
        total_price=final_total,
        platform_income=platform_income,
        wait_started_at=datetime.now() if not is_preorder else None,
        promo_code=promo_code,
    )
    session.add(order)
    await session.flush()

    # Позиции заказа
    for item in items:
        product = item["product"]
        qty = item["quantity"]
        oi = OrderItem(
            order_id=order.id,
            product_id=product.id,
            title=product.title,
            category=product.category,
            shop_price=product.shop_price,
            markup=product.markup,
            client_price=product.client_price,
            quantity=qty,
            total=Decimal(str(product.client_price)) * qty,
        )
        session.add(oi)
        # Увеличиваем счётчик заказов товара
        product.order_count += qty

    # Очищаем корзину
    for ci in cart_items:
        await session.delete(ci)

    # Запись в payments
    payment = Payment(
        order_id=order.id,
        client_id=client_id,
        amount=final_total,
        status="pending",
    )
    session.add(payment)

    await session.commit()
    return order


# ═══════════════════════════════════════════
#   ПРОМОКОДЫ
# ═══════════════════════════════════════════
async def apply_promo(session: AsyncSession, code: str, total: Decimal, client_id: int) -> Decimal:
    """Применяет промокод, возвращает сумму скидки."""
    from models import Promo, PromoUse

    result = await session.execute(
        select(Promo).where(Promo.code == code, Promo.is_active == True)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        return Decimal("0")

    if promo.valid_until and promo.valid_until < date.today():
        return Decimal("0")
    if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
        return Decimal("0")
    if total < promo.min_order:
        return Decimal("0")

    # Проверяем, не использовал ли клиент
    used = await session.execute(
        select(PromoUse).where(
            PromoUse.promo_id == promo.id,
            PromoUse.client_id == client_id,
        )
    )
    if used.scalar_one_or_none():
        return Decimal("0")

    if promo.discount_type == "percent":
        discount = (total * promo.discount_value / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount = promo.discount_value

    promo.used_count += 1
    return discount


# ═══════════════════════════════════════════
#   ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
# ═══════════════════════════════════════════
async def confirm_payment(session: AsyncSession, order_id: int, admin_id: int):
    """Админ подтвердил оплату — заказ идёт магазину."""
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        return None

    order.payment_status = "confirmed"
    order.status = "wait"
    order.wait_started_at = datetime.now()

    # Обновляем платёж
    p_result = await session.execute(
        select(Payment).where(Payment.order_id == order_id)
    )
    payment = p_result.scalar_one_or_none()
    if payment:
        payment.status = "confirmed"
        payment.admin_id = admin_id
        payment.confirmed_at = datetime.now()

    # Плюс к обороту магазина
    shop_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = shop_result.scalar_one_or_none()
    if shop:
        shop.total_orders += 1

    await session.commit()
    return order


# ═══════════════════════════════════════════
#   ВЗЯТИЕ ЗАКАЗА КУРЬЕРОМ (атомарно!)
# ═══════════════════════════════════════════
async def take_order(session: AsyncSession, order_id: int, courier_id: int) -> bool:
    """
    Атомарно берёт заказ курьером.
    Возвращает True если успех, False если уже занят.
    """
    result = await session.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == "wait",
            Order.courier_id.is_(None),
        )
        .values(
            courier_id=courier_id,
            status="going",
            taken_at=datetime.now(),
        )
    )
    await session.commit()
    return result.rowcount == 1


# ═══════════════════════════════════════════
#   СМЕНА СТАТУСА
# ═══════════════════════════════════════════
async def update_order_status(session: AsyncSession, order_id: int, new_status: str):
    await session.execute(
        update(Order).where(Order.id == order_id).values(status=new_status)
    )
    await session.commit()


# ═══════════════════════════════════════════
#   ЗАВЕРШЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
async def complete_order(session: AsyncSession, order_id: int):
    """Заказ доставлен. Начисляем деньги магазину и курьеру."""
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.status == "done":
        return None

    order.status = "done"
    order.delivered_at = datetime.now()

    # Считаем заработок курьера
    courier_fee = Decimal(str(config.get_courier_fee(float(order.delivery_price))))
    courier_fee += Decimal(str(order.boost_amount))

    # Считаем сумму магазину
    items_result = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order_id)
    )
    order_items = items_result.scalars().all()
    shop_sum = sum(Decimal(str(oi.shop_price)) * oi.quantity for oi in order_items)

    # Магазину на баланс
    await session.execute(
        update(Shop).where(Shop.id == order.shop_id).values(balance=Shop.balance + shop_sum)
    )

    # Курьеру на баланс
    if order.courier_id:
        await session.execute(
            update(Courier).where(Courier.id == order.courier_id)
            .values(balance=Courier.balance + courier_fee, total_orders=Courier.total_orders + 1)
        )
        # Статистика дня
        today_stat = await session.execute(
            select(CourierDailyStat).where(
                CourierDailyStat.courier_id == order.courier_id,
                CourierDailyStat.date == date.today(),
            )
        )
        stat = today_stat.scalar_one_or_none()
        if stat:
            stat.completed_orders += 1
            stat.earned += courier_fee
        else:
            stat = CourierDailyStat(
                courier_id=order.courier_id,
                date=date.today(),
                completed_orders=1,
                earned=courier_fee,
            )
            session.add(stat)

    # Транзакции
    session.add(Transaction(
        user_type="shop", user_id=order.shop_id, amount=shop_sum,
        type="order_payment", order_id=order_id,
    ))
    if order.courier_id:
        session.add(Transaction(
            user_type="courier", user_id=order.courier_id, amount=courier_fee,
            type="order_payment", order_id=order_id,
        ))
    session.add(Transaction(
        user_type="platform", user_id=0, amount=order.platform_income,
        type="order_income", order_id=order_id,
    ))

    await session.commit()
    return order


# ═══════════════════════════════════════════
#   ОТМЕНА ЗАКАЗА
# ═══════════════════════════════════════════
async def cancel_order(
    session: AsyncSession,
    order_id: int,
    reason: str = None,
    cancelled_by: str = "shop",
    refund: bool = True,
):
    """Отменяет заказ. Возвращает на баланс клиента."""
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        return None

    order.status = "cancel"
    order.cancel_reason = reason
    order.cancelled_by = cancelled_by

    if refund and order.payment_status == "confirmed":
        # Возврат на баланс клиента
        await session.execute(
            update(Client).where(Client.id == order.client_id)
            .values(balance=Client.balance + order.total_price)
        )
        session.add(Transaction(
            user_type="client", user_id=order.client_id,
            amount=order.total_price, type="refund", order_id=order_id,
        ))
        order.payment_status = "refunded"

    # Если магазин отклонил — считаем отказ
    if cancelled_by == "shop":
        await session.execute(
            update(Shop).where(Shop.id == order.shop_id)
            .values(rejected_count=Shop.rejected_count + 1)
        )

    await session.commit()
    return order


# ═══════════════════════════════════════════
#   ПОИСК АЛЬТЕРНАТИВНОГО МАГАЗИНА
# ═══════════════════════════════════════════
async def find_alternative_shop(session: AsyncSession, order_id: int) -> int | None:
    """Ищет другой магазин с таким же товаром."""
    items_result = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order_id)
    )
    items = items_result.scalars().all()
    if not items:
        return None

    first_product_result = await session.execute(
        select(Product).where(Product.id == items[0].product_id)
    )
    first_product = first_product_result.scalar_one_or_none()
    if not first_product:
        return None

    # Ищем такой же товар у другого магазина
    result = await session.execute(
        select(Product).where(
            Product.title == first_product.title,
            Product.category == first_product.category,
            Product.is_active == True,
            Product.shop_id != first_product.shop_id,
        ).limit(1)
    )
    alt = result.scalar_one_or_none()
    if alt:
        return alt.shop_id
    return None


# ═══════════════════════════════════════════
#   ПОЛУЧЕНИЕ ЗАКАЗОВ
# ═══════════════════════════════════════════
async def get_client_orders(session: AsyncSession, client_id: int, limit: int = 20):
    result = await session.execute(
        select(Order).where(Order.client_id == client_id)
        .order_by(Order.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def get_shop_orders(session: AsyncSession, shop_id: int, limit: int = 50):
    result = await session.execute(
        select(Order).where(Order.shop_id == shop_id)
        .order_by(Order.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def get_free_orders(session: AsyncSession, limit: int = 20):
    """Свободные заказы для курьеров."""
    result = await session.execute(
        select(Order).where(
            Order.status == "wait",
            Order.payment_status == "confirmed",
            Order.courier_id.is_(None),
        ).order_by(Order.id.asc()).limit(limit)
    )
    return result.scalars().all()


async def get_courier_active_orders(session: AsyncSession, courier_id: int):
    result = await session.execute(
        select(Order).where(
            Order.courier_id == courier_id,
            Order.status.in_(["going", "picked", "delivering", "at_client"]),
        ).order_by(Order.id.desc())
    )
    return result.scalars().all()
