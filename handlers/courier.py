# -*- coding: utf-8 -*-
"""
Flowers Express — бот курьера
"""
from datetime import datetime, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update

import config
import keyboards as kb
from states import CourierReg, CourierFSM
from database import async_session
from models import (
    Courier, Order, OrderItem, Shop, Client, DeliveryOrder,
    CourierDailyStat, Transaction,
)
from services import orders as orders_service
from services import geo as geo_service
from services import bonuses as bonuses_service
from services import payments as payments_service
from utils import helpers
from bots import bot_client, bot_shop, bot_courier, bot_admin

router = Router(name="courier")

async def get_courier(session, tg_id: int):
    result = await session.execute(select(Courier).where(Courier.tg_id == tg_id))
    return result.scalar_one_or_none()

async def show_courier_menu(message: Message, courier: Courier, edit: bool = False):
    state_map = {"on": "🟢 На смене", "off": "🔴 Не на смене", "break": "☕ Перерыв", "busy": "🚗 На заказе"}
    text = (
        f"{state_map.get(courier.courier_state, '—')}\n"
        f"💰 Баланс: {helpers.money(courier.balance)}\n"
        f"⭐ Рейтинг: {float(courier.rating or 0):.1f}\n"
        f"📦 Заказов: {courier.total_orders}"
    )
    markup = kb.courier_main_off_shift() if courier.courier_state == "off" else kb.courier_main_on_shift()
    if edit:
        try: await message.edit_text(text, reply_markup=markup)
        except Exception: await message.answer(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)

# ═══════════════════════════════════════════
#   /start И РЕГИСТРАЦИЯ (БЕЗ КАРТЫ)
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)

    if not courier:
        await message.answer("🚴 <b>Стать курьером Flowers Express</b>\n\nОтправьте команду /register чтобы зарегистрироваться.")
        return
    if courier.status == "pending":
        await message.answer("⏳ Ваша заявка на рассмотрении.")
        return
    if courier.is_blocked or courier.status == "blocked":
        await message.answer(f"🚫 <b>Доступ закрыт.</b>\n\nНапишите в поддержку: {config.SUPPORT_TG}", reply_markup=kb.courier_support())
        return
    await show_courier_menu(message, courier)

@router.callback_query(F.data == "courier_menu")
async def back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
    if not courier: return
    await show_courier_menu(call.message, courier, edit=True)
    await call.answer()

@router.callback_query(F.data == "courier_support")
async def courier_support_handler(call: CallbackQuery):
    await call.message.edit_text(f"🆘 <b>Поддержка</b>\n\nНапишите: {config.SUPPORT_TG}\n📞 {config.SUPPORT_PHONE}", reply_markup=kb.courier_support())
    await call.answer()

@router.message(Command("register"))
async def courier_register(message: Message, state: FSMContext):
    async with async_session() as session:
        existing = await get_courier(session, message.from_user.id)
        if existing:
            await message.answer("Вы уже зарегистрированы.")
            return

    await state.set_state(CourierReg.name)
    await message.answer("📝 <b>Шаг 1/5:</b> Ваше имя", reply_markup=kb.cancel_kb("courier_menu"))

@router.message(CourierReg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CourierReg.phone)
    await message.answer("📞 <b>Шаг 2/5:</b> Телефон", reply_markup=kb.cancel_kb("courier_menu"))

@router.message(CourierReg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(phone=helpers.clean_phone(message.text))
    await state.set_state(CourierReg.city)
    await message.answer(f"🏙 <b>Шаг 3/5:</b> Город\n\n<i>Например: {config.CITY}</i>", reply_markup=kb.cancel_kb("courier_menu"))

@router.message(CourierReg.city)
async def reg_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(CourierReg.transport)
    await message.answer("🚗 <b>Шаг 4/5:</b> Транспорт?", reply_markup=kb.kb([
        [kb.btn("🚗 Авто", "reg_transport_auto"), kb.btn("🏍 Мото", "reg_transport_moto")],
        [kb.btn("🚲 Вело", "reg_transport_bike"), kb.btn("🚶 Пешком", "reg_transport_walk")],
        [kb.btn("❌ Отмена", "courier_menu")],
    ]))

@router.callback_query(F.data.startswith("reg_transport_"), CourierReg.transport)
async def reg_transport(call: CallbackQuery, state: FSMContext):
    tr = call.data.replace("reg_transport_", "")
    names = {"auto": "Авто", "moto": "Мото", "bike": "Вело", "walk": "Пешком"}
    await state.update_data(transport=names.get(tr, tr))
    await state.set_state(CourierReg.referral)
    await call.message.edit_text("🎁 <b>Шаг 5/5:</b> Реферальный код\n\nВведите или /skip", reply_markup=kb.cancel_kb("courier_menu"))
    await call.answer()

@router.message(CourierReg.referral)
async def reg_referral(message: Message, state: FSMContext):
    ref_tg_id = None
    txt = message.text.strip()
    if not txt.startswith("/skip") and txt.startswith("ref_"):
        try: ref_tg_id = int(txt.replace("ref_", ""))
        except ValueError: ref_tg_id = None

    data = await state.get_data()
    async with async_session() as session:
        courier = Courier(
            tg_id=message.from_user.id, name=data["name"], phone=data["phone"],
            city=data["city"], transport=data["transport"],
            status="pending", courier_state="off",
        )
        session.add(courier)
        await session.commit()
        await session.refresh(courier)

        if ref_tg_id:
            await bonuses_service.register_referral(session, courier.id, ref_tg_id)

    await state.clear()
    await message.answer(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Ждите одобрения админа.\n\n"
        "💳 <i>Карту для выплат вы сможете указать позже в разделе «Реквизиты».</i>",
        reply_markup=kb.courier_main_off_shift()
    )

    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🚴 <b>Новая заявка курьера</b>\n\n👤 {helpers.escape(data['name'])}\n📞 {data['phone']}\n🏙 {helpers.escape(data['city'])}\n🚗 {data['transport']}",
            reply_markup=kb.admin_approve_courier(courier.id)
        )
    except Exception: pass

# ═══════════════════════════════════════════
#   СМЕНА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_on_shift")
async def on_shift(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return
        courier.courier_state = "on"
        courier.status = "active"
        await session.commit()

    await call.message.edit_text("🟢 <b>Вы на смене!</b>\n\nОтправьте гео (📍 скрепка), чтобы получать заказы.", reply_markup=kb.kb([[kb.btn("🔙 В меню", "courier_menu")]]))
    await call.answer()

@router.message(F.location)
async def got_geo(message: Message):
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        if not courier: return
        await geo_service.update_courier_location(session, courier.id, message.location.latitude, message.location.longitude)

    await message.answer(f"✅ Гео сохранено!\n📍 {message.location.latitude:.5f}, {message.location.longitude:.5f}\n\n🟢 Вы автоматически на смене!", reply_markup=kb.courier_main_on_shift())

@router.callback_query(F.data == "courier_off_shift")
async def off_shift(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return
        courier.courier_state = "off"
        await session.commit()

    await call.message.edit_text("🔴 <b>Вы ушли со смены.</b>", reply_markup=kb.courier_main_off_shift())
    await call.answer()

# ═══════════════════════════════════════════
#   СВОБОДНЫЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_free_orders")
async def free_orders(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return

        orders = await orders_service.get_free_orders(session, limit=10)
        d_result = await session.execute(
            select(DeliveryOrder).where(DeliveryOrder.status == "confirmed", DeliveryOrder.courier_id.is_(None)).order_by(DeliveryOrder.id.asc()).limit(10)
        )
        deliveries = d_result.scalars().all()

        items = []
        for o in orders:
            distance = 0
            if courier.lat and courier.lon and o.lat and o.lon:
                shop_r = await session.execute(select(Shop).where(Shop.id == o.shop_id))
                shop = shop_r.scalar_one_or_none()
                if shop and shop.lat and shop.lon:
                    distance = helpers.distance_km(float(courier.lat), float(courier.lon), float(shop.lat), float(shop.lon))
            
            fee = float(o.courier_fee or 0) + float(o.boost_amount or 0)
            wait_min = 0
            if o.wait_started_at: wait_min = int((helpers.now_moscow() - o.wait_started_at).total_seconds() / 60)
            
            items.append({
                "id": o.id, "fee": int(fee), "distance": f"{distance:.1f}",
                "wait_min": wait_min, "address": o.address, "type": "order", "is_boosted": o.boost_amount > 0
            })

        for d in deliveries:
            distance = 0
            if courier.lat and courier.lon and d.from_lat and d.from_lon:
                distance = helpers.distance_km(float(courier.lat), float(courier.lon), float(d.from_lat), float(d.from_lon))
            fee = float(d.courier_fee or 0)
            items.append({"id": f"Д-{d.id}", "fee": int(fee), "distance": f"{distance:.1f}", "wait_min": 0, "address": d.to_address, "type": "delivery", "is_boosted": False})

    if not items:
        await call.message.edit_text("📦 <b>Свободных заказов нет</b>\n\nЗаглядывайте позже.", reply_markup=kb.kb([[kb.btn("🔙 В меню", "courier_menu")]]))
        await call.answer()
        return

    text = f"📦 <b>Свободные заказы ({len(items)})</b>\n\n"
    for it in items[:3]:
        emoji = "🔥" if it["wait_min"] < 5 else ("🟢" if it["wait_min"] < 10 else "🟡")
        prefix = "🚚" if it["type"] == "delivery" else emoji
        boost_str = " 🔥 +50₽" if it["is_boosted"] else ""
        text += f"{prefix} <b>{it['id']}</b> — {it['fee']} ₽{boost_str}\n📍 {helpers.escape(it['address'])}\n📏 {it['distance']} км | ⏱ {it['wait_min']} мин\n\n"

    rows = []
    for it in items[:3]:
        if it["type"] == "order":
            rows.append([kb.btn(f"🤝 Взять #{it['id']}", f"courier_take_{it['id']}")])
        else:
            del_id = str(it['id']).replace("Д-", "")
            rows.append([kb.btn(f"🤝 Взять {it['id']}", f"courier_take_del_{del_id}")])
    rows.append([kb.btn("🔄 Обновить", "courier_free_orders")])
    rows.append([kb.btn("🔙 В меню", "courier_menu")])

    try: await call.message.edit_text(text, reply_markup=kb.kb(rows))
    except Exception: await call.message.answer(text, reply_markup=kb.kb(rows))
    await call.answer()

# ═══════════════════════════════════════════
#   ВЗЯТИЕ ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_take_") & ~F.data.startswith("courier_take_del_"))
async def take_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return

        ok = await orders_service.take_order(session, order_id, courier.id)
        if not ok:
            await call.answer("😔 Уже занят или вы не на смене", show_alert=True)
            return

        if courier.courier_state == "on":
            courier.courier_state = "busy"
        await session.commit()

        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        shop_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_r.scalar_one_or_none()
        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    fee = int(float(order.courier_fee or 0) + float(order.boost_amount or 0))
    photo_req = "📸 Обязательно" if order.need_delivery_photo else "📸 Не требуется"
    shop_name = shop.name if shop else "—"
    shop_addr = shop.address if shop else "—"
    shop_phone = shop.phone if shop else "—"

    text = (
        f"✅ <b>Заказ #{order_id} ваш!</b>\n\n"
        f"🏪 <b>ЗАБРАТЬ ИЗ:</b> {helpers.escape(shop_name)}\n"
        f"  {helpers.escape(shop_addr)}\n"
        f"  📞 {helpers.escape(shop_phone)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏠 <b>ДОСТАВИТЬ В:</b>\n  {helpers.escape(order.address)}\n"
        f"  👤 {helpers.escape(order.client_name)}, {helpers.escape(order.client_phone)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>ДАТА:</b> {helpers.format_date(order.delivery_date)}\n"
        f"🕒 <b>ВРЕМЯ:</b> {order.delivery_slot or '—'}\n"
        f"{photo_req}\n"
        f"💰 <b>Заработок:</b> {fee} ₽\n"
    )
    if order.comment:
        text += f"💬 <b>Комментарий:</b> {helpers.escape(order.comment)}\n"

    rows = [
        [kb.btn("📦 Забрал", f"courier_picked_{order_id}")],
        [kb.btn("🗺 Маршрут", f"courier_map_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))

    if client and client.tg_id:
        try: await bot_client.send_message(client.tg_id, f"🚴 <b>Курьер назначен на заказ #{order_id}</b>\n\n👤 {helpers.escape(courier.name)}\n📞 {helpers.escape(courier.phone)}")
        except Exception: pass
    await call.answer()
    # ═══════════════════════════════════════════
#   ВЗЯТИЕ СВОЕЙ ДОСТАВКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_take_del_"))
async def take_delivery(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return

        result = await session.execute(
            update(DeliveryOrder).where(DeliveryOrder.id == delivery_id, DeliveryOrder.status == "confirmed", DeliveryOrder.courier_id.is_(None))
            .values(courier_id=courier.id, status="going", taken_at=helpers.now_moscow())
        )
        await session.commit()
        if result.rowcount != 1:
            await call.answer("😔 Уже занято", show_alert=True)
            return

        if courier.courier_state == "on":
            courier.courier_state = "busy"
        await session.commit()
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()

    fee = int(float(d.courier_fee or 0))
    text = (
        f"✅ <b>Доставка #Д-{delivery_id} ваша!</b>\n\n🏪 Забрать: {helpers.escape(d.from_address)}\n"
        f"🏠 Доставить: {helpers.escape(d.to_address)}\n👤 {helpers.escape(d.client_name)}, {helpers.escape(d.client_phone)}\n💰 Заработок: {fee} ₽"
    )
    if d.shop_comment: text += f"\n💬 Магазин: {helpers.escape(d.shop_comment)}"
    if d.client_comment: text += f"\n💬 Клиент: {helpers.escape(d.client_comment)}"

    rows = [
        [kb.btn("📦 Забрал", f"courier_del_picked_{delivery_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))

    async with async_session() as s2:
        sr = await s2.execute(select(Shop).where(Shop.id == d.shop_id))
        shop = sr.scalar_one_or_none()
    if shop and shop.tg_id:
        try: await bot_shop.send_message(shop.tg_id, f"🚴 Курьер {helpers.escape(courier.name)} взял доставку #Д-{delivery_id}")
        except Exception: pass
    await call.answer()

# ═══════════════════════════════════════════
#   СТАТУСЫ ЗАКАЗА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_picked_") & ~F.data.startswith("courier_del_picked_"))
async def picked(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await orders_service.update_order_status(session, order_id, "picked")
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    text = f"📦 <b>Заказ #{order_id} забран.</b>\n\nВезём: {helpers.escape(order.address)}"
    rows = [
        [kb.btn("🏠 У клиента", f"courier_at_client_{order_id}")],
        [kb.btn("🗺 Маршрут", f"courier_map_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))

    if client and client.tg_id:
        try: await bot_client.send_message(client.tg_id, f"📦 <b>Курьер забрал ваш букет!</b>\n🚴 Везёт: {helpers.escape(order.address)}")
        except Exception: pass
    await call.answer()

@router.callback_query(F.data.startswith("courier_at_client_"))
async def at_client(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await orders_service.update_order_status(session, order_id, "at_client")

    rows = [
        [kb.btn("✅ Доставлено", f"courier_done_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(f"📍 <b>Заказ #{order_id} у клиента.</b>\n\nПередали букет? Нажмите «Доставлено».", reply_markup=kb.kb(rows))
    await call.answer()

@router.callback_query(F.data.startswith("courier_done_") & ~F.data.startswith("courier_done_del_"))
async def done(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()

    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order.need_delivery_photo:
        await state.update_data(order_id=order_id, target_type="order")
        await state.set_state(CourierFSM.delivery_photo)
        await call.message.edit_text("📸 <b>ФОТО ОБЯЗАТЕЛЬНО</b>\n\nСфотографируйте момент передачи букета.", reply_markup=kb.kb([[kb.btn("❌ Отмена", "courier_menu")]]))
        await call.answer()
        return

    await complete_delivery_order(call.message, order_id, call.from_user.id)
    await call.answer()

# ═══════════════════════════════════════════
#   СТАТУСЫ СВОЕЙ ДОСТАВКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_del_picked_"))
async def del_picked(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await session.execute(update(DeliveryOrder).where(DeliveryOrder.id == delivery_id).values(status="picked"))
        await session.commit()
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()

    rows = [
        [kb.btn("🏠 У клиента", f"courier_del_at_client_{delivery_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(f"📦 <b>Доставка #Д-{delivery_id} забрана.</b>\n\nВезём: {helpers.escape(d.to_address)}", reply_markup=kb.kb(rows))
    await call.answer()

@router.callback_query(F.data.startswith("courier_del_at_client_"))
async def del_at_client(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await session.execute(update(DeliveryOrder).where(DeliveryOrder.id == delivery_id).values(status="at_client"))
        await session.commit()

    rows = [
        [kb.btn("✅ Доставлено", f"courier_del_done_{delivery_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(f"📍 <b>Доставка #Д-{delivery_id} у клиента.</b>\n\nПередали букет?", reply_markup=kb.kb(rows))
    await call.answer()

@router.callback_query(F.data.startswith("courier_del_done_"))
async def del_done(call: CallbackQuery, state: FSMContext):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()

    if not d:
        await call.answer("Не найдено", show_alert=True)
        return

    if d.need_delivery_photo:
        await state.update_data(delivery_id=delivery_id, target_type="delivery")
        await state.set_state(CourierFSM.delivery_photo)
        await call.message.edit_text("📸 <b>ФОТО ОБЯЗАТЕЛЬНО</b>\n\nСфотографируйте момент передачи.", reply_markup=kb.kb([[kb.btn("❌ Отмена", "courier_menu")]]))
        await call.answer()
        return

    await complete_delivery_shop(call.message, delivery_id, call.from_user.id)
    await call.answer()

# ═══════════════════════════════════════════
#   ФОТО ВРУЧЕНИЯ
# ═══════════════════════════════════════════
@router.message(CourierFSM.delivery_photo, F.photo)
async def receive_delivery_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("target_type", "order")
    obj_id = data.get("order_id") or data.get("delivery_id")
    photo_id = message.photo[-1].file_id

    if target == "order":
        async with async_session() as session:
            o_r = await session.execute(select(Order).where(Order.id == obj_id))
            order = o_r.scalar_one_or_none()
            if order:
                order.delivery_photo_id = photo_id
                await session.commit()

                try: await bot_admin.send_photo(config.ADMIN_ID, photo_id, caption=f"📸 <b>Заказ #{order.id} доставлен</b>")
                except Exception: pass

                s_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
                shop = s_r.scalar_one_or_none()
                if shop and shop.tg_id:
                    try: await bot_shop.send_photo(shop.tg_id, photo_id, caption=f"📸 <b>Заказ #{order.id} доставлен</b>")
                    except Exception: pass

        await state.clear()
        await complete_delivery_order(message, obj_id, message.from_user.id)
    else:
        async with async_session() as session:
            d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == obj_id))
            d = d_r.scalar_one_or_none()
            if d:
                d.delivery_photo_id = photo_id
                await session.commit()

                try: await bot_admin.send_photo(config.ADMIN_ID, photo_id, caption=f"📸 <b>Доставка #Д-{d.id} выполнена</b>")
                except Exception: pass

                s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
                shop = s_r.scalar_one_or_none()
                if shop and shop.tg_id:
                    try: await bot_shop.send_photo(shop.tg_id, photo_id, caption=f"📸 <b>Доставка #Д-{d.id} выполнена</b>")
                    except Exception: pass

        await state.clear()
        await complete_delivery_shop(message, obj_id, message.from_user.id)

@router.message(CourierFSM.delivery_photo)
async def wrong_photo(message: Message):
    await message.answer("⚠️ <b>Нужно именно фото!</b>")

# ═══════════════════════════════════════════
#   ЗАВЕРШЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
async def complete_delivery_order(message: Message, order_id: int, courier_tg_id: int):
    async with async_session() as session:
        courier = await get_courier(session, courier_tg_id)
        order = await orders_service.complete_order(session, order_id)

        if not order or not courier:
            await message.answer("❌ Ошибка при завершении заказа.")
            return

        fee = float(order.courier_fee or 0) + float(order.boost_amount or 0)
        await session.refresh(courier)

        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    await message.answer(f"✅ <b>Заказ #{order_id} доставлен!</b>\n\n💰 +{int(fee)} ₽\n💳 Баланс: {helpers.money(courier.balance)}", reply_markup=kb.courier_main_on_shift())

    if client and client.tg_id:
        try:
            if order.delivery_photo_id:
                await bot_client.send_photo(
                    chat_id=client.tg_id, photo=order.delivery_photo_id,
                    caption=f"📸 <b>Заказ #{order_id} доставлен!</b>\n\nСпасибо! 🌸",
                    reply_markup=kb.rating_kb("shop", order_id)
                )
            else:
                await bot_client.send_message(client.tg_id, f"✅ <b>Заказ #{order_id} доставлен!</b>", reply_markup=kb.rating_kb("shop", order_id))
        except Exception: pass

async def complete_delivery_shop(message: Message, delivery_id: int, courier_tg_id: int):
    async with async_session() as session:
        courier = await get_courier(session, courier_tg_id)
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()
        if not d or not courier:
            await message.answer("❌ Ошибка.")
            return

        fee = Decimal(str(d.courier_fee or 0))
        d.status = "done"
        d.delivered_at = helpers.now_moscow()

        await session.execute(update(Courier).where(Courier.id == courier.id).values(balance=Courier.balance + fee, total_orders=Courier.total_orders + 1))
        courier.courier_state = "on"
        await session.commit()
        await session.refresh(courier)

        s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
        shop = s_r.scalar_one_or_none()

    await message.answer(f"✅ <b>Доставка #Д-{delivery_id} выполнена!</b>\n\n💰 +{int(fee)} ₽\n💳 Баланс: {helpers.money(courier.balance)}", reply_markup=kb.courier_main_on_shift())

    if shop and shop.tg_id:
        try:
            if d.delivery_photo_id:
                await bot_shop.send_photo(shop.tg_id, d.delivery_photo_id, caption=f"✅ Доставка #Д-{delivery_id} выполнена!")
            else:
                await bot_shop.send_message(shop.tg_id, f"✅ Доставка #Д-{delivery_id} выполнена!")
        except Exception: pass

# ═══════════════════════════════════════════
#   МАРШРУТЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_map_"))
async def map_route(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        courier = await get_courier(session, call.from_user.id)
        shop_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_r.scalar_one_or_none()

    if not order or not shop:
        await call.answer("Маршрут недоступен", show_alert=True)
        return

    points = []
    if courier.lat and courier.lon: points.append((float(courier.lat), float(courier.lon)))
    if shop.lat and shop.lon: points.append((float(shop.lat), float(shop.lon)))
    if order.lat and order.lon: points.append((float(order.lat), float(order.lon)))

    if len(points) < 2:
        await call.answer("Недостаточно координат", show_alert=True)
        return

    link = helpers.route_link(points)
    await call.message.answer(
        "🗺 <b>Маршрут построен!</b>\nНажмите кнопку ниже, чтобы открыть Яндекс.Карты.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺 Открыть карту", url=link)]])
    )
    await call.answer()

@router.callback_query(F.data == "courier_route_all")
async def route_all(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        orders = await orders_service.get_courier_active_orders(session, courier.id)
        
        if not orders:
            await call.answer("У вас нет активных заказов", show_alert=True)
            return

        points = []
        if courier.lat and courier.lon:
            points.append((float(courier.lat), float(courier.lon)))
        
        for o in orders:
            shop_r = await session.execute(select(Shop).where(Shop.id == o.shop_id))
            shop = shop_r.scalar_one_or_none()
            if shop and shop.lat and shop.lon:
                points.append((float(shop.lat), float(shop.lon)))
        
        for o in orders:
            if o.lat and o.lon:
                points.append((float(o.lat), float(o.lon)))

    if len(points) < 2:
        await call.answer("Недостаточно координат для маршрута", show_alert=True)
        return

    link = helpers.route_link(points)
    await call.message.answer(
        f"🗺 <b>Маршрут по {len(orders)} заказам</b>\n\nСначала заберите букеты из магазинов, затем развезите клиентам.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺 Открыть карту", url=link)]])
    )
    await call.answer()

# ═══════════════════════════════════════════
#   ПРОБЛЕМА
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_problem_"))
async def courier_problem(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🆘 <b>Проблема у курьера!</b>\n\nЗаказ #{order_id}\nКурьер нажал «Проблема»."
        )
    except Exception: pass
    await call.answer("🆘 Администратор уведомлен.", show_alert=True)

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

@router.callback_query(F.data == "courier_tx_history")
async def tx_history(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        txs = await payments_service.get_user_transactions(session, "courier", courier.id, 30)

    if not txs:
        await call.message.edit_text("📜 История пуста.", reply_markup=kb.courier_balance_menu())
        await call.answer()
        return

    text = "📜 <b>История:</b>\n\n"
    for t in txs:
        sign = "+" if float(t.amount) >= 0 else ""
        text += f"{helpers.format_dt(t.created_at)} — {sign}{helpers.money(t.amount)} — {t.type}\n"

    await call.message.edit_text(text, reply_markup=kb.courier_balance_menu())
    await call.answer()

@router.callback_query(F.data == "courier_withdraw")
async def withdraw_start(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if float(courier.balance) < config.COURIER_MIN_WITHDRAW:
            await call.answer(f"Минимум {config.COURIER_MIN_WITHDRAW} ₽", show_alert=True)
            return

    await call.message.edit_text(
        f"💸 <b>Вывод средств</b>\n\n💰 Баланс: {helpers.money(courier.balance)}\n💳 Минимум: {config.COURIER_MIN_WITHDRAW} ₽\n\nВыберите способ:",
        reply_markup=kb.courier_withdraw_method()
    )
    await call.answer()

@router.callback_query(F.data == "cw_card")
async def cw_card(call: CallbackQuery, state: FSMContext):
    await state.set_state(CourierFSM.withdraw_amount)
    await state.update_data(method="card")
    await call.message.edit_text("💳 Введите сумму:", reply_markup=kb.cancel_kb("courier_balance"))
    await call.answer()

@router.callback_query(F.data == "cw_sbp")
async def cw_sbp(call: CallbackQuery, state: FSMContext):
    await state.set_state(CourierFSM.withdraw_amount)
    await state.update_data(method="sbp")
    await call.message.edit_text("📱 Введите сумму:", reply_markup=kb.cancel_kb("courier_balance"))
    await call.answer()

@router.message(CourierFSM.withdraw_amount)
async def process_withdraw(message: Message, state: FSMContext):
    try: amount = Decimal(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        if amount < config.COURIER_MIN_WITHDRAW:
            await message.answer(f"❌ Минимум {config.COURIER_MIN_WITHDRAW} ₽")
            return
        if amount > courier.balance:
            await message.answer("❌ Недостаточно средств.")
            return

        data = await state.get_data()
        method = data.get("method", "card")

        payout = await payments_service.create_payout(
            session=session, user_type="courier", user_id=courier.id, amount=amount, method=method,
            card_number=courier.card_number, bank_name=courier.bank_name,
            card_holder=courier.card_holder, sbp_phone=courier.sbp_phone,
        )

    await state.clear()
    if not payout:
        await message.answer("❌ Ошибка. Недостаточно средств.", reply_markup=kb.courier_main_on_shift())
        return
    await message.answer(f"✅ Заявка на вывод {helpers.money(amount)} отправлена.", reply_markup=kb.courier_main_on_shift())

# ═══════════════════════════════════════════
#   СТАТИСТИКА И ДОСТИЖЕНИЯ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_stats")
async def courier_stats(call: CallbackQuery):
    await call.message.edit_text("📊 <b>Статистика</b>\n\nВыберите период:", reply_markup=kb.courier_stats_menu())
    await call.answer()

@router.callback_query(F.data.startswith("courier_stats_") & ~F.data.startswith("courier_stats_menu"))
async def courier_stats_period(call: CallbackQuery):
    period = call.data.replace("courier_stats_", "")
    now = helpers.now_moscow()
    if period == "today": since, label = now.replace(hour=0, minute=0, second=0, microsecond=0), "Сегодня"
    elif period == "week": since, label = now - timedelta(days=7), "За неделю"
    elif period == "month": since, label = now - timedelta(days=30), "За месяц"
    else: since, label = datetime(2020, 1, 1), "За всё время"

    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        r = await session.execute(select(Order).where(Order.courier_id == courier.id, Order.delivered_at >= since, Order.status == "done"))
        done_orders = r.scalars().all()

        level_info = bonuses_service.get_level_by_orders(courier.total_orders)
        next_level = bonuses_service.get_next_level(courier.total_orders)
        bonus = await bonuses_service.calculate_daily_bonus(session, courier.id)

    earned = sum(float(o.courier_fee or 0) + float(o.boost_amount or 0) for o in done_orders)

    text = (
        f"📊 <b>Статистика — {label}</b>\n\n📦 Доставок: {len(done_orders)}\n"
        f"💰 Заработано: {helpers.money(earned)}\n⭐ Рейтинг: {float(courier.rating or 0):.1f}\n\n"
        f"{level_info[1]}"
    )
    if next_level: text += f"\nДо {next_level[1]}: {next_level[2] - courier.total_orders} заказов"
    if bonus > 0: text += f"\n\n🎁 Бонус за сегодня: {helpers.money(bonus)}"

    await call.message.edit_text(text, reply_markup=kb.courier_stats_menu())
    await call.answer()

@router.callback_query(F.data == "courier_achievements")
async def achievements(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        got = await bonuses_service.get_courier_achievements(session, courier.id)

    got_codes = {a.code for a in got}
    total = len(bonuses_service.ACHIEVEMENTS_LIST)

    text = f"🏆 <b>Достижения ({len(got_codes)}/{total})</b>\n\n"
    for a in bonuses_service.ACHIEVEMENTS_LIST:
        mark = "✅" if a["code"] in got_codes else "⬜"
        text += f"{mark} {a['icon']} <b>{a['title']}</b>\n   {a['description']}\n\n"

    await call.message.edit_text(text, reply_markup=kb.courier_stats_menu())
    await call.answer()

@router.callback_query(F.data == "courier_referral")
async def courier_referral(call: CallbackQuery):
    ref_link = helpers.referral_link(call.from_user.id)
    text = f"🎁 <b>Приглашай друзей!</b>\n\nПолучай {config.REFERRAL_PERCENT}% от заработка приглашённых ({config.REFERRAL_MONTHS} мес.)\n\n🔗 {ref_link}"
    await call.message.edit_text(text, reply_markup=kb.courier_referral_menu(ref_link))
    await call.answer()

@router.callback_query(F.data == "courier_ref_copy")
async def ref_copy(call: CallbackQuery):
    link = helpers.referral_link(call.from_user.id)
    await call.message.answer(f"<code>{link}</code>")
    await call.answer("Скопировано")

# ═══════════════════════════════════════════
#   РЕКВИЗИТЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_requisites")
async def courier_requisites(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
    text = (
        f"💳 <b>Реквизиты для выплат</b>\n\n💳 Карта: {helpers.format_card(courier.card_number or '—')}\n"
        f"🏦 Банк: {courier.bank_name or '—'}\n👤 ФИО: {helpers.escape(courier.card_holder or '—')}\n📱 СБП: {courier.sbp_phone or '—'}"
    )
    await call.message.edit_text(text, reply_markup=kb.courier_requisites_menu())
    await call.answer()

@router.callback_query(F.data == "courier_req_card")
async def cr_card(call: CallbackQuery, state: FSMContext):
    await state.set_state(CourierFSM.req_card)
    await call.message.edit_text("💳 Номер карты (16 цифр):", reply_markup=kb.cancel_kb("courier_requisites"))
    await call.answer()

@router.message(CourierFSM.req_card)
async def cr_card_save(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер.")
        return
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        courier.card_number = helpers.clean_phone(message.text)
        await session.commit()
    await state.clear()
    await message.answer("✅ Карта сохранена.", reply_markup=kb.courier_main_on_shift())

@router.callback_query(F.data == "courier_req_bank")
async def cr_bank(call: CallbackQuery):
    await call.message.edit_text("🏦 Выберите банк:", reply_markup=kb.courier_banks_kb())
    await call.answer()

@router.callback_query(F.data.startswith("cour_bank_"))
async def cr_bank_save(call: CallbackQuery):
    bank = call.data.replace("cour_bank_", "")
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        courier.bank_name = bank
        await session.commit()
    await call.answer(f"✅ {bank}", show_alert=True)
    await courier_requisites(call)

@router.callback_query(F.data == "courier_req_holder")
async def cr_holder(call: CallbackQuery, state: FSMContext):
    await state.set_state(CourierFSM.req_holder)
    await call.message.edit_text("👤 ФИО владельца карты:", reply_markup=kb.cancel_kb("courier_requisites"))
    await call.answer()

@router.message(CourierFSM.req_holder)
async def cr_holder_save(message: Message, state: FSMContext):
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        courier.card_holder = message.text.strip()
        await session.commit()
    await state.clear()
    await message.answer("✅ ФИО сохранено.", reply_markup=kb.courier_main_on_shift())

@router.callback_query(F.data == "courier_req_sbp")
async def cr_sbp(call: CallbackQuery, state: FSMContext):
    await state.set_state(CourierFSM.req_sbp)
    await call.message.edit_text("📱 Телефон для СБП:", reply_markup=kb.cancel_kb("courier_requisites"))
    await call.answer()

@router.message(CourierFSM.req_sbp)
async def cr_sbp_save(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)
        courier.sbp_phone = helpers.clean_phone(message.text)
        await session.commit()
    await state.clear()
    await message.answer("✅ СБП сохранён.", reply_markup=kb.courier_main_on_shift())

# ═══════════════════════════════════════════
#   АКТИВНЫЕ ЗАКАЗЫ (С МАРШРУТОМ ПО ВСЕМ)
# ═══════════════════════════════════════════
@router.callback_query(F.data == "courier_my_orders")
async def my_orders(call: CallbackQuery):
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        orders = await orders_service.get_courier_active_orders(session, courier.id)

        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.courier_id == courier.id, DeliveryOrder.status.in_(["going", "picked", "at_client"])))
        deliveries = d_r.scalars().all()

    if not orders and not deliveries:
        await call.message.edit_text("🚗 Активных заказов нет.", reply_markup=kb.kb([[kb.btn("🔙 В меню", "courier_menu")]]))
        await call.answer()
        return

    text = "🚗 <b>Активные заказы</b>\n\n"
    rows = []
    for o in orders:
        text += f"#{o.id} — {helpers.status_text(o.status)}\n📍 {helpers.escape(o.address)}\n\n"
        rows.append([kb.btn(f"📦 Заказ #{o.id}", f"courier_view_{o.id}")])
    for d in deliveries:
        text += f"#Д-{d.id} — {helpers.escape(d.to_address)}\n\n"
        rows.append([kb.btn(f"🚚 Доставка #Д-{d.id}", f"courier_view_del_{d.id}")])
    
    if orders:
        rows.append([kb.btn("🗺 Маршрут по всем", "courier_route_all")])
    rows.append([kb.btn("🔙 В меню", "courier_menu")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()

@router.callback_query(F.data.startswith("courier_view_") & ~F.data.startswith("courier_view_del_"))
async def view_active_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        shop_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_r.scalar_one_or_none()

    if not order:
        await call.answer("Не найден", show_alert=True)
        return

    text = f"📦 <b>Заказ #{order.id}</b>\n\n🏪 {helpers.escape(shop.address if shop else '—')}\n🏠 {helpers.escape(order.address)}\n👤 {helpers.escape(order.client_name)}, {helpers.escape(order.client_phone)}"
    rows = []
    if order.status == "going": rows.append([kb.btn("📦 Забрал", f"courier_picked_{order_id}")])
    elif order.status == "picked": rows.append([kb.btn("🏠 У клиента", f"courier_at_client_{order_id}")])
    elif order.status == "at_client": rows.append([kb.btn("✅ Доставлено", f"courier_done_{order_id}")])
    rows.append([kb.btn("🗺 Маршрут", f"courier_map_{order_id}")])
    rows.append([kb.btn("🔙 Назад", "courier_my_orders")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()

@router.callback_query(F.data.startswith("courier_view_del_"))
async def view_active_delivery(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()

    if not d:
        await call.answer("Не найдено", show_alert=True)
        return

    text = f"🚚 <b>Доставка #Д-{d.id}</b>\n\n🏪 {helpers.escape(d.from_address)}\n🏠 {helpers.escape(d.to_address)}\n👤 {helpers.escape(d.client_name)}, {helpers.escape(d.client_phone)}"
    rows = []
    if d.status == "going": rows.append([kb.btn("📦 Забрал", f"courier_del_picked_{delivery_id}")])
    elif d.status == "picked": rows.append([kb.btn("🏠 У клиента", f"courier_del_at_client_{delivery_id}")])
    elif d.status == "at_client": rows.append([kb.btn("✅ Доставлено", f"courier_del_done_{delivery_id}")])
    rows.append([kb.btn("🔙 Назад", "courier_my_orders")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()
    
    
