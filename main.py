# -*- coding: utf-8 -*-
"""
SLIPI — точка входа, запуск всех ботов
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from database import init_db, async_session
from handlers import client as client_h
from handlers import shop as shop_h
from handlers import courier as courier_h
from handlers import admin as admin_h
from services import bonuses as bonuses_service


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("slipi")


# ═══════════════════════════════════════════
#   СОЗДАНИЕ БОТОВ
# ═══════════════════════════════════════════
def make_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


bot_client = make_bot(config.CLIENT_TOKEN)
bot_shop = make_bot(config.SHOP_TOKEN)
bot_courier = make_bot(config.COURIER_TOKEN)
bot_admin = make_bot(config.ADMIN_TOKEN)


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
#   ПЕРИОДИЧЕСКИЕ ЗАДАЧИ
# ═══════════════════════════════════════════
async def daily_bonus_job():
    """Каждый день в 23:59 — начислить бонусы курьерам."""
    log.info("⏰ Запуск бонусов")
    try:
        async with async_session() as session:
            await bonuses_service.apply_all_daily_bonuses(session)
        log.info("✅ Бонусы начислены")
    except Exception as e:
        log.error(f"Ошибка бонусов: {e}")


def setup_scheduler():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(daily_bonus_job, "cron", hour=23, minute=59)
    scheduler.start()
    log.info("⏰ Планировщик запущен")


# ═══════════════════════════════════════════
#   ЗАПУСК БОТОВ
# ═══════════════════════════════════════════
async def run_bot(bot: Bot, dp: Dispatcher, name: str):
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info(f"🚀 {name} запущен")
        await dp.start_polling(bot)
    except Exception as e:
        log.error(f"❌ {name} упал: {e}")


async def main():
    log.info("🚀 SLIPI — запуск")

    # Инициализация БД
    try:
        await init_db()
        log.info("✅ База данных готова")
    except Exception as e:
        log.error(f"❌ Ошибка БД: {e}")
        return

    # Планировщик
    setup_scheduler()

    # Запуск всех ботов параллельно
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
