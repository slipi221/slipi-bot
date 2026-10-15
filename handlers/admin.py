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
    Promo, Log,
)
from services import orders as orders_service
from services import payments as payments_service
from utils import helpers

from bots import bot_client, bot_shop, bot_courier, bot_admin

router = Router(name="admin")


def is_admin(tg_id: int) -> bool:
    return tg_id == config.ADMIN_ID


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
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Доступ запрещён.")
        return
    await show_dashboard(message, edit=False)


async def show_dashboard(message: Message, edit: bool = False):
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
        f"💸 Заявок на выплату: {payouts_count}\n"
        f"💰 Доход платформы: {helpers.money(summary['platform_income'])}"
    )

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb.admin_main())
        except Exception:
            await message.answer(text, reply_markup=kb.admin_main())
    else:
        await message.answer(text, reply_markup=kb.admin_main())


@router.callback_query(F.data == "admin_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await show_dashboard(call.message, edit=True)
    await call.answer()


# ═══════════════════════════════════════════
#   ЗАЯВКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_requests")
async def requests_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
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
            f"📛 {s.name}\n"
            f"📍 {s.address or '—'}\n"
            f"📞 {s.phone or '—'}\n"
            f"👤 {s.owner_name or '—'}"
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
                    await bot_shop.send_message(shop.tg_id, "✅ Ваш магазин одобрен! Отправьте /start")
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
            f"👤 {c.name}\n"
            f"📞 {c.phone or '—'}\n"
            f"🏙 {c.city or '—'}\n"
            f"🚗 {c.transport or '—'}"
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
    if not is_admin(call.from_user.id):
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

    status_map = {"active": "🟢 Активен", "pending": "🟡 На модерации", "blocked": "🔴 Заблокирован"}

    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"{status_map.get(shop.status, shop.status)}\n\n"
        f"👤 Владелец: {shop.owner_name or '—'}\n"
        f"📞 {shop.phone or '—'}\n"
        f"📍 {shop.address or '—'}\n"
        f"⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})\n\n"
        f"📦 Заказов: {len(done_orders)}\n"
        f"💰 Оборот: {helpers.money(turnover)}\n"
        f"🏦 К выплате: {helpers.money(shop.balance)}"
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
                    await bot_shop.send_message(shop.tg_id, "🚫 Ваш магазин заблокирован админом.")
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
        f"📦 Всего: {len(orders)}\n"
        f"✅ Доставлено: {done}\n"
        f"❌ Отменено: {cancel}\n"
        f"⏳ В работе: {wait}\n\n"
        f"💰 Оборот: {helpers.money(total_sum)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_shop_view_{shop_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("admin_shop_msg_"))
async def admin_shop_msg(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data.split("_")[3])
    await state.update_data(msg_target_type="shop", msg_target_id=shop_id)
    await state.set_state(AdminFSM.reply_to_client)
    await call.message.edit_text(
        "✉️ Введите сообщение для магазина:",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   КУРЬЕРЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_couriers")
async def admin_couriers(call: CallbackQuery):
    if not is_admin(call.from_user.id):
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
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "balance": helpers.money(c.balance),
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

    status_map = {"active": "🟢 Активен", "pending": "🟡 На модерации", "blocked": "🔴 Заблокирован"}
    state_map = {"on": "🟢 На смене", "off": "⚪ Не на смене", "break": "☕ Перерыв", "busy": "🚗 На заказе"}

    text = (
        f"🚴 <b>{courier.name}</b>\n"
        f"{status_map.get(courier.status, courier.status)}\n"
        f"{state_map.get(courier.courier_state, '—')}\n\n"
        f"📞 {courier.phone or '—'}\n"
        f"🏙 {courier.city or '—'}\n"
        f"🚗 {courier.transport or '—'}\n"
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
                    await bot_courier.send_message(c.tg_id, "🚫 Доступ закрыт админом.")
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
    earned = sum(
        float(o.delivery_price) * (100 - config.COMMISSION_PERCENT) / 100
        for o in orders if o.status == "done"
    )

    text = (
        f"📊 <b>Статистика курьера</b>\n\n"
        f"📦 Всего: {len(orders)}\n"
        f"✅ Доставлено: {done}\n"
        f"❌ Отменено: {cancel}\n\n"
        f"💰 Заработал: {helpers.money(earned)}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_cour_view_{courier_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("admin_cour_msg_"))
async def admin_cour_msg(call: CallbackQuery, state: FSMContext):
    courier_id = int(call.data.split("_")[3])
    await state.update_data(msg_target_type="courier", msg_target_id=courier_id)
    await state.set_state(AdminFSM.reply_to_client)
    await call.message.edit_text(
        "✉️ Введите сообщение для курьера:",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ОТПРАВКА СООБЩЕНИЯ ОТ АДМИНА
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
#   ПЕРЕВОДЫ — ВХОДЯЩИЕ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_payments")
async def payments_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
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
        await call.message.edit_text("✅ Нет ожидающих платежей.",
                                     reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    for p in payments[:10]:
        async with async_session() as session:
            o_r = await session.execute(select(Order).where(Order.id == p.order_id))
            order = o_r.scalar_one_or_none()
            c_r = await session.execute(select(Client).where(Client.id == p.client_id))
            client = c_r.scalar_one_or_none()

        text = (
            f"💳 <b>Платёж #{p.order_id}</b>\n\n"
            f"👤 Клиент: {client.name if client else '—'}\n"
            f"💰 Сумма: {helpers.money(p.amount)}\n"
            f"🕒 {helpers.format_dt(p.created_at)}\n\n"
            f"⚠️ Комментарий в банке: <b>{p.order_id}</b>"
        )
        await call.message.answer(text, reply_markup=kb.admin_confirm_payment(p.order_id))
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
                    f"🔔 <b>Новый заказ #{order.id}</b>\n"
                    f"📍 {order.address}\n"
                    f"👤 {order.client_name}, {order.client_phone}\n"
                    f"💰 {helpers.money(order.total_price)}"
                )
            except Exception:
                pass

        if client and client.tg_id:
            try:
                await bot_client.send_message(
                    client.tg_id,
                    f"✅ <b>Оплата заказа #{order.id} подтверждена!</b>\n\n"
                    f"Заказ ушёл магазину 🌸"
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
                f"Проверьте, указали ли вы номер заказа в комментарии.\n"
                f"Поддержка: {config.SUPPORT_TG}"
            )
        except Exception:
            pass

    await log_action(f"Платёж #{order_id} отклонён")
    await call.answer()


# ═══════════════════════════════════════════
#   БЫСТРОЕ ПОДТВЕРЖДЕНИЕ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_pay_fast")
async def pay_fast(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        payments = await payments_service.get_pending_payments(session)

    if not payments:
        await call.message.edit_text("✅ Нет платежей для подтверждения.",
                                     reply_markup=kb.admin_payments_menu())
        await call.answer()
        return

    orders = [{"id": p.order_id, "amount": helpers.money(p.amount)} for p in payments[:10]]
    await state.update_data(fast_selected=[])

    await call.message.edit_text(
        f"⚡ <b>Быстрое подтверждение</b>\n\n"
        f"Отметьте поступившие платежи, затем нажмите «Подтвердить выбранные».",
        reply_markup=kb.admin_fast_confirm_menu(orders, [])
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_fast_toggle_"))
async def fast_toggle(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[3])
    data = await state.get_data()
    selected = list(data.get("fast_selected", []))

    if order_id in selected:
        selected.remove(order_id)
    else:
        selected.append(order_id)

    await state.update_data(fast_selected=selected)

    async with async_session() as session:
        payments = await payments_service.get_pending_payments(session)
    orders = [{"id": p.order_id, "amount": helpers.money(p.amount)} for p in payments[:10]]

    try:
        await call.message.edit_reply_markup(reply_markup=kb.admin_fast_confirm_menu(orders, selected))
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "admin_fast_apply")
async def fast_apply(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("fast_selected", [])

    if not selected:
        await call.answer("Ничего не выбрано", show_alert=True)
        return

    confirmed = 0
    for order_id in selected:
        async with async_session() as session:
            order = await orders_service.confirm_payment(session, order_id, call.from_user.id)
            if order:
                confirmed += 1
                async with async_session() as s2:
                    sr = await s2.execute(select(Shop).where(Shop.id == order.shop_id))
                    shop = sr.scalar_one_or_none()
                    cr = await s2.execute(select(Client).where(Client.id == order.client_id))
                    client = cr.scalar_one_or_none()

                if shop and shop.tg_id:
                    try:
                        await bot_shop.send_message(
                            shop.tg_id,
                            f"🔔 <b>Новый заказ #{order.id}</b>\n"
                            f"📍 {order.address}\n"
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

    await state.clear()
    await log_action(f"Быстрое подтверждение: {confirmed} платежей")
    await call.message.edit_text(
        f"✅ Подтверждено платежей: {confirmed}",
        reply_markup=kb.admin_payments_menu()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ПЕРЕВОДЫ — ВЫПЛАТЫ
# ═══════════════════════════════════════════
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
        role_map = {"courier": "🚴 Курьер", "shop": "🏪 Магазин", "client": "👤 Клиент"}
        text = (
            f"💸 <b>Выплата #{p.id}</b>\n\n"
            f"👤 {role_map.get(p.user_type, p.user_type)} — ID {p.user_id}\n"
            f"💰 Сумма: {helpers.money(p.amount)}\n"
            f"🏦 Карта: {helpers.format_card(p.card_number or '—')}"
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
                        await bot_courier.send_message(
                            user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!"
                        )
                    except Exception:
                        pass
            elif p.user_type == "shop":
                r = await session.execute(select(Shop).where(Shop.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try:
                        await bot_shop.send_message(
                            user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!"
                        )
                    except Exception:
                        pass
            elif p.user_type == "client":
                r = await session.execute(select(Client).where(Client.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try:
                        await bot_client.send_message(
                            user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!"
                        )
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


# ═══════════════════════════════════════════
#   ИСТОРИЯ ПЕРЕВОДОВ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_pay_history")
async def pay_history(call: CallbackQuery):
    await call.message.edit_text(
        "📜 <b>История переводов</b>\n\nВыберите тип:",
        reply_markup=kb.admin_pay_history_menu()
    )
    await call.answer()


@router.callback_query(F.data == "admin_hist_in")
async def hist_in(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Payment).order_by(Payment.id.desc()).limit(30))
        payments = r.scalars().all()

    text = "📥 <b>Входящие платежи (30):</b>\n\n"
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

    text = "📤 <b>Исходящие выплаты (30):</b>\n\n"
    for p in payouts:
        emoji = {"pending": "⏳", "processing": "💳", "done": "✅", "rejected": "❌"}.get(p.status, "❓")
        role = {"courier": "🚴", "shop": "🏪", "client": "👤"}.get(p.user_type, "•")
        text += f"{emoji} {role} #{p.id} — {helpers.money(p.amount)} — {helpers.format_dt(p.created_at)}\n"

    if not payouts:
        text = "📤 История пуста."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_pay_history"))
    await call.answer()


# ═══════════════════════════════════════════
#   ВОЗВРАТЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_pay_refunds")
async def pay_refunds(call: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.status == "cancel")
            .order_by(Order.id.desc()).limit(20)
        )
        orders = result.scalars().all()

    if not orders:
        await call.message.edit_text("💸 Нет отменённых заказов.",
                                     reply_markup=kb.admin_back("admin_payments"))
        await call.answer()
        return

    refunds = [{"order_id": o.id, "amount": helpers.money(o.total_price)} for o in orders]
    text = f"💸 <b>Возвраты ({len(refunds)})</b>\n\nВыберите заказ:"
    await call.message.edit_text(text, reply_markup=kb.admin_refunds_list(refunds))
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
        f"👤 Клиент: {client.name if client else '—'}\n"
        f"💰 Сумма: {helpers.money(order.total_price)}\n"
        f"📋 Причина: {order.cancel_reason or '—'}\n"
        f"👤 Отменил: {order.cancelled_by or '—'}\n"
        f"💳 Статус оплаты: {order.payment_status}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_refund_card(order_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_refund_card_"))
async def admin_refund_card(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[3])
    await state.update_data(refund_order_id=order_id)
    await state.set_state(AdminFSM.refund_amount)
    await call.message.edit_text(
        "💳 <b>Возврат на карту</b>\n\n"
        "Введите номер карты клиента (16 цифр):",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.refund_amount)
async def admin_refund_card_process(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты. 16 цифр.")
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

        await payments_service.create_payout(
            session=session,
            user_type="client",
            user_id=order.client_id,
            amount=order.total_price,
            card_number=card,
        )

    await log_action(f"Возврат на карту для заказа #{order_id}")
    await state.clear()
    await message.answer(
        f"✅ <b>Возврат создан</b>\n\n"
        f"💰 {helpers.money(order.total_price)} → карта *{card[-4:]}\n\n"
        f"Переведите вручную, потом подтвердите в «Выплаты».",
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
                    f"💰 <b>Возврат {helpers.money(order.total_price)}</b>\n\n"
                    f"Зачислен на ваш баланс в боте."
                )
            except Exception:
                pass

    await log_action(f"Возврат на баланс для заказа #{order_id}")
    await call.answer("✅ Зачислено на баланс", show_alert=True)
    await pay_refunds(call)


@router.callback_query(F.data.startswith("admin_refund_reject_"))
async def admin_refund_reject(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    await call.answer("❌ Возврат отклонён", show_alert=True)
    await pay_refunds(call)


# ═══════════════════════════════════════════
#   ФИНАНСЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_finance")
async def finance(call: CallbackQuery):
    async with async_session() as session:
        s = await payments_service.get_finance_summary(session)

    text = (
        f"💰 <b>Финансовая сводка</b>\n\n"
        f"📈 Общая касса: {helpers.money(s['total_income'])}\n"
        f"📉 Доход платформы: {helpers.money(s['platform_income'])}\n"
        f"✅ Доставлено: {s['done_orders']} заказов\n\n"
        f"🏪 Магазинам: {helpers.money(s['shops_balance'])}\n"
        f"🚴 Курьерам: {helpers.money(s['couriers_balance'])}\n"
        f"💸 Ожидают выплаты: {helpers.money(s['pending_payouts'])}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back())
    await call.answer()


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
        fee = int(config.get_courier_fee(float(o.delivery_price)) + float(o.boost_amount or 0))
        text = (
            f"⏰ <b>Заказ #{o.id}</b>\n"
            f"🕒 Ждёт: {wait_min} мин\n"
            f"💰 Курьеру: {fee} ₽\n"
            f"📍 {o.address}"
        )
        await call.message.answer(text, reply_markup=kb.admin_stuck_order(o.id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_boost_")
                     & ~F.data.startswith("admin_boost_set_")
                     & ~F.data.startswith("admin_boost_custom"))
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

    await log_action(f"Boost +{amount} ₽ на заказ #{order_id}")
    await call.message.edit_text(f"✅ Ставка поднята на {amount} ₽.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_boost_custom_"))
async def admin_boost_custom(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[3])
    await state.update_data(boost_order_id=order_id)
    await state.set_state(AdminFSM.boost_custom)
    await call.message.edit_text(
        "💰 Введите сумму прибавки (₽):",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.boost_custom)
async def admin_boost_custom_save(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    data = await state.get_data()
    order_id = data.get("boost_order_id")

    async with async_session() as session:
        await session.execute(
            update(Order).where(Order.id == order_id)
            .values(boost_amount=Order.boost_amount + amount)
        )
        await session.commit()

    await log_action(f"Boost +{amount} ₽ на заказ #{order_id}")
    await state.clear()
    await message.answer(f"✅ Ставка поднята на {amount} ₽.", reply_markup=kb.admin_main())


@router.callback_query(F.data.startswith("admin_cancel_order_"))
async def admin_cancel_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await orders_service.cancel_order(
            session, order_id,
            reason="admin_cancelled",
            cancelled_by="admin",
            refund=True,
        )
    await log_action(f"Заказ #{order_id} отменён админом")
    await call.answer("❌ Заказ отменён", show_alert=True)
    await stuck_orders(call)


# ═══════════════════════════════════════════
#   ПРОМОКОДЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_promos")
async def admin_promos(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(Promo).order_by(Promo.id.desc()).limit(20))
        promos = result.scalars().all()

    if not promos:
        text = "🎁 <b>Промокоды</b>\n\nПока нет ни одного промокода."
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
        "🎁 <b>Создание промокода</b>\n\n"
        "Шаг 1/4: Введите код (латиницей, заглавными)\n\n"
        "<i>Например: SUMMER20</i>",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.promo_code)
async def promo_set_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code.isalnum():
        await message.answer("❌ Только буквы и цифры, без пробелов.")
        return

    async with async_session() as session:
        r = await session.execute(select(Promo).where(Promo.code == code))
        if r.scalar_one_or_none():
            await message.answer("❌ Такой код уже существует.")
            return

    await state.update_data(promo_code=code)
    await state.set_state(AdminFSM.promo_type)
    await message.answer("🎁 Шаг 2/4: Тип скидки:", reply_markup=kb.admin_promo_type())


@router.callback_query(F.data.startswith("promo_type_"), AdminFSM.promo_type)
async def promo_set_type(call: CallbackQuery, state: FSMContext):
    d_type = call.data.replace("promo_type_", "")
    await state.update_data(discount_type=d_type)
    await state.set_state(AdminFSM.promo_value)

    hint = "Введите процент скидки (1–100):" if d_type == "percent" else "Введите сумму скидки в рублях:"
    await call.message.edit_text(f"🎁 Шаг 3/4: {hint}", reply_markup=kb.admin_cancel())
    await call.answer()


@router.message(AdminFSM.promo_value)
async def promo_set_value(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(",", ".").strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    await state.update_data(discount_value=value)
    await state.set_state(AdminFSM.promo_uses)
    await message.answer(
        "🎁 Шаг 4/4: Лимит использований\n\n"
        "Введите число или <code>0</code> — безлимит.",
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
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎁 <code>{data['promo_code']}</code>\n"
        f"📊 Скидка: {d}\n"
        f"🔢 Лимит: {max_uses or '∞'}",
        reply_markup=kb.admin_main()
    )


@router.callback_query(F.data.startswith("admin_promo_view_"))
async def promo_view(call: CallbackQuery):
    promo_id = int(call.data.split("_")[3])
    await call.message.edit_text(
        f"🎁 Промокод #{promo_id}",
        reply_markup=kb.admin_promo_view(promo_id)
    )
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
    await call.answer("🗑 Промокод отключён", show_alert=True)
    await admin_promos(call)


# ═══════════════════════════════════════════
#   ЖАЛОБЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_complaints")
async def admin_complaints(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(
            select(Order).where(Order.status == "problem")
            .order_by(Order.id.desc()).limit(20)
        )
        orders = r.scalars().all()

    if not orders:
        await call.message.edit_text("✅ Жалоб нет.", reply_markup=kb.admin_back())
        await call.answer()
        return

    complaints = [{"order_id": o.id, "type": o.cancel_reason or "жалоба"} for o in orders]
    text = f"🆘 <b>Жалобы ({len(complaints)})</b>\n\nВыберите:"
    await call.message.edit_text(text, reply_markup=kb.admin_complaints_list(complaints))
    await call.answer()


@router.callback_query(F.data.startswith("admin_complaint_view_"))
async def admin_complaint_view(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()
        if not order:
            await call.answer("Не найден", show_alert=True)
            return

    text = (
        f"🆘 <b>Жалоба по заказу #{order.id}</b>\n\n"
        f"👤 {order.client_name}, {order.client_phone}\n"
        f"📍 {order.address}\n"
        f"💰 {helpers.money(order.total_price)}\n"
        f"📋 {order.cancel_reason or '—'}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_complaint_card(order_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_comp_full_"))
async def admin_comp_full(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()
        if order:
            await payments_service.refund_to_balance(session, order.client_id, order.total_price, order_id)
            order.status = "cancel"
            await session.commit()

            c_r = await session.execute(select(Client).where(Client.id == order.client_id))
            client = c_r.scalar_one_or_none()
            if client and client.tg_id:
                try:
                    await bot_client.send_message(
                        client.tg_id,
                        f"💰 <b>Возврат {helpers.money(order.total_price)}</b>\n\n"
                        f"Жалоба одобрена. Деньги на вашем балансе в боте."
                    )
                except Exception:
                    pass

    await log_action(f"Жалоба #{order_id} одобрена, полный возврат")
    await call.answer("✅ Полный возврат сделан", show_alert=True)
    await admin_complaints(call)


@router.callback_query(F.data.startswith("admin_comp_reject_"))
async def admin_comp_reject(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()
        if order:
            order.status = "done"
            await session.commit()
    await log_action(f"Жалоба #{order_id} отклонена")
    await call.answer("❌ Жалоба отклонена", show_alert=True)
    await admin_complaints(call)


@router.callback_query(F.data.startswith("admin_comp_details_"))
async def admin_comp_details(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Order).where(Order.id == order_id))
        order = r.scalar_one_or_none()

    text = (
        f"📊 <b>Заказ #{order_id}</b>\n\n"
        f"Статус: {helpers.status_text(order.status) if order else '—'}\n"
        f"Оплата: {order.payment_status if order else '—'}\n"
        f"Создан: {helpers.format_dt(order.created_at) if order else '—'}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back(f"admin_complaint_view_{order_id}"))
    await call.answer()


# ═══════════════════════════════════════════
#   РАССЫЛКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery):
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nКому отправить?",
        reply_markup=kb.admin_broadcast_menu()
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_bc_") & ~F.data.startswith("admin_bc_send"))
async def admin_bc_start(call: CallbackQuery, state: FSMContext):
    target = call.data.replace("admin_bc_", "")
    await state.update_data(bc_target=target)
    await state.set_state(AdminFSM.broadcast_text)
    await call.message.edit_text(
        "📝 Введите текст рассылки:",
        reply_markup=kb.admin_cancel()
    )
    await call.answer()


@router.message(AdminFSM.broadcast_text)
async def admin_bc_text(message: Message, state: FSMContext):
    await state.update_data(bc_text=message.text)
    data = await state.get_data()

    target_map = {
        "clients": "👥 Клиентам",
        "couriers": "🚴 Курьерам",
        "shops": "🏪 Магазинам",
    }
    target = target_map.get(data.get("bc_target"), "?")

    await state.set_state(AdminFSM.broadcast_confirm)
    await message.answer(
        f"👁 <b>Проверьте рассылку</b>\n\n"
        f"Кому: {target}\n\n"
        f"Текст:\n{data['bc_text']}",
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
            r = await session.execute(select(Client).where(Client.tg_id.isnot(None)))
            ids = [u.tg_id for u in r.scalars().all()]
            bot = bot_client
        elif target == "couriers":
            r = await session.execute(select(Courier).where(Courier.tg_id.isnot(None)))
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

    await log_action(f"Рассылка ({target}): {sent} отправлено")
    await state.clear()
    await call.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=kb.admin_main()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   АНАЛИТИКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_analytics")
async def admin_analytics(call: CallbackQuery):
    await call.message.edit_text(
        "📊 <b>Аналитика</b>\n\nВыберите период:",
        reply_markup=kb.admin_analytics_menu()
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_analytics_"))
async def admin_analytics_period(call: CallbackQuery):
    period = call.data.replace("admin_analytics_", "")

    now = datetime.now()
    if period == "week":
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
    in_work = sum(1 for o in orders if o.status in ("pending", "wait", "going", "picked", "delivering", "at_client"))
    turnover = sum(float(o.total_price) for o in orders if o.status == "done")
    platform = sum(float(o.platform_income) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Аналитика — {label}</b>\n\n"
        f"📦 Заказов: {total}\n"
        f"✅ Доставлено: {done}\n"
        f"❌ Отменено: {cancel}\n"
        f"⏳ В работе: {in_work}\n\n"
        f"💰 Оборот: {helpers.money(turnover)}\n"
        f"📈 Доход платформы: {helpers.money(platform)}"
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
        text += f"{i}. {s.name} — {s.total_orders} заказов — ⭐ {float(s.rating or 0):.1f}\n"

    if not shops:
        text = "🏆 Пока нет данных."

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
        text += f"{i}. {c.name} — {c.total_orders} заказов — ⭐ {float(c.rating or 0):.1f}\n"

    if not couriers:
        text = "🏆 Пока нет данных."

    await call.message.edit_text(text, reply_markup=kb.admin_back("admin_analytics"))
    await call.answer()


# ═══════════════════════════════════════════
#   НАСТРОЙКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_settings")
async def admin_settings(call: CallbackQuery):
    text = (
        f"⚙️ <b>Настройки системы</b>\n\n"
        f"💸 Комиссия с доставки: {config.COMMISSION_PERCENT}%\n"
        f"💰 Мин. вывод курьера: {config.COURIER_MIN_WITHDRAW} ₽\n"
        f"🎁 Бонус за 10 заказов: {config.BONUS_PER_10_ORDERS} ₽\n"
        f"🚚 Доставка: {config.DELIVERY_PRICE} ₽\n"
        f"🕒 Часы работы: {config.WORK_HOURS}\n"
        f"🏙 Город: {config.CITY}\n\n"
        f"<i>Пока значения из config.py. Скоро — редактирование в боте.</i>"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_settings_menu())
    await call.answer()


@router.callback_query(F.data == "admin_multicity")
async def multicity_stub(call: CallbackQuery):
    await call.message.edit_text(
        "🌍 <b>Мультигород</b>\n\n"
        "🚧 Раздел в разработке.\n\n"
        "Планируем добавить в следующих версиях:\n"
        "• Один бот на несколько городов\n"
        "• Клиент выбирает свой город\n"
        "• Отдельные магазины и курьеры по городам",
        reply_markup=kb.admin_back("admin_settings")
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ЛОГИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_logs")
async def admin_logs(call: CallbackQuery):
    async with async_session() as session:
        r = await session.execute(select(Log).order_by(Log.id.desc()).limit(30))
        logs = r.scalars().all()

    if not logs:
        text = "📜 <b>Логи</b>\n\nПока пусто."
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
    await call.answer("🗑 Логи очищены", show_alert=True)
    await admin_logs(call)
