# -*- coding: utf-8 -*-
"""
SLIPI — точка входа, запуск всех ботов
"""
import asyncio
import logging
from datetime import datetime, date, timedelta

from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

import config
from database import init_db, async_session
from models import Order, ClientEvent, Courier, Client, Shop, CourierDailyStat
from handlers import client as client_h
from handlers import shop as shop_h
from handlers import courier as courier_h
from handlers import admin as admin_h
from services import bonuses as bonuses_service
from services import orders as orders_service
from utils import helpers

from bots import bot_client, bot_shop, bot_courier, bot_admin


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("slipi")


# ═══════════════════════════════════════════
#   ДИСПЕТЧЕРЫ
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
#   ЕЖЕДНЕВНЫЕ БОНУСЫ (23:59)
# ═══════════════════════════════════════════
async def daily_bonus_job():
    log.info("⏰ Запуск бонусов")
    try:
        async with async_session() as session:
            await bonuses_service.apply_all_daily_bonuses(session)
        log.info("✅ Бонусы начислены")
    except Exception as e:
        log.error(f"Ошибка бонусов: {e}")


# ═══════════════════════════════════════════
#   АВТООТМЕНА (каждые 5 минут)
# ═══════════════════════════════════════════
async def auto_cancel_job():
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.status == "wait",
                    Order.payment_status == "confirmed",
                )
            )
            orders = result.scalars().all()

            now = datetime.now()
            for o in orders:
                if not o.wait_started_at:
                    continue
                elapsed = (now - o.wait_started_at).total_seconds() / 60

                if 8 <= now.hour < 23:
                    if elapsed >= config.DAY_ORDER_TIMEOUT_MINUTES:
                        await orders_service.cancel_order(
                            session, o.id,
                            reason="shop_no_response",
                            cancelled_by="auto",
                            refund=True,
                        )
                        log.info(f"Автоотмена заказа #{o.id}")

                        c_r = await session.execute(select(Client).where(Client.id == o.client_id))
                        client = c_r.scalar_one_or_none()
                        if client and client.tg_id:
                            try:
                                await bot_client.send_message(
                                    client.tg_id,
                                    f"😔 <b>Заказ #{o.id} отменён</b>\n\n"
                                    f"Магазин не ответил вовремя.\n"
                                    f"💰 Деньги вернулись на ваш баланс."
                                )
                            except Exception:
                                pass
    except Exception as e:
        log.error(f"Ошибка автоотмены: {e}")


# ═══════════════════════════════════════════
#   НАПОМИНАНИЯ О СОБЫТИЯХ (10:00)
# ═══════════════════════════════════════════
async def events_reminder_job():
    log.info("📅 Проверка событий")
    try:
        async with async_session() as session:
            today = date.today()

            target_3 = today + timedelta(days=3)
            result = await session.execute(
                select(ClientEvent).where(
                    ClientEvent.event_date == target_3,
                    ClientEvent.notified_3d == False,
                )
            )
            for e in result.scalars().all():
                c_r = await session.execute(select(Client).where(Client.id == e.client_id))
                client = c_r.scalar_one_or_none()
                if client and client.tg_id:
                    try:
                        await bot_client.send_message(
                            client.tg_id,
                            f"🔔 <b>Напоминание!</b>\n\n"
                            f"Через 3 дня — <b>{e.title}</b> "
                            f"({helpers.format_date(e.event_date)}).\n\n"
                            f"Успейте заказать букет заранее 🌸",
                        )
                        e.notified_3d = True
                    except Exception:
                        pass

            target_1 = today + timedelta(days=1)
            result = await session.execute(
                select(ClientEvent).where(
                    ClientEvent.event_date == target_1,
                    ClientEvent.notified_1d == False,
                )
            )
            for e in result.scalars().all():
                c_r = await session.execute(select(Client).where(Client.id == e.client_id))
                client = c_r.scalar_one_or_none()
                if client and client.tg_id:
                    try:
                        await bot_client.send_message(
                            client.tg_id,
                            f"⏰ <b>Завтра — {e.title}!</b>\n\n"
                            f"Последний шанс заказать букет с доставкой на завтра."
                        )
                        e.notified_1d = True
                    except Exception:
                        pass

            await session.commit()
    except Exception as e:
        log.error(f"Ошибка напоминаний: {e}")


# ═══════════════════════════════════════════
#   НАПОМИНАНИЕ О ФОТО (каждые 15 минут)
# ═══════════════════════════════════════════
async def photo_reminder_job():
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

            for o in orders:
                if not o.courier_id:
                    continue
                c_r = await session.execute(select(Courier).where(Courier.id == o.courier_id))
                courier = c_r.scalar_one_or_none()
                if courier and courier.tg_id:
                    try:
                        await bot_courier.send_message(
                            courier.tg_id,
                            f"⏰ <b>Заказ #{o.id} ждёт фото!</b>\n\n"
                            f"Пришлите фото вручения — без него заказ не закроется."
                        )
                    except Exception:
                        pass
    except Exception as e:
        log.error(f"Ошибка напоминаний о фото: {e}")


# ═══════════════════════════════════════════
#   ПЛАНИРОВЩИК
# ═══════════════════════════════════════════
def setup_scheduler():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(daily_bonus_job, "cron", hour=23, minute=59)
    scheduler.add_job(auto_cancel_job, "interval", minutes=5)
    scheduler.add_job(events_reminder_job, "cron", hour=10, minute=0)
    scheduler.add_job(photo_reminder_job, "interval", minutes=15)
    scheduler.start()
    log.info("⏰ Планировщик запущен")


# ═══════════════════════════════════════════
#   ЗАПУСК
# ═══════════════════════════════════════════
async def run_bot(bot, dp, name: str):
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info(f"🚀 {name} запущен")
        await dp.start_polling(bot)
    except Exception as e:
        log.error(f"❌ {name} упал: {e}")


async def main():
    log.info("🚀 SLIPI — запуск")

    try:
        await init_db()
        log.info("✅ База данных готова")
    except Exception as e:
        log.error(f"❌ Ошибка БД: {e}")
        return

    setup_scheduler()

    await asyncio.gather(
        run_bot(bot_client, dp_client, "CLIENT"),
        run_bot(bot_shop, dp_shop, "SHOP"),
        run_bot(bot_courier, dp_courier, "COURIER"),
        run_bot(bot_admin, dp_admin, "ADMIN"),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("⛔ SLIPI остановлен")
