# -*- coding: utf-8 -*-
"""
SLIPI — бот админа (полная версия)
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
    Admin, BotUpdate,
)
from services import orders as orders_service
from services import payments as payments_service
from utils import helpers

from bots import bot_client, bot_shop, bot_courier, bot_admin

router = Router(name="admin")


# ═══════════════════════════════════════════
#   ПРАВА АДМИНОВ
# ═══════════════════════════════════════════
async def get_admin_permissions(session, tg_id: int):
    """None = полный доступ. False = не админ. Dict = права."""
    if tg_id == config.ADMIN_ID:
        return None

    r = await session.execute(select(Admin).where(Admin.tg_id == tg_id, Admin.is_active == True))
    admin = r.scalar_one_or_none()
    if not admin:
        return False

    return helpers.parse_permissions(admin.permissions)


def has_perm(permissions, key: str) -> bool:
    if permissions is None:
        return True
    if permissions is False:
        return False
    return permissions.get(key, False)


async def log_action(text: str):
    try:
        async with async_session() as session:
            session.add(Log(text=text))
            await session.commit()
    except Exception:
        pass


# ═══════════════════════════════════════════
#   /start
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

        shops_count = len((await session.execute(
            select(Shop).where(Shop.status == "pending")
        )).scalars().all())
        couriers_count = len((await session.execute(
            select(Courier).where(Courier.status == "pending")
        )).scalars().all())
        payments_count = len((await session.execute(
            select(Payment).where(Payment.status == "pending")
        )).scalars().all())
        del_payments_count = len((await session.execute(
            select(DeliveryPayment).where(DeliveryPayment.status == "pending")
        )).scalars().all())
        payouts_count = len((await session.execute(
            select(Payout).where(Payout.status == "pending")
        )).scalars().all())
        in_work = await payments_service.get_orders_in_work(session)

    total_pending = shops_count + couriers_count

    text = (
        f"👑 <b>Админ-панель {config.SERVICE_NAME}</b>\n\n"
        f"📨 Заявок: {total_pending}\n"
        f"🚗 В работе: {in_work}\n"
        f"💳 Ожидают оплаты: {payments_count}\n"
        f"🚚 Доставки: {del_payments_count}\n"
        f"💸 Выплаты: {payouts_count}\n"
        f"💰 Доход: {helpers.money(summary['platform_income'])}"
    )

    markup = kb.admin_main(perms)
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
        except Exception:
            await message.answer(text, reply_markup=markup)
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
        await call.message.edit_text("✅ Нет новых заявок магазинов.",
                                     reply_markup=kb.admin_requests_menu())
        await call.answer()
        return

    for s in shops[:10]:
        text = (
            f"🏪 <b>Новый магазин</b>\n\n"
            f"📛 {s.name}\n📍 {s.address or '—'}\n📞 {s.phone or '—'}"
        )
        await call.message.answer(text, reply_markup=kb.admin_approve_shop(s.id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_shop_ok_"))
async def shop_ok(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "active"
            await session.commit()
            if shop.tg_id:
                try:
                    await bot_shop.send_message(shop.tg_id,
                        "✅ <b>Ваш магазин одобрен!</b>\n\nОтправьте /start")
                except Exception:
                    pass
    await log_action(f"Магазин #{shop_id} одобрен")
    await call.message.edit_text(f"✅ Магазин #{shop_id} одобрен.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_shop_no_"))
async def shop_no(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "blocked"
            await session.commit()
            if shop.tg_id:
                try:
                    await bot_shop.send_message(shop.tg_id, "❌ Ваш магазин отклонён.")
                except Exception:
                    pass
    await log_action(f"Магазин #{shop_id} отклонён")
    await call.message.edit_text(f"❌ Магазин #{shop_id} отклонён.")
    await call.answer()


@router.callback_query(F.data == "admin_req_couriers")
async def req_couriers(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.status == "pending"))
        couriers = r.scalars().all()

    if not couriers:
        await call.message.edit_text("✅ Нет заявок курьеров.",
                                     reply_markup=kb.admin_requests_menu())
        await call.answer()
        return

    for c in couriers[:10]:
        text = (
            f"🚴 <b>Новый курьер</b>\n\n"
            f"👤 {c.name}\n📞 {c.phone or '—'}\n🏙 {c.city or '—'}\n🚗 {c.transport or '—'}"
        )
        await call.message.answer(text, reply_markup=kb.admin_approve_courier(c.id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_cour_ok_"))
async def cour_ok(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = r.scalar_one_or_none()
        if c:
            c.status = "active"
            c.is_blocked = False
            await session.commit()
            if c.tg_id:
                try:
                    await bot_courier.send_message(c.tg_id, "✅ Вы одобрены! Отправьте /start")
                except Exception:
                    pass
    await log_action(f"Курьер #{courier_id} одобрен")
    await call.message.edit_text(f"✅ Курьер #{courier_id} одобрен.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_cour_no_"))
async def cour_no(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = r.scalar_one_or_none()
        if c:
            c.status = "blocked"
            c.is_blocked = True
            await session.commit()
            if c.tg_id:
                try:
                    await bot_courier.send_message(c.tg_id, "❌ Заявка отклонена.")
                except Exception:
                    pass
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

    text = f"🏪 <b>Магазины ({len(all_shops)})</b>\n\nСтр. {page + 1}"
    await call.message.edit_text(text, reply_markup=kb.admin_shops_list(items, page))
    await call.answer()


@router.callback_query(F.data.startswith("admin_shops_page_"))
async def admin_shops_page_route(call: CallbackQuery):
    page = int(call.data.split("_")[3])
    await admin_shops_page(call, page)


@router.callback_query(F.data.startswith("admin_shop_view_"))
async def admin_shop_view(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if not shop:
            await call.answer("Не найден", show_alert=True)
            return
        orders_r = await session.execute(
            select(Order).where(Order.shop_id == shop_id, Order.status == "done")
        )
        done_orders = orders_r.scalars().all()
        turnover = sum(float(o.total_price) for o in done_orders)

    status_map = {"active": "🟢", "pending": "🟡", "blocked": "🔴"}
    text = (
        f"🏪 <b>{shop.name}</b> {status_map.get(shop.status, '')}\n\n"
        f"👤 {shop.owner_name or '—'}\n📞 {shop.phone or '—'}\n📍 {shop.address or '—'}\n"
        f"⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})\n\n"
        f"📦 Заказов: {len(done_orders)}\n"
        f"💰 Оборот: {helpers.money(turnover)}\n"
        f"🏦 Баланс: {helpers.money(shop.balance)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_shop_card(shop_id, shop.status))
    await call.answer()


@router.callback_query(F.data.startswith("admin_shop_block_"))
async def admin_shop_block(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "blocked"
            await session.commit()
            if shop.tg_id:
                try:
                    await bot_shop.send_message(
                        shop.tg_id,
                        f"🚫 <b>Магазин заблокирован.</b>\n\nПоддержка: {config.SUPPORT_TG}"
                    )
                except Exception:
                    pass
    await log_action(f"Магазин #{shop_id} заблокирован")
    await call.answer("🚫 Заблокирован", show_alert=True)
    await admin_shop_view(call)


@router.callback_query(F.data.startswith("admin_shop_unblock_"))
async def admin_shop_unblock(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "active"
            await session.commit()
            if shop.tg_id:
                try:
                    await bot_shop.send_message(shop.tg_id, "✅ Ваш магазин разблокирован!")
                except Exception:
                    pass
    await log_action(f"Магазин #{shop_id} разблокирован")
    await call.answer("✅ Разблокирован", show_alert=True)
    await admin_shop_view(call)


@router.callback_query(F.data.startswith("admin_shop_stats_"))
async def admin_shop_stats(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    async with async_session() as session:
        orders_r = await session.execute(
            select(Order).where(Order.shop_id == shop_id).order_by(Order.id.desc())
        )
        orders = orders_r.scalars().all()

    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    wait = sum(1 for o in orders if o.status == "wait")
    total_sum = sum(float(o.total_price) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Статистика магазина</b>\n\n"
        f"📦 Всего: {len(orders)}\n✅ Доставлено: {done}\n"
        f"❌ Отменено: {cancel}\n⏳ В работе: {wait}\n\n"
        f"💰 Оборот: {helpers.money(total_sum)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_shop_view_{shop_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("admin_shop_msg_"))
async def admin_shop_msg(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[3])
    await state.update_data(msg_target_type="shop", msg_target_id=shop_id)
    await state.set_state(AdminFSM.reply_to_client)
    await call.message.edit_text("✉️ Введите сообщение:", reply_markup=kb.admin_cancel())
    await call.answer()


@router.callback_query(F.data.startswith("admin_shop_topup_"))
async def shop_topup_start(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[3])
    await state.update_data(topup_shop_id=shop_id)
    await state.set_state(AdminFSM.topup_amount)
    await call.message.edit_text(
        "💰 <b>Пополнение баланса магазина</b>\n\nВведите сумму:",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.topup_amount)
async def shop_topup_apply(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    data = await state.get_data()
    shop_id = data.get("topup_shop_id")

    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.id == shop_id))
        shop = r.scalar_one_or_none()
        if not shop:
            await message.answer("❌ Не найден.")
            await state.clear()
            return

        await payments_service.topup_shop_balance(session, shop_id, amount)

        if shop.tg_id:
            try:
                await bot_shop.send_message(
                    shop.tg_id,
                    f"💰 Баланс пополнен на {helpers.money(amount)}"
                )
            except Exception:
                pass

    await log_action(f"Магазин #{shop_id} пополнен на {amount} ₽")
    await state.clear()
    await message.answer(f"✅ Баланс пополнен.", reply_markup=kb.admin_main())


@router.callback_query(F.data.startswith("admin_shop_edit_"))
async def admin_shop_edit(call: CallbackQuery):
    shop_id = int(call.data.split("_")[3])
    await call.message.edit_text(
        "✏️ <b>Что изменить?</b>",
        reply_markup=kb.admin_shop_edit_menu(shop_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("ase_"))
async def ase_field_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    field = parts[1]
    shop_id = int(parts[2])

    field_names = {"name": "название", "address": "адрес", "phone": "телефон", "geo": "гео"}
    await state.update_data(ase_shop_id=shop_id, ase_field=field)
    await state.set_state(AdminFSM.ase_field)

    if field == "geo":
        await call.message.edit_text(
            "📍 Отправьте геолокацию:",
            reply_markup=kb.admin_cancel()
        )
    else:
        await call.message.edit_text(
            f"✏️ Введите {field_names.get(field, field)}:",
            reply_markup=kb.admin_cancel()
        )
    await call.answer()


@router.message(AdminFSM.ase_field, F.location)
async def ase_field_geo_save(message: Message, state: FSMContext):
    data = await state.get_data()
    shop_id = data.get("ase_shop_id")
    if data.get("ase_field") != "geo":
        return
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
    items = [{
        "id": c.id, "name": c.name,
        "status": c.status, "balance": helpers.money(c.balance),
    } for c in page_c]

    text = f"🚴 <b>Курьеры ({len(all_c)})</b>\n\nСтр. {page + 1}"
    await call.message.edit_text(text, reply_markup=kb.admin_couriers_list(items, page))
    await call.answer()


@router.callback_query(F.data.startswith("admin_couriers_page_"))
async def admin_couriers_page_route(call: CallbackQuery):
    page = int(call.data.split("_")[3])
    await admin_couriers_page(call, page)


@router.callback_query(F.data.startswith("admin_cour_view_"))
async def admin_cour_view(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    async with async_session() as session:
        result = await session.execute(select(Courier).where(Courier.id == courier_id))
        courier = result.scalar_one_or_none()
        if not courier:
            await call.answer("Не найден", show_alert=True)
            return

    status_map = {"active": "🟢", "pending": "🟡", "blocked": "🔴"}
    state_map = {"on": "🟢 На смене", "off": "⚪ Не на смене", "break": "☕", "busy": "🚗"}

    text = (
        f"🚴 <b>{courier.name}</b> {status_map.get(courier.status, '')}\n"
        f"{state_map.get(courier.courier_state, '—')}\n\n"
        f"📞 {courier.phone or '—'}\n🏙 {courier.city or '—'}\n🚗 {courier.transport or '—'}\n"
        f"💳 {helpers.format_card(courier.card_number or '—')}\n\n"
        f"💰 Баланс: {helpers.money(courier.balance)}\n"
        f"⭐ {float(courier.rating or 0):.1f} ({courier.reviews_count})\n"
        f"📦 Заказов: {courier.total_orders}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_courier_card(courier_id, courier.status))
    await call.answer()


@router.callback_query(F.data.startswith("admin_cour_block_"))
async def admin_cour_block(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    async with async_session() as session:
        result = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = result.scalar_one_or_none()
        if c:
            c.status = "blocked"
            c.is_blocked = True
            await session.commit()
            if c.tg_id:
                try:
                    await bot_courier.send_message(
                        c.tg_id,
                        f"🚫 <b>Доступ закрыт.</b>\n\nПоддержка: {config.SUPPORT_TG}"
                    )
                except Exception:
                    pass
    await log_action(f"Курьер #{courier_id} заблокирован")
    await call.answer("🚫 Заблокирован", show_alert=True)
    await admin_cour_view(call)


@router.callback_query(F.data.startswith("admin_cour_unblock_"))
async def admin_cour_unblock(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    async with async_session() as session:
        result = await session.execute(select(Courier).where(Courier.id == courier_id))
        c = result.scalar_one_or_none()
        if c:
            c.status = "active"
            c.is_blocked = False
            await session.commit()
            if c.tg_id:
                try:
                    await bot_courier.send_message(c.tg_id, "✅ Доступ открыт!")
                except Exception:
                    pass
    await log_action(f"Курьер #{courier_id} разблокирован")
    await call.answer("✅ Разблокирован", show_alert=True)
    await admin_cour_view(call)


@router.callback_query(F.data.startswith("admin_cour_stats_"))
async def admin_cour_stats(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    async with async_session() as session:
        orders_r = await session.execute(
            select(Order).where(Order.courier_id == courier_id).order_by(Order.id.desc())
        )
        orders = orders_r.scalars().all()

    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    earned = sum(float(o.courier_fee or 0) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Статистика курьера</b>\n\n"
        f"📦 Всего: {len(orders)}\n✅ Доставлено: {done}\n❌ Отменено: {cancel}\n\n"
        f"💰 Заработал: {helpers.money(earned)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_cour_view_{courier_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("admin_cour_msg_"))
async def admin_cour_msg(call: CallbackQuery, state: FSMContext):
    courier_id = int(call.data.split("_")[3])
    await state.update_data(msg_target_type="courier", msg_target_id=courier_id)
    await state.set_state(AdminFSM.reply_to_client)
    await call.message.edit_text("✉️ Введите сообщение:", reply_markup=kb.admin_cancel())
    await call.answer()


@router.callback_query(F.data.startswith("admin_cour_topup_"))
async def cour_topup_start(call: CallbackQuery, state: FSMContext):
    courier_id = int(call.data.split("_")[3])
    await state.update_data(topup_cour_id=courier_id)
    await state.set_state(AdminFSM.topup_amount)
    await call.message.edit_text(
        "💰 <b>Пополнение баланса курьера</b>\n\nВведите сумму:",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.topup_amount)
async def cour_topup_apply(message: Message, state: FSMContext):
    # Если это не магазин — обрабатываем курьера
    data = await state.get_data()
    if data.get("topup_shop_id"):
        return  # уже обработано выше

    courier_id = data.get("topup_cour_id")
    if not courier_id:
        return

    try:
        amount = Decimal(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
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
            try:
                await bot_courier.send_message(
                    c.tg_id,
                    f"💰 Баланс пополнен на {helpers.money(amount)}"
                )
            except Exception:
                pass

    await log_action(f"Курьер #{courier_id} пополнен на {amount} ₽")
    await state.clear()
    await message.answer("✅ Баланс пополнен.", reply_markup=kb.admin_main())


@router.callback_query(F.data.startswith("admin_cour_edit_"))
async def admin_cour_edit(call: CallbackQuery):
    courier_id = int(call.data.split("_")[3])
    await call.message.edit_text(
        "✏️ <b>Что изменить?</b>",
        reply_markup=kb.admin_courier_edit_menu(courier_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("ace_"))
async def ace_field_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    field = parts[1]
    courier_id = int(parts[2])

    field_names = {"name": "имя", "phone": "телефон", "city": "город", "transport": "транспорт"}
    await state.update_data(ace_courier_id=courier_id, ace_field=field)
    await state.set_state(AdminFSM.ace_field)
    await call.message.edit_text(
        f"✏️ Введите {field_names.get(field, field)}:",
        reply_markup=kb.admin_cancel()
    )
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
#   ОТПРАВКА СООБЩЕНИЯ
# ═══════════════════════════════════════════
@router.message(AdminFSM.reply_to_client)
async def admin_send_message(message: Message, state: FSMContext):
    data = await state.get_data()
    ttype = data.get("msg_target_type")
    tid = data.get("msg_target_id")
    text = message.text.strip()

    target_id = None
    bot = None

    async with async_session() as session:
        if ttype == "shop":
            r = await session.execute(select(Shop).where(Shop.id == tid))
            obj = r.scalar_one_or_none()
            if obj:
                target_id = obj.tg_id
                bot = bot_shop
        elif ttype == "courier":
            r = await session.execute(select(Courier).where(Courier.id == tid))
            obj = r.scalar_one_or_none()
            if obj:
                target_id = obj.tg_id
                bot = bot_courier
        elif ttype == "client":
            r = await session.execute(select(Client).where(Client.id == tid))
            obj = r.scalar_one_or_none()
            if obj:
                target_id = obj.tg_id
                bot = bot_client

    if target_id and bot:
        try:
            await bot.send_message(target_id, f"✉️ <b>Сообщение от админа:</b>\n\n{text}")
            await message.answer("✅ Отправлено.", reply_markup=kb.admin_main())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=kb.admin_main())
    else:
        await message.answer("❌ Получатель не найден.", reply_markup=kb.admin_main())

    await state.clear()


# ═══════════════════════════════════════════
#   ПЕРЕВОДЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_payments")
async def payments_menu(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "payments"):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text("💳 <b>Переводы и платежи</b>",
                                 reply_markup=kb.admin_payments_menu())
    await call.answer()


@router.callback_query(F.data == "admin_pay_incoming")
async def pay_incoming(call: CallbackQuery):
    async with async_session() as session:
        payments = await payments_service.get_pending_payments(session)

    if not payments:
        await call.message.edit_text("✅ Нет ожидающих платежей заказов.",
                                     reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payments[:10]:
        async with async_session() as session:
            c_r = await session.execute(select(Client).where(Client.id == p.client_id))
            client = c_r.scalar_one_or_none()

        text = (
            f"💳 <b>Платёж заказа #{p.order_id}</b>\n\n"
            f"👤 {client.name if client else '—'}\n"
            f"💰 {helpers.money(p.amount)}\n"
            f"🕒 {helpers.format_dt(p.created_at)}\n\n"
            f"⚠️ Комментарий: <b>{p.order_id}</b>"
        )
        await call.message.answer(text, reply_markup=kb.admin_confirm_payment(p.order_id))
    await call.answer()


@router.callback_query(F.data == "admin_pay_deliveries")
async def pay_deliveries(call: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(DeliveryPayment).where(DeliveryPayment.status == "pending")
        )
        payments = result.scalars().all()

    if not payments:
        await call.message.edit_text("✅ Нет ожидающих платежей за доставки.",
                                     reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payments[:10]:
        async with async_session() as session:
            s_r = await session.execute(select(Shop).where(Shop.id == p.shop_id))
            shop = s_r.scalar_one_or_none()

        text = (
            f"🚚 <b>Платёж #Д-{p.delivery_id}</b>\n\n"
            f"🏪 {shop.name if shop else '—'}\n"
            f"💰 {helpers.money(p.amount)}\n"
            f"⚠️ Комментарий: <b>Д-{p.delivery_id}</b>"
        )
        await call.message.answer(text, reply_markup=kb.admin_confirm_delivery(p.delivery_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_pay_ok_"))
async def pay_ok(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        order = await orders_service.confirm_payment(session, order_id, call.from_user.id)

    await call.message.edit_text(f"✅ Оплата #{order_id} подтверждена.")

    if order:
        async with async_session() as s2:
            sr = await s2.execute(select(Shop).where(Shop.id == order.shop_id))
            shop = sr.scalar_one_or_none()
            cr = await s2.execute(select(Client).where(Client.id == order.client_id))
            client = cr.scalar_one_or_none()

        if shop and shop.tg_id:
            try:
                await bot_shop.send_message(
                    shop.tg_id,
                    f"🔔 <b>Новый заказ #{order.id}</b>\n\n"
                    f"📍 {order.address}\n👤 {order.client_name}, {order.client_phone}\n"
                    f"💰 {helpers.money(order.total_price)}"
                )
            except Exception:
                pass

        if client and client.tg_id:
            try:
                await bot_client.send_message(
                    client.tg_id,
                    f"✅ <b>Оплата заказа #{order.id} подтверждена!</b>"
                )
            except Exception:
                pass

    await log_action(f"Оплата #{order_id} подтверждена")
    await call.answer()


@router.callback_query(F.data.startswith("admin_pay_no_"))
async def pay_no(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await payments_service.mark_payment_rejected(session, order_id, call.from_user.id)
        await orders_service.cancel_order(session, order_id, reason="payment_rejected",
                                          cancelled_by="admin", refund=False)
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        client = None
        if order:
            cr = await session.execute(select(Client).where(Client.id == order.client_id))
            client = cr.scalar_one_or_none()

    await call.message.edit_text(f"❌ Платёж #{order_id} отклонён.")

    if client and client.tg_id:
        try:
            await bot_client.send_message(
                client.tg_id,
                f"❌ <b>Платёж по заказу #{order_id} не подтверждён.</b>\n\n"
                f"Проверьте комментарий.\nПоддержка: {config.SUPPORT_TG}"
            )
        except Exception:
            pass

    await log_action(f"Платёж #{order_id} отклонён")
    await call.answer()


@router.callback_query(F.data.startswith("admin_del_pay_ok_"))
async def del_pay_ok(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[4])
    async with async_session() as session:
        d = await payments_service.confirm_delivery_payment(session, delivery_id, call.from_user.id)
        shop = None
        if d:
            s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
            shop = s_r.scalar_one_or_none()

    await call.message.edit_text(f"✅ Оплата #Д-{delivery_id} подтверждена.")

    if shop and shop.tg_id:
        try:
            await bot_shop.send_message(
                shop.tg_id,
                f"✅ <b>Оплата доставки #Д-{delivery_id} подтверждена!</b>\n\nИщем курьера 🚴"
            )
        except Exception:
            pass

    await log_action(f"Оплата #Д-{delivery_id} подтверждена")
    await call.answer()


@router.callback_query(F.data.startswith("admin_del_pay_no_"))
async def del_pay_no(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[4])
    async with async_session() as session:
        d = await payments_service.reject_delivery_payment(session, delivery_id, call.from_user.id)
        shop = None
        if d:
            s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
            shop = s_r.scalar_one_or_none()

    await call.message.edit_text(f"❌ Платёж #Д-{delivery_id} отклонён.")

    if shop and shop.tg_id:
        try:
            await bot_shop.send_message(shop.tg_id,
                f"❌ Платёж доставки #Д-{delivery_id} не подтверждён.")
        except Exception:
            pass

    await call.answer()


@router.callback_query(F.data == "admin_pay_outgoing")
async def pay_outgoing(call: CallbackQuery):
    async with async_session() as session:
        payouts = await payments_service.get_pending_payouts(session)

    if not payouts:
        await call.message.edit_text("✅ Нет ожидающих выплат.",
                                     reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payouts[:10]:
        role_map = {"courier": "🚴", "shop": "🏪", "client": "👤"}
        method_map = {"card": "💳 Карта", "sbp": "📱 СБП"}
        text = (
            f"💸 <b>Выплата #{p.id}</b>\n\n"
            f"{role_map.get(p.user_type, '•')} ID {p.user_id}\n"
            f"💰 {helpers.money(p.amount)}\n"
            f"{method_map.get(p.method, '')}: {p.target or '—'}\n"
            f"🏦 {p.bank_name or '—'}\n"
            f"👤 {p.card_holder or '—'}"
        )
        if p.commission > 0:
            text += f"\n📉 Комиссия: {helpers.money(p.commission)}\n💵 К выплате: {helpers.money(p.amount_to_pay)}"
        await call.message.answer(text, reply_markup=kb.admin_payout_actions(p.id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_payout_transfer_"))
async def payout_transfer(call: CallbackQuery):
    payout_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await payments_service.mark_payout_transferred(session, payout_id, call.from_user.id)
    await log_action(f"Выплата #{payout_id} отправлена")
    await call.message.edit_text(f"💳 Выплата #{payout_id} отмечена как отправленная.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_payout_ok_"))
async def payout_ok(call: CallbackQuery):
    payout_id = int(call.data.split("_")[3])
    async with async_session() as session:
        p = await payments_service.mark_payout_done(session, payout_id, call.from_user.id)

        if p:
            if p.user_type == "courier":
                r = await session.execute(select(Courier).where(Courier.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try:
                        await bot_courier.send_message(user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!")
                    except Exception:
                        pass
            elif p.user_type == "shop":
                r = await session.execute(select(Shop).where(Shop.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try:
                        await bot_shop.send_message(user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!")
                    except Exception:
                        pass
            elif p.user_type == "client":
                r = await session.execute(select(Client).where(Client.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try:
                        await bot_client.send_message(user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!")
                    except Exception:
                        pass

    await log_action(f"Выплата #{payout_id} подтверждена")
    await call.message.edit_text(f"✅ Выплата #{payout_id} подтверждена.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_payout_no_"))
async def payout_no(call: CallbackQuery):
    payout_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await payments_service.mark_payout_rejected(session, payout_id, call.from_user.id)
    await log_action(f"Выплата #{payout_id} отклонена")
    await call.message.edit_text(f"❌ Выплата #{payout_id} отклонена.")
    await call.answer()


@router.callback_query(F.data == "admin_pay_history")
async def pay_history(call: CallbackQuery):
    await call.message.edit_text("📜 <b>История переводов</b>",
                                 reply_markup=kb.admin_pay_history_menu())
    await call.answer()


@router.callback_query(F.data == "admin_hist_in")
async def hist_in(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Payment).order_by(Payment.id.desc()).limit(30))
        payments = r.scalars().all()

    text = "📥 <b>Входящие (30):</b>\n\n"
    for p in payments:
        emoji = {"pending": "⏳", "confirmed": "✅", "rejected": "❌"}.get(p.status, "❓")
        text += f"{emoji} #{p.order_id} — {helpers.money(p.amount)} — {helpers.format_dt(p.created_at)}\n"

    if not payments:
        text = "📥 История пуста."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_pay_history"))
    await call.answer()


@router.callback_query(F.data == "admin_hist_out")
async def hist_out(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Payout).order_by(Payout.id.desc()).limit(30))
        payouts = r.scalars().all()

    text = "📤 <b>Исходящие (30):</b>\n\n"
    for p in payouts:
        emoji = {"pending": "⏳", "processing": "💳", "done": "✅", "rejected": "❌"}.get(p.status, "❓")
        role = {"courier": "🚴", "shop": "🏪", "client": "👤"}.get(p.user_type, "•")
        text += f"{emoji} {role} #{p.id} — {helpers.money(p.amount)} — {helpers.format_dt(p.created_at)}\n"

    if not payouts:
        text = "📤 История пуста."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_pay_history"))
    await call.answer()


@router.callback_query(F.data == "admin_pay_refunds")
async def pay_refunds(call: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.status == "cancel").order_by(Order.id.desc()).limit(20)
        )
        orders = result.scalars().all()

    if not orders:
        await call.message.edit_text("💸 Нет отменённых заказов.",
                                     reply_markup=kb.admin_back("admin_payments"))
        await call.answer()
        return

    refunds = [{"order_id": o.id, "amount": helpers.money(o.total_price)} for o in orders]
    await call.message.edit_text(
        f"💸 <b>Возвраты ({len(refunds)})</b>",
        reply_markup=kb.admin_refunds_list(refunds)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_refund_view_"))
async def admin_refund_view(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()
        if not order:
            await call.answer("Не найден", show_alert=True)
            return
        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    text = (
        f"💸 <b>Заказ #{order.id}</b>\n\n"
        f"👤 {client.name if client else '—'}\n"
        f"💰 {helpers.money(order.total_price)}\n"
        f"📋 {order.cancel_reason or '—'}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_refund_card(order_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_refund_card_"))
async def admin_refund_card(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[3])
    await state.update_data(refund_order_id=order_id)
    await state.set_state(AdminFSM.refund_amount)
    await call.message.edit_text(
        "💳 Введите номер карты клиента (16 цифр):",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.refund_amount)
async def admin_refund_card_process(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты.")
        return

    data = await state.get_data()
    order_id = data.get("refund_order_id")
    card = helpers.clean_phone(message.text)

    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()
        if not order:
            await message.answer("❌ Заказ не найден.")
            await state.clear()
            return

        await payments_service.refund_to_card(
            session=session, client_id=order.client_id,
            amount=order.total_price, card_number=card, order_id=order_id,
        )

    await log_action(f"Возврат на карту #{order_id}")
    await state.clear()
    await message.answer(
        f"✅ Возврат {helpers.money(order.total_price)} → *{card[-4:]}",
        reply_markup=kb.admin_main()
    )


@router.callback_query(F.data.startswith("admin_refund_balance_"))
async def admin_refund_balance(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()
        if not order:
            await call.answer("Не найден", show_alert=True)
            return
        await payments_service.refund_to_balance(session, order.client_id, order.total_price, order_id)

        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()
        if client and client.tg_id:
            try:
                await bot_client.send_message(
                    client.tg_id,
                    f"💰 <b>Возврат {helpers.money(order.total_price)}</b> зачислен на баланс."
                )
            except Exception:
                pass

    await log_action(f"Возврат на баланс #{order_id}")
    await call.answer("✅ Зачислено на баланс", show_alert=True)
    await pay_refunds(call)


@router.callback_query(F.data.startswith("admin_refund_reject_"))
async def admin_refund_reject(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    await call.answer("❌ Отклонено", show_alert=True)
    await pay_refunds(call)


# ═══════════════════════════════════════════
#   ДОСТАВКИ МАГАЗИНОВ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_deliveries")
async def admin_deliveries(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(DeliveryOrder).order_by(DeliveryOrder.id.desc()).limit(50)
        )
        deliveries = r.scalars().all()

    if not deliveries:
        await call.message.edit_text("🚚 Доставок нет.", reply_markup=kb.admin_back())
        await call.answer()
        return

    items = []
    for d in deliveries:
        async with async_session() as s2:
            sr = await s2.execute(select(Shop).where(Shop.id == d.shop_id))
            shop = sr.scalar_one_or_none()
        items.append({
            "id": d.id,
            "shop_name": shop.name if shop else "—",
            "status": d.status,
        })

    await call.message.edit_text(
        f"🚚 <b>Доставки ({len(deliveries)})</b>",
        reply_markup=kb.admin_deliveries_list(items)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_del_view_"))
async def admin_del_view(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[3])
    async with async_session() as session:
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()
        if not d:
            await call.answer("Не найдено", show_alert=True)
            return
        s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
        shop = s_r.scalar_one_or_none()

    status_map = {
        "pending": "⏸ Ожидает оплаты", "paid": "💳 Ждёт админа",
        "confirmed": "✅ Ищем курьера", "going": "🚴 В пути",
        "picked": "📦 Забрал", "at_client": "📍 У клиента",
        "done": "✅ Доставлено", "cancel": "❌ Отменено",
    }
    text = (
        f"🚚 <b>Доставка #Д-{d.id}</b>\n"
        f"{status_map.get(d.status, d.status)}\n\n"
        f"🏪 {shop.name if shop else '—'}\n"
        f"📍 Откуда: {d.from_address}\n"
        f"📍 Куда: {d.to_address}\n"
        f"👤 {d.client_name}, {d.client_phone}\n"
        f"💰 {helpers.money(d.client_pays)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_delivery_view(delivery_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_del_cancel_"))
async def admin_del_cancel(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[3])
    async with async_session() as session:
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()
        if d:
            d.status = "cancel"
            d.cancel_reason = "admin_cancelled"
            await session.commit()
            s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
            shop = s_r.scalar_one_or_none()
            if shop and shop.tg_id:
                try:
                    await bot_shop.send_message(shop.tg_id,
                        f"❌ Доставка #Д-{delivery_id} отменена админом.")
                except Exception:
                    pass

    await log_action(f"Доставка #Д-{delivery_id} отменена")
    await call.answer("❌ Отменено", show_alert=True)
    await admin_deliveries(call)


# ═══════════════════════════════════════════
#   ЗАВИСШИЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_stuck_orders")
async def stuck_orders(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(Order).where(
                Order.status == "wait",
                Order.payment_status == "confirmed",
                Order.courier_id.is_(None),
            )
        )
        orders = r.scalars().all()

    stuck = [
        o for o in orders
        if o.wait_started_at and (helpers.now() - o.wait_started_at).total_seconds() > 30 * 60
    ]

    if not stuck:
        await call.message.edit_text("✅ Нет зависших заказов.", reply_markup=kb.admin_back())
        await call.answer()
        return

    for o in stuck[:10]:
        wait_min = int((helpers.now() - o.wait_started_at).total_seconds() / 60)
        fee = int(float(o.courier_fee or 0) + float(o.boost_amount or 0))
        text = (
            f"⏰ <b>Заказ #{o.id}</b>\n"
            f"🕒 Ждёт: {wait_min} мин\n💰 Курьеру: {fee} ₽\n📍 {o.address}"
        )
        await call.message.answer(text, reply_markup=kb.admin_stuck_order(o.id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_boost_") & ~F.data.startswith("admin_boost_set_") & ~F.data.startswith("admin_boost_custom"))
async def admin_boost(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    await call.message.edit_text(
        "💰 <b>На сколько поднять ставку?</b>",
        reply_markup=kb.admin_boost_amount(order_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_boost_set_"))
async def admin_boost_set(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[3])
    amount = float(parts[4])

    async with async_session() as session:
        await session.execute(
            update(Order).where(Order.id == order_id)
            .values(boost_amount=Order.boost_amount + amount)
        )
        await session.commit()

    await log_action(f"Boost +{amount} ₽ на #{order_id}")
    await call.message.edit_text(f"✅ Ставка поднята на {amount} ₽.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_boost_custom_"))
async def admin_boost_custom(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[3])
    await state.update_data(boost_order_id=order_id)
    await state.set_state(AdminFSM.boost_custom)
    await call.message.edit_text("💰 Введите сумму прибавки:", reply_markup=kb.admin_cancel())
    await call.answer()


@router.message(AdminFSM.boost_custom)
async def admin_boost_custom_save(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число > 0.")
        return

    data = await state.get_data()
    order_id = data.get("boost_order_id")

    async with async_session() as session:
        await session.execute(
            update(Order).where(Order.id == order_id)
            .values(boost_amount=Order.boost_amount + amount)
        )
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Ставка поднята на {amount} ₽.", reply_markup=kb.admin_main())


@router.callback_query(F.data.startswith("admin_cancel_order_"))
async def admin_cancel_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await orders_service.cancel_order(
            session, order_id,
            reason="admin_cancelled", cancelled_by="admin", refund=True,
        )
    await log_action(f"Заказ #{order_id} отменён админом")
    await call.answer("❌ Отменён", show_alert=True)
    await stuck_orders(call)


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

    promos_data = []
    for p in promos[:8]:
        d = f"{int(p.discount_value)}%" if p.discount_type == "percent" else helpers.money(p.discount_value)
        promos_data.append({"id": p.id, "code": p.code, "discount_text": d, "is_active": p.is_active})

    await call.message.edit_text(text, reply_markup=kb.admin_promo_list(promos_data))
    await call.answer()


@router.callback_query(F.data == "admin_promo_create")
async def promo_create_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.promo_code)
    await call.message.edit_text(
        "🎁 <b>Создание промокода</b>\n\nШаг 1/4: Введите код:",
        reply_markup=kb.admin_cancel()
    )
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
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число > 0.")
        return

    await state.update_data(discount_value=value)
    await state.set_state(AdminFSM.promo_uses)
    await message.answer(
        "🎁 Шаг 4/4: Лимит использований\n\nЧисло или 0 (безлимит):",
        reply_markup=kb.admin_cancel()
    )


@router.message(AdminFSM.promo_uses)
async def promo_set_uses(message: Message, state: FSMContext):
    try:
        max_uses = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    data = await state.get_data()
    async with async_session() as session:
        promo = Promo(
            code=data["promo_code"],
            discount_type=data["discount_type"],
            discount_value=data["discount_value"],
            max_uses=max_uses,
            is_active=True,
        )
        session.add(promo)
        await session.commit()

    await log_action(f"Промокод {data['promo_code']} создан")
    await state.clear()
    d = f"{int(data['discount_value'])}%" if data["discount_type"] == "percent" else helpers.money(data["discount_value"])
    await message.answer(
        f"✅ Промокод создан!\n🎁 <code>{data['promo_code']}</code> — {d}",
        reply_markup=kb.admin_main()
    )


@router.callback_query(F.data.startswith("admin_promo_view_"))
async def promo_view(call: CallbackQuery):
    promo_id = int(call.data.split("_")[3])
    await call.message.edit_text(f"🎁 Промокод #{promo_id}",
                                 reply_markup=kb.admin_promo_view(promo_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_promo_del_"))
async def promo_delete(call: CallbackQuery):
    promo_id = int(call.data.split("_")[3])
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
        r = await session.execute(
            select(Complaint).where(Complaint.status == "pending")
            .order_by(Complaint.id.desc()).limit(20)
        )
        complaints = r.scalars().all()

    if not complaints:
        await call.message.edit_text("✅ Жалоб нет.", reply_markup=kb.admin_back())
        await call.answer()
        return

    items = [{"id": c.id, "type": c.target_type} for c in complaints]
    await call.message.edit_text(
        f"🆘 <b>Жалобы ({len(items)})</b>",
        reply_markup=kb.admin_complaints_list(items)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_complaint_view_"))
async def admin_complaint_view(call: CallbackQuery):
    complaint_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
        c = r.scalar_one_or_none()
        if not c:
            await call.answer("Не найдено", show_alert=True)
            return

    text = (
        f"🆘 <b>Жалоба #{c.id}</b>\n\n"
        f"🎯 На: {c.target_type} #{c.target_id}\n"
        f"📦 Заказ: #{c.order_id}\n\n"
        f"📝 {c.reason}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_complaint_card(complaint_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_comp_refund_"))
async def admin_comp_refund(call: CallbackQuery):
    complaint_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
        c = r.scalar_one_or_none()
        if c:
            o_r = await session.execute(select(Order).where(Order.id == c.order_id))
            order = o_r.scalar_one_or_none()
            if order:
                await payments_service.refund_to_balance(
                    session, order.client_id, order.total_price, order.id
                )
            c.status = "resolved"
            c.admin_id = call.from_user.id
            await session.commit()

    await log_action(f"Жалоба #{complaint_id} одобрена")
    await call.answer("✅ Возврат сделан", show_alert=True)
    await admin_complaints(call)


@router.callback_query(F.data.startswith("admin_comp_reject_"))
async def admin_comp_reject(call: CallbackQuery):
    complaint_id = int(call.data.split("_")[3])
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
    await call.message.edit_text("📢 <b>Рассылка</b>\n\nКому?",
                                 reply_markup=kb.admin_broadcast_menu())
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
    await message.answer(
        f"👁 <b>Проверьте</b>\n\nКому: {target}\n\n{data['bc_text']}",
        reply_markup=kb.admin_broadcast_confirm()
    )


@router.callback_query(F.data == "admin_bc_send", AdminFSM.broadcast_confirm)
async def admin_bc_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target = data.get("bc_target")
    text = data.get("bc_text")

    ids = []
    bot = None

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

    sent = 0
    failed = 0
    for uid in ids:
        try:
            await bot.send_message(uid, f"📢 <b>Сообщение от SLIPI:</b>\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    await log_action(f"Рассылка ({target}): {sent}")
    await state.clear()
    await call.message.edit_text(
        f"✅ Рассылка завершена.\n📤 {sent}\n❌ {failed}",
        reply_markup=kb.admin_main()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   АНАЛИТИКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_analytics")
async def admin_analytics(call: CallbackQuery):
    await call.message.edit_text("📊 <b>Аналитика</b>\n\nПериод:",
                                 reply_markup=kb.admin_analytics_menu())
    await call.answer()


@router.callback_query(F.data.startswith("admin_analytics_"))
async def admin_analytics_period(call: CallbackQuery):
    period = call.data.replace("admin_analytics_", "")
    now = datetime.now()
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "Сегодня"
    elif period == "week":
        since = now - timedelta(days=7)
        label = "За неделю"
    elif period == "month":
        since = now - timedelta(days=30)
        label = "За месяц"
    else:
        since = datetime(2020, 1, 1)
        label = "За всё время"

    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.created_at >= since))
        orders = r.scalars().all()

    total = len(orders)
    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    turnover = sum(float(o.total_price) for o in orders if o.status == "done")
    platform = sum(float(o.platform_income) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Аналитика — {label}</b>\n\n"
        f"📦 Заказов: {total}\n✅ Доставлено: {done}\n❌ Отменено: {cancel}\n\n"
        f"💰 Оборот: {helpers.money(turnover)}\n"
        f"📈 Доход: {helpers.money(platform)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_analytics_menu())
    await call.answer()


@router.callback_query(F.data == "admin_top_shops")
async def admin_top_shops(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(Shop).where(Shop.status == "active")
            .order_by(Shop.total_orders.desc()).limit(10)
        )
        shops = r.scalars().all()

    text = "🏆 <b>Топ-10 магазинов:</b>\n\n"
    for i, s in enumerate(shops, start=1):
        text += f"{i}. {s.name} — {s.total_orders} — ⭐ {float(s.rating or 0):.1f}\n"
    if not shops:
        text = "🏆 Нет данных."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()


@router.callback_query(F.data == "admin_top_couriers")
async def admin_top_couriers(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(Courier).where(Courier.status == "active")
            .order_by(Courier.total_orders.desc()).limit(10)
        )
        couriers = r.scalars().all()

    text = "🏆 <b>Топ-10 курьеров:</b>\n\n"
    for i, c in enumerate(couriers, start=1):
        text += f"{i}. {c.name} — {c.total_orders} — ⭐ {float(c.rating or 0):.1f}\n"
    if not couriers:
        text = "🏆 Нет данных."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()


@router.callback_query(F.data == "admin_shifts_dashboard")
async def admin_shifts_dashboard(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(Courier).where(Courier.courier_state == "on")
        )
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
        text += f"• {c.name} — 📍 {lat}, {lon} (обновлено {loc_time})\n"

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()


# ═══════════════════════════════════════════
#   НАСТРОЙКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_settings")
async def admin_settings(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "settings"):
        await call.answer("Нет доступа", show_alert=True)
        return

    text = (
        f"⚙️ <b>Настройки системы</b>\n\n"
        f"💸 Зоны доставки: 350–600 ₽\n"
        f"💰 Мин. вывод курьера: {config.COURIER_MIN_WITHDRAW} ₽\n"
        f"🎁 Бонус за 10: {config.BONUS_PER_10_ORDERS} ₽\n"
        f"🕒 Часы: {config.WORK_HOURS}\n"
        f"🏙 Город: {config.CITY}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_settings_menu())
    await call.answer()


@router.callback_query(F.data == "admin_multicity")
async def multicity_stub(call: CallbackQuery):
    await call.message.edit_text(
        "🌍 <b>Мультигород</b>\n\n🚧 В разработке.\n\nПланируем:\n"
        "• Один бот на несколько городов\n"
        "• Клиент выбирает свой город\n"
        "• Отдельные магазины и курьеры",
        reply_markup=kb.admin_back("admin_settings")
    )
    await call.answer()


# Обновление бота
@router.callback_query(F.data == "admin_update_bot")
async def admin_update_bot(call: CallbackQuery):
    await call.message.edit_text(
        "🔄 <b>Обновление бота</b>\n\n"
        "Создайте обновление и отправьте всем пользователям.",
        reply_markup=kb.admin_update_bot_menu()
    )
    await call.answer()


@router.callback_query(F.data == "admin_update_new")
async def update_new_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.update_version)
    await call.message.edit_text("📝 Введите версию (например 1.2.0):",
                                 reply_markup=kb.admin_cancel())
    await call.answer()


@router.message(AdminFSM.update_version)
async def update_set_version(message: Message, state: FSMContext):
    await state.update_data(update_version=message.text.strip())
    await state.set_state(AdminFSM.update_changes)
    await message.answer("📝 Опишите изменения:", reply_markup=kb.admin_cancel())


@router.message(AdminFSM.update_changes)
async def update_set_changes(message: Message, state: FSMContext):
    await state.update_data(update_changes=message.text.strip())
    data = await state.get_data()

    await state.set_state(AdminFSM.update_changes)  # временно оставим
    await state.clear()

    await message.answer(
        f"👁 <b>Проверьте обновление</b>\n\n"
        f"📌 Версия: {data['update_version']}\n\n{data['update_changes']}\n\n"
        f"Отправить всем?",
        reply_markup=kb.admin_update_confirm()
    )

    # Сохраняем данные в FSM повторно
    await state.update_data(
        update_version=data["update_version"],
        update_changes=data["update_changes"],
        ready_to_send=True,
    )


@router.callback_query(F.data == "admin_update_send")
async def update_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    version = data.get("update_version")
    changes = data.get("update_changes")
    if not version or not changes:
        await call.answer("Данные потеряны", show_alert=True)
        return

    text = f"🔄 <b>Обновление {version}</b>\n\n{changes}"

    ids = []
    async with async_session() as session:
        # Клиенты
        r = await session.execute(select(Client).where(Client.tg_id.isnot(None), Client.is_blocked == False))
        clients = [u.tg_id for u in r.scalars().all()]
        # Курьеры
        r = await session.execute(select(Courier).where(Courier.tg_id.isnot(None), Courier.is_blocked == False))
        couriers = [u.tg_id for u in r.scalars().all()]
        # Магазины
        r = await session.execute(select(Shop).where(Shop.tg_id.isnot(None)))
        shops = [u.tg_id for u in r.scalars().all()]

        # Записываем обновление
        upd = BotUpdate(version=version, changes=changes, sent_to_all=True)
        session.add(upd)
        await session.commit()

    sent = 0
    for uid in clients:
        try:
            await bot_client.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    for uid in couriers:
        try:
            await bot_courier.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    for uid in shops:
        try:
            await bot_shop.send_message(uid, text)
            sent += 1
        except Exception:
            pass

    await state.clear()
    await log_action(f"Обновление {version} отправлено: {sent}")
    await call.message.edit_text(
        f"✅ Обновление {version} отправлено {sent} пользователям.",
        reply_markup=kb.admin_main()
    )
    await call.answer()


@router.callback_query(F.data == "admin_update_history")
async def update_history(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(BotUpdate).order_by(BotUpdate.id.desc()).limit(20))
        updates = r.scalars().all()

    if not updates:
        text = "📜 История обновлений пуста."
    else:
        text = "📜 <b>История обновлений:</b>\n\n"
        for u in updates:
            text += f"<b>{u.version}</b> — {helpers.format_dt(u.created_at)}\n{u.changes[:100]}\n\n"

    await call.message.edit_text(text, reply_markup=kb.admin_update_bot_menu())
    await call.answer()


# ═══════════════════════════════════════════
#   МУЛЬТИАДМИН
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_admins")
async def admin_admins(call: CallbackQuery):
    async with async_session() as session:
        perms = await get_admin_permissions(session, call.from_user.id)
    if not has_perm(perms, "admins"):
        await call.answer("Нет доступа", show_alert=True)
        return

    await call.message.edit_text(
        "🔑 <b>Управление админами</b>\n\n"
        f"👑 Главный админ: <code>{config.ADMIN_ID}</code>",
        reply_markup=kb.admin_admins_menu()
    )
    await call.answer()


@router.callback_query(F.data == "admin_add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.add_admin_id)
    await call.message.edit_text(
        "➕ <b>Новый админ</b>\n\nВведите Telegram ID:",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.add_admin_id)
async def add_admin_set_id(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
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
        admin = Admin(
            tg_id=(await state.get_data()).get("new_admin_id"),
            name=name,
            added_by=message.from_user.id,
            permissions="{}",
            is_active=True,
        )
        session.add(admin)
        await session.commit()

    await state.clear()
    await message.answer("✅ Админ добавлен. Настройте права.",
                         reply_markup=kb.admin_main())


@router.callback_query(F.data == "admin_list_admins")
async def list_admins(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.is_active == True))
        admins = r.scalars().all()

    if not admins:
        text = "📋 Дополнительных админов нет."
    else:
        text = f"📋 <b>Админы ({len(admins)})</b>\n\n"
        for a in admins:
            text += f"• {a.name or '—'} — <code>{a.tg_id}</code>\n"

    rows = [[kb.btn("👑 Главный", "noop")]]
    for a in admins:
        rows.append([kb.btn(f"🔑 {a.name or a.tg_id}", f"admin_admin_view_{a.id}")])
    rows.append([kb.btn("🔙 Назад", "admin_admins")])

    await call.message.edit_text(text, reply_markup=kb.kb(rows))
    await call.answer()


@router.callback_query(F.data.startswith("admin_admin_view_"))
async def admin_admin_view(call: CallbackQuery):
    admin_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.id == admin_id))
        admin = r.scalar_one_or_none()
        if not admin:
            await call.answer("Не найден", show_alert=True)
            return

    active = list(helpers.parse_permissions(admin.permissions).keys())
    text = f"🔑 <b>{admin.name or admin.tg_id}</b>\n\nID: <code>{admin.tg_id}</code>\n\nВыберите права:"
    await call.message.edit_text(text, reply_markup=kb.admin_permissions_menu(admin_id, active))
    await call.answer()


@router.callback_query(F.data.startswith("perm_toggle_"))
async def perm_toggle(call: CallbackQuery):
    parts = call.data.split("_")
    admin_id = int(parts[2])
    key = parts[3]

    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.id == admin_id))
        admin = r.scalar_one_or_none()
        if not admin:
            await call.answer("Не найден", show_alert=True)
            return

        perms = helpers.parse_permissions(admin.permissions)
        perms[key] = not perms.get(key, False)
        admin.permissions = helpers.permissions_to_str(perms)
        await session.commit()
        active = list(k for k, v in perms.items() if v)

    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.admin_permissions_menu(admin_id, active)
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("perm_save_"))
async def perm_save(call: CallbackQuery):
    admin_id = int(call.data.split("_")[2])
    await call.answer("✅ Сохранено", show_alert=True)


@router.callback_query(F.data.startswith("admin_del_") & ~F.data.startswith("admin_del_pay_") & ~F.data.startswith("admin_del_view_") & ~F.data.startswith("admin_del_cancel_") & ~F.data.startswith("admin_deliveries"))
async def admin_del_admin(call: CallbackQuery):
    admin_id = int(call.data.split("_")[2])
    async with async_session() as session:
        r = await session.execute(select(Admin).where(Admin.id == admin_id))
        admin = r.scalar_one_or_none()
        if admin:
            admin.is_active = False
            await session.commit()

    await log_action(f"Админ #{admin_id} удалён")
    await call.answer("🗑 Удалён", show_alert=True)
    await admin_admins(call)


# ═══════════════════════════════════════════
#   ДОСТУП ПО ID
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_access")
async def admin_access(call: CallbackQuery):
    await call.message.edit_text(
        "🔒 <b>Управление доступом</b>\n\nЗаблокируйте или разблокируйте по Telegram ID.",
        reply_markup=kb.admin_access_menu()
    )
    await call.answer()


@router.callback_query(F.data == "admin_block_by_id")
async def block_by_id_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.block_by_id)
    await call.message.edit_text("🚫 Введите Telegram ID:", reply_markup=kb.admin_cancel())
    await call.answer()


@router.message(AdminFSM.block_by_id)
async def block_by_id_apply(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    found = False
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.tg_id == tg_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "blocked"
            found = True

        r = await session.execute(select(Courier).where(Courier.tg_id == tg_id))
        courier = r.scalar_one_or_none()
        if courier:
            courier.is_blocked = True
            courier.status = "blocked"
            found = True

        r = await session.execute(select(Client).where(Client.tg_id == tg_id))
        client = r.scalar_one_or_none()
        if client:
            client.is_blocked = True
            found = True

        await session.commit()

    if found:
        await state.clear()
        await message.answer(f"🚫 Пользователь {tg_id} заблокирован.",
                             reply_markup=kb.admin_main())
        await log_action(f"Заблокирован {tg_id}")
    else:
        await message.answer(
            f"❌ Пользователь {tg_id} не найден.\n\n"
            f"Проверьте, что ID правильный (только цифры)."
        )
        await state.clear()


@router.callback_query(F.data == "admin_unblock_by_id")
async def unblock_by_id_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.unblock_by_id)
    await call.message.edit_text("✅ Введите Telegram ID:", reply_markup=kb.admin_cancel())
    await call.answer()


@router.message(AdminFSM.unblock_by_id)
async def unblock_by_id_apply(message: Message, state: FSMContext):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    found = False
    async with async_session() as session:
        r = await session.execute(select(Shop).where(Shop.tg_id == tg_id))
        shop = r.scalar_one_or_none()
        if shop:
            shop.status = "active"
            found = True

        r = await session.execute(select(Courier).where(Courier.tg_id == tg_id))
        courier = r.scalar_one_or_none()
        if courier:
            courier.is_blocked = False
            courier.status = "active"
            found = True

        r = await session.execute(select(Client).where(Client.tg_id == tg_id))
        client = r.scalar_one_or_none()
        if client:
            client.is_blocked = False
            found = True

        await session.commit()

    if found:
        await state.clear()
        await message.answer(f"✅ Пользователь {tg_id} разблокирован.",
                             reply_markup=kb.admin_main())
        await log_action(f"Разблокирован {tg_id}")
    else:
        await message.answer(f"❌ Пользователь {tg_id} не найден.")


# ═══════════════════════════════════════════
#   ЛОГИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_logs")
async def admin_logs(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Log).order_by(Log.id.desc()).limit(30))
        logs = r.scalars().all()

    if not logs:
        text = "📜 Логи пусты."
    else:
        text = "📜 <b>Последние 30 записей:</b>\n\n"
        for lg in logs:
            text += f"• {helpers.format_dt(lg.created_at)} — {lg.text}\n"

    await call.message.edit_text(text, reply_markup=kb.admin_logs_menu())
    await call.answer()


@router.callback_query(F.data == "admin_logs_clear")
async def admin_logs_clear(call: CallbackQuery):
    async with async_session() as session:
        await session.execute(sa_delete(Log))
        await session.commit()
    await call.answer("🗑 Очищено", show_alert=True)
    await admin_logs(call)
