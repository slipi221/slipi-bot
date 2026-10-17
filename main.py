# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal

from aiogram import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update, text

import config
from database import engine, Base, async_session
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
log = logging.getLogger("slipi")

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
#   ПЛАНИРОВЩИК (все 8 задач)
# ═══════════════════════════════════════════
# (Здесь оставь все функции задач: daily_bonus_job, auto_cancel_job и т.д., 
# которые я присылал в предыдущем сообщении. Они не меняются.)
# ...

def setup_scheduler():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    # (Оставь тут добавление задач, как было)
    scheduler.start()
    log.info("⏰ Планировщик запущен")

# ═══════════════════════════════════════════
#   ЗАПУСК БОТОВ
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

    # ПРИНУДИТЕЛЬНОЕ СОЗДАНИЕ ТАБЛИЦ
    try:
        log.info(f"🔧 Подключение к БД: {config.DATABASE_URL}")
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.run_sync(Base.metadata.create_all)
        log.info("✅ Все таблицы успешно созданы в базе!")
    except Exception as e:
        log.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА БД: {e}")
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
