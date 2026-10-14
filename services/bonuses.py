# -*- coding: utf-8 -*-
"""
SLIPI — бонусы курьерам и реферальная программа
"""
from datetime import datetime, date, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import (
    Courier, CourierDailyStat, CourierAchievement, Achievement,
    Order, Transaction,
)
from utils import helpers


# ═══════════════════════════════════════════
#   ЕЖЕДНЕВНЫЙ БОНУС
# ═══════════════════════════════════════════
async def calculate_daily_bonus(session: AsyncSession, courier_id: int) -> Decimal:
    """
    Считает бонус курьера за сегодня.
    Прогрессивно: 10 заказов → +50 ₽, 20 → +100 ₽, 30 → +150 ₽.
    """
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
    bonus = Decimal(str(groups * config.BONUS_PER_10_ORDERS))
    return bonus


async def apply_daily_bonus(session: AsyncSession, courier_id: int) -> Decimal:
    """
    Применяет бонус в конце дня (23:59).
    Начисляет разницу, если ещё не начисляли.
    """
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
        # Начисляем на баланс курьера
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
    """Применяет бонусы всем курьерам (запускается в 23:59)."""
    result = await session.execute(
        select(CourierDailyStat).where(CourierDailyStat.date == date.today())
    )
    stats = result.scalars().all()
    for stat in stats:
        if stat.completed_orders >= 10:
            await apply_daily_bonus(session, stat.courier_id)


# ═══════════════════════════════════════════
#   РЕФЕРАЛЬНАЯ ПРОГРАММА
# ═══════════════════════════════════════════
async def apply_referral_percent(
    session: AsyncSession,
    courier_id: int,
    earned_amount: Decimal,
):
    """
    Начисляет реферальный процент пригласившему курьеру.
    Вызывается после завершения заказа.
    """
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier or not courier.referred_by:
        return

    # Проверяем срок рефералки
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
    """
    Привязывает нового курьера к пригласившему.
    Вызывается при регистрации.
    """
    result = await session.execute(
        select(Courier).where(Courier.tg_id == referrer_tg_id)
    )
    referrer = result.scalar_one_or_none()
    if not referrer:
        return False

    # Не даём пригласить самого себя
    if referrer.id == new_courier_id:
        return False

    until = datetime.now() + timedelta(days=config.REFERRAL_MONTHS * 30)

    await session.execute(
        update(Courier).where(Courier.id == new_courier_id)
        .values(referred_by=referrer.id, referral_until=until)
    )
    await session.commit()
    return True


# ═══════════════════════════════════════════
#   УРОВНИ КУРЬЕРА
# ═══════════════════════════════════════════
LEVELS = [
    ("newbie", "🥉 Новичок", 0),
    ("experienced", "🥈 Опытный", 51),
    ("pro", "🥇 Про", 201),
    ("legend", "👑 Легенда", 501),
]


def get_level_by_orders(total_orders: int) -> tuple:
    """Возвращает (код, название, порог) по количеству заказов."""
    current = LEVELS[0]
    for code, title, threshold in LEVELS:
        if total_orders >= threshold:
            current = (code, title, threshold)
    return current


def get_next_level(total_orders: int) -> tuple | None:
    """Возвращает следующий уровень или None."""
    for code, title, threshold in LEVELS:
        if total_orders < threshold:
            return (code, title, threshold)
    return None


async def update_courier_level(session: AsyncSession, courier_id: int):
    """Обновляет уровень курьера по количеству заказов."""
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return
    code, _, _ = get_level_by_orders(courier.total_orders)
    if courier.level != code:
        courier.level = code
        await session.commit()


# ═══════════════════════════════════════════
#   ДОСТИЖЕНИЯ
# ═══════════════════════════════════════════
ACHIEVEMENTS = [
    {"code": "sprinter", "title": "🏆 Спринтер", "description": "10 заказов за день", "icon": "🏆"},
    {"code": "marathon", "title": "🏆 Марафонец", "description": "100 заказов за месяц", "icon": "🏆"},
    {"code": "no_errors", "title": "🏆 Без ошибок", "description": "50 заказов без жалоб", "icon": "🏆"},
    {"code": "early_bird", "title": "🏆 Ранняя пташка", "description": "5 заказов до 9:00", "icon": "🏆"},
    {"code": "night_owl", "title": "🦉 Ночная сова", "description": "5 заказов после 22:00", "icon": "🦉"},
]


async def check_achievements(session: AsyncSession, courier_id: int):
    """Проверяет и выдаёт достижения."""
    # Спринтер — 10 заказов за день
    stat_result = await session.execute(
        select(CourierDailyStat).where(
            CourierDailyStat.courier_id == courier_id,
            CourierDailyStat.date == date.today(),
        )
    )
    stat = stat_result.scalar_one_or_none()
    if stat and stat.completed_orders >= 10:
        await grant_achievement(session, courier_id, "sprinter")


async def grant_achievement(session: AsyncSession, courier_id: int, code: str):
    """Выдаёт достижение курьеру, если его ещё нет."""
    ach_result = await session.execute(
        select(Achievement).where(Achievement.code == code)
    )
    ach = ach_result.scalar_one_or_none()
    if not ach:
        return False

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


async def get_courier_achievements(session: AsyncSession, courier_id: int) -> list:
    """Возвращает список достижений курьера."""
    result = await session.execute(
        select(Achievement).join(
            CourierAchievement,
            CourierAchievement.achievement_id == Achievement.id,
        ).where(CourierAchievement.courier_id == courier_id)
    )
    return result.scalars().all()
