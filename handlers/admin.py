# -*- coding: utf-8 -*-
"""
SLIPI — бот админа
"""
from datetime import date
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from sqlalchemy import select, update, func

import config
import keyboards as kb
from states import AdminFSM
from database import async_session
from models import (
    Shop, Courier, Order, Payment, Payout, Client, Product,
    Promo, Transaction,
)
from services import orders as orders_service
from services import payments as payments_service
from utils import helpers

router = Router(name="admin")


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

    await show_dashboard(message, edit=False)


async def show_dashboard(message: Message, edit: bool = False):
    async with async_session() as session:
        summary = await payments_service.get_finance_summary(session)

        shops_pending = await session.execute(select(Shop).where(Shop.status == "pending"))
        couriers_pending = await session.execute(select(Courier).where(Courier.status == "pending"))
        payments_pending = await session.execute(select(Payment).where(Payment.status == "pending"))
        payouts_pending = await session.execute(select(Payout).where(Payout.status == "pending"))

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
                await call.bot.send_message(shop.tg_id, "✅ Ваш магазин одобрен! Отправьте /start")
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

    for p in payments[:5]:
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
            f"⚠️ Проверьте комментарий в банке: <b>{p.order_id}</b>"
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
                await call.bot.send_message(
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
                await call.bot.send_message(
                    client.tg_id,
                    f"✅ <b>Оплата заказа #{order.id} подтверждена!</b>\n\n"
                    f"Заказ ушёл магазину 🌸"
                )
            except Exception:
                pass

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
            await call.bot.send_message(
                client.tg_id,
                f"❌ <b>Платёж по заказу #{order_id} не подтверждён.</b>\n\n"
                f"Проверьте, указали ли вы номер заказа в комментарии к переводу.\n"
                f"Или свяжитесь с поддержкой: {config.SUPPORT_TG}"
            )
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

        if p:
            if p.user_type == "courier":
                r = await session.execute(select(Courier).where(Courier.id == p.user_id))
                user = r.scalar_one_or_none()
                if user and user.tg_id:
                    try:
                        await call.bot.send_message(
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
                        await call.bot.send_message(
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


@router.callback_query(F.data == "admin_pay_history")
async def pay_history(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_pay_fast")
async def pay_fast(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_pay_refunds")
async def pay_refunds(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


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
        await call.message.edit_text("✅ Нет зависших заказов.", reply_markup=kb.admin_back())
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

    await state.clear()
    await message.answer(f"✅ Ставка поднята на {amount} ₽.", reply_markup=kb.admin_main())


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
            if p.discount_type == "percent":
                d = f"{int(p.discount_value)}%"
            else:
                d = helpers.money(p.discount_value)
            status = "✅" if p.is_active else "⏸"
            text += f"{status} <code>{p.code}</code> — {d} — {p.used_count}/{p.max_uses or '∞'}\n"

    promos_data = []
    for p in promos[:8]:
        if p.discount_type == "percent":
            d = f"{int(p.discount_value)}%"
        else:
            d = helpers.money(p.discount_value)
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
        result = await session.execute(select(Promo).where(Promo.code == code))
        if result.scalar_one_or_none():
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

    await state.clear()
    if data["discount_type"] == "percent":
        d = f"{int(data['discount_value'])}%"
    else:
        d = helpers.money(data["discount_value"])

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
        result = await session.execute(select(Promo).where(Promo.id == promo_id))
        promo = result.scalar_one_or_none()
        if promo:
            promo.is_active = False
            await session.commit()
    await call.answer("🗑 Промокод отключён", show_alert=True)
    await admin_promos(call)


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
        f"<i>Изменение настроек — в следующих версиях.</i>"
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
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_couriers")
async def admin_couriers_stub(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_complaints")
async def admin_complaints_stub(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_stub(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_analytics")
async def admin_analytics_stub(call: CallbackQuery):
    await call.answer("🚧 Раздел в разработке", show_alert=True)


@router.callback_query(F.data == "admin_req_payouts")
async def req_payouts_stub(call: CallbackQuery):
    await call.answer("Смотрите раздел «Переводы» → «Выплаты»", show_alert=True)
