# -*- coding: utf-8 -*-
"""
SLIPI — бот курьера
"""
from datetime import datetime, date, timedelta
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
#   /start И РЕГИСТРАЦИЯ
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        courier = await get_courier(session, message.from_user.id)

    if not courier:
        await message.answer("🚴 <b>Стать курьером SLIPI</b>\n\nОтправьте команду /register чтобы зарегистрироваться.")
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
    await call.message.edit_text(f"🆘 <b>Поддержка SLIPI</b>\n\nНапишите: {config.SUPPORT_TG}\n📞 {config.SUPPORT_PHONE}", reply_markup=kb.courier_support())
    await call.answer()

@router.message(Command("register"))
async def courier_register(message: Message, state: FSMContext):
    async with async_session() as session:
        existing = await get_courier(session, message.from_user.id)
        if existing:
            await message.answer("Вы уже зарегистрированы.")
            return

    await state.set_state(CourierReg.name)
    await message.answer("📝 <b>Шаг 1/6:</b> Ваше имя", reply_markup=kb.cancel_kb("courier_menu"))

@router.message(CourierReg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CourierReg.phone)
    await message.answer("📞 <b>Шаг 2/6:</b> Телефон", reply_markup=kb.cancel_kb("courier_menu"))

@router.message(CourierReg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(phone=helpers.clean_phone(message.text))
    await state.set_state(CourierReg.city)
    await message.answer(f"🏙 <b>Шаг 3/6:</b> Город\n\n<i>Например: {config.CITY}</i>", reply_markup=kb.cancel_kb("courier_menu"))

@router.message(CourierReg.city)
async def reg_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(CourierReg.transport)
    await message.answer("🚗 <b>Шаг 4/6:</b> Транспорт?", reply_markup=kb.kb([
        [kb.btn("🚗 Авто", "reg_transport_auto"), kb.btn("🏍 Мото", "reg_transport_moto")],
        [kb.btn("🚲 Вело", "reg_transport_bike"), kb.btn("🚶 Пешком", "reg_transport_walk")],
        [kb.btn("❌ Отмена", "courier_menu")],
    ]))

@router.callback_query(F.data.startswith("reg_transport_"), CourierReg.transport)
async def reg_transport(call: CallbackQuery, state: FSMContext):
    tr = call.data.replace("reg_transport_", "")
    names = {"auto": "Авто", "moto": "Мото", "bike": "Вело", "walk": "Пешком"}
    await state.update_data(transport=names.get(tr, tr))
    await state.set_state(CourierReg.card)
    await call.message.edit_text("💳 <b>Шаг 5/6:</b> Номер карты (16 цифр)", reply_markup=kb.cancel_kb("courier_menu"))
    await call.answer()

@router.message(CourierReg.card)
async def reg_card(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты.")
        return
    await state.update_data(card=helpers.clean_phone(message.text))
    await state.set_state(CourierReg.referral)
    await message.answer("🎁 <b>Шаг 6/6:</b> Реферальный код\n\nВведите или /skip", reply_markup=kb.cancel_kb("courier_menu"))

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
            city=data["city"], transport=data["transport"], card_number=data["card"],
            status="pending", courier_state="off",
        )
        session.add(courier)
        await session.commit()
        await session.refresh(courier)

        if ref_tg_id:
            await bonuses_service.register_referral(session, courier.id, ref_tg_id)

    await state.clear()
    await message.answer("✅ <b>Заявка отправлена!</b>\n\nЖдите одобрения админа.", reply_markup=kb.courier_main_off_shift())

    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🚴 <b>Новая заявка курьера</b>\n\n👤 {data['name']}\n📞 {data['phone']}\n🏙 {data['city']}\n🚗 {data['transport']}",
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
#   СВОБОДНЫЕ ЗАКАЗЫ (С УЧЕТОМ БУСТА)
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
            
            # ИСПРАВЛЕНО: Учитываем буст при показе цены
            fee = float(o.courier_fee or 0) + float(o.boost_amount or 0)
            
            wait_min = 0
            if o.wait_started_at: wait_min = int((datetime.now() - o.wait_started_at).total_seconds() / 60)
            
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
        text += f"{prefix} <b>{it['id']}</b> — {it['fee']} ₽{boost_str}\n📍 {it['address']}\n📏 {it['distance']} км | ⏱ {it['wait_min']} мин\n\n"

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
#   ВЗЯТИЕ ЗАКАЗОВ
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("courier_take_") & ~F.data.startswith("courier_take_del_"))
async def take_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return

        ok = await orders_service.take_order(session, order_id, courier.id)
        if not ok:
            await call.answer("😔 Уже занят или вы не на смене", show_alert=True)
            return

        courier.courier_state = "busy"
        await session.commit()

        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        shop_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_r.scalar_one_or_none()
        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    fee = int(float(order.courier_fee or 0) + float(order.boost_amount or 0))
    text = (
        f"✅ <b>Заказ #{order_id} ваш!</b>\n\n🏪 Забрать: {shop.address if shop else '—'}\n"
        f"🏠 Доставить: {order.address}\n👤 {order.client_name}, {order.client_phone}\n💰 Заработок: {fee} ₽"
    )
    rows = [
        [kb.btn("📦 Забрал", f"courier_picked_{order_id}")],
        [kb.btn("🗺 Маршрут", f"courier_map_{order_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))

    if client and client.tg_id:
        try: await bot_client.send_message(client.tg_id, f"🚴 <b>Курьер назначен на заказ #{order_id}</b>\n\n👤 {courier.name}\n⭐ {float(courier.rating or 0):.1f}")
        except Exception: pass
    await call.answer()

@router.callback_query(F.data.startswith("courier_take_del_"))
async def take_delivery(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[3])
    async with async_session() as session:
        courier = await get_courier(session, call.from_user.id)
        if not courier: return

        result = await session.execute(
            update(DeliveryOrder).where(DeliveryOrder.id == delivery_id, DeliveryOrder.status == "confirmed", DeliveryOrder.courier_id.is_(None))
            .values(courier_id=courier.id, status="going", taken_at=datetime.now())
        )
        await session.commit()
        if result.rowcount != 1:
            await call.answer("😔 Уже занято", show_alert=True)
            return

        courier.courier_state = "busy"
        await session.commit()
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()

    fee = int(float(d.courier_fee or 0))
    text = (
        f"✅ <b>Доставка #Д-{delivery_id} ваша!</b>\n\n🏪 Забрать: {d.from_address}\n"
        f"🏠 Доставить: {d.to_address}\n👤 {d.client_name}, {d.client_phone}\n💰 Заработок: {fee} ₽"
    )
    if d.shop_comment: text += f"\n💬 Магазин: {d.shop_comment}"
    if d.client_comment: text += f"\n💬 Клиент: {d.client_comment}"

    rows = [
        [kb.btn("📦 Забрал", f"courier_del_picked_{delivery_id}")],
        [kb.btn("🔙 В меню", "courier_menu")],
    ]
    await call.message.edit_text(text, reply_markup=kb.kb(rows))

    async with async_session() as s2:
        sr = await s2.execute(select(Shop).where(Shop.id == d.shop_id))
        shop = sr.scalar_one_or_none()
    if shop and shop.tg_id:
        try: await bot_shop.send_message(shop.tg_id, f"🚴 Курьер {courier.name} взял доставку #Д-{delivery_id}")
        except Exception: pass
    await call.answer()
