# -*- coding: utf-8 -*-
"""
SLIPI — бонусы и рефералка
"""
from datetime import datetime, date, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Courier, CourierDailyStat, Achievement, CourierAchievement,
    Transaction,
)


# ═══════════════════════════════════════════
#   ЕЖЕДНЕВНЫЙ БОНУС
# ═══════════════════════════════════════════
async def calculate_daily_bonus(session: AsyncSession, courier_id: int) -> Decimal:
    result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == date.today(),
        )
    )
    stat = result.scalar_one_or_none()
    if not stat:
        return Decimal("0")

    groups = stat.completed_orders // 10
    return Decimal(str(groups * config.BONUS_PER_10_ORDERS))


async def apply_daily_bonus(session: AsyncSession, courier_id: int) -> Decimal:
    result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == date.today(),
        )
    )
    stat = result.scalar_one_or_none()
    if not stat:
        return Decimal("0")

    new_bonus = await calculate_daily_bonus(session, courier_id)
    diff = new_bonus - Decimal(str(stat.bonus_earned))

    if diff > 0:
        stat.bonus_earned = new_bonus
        await session.execute(
            update(Courier).where(Courier.id == courier_id)
            .values(balance=Courier.balance + diff)
        )
        session.add(Transaction(
            user_type="courier", user_id=courier_id,
            amount=diff, type="bonus",
            comment=f"Бонус за {stat.completed_orders} заказов",
        ))

    await session.commit()
    return new_bonus


async def apply_all_daily_bonuses(session: AsyncSession):
    result = await session.execute(
        select(CourierDailyStat).where(CourierDailyStat.date == date.today())
    )
    stats = result.scalars().all()
    for stat in stats:
        if stat.completed_orders >= 10:
            await apply_daily_bonus(session, stat.courier_id)


# ═══════════════════════════════════════════
#   РЕФЕРАЛКА
# ═══════════════════════════════════════════
async def apply_referral_percent(
    session: AsyncSession,
    courier_id: int,
    earned_amount: Decimal,
):
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier or not courier.referred_by:
        return

    if courier.referral_until and courier.referral_until < datetime.now():
        return

    ref_bonus = (earned_amount * Decimal(str(config.REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
    if ref_bonus <= 0:
        return

    await session.execute(
        update(Courier).where(Courier.id == courier.referred_by)
        .values(balance=Courier.balance + ref_bonus)
    )
    session.add(Transaction(
        user_type="courier", user_id=courier.referred_by,
        amount=ref_bonus, type="referral",
        comment=f"Реферал от курьера #{courier_id}",
    ))
    await session.commit()


async def register_referral(
    session: AsyncSession,
    new_courier_id: int,
    referrer_tg_id: int,
):
    result = await session.execute(
        select(Courier).where(Courier.tg_id == referrer_tg_id)
    )
    referrer = result.scalar_one_or_none()
    if not referrer or referrer.id == new_courier_id:
        return False

    until = datetime.now() + timedelta(days=config.REFERRAL_MONTHS * 30)
    await session.execute(
        update(Courier).where(Courier.id == new_courier_id)
        .values(referred_by=referrer.id, referral_until=until)
    )
    await session.commit()
    return True


# ═══════════════════════════════════════════
#   УРОВНИ
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
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return
    code, _, _, _ = get_level_by_orders(courier.total_orders)
    if courier.level != code:
        courier.level = code
        await session.commit()


# ═══════════════════════════════════════════
#   ДОСТИЖЕНИЯ
# ═══════════════════════════════════════════
ACHIEVEMENTS_LIST = [
    {"code": "first_order",     "title": "🌟 Первый заказ",   "description": "1 доставка",               "icon": "🌟"},
    {"code": "sprinter",        "title": "🏆 Спринтер",       "description": "10 заказов за день",       "icon": "🏆"},
    {"code": "marathon",        "title": "🏆 Марафонец",      "description": "100 заказов за месяц",     "icon": "🏆"},
    {"code": "no_errors",       "title": "🏆 Без ошибок",     "description": "50 заказов без жалоб",     "icon": "🏆"},
    {"code": "early_bird",      "title": "🐦 Ранняя пташка",  "description": "5 заказов до 9:00",        "icon": "🐦"},
    {"code": "night_owl",       "title": "🦉 Ночная сова",    "description": "5 заказов после 22:00",    "icon": "🦉"},
    {"code": "five_star",       "title": "⭐ Пять звёзд",     "description": "10 отзывов с 5 звёзд",     "icon": "⭐"},
    {"code": "referral_master", "title": "🎁 Реферер",        "description": "5 приглашённых курьеров",  "icon": "🎁"},
    {"code": "legend_100",      "title": "👑 Сотня",          "description": "100 заказов за всё время", "icon": "👑"},
    {"code": "legend_500",      "title": "👑 Легенда",        "description": "500 заказов за всё время", "icon": "👑"},
]


async def grant_achievement(session: AsyncSession, courier_id: int, code: str) -> bool:
    ach_result = await session.execute(
        select(Achievement).where(Achievement.code == code)
    )
    ach = ach_result.scalar_one_or_none()
    if not ach:
        # Создаём достижение, если нет
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
    await session.commit()
    return True


async def check_achievements(session: AsyncSession, courier_id: int):
    result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == date.today(),
        )
    )
    stat = result.scalar_one_or_none()
    if stat and stat.completed_orders >= 10:
        await grant_achievement(session, courier_id, "sprinter")


async def get_courier_achievements(session: AsyncSession, courier_id: int) -> list:
    result = await session.execute(
        select(Achievement).join(
            CourierAchievement,
            CourierAchievement.achievement_id == Achievement.id,
        ).where(CourierAchievement.courier_id == courier_id)
    )
    return result.scalars().all()
