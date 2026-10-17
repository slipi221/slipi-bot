# -*- coding: utf-8 -*-
"""
SLIPI — точка входа
"""
import asyncio
import logging
from datetime import datetime, date, timedelta

from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from database import init_db, async_session
from handlers import client as client_h
from handlers import shop as shop_h
from handlers import courier as courier_h
from handlers import admin as admin_h
from services import bonuses as bonuses_service

from bots import bot_client, bot_shop, bot_courier, bot_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("slipi")

dp_client = Dispatcher()
dp_shop = Dispatcher()
dp_courier = Dispatcher()
dp_admin = Dispatcher()

dp_client.include_router(client_h.router)
dp_shop.include_router(shop_h.router)
dp_courier.include_router(courier_h.router)
dp_admin.include_router(admin_h.router)

async def daily_bonus_job():
    async with async_session() as session:
        await bonuses_service.apply_all_daily_bonuses(session)

def setup_scheduler():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(daily_bonus_job, "cron", hour=23, minute=59)
    scheduler.start()
    log.info("⏰ Планировщик запущен")

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
