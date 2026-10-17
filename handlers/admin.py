# -*- coding: utf-8 -*-
"""
Flowers Express — бот админа
"""
from datetime import datetime, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update, delete as sa_delete

import config
import keyboards as kb
from states import AdminFSM
from database import async_session
from models import (
    Shop, Courier, Order, Payment, Payout, Client,
    Promo, Log, DeliveryOrder, DeliveryPayment, Complaint,
    Admin, BotUpdate, OrderItem,
)
from services import orders as orders_service
from services import payments as payments_service
from services import notify
from utils import helpers
from bots import bot_client, bot_shop, bot_courier, bot_admin

router = Router(name="admin")

# ═══════════════════════════════════════════
#   ПРАВА АДМИНОВ
# ═══════════════════════════════════════════
async def get_admin_permissions(session, tg_id: int):
    if tg_id == config.ADMIN_ID: return None
    r = await session.execute(select(Admin).where(Admin.tg_id == tg_id, Admin.is_active == True))
    admin = r.scalar_one_or_none()
    if not admin: return False
    return helpers.parse_permissions(admin.permissions)

def has_perm(permissions, key: str) -> bool:
    if permissions is None: return True
    if permissions is False: return False
    return permissions.get(key, False)

async def log_action(text: str):
    try:
        async with async_session() as session:
            session.add(Log(text=text))
            await session.commit()
    except Exception: pass

# ═══════════════════════════════════════════
#   СТАРТ И ДАШБОРД
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        perms = await get_admin_permissions(session, message.from_user.id)
    if perms is False:
        await message.answer("🚫 Доступ запрещён.")
        return
    await show_dashboard(message, perms, edit=False)

async def show_dashboard(message: Message, perms, edit: bool = False):
    async with async_session() as session:
        summary = await payments_service.get_finance_summary(session)
        shops_count = len((await session.execute(select(Shop).where(Shop.status == "pending"))).scalars().all())
        couriers_count = len((await session.execute(select(Courier).where(Courier.status == "pending"))).scalars().all())
        payments_count = len((await session.execute(select(Payment).where(Payment.status == "pending"))).scalars().all())
        del_payments_count = len((await session.execute(select(DeliveryPayment).where(DeliveryPayment.status == "pending"))).scalars().all())
        payouts_count = len((await session.execute(select(Payout).where(Payout.status == "pending"))).scalars().all())
        in_work = await payments_service.get_orders_in_work(session)

    total_pending = shops_count + couriers_count
    text = (
        f"👑 <b>Админ-панель {config.SERVICE_NAME}</b>\n\n"
        f"📨 Заявок: {total_pending}\n🚗 В работе: {in_work}\n"
        f"💳 Ожидают оплаты: {payments_count}\n🚚 Доставки: {del_payments_count}\n"
        f"💸 Выплаты: {payouts_count}\n💰 Доход: {helpers.money(summary['platform_income'])}"
    )
    markup = kb.admin_main(perms)
    if edit:
        try: await message.edit_text(text, reply_markup=markup)
        except Exception: await message.answer(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)

@router.callback_query(F.data == "admin_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if perms is False:
        await call.answer("Нет доступа", show_alert=True)
        return
    await show_dashboard(call.message, perms, edit=True)
    await call.answer()

# ═══════════════════════════════════════════
#   ЗАЯВКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_requests")
async def requests_menu(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "requests"):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("📨 <b>Заявки</b>", reply_markup=kb.admin_requests_menu())
    await call.answer()

@router.callback_query(F.data == "admin_req_shops")
async def req_shops(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.status == "pending"))
        shops = r.scalars().all()

    if not shops:
        await call.message.edit_text("✅ Нет новых заявок магазинов.", reply_markup=kb.admin_requests_menu())
        await call.answer()
        return

    for s in shops[:10]:
        text = f"🏪 <b>Новый магазин</b>\n\n📛 {helpers.escape(s.name)}\n📍 {helpers.escape(s.address or '—')}\n📞 {helpers.escape(s.phone or '—')}"
        await call.message.answer(text, reply_markup=kb.admin_approve_shop(s.id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_shop_ok_"))
async def shop_ok(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "active"
            await session.commit()
            if shop.tg_id:
                text = (
                    f"🎉 <b>Ваш магазин «{helpers.escape(shop.name)}» одобрен!</b>\n\n"
                    f"Вот краткая инструкция:\n"
                    f"1️⃣ <b>Добавьте товары</b> в разделе «📦 Мои товары».\n"
                    f"2️⃣ <b>Настройте график</b> в «⚙️ Настройки» → «📅 График работы».\n"
                    f"3️⃣ Когда будете готовы принимать заказы, нажмите <b>«🟢 Выйти на смену»</b> в главном меню.\n\n"
                    f"После этого вам начнут приходить заказы! 🚀"
                )
                try: await bot_shop.send_message(shop.tg_id, text, reply_markup=kb.shop_main(False))
                except Exception: pass
    await log_action(f"Магазин #{shop_id} одобрен")
    await call.message.edit_text(f"✅ Магазин #{shop_id} одобрен.")
    await call.answer()

@router.callback_query(F.data.startswith("admin_shop_no_"))
async def shop_no(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "blocked"
            await session.commit()
            if shop.tg_id:
                try: await bot_shop.send_message(shop.tg_id, "❌ Ваш магазин отклонён.")
                except Exception: pass
    await log_action(f"Магазин #{shop_id} отклонён")
    await call.message.edit_text(f"❌ Магазин #{shop_id} отклонён.")
    await call.answer()

@router.callback_query(F.data == "admin_req_couriers")
async def req_couriers(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.status == "pending"))
        couriers = r.scalars().all()

    if not couriers:
        await call.message.edit_text("✅ Нет заявок курьеров.", reply_markup=kb.admin_requests_menu())
        await call.answer()
        return

    for c in couriers[:10]:
        text = f"🚴 <b>Новый курьер</b>\n\n👤 {helpers.escape(c.name)}\n📞 {helpers.escape(c.phone or '—')}\n🏙 {helpers.escape(c.city or '—')}\n🚗 {helpers.escape(c.transport or '—')}"
        await call.message.answer(text, reply_markup=kb.admin_approve_courier(c.id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_cour_ok_"))
async def cour_ok(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = r.scalar_one_or_none()
        if c:
            c.status = "active"
            c.is_blocked = False
            await session.commit()
            if c.tg_id:
                try: await bot_courier.send_message(c.tg_id, "✅ Вы одобрены! Отправьте /start")
                except Exception: pass
    await log_action(f"Курьер #{courier_id} одобрен")
    await call.message.edit_text(f"✅ Курьер #{courier_id} одобрен.")
    await call.answer()

@router.callback_query(F.data.startswith("admin_cour_no_"))
async def cour_no(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = r.scalar_one_or_none()
        if c:
            c.status = "blocked"
            c.is_blocked = True
            await session.commit()
            if c.tg_id:
                try: await bot_courier.send_message(c.tg_id, "❌ Заявка отклонена.")
                except Exception: pass
    await log_action(f"Курьер #{courier_id} отклонён")
    await call.message.edit_text(f"❌ Курьер #{courier_id} отклонён.")
    await call.answer()

# ═══════════════════════════════════════════
#   МАГАЗИНЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_shops")
async def admin_shops(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "shops"):
        await call.answer("Нет доступа", show_alert=True)
        return
    await admin_shops_page(call, 0)

async def admin_shops_page(call: CallbackQuery, page: int):
    async with async_session() as session:
        result = await session.execute(select(Shop).order_by(Shop.id.desc()).limit(200))
        all_shops = result.scalars().all()

    start = page * 10
    page_shops = all_shops[start:start + 10]
    items = [{"id": s.id, "name": s.name, "status": s.status} for s in page_shops]
    await call.message.edit_text(f"🏪 <b>Магазины ({len(all_shops)})</b>\n\nСтр. {page + 1}", reply_markup=kb.admin_shops_list(items, page))
    await call.answer()

@router.callback_query(F.data.startswith("admin_shops_page_"))
async def admin_shops_page_route(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    await admin_shops_page(call, page)

@router.callback_query(F.data.startswith("admin_shop_view_"))
async def admin_shop_view(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if not shop: return
        orders_r = await session.execute(select(Order).where(Order.shop_id == shop_id, Order.status == "done"))
        done_orders = orders_r.scalars().all()
        turnover = sum(float(o.total_price) for o in done_orders)

    status_map = {"active": "🟢", "pending": "🟡", "blocked": "🔴"}
    text = (
        f"🏪 <b>{helpers.escape(shop.name)}</b> {status_map.get(shop.status, '')}\n\n"
        f"👤 {helpers.escape(shop.owner_name or '—')}\n📞 {helpers.escape(shop.phone or '—')}\n📍 {helpers.escape(shop.address or '—')}\n"
        f"⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})\n\n"
        f"📦 Заказов: {len(done_orders)}\n💰 Оборот: {helpers.money(turnover)}\n🏦 Баланс: {helpers.money(shop.balance)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_shop_card(shop_id, shop.status))
    await call.answer()

@router.callback_query(F.data.startswith("admin_shop_block_"))
async def admin_shop_block(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "blocked"
            await session.commit()
            if shop.tg_id:
                try: await bot_shop.send_message(shop.tg_id, f"🚫 <b>Магазин заблокирован.</b>\n\nПоддержка: {config.SUPPORT_TG}")
                except Exception: pass
    await log_action(f"Магазин #{shop_id} заблокирован")
    await call.answer("🚫 Заблокирован", show_alert=True)
    await admin_shop_view(call)

@router.callback_query(F.data.startswith("admin_shop_unblock_"))
async def admin_shop_unblock(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "active"
            await session.commit()
            if shop.tg_id:
                try: await bot_shop.send_message(shop.tg_id, "✅ Ваш магазин разблокирован!")
                except Exception: pass
    await log_action(f"Магазин #{shop_id} разблокирован")
    await call.answer("✅ Разблокирован", show_alert=True)
    await admin_shop_view(call)

@router.callback_query(F.data.startswith("admin_shop_stats_"))
async def admin_shop_stats(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        orders_r = await session.execute(select(Order).where(Order.shop_id == shop_id).order_by(Order.id.desc()))
        orders = orders_r.scalars().all()

    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    wait = sum(1 for o in orders if o.status == "wait")
    total_sum = sum(float(o.total_price) for o in orders if o.status == "done")

    text = f"📊 <b>Статистика магазина</b>\n\n📦 Всего: {len(orders)}\n✅ Доставлено: {done}\n❌ Отменено: {cancel}\n⏳ В работе: {wait}\n\n💰 Оборот: {helpers.money(total_sum)}"
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_shop_view_{shop_id}"))
    await call.answer()

@router.callback_query(F.data.startswith("admin_shop_msg_"))
async def admin_shop_msg(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[-1])
    await state.update_data(msg_target_type="shop", msg_target_id=shop_id)
    await state.set_state(AdminFSM.reply_to_client)
    await call.message.edit_text("✉️ Введите сообщение:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.callback_query(F.data.startswith("admin_shop_topup_"))
async def shop_topup_start(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[-1])
    await state.update_data(topup_shop_id=shop_id, topup_cour_id=None)
    await state.set_state(AdminFSM.topup_amount)
    await call.message.edit_text("💰 <b>Пополнение баланса магазина</b>\n\nВведите сумму:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.topup_amount)
async def shop_topup_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("topup_cour_id"): return 
    
    shop_id = data.get("topup_shop_id")
    if not shop_id: return

    try:
        amount = Decimal(message.text.replace(",", ".").strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if not shop:
            await message.answer("❌ Не найден.")
            await state.clear()
            return

        await payments_service.topup_shop_balance(session, shop_id, amount)

        if shop.tg_id:
            try: await bot_shop.send_message(shop.tg_id, f"💰 Баланс пополнен на {helpers.money(amount)}")
            except Exception: pass

    await log_action(f"Магазин #{shop_id} пополнен на {amount} ₽")
    await state.clear()
    await message.answer("✅ Баланс пополнен.", reply_markup=kb.admin_main())

@router.callback_query(F.data.startswith("admin_shop_edit_"))
async def admin_shop_edit(call: CallbackQuery):
    shop_id = int(call.data.split("_")[-1])
    await call.message.edit_text("✏️ <b>Что изменить?</b>", reply_markup=kb.admin_shop_edit_menu(shop_id))
    await call.answer()

@router.callback_query(F.data.startswith("ase_"))
async def ase_field_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    field = parts[1]
    shop_id = int(parts[-1])

    field_names = {"name": "название", "address": "адрес", "phone": "телефон", "geo": "гео"}
    await state.update_data(ase_shop_id=shop_id, ase_field=field)
    await state.set_state(AdminFSM.ase_field)

    if field == "geo":
        await call.message.edit_text("📍 Отправьте геолокацию:", reply_markup=kb.admin_cancel())
    else:
        await call.message.edit_text(f"✏️ Введите {field_names.get(field, field)}:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.ase_field, F.location)
async def ase_field_geo_save(message: Message, state: FSMContext):
    data = await state.get_data()
    shop_id = data.get("ase_shop_id")
    if data.get("ase_field") != "geo": return
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.lat = message.location.latitude
            shop.lon = message.location.longitude
            await session.commit()
    await state.clear()
    await message.answer("✅ Гео обновлено.", reply_markup=kb.admin_main())

@router.message(AdminFSM.ase_field)
async def ase_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    shop_id = data.get("ase_shop_id")
    field = data.get("ase_field")

    field_map = {"name": "name", "address": "address", "phone": "phone"}
    db_field = field_map.get(field)
    if not db_field:
        await state.clear()
        return

    value = message.text.strip()
    if field == "phone":
        if not helpers.is_valid_phone(value):
            await message.answer("❌ Неверный номер.")
            return
        value = helpers.clean_phone(value)

    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            setattr(shop, db_field, value)
            await session.commit()

    await state.clear()
    await message.answer("✅ Обновлено.", reply_markup=kb.admin_main())

# ═══════════════════════════════════════════
#   КУРЬЕРЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_couriers")
async def admin_couriers(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "couriers"):
        await call.answer("Нет доступа", show_alert=True)
        return
    await admin_couriers_page(call, 0)

async def admin_couriers_page(call: CallbackQuery, page: int):
    async with async_session() as session:
        result = await session.execute(select(Courier).order_by(Courier.id.desc()).limit(200))
        all_c = result.scalars().all()

    start = page * 10
    page_c = all_c[start:start + 10]
    items = [{"id": c.id, "name": c.name, "status": c.status, "balance": helpers.money(c.balance)} for c in page_c]
    await call.message.edit_text(f"🚴 <b>Курьеры ({len(all_c)})</b>\n\nСтр. {page + 1}", reply_markup=kb.admin_couriers_list(items, page))
    await call.answer()

@router.callback_query(F.data.startswith("admin_couriers_page_"))
async def admin_couriers_page_route(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    await admin_couriers_page(call, page)

@router.callback_query(F.data.startswith("admin_cour_view_"))
async def admin_cour_view(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(select(Courier).where(Courier.id == courier_id))
        courier = result.scalar_one_or_none()
        if not courier: return

    status_map = {"active": "🟢", "pending": "🟡", "blocked": "🔴"}
    state_map = {"on": "🟢 На смене", "off": "⚪ Не на смене", "break": "☕", "busy": "🚗"}

    text = (
        f"🚴 <b>{helpers.escape(courier.name)}</b> {status_map.get(courier.status, '')}\n{state_map.get(courier.courier_state, '—')}\n\n"
        f"📞 {helpers.escape(courier.phone or '—')}\n🏙 {helpers.escape(courier.city or '—')}\n🚗 {helpers.escape(courier.transport or '—')}\n"
        f"💳 {helpers.format_card(courier.card_number or '—')}\n\n"
        f"💰 Баланс: {helpers.money(courier.balance)}\n"
        f"⭐ {float(courier.rating or 0):.1f} ({courier.reviews_count})\n📦 Заказов: {courier.total_orders}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_courier_card(courier_id, courier.status))
    await call.answer()

@router.callback_query(F.data.startswith("admin_cour_block_"))
async def admin_cour_block(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = result.scalar_one_or_none()
        if c:
            c.status = "blocked"
            c.is_blocked = True
            await session.commit()
            if c.tg_id:
                try: await bot_courier.send_message(c.tg_id, f"🚫 <b>Доступ закрыт.</b>\n\nПоддержка: {config.SUPPORT_TG}")
                except Exception: pass
    await log_action(f"Курьер #{courier_id} заблокирован")
    await call.answer("🚫 Заблокирован", show_alert=True)
    await admin_cour_view(call)

@router.callback_query(F.data.startswith("admin_cour_unblock_"))
async def admin_cour_unblock(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        result = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = result.scalar_one_or_none()
        if c:
            c.status = "active"
            c.is_blocked = False
            await session.commit()
            if c.tg_id:
                try: await bot_courier.send_message(c.tg_id, "✅ Доступ открыт!")
                except Exception: pass
    await log_action(f"Курьер #{courier_id} разблокирован")
    await call.answer("✅ Разблокирован", show_alert=True)
    await admin_cour_view(call)

@router.callback_query(F.data.startswith("admin_cour_stats_"))
async def admin_cour_stats(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        orders_r = await session.execute(select(Order).where(Order.courier_id == courier_id).order_by(Order.id.desc()))
        orders = orders_r.scalars().all()

    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    earned = sum(float(o.courier_fee or 0) + float(o.boost_amount or 0) for o in orders if o.status == "done")

    text = f"📊 <b>Статистика курьера</b>\n\n📦 Всего: {len(orders)}\n✅ Доставлено: {done}\n❌ Отменено: {cancel}\n\n💰 Заработал: {helpers.money(earned)}"
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_cour_view_{courier_id}"))
    await call.answer()

@router.callback_query(F.data.startswith("admin_cour_msg_"))
async def admin_cour_msg(call: CallbackQuery, state: FSMContext):
    courier_id = int(call.data.split("_")[-1])
    await state.update_data(msg_target_type="courier", msg_target_id=courier_id)
    await state.set_state(AdminFSM.reply_to_client)
    await call.message.edit_text("✉️ Введите сообщение:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.callback_query(F.data.startswith("admin_cour_topup_"))
async def cour_topup_start(call: CallbackQuery, state: FSMContext):
    courier_id = int(call.data.split("_")[-1])
    await state.update_data(topup_cour_id=courier_id, topup_shop_id=None)
    await state.set_state(AdminFSM.topup_amount)
    await call.message.edit_text("💰 <b>Пополнение баланса курьера</b>\n\nВведите сумму:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.topup_amount)
async def cour_topup_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("topup_shop_id"): return 

    courier_id = data.get("topup_cour_id")
    if not courier_id: return

    try:
        amount = Decimal(message.text.replace(",", ".").strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = r.scalar_one_or_none()
        if not c:
            await message.answer("❌ Не найден.")
            await state.clear()
            return

        await payments_service.topup_courier_balance(session, courier_id, amount)

        if c.tg_id:
            try: await bot_courier.send_message(c.tg_id, f"💰 Баланс пополнен на {helpers.money(amount)}")
            except Exception: pass

    await log_action(f"Курьер #{courier_id} пополнен на {amount} ₽")
    await state.clear()
    await message.answer("✅ Баланс пополнен.", reply_markup=kb.admin_main())

@router.callback_query(F.data.startswith("admin_cour_edit_"))
async def admin_cour_edit(call: CallbackQuery):
    courier_id = int(call.data.split("_")[-1])
    await call.message.edit_text("✏️ <b>Что изменить?</b>", reply_markup=kb.admin_courier_edit_menu(courier_id))
    await call.answer()

@router.callback_query(F.data.startswith("ace_"))
async def ace_field_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    field = parts[1]
    courier_id = int(parts[-1])

    field_names = {"name": "имя", "phone": "телефон", "city": "город", "transport": "транспорт"}
    await state.update_data(ace_courier_id=courier_id, ace_field=field)
    await state.set_state(AdminFSM.ace_field)
    await call.message.edit_text(f"✏️ Введите {field_names.get(field, field)}:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.ace_field)
async def ace_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    courier_id = data.get("ace_courier_id")
    field = data.get("ace_field")

    field_map = {"name": "name", "phone": "phone", "city": "city", "transport": "transport"}
    db_field = field_map.get(field)
    if not db_field:
        await state.clear()
        return

    value = message.text.strip()
    if field == "phone":
        if not helpers.is_valid_phone(value):
            await message.answer("❌ Неверный номер.")
            return
        value = helpers.clean_phone(value)

    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = r.scalar_one_or_none()
        if c:
            setattr(c, db_field, value)
            await session.commit()

    await state.clear()
    await message.answer("✅ Обновлено.", reply_markup=kb.admin_main())
    # ═══════════════════════════════════════════
#   ПЛАТЕЖИ И ВЫПЛАТЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_payments")
async def payments_menu(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "payments"):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("💳 <b>Переводы и платежи</b>", reply_markup=kb.admin_payments_menu())
    await call.answer()

@router.callback_query(F.data == "admin_pay_incoming")
async def pay_incoming(call: CallbackQuery):
    async with async_session() as session:
        payments = await payments_service.get_pending_payments(session)

    if not payments:
        await call.message.edit_text("✅ Нет ожидающих платежей заказов.", reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payments[:10]:
        async with async_session() as session:
            c_r = await session.execute(select(Client).where(Client.id == p.client_id))
            client = c_r.scalar_one_or_none()

        text = (
            f"💳 <b>Платёж заказа #{p.order_id}</b>\n\n"
            f"👤 {helpers.escape(client.name if client else '—')}\n💰 {helpers.money(p.amount)}\n"
            f"🕒 {helpers.format_dt(p.created_at)}\n\n⚠️ Комментарий: <b>{p.order_id}</b>"
        )
        await call.message.answer(text, reply_markup=kb.admin_confirm_payment(p.order_id))
    await call.answer()

@router.callback_query(F.data == "admin_pay_deliveries")
async def pay_deliveries(call: CallbackQuery):
    async with async_session() as session:
        payments = await payments_service.get_pending_delivery_payments(session)

    if not payments:
        await call.message.edit_text("✅ Нет ожидающих платежей за доставки.", reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payments[:10]:
        async with async_session() as session:
            s_r = await session.execute(select(Shop).where(Shop.id == p.shop_id))
            shop = s_r.scalar_one_or_none()

        text = (
            f"🚚 <b>Платёж #Д-{p.delivery_id}</b>\n\n"
            f"🏪 {helpers.escape(shop.name if shop else '—')}\n💰 {helpers.money(p.amount)}\n"
            f"⚠️ Комментарий: <b>Д-{p.delivery_id}</b>"
        )
        await call.message.answer(text, reply_markup=kb.admin_confirm_delivery(p.delivery_id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_pay_ok_"))
async def pay_ok(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        order = await orders_service.confirm_payment(session, order_id, call.from_user.id)

    await call.message.edit_text(f"✅ Оплата #{order_id} подтверждена.")
    if order:
        async with async_session() as s2:
            cr = await s2.execute(select(Client).where(Client.id == order.client_id))
            client = cr.scalar_one_or_none()

        if client and client.tg_id:
            try: await bot_client.send_message(client.tg_id, f"✅ <b>Оплата заказа #{order.id} подтверждена!</b>")
            except Exception: pass

    await log_action(f"Оплата #{order_id} подтверждена")
    await call.answer()

@router.callback_query(F.data.startswith("admin_pay_no_"))
async def pay_no(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await payments_service.mark_payment_rejected(session, order_id, call.from_user.id)
        await orders_service.cancel_order(session, order_id, reason="payment_rejected", cancelled_by="admin", refund=False)
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        client = None
        if order:
            cr = await session.execute(select(Client).where(Client.id == order.client_id))
            client = cr.scalar_one_or_none()

    await call.message.edit_text(f"❌ Платёж #{order_id} отклонён.")
    if client and client.tg_id:
        try: await bot_client.send_message(client.tg_id, f"❌ <b>Платёж по заказу #{order_id} не подтверждён.</b>\n\nПроверьте комментарий.\nПоддержка: {config.SUPPORT_TG}")
        except Exception: pass

    await log_action(f"Платёж #{order_id} отклонён")
    await call.answer()

@router.callback_query(F.data.startswith("admin_pay_msg_"))
async def pay_msg(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        if order:
            await state.update_data(msg_target_type="client", msg_target_id=order.client_id)
            await state.set_state(AdminFSM.reply_to_client)
            await call.message.answer("✉️ Введите сообщение для клиента:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.callback_query(F.data.startswith("admin_del_pay_ok_"))
async def del_pay_ok(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        d = await payments_service.confirm_delivery_payment(session, delivery_id, call.from_user.id)
        shop = None
        if d:
            s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
            shop = s_r.scalar_one_or_none()

    await call.message.edit_text(f"✅ Оплата #Д-{delivery_id} подтверждена.")
    if shop and shop.tg_id:
        try: await bot_shop.send_message(shop.tg_id, f"✅ <b>Оплата доставки #Д-{delivery_id} подтверждена!</b>\n\nИщем курьера 🚴")
        except Exception: pass

    await log_action(f"Оплата #Д-{delivery_id} подтверждена")
    await call.answer()

@router.callback_query(F.data.startswith("admin_del_pay_no_"))
async def del_pay_no(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        d = await payments_service.reject_delivery_payment(session, delivery_id, call.from_user.id)
        shop = None
        if d:
            s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
            shop = s_r.scalar_one_or_none()

    await call.message.edit_text(f"❌ Платёж #Д-{delivery_id} отклонён.")
    if shop and shop.tg_id:
        try: await bot_shop.send_message(shop.tg_id, f"❌ Платёж доставки #Д-{delivery_id} не подтверждён.")
        except Exception: pass
    await call.answer()

@router.callback_query(F.data == "admin_pay_outgoing")
async def pay_outgoing(call: CallbackQuery):
    async with async_session() as session:
        payouts = await payments_service.get_pending_payouts(session)

    if not payouts:
        await call.message.edit_text("✅ Нет ожидающих выплат.", reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payouts[:10]:
        role_map = {"courier": "🚴", "shop": "🏪", "client": "👤"}
        method_map = {"card": "💳 Карта", "sbp": "📱 СБП"}
        text = (
            f"💸 <b>Выплата #{p.id}</b>\n\n{role_map.get(p.user_type, '•')} ID {p.user_id}\n"
            f"💰 {helpers.money(p.amount)}\n{method_map.get(p.method, '')}: {helpers.escape(p.target or '—')}\n"
            f"🏦 {helpers.escape(p.bank_name or '—')}\n👤 {helpers.escape(p.card_holder or '—')}"
        )
        if p.commission > 0:
            text += f"\n📉 Комиссия: {helpers.money(p.commission)}\n💵 К выплате: {helpers.money(p.amount_to_pay)}"
        await call.message.answer(text, reply_markup=kb.admin_payout_actions(p.id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_payout_transfer_"))
async def payout_transfer(call: CallbackQuery):
    payout_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await payments_service.mark_payout_transferred(session, payout_id, call.from_user.id)
    await log_action(f"Выплата #{payout_id} отправлена")
    await call.message.edit_text(f"💳 Выплата #{payout_id} отмечена как отправленная.")
    await call.answer()

@router.callback_query(F.data.startswith("admin_payout_ok_"))
async def payout_ok(call: CallbackQuery):
    payout_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        p = await payments_service.mark_payout_done(session, payout_id, call.from_user.id)

        if p:
            if p.user_type == "courier":
                r = await session.execute(select(Courier).where(Courier.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try: await bot_courier.send_message(user.tg_id, f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!")
                    except Exception: pass
            elif p.user_type == "shop":
                r = await session.execute(select(Shop).where(Shop.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try: await bot_shop.send_message(user.tg_id, f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!")
                    except Exception: pass
            elif p.user_type == "client":
                r = await session.execute(select(Client).where(Client.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try: await bot_client.send_message(user.tg_id, f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!")
                    except Exception: pass

    await log_action(f"Выплата #{payout_id} подтверждена")
    await call.message.edit_text(f"✅ Выплата #{payout_id} подтверждена.")
    await call.answer()

@router.callback_query(F.data.startswith("admin_payout_no_"))
async def payout_no(call: CallbackQuery):
    payout_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        p = await payments_service.mark_payout_rejected(session, payout_id, call.from_user.id)
        if p:
            if p.user_type == "courier":
                r = await session.execute(select(Courier).where(Courier.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try: await bot_courier.send_message(user.tg_id, f"❌ Выплата {helpers.money(p.amount)} отклонена. Средства возвращены на баланс.")
                    except Exception: pass
            elif p.user_type == "shop":
                r = await session.execute(select(Shop).where(Shop.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try: await bot_shop.send_message(user.tg_id, f"❌ Выплата {helpers.money(p.amount)} отклонена. Средства возвращены на баланс.")
                    except Exception: pass

    await log_action(f"Выплата #{payout_id} отклонена")
    await call.message.edit_text(f"❌ Выплата #{payout_id} отклонена.")
    await call.answer()

# ═══════════════════════════════════════════
#   КОНТРОЛЬ ДОСТАВКИ (ФИНАНСОВАЯ РАСКЛАДКА)
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_delivery_control")
async def admin_delivery_control(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(Order).where(
                Order.status == "wait",
                Order.payment_status == "confirmed",
                Order.courier_id.is_(None),
            )
        )
        orders = r.scalars().all()

    if not orders:
        await call.message.edit_text("✅ Нет зависших заказов.", reply_markup=kb.admin_back())
        await call.answer()
        return

    stuck = []
    for o in orders:
        if o.wait_started_at:
            elapsed = int((helpers.now_moscow() - o.wait_started_at).total_seconds() / 60)
            if elapsed > 15:
                stuck.append((o, elapsed))

    if not stuck:
        await call.message.edit_text("✅ Все заказы в пределах нормы (ждут курьера до 15 мин).", reply_markup=kb.admin_back())
        await call.answer()
        return

    for o, wait_min in stuck[:10]:
        fee = int(float(o.courier_fee or 0) + float(o.boost_amount or 0))
        boost_str = f" 🔥 +{int(o.boost_amount)}₽" if o.boost_amount > 0 else ""
        text = f"⏰ <b>Заказ #{o.id} на грани срыва!</b>\n\n🕒 Ждёт: {wait_min} мин\n💰 Курьеру: {fee} ₽{boost_str}\n📍 {helpers.escape(o.address)}"
        await call.message.answer(text, reply_markup=kb.admin_delivery_control(o.id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_delivery_control_details_"))
async def admin_delivery_control_details(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        if not order: return
        
        shop_r = await session.execute(select(Shop).where(Shop.id == order.shop_id))
        shop = shop_r.scalar_one_or_none()
        
        courier = None
        if order.courier_id:
            cr = await session.execute(select(Courier).where(Courier.id == order.courier_id))
            courier = cr.scalar_one_or_none()
            
        items_r = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
        items = items_r.scalars().all()

    items_text = ""
    shop_sum = Decimal("0.00")
    markup_sum = Decimal("0.00")
    
    for it in items:
        items_text += f"  • {helpers.escape(it.title)} × {it.quantity} = {helpers.money(it.total)}\n"
        shop_sum += Decimal(str(it.shop_price)) * it.quantity
        markup_sum += Decimal(str(it.markup)) * it.quantity

    delivery_fee = Decimal(str(order.delivery_price or 0))
    courier_fee = Decimal(str(order.courier_fee or 0))
    boost = Decimal(str(order.boost_amount or 0))
    discount = Decimal(str(order.discount or 0))
    
    delivery_commission = delivery_fee - courier_fee
    platform_net = markup_sum + delivery_commission - discount

    text = (
        f"🔍 <b>ДЕТАЛИ ЗАКАЗА #{order.id}</b>\n"
        f"Статус: {order.status} | Оплата: {order.payment_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌷 <b>СОСТАВ:</b>\n{items_text}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 <b>Магазин:</b> {helpers.escape(shop.name)} ({shop.phone})\n"
        f"📍 <b>Откуда:</b> {helpers.escape(shop.address)}\n"
        f"🏠 <b>Куда:</b> {helpers.escape(order.address)}\n"
        f"👤 <b>Получатель:</b> {helpers.escape(order.client_name)}, {order.client_phone}\n"
        f"📅 <b>Дата:</b> {helpers.format_date(order.delivery_date)}\n"
        f"🕒 <b>Время доставки:</b> {order.delivery_slot}\n"
    )
    if order.comment:
        text += f"💬 <b>Коммент:</b> {helpers.escape(order.comment)}\n"
    
    if courier:
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n🚴 <b>Курьер:</b> {helpers.escape(courier.name)} ({courier.phone})\n"
    else:
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n🚴 <b>Курьер:</b> не назначен\n"

    text += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>ФИНАНСОВАЯ РАСКЛАДКА:</b>\n\n"
        f"👤 <b>Клиент платит:</b> {helpers.money(order.total_price)}\n"
        f"   • За букеты: {helpers.money(order.items_total)}\n"
        f"   • За доставку: {helpers.money(delivery_fee)}\n"
    )
    if discount > 0:
        text += f"   • Скидка: -{helpers.money(discount)}\n"
    
    text += (
        f"\n🏪 <b>Магазин получает:</b> {helpers.money(shop_sum)}\n"
        f"🚴 <b>Курьер получает:</b> {helpers.money(courier_fee)}"
    )
    if boost > 0:
        text += f" + {helpers.money(boost)} (буст)"
    
    text += (
        f"\n\n💰 <b>ПЛАТФОРМА (ВЫ):</b>\n"
        f"   • Наценка на товары: +{helpers.money(markup_sum)}\n"
        f"   • Комиссия с доставки: +{helpers.money(delivery_commission)}\n"
    )
    if discount > 0:
        text += f"   • Оплата скидки: -{helpers.money(discount)}\n"
    if boost > 0:
        text += f"   • Оплата буста: -{helpers.money(boost)}\n"
    
    text += (
        f"   ━━━━━━━━━━━━━━━━━━━━━━\n"
        f"   <b>ЧИСТАЯ ПРИБЫЛЬ: {helpers.money(platform_net - boost)}</b>\n"
    )
    
    await call.message.edit_text(text, reply_markup=kb.admin_delivery_control(order_id, show_details=True))
    await call.answer()

@router.callback_query(F.data.startswith("admin_boost_") & ~F.data.startswith("admin_boost_set_") & ~F.data.startswith("admin_boost_custom"))
async def admin_boost(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    await call.message.edit_text("💰 <b>На сколько поднять ставку?</b>", reply_markup=kb.admin_boost_amount(order_id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_boost_set_"))
async def admin_boost_set(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[-2])
    amount = float(parts[-1])

    async with async_session() as session:
        await session.execute(update(Order).where(Order.id == order_id).values(boost_amount=Order.boost_amount + amount))
        await session.commit()

    await log_action(f"Boost +{amount} ₽ на #{order_id}")
    await call.message.edit_text(f"✅ Ставка поднята на {amount} ₽.")
    await call.answer()

@router.callback_query(F.data.startswith("admin_boost_custom_"))
async def admin_boost_custom(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[-1])
    await state.update_data(boost_order_id=order_id)
    await state.set_state(AdminFSM.boost_custom)
    await call.message.edit_text("💰 Введите сумму прибавки:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.boost_custom)
async def admin_boost_custom_save(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Введите число > 0.")
        return

    data = await state.get_data()
    order_id = data.get("boost_order_id")

    async with async_session() as session:
        await session.execute(update(Order).where(Order.id == order_id).values(boost_amount=Order.boost_amount + amount))
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Ставка поднята на {amount} ₽.", reply_markup=kb.admin_main())

@router.callback_query(F.data.startswith("admin_cancel_order_"))
async def admin_cancel_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        await orders_service.cancel_order(session, order_id, reason="admin_cancelled", cancelled_by="admin", refund=True)
    await log_action(f"Заказ #{order_id} отменён админом")
    await call.answer("❌ Отменён", show_alert=True)
    await admin_delivery_control(call)

# ═══════════════════════════════════════════
#   KPI / SLA
# ═══════════════════════════════════════════
@router.callback_query(F.data.startswith("admin_kpi_"))
async def admin_kpi(call: CallbackQuery):
    period = call.data.replace("admin_kpi_", "")
    now = helpers.now_moscow()
    if period == "today": since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week": since = now - timedelta(days=7)
    else: since = now - timedelta(days=30)

    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.delivered_at >= since, Order.status == "done"))
        orders = r.scalars().all()

    if not orders:
        await call.message.edit_text("📊 Нет данных за этот период.", reply_markup=kb.admin_kpi_menu())
        await call.answer()
        return

    on_time = 0
    delay_5_10 = 0
    delay_10_15 = 0
    delay_15_30 = 0
    delay_30 = 0
    urgent_count = 0

    for o in orders:
        if not o.delivery_slot: continue
        try:
            end_time_str = o.delivery_slot.split("-")[1]
            h, m = map(int, end_time_str.split(":"))
            slot_end = o.delivered_at.replace(hour=h, minute=m, second=0, microsecond=0)
            
            if o.created_at and (slot_end - o.created_at).total_seconds() < 7200:
                urgent_count += 1

            diff_min = (o.delivered_at - slot_end).total_seconds() / 60
            
            if diff_min <= 5: on_time += 1
            elif diff_min <= 10: delay_5_10 += 1
            elif diff_min <= 15: delay_10_15 += 1
            elif diff_min <= 30: delay_15_30 += 1
            else: delay_30 += 1
        except Exception: pass

    total = len(orders)
    percent = (on_time / total * 100) if total > 0 else 0

    text = (
        f"📈 <b>KPI / SLA Доставки</b>\n\n"
        f"Физически доставлено: {total}\n"
        f"Вовремя: {on_time} ({percent:.1f}%)\n\n"
        f"<b>Разбивка задержек:</b>\n"
        f"🟢 до 5 мин: {on_time}\n"
        f"🟡 5–10 мин: {delay_5_10}\n"
        f"🟠 10–15 мин: {delay_10_15}\n"
        f"🔴 15–30 мин: {delay_15_30}\n"
        f"🚨 >30 мин: {delay_30}\n\n"
        f"⚡ Срочных заказов: {urgent_count}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_kpi_menu())
    await call.answer()
    # ═══════════════════════════════════════════
#   ПРОМОКОДЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_promos")
async def admin_promos(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "settings"):
        await call.answer("Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(Promo).order_by(Promo.id.desc()).limit(20))
        promos = result.scalars().all()

    if not promos:
        text = "🎁 Промокодов нет."
    else:
        text = f"🎁 <b>Промокоды ({len(promos)})</b>\n\n"
        for p in promos:
            d = f"{int(p.discount_value)}%" if p.discount_type == "percent" else helpers.money(p.discount_value)
            status = "✅" if p.is_active else "⏸"
            text += f"{status} <code>{p.code}</code> — {d} — {p.used_count}/{p.max_uses or '∞'}\n"

    promos_data = [{"id": p.id, "code": p.code, "discount_text": f"{int(p.discount_value)}%" if p.discount_type == "percent" else helpers.money(p.discount_value), "is_active": p.is_active} for p in promos[:8]]
    await call.message.edit_text(text, reply_markup=kb.admin_promo_list(promos_data))
    await call.answer()

@router.callback_query(F.data == "admin_promo_create")
async def promo_create_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.promo_code)
    await call.message.edit_text("🎁 <b>Создание промокода</b>\n\nШаг 1/4: Введите код:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.promo_code)
async def promo_set_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code.isalnum():
        await message.answer("❌ Только буквы и цифры.")
        return

    async with async_session() as session:
        r = await session.execute(select(Promo).where(Promo.code == code))
        if r.scalar_one_or_none():
            await message.answer("❌ Такой код уже есть.")
            return

    await state.update_data(promo_code=code)
    await state.set_state(AdminFSM.promo_type)
    await message.answer("🎁 Шаг 2/4: Тип скидки:", reply_markup=kb.admin_promo_type())

@router.callback_query(F.data.startswith("promo_type_"), AdminFSM.promo_type)
async def promo_set_type(call: CallbackQuery, state: FSMContext):
    d_type = call.data.replace("promo_type_", "")
    await state.update_data(discount_type=d_type)
    await state.set_state(AdminFSM.promo_value)
    hint = "Введите процент (1–100):" if d_type == "percent" else "Введите сумму в рублях:"
    await call.message.edit_text(f"🎁 Шаг 3/4: {hint}", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.promo_value)
async def promo_set_value(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(",", ".").strip())
        if value <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Введите число > 0.")
        return

    await state.update_data(discount_value=value)
    await state.set_state(AdminFSM.promo_uses)
    await message.answer("🎁 Шаг 4/4: Лимит использований\n\nЧисло или 0 (безлимит):", reply_markup=kb.admin_cancel())

@router.message(AdminFSM.promo_uses)
async def promo_set_uses(message: Message, state: FSMContext):
    try: max_uses = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    data = await state.get_data()
    async with async_session() as session:
        session.add(Promo(code=data["promo_code"], discount_type=data["discount_type"], discount_value=data["discount_value"], max_uses=max_uses, is_active=True))
        await session.commit()

    await log_action(f"Промокод {data['promo_code']} создан")
    await state.clear()
    d = f"{int(data['discount_value'])}%" if data["discount_type"] == "percent" else helpers.money(data["discount_value"])
    await message.answer(f"✅ Промокод создан!\n🎁 <code>{data['promo_code']}</code> — {d}", reply_markup=kb.admin_main())

@router.callback_query(F.data.startswith("admin_promo_view_"))
async def promo_view(call: CallbackQuery):
    promo_id = int(call.data.split("_")[-1])
    await call.message.edit_text(f"🎁 Промокод #{promo_id}", reply_markup=kb.admin_promo_view(promo_id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_promo_del_"))
async def promo_delete(call: CallbackQuery):
    promo_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Promo).where(Promo.id == promo_id))
        promo = r.scalar_one_or_none()
        if promo:
            promo.is_active = False
            await session.commit()
            await log_action(f"Промокод {promo.code} отключён")
    await call.answer("🗑 Отключён", show_alert=True)
    await admin_promos(call)

# ═══════════════════════════════════════════
#   ЖАЛОБЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_complaints")
async def admin_complaints(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Complaint).where(Complaint.status == "pending").order_by(Complaint.id.desc()).limit(20))
        complaints = r.scalars().all()

    if not complaints:
        await call.message.edit_text("✅ Жалоб нет.", reply_markup=kb.admin_back())
        await call.answer()
        return

    items = [{"id": c.id, "type": c.target_type} for c in complaints]
    await call.message.edit_text(f"🆘 <b>Жалобы ({len(items)})</b>", reply_markup=kb.admin_complaints_list(items))
    await call.answer()

@router.callback_query(F.data.startswith("admin_complaint_view_"))
async def admin_complaint_view(call: CallbackQuery):
    complaint_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
        c = r.scalar_one_or_none()
        if not c: return

    text = f"🆘 <b>Жалоба #{c.id}</b>\n\n🎯 На: {c.target_type} #{c.target_id}\n📦 Заказ: #{c.order_id}\n\n📝 {helpers.escape(c.reason)}"
    await call.message.edit_text(text, reply_markup=kb.admin_complaint_card(complaint_id))
    await call.answer()

@router.callback_query(F.data.startswith("admin_comp_refund_"))
async def admin_comp_refund(call: CallbackQuery):
    complaint_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
        c = r.scalar_one_or_none()
        if c:
            o_r = await session.execute(select(Order).where(Order.id == c.order_id))
            order = o_r.scalar_one_or_none()
            if order:
                await payments_service.refund_to_balance(session, order.client_id, order.total_price, order.id)
            c.status = "resolved"
            c.admin_id = call.from_user.id
            await session.commit()

    await log_action(f"Жалоба #{complaint_id} одобрена")
    await call.answer("✅ Возврат сделан", show_alert=True)
    await admin_complaints(call)

@router.callback_query(F.data.startswith("admin_comp_reject_"))
async def admin_comp_reject(call: CallbackQuery):
    complaint_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
        c = r.scalar_one_or_none()
        if c:
            c.status = "rejected"
            c.admin_id = call.from_user.id
            await session.commit()
    await log_action(f"Жалоба #{complaint_id} отклонена")
    await call.answer("❌ Отклонено", show_alert=True)
    await admin_complaints(call)

# ═══════════════════════════════════════════
#   РАССЫЛКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery):
    await call.message.edit_text("📢 <b>Рассылка</b>\n\nКому?", reply_markup=kb.admin_broadcast_menu())
    await call.answer()

@router.callback_query(F.data.startswith("admin_bc_") & ~F.data.startswith("admin_bc_send"))
async def admin_bc_start(call: CallbackQuery, state: FSMContext):
    target = call.data.replace("admin_bc_", "")
    await state.update_data(bc_target=target)
    await state.set_state(AdminFSM.broadcast_text)
    await call.message.edit_text("📝 Введите текст:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.broadcast_text)
async def admin_bc_text(message: Message, state: FSMContext):
    await state.update_data(bc_text=message.text)
    data = await state.get_data()
    target_map = {"clients": "👥 Клиентам", "couriers": "🚴 Курьерам", "shops": "🏪 Магазинам"}
    target = target_map.get(data.get("bc_target"), "?")

    await state.set_state(AdminFSM.broadcast_confirm)
    await message.answer(f"👁 <b>Проверьте</b>\n\nКому: {target}\n\n{data['bc_text']}", reply_markup=kb.admin_broadcast_confirm())

@router.callback_query(F.data == "admin_bc_send", AdminFSM.broadcast_confirm)
async def admin_bc_send(call: CallbackQuery, state: FSMContext):
    import asyncio
    data = await state.get_data()
    target, text = data.get("bc_target"), data.get("bc_text")

    ids, bot = [], None
    async with async_session() as session:
        if target == "clients":
            r = await session.execute(select(Client).where(Client.tg_id.isnot(None), Client.is_blocked == False))
            ids = [u.tg_id for u in r.scalars().all()]
            bot = bot_client
        elif target == "couriers":
            r = await session.execute(select(Courier).where(Courier.tg_id.isnot(None), Courier.is_blocked == False))
            ids = [u.tg_id for u in r.scalars().all()]
            bot = bot_courier
        elif target == "shops":
            r = await session.execute(select(Shop).where(Shop.tg_id.isnot(None)))
            ids = [u.tg_id for u in r.scalars().all()]
            bot = bot_shop

    sent, failed = 0, 0
    for uid in ids:
        try:
            await bot.send_message(uid, f"📢 <b>Сообщение от Flowers Express:</b>\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05) # ЗАЩИТА ОТ СПАМА (П. 96)
        except Exception: 
            failed += 1

    await log_action(f"Рассылка ({target}): {sent}")
    await state.clear()
    await call.message.edit_text(f"✅ Рассылка завершена.\n📤 {sent}\n❌ {failed}", reply_markup=kb.admin_main())
    await call.answer()

# ═══════════════════════════════════════════
#   АНАЛИТИКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_analytics")
async def admin_analytics(call: CallbackQuery):
    await call.message.edit_text("📊 <b>Аналитика</b>\n\nПериод:", reply_markup=kb.admin_analytics_menu())
    await call.answer()

@router.callback_query(F.data.startswith("admin_analytics_") & ~F.data.startswith("admin_analytics_menu"))
async def admin_analytics_period(call: CallbackQuery):
    period = call.data.replace("admin_analytics_", "")
    now = helpers.now_moscow()
    if period == "today": since, label = now.replace(hour=0, minute=0, second=0, microsecond=0), "Сегодня"
    elif period == "week": since, label = now - timedelta(days=7), "За неделю"
    elif period == "month": since, label = now - timedelta(days=30), "За месяц"
    else: since, label = datetime(2020, 1, 1), "За всё время"

    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.created_at >= since))
        orders = r.scalars().all()

    total = len(orders)
    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    turnover = sum(float(o.total_price) for o in orders if o.status == "done")
    platform = sum(float(o.platform_income) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Аналитика — {label}</b>\n\n📦 Заказов: {total}\n✅ Доставлено: {done}\n❌ Отменено: {cancel}\n\n"
        f"💰 Оборот: {helpers.money(turnover)}\n📈 Доход: {helpers.money(platform)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_analytics_menu())
    await call.answer()

@router.callback_query(F.data == "admin_top_shops")
async def admin_top_shops(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.status == "active").order_by(Shop.total_orders.desc()).limit(10))
        shops = r.scalars().all()

    text = "🏆 <b>Топ-10 магазинов:</b>\n\n"
    for i, s in enumerate(shops, start=1):
        text += f"{i}. {helpers.escape(s.name)} — {s.total_orders} — ⭐ {float(s.rating or 0):.1f}\n"
    if not shops: text = "🏆 Нет данных."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()

@router.callback_query(F.data == "admin_top_couriers")
async def admin_top_couriers(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.status == "active").order_by(Courier.total_orders.desc()).limit(10))
        couriers = r.scalars().all()

    text = "🏆 <b>Топ-10 курьеров:</b>\n\n"
    for i, c in enumerate(couriers, start=1):
        text += f"{i}. {helpers.escape(c.name)} — {c.total_orders} — ⭐ {float(c.rating or 0):.1f}\n"
    if not couriers: text = "🏆 Нет данных."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()

@router.callback_query(F.data == "admin_shifts_dashboard")
async def admin_shifts_dashboard(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.courier_state == "on"))
        on_shift = r.scalars().all()

    if not on_shift:
        await call.message.edit_text("👥 Никого нет на смене.", reply_markup=kb.admin_back("admin_analytics"))
        await call.answer()
        return

    text = f"👥 <b>На смене ({len(on_shift)})</b>\n\n"
    for c in on_shift:
        lat = f"{float(c.lat):.4f}" if c.lat else "—"
        lon = f"{float(c.lon):.4f}" if c.lon else "—"
        loc_time = helpers.format_time(c.loc_time) if c.loc_time else "—"
        text += f"• {helpers.escape(c.name)} — 📍 {lat}, {lon} (обновлено {loc_time})\n"

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()

# ═══════════════════════════════════════════
#   НАСТРОЙКИ, МУЛЬТИАДМИН, ЛОГИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_settings")
async def admin_settings(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "settings"):
        await call.answer("Нет доступа", show_alert=True)
        return

    text = (
        f"⚙️ <b>Настройки системы</b>\n\n💸 Зоны доставки: 350–600 ₽\n"
        f"💰 Мин. вывод курьера: {config.COURIER_MIN_WITHDRAW} ₽\n"
        f"🎁 Бонус за 10: {config.BONUS_PER_10_ORDERS} ₽\n"
        f"🕒 Часы: {config.WORK_HOURS}\n🏙 Город: {config.CITY}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_settings_menu())
    await call.answer()

@router.callback_query(F.data == "admin_multicity")
async def multicity_stub(call: CallbackQuery):
    await call.message.edit_text("🌍 <b>Мультигород</b>\n\n🚧 В разработке.", reply_markup=kb.admin_back("admin_settings"))
    await call.answer()

@router.callback_query(F.data == "admin_admins")
async def admin_admins(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "admins"):
        await call.answer("Нет доступа", show_alert=True)
        return

    await call.message.edit_text(f"🔑 <b>Управление админами</b>\n\n👑 Главный админ: <code>{config.ADMIN_ID}</code>", reply_markup=kb.admin_admins_menu())
    await call.answer()

@router.callback_query(F.data == "admin_add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.add_admin_id)
    await call.message.edit_text("➕ <b>Новый админ</b>\n\nВведите Telegram ID:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.add_admin_id)
async def add_admin_set_id(message: Message, state: FSMContext):
    try: tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    if tg_id == config.ADMIN_ID:
        await message.answer("❌ Это главный админ.")
        return

    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.tg_id == tg_id))
        if r.scalar_one_or_none():
            await message.answer("❌ Уже админ.")
            return

    await state.update_data(new_admin_id=tg_id)
    await state.set_state(AdminFSM.add_admin_name)
    await message.answer("📝 Введите имя (или /skip):", reply_markup=kb.admin_cancel())

@router.message(AdminFSM.add_admin_name)
async def add_admin_set_name(message: Message, state: FSMContext):
    txt = message.text.strip()
    name = None if txt.startswith("/skip") else txt
    async with async_session() as session:
        admin = Admin(tg_id=(await state.get_data()).get("new_admin_id"), name=name, added_by=message.from_user.id, permissions="{}", is_active=True)
        session.add(admin)
        await session.commit()

    await state.clear()
    await message.answer("✅ Админ добавлен. Настройте права.", reply_markup=kb.admin_main())

@router.callback_query(F.data == "admin_list_admins")
async def list_admins(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.is_active == True))
        admins = r.scalars().all()

    if not admins: text = "📋 Дополнительных админов нет."
    else:
        text = f"📋 <b>Админы ({len(admins)})</b>\n\n"
        for a in admins: text += f"• {helpers.escape(a.name or '—')} — <code>{a.tg_id}</code>\n"

    rows = [[kb.btn("👑 Главный", "noop")]]
    for a in admins: rows.append([kb.btn(f"🔑 {a.name or a.tg_id}", f"admin_admin_view_{a.id}")])
    rows.append([kb.btn("🔙 Назад", "admin_admins")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()

@router.callback_query(F.data.startswith("admin_admin_view_"))
async def admin_admin_view(call: CallbackQuery):
    admin_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.id == admin_id))
        admin = r.scalar_one_or_none()
        if not admin: return

    active = list(helpers.parse_permissions(admin.permissions).keys())
    text = f"🔑 <b>{helpers.escape(admin.name or str(admin.tg_id))}</b>\n\nID: <code>{admin.tg_id}</code>\n\nВыберите права:"
    await call.message.edit_text(text, reply_markup=kb.admin_permissions_menu(admin_id, active))
    await call.answer()

@router.callback_query(F.data.startswith("perm_toggle_"))
async def perm_toggle(call: CallbackQuery):
    parts = call.data.split("_")
    admin_id, key = int(parts[-2]), parts[-1]

    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.id == admin_id))
        admin = r.scalar_one_or_none()
        if not admin: return

        perms = helpers.parse_permissions(admin.permissions)
        perms[key] = not perms.get(key, False)
        admin.permissions = helpers.permissions_to_str(perms)
        await session.commit()
        active = list(k for k, v in perms.items() if v)

    try: await call.message.edit_reply_markup(reply_markup=kb.admin_permissions_menu(admin_id, active))
    except Exception: pass
    await call.answer()

@router.callback_query(F.data.startswith("perm_save_"))
async def perm_save(call: CallbackQuery):
    await call.answer("✅ Сохранено", show_alert=True)

@router.callback_query(F.data.startswith("admin_del_") & ~F.data.startswith("admin_del_pay_") & ~F.data.startswith("admin_del_view_") & ~F.data.startswith("admin_del_cancel_") & ~F.data.startswith("admin_deliveries"))
async def admin_del_admin(call: CallbackQuery):
    admin_id = int(call.data.split("_")[-1])
    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.id == admin_id))
        admin = r.scalar_one_or_none()
        if admin:
            admin.is_active = False
            await session.commit()

    await log_action(f"Админ #{admin_id} удалён")
    await call.answer("🗑 Удалён", show_alert=True)
    await admin_admins(call)

@router.callback_query(F.data == "admin_access")
async def admin_access(call: CallbackQuery):
    await call.message.edit_text("🔒 <b>Управление доступом</b>\n\nЗаблокируйте или разблокируйте по Telegram ID.", reply_markup=kb.admin_access_menu())
    await call.answer()

@router.callback_query(F.data == "admin_block_by_id")
async def block_by_id_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.block_by_id)
    await call.message.edit_text("🚫 Введите Telegram ID:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.block_by_id)
async def block_by_id_apply(message: Message, state: FSMContext):
    try: tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    found = False
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.tg_id == tg_id))
        shop = r.scalar_one_or_none()
        if shop: shop.status = "blocked"; found = True

        r = await session.execute(select(Courier).where(Courier.tg_id == tg_id))
        courier = r.scalar_one_or_none()
        if courier: courier.is_blocked = True; courier.status = "blocked"; found = True

        r = await session.execute(select(Client).where(Client.tg_id == tg_id))
        client = r.scalar_one_or_none()
        if client: client.is_blocked = True; found = True

        await session.commit()

    if found:
        await state.clear()
        await message.answer(f"🚫 Пользователь {tg_id} заблокирован.", reply_markup=kb.admin_main())
        await log_action(f"Заблокирован {tg_id}")
    else:
        await message.answer(f"❌ Пользователь {tg_id} не найден.\n\nПроверьте, что ID правильный (только цифры).")
        await state.clear()

@router.callback_query(F.data == "admin_unblock_by_id")
async def unblock_by_id_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.unblock_by_id)
    await call.message.edit_text("✅ Введите Telegram ID:", reply_markup=kb.admin_cancel())
    await call.answer()

@router.message(AdminFSM.unblock_by_id)
async def unblock_by_id_apply(message: Message, state: FSMContext):
    try: tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    found = False
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.tg_id == tg_id))
        shop = r.scalar_one_or_none()
        if shop: shop.status = "active"; found = True

        r = await session.execute(select(Courier).where(Courier.tg_id == tg_id))
        courier = r.scalar_one_or_none()
        if courier: courier.is_blocked = False; courier.status = "active"; found = True

        r = await session.execute(select(Client).where(Client.tg_id == tg_id))
        client = r.scalar_one_or_none()
        if client: client.is_blocked = False; found = True

        await session.commit()

    if found:
        await state.clear()
        await message.answer(f"✅ Пользователь {tg_id} разблокирован.", reply_markup=kb.admin_main())
        await log_action(f"Разблокирован {tg_id}")
    else:
        await message.answer(f"❌ Пользователь {tg_id} не найден.")

@router.callback_query(F.data == "admin_logs")
async def admin_logs(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Log).order_by(Log.id.desc()).limit(30))
        logs = r.scalars().all()

    if not logs: text = "📜 Логи пусты."
    else:
        text = "📜 <b>Последние 30 записей:</b>\n\n"
        for lg in logs: text += f"• {helpers.format_dt(lg.created_at)} — {helpers.escape(lg.text)}\n"

    await call.message.edit_text(text, reply_markup=kb.admin_logs_menu())
    await call.answer()

@router.callback_query(F.data == "admin_logs_clear")
async def admin_logs_clear(call: CallbackQuery):
    async with async_session() as session:
        await session.execute(sa_delete(Log))
        await session.commit()
    await call.answer("🗑 Очищено", show_alert=True)
    await admin_logs(call)

# ═══════════════════════════════════════════
#   ОТПРАВКА СООБЩЕНИЯ (ОТ АДМИНА)
# ═══════════════════════════════════════════
@router.message(AdminFSM.reply_to_client)
async def admin_send_message(message: Message, state: FSMContext):
    data = await state.get_data()
    ttype = data.get("msg_target_type")
    tid = data.get("msg_target_id")
    text = message.text.strip()

    target_id, bot = None, None

    async with async_session() as session:
        if ttype == "shop":
            r = await session.execute(select(Shop).where(Shop.id == tid))
            obj = r.scalar_one_or_none()
            if obj: target_id, bot = obj.tg_id, bot_shop
        elif ttype == "courier":
            r = await session.execute(select(Courier).where(Courier.id == tid))
            obj = r.scalar_one_or_none()
            if obj: target_id, bot = obj.tg_id, bot_courier
        elif ttype == "client":
            r = await session.execute(select(Client).where(Client.id == tid))
            obj = r.scalar_one_or_none()
            if obj: target_id, bot = obj.tg_id, bot_client

    if target_id and bot:
        try:
            await bot.send_message(target_id, f"✉️ <b>Сообщение от админа:</b>\n\n{text}")
            await message.answer("✅ Отправлено.", reply_markup=kb.admin_main())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=kb.admin_main())
    else:
        await message.answer("❌ Получатель не найден.", reply_markup=kb.admin_main())

    await state.clear()
