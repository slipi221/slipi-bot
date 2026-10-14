# -*- coding: utf-8 -*-
"""
SLIPI — бот курьера
"""
from datetime import datetime
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from sqlalchemy import select, update

import config
import keyboards as kb
from states import CourierReg, CourierFSM
from database import async_session
from models import Courier, Order, OrderItem, Shop
from services import orders as orders_service
from services import geo as geo_service
from services import bonuses as bonuses_service
from services import payments as payments_service
from utils import helpers

router = Router(name="courier")


# ═══════════════════════════════════════════
#   ХЕЛПЕРЫ
# ═══════════════════════════════════════════
async def get_courier(session, tg_id: int):
    result = await session.execute(select(Courier).where(Courier.tg_id == tg_id))
    return result.scalar_one_or_none()


async def show_courier_menu(message: Message, courier: Courier, edit=False):
    state_map = {
        "on": "🟢 На смене",
        "off": "🔴 Не на смене",
        "break": "☕ Перерыв",
        "busy": "🚗 На заказе",
    }
    text = (
        f"{state_map.get(courier.courier_state, '—')}\n"
        f"💰 Баланс: {helpers.money(courier.balance)}\n"
        f"⭐ Рейтинг: {float(courier.rating or 0):.1f}\n"
        f"📦 Заказов: {courier.total_orders}"
    )

    if courier.courier_state == "on":
        markup = kb.courier_main_on_shift()
    elif courier.courier_state == "off":
        markup = kb.courier_main_off_shift()
    else:
        markup = kb.courier_main_on_shift()

    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


# ═══════════════════════════════════════════
#   /start
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)

    if not courier:
        await message.answer(
            "🚴 <b>Стать курьером SLIPI</b>\n\n"
            "Отправьте команду /register чтобы зарегистрироваться."
        )
        return

    if courier.status == "pending":
        await message.answer("⏳ Ваша заявка на рассмотрении.")
        return

    if courier.is_blocked:
        await message.answer("🚫 Доступ закрыт.")
        return

    await show_courier_menu(message, courier)


@router.callback_query(F.data == "courier_menu")
async def back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
    if not courier:
        await call.answer("Ошибка", show_alert=True)
        return
    await show_courier_menu(call.message, courier, edit=True)
    await call.answer()


# ═══════════════════════════════════════════
#   РЕГИСТРАЦИЯ
# ═══════════════════════════════════════════
@router.message(Command("register"))
async def courier_register(message: Message, state: FSMContext):
    async with async_session() as session:
        existing = await get_courier(session, message.from_user.id)
        if existing:
            await message.answer("Вы уже зарегистрированы.")
            return

    await state.set_state(CourierReg.name)
    await message.answer(
        "📝 <b>Шаг 1/6:</b> Ваше имя",
        reply_markup=kb.cancel_kb()
    )


@router.message(CourierReg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CourierReg.phone)
    await message.answer("📞 <b>Шаг 2/6:</b> Телефон (10–15 цифр)", reply_markup=kb.cancel_kb())


@router.message(CourierReg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(phone=helpers.clean_phone(message.text))
    await state.set_state(CourierReg.city)
    await message.answer(f"🏙 <b>Шаг 3/6:</b> Город (например, {config.CITY})",
                         reply_markup=kb.cancel_kb())


@router.message(CourierReg.city)
async def reg_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(CourierReg.transport)
    await message.answer(
        "🚗 <b>Шаг 4/6:</b> Транспорт?",
        reply_markup=kb.kb([
            [kb.btn("🚗 Авто", "reg_transport_auto"),
             kb.btn("🏍 Мото", "reg_transport_moto")],
            [kb.btn("🚲 Вело", "reg_transport_bike"),
             kb.btn("🚶 Пешком", "reg_transport_walk")],
            [kb.btn("❌ Отмена", "cancel")],
        ])
    )


@router.callback_query(F.data.startswith("reg_transport_"), CourierReg.transport)
async def reg_transport(call: CallbackQuery, state: FSMContext):
    tr = call.data.replace("reg_transport_", "")
    names = {"auto": "Авто", "moto": "Мото", "bike": "Вело", "walk": "Пешком"}
    await state.update_data(transport=names.get(tr, tr))
    await state.set_state(CourierReg.card)
    await call.message.edit_text(
        "💳 <b>Шаг 5/6:</b> Номер карты для выплат (16 цифр)",
        reply_markup=kb.cancel_kb()
    )
    await call.answer()


@router.message(CourierReg.card)
async def reg_card(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты. Введите 16 цифр.")
        return
    await state.update_data(card=helpers.clean_phone(message.text))
    await state.set_state(CourierReg.referral)
    await message.answer(
        "🎁 <b>Шаг 6/6:</b> Есть реферальный код? (например, ref_12345)\n"
        "Или отправьте /skip",
        reply_markup=kb.cancel_kb()
    )


@router.message(CourierReg.referral)
async def reg_referral(message: Message, state: FSMContext):
    ref_tg_id = None
    txt = message.text.strip()
    if not txt.startswith("/skip") and txt.startswith("ref_"):
        try:
            ref_tg_id = int(txt.replace("ref_", ""))
        except ValueError:
            ref_tg_id = None

    data = await state.get_data()

    async with async_session() as session:
        courier = Courier(
            tg_id=message.from_user.id,
            name=data["name"],
            phone=data["phone"],
            city=data["city"],
            transport=data["transport"],
            card_number=data["card"],
            status="pending",
            courier_state="off",
        )
        session.add(courier)
        await session.commit()
        await session.refresh(courier)

        if ref_tg_id:
            await bonuses_service.register_referral(session, courier.id, ref_tg_id)

    await state.clear()
    await message.answer(
        "✅ <b>Заявка отправлена!</b>\nЖдите одобрения админа.",
        reply_markup=kb.cancel_kb()
    )

    # Уведомление админу
    try:
        await message.bot.send_message(
            config.ADMIN_ID,
            f"🚴 <b>Новая заявка курьера</b>\n\n"
            f"👤 {data['name']}\n"
            f"📞 {data['phone']}\n"
            f"🏙 {data['city']}\n"
            f"🚗 {data['transport']}"
        )
    except Exception:
        pass


# ═══════════════════════════════════════════
#   СМЕНА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_on_shift")
async def on_shift(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier:
            await call.answer("Ошибка", show_alert=True)
            return
        courier.courier_state = "on"
        courier.status = "active"
        await session.commit()

    await call.message.edit_text(
        "🟢 <b>Вы на смене!</b>\n\n"
        "Отправьте геолокацию, чтобы получать заказы поблизости.",
        reply_markup=kb.kb([
            [kb.btn("📍 Отправить гео", "courier_send_geo")],
            [kb.btn("🔙 В меню", "courier_menu")],
        ])
    )
    await call.answer()


@router.callback_query(F.data == "courier_send_geo")
async def ask_geo(call: CallbackQuery):
    await call.message.answer(
        "📍 Нажмите на скрепку → «Геолокация» → «Отправить»",
        reply_markup=kb.kb([
            [kb.btn("🔙 В меню", "courier_menu")]
        ])
    )
    await call.answer()


@router.message(F.location)
async def got_geo(message: Message):
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        if not courier:
            return
        courier.lat = message.location.latitude
        courier.lon = message.location.longitude
        courier.loc_time = datetime.now()
        await session.commit()

    await message.answer(
        f"✅ Гео сохранено!\n📍 {message.location.latitude:.5f}, {message.location.longitude:.5f}",
        reply_markup=kb.courier_main_on_shift()
    )


@router.callback_query(F.data == "courier_off_shift")
async def off_shift(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier:
            await call.answer("Ошибка", show_alert=True)
            return
        courier.courier_state = "off"
        await session.commit()

    await call.message.edit_text(
        "🔴 <b>Вы ушли со смены.</b>\nЗаказы больше не приходят.",
        reply_markup=kb.courier_main_off_shift()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   СВОБОДНЫЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_free_orders")
async def free_orders(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier:
            await call.answer("Ошибка", show_alert=True)
            return

        orders = await orders_service.get_free_orders(session, limit=10)

        items = []
        for o in orders:
            distance = 0
            if courier.lat and courier.lon and o.lat and o.lon:
                shop_r = await session.execute(select(Shop).where(Shop.id == o.shop_id))
                shop = shop_r.scalar_one_or_none()
                if shop and shop.lat and shop.lon:
                    distance = helpers.distance_km(
                        float(courier.lat), float(courier.lon),
                        float(shop.lat), float(shop.lon)
                    )
            fee = config.get_courier_fee(float(o.delivery_price)) + float(o.boost_amount or 0)
            items.append({
                "id": o.id,
                "fee": int(fee),
                "distance": f"{distance:.1f}",
                "wait_min": int((datetime.now() - o.wait_started_at).total_seconds() / 60)
                    if o.wait_started_at else 0,
                "address": o.address,
            })

    if not items:
        await call.message.edit_text(
            "📦 <b>Свободных заказов нет</b>\n\nЗаглядывайте позже.",
            reply_markup=kb.kb([[kb.btn("🔙 В меню", "courier_menu")]])
        )
        await call.answer()
        return

    text = f"📦 <b>Свободные заказы ({len(items)})</b>\n\n"
    for it in items[:3]:
        emoji = "🔥" if it["wait_min"] < 5 else ("🟢" if it["wait_min"] < 10 else "🟡")
        text += (
            f"{emoji} <b>#{it['id']}</b> — {it['fee']} ₽\n"
            f"📍 {it['address']}\n"
            f"📏 {it['distance']} км | ⏱ Ждёт {it['wait_min']} мин\n\n"
        )

    rows = []
    for it in items[:3]:
        rows.append([kb.btn(f"🤝 Взять #{it['id']}", f"courier_take_{it['id']}")])
    rows.append([kb.btn("🔄 Обновить", "courier_free_orders")])
    rows.append([kb.btn("🔙 В меню", "courier_menu")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()


@router.callback_query(F.data.startswith("courier_take_"))
async def take_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier:
            await call.answer("Ошибка", show_alert=True)
            return

        ok = await orders_service.take_order(session, order_id, courier.id)
        if not ok:
            await call.answer("😔 Заказ уже занят другим курьером", show_alert=True)
            return

        # Обновляем статус курьера
        courier.courier_state = "busy"
        await session.commit()

        # Данные заказа
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        shop_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_r.scalar_one_or_none()

    fee = int(config.get_courier_fee(float(order.delivery_price)) + float(order.boost_amount or 0))

    text = (
        f"✅ <b>Заказ #{order_id} ваш!</b>\n\n"
        f"🏪 Забрать: {shop.address if shop else '—'}\n"
        f"🏠 Доставить: {order.address}\n"
        f"👤 {order.client_name}, {order.client_phone}\n"
        f"💰 Заработок: {fee} ₽"
    )
    rows = [
        [kb.btn("📦 Забрал", f"courier_picked_{order_id}")],
        [kb.btn("🗺 Маршрут", f"courier_map_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()


# ═══════════════════════════════════════════
#   СТАТУСЫ ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_picked_"))
async def picked(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        await orders_service.update_order_status(session, order_id, "picked")
        # Уведомляем магазин и клиента
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()

    text = (
        f"📦 <b>Заказ #{order_id} забран.</b>\n"
        f"Везём клиенту: {order.address}\n"
        f"👤 {order.client_name}, {order.client_phone}"
    )
    rows = [
        [kb.btn("🏠 У клиента", f"courier_at_client_{order_id}")],
        [kb.btn("🗺 Маршрут", f"courier_map_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()


@router.callback_query(F.data.startswith("courier_delivering_"))
async def delivering(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        await orders_service.update_order_status(session, order_id, "delivering")
    await call.answer("✅ Статус: доставляем")


@router.callback_query(F.data.startswith("courier_at_client_"))
async def at_client(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        await orders_service.update_order_status(session, order_id, "at_client")

    text = (
        f"📍 <b>Заказ #{order_id} у клиента.</b>\n\n"
        f"Когда отдадите букет — нажмите «Доставлено»."
    )
    rows = [
        [kb.btn("✅ Доставлено", f"courier_done_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()


@router.callback_query(F.data.startswith("courier_done_"))
async def done(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        order = await orders_service.complete_order(session, order_id)

        if not order or not courier:
            await call.answer("Ошибка", show_alert=True)
            return

        # Рефералка
        fee = config.get_courier_fee(float(order.delivery_price)) + float(order.boost_amount or 0)
        await bonuses_service.apply_referral_percent(session, courier.id, Decimal(str(fee)))

        # Уровень
        await bonuses_service.update_courier_level(session, courier.id)

        # Вернуть курьера в "свободен"
        courier.courier_state = "on"
        await session.commit()

        # Обновляем баланс
        await session.refresh(courier)

    await call.message.edit_text(
        f"✅ <b>Заказ #{order_id} доставлен!</b>\n\n"
        f"💰 +{fee} ₽\n"
        f"💳 Баланс: {helpers.money(courier.balance)}",
        reply_markup=kb.courier_main_on_shift()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   БАЛАНС И ВЫВОД
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_balance")
async def courier_balance(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        txs = await payments_service.get_user_transactions(session, "courier", courier.id, 5)

    text = f"💰 <b>Баланс: {helpers.money(courier.balance)}</b>\n\n"
    if txs:
        text += "Последние операции:\n"
        for t in txs:
            sign = "+" if float(t.amount) >= 0 else ""
            text += f"{sign}{helpers.money(t.amount)} — {t.type}\n"

    await call.message.edit_text(text, reply_markup=kb.courier_balance_menu())
    await call.answer()


@router.callback_query(F.data == "courier_withdraw_normal")
async def withdraw_normal(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if float(courier.balance) < config.COURIER_MIN_WITHDRAW:
            await call.answer(f"Минимум {config.COURIER_MIN_WITHDRAW} ₽", show_alert=True)
            return

    await state.set_state(CourierFSM.withdraw_amount)
    await call.message.edit_text(
        f"💸 <b>Вывод средств</b>\n\n"
        f"Баланс: {helpers.money(courier.balance)}\n"
        f"Минимум: {config.COURIER_MIN_WITHDRAW} ₽\n\n"
        f"Введите сумму:",
        reply_markup=kb.cancel_kb()
    )
    await call.answer()


@router.message(CourierFSM.withdraw_amount)
async def process_withdraw(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        if amount < config.COURIER_MIN_WITHDRAW:
            await message.answer(f"❌ Минимум {config.COURIER_MIN_WITHDRAW} ₽")
            return
        if amount > courier.balance:
            await message.answer(f"❌ Больше баланса. У вас {helpers.money(courier.balance)}")
            return

        await payments_service.create_payout(
            session=session,
            user_type="courier",
            user_id=courier.id,
            amount=amount,
            card_number=courier.card_number,
            holder_name=courier.name,
        )

    await state.clear()
    await message.answer(
        f"✅ Заявка на вывод {helpers.money(amount)} отправлена админу.",
        reply_markup=kb.courier_main_on_shift()
    )


# ═══════════════════════════════════════════
#   СТАТИСТИКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_stats")
async def courier_stats(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        level_info = bonuses_service.get_level_by_orders(courier.total_orders)
        next_level = bonuses_service.get_next_level(courier.total_orders)
        bonus = await bonuses_service.calculate_daily_bonus(session, courier.id)

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📦 Всего доставок: {courier.total_orders}\n"
        f"⭐ Рейтинг: {float(courier.rating or 0):.1f}\n"
        f"💰 Баланс: {helpers.money(courier.balance)}\n\n"
        f"{level_info[1]}"
    )
    if next_level:
        text += f"\nДо {next_level[1]}: {next_level[2] - courier.total_orders} заказов"

    if bonus > 0:
        text += f"\n\n🎁 Бонус за сегодня: {helpers.money(bonus)}"

    await call.message.edit_text(text, reply_markup=kb.courier_stats_menu())
    await call.answer()


# ═══════════════════════════════════════════
#   РЕФЕРАЛКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_referral")
async def courier_referral(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)

    ref_link = helpers.referral_link(call.from_user.id)

    text = (
        f"🎁 <b>Приглашай друзей!</b>\n\n"
        f"Получай {config.REFERRAL_PERCENT}% от заработка приглашённых "
        f"({config.REFERRAL_MONTHS} мес.)\n\n"
        f"🔗 {ref_link}"
    )
    await call.message.edit_text(text, reply_markup=kb.courier_referral_menu(ref_link))
    await call.answer()


@router.callback_query(F.data == "courier_ref_copy")
async def ref_copy(call: CallbackQuery):
    link = helpers.referral_link(call.from_user.id)
    await call.message.answer(f"<code>{link}</code>")
    await call.answer("Скопировано")


# ═══════════════════════════════════════════
#   АКТИВНЫЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_my_orders")
async def my_orders(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        orders = await orders_service.get_courier_active_orders(session, courier.id)

    if not orders:
        await call.message.edit_text(
            "🚗 Активных заказов нет.",
            reply_markup=kb.kb([[kb.btn("🔙 В меню", "courier_menu")]])
        )
        await call.answer()
        return

    text = f"🚗 <b>Активные заказы ({len(orders)})</b>\n\n"
    for o in orders:
        text += f"#{o.id} — {helpers.status_text(o.status)}\n📍 {o.address}\n\n"

    rows = []
    for o in orders[:3]:
        rows.append([kb.btn(f"📦 #{o.id}", f"courier_open_{o.id}")])
    rows.append([kb.btn("🔙 В меню", "courier_menu")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()
