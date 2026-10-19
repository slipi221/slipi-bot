# -*- coding: utf-8 -*-
"""
Flowers Express — бонусы, рефералка, уровни, достижения

FIX bug12: дописаны 6 ачивок (marathon, no_errors, early_bird, night_owl, five_star, referral_master).
FIX bug1: TZ — все даты/время через helpers (naive MSK).
NEW: seed_achievements() — заполняет таблицу Achievement при старте.
NEW: apply_all_daily_bonuses(for_date) — можно вызвать за вчера (граница 23:59).
"""
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Courier, CourierDailyStat, Achievement, CourierAchievement,
    Transaction, Order, Review, Complaint,
)
from utils import helpers

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#   ЕЖЕДНЕВНЫЙ БОНУС
# ═══════════════════════════════════════════
async def calculate_daily_bonus(session: AsyncSession, courier_id: int, for_date: date = None) -> Decimal:
    target_date = for_date or helpers.today_moscow()
    result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == target_date,
        )
    )
    stat = result.scalar_one_or_none()
    if not stat:
        return Decimal("0.00")

    groups = stat.completed_orders // 10
    return Decimal(str(groups * config.BONUS_PER_10_ORDERS))


async def apply_daily_bonus(session: AsyncSession, courier_id: int, for_date: date = None) -> Decimal:
    """Начисляет бонус. Возвращает сумму, которая была начислена (0 если ничего)."""
    target_date = for_date or helpers.today_moscow()
    result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == target_date,
        )
    )
    stat = result.scalar_one_or_none()
    if not stat:
        return Decimal("0.00")

    new_bonus = await calculate_daily_bonus(session, courier_id, target_date)
    diff = new_bonus - Decimal(str(stat.bonus_earned))

    if diff > 0:
        stat.bonus_earned = new_bonus
        await session.execute(
            update(Courier).where(Courier.id == courier_id)
            .values(balance=Courier.balance + diff)
        )
        session.add(Transaction(
            user_type="courier", user_id=courier_id, account_type="main",
            amount=diff, type="bonus",
            comment=f"Бонус за {stat.completed_orders} заказов ({target_date})",
        ))
        return diff
    return Decimal("0.00")


async def apply_all_daily_bonuses(session: AsyncSession, for_date: date = None):
    """
    Начисляет бонусы всем курьерам за указанную дату (по умолчанию — сегодня).
    Можно вызывать дважды: 23:59 (сегодня) и 00:05 (за вчера) — дубли не начислятся.
    """
    target_date = for_date or helpers.today_moscow()
    result = await session.execute(
        select(CourierDailyStat).where(CourierDailyStat.date == target_date)
    )
    stats = result.scalars().all()
    for stat in stats:
        if stat.completed_orders >= 10:
            await apply_daily_bonus(session, stat.courier_id, target_date)
    await session.commit()


# ═══════════════════════════════════════════
#   РЕФЕРАЛЬНАЯ ПРОГРАММА
# ═══════════════════════════════════════════
async def apply_referral_percent(
    session: AsyncSession,
    courier_id: int,
    earned_amount: Decimal,
):
    """Начисляет процент рефереру (без коммита)."""
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier or not courier.referred_by:
        return

    # FIX bug1: after helpers fix — оба naive MSK, сравнение корректно
    if courier.referral_until and courier.referral_until < helpers.now_moscow():
        return

    ref_bonus = (earned_amount * Decimal(str(config.REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
    if ref_bonus <= 0:
        return

    await session.execute(
        update(Courier).where(Courier.id == courier.referred_by)
        .values(balance=Courier.balance + ref_bonus)
    )
    session.add(Transaction(
        user_type="courier", user_id=courier.referred_by, account_type="main",
        amount=ref_bonus, type="referral",
        comment=f"Реферал от курьера #{courier_id}",
    ))


async def register_referral(
    session: AsyncSession,
    new_courier_id: int,
    referrer_tg_id: int,
):
    """Регистрирует реферальную связь курьер→курьер."""
    result = await session.execute(
        select(Courier).where(Courier.tg_id == referrer_tg_id)
    )
    referrer = result.scalar_one_or_none()
    if not referrer or referrer.id == new_courier_id:
        return False

    until = helpers.now_moscow() + timedelta(days=config.REFERRAL_MONTHS * 30)
    await session.execute(
        update(Courier).where(Courier.id == new_courier_id)
        .values(referred_by=referrer.id, referral_until=until)
    )
    await session.commit()
    return True


# ═══════════════════════════════════════════
#   УРОВНИ КУРЬЕРОВ
# ═══════════════════════════════════════════
LEVELS = [
    ("newbie",      "🥉 Новичок",  0,   0),
    ("experienced", "🥈 Опытный",  51,  1),
    ("pro",         "🥇 Про",      201, 2),
    ("legend",      "👑 Легенда",  501, 5),
]


def get_level_by_orders(total_orders: int) -> tuple:
    current = LEVELS[0]
    for code, title, threshold, bonus in LEVELS:
        if total_orders >= threshold:
            current = (code, title, threshold, bonus)
    return current


def get_next_level(total_orders: int) -> tuple | None:
    for code, title, threshold, bonus in LEVELS:
        if total_orders < threshold:
            return (code, title, threshold, bonus)
    return None


async def update_courier_level(session: AsyncSession, courier_id: int):
    """Обновляет уровень курьера (без коммита)."""
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return
    code, _, _, _ = get_level_by_orders(courier.total_orders)
    if courier.level != code:
        courier.level = code


# ═══════════════════════════════════════════
#   ДОСТИЖЕНИЯ
# ═══════════════════════════════════════════
ACHIEVEMENTS_LIST = [
    {"code": "first_order",     "title": "🌟 Первый заказ",   "description": "1 доставка",                     "icon": "🌟"},
    {"code": "sprinter",        "title": "🏆 Спринтер",       "description": "10 заказов за день",             "icon": "🏆"},
    {"code": "marathon",        "title": "🏆 Марафонец",      "description": "100 заказов за 30 дней",         "icon": "🏆"},
    {"code": "no_errors",       "title": "🏆 Без ошибок",     "description": "50 заказов без жалоб",           "icon": "🏆"},
    {"code": "early_bird",      "title": "🐦 Ранняя пташка",  "description": "5 заказов до 9:00",              "icon": "🐦"},
    {"code": "night_owl",       "title": "🦉 Ночная сова",    "description": "5 заказов после 22:00",          "icon": "🦉"},
    {"code": "five_star",       "title": "⭐ Пять звёзд",     "description": "10 отзывов с 5 звёзд",           "icon": "⭐"},
    {"code": "referral_master", "title": "🎁 Реферер",        "description": "5 приглашённых курьеров (с заказом)", "icon": "🎁"},
    {"code": "legend_100",      "title": "👑 Сотня",          "description": "100 заказов за всё время",       "icon": "👑"},
    {"code": "legend_500",      "title": "👑 Легенда",        "description": "500 заказов за всё время",       "icon": "👑"},
]


async def seed_achievements(session: AsyncSession):
    """
    Заполняет таблицу Achievement (если пусто).
    Вызывать при старте бота — иначе в БД только те, что кто-то уже получил.
    """
    for info in ACHIEVEMENTS_LIST:
        r = await session.execute(select(Achievement).where(Achievement.code == info["code"]))
        if r.scalar_one_or_none():
            continue
        session.add(Achievement(**info))
    try:
        await session.commit()
    except Exception as e:
        log.error(f"seed_achievements: {e}")
        await session.rollback()


async def grant_achievement(session: AsyncSession, courier_id: int, code: str) -> bool:
    """Выдаёт ачивку (без коммита). Возвращает True, если выдана новая."""
    ach_result = await session.execute(
        select(Achievement).where(Achievement.code == code)
    )
    ach = ach_result.scalar_one_or_none()
    if not ach:
        info = next((a for a in ACHIEVEMENTS_LIST if a["code"] == code), None)
        if not info:
            return False
        ach = Achievement(**info)
        session.add(ach)
        await session.flush()

    check = await session.execute(
        select(CourierAchievement).where(
            CourierAchievement.courier_id == courier_id,
            CourierAchievement.achievement_id == ach.id,
        )
    )
    if check.scalar_one_or_none():
        return False

    session.add(CourierAchievement(
        courier_id=courier_id,
        achievement_id=ach.id,
    ))
    return True


async def check_achievements(session: AsyncSession, courier_id: int) -> list:
    """
    Проверяет и выдаёт достижения.
    FIX bug12: все 10 ачивок.
    """
    new_achievements = []
    c_result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = c_result.scalar_one_or_none()
    if not courier:
        return []

    # 1. first_order — 1 заказ
    if courier.total_orders >= 1:
        if await grant_achievement(session, courier_id, "first_order"):
            new_achievements.append("first_order")

    # 2. legend_100 — 100 за всё время
    if courier.total_orders >= 100:
        if await grant_achievement(session, courier_id, "legend_100"):
            new_achievements.append("legend_100")

    # 3. legend_500 — 500 за всё время
    if courier.total_orders >= 500:
        if await grant_achievement(session, courier_id, "legend_500"):
            new_achievements.append("legend_500")

    # 4. sprinter — 10 за день (сегодня)
    stat_result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == helpers.today_moscow(),
        )
    )
    stat = stat_result.scalar_one_or_none()
    if stat and stat.completed_orders >= 10:
        if await grant_achievement(session, courier_id, "sprinter"):
            new_achievements.append("sprinter")

    # 5. marathon — 100 за 30 дней (скользящее окно)
    since_30 = helpers.today_moscow() - timedelta(days=30)
    marathon_r = await session.execute(
        select(func.coalesce(func.sum(CourierDailyStat.completed_orders), 0))
        .where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date >= since_30,
        )
    )
    marathon_count = int(marathon_r.scalar() or 0)
    if marathon_count >= 100:
        if await grant_achievement(session, courier_id, "marathon"):
            new_achievements.append("marathon")

    # 6. no_errors — 50 заказов, ни одной ПРИНЯТОЙ жалобы
    if courier.total_orders >= 50:
        complaints_r = await session.execute(
            select(func.count(Complaint.id)).where(
                Complaint.target_type == "courier",
                Complaint.target_id == courier_id,
                Complaint.status == "approved",
            )
        )
        approved_complaints = int(complaints_r.scalar() or 0)
        if approved_complaints == 0:
            if await grant_achievement(session, courier_id, "no_errors"):
                new_achievements.append("no_errors")

    # 7. early_bird — 5 доставок до 9:00 (МСК)
    early_r = await session.execute(
        select(func.count(Order.id)).where(
            Order.courier_id == courier_id,
            Order.status == "done",
            Order.delivered_at.isnot(None),
            func.strftime("%H", Order.delivered_at) < "09",
        )
    )
    early_count = int(early_r.scalar() or 0)
    if early_count >= 5:
        if await grant_achievement(session, courier_id, "early_bird"):
            new_achievements.append("early_bird")

    # 8. night_owl — 5 доставок после 22:00 (МСК)
    night_r = await session.execute(
        select(func.count(Order.id)).where(
            Order.courier_id == courier_id,
            Order.status == "done",
            Order.delivered_at.isnot(None),
            func.strftime("%H", Order.delivered_at) >= "22",
        )
    )
    night_count = int(night_r.scalar() or 0)
    if night_count >= 5:
        if await grant_achievement(session, courier_id, "night_owl"):
            new_achievements.append("night_owl")

    # 9. five_star — 10 отзывов с 5 звёзд на курьера
    stars_r = await session.execute(
        select(func.count(Review.id)).where(
            Review.target_type == "courier",
            Review.target_id == courier_id,
            Review.rating == 5,
        )
    )
    five_star_count = int(stars_r.scalar() or 0)
    if five_star_count >= 10:
        if await grant_achievement(session, courier_id, "five_star"):
            new_achievements.append("five_star")

    # 10. referral_master — 5 приглашённых с ≥1 заказом
    ref_r = await session.execute(
        select(func.count(Courier.id)).where(
            Courier.referred_by == courier_id,
            Courier.total_orders >= 1,
        )
    )
    active_refs = int(ref_r.scalar() or 0)
    if active_refs >= 5:
        if await grant_achievement(session, courier_id, "referral_master"):
            new_achievements.append("referral_master")

    return new_achievements


async def get_courier_achievements(session: AsyncSession, courier_id: int) -> list:
    result = await session.execute(
        select(Achievement).join(
            CourierAchievement,
            CourierAchievement.achievement_id == Achievement.id,
        ).where(CourierAchievement.courier_id == courier_id)
    )
    return result.scalars().all()
