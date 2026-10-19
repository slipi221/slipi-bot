# -*- coding: utf-8 -*-
"""
Flowers Express — логика заказов

FIX bug6: требование гео клиента (без lat/lon заказ не создаётся).
FIX bug7: одиночное фото — send_photo, 2+ — send_media_group.
FIX bug10: антидубль чистит корзину.
FIX bug11: промокод берётся и из client.active_promo.
FIX bug15: клиент не может отменить оплаченный заказ; «Отменить» скрыта в track_order.
FIX bug4: is_slot_past(slot, delivery_date) — новая сигнатура.
FIX bug1: все datetime — через helpers.now_moscow() (naive MSK).
NEW: бонусный счёт (client.bonus_balance) — авто-списание, Order.bonus_used.
NEW Feature 7: add_tip_to_order() — чаевые 90/10.
"""
import logging
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

log = logging.getLogger(__name__)


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
    # "fixed" — это бонусный счёт, НЕ скидка при заказе
    return Decimal("0.00")


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
) -> Order | None:
    # ВАЛИДАЦИЯ: Пустой адрес
    if not address or not address.strip():
        return None

    # ВАЛИДАЦИЯ: Дата доставки (московское время)
    today = helpers.today_moscow()
    if delivery_date < today:
        return None
    if (delivery_date - today).days > config.PREORDER_DAYS_AHEAD:
        return None

    # FIX bug4: проверка прошедшего слота — с учётом даты доставки
    if helpers.is_slot_past(delivery_slot, delivery_date):
        return None

    # ВАЛИДАЦИЯ: Существование слота
    valid_slots = []
    for period in config.DELIVERY_SLOTS.values():
        valid_slots.extend(period["slots"])
    if delivery_slot not in valid_slots:
        return None

    # Антидубль + FIX bug10: чистим корзину при возврате pending
    existing = await session.execute(
        select(Order).where(Order.client_id == client_id, Order.status == "pending").order_by(Order.id.desc()).limit(1)
    )
    last = existing.scalar_one_or_none()
    if last:
        await session.execute(delete(CartItem).where(CartItem.client_id == client_id))
        await session.commit()
        return last

    # Получаем корзину
    result = await session.execute(select(CartItem).where(CartItem.client_id == client_id))
    cart_items = result.scalars().all()
    if not cart_items:
        return None

    shop_ids = {ci.shop_id for ci in cart_items}
    if len(shop_ids) > 1:
        return None
    shop_id = shop_ids.pop()

    # Проверяем магазин
    shop_res = await session.execute(select(Shop).where(Shop.id == shop_id))
    shop = shop_res.scalar_one_or_none()
    if not shop or shop.status != "active" or shop.is_paused:
        return None

    # FIX Feature 4: если заказ на сегодня — проверяем, что магазин открыт
    if delivery_date == today:
        from services.geo import is_shop_open
        if not is_shop_open(shop):
            return None

    # FIX bug6: требуем гео клиента (без координат нельзя рассчитать расстояние)
    client_res = await session.execute(select(Client).where(Client.id == client_id))
    client = client_res.scalar_one_or_none()
    if not client or not client.lat or not client.lon:
        return None

    # Считаем расстояние
    real_distance = 0.0
    if shop.lat and shop.lon:
        real_distance = helpers.distance_km(
            float(shop.lat), float(shop.lon),
            float(client.lat), float(client.lon),
        )

    # Формируем список товаров
    items = []
    for ci in cart_items:
        p_result = await session.execute(select(Product).where(Product.id == ci.product_id))
        product = p_result.scalar_one_or_none()
        if product and product.is_active:
            items.append({"product": product, "quantity": ci.quantity})

    if not items:
        return None

    totals = calculate_cart_total(items, real_distance)
    if totals["zone"] is None:
        return None

    # FIX bug11: промокод из профиля
    effective_promo_code = promo_code
    if not effective_promo_code and client.active_promo:
        effective_promo_code = client.active_promo

    # Процентный промокод — скидка при заказе
    promo_discount = Decimal("0.00")
    promo_obj = None
    if effective_promo_code:
        promo_obj = await check_promo(session, effective_promo_code)
        if promo_obj and promo_obj.discount_type == "percent":
            promo_discount = await calc_promo_discount(session, promo_obj, totals["items_total"], client_id)
        else:
            promo_obj = None  # fixed — не скидка, обрабатывается как бонус

    total_discount = totals["discount"] + promo_discount
    after_discount = totals["total"] - promo_discount

    # Бонусный счёт (auto-apply)
    bonus_to_use = Decimal("0.00")
    bonus_available = Decimal(str(client.bonus_balance or 0))
    if bonus_available > 0:
        bonus_to_use = min(bonus_available, after_discount)

    final_total = (after_discount - bonus_to_use).quantize(Decimal("0.01"))

    platform_income = calculate_platform_income(items, real_distance, total_discount)
    is_preorder = delivery_date > today

    # Создаём заказ
    order = Order(
        client_id=client_id, shop_id=shop_id, status="pending", payment_status="pending",
        address=address.strip(), client_name=client_name.strip(), client_phone=client_phone,
        comment=comment,
        delivery_date=delivery_date, delivery_slot=delivery_slot, is_preorder=is_preorder,
        items_total=totals["items_total"], delivery_price=totals["delivery"],
        discount=total_discount, bonus_used=bonus_to_use, total_price=final_total,
        platform_income=platform_income,
        courier_fee=Decimal(str(totals["zone"]["courier_gets"])),
        need_delivery_photo=need_photo,
        promo_code=effective_promo_code if promo_obj else None,
        lat=client.lat, lon=client.lon,
    )
    session.add(order)
    await session.flush()

    # Списание бонусов
    if bonus_to_use > 0:
        client.bonus_balance -= bonus_to_use
        session.add(Transaction(
            user_type="client", user_id=client_id, account_type="bonus",
            amount=-bonus_to_use, type="order_payment_bonus",
            order_id=order.id, comment="Оплата бонусами",
        ))

    # Товары
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

    # Чистим корзину
    for ci in cart_items:
        await session.delete(ci)

    # Платёж (или авто-подтверждение, если полностью бонусами)
    if final_total > 0:
        session.add(Payment(order_id=order.id, client_id=client_id, amount=final_total, status="pending"))
    else:
        order.payment_status = "confirmed"
        order.status = "new"
        order.wait_started_at = helpers.now_moscow()
        session.add(Payment(order_id=order.id, client_id=client_id, amount=Decimal("0"), status="confirmed"))

    # Промокод использован
    if promo_obj:
        promo_obj.used_count += 1
        session.add(PromoUse(promo_id=promo_obj.id, client_id=client_id, order_id=order.id))
        if client.active_promo == effective_promo_code:
            client.active_promo = None

    await session.commit()
    return order


# ═══════════════════════════════════════════
#   ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
# ═══════════════════════════════════════════
async def confirm_payment(session: AsyncSession, order_id: int, admin_id: int):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.payment_status == "confirmed":
        return None

    order.payment_status = "confirmed"
    order.status = "new"
    order.wait_started_at = helpers.now_moscow()

    p_result = await session.execute(select(Payment).where(Payment.order_id == order_id))
    payment = p_result.scalar_one_or_none()
    if payment and payment.status == "pending":
        payment.status = "confirmed"
        payment.admin_id = admin_id
        payment.confirmed_at = helpers.now_moscow()

    shop_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = shop_result.scalar_one_or_none()

    await session.commit()

    if shop:
        from keyboards import shop_order_new
        from services.notify import send_notification
        from aiogram.types import InputMediaPhoto
        from bots import bot_shop

        is_shop_awake = shop.is_on_shift and not shop.is_paused and shop.tg_id

        items_r = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
        items = items_r.scalars().all()

        items_text = ""
        media = []
        for it in items:
            items_text += f"  • {helpers.escape(it.title)} × {it.quantity} = {helpers.money(it.total)}\n"
            if it.photo_id:
                media.append(InputMediaPhoto(media=it.photo_id))

        pay_status = "✅ <b>ОПЛАЧЕН</b>" if order.payment_status == "confirmed" else "⏳ Ожидает оплаты"

        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ #{order.id}</b>\n"
            f"💳 Статус: {pay_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌷 <b>СОСТАВ ЗАКАЗА:</b>\n"
            f"{items_text}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>КУДА ДОСТАВИТЬ:</b>\n"
            f"  {helpers.escape(order.address)}\n"
            f"👤 <b>ПОЛУЧАТЕЛЬ:</b> {helpers.escape(order.client_name)}\n"
            f"📞 <b>ТЕЛЕФОН:</b> {helpers.escape(order.client_phone)}\n"
            f"📅 <b>ДАТА:</b> {helpers.format_date(order.delivery_date)}\n"
            f"🕒 <b>ВРЕМЯ ДОСТАВКИ:</b> {order.delivery_slot or '—'}\n"
        )

        if order.comment:
            text += f"💬 <b>КОММЕНТАРИЙ:</b> {helpers.escape(order.comment)}\n"

        text += f"📸 <b>ФОТО ВРУЧЕНИЯ:</b> {'Да' if order.need_delivery_photo else 'Нет'}\n"
        text += (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>ФИНАНСЫ:</b>\n"
            f"  Стоимость букетов: {helpers.money(order.items_total)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <i>Примите заказ в течение {config.DAY_ORDER_TIMEOUT_MINUTES} минут.</i>"
        )

        if is_shop_awake:
            if media:
                if len(media) == 1:
                    try:
                        await bot_shop.send_photo(chat_id=shop.tg_id, photo=media[0].media)
                    except Exception as e:
                        log.error(f"send_photo магазину #{shop.id}: {e}")
                else:
                    try:
                        await bot_shop.send_media_group(chat_id=shop.tg_id, media=media[:10])
                    except Exception as e:
                        log.error(f"send_media_group магазину #{shop.id}: {e}")

            try:
                msg = await bot_shop.send_message(chat_id=shop.tg_id, text=text, reply_markup=shop_order_new(order.id))
                order.track_message_id = msg.message_id
                await session.commit()
            except Exception as e:
                log.error(f"send_message магазину #{shop.id}: {e}")
        else:
            await send_notification(
                session=session, recipient_type="shop", recipient_id=shop.id, text=text,
                reply_markup=shop_order_new(order.id).model_dump(exclude_none=True),
                force_outbox=True,
            )
    return order


# ═══════════════════════════════════════════
#   ВЗЯТИЕ ЗАКАЗА КУРЬЕРОМ
# ═══════════════════════════════════════════
async def take_order(session: AsyncSession, order_id: int, courier_id: int) -> bool:
    c_result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = c_result.scalar_one_or_none()

    if not courier or courier.is_blocked or courier.courier_state not in ("on", "busy"):
        return False

    result = await session.execute(
        update(Order).where(Order.id == order_id, Order.status == "wait", Order.courier_id.is_(None))
        .values(courier_id=courier_id, status="going", taken_at=helpers.now_moscow())
    )
    await session.commit()

    if result.rowcount != 1:
        return False

    o_result = await session.execute(select(Order).where(Order.id == order_id))
    order = o_result.scalar_one_or_none()

    if order and order.track_message_id:
        s_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = s_result.scalar_one_or_none()

        if shop and shop.tg_id:
            items_r = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
            items = items_r.scalars().all()

            items_text = ""
            for it in items:
                items_text += f"  • {helpers.escape(it.title)} × {it.quantity} = {helpers.money(it.total)}\n"

            text = (
                f"🔔 <b>ЗАКАЗ #{order.id}</b>\n"
                f"💳 Статус: ✅ <b>ОПЛАЧЕН</b>\n"
                f"🚴 <b>Курьер назначен</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌷 <b>СОСТАВ ЗАКАЗА:</b>\n"
                f"{items_text}"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 <b>КУДА ДОСТАВИТЬ:</b>\n"
                f"  {helpers.escape(order.address)}\n"
                f"👤 <b>ПОЛУЧАТЕЛЬ:</b> {helpers.escape(order.client_name)}\n"
                f"📞 <b>ТЕЛЕФОН:</b> {helpers.escape(order.client_phone)}\n"
                f"📅 <b>ДАТА:</b> {helpers.format_date(order.delivery_date)}\n"
                f"🕒 <b>ВРЕМЯ ДОСТАВКИ:</b> {order.delivery_slot or '—'}\n"
            )
            if order.comment:
                text += f"💬 <b>КОММЕНТАРИЙ:</b> {helpers.escape(order.comment)}\n"

            text += (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚴 <b>ВАШ КУРЬЕР:</b>\n"
                f"  👤 {helpers.escape(courier.name)}\n"
                f"  📞 {helpers.escape(courier.phone)}\n"
                f"  🚗 {helpers.escape(courier.transport)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <i>Курьер уже едет забирать заказ.</i>"
            )

            from bots import bot_shop
            from aiogram.exceptions import TelegramBadRequest
            try:
                await bot_shop.edit_message_text(chat_id=shop.tg_id, message_id=order.track_message_id, text=text)
            except TelegramBadRequest as e:
                log.error(f"edit_message_text магазину: {e}")

    await update_client_order_message(session, order_id)
    return True


# ═══════════════════════════════════════════
#   СМЕНА СТАТУСА
# ═══════════════════════════════════════════
async def update_order_status(session: AsyncSession, order_id: int, new_status: str):
    await session.execute(update(Order).where(Order.id == order_id).values(status=new_status))
    await session.commit()
    await update_client_order_message(session, order_id)


# ═══════════════════════════════════════════
#   ЗАВЕРШЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
async def complete_order(session: AsyncSession, order_id: int):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.status == "done":
        return None

    order.status = "done"
    order.delivered_at = helpers.now_moscow()

    courier_fee = Decimal(str(order.courier_fee or 0))
    courier_fee += Decimal(str(order.boost_amount or 0))

    tip_platform = Decimal("0.00")
    if order.tip_amount and order.tip_amount > 0:
        tip = Decimal(str(order.tip_amount))
        tip_platform = (tip * Decimal(str(config.TIP_PLATFORM_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
        courier_fee += tip - tip_platform

    items_result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    order_items = items_result.scalars().all()
    shop_sum = sum(Decimal(str(oi.shop_price)) * oi.quantity for oi in order_items)

    # FIX: shop.total_orders += 1 здесь (при доставке), не при оплате
    await session.execute(update(Shop).where(Shop.id == order.shop_id).values(
        balance=Shop.balance + shop_sum,
        total_orders=Shop.total_orders + 1,
    ))

    if order.courier_id:
        await session.execute(
            update(Courier).where(Courier.id == order.courier_id)
            .values(balance=Courier.balance + courier_fee, total_orders=Courier.total_orders + 1)
        )

        today_stat = await session.execute(
            select(CourierDailyStat).where(
                CourierDailyStat.courier_id == order.courier_id,
                CourierDailyStat.date == helpers.today_moscow(),
            )
        )
        stat = today_stat.scalar_one_or_none()
        if stat:
            stat.completed_orders += 1
            stat.earned += courier_fee
        else:
            session.add(CourierDailyStat(
                courier_id=order.courier_id, date=helpers.today_moscow(),
                completed_orders=1, earned=courier_fee,
            ))

    session.add(Transaction(user_type="shop", user_id=order.shop_id, amount=shop_sum, type="order_payment", order_id=order_id))
    if order.courier_id:
        session.add(Transaction(user_type="courier", user_id=order.courier_id, amount=courier_fee, type="order_payment", order_id=order_id))
    session.add(Transaction(user_type="platform", user_id=0, amount=order.platform_income, type="order_income", order_id=order_id))
    if tip_platform > 0:
        session.add(Transaction(user_type="platform", user_id=0, amount=tip_platform, type="tip_income", order_id=order_id))

    new_achievements = []
    if order.courier_id:
        c_res = await session.execute(select(Courier).where(Courier.id == order.courier_id))
        courier = c_res.scalar_one_or_none()

        if courier:
            await bonuses_service.apply_referral_percent(session, courier.id, courier_fee)
            await bonuses_service.update_courier_level(session, courier.id)
            new_achievements = await bonuses_service.check_achievements(session, courier.id)
            # FIX: возвращаем в "on" только если был "busy"
            if courier.courier_state == "busy":
                courier.courier_state = "on"

    await session.commit()

    # Уведомление магазину
    s_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = s_result.scalar_one_or_none()
    if shop and shop.tg_id:
        try:
            await notify.bot_shop.send_message(
                shop.tg_id,
                f"✅ <b>Заказ #{order.id} доставлен!</b>\n\nКурьер выполнил доставку. Спасибо за работу! 🌸",
            )
        except Exception as e:
            log.error(f"Уведомление магазину #{shop.id}: {e}")

    # Достижения
    if order.courier_id and new_achievements:
        from services.bonuses import ACHIEVEMENTS_LIST

        for code in new_achievements:
            info = next((a for a in ACHIEVEMENTS_LIST if a["code"] == code), None)
            if info:
                text = f"🏆 <b>Новое достижение!</b>\n\n{info['icon']} <b>{info['title']}</b>\n{info['description']}"
                await notify.send_notification(
                    session=session, recipient_type="courier", recipient_id=order.courier_id, text=text,
                )

    await update_client_order_message(session, order_id)
    return order


# ═══════════════════════════════════════════
#   ЧАЕВЫЕ (Feature 7)
# ═══════════════════════════════════════════
async def add_tip_to_order(session: AsyncSession, order_id: int, tip_amount: Decimal) -> bool:
    """
    Начисляет чаевые: списывает с client.balance, делит 90/10.
    Если заказ уже done — курьеру сразу. Если нет — при complete_order.
    """
    order_r = await session.execute(select(Order).where(Order.id == order_id))
    order = order_r.scalar_one_or_none()
    if not order or order.tip_amount > 0:
        return False

    tip = Decimal(str(tip_amount)).quantize(Decimal("0.01"))
    if tip <= 0:
        return False

    c_r = await session.execute(select(Client).where(Client.id == order.client_id))
    client = c_r.scalar_one_or_none()
    if not client or Decimal(str(client.balance)) < tip:
        return False

    client.balance -= tip
    order.tip_amount = tip

    session.add(Transaction(
        user_type="client", user_id=order.client_id, account_type="main",
        amount=-tip, type="tip_out", order_id=order_id, comment="Чаевые курьеру",
    ))

    platform_tip = (tip * Decimal(str(config.TIP_PLATFORM_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
    courier_tip = tip - platform_tip

    if order.status == "done" and order.courier_id:
        await session.execute(
            update(Courier).where(Courier.id == order.courier_id)
            .values(balance=Courier.balance + courier_tip)
        )
        session.add(Transaction(
            user_type="courier", user_id=order.courier_id,
            amount=courier_tip, type="tip_in", order_id=order_id, comment="Чаевые от клиента",
        ))
        session.add(Transaction(
            user_type="platform", user_id=0,
            amount=platform_tip, type="tip_income", order_id=order_id,
        ))

    await session.commit()
    return True


# ═══════════════════════════════════════════
#   ОТМЕНА ЗАКАЗА
# ═══════════════════════════════════════════
async def cancel_order(session: AsyncSession, order_id: int, reason: str = None, cancelled_by: str = "shop", refund: bool = True):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order or order.status in ("picked", "delivering", "at_client", "done", "cancel"):
        return None

    # FIX bug15: клиент не может отменить оплаченный заказ
    if cancelled_by == "client" and order.payment_status == "confirmed":
        return None

    order.status = "cancel"
    order.cancel_reason = reason
    order.cancelled_by = cancelled_by

    # FIX: отменяем платёж, если он pending
    p_result = await session.execute(select(Payment).where(Payment.order_id == order_id))
    payment = p_result.scalar_one_or_none()
    if payment and payment.status == "pending":
        payment.status = "cancelled"

    if refund and order.payment_status == "confirmed":
        await session.execute(
            update(Client).where(Client.id == order.client_id)
            .values(balance=Client.balance + order.total_price)
        )
        session.add(Transaction(
            user_type="client", user_id=order.client_id, account_type="main",
            amount=order.total_price, type="refund", order_id=order_id,
        ))
        if order.bonus_used and order.bonus_used > 0:
            await session.execute(
                update(Client).where(Client.id == order.client_id)
                .values(bonus_balance=Client.bonus_balance + order.bonus_used)
            )
            session.add(Transaction(
                user_type="client", user_id=order.client_id, account_type="bonus",
                amount=order.bonus_used, type="bonus_refund", order_id=order_id,
            ))
        order.payment_status = "refunded"
        if payment and payment.status == "confirmed":
            payment.status = "refunded"

    # bug9: штраф только за ручное отклонение магазином (авто — не штрафуем)
    if cancelled_by == "shop":
        await session.execute(
            update(Shop).where(Shop.id == order.shop_id).values(rejected_count=Shop.rejected_count + 1)
        )

    await session.commit()
    await update_client_order_message(session, order_id)
    return order


# ═══════════════════════════════════════════
#   ОБНОВЛЕНИЕ СООБЩЕНИЯ КЛИЕНТА
# ═══════════════════════════════════════════
async def update_client_order_message(session: AsyncSession, order_id: int):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or not order.client_message_id:
        return

    c_result = await session.execute(select(Client).where(Client.id == order.client_id))
    client = c_result.scalar_one_or_none()
    if not client or not client.tg_id:
        return

    items_r = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = items_r.scalars().all()

    courier = None
    if order.courier_id:
        cr = await session.execute(select(Courier).where(Courier.id == order.courier_id))
        courier = cr.scalar_one_or_none()

    status_map = {
        "pending": "⏳ Ожидает оплаты", "new": "🆕 Оплачен, ждет магазина",
        "wait": "🔍 Ищем курьера", "going": "🚴 Курьер едет в магазин",
        "picked": "📦 Курьер забрал букет", "delivering": "🚴 Курьер везёт вам",
        "at_client": "📍 Курьер у вас", "done": "✅ Доставлено", "cancel": "❌ Отменено",
    }
    status_text = status_map.get(order.status, order.status)

    text = (
        f"📦 <b>Заказ #{order.id}</b>\n"
        f"💳 Статус: <b>{status_text}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌷 <b>СОСТАВ ЗАКАЗА:</b>\n"
    )
    for it in items:
        text += f"  • {helpers.escape(it.title)} × {it.quantity} = {helpers.money(it.total)}\n"

    text += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>КУДА ДОСТАВИТЬ:</b>\n"
        f"  {helpers.escape(order.address)}\n"
        f"👤 <b>ПОЛУЧАТЕЛЬ:</b> {helpers.escape(order.client_name)}\n"
        f"📞 <b>ТЕЛЕФОН:</b> {helpers.escape(order.client_phone)}\n"
        f"📅 <b>ДАТА:</b> {helpers.format_date(order.delivery_date)}\n"
        f"🕒 <b>ВРЕМЯ ДОСТАВКИ:</b> {order.delivery_slot or '—'}\n"
    )

    if order.is_preorder:
        text += "🗓 <b>ПРЕДЗАКАЗ</b>\n"

    if courier and order.status in ("going", "picked", "delivering", "at_client"):
        text += (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚴 <b>ВАШ КУРЬЕР:</b>\n"
            f"  👤 {helpers.escape(courier.name)}\n"
            f"  📞 {helpers.escape(courier.phone)}\n"
        )

    text += f"━━━━━━━━━━━━━━━━━━━━━━\n💰 <b>СУММА:</b> {helpers.money(order.total_price)}\n"

    from keyboards import track_order
    from bots import bot_client
    from aiogram.exceptions import TelegramBadRequest

    # FIX bug15: передаём payment_status — «Отменить» скрыта, если оплачено
    markup = track_order(
        order.id, order.status, courier.phone if courier else None,
        float(courier.lat) if courier and courier.lat else None,
        float(courier.lon) if courier and courier.lon else None,
        payment_status=order.payment_status,
    )

    try:
        await bot_client.edit_message_text(
            chat_id=client.tg_id, message_id=order.client_message_id, text=text, reply_markup=markup,
        )
    except TelegramBadRequest as e:
        log.error(f"edit_message_text клиенту: {e}")


# ═══════════════════════════════════════════
#   РЕДАКТИРОВАНИЕ
# ═══════════════════════════════════════════
async def edit_order_field(session: AsyncSession, order_id: int, field: str, new_value, changed_by: str, changed_by_id: int) -> bool:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or order.status in ("picked", "delivering", "at_client", "done", "cancel"):
        return False

    if field == "delivery_slot" and new_value:
        if helpers.is_slot_past(new_value, order.delivery_date):
            return False

    old_value = getattr(order, field, None)
    setattr(order, field, new_value)

    session.add(ChangeLog(
        object_type="order", object_id=order_id, field=field,
        old_value=str(old_value) if old_value else None, new_value=str(new_value),
        changed_by=changed_by, changed_by_id=changed_by_id,
    ))
    await session.commit()
    return True


async def edit_delivery_field(session: AsyncSession, delivery_id: int, field: str, new_value, changed_by: str, changed_by_id: int) -> bool:
    result = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
    d = result.scalar_one_or_none()
    if not d or d.status in ("picked", "at_client", "done", "cancel"):
        return False

    old_value = getattr(d, field, None)
    setattr(d, field, new_value)

    session.add(ChangeLog(
        object_type="delivery", object_id=delivery_id, field=field,
        old_value=str(old_value) if old_value else None, new_value=str(new_value),
        changed_by=changed_by, changed_by_id=changed_by_id,
    ))
    await session.commit()
    return True


# ═══════════════════════════════════════════
#   ПОИСК, ПОЛУЧЕНИЕ
# ═══════════════════════════════════════════
async def find_alternative_shop(session: AsyncSession, order_id: int) -> int | None:
    items_result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = items_result.scalars().all()
    if not items:
        return None

    first_product_result = await session.execute(select(Product).where(Product.id == items[0].product_id))
    first_product = first_product_result.scalar_one_or_none()
    if not first_product:
        return None

    result = await session.execute(
        select(Product).join(Shop, Shop.id == Product.shop_id).where(
            Product.title == first_product.title,
            Product.category == first_product.category,
            Product.is_active == True,
            Product.shop_id != first_product.shop_id,
            Shop.status == "active",
            Shop.is_paused == False,
        ).limit(1)
    )
    alt = result.scalar_one_or_none()
    return alt.shop_id if alt else None


async def get_client_orders(session: AsyncSession, client_id: int, limit: int = 20):
    result = await session.execute(
        select(Order).where(Order.client_id == client_id).order_by(Order.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def get_shop_orders(session: AsyncSession, shop_id: int, limit: int = 50):
    result = await session.execute(
        select(Order).where(Order.shop_id == shop_id).order_by(Order.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def get_free_orders(session: AsyncSession, limit: int = 30):
    result = await session.execute(
        select(Order).where(
            Order.status == "wait", Order.payment_status == "confirmed", Order.courier_id.is_(None),
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
