# -*- coding: utf-8 -*-
"""
SLIPI — бот админа
"""
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from sqlalchemy import select, update

import config
import keyboards as kb
from states import AdminFSM
from database import async_session
from models import (
    Shop, Courier, Order, Payment, Payout, Client, Product,
)
from services import orders as orders_service
from services import payments as payments_service
from utils import helpers

router = Router(name="admin")


# ═══════════════════════════════════════════
#   ПРОВЕРКА АДМИНА
# ═══════════════════════════════════════════
def is_admin(tg_id: int) -> bool:
    return tg_id == config.ADMIN_ID


# ═══════════════════════════════════════════
#   /start
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Доступ запрещён.")
        return

    async with async_session() as session:
        summary = await payments_service.get_finance_summary(session)

        # Считаем заявки
        shops_pending = await session.execute(
            select(Shop).where(Shop.status == "pending")
        )
        couriers_pending = await session.execute(
            select(Courier).where(Courier.status == "pending")
        )
        payments_pending = await session.execute(
            select(Payment).where(Payment.status == "pending")
        )
        payouts_pending = await session.execute(
            select(Payout).where(Payout.status == "pending")
        )

        shops_count = len(shops_pending.scalars().all())
        couriers_count = len(couriers_pending.scalars().all())
        payments_count = len(payments_pending.scalars().all())
        payouts_count = len(payouts_pending.scalars().all())

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
    await message.answer(text, reply_markup=kb.admin_main())


@router.callback_query(F.data == "admin_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        summary = await payments_service.get_finance_summary(session)
        in_work = await payments_service.get_orders_in_work(session)

    text = (
        f"👑 <b>Админ-панель {config.SERVICE_NAME}</b>\n\n"
        f"🚗 В работе: {in_work}\n"
        f"💰 Доход платформы: {helpers.money(summary['platform_income'])}"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_main())
    await call.answer()


# ═══════════════════════════════════════════
#   ЗАЯВКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_requests")
async def requests_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "📨 <b>Заявки</b>",
        reply_markup=kb.admin_requests_menu()
    )
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

    for s in shops[:5]:
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
            try:
                await call.bot.send_message(
                    shop.tg_id,
                    "✅ Ваш магазин одобрен! Отправьте /start"
                )
            except Exception:
                pass
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
            try:
                await call.bot.send_message(shop.tg_id, "❌ Ваш магазин отклонён.")
            except Exception:
                pass
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

    for c in couriers[:5]:
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
            await session.commit()
            try:
                await call.bot.send_message(c.tg_id, "✅ Вы одобрены! Отправьте /start")
            except Exception:
                pass
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
            await session.commit()
            try:
                await call.bot.send_message(c.tg_id, "❌ Заявка отклонена.")
            except Exception:
                pass
    await call.message.edit_text(f"❌ Курьер #{courier_id} отклонён.")
    await call.answer()


# ═══════════════════════════════════════════
#   ПЕРЕВОДЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_payments")
async def payments_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "💳 <b>Переводы и платежи</b>",
        reply_markup=kb.admin_payments_menu()
    )
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

    for p in payments[:5]:
        async with async_session() as session:
            o_r = await session.execute(select(Order).where(Order.id == p.order_id))
            order = o_r.scalar_one_or_none()
            c_r = await session.execute(select(Client).where(Client.id == p.client_id))
            client = c_r.scalar_one_or_none()

        text = (
            f"💳 <b>Платёж #{p.order_id}</b>\n\n"
            f"👤 Клиент: {client.name if client else '—'} (tg {client.tg_id if client else '—'})\n"
            f"💰 Сумма: {helpers.money(p.amount)}\n"
            f"🕒 Создан: {helpers.format_dt(p.created_at)}"
        )
        await call.message.answer(text, reply_markup=kb.admin_confirm_payment(p.order_id))
    await call.answer()


@router.callback_query(F.data.startswith("admin_pay_ok_"))
async def pay_ok(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        order = await orders_service.confirm_payment(session, order_id, call.from_user.id)

    await call.message.edit_text(f"✅ Оплата #{order_id} подтверждена.")
    # Уведомляем магазин
    if order:
        try:
            s_r_shop = None
            async with async_session() as s2:
                sr = await s2.execute(select(Shop).where(Shop.id == order.shop_id))
                shop = sr.scalar_one_or_none()
                if shop and shop.tg_id:
                    await call.bot.send_message(
                        shop.tg_id,
                        f"🔔 <b>Новый заказ #{order.id}</b>\n"
                        f"📍 {order.address}\n"
                        f"👤 {order.client_name}\n"
                        f"💰 {helpers.money(order.total_price)}"
                    )
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data.startswith("admin_pay_no_"))
async def pay_no(call: CallbackQuery):
    order_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await payments_service.mark_payment_rejected(session, order_id, call.from_user.id)
        await orders_service.cancel_order(session, order_id, reason="payment_rejected", cancelled_by="admin")

    await call.message.edit_text(f"❌ Платёж #{order_id} отклонён.")
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

    for p in payouts[:5]:
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
    await call.message.edit_text(f"💳 Выплата #{payout_id} отмечена как отправленная.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_payout_ok_"))
async def payout_ok(call: CallbackQuery):
    payout_id = int(call.data.split("_")[3])
    async with async_session() as session:
        p = await payments_service.mark_payout_done(session, payout_id, call.from_user.id)

        # Уведомляем получателя
        if p:
            try:
                if p.user_type == "courier":
                    r = await session.execute(select(Courier).where(Courier.id == p.user_id))
                    user = r.scalar_one_or_none()
                    if user and user.tg_id:
                        await call.bot.send_message(
                            user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!"
                        )
                elif p.user_type == "shop":
                    r = await session.execute(select(Shop).where(Shop.id == p.user_id))
                    user = r.scalar_one_or_none()
                    if user and user.tg_id:
                        await call.bot.send_message(
                            user.tg_id,
                            f"✅ Выплата {helpers.money(p.amount_to_pay)} зачислена!"
                        )
            except Exception:
                pass

    await call.message.edit_text(f"✅ Выплата #{payout_id} подтверждена.")
    await call.answer()


@router.callback_query(F.data.startswith("admin_payout_no_"))
async def payout_no(call: CallbackQuery):
    payout_id = int(call.data.split("_")[3])
    async with async_session() as session:
        await payments_service.mark_payout_rejected(session, payout_id, call.from_user.id)
    await call.message.edit_text(f"❌ Выплата #{payout_id} отклонена.")
    await call.answer()


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

    stuck = [o for o in orders if o.wait_started_at and
             (helpers.now() - o.wait_started_at).total_seconds() > 30 * 60]

    if not stuck:
        await call.message.edit_text("✅ Нет зависших заказов.",
                                     reply_markup=kb.admin_back())
        await call.answer()
        return

    for o in stuck[:5]:
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


@router.callback_query(F.data.startswith("admin_boost_"))
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
            .values(boost_amount=Order.boost_amount + amount, boost_by_admin=True)
        )
        await session.commit()

    await call.message.edit_text(f"✅ Ставка поднята на {amount} ₽.")
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
        f"<i>Изменение настроек — в следующей версии.</i>"
    )
    await call.message.edit_text(text, reply_markup=kb.admin_back())
    await call.answer()


# ═══════════════════════════════════════════
#   ЛОГИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_logs")
async def admin_logs(call: CallbackQuery):
    await call.message.edit_text(
        "📜 <b>Логи</b>\n\nЗдесь будут последние действия.",
        reply_markup=kb.admin_back()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   ЗАГЛУШКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "admin_shops")
async def admin_shops_stub(call: CallbackQuery):
    await call.answer("Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_couriers")
async def admin_couriers_stub(call: CallbackQuery):
    await call.answer("Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_promos")
async def admin_promos_stub(call: CallbackQuery):
    await call.answer("Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_complaints")
async def admin_complaints_stub(call: CallbackQuery):
    await call.answer("Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_stub(call: CallbackQuery):
    await call.answer("Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_analytics")
async def admin_analytics_stub(call: CallbackQuery):
    await call.answer("Раздел в разработке", show_alert=True)
