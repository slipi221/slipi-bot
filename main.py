# -*- coding: utf-8 -*-
"""
SLIPI — точка входа, запуск всех ботов и планировщика
"""
import asyncio
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal

from aiogram import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update

import config
from database import init_db, async_session
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
#   1. ЕЖЕДНЕВНЫЕ БОНУСЫ (23:59)
# ═══════════════════════════════════════════
async def daily_bonus_job():
    log.info("⏰ Бонусы")
    try:
        async with async_session() as session:
            await bonuses_service.apply_all_daily_bonuses(session)
        log.info("✅ Бонусы начислены")
    except Exception as e:
        log.error(f"Ошибка бонусов: {e}")


# ═══════════════════════════════════════════
#   2. АВТООТМЕНА ЗАКАЗОВ (каждые 5 мин)
# ═══════════════════════════════════════════
async def auto_cancel_job():
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.status == "new", # Магазин не ответил
                    Order.payment_status == "confirmed",
                )
            )
            orders = result.scalars().all()

            now = datetime.now()
            for o in orders:
                if not o.wait_started_at: continue
                elapsed = (now - o.wait_started_at).total_seconds() / 60

                if 8 <= now.hour < 23:
                    if elapsed >= config.DAY_ORDER_TIMEOUT_MINUTES:
                        await orders_service.cancel_order(session, o.id, reason="shop_no_response", cancelled_by="auto", refund=True)
                        log.info(f"Автоотмена магазином #{o.id}")

                        c_r = await session.execute(select(Client).where(Client.id == o.client_id))
                        client = c_r.scalar_one_or_none()
                        if client and client.tg_id:
                            try: await bot_client.send_message(client.tg_id, f"😔 Заказ #{o.id} отменён.\n\nМагазин не ответил. Деньги вернулись на баланс.")
                            except Exception: pass
    except Exception as e:
        log.error(f"Ошибка автоотмены: {e}")


# ═══════════════════════════════════════════
#   3. СОБЫТИЯ КЛИЕНТА (10:00)
# ═══════════════════════════════════════════
async def events_reminder_job():
    log.info("📅 События")
    try:
        async with async_session() as session:
            today = date.today()

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
                            if days == 3: text += f"Через 3 дня — <b>{e.title}</b> ({helpers.format_date(e.event_date)}).\n\nУспейте заказать букет 🌸"
                            else: text += f"Завтра — <b>{e.title}</b>!\n\nПоследний шанс заказать букет."
                            await bot_client.send_message(client.tg_id, text)
                            setattr(e, flag_field, True)
                        except Exception: pass

            await session.commit()
    except Exception as e:
        log.error(f"Ошибка событий: {e}")


# ═══════════════════════════════════════════
#   4. ФОТО-НАПОМИНАНИЯ (каждые 15 мин)
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
                if not o.courier_id: continue
                c_r = await session.execute(select(Courier).where(Courier.id == o.courier_id))
                courier = c_r.scalar_one_or_none()
                if courier and courier.tg_id:
                    try: await bot_courier.send_message(courier.tg_id, f"⏰ <b>Заказ #{o.id} ждёт фото!</b>")
                    except Exception: pass
    except Exception as e:
        log.error(f"Ошибка фото: {e}")


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
                if not d.created_at: continue
                elapsed_min = (datetime.now() - d.created_at).total_seconds() / 60
                if elapsed_min >= 120:
                    d.status = "cancel"
                    d.cancel_reason = "auto_no_payment"
                    await session.commit()

                    s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
                    shop = s_r.scalar_one_or_none()
                    if shop and shop.tg_id:
                        try: await bot_shop.send_message(shop.tg_id, f"⏰ <b>Доставка #Д-{d.id} автоотменена</b>\n\nОплата не поступила за 2 часа.")
                        except Exception: pass
    except Exception as e:
        log.error(f"Ошибка автоотмены доставок: {e}")


# ═══════════════════════════════════════════
#   6. НАПОМИНАНИЕ О ДОСТАВКАХ (каждые 30 мин)
# ═══════════════════════════════════════════
async def delivery_reminder_job():
    try:
        async with async_session() as session:
            result = await session.execute(select(DeliveryOrder).where(DeliveryOrder.status == "paid"))
            for d in result.scalars().all():
                s_r = await session.execute(select(Shop).where(Shop.id == d.shop_id))
                shop = s_r.scalar_one_or_none()
                if shop and shop.tg_id:
                    try: await bot_shop.send_message(shop.tg_id, f"⏳ <b>Доставка #Д-{d.id}</b>\n\nОжидает подтверждения админа 🔍")
                    except Exception: pass
    except Exception as e:
        log.error(f"Ошибка напоминаний: {e}")


# ═══════════════════════════════════════════
#   7. НОВОЕ: ГОРЯЩИЕ ЗАКАЗЫ (каждые 5 мин)
# ═══════════════════════════════════════════
async def urgent_orders_job():
    """
    Находит заказы, у которых до конца слота осталось 30 минут.
    Добавляет +50₽ буста, шлёт пуш ВСЕМ курьерам (1 раз).
    """
    try:
        async with async_session() as session:
            # Ищем заказы "wait" (без курьера), которым ещё не слали пуш
            result = await session.execute(
                select(Order).where(
                    Order.status == "wait",
                    Order.is_urgent_notified == False,
                    Order.courier_id.is_(None),
                    Order.delivery_date == date.today(),
                )
            )
            orders = result.scalars().all()

            if not orders:
                return

            now = datetime.now()
            for o in orders:
                if not o.delivery_slot: continue
                try:
                    end_str = o.delivery_slot.split("-")[1]
                    h, m = map(int, end_str.split(":"))
                    slot_end = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    minutes_left = (slot_end - now).total_seconds() / 60

                    if minutes_left <= 30:
                        # 1. Накидываем буст
                        o.boost_amount = Decimal(str(o.boost_amount or 0)) + Decimal(str(config.URGENT_BONUS))
                        o.is_urgent_notified = True
                        await session.commit()

                        # 2. Ищем всех активных курьеров
                        c_result = await session.execute(
                            select(Courier).where(
                                Courier.status == "active",
                                Courier.is_blocked == False,
                                Courier.tg_id.isnot(None),
                            )
                        )
                        couriers = c_result.scalars().all()

                        # 3. Рассылка
                        text = (
                            f"🚨 <b>СРОЧНЫЙ ЗАКАЗ #{o.id}!</b>\n\n"
                            f"⏰ Осталось <b>{int(minutes_left)} мин</b> до конца слота!\n"
                            f"💰 Ставка: <b>{helpers.money(o.courier_fee)} + {config.URGENT_BONUS}₽ буст</b>\n"
                            f"📍 {o.address}\n\n"
                            f"<i>Если вы готовы помочь — выйдите на смену и заберите заказ!</i>"
                        )
                        for c in couriers:
                            try:
                                on_shift = c.courier_state == "on"
                                kb_rows = []
                                if not on_shift:
                                    kb_rows.append([InlineKeyboardButton(text="🟢 Выйти на смену", callback_data="courier_on_shift")])
                                else:
                                    kb_rows.append([InlineKeyboardButton(text="📦 Взять заказ", callback_data=f"courier_take_{o.id}")])

                                await bot_courier.send_message(
                                    c.tg_id, text,
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
                                )
                            except Exception: pass
                        log.info(f"🚨 Пуш по горящему заказу #{o.id} разослан курьерам")
                except Exception as e:
                    log.error(f"Ошибка в urgent_orders_job для #{o.id}: {e}")
    except Exception as e:
        log.error(f"Ошибка urgent_orders_job: {e}")


# ═══════════════════════════════════════════
#   8. НОВОЕ: УМНЫЙ ДАЙДЖЕСТ НОВИНОК (18:00)
# ═══════════════════════════════════════════
async def daily_digest_job():
    """
    Раз в день ищет новые товары за последние 24 часа.
    Отправляет подписчикам магазина фото первого товара + кнопку.
    """
    log.info("📬 Дайджест новинок")
    try:
        async with async_session() as session:
            since = datetime.now() - timedelta(hours=24)
            
            # Ищем магазины, у которых были новые товары за сутки
            result = await session.execute(
                select(Product.shop_id).where(
                    Product.created_at >= since,
                    Product.is_active == True,
                    Product.is_draft == False,
                ).distinct()
            )
            shop_ids = [row[0] for row in result.all()]

            for shop_id in shop_ids:
                # Все новые товары этого магазина
                p_result = await session.execute(
                    select(Product).where(
                        Product.shop_id == shop_id,
                        Product.created_at >= since,
                        Product.is_active == True,
                        Product.is_draft == False,
                    ).order_by(Product.id.desc())
                )
                products = p_result.scalars().all()
                if not products: continue

                # Информация о магазине
                s_result = await session.execute(select(Shop).where(Shop.id == shop_id))
                shop = s_result.scalar_one_or_none()
                if not shop: continue

                # Подписчики
                sub_result = await session.execute(
                    select(Client).join(ShopSubscription, ShopSubscription.client_id == Client.id)
                    .where(ShopSubscription.shop_id == shop_id, Client.tg_id.isnot(None), Client.is_blocked == False)
                )
                subscribers = sub_result.scalars().all()
                if not subscribers: continue

                # Формируем сообщение
                first_product = products[0]
                count = len(products)
                
                if count == 1:
                    caption = f"🌸 <b>Новинка в магазине «{shop.name}»!</b>\n\n💐 {first_product.title}\n💰 {helpers.money(first_product.client_price)}"
                else:
                    caption = f"🌸 <b>Новые поступления в магазине «{shop.name}»!</b>\n\nНа фото: {first_product.title}. А ещё {count - 1} новинок ждут вас!"
                
                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍 Посмотреть все", callback_data=f"shop_products_{shop_id}")]
                ])

                for sub in subscribers:
                    try:
                        if first_product.photo_id:
                            await bot_client.send_photo(
                                chat_id=sub.tg_id, photo=first_product.photo_id,
                                caption=caption, reply_markup=markup
                            )
                        else:
                            await bot_client.send_message(sub.tg_id, caption, reply_markup=markup)
                    except Exception: pass
                
                log.info(f"📬 Дайджест для магазина «{shop.name}» отправлен {len(subscribers)} подписчикам")
    except Exception as e:
        log.error(f"Ошибка daily_digest_job: {e}")


# ═══════════════════════════════════════════
#   ПЛАНИРОВЩИК
# ═══════════════════════════════════════════
def setup_scheduler():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Старые задачи
    scheduler.add_job(daily_bonus_job, "cron", hour=23, minute=59)              # Бонусы курьерам
    scheduler.add_job(auto_cancel_job, "interval", minutes=5)                   # Автоотмена (магазин не ответил)
    scheduler.add_job(events_reminder_job, "cron", hour=10, minute=0)           # События клиента
    scheduler.add_job(photo_reminder_job, "interval", minutes=15)               # Напоминание о фото
    scheduler.add_job(delivery_autocancel_job, "interval", minutes=10)          # Автоотмена доставок
    scheduler.add_job(delivery_reminder_job, "interval", minutes=30)            # Напоминание о доставках

    # НОВЫЕ задачи
    scheduler.add_job(urgent_orders_job, "interval", minutes=5)                 # 🔥 Горящие заказы + Буст
    scheduler.add_job(daily_digest_job, "cron", hour=18, minute=0)              # 📬 Дайджест новинок

    scheduler.start()
    log.info("⏰ Планировщик запущен (8 задач)")


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
