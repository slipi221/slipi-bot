# -*- coding: utf-8 -*-
"""
Flowers Express — точка входа, запуск всех ботов и планировщика

FIX bug8: urgent_orders_job — 0 < minutes_left <= 30 (не бустить мёртвые).
FIX bug1: все datetime — через helpers.now_moscow() (naive MSK).
FIX spam1: photo_reminder_job — photo_requested_at (раз в 30 мин).
FIX spam2: delivery_reminder_job — шлёт админу (не магазину).
NEW Feature 1: LogMiddleware на 4 диспетчера (4 канала, rate-limit).
NEW Feature 14: courier_reminder_1h_job, courier_going_reminder_job, courier_auto_return_job.
NEW: seed_achievements + load_config_from_db при старте.
NEW: graceful shutdown.
"""
import asyncio
import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, TelegramObject,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update

import config
from database import init_db, load_config_from_db, async_session, engine
from models import (
    Order, ClientEvent, Courier, Client, Shop, Product,
    DeliveryOrder, DeliveryPayment, CourierDailyStat, ShopSubscription,
)
from handlers import client as client_h
from handlers import shop as shop_h
from handlers import courier as courier_h
from handlers import admin as admin_h
from services import bonuses as bonuses_service
from services import orders as orders_service
from services import notify
from utils import helpers

from bots import bot_client, bot_shop, bot_courier, bot_admin


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("flowers_express")


# ═══════════════════════════════════════════
#   ДИСПЕТЧЕРЫ И РОУТЕРЫ
# ═══════════════════════════════════════════
dp_client = Dispatcher()
dp_shop = Dispatcher()
dp_courier = Dispatcher()
dp_admin = Dispatcher()

dp_client.include_router(client_h.router)
dp_shop.include_router(shop_h.router)
dp_courier.include_router(courier_h.router)
dp_admin.include_router(admin_h.router)


# ═══════════════════════════════════════════
#   FEATURE 1: MIDDLEWARE ЛОГГЕРА В КАНАЛ
# ═══════════════════════════════════════════
class LogMiddleware(BaseMiddleware):
    """
    Логирует действия пользователя в канал роли (Feature 1).
    Rate-limit: не более 15 сообщений/мин от одного пользователя.
    Не блокирует обработку (asyncio.create_task).
    """

    def __init__(self, role: str):
        self.role = role
        self._counter: dict[tuple[int, str], int] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            user_id = None
            action = None

            if isinstance(event, CallbackQuery):
                user_id = event.from_user.id
                action = f"callback: {event.data}"
            elif isinstance(event, Message):
                user_id = event.from_user.id
                if event.text:
                    action = f"msg: {event.text[:60]}"
                elif event.photo:
                    action = "msg: [photo]"
                elif event.location:
                    action = "msg: [location]"
                elif event.document:
                    action = "msg: [doc]"
                else:
                    action = "msg: [?]"

            if user_id and action:
                now = datetime.now()
                minute_key = now.strftime("%Y%m%d%H%M")
                key = (user_id, minute_key)
                self._counter[key] = self._counter.get(key, 0) + 1

                # чистка старых ключей
                if len(self._counter) > 500:
                    cutoff = (now - timedelta(minutes=2)).strftime("%Y%m%d%H%M")
                    self._counter = {k: v for k, v in self._counter.items() if k[1] >= cutoff}

                if self._counter[key] <= 15:
                    asyncio.create_task(notify.log_action_to_channel(self.role, user_id, action))
        except Exception as e:
            log.debug(f"LogMiddleware: {e}")

        return await handler(event, data)


dp_client.message.middleware(LogMiddleware("client"))
dp_client.callback_query.middleware(LogMiddleware("client"))
dp_shop.message.middleware(LogMiddleware("shop"))
dp_shop.callback_query.middleware(LogMiddleware("shop"))
dp_courier.message.middleware(LogMiddleware("courier"))
dp_courier.callback_query.middleware(LogMiddleware("courier"))
dp_admin.message.middleware(LogMiddleware("admin"))
dp_admin.callback_query.middleware(LogMiddleware("admin"))


# ═══════════════════════════════════════════
#   ВСПОМОГАТЕЛЬНЫЕ
# ═══════════════════════════════════════════
def _parse_slot_end(delivery_date: date, delivery_slot: str) -> datetime | None:
    """
    Возвращает datetime конца слота (naive MSK).
    delivery_slot: "HH:MM-HH:MM". Если конец "00:00" — это конец дня (завтра 00:00).
    """
    try:
        end_str = delivery_slot.split("-")[1]
        h, m = map(int, end_str.split(":"))
        if h == 0 and m == 0:
            return datetime.combine(delivery_date + timedelta(days=1), datetime.min.time())
        return datetime.combine(delivery_date, datetime.min.time()).replace(hour=h, minute=m)
    except Exception:
        return None


# ═══════════════════════════════════════════
#   1. ЕЖЕДНЕВНЫЕ БОНУСЫ
# ═══════════════════════════════════════════
async def daily_bonus_job():
    """23:59 — за сегодня."""
    log.info("⏰ Бонусы (сегодня)")
    try:
        async with async_session() as session:
            await bonuses_service.apply_all_daily_bonuses(session)
        log.info("✅ Бонусы начислены (сегодня)")
    except Exception as e:
        log.exception(f"Ошибка бонусов: {e}")


async def daily_bonus_job_yesterday():
    """00:05 — за вчера (для тех, кто доделал заказы в 23:59:30)."""
    log.info("⏰ Бонусы (вчера)")
    try:
        yesterday = helpers.today_moscow() - timedelta(days=1)
        async with async_session() as session:
            await bonuses_service.apply_all_daily_bonuses(session, for_date=yesterday)
        log.info("✅ Бонусы начислены (вчера)")
    except Exception as e:
        log.exception(f"Ошибка бонусов (вчера): {e}")


# ═══════════════════════════════════════════
#   2. АВТООТМЕНА ЗАКАЗОВ (магазин не ответил)
# ═══════════════════════════════════════════
async def auto_cancel_job():
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.status == "new",
                    Order.payment_status == "confirmed",
                )
            )
            orders = result.scalars().all()

            now = helpers.now_moscow()
            for o in orders:
                if not o.wait_started_at:
                    continue
                elapsed = (now - o.wait_started_at).total_seconds() / 60

                if 8 <= now.hour < 23:
                    if elapsed >= config.DAY_ORDER_TIMEOUT_MINUTES:
                        # bug9: cancelled_by="auto" — штраф НЕ начисляем
                        await orders_service.cancel_order(
                            session, o.id,
                            reason="shop_no_response", cancelled_by="auto", refund=True,
                        )
                        log.info(f"Автоотмена магазином #{o.id}")

                        c_r = await session.execute(select(Client).where(Client.id == o.client_id))
                        client = c_r.scalar_one_or_none()
                        if client and client.tg_id:
                            try:
                                await bot_client.send_message(
                                    client.tg_id,
                                    f"😔 Заказ #{o.id} отменён.\n\nМагазин не ответил. Деньги вернулись на баланс.",
                                )
                            except Exception:
                                pass
    except Exception as e:
        log.exception(f"Ошибка автоотмены: {e}")


# ═══════════════════════════════════════════
#   3. СОБЫТИЯ КЛИЕНТА (10:00)
# ═══════════════════════════════════════════
async def events_reminder_job():
    log.info("📅 События")
    try:
        async with async_session() as session:
            today = helpers.today_moscow()

            for days, flag_field in [(3, "notified_3d"), (1, "notified_1d")]:
                target = today + timedelta(days=days)
                result = await session.execute(
                    select(ClientEvent).where(
                        ClientEvent.event_date == target,
                        getattr(ClientEvent, flag_field) == False,
                    )
                )
                for e in result.scalars().all():
                    c_r = await session.execute(select(Client).where(Client.id == e.client_id))
                    client = c_r.scalar_one_or_none()
                    if client and client.tg_id:
                        try:
                            emoji = "🔔" if days == 3 else "⏰"
                            text = f"{emoji} <b>Напоминание!</b>\n\n"
                            if days == 3:
                                text += f"Через 3 дня — <b>{e.title}</b> ({helpers.format_date(e.event_date)}).\n\nУспейте заказать букет 🌸"
                            else:
                                text += f"Завтра — <b>{e.title}</b>!\n\nПоследний шанс заказать букет."
                            await bot_client.send_message(client.tg_id, text)
                            setattr(e, flag_field, True)
                        except Exception:
                            pass

            await session.commit()
    except Exception as e:
        log.exception(f"Ошибка событий: {e}")


# ═══════════════════════════════════════════
#   4. ФОТО-НАПОМИНАНИЯ (каждые 15 мин)
# ═══════════════════════════════════════════
async def photo_reminder_job():
    """
    FIX spam1: напоминание курьеру не чаще раза в 30 минут (photo_requested_at).
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.status == "at_client",
                    Order.delivery_photo_id.is_(None),
                    Order.need_delivery_photo == True,
                )
            )
            orders = result.scalars().all()
            now = helpers.now_moscow()

            for o in orders:
                if not o.courier_id:
                    continue
                # FIX: проверяем, что не напоминали за последние 30 минут
                if o.photo_requested_at:
                    elapsed_min = (now - o.photo_requested_at).total_seconds() / 60
                    if elapsed_min < 30:
                        continue

                c_r = await session.execute(select(Courier).where(Courier.id == o.courier_id))
                courier = c_r.scalar_one_or_none()
                if courier and courier.tg_id:
                    try:
                        await bot_courier.send_message(courier.tg_id, f"⏰ <b>Заказ #{o.id} ждёт фото!</b>")
                        o.photo_requested_at = now
                    except Exception:
                        pass

            await session.commit()
    except Exception as e:
        log.exception(f"Ошибка фото: {e}")


# ═══════════════════════════════════════════
#   5. АВТООТМЕНА ДОСТАВОК (каждые 10 мин)
# ═══════════════════════════════════════════
async def delivery_autocancel_job():
    try:
        async with async_session() as session:
            result = await session.execute(
                select(DeliveryOrder).where(
                    DeliveryOrder.status == "pending",
                    DeliveryOrder.payment_status == "pending",
                )
            )
            for d in result.scalars().all():
                if not d.created_at:
                    continue
                elapsed_min = (helpers.now_moscow() - d.created_at).total_seconds() / 60
                if elapsed_min >= 120:
                    d.status = "cancel"
                    d.cancel_reason = "auto_no_payment"
                    await session.commit()

                    s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
                    shop = s_r.scalar_one_or_none()
                    if shop and shop.tg_id:
                        try:
                            await bot_shop.send_message(
                                shop.tg_id,
                                f"⏰ <b>Доставка #Д-{d.id} автоотменена</b>\n\nОплата не поступила за 2 часа.",
                            )
                        except Exception:
                            pass
    except Exception as e:
        log.exception(f"Ошибка автоотмены доставок: {e}")


# ═══════════════════════════════════════════
#   6. НАПОМИНАНИЕ О ДОСТАВКАХ — АДМИНУ (не магазину!)
# ═══════════════════════════════════════════
_reminded_deliveries: dict[int, datetime] = {}


async def delivery_reminder_job():
    """
    FIX spam2: шлёт АДМИНУ (не магазину) — «доставка ждёт подтверждения».
    Не чаще раза в 60 минут на одну доставку.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(DeliveryOrder).where(DeliveryOrder.status == "paid")
            )
            deliveries = result.scalars().all()
            now = helpers.now_moscow()

            for d in deliveries:
                last = _reminded_deliveries.get(d.id)
                if last and (now - last).total_seconds() / 60 < 60:
                    continue

                if not config.ADMIN_ID:
                    continue
                try:
                    await bot_admin.send_message(
                        config.ADMIN_ID,
                        f"⏳ <b>Доставка #Д-{d.id} ждёт подтверждения оплаты</b>\n\n"
                        f"🏪 Магазин: #{d.shop_id}\n💰 {helpers.money(d.client_pays)}",
                    )
                    _reminded_deliveries[d.id] = now
                except Exception:
                    pass
    except Exception as e:
        log.exception(f"Ошибка напоминаний доставок: {e}")


# ═══════════════════════════════════════════
#   7. ГОРЯЩИЕ ЗАКАЗЫ + БУСТ (каждые 5 мин)
# ═══════════════════════════════════════════
async def urgent_orders_job():
    log.info("🔥 Горящие заказы")
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.status == "wait",
                    Order.is_urgent_notified == False,
                    Order.courier_id.is_(None),
                    Order.delivery_date == helpers.today_moscow(),
                )
            )
            orders = result.scalars().all()
            if not orders:
                return

            now = helpers.now_moscow()
            for o in orders:
                if not o.delivery_slot:
                    continue
                try:
                    end_str = o.delivery_slot.split("-")[1]
                    h, m = map(int, end_str.split(":"))
                    slot_end = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if h == 0 and m == 0:
                        slot_end += timedelta(days=1)
                    minutes_left = (slot_end - now).total_seconds() / 60

                    # FIX bug8: 0 < minutes_left <= 30 (не бустить мёртвые заказы)
                    if not (0 < minutes_left <= config.BOOST_TRIGGER_MINUTES):
                        continue

                    # 1. Начисляем буст
                    o.boost_amount = Decimal(str(o.boost_amount or 0)) + Decimal(str(config.URGENT_BONUS))
                    o.is_urgent_notified = True

                    # 2. Курьеры на смене (TG или VK, не на паузе)
                    c_result = await session.execute(
                        select(Courier).where(
                            Courier.status == "active",
                            Courier.is_blocked == False,
                            Courier.is_paused_geo == False,
                            (Courier.tg_id.isnot(None)) | (Courier.vk_id.isnot(None)),
                        )
                    )
                    couriers = c_result.scalars().all()

                    # 3. Коммит ДО рассылки (чтобы флаг сохранился), но после подготовки
                    await session.commit()

                    # 4. Рассылка
                    text = (
                        f"🚨 <b>СРОЧНЫЙ ЗАКАЗ #{o.id}!</b>\n\n"
                        f"⏰ Осталось <b>{int(minutes_left)} мин</b> до конца слота!\n"
                        f"💰 Ставка: <b>{helpers.money(o.courier_fee)} + {config.URGENT_BONUS}₽ буст</b>\n"
                        f"📍 {helpers.escape(o.address)}\n\n"
                        f"<i>Если вы готовы помочь — выйдите на смену и заберите заказ!</i>"
                    )
                    for c in couriers:
                        try:
                            on_shift = c.courier_state in ("on", "busy")
                            kb_rows = []
                            if not on_shift:
                                kb_rows.append([InlineKeyboardButton(text="🟢 Выйти на смену", callback_data="courier_on_shift")])
                            else:
                                kb_rows.append([InlineKeyboardButton(text="📦 Взять заказ", callback_data=f"courier_take_{o.id}")])

                            await bot_courier.send_message(
                                c.tg_id, text,
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
                            )
                        except Exception:
                            pass
                    log.info(f"🚨 Пуш по горящему заказу #{o.id} разослан {len(couriers)} курьерам")
                except Exception as e:
                    log.error(f"Ошибка в urgent_orders_job для #{o.id}: {e}")
    except Exception as e:
        log.exception(f"Ошибка urgent_orders_job: {e}")


# ═══════════════════════════════════════════
#   8. FEATURE 14: НАПОМИНАНИЯ КУРЬЕРУ
# ═══════════════════════════════════════════
_reminded_1h: dict[int, datetime] = {}
_reminded_30m: dict[int, datetime] = {}


async def courier_timeout_job():
    """
    Feature 14:
    - За 1 час до слота: напоминание курьеру, если status="going".
    - За 30 минут до слота: напоминание + кнопка «Я в пути».
    - За 15 минут до слота (если status всё ещё "going"): заказ возвращается в пул.
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.status == "going",
                    Order.courier_id.isnot(None),
                )
            )
            orders = result.scalars().all()
            now = helpers.now_moscow()

            for o in orders:
                if not o.delivery_slot:
                    continue
                slot_end = _parse_slot_end(o.delivery_date, o.delivery_slot)
                if not slot_end:
                    continue
                minutes_left = (slot_end - now).total_seconds() / 60

                c_r = await session.execute(select(Courier).where(Courier.id == o.courier_id))
                courier = c_r.scalar_one_or_none()
                if not courier or not courier.tg_id:
                    continue

                # За 60 мин — напоминание
                if 55 <= minutes_left <= 65:
                    last = _reminded_1h.get(o.id)
                    if not last or (now - last).total_seconds() / 60 > 30:
                        try:
                            await bot_courier.send_message(
                                courier.tg_id,
                                f"⏰ <b>Заказ #{o.id}</b>\n\n"
                                f"Через час нужно доставить. Слот: {o.delivery_slot}\n"
                                f"📍 {helpers.escape(o.address)}\n\n"
                                f"Не забудьте забрать букет из магазина!",
                            )
                            _reminded_1h[o.id] = now
                        except Exception:
                            pass

                # За 30 мин — кнопка «Я в пути»
                elif 25 <= minutes_left < 55:
                    last = _reminded_30m.get(o.id)
                    if not last or (now - last).total_seconds() / 60 > 20:
                        try:
                            kb_rows = [
                                [InlineKeyboardButton(text="🚗 Я в пути", callback_data=f"courier_going_{o.id}")],
                                [InlineKeyboardButton(text="📦 Забрал", callback_data=f"courier_picked_{o.id}")],
                            ]
                            await bot_courier.send_message(
                                courier.tg_id,
                                f"⚡ <b>Заказ #{o.id} — 30 минут до слота!</b>\n\n"
                                f"Слот: {o.delivery_slot}\n"
                                f"📍 {helpers.escape(o.address)}\n\n"
                                f"Нажмите «Я в пути» или «Забрал».",
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
                            )
                            _reminded_30m[o.id] = now
                        except Exception:
                            pass

                # За 15 мин и меньше — авто-возврат в пул
                elif minutes_left <= 15:
                    # Возвращаем заказ в пул
                    await session.execute(
                        update(Order).where(Order.id == o.id)
                        .values(
                            courier_id=None,
                            status="wait",
                            taken_at=None,
                            is_urgent_notified=False,
                        )
                    )
                    await session.commit()

                    # Уведомить курьера
                    try:
                        await bot_courier.send_message(
                            courier.tg_id,
                            f"❌ <b>Заказ #{o.id} снят</b>\n\n"
                            f"Вы не забрали букет вовремя. Заказ возвращён в пул.",
                        )
                    except Exception:
                        pass

                    # Уведомить магазин
                    s_r = await session.execute(select(Shop).where(Shop.id == o.shop_id))
                    shop = s_r.scalar_one_or_none()
                    if shop and shop.tg_id:
                        try:
                            await bot_shop.send_message(
                                shop.tg_id,
                                f"⚠️ <b>Заказ #{o.id} возвращён в поиск курьера</b>\n\n"
                                f"Курьер не забрал заказ вовремя.",
                            )
                        except Exception:
                            pass

                    log.info(f"⏰ Заказ #{o.id} возвращён в пул (курьер проигнорировал)")
                    _reminded_1h.pop(o.id, None)
                    _reminded_30m.pop(o.id, None)
    except Exception as e:
        log.exception(f"Ошибка courier_timeout_job: {e}")


# ═══════════════════════════════════════════
#   9. ДАЙДЖЕСТ НОВИНОК (18:00)
# ═══════════════════════════════════════════
async def daily_digest_job():
    log.info("📬 Дайджест новинок")
    try:
        async with async_session() as session:
            since = helpers.now_moscow() - timedelta(hours=24)

            result = await session.execute(
                select(Product.shop_id).where(
                    Product.created_at >= since,
                    Product.is_active == True,
                    Product.is_draft == False,
                ).distinct()
            )
            shop_ids = [row[0] for row in result.all()]

            for shop_id in shop_ids:
                p_result = await session.execute(
                    select(Product).where(
                        Product.shop_id == shop_id,
                        Product.created_at >= since,
                        Product.is_active == True,
                        Product.is_draft == False,
                    ).order_by(Product.id.desc())
                )
                products = p_result.scalars().all()
                if not products:
                    continue

                s_result = await session.execute(select(Shop).where(Shop.id == shop_id))
                shop = s_result.scalar_one_or_none()
                if not shop:
                    continue

                sub_result = await session.execute(
                    select(Client).join(ShopSubscription, ShopSubscription.client_id == Client.id)
                    .where(
                        ShopSubscription.shop_id == shop_id,
                        Client.tg_id.isnot(None),
                        Client.is_blocked == False,
                        Client.bot_blocked == False,
                    )
                )
                subscribers = sub_result.scalars().all()
                if not subscribers:
                    continue

                first_product = products[0]
                count = len(products)

                if count == 1:
                    caption = f"🌸 <b>Новинка в магазине «{helpers.escape(shop.name)}»!</b>\n\n💐 {helpers.escape(first_product.title)}\n💰 {helpers.money(first_product.client_price)}"
                else:
                    caption = f"🌸 <b>Новые поступления в магазине «{helpers.escape(shop.name)}»!</b>\n\nНа фото: {helpers.escape(first_product.title)}. А ещё {count - 1} новинок ждут вас!"

                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍 Посмотреть все", callback_data=f"shop_products_{shop_id}")]
                ])

                for sub in subscribers:
                    try:
                        if first_product.photo_id:
                            await bot_client.send_photo(
                                chat_id=sub.tg_id, photo=first_product.photo_id,
                                caption=caption, reply_markup=markup,
                            )
                        else:
                            await bot_client.send_message(sub.tg_id, caption, reply_markup=markup)
                    except Exception:
                        pass

                log.info(f"📬 Дайджест магазина «{shop.name}» — {len(subscribers)} подписчикам")
    except Exception as e:
        log.exception(f"Ошибка daily_digest_job: {e}")


# ═══════════════════════════════════════════
#   ПЛАНИРОВЩИК
# ═══════════════════════════════════════════
def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Бонусы
    scheduler.add_job(daily_bonus_job, "cron", hour=23, minute=59)
    scheduler.add_job(daily_bonus_job_yesterday, "cron", hour=0, minute=5)

    # Заказы
    scheduler.add_job(auto_cancel_job, "interval", minutes=5)
    scheduler.add_job(events_reminder_job, "cron", hour=10, minute=0)
    scheduler.add_job(photo_reminder_job, "interval", minutes=15)

    # Доставки
    scheduler.add_job(delivery_autocancel_job, "interval", minutes=10)
    scheduler.add_job(delivery_reminder_job, "interval", minutes=30)

    # Горящие заказы
    scheduler.add_job(urgent_orders_job, "interval", minutes=5)

    # Feature 14: тайм-аут курьера
    scheduler.add_job(courier_timeout_job, "interval", minutes=5)

    # Дайджест
    scheduler.add_job(daily_digest_job, "cron", hour=18, minute=0)

    scheduler.start()
    log.info("⏰ Планировщик запущен (10 задач)")
    return scheduler


# ═══════════════════════════════════════════
#   ЗАПУСК БОТОВ
# ═══════════════════════════════════════════
async def run_bot(bot, dp, name: str):
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info(f"🚀 {name} запущен")
        await dp.start_polling(bot)
    except Exception as e:
        log.exception(f"❌ {name} упал: {e}")


async def main():
    log.info("🚀 Flowers Express — запуск")

    try:
        await init_db()
        log.info("✅ База данных готова")
    except Exception as e:
        log.exception(f"❌ Ошибка БД: {e}")
        return

    # Загружаем настройки из БД (праздничная наценка и т.д.)
    try:
        await load_config_from_db()
    except Exception as e:
        log.error(f"Ошибка load_config_from_db: {e}")

    # Seed ачивок
    try:
        async with async_session() as session:
            await bonuses_service.seed_achievements(session)
        log.info("🏆 Ачивки засеяны")
    except Exception as e:
        log.error(f"Ошибка seed_achievements: {e}")

    scheduler = setup_scheduler()

    try:
        await asyncio.gather(
            run_bot(bot_client, dp_client, "CLIENT"),
            run_bot(bot_shop, dp_shop, "SHOP"),
            run_bot(bot_courier, dp_courier, "COURIER"),
            run_bot(bot_admin, dp_admin, "ADMIN"),
        )
    finally:
        # Graceful shutdown
        log.info("⛔ Завершение...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        for b in (bot_client, bot_shop, bot_courier, bot_admin):
            try:
                await b.session.close()
            except Exception:
                pass
        try:
            await engine.dispose()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("⛔ Flowers Express остановлен")
