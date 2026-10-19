# -*- coding: utf-8 -*-
"""
Flowers Express — геолокация

FIX (P0): update_courier_location — блокировка и авто-модерация.
FIX: get_couriers_on_shift — фильтр tg_id | vk_id (Feature 2).
FIX Feature 4: find_nearby_shops / get_all_shops — не скрывать is_paused, отдавать is_open.
FIX: is_shop_open — fail-safe (except → False), проверка is_paused внутри.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import Shop, Courier, Order
from utils import helpers

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#   БЛИЖАЙШИЕ МАГАЗИНЫ
# ═══════════════════════════════════════════
async def find_nearby_shops(
    session: AsyncSession,
    client_lat: float,
    client_lon: float,
    radius_km: float = None,
    limit: int = 20,
) -> list:
    """
    FIX Feature 4: не фильтруем is_paused — магазин виден всегда.
    Отдаём is_open — клиент видит пометку «закрыт», но может заказать на будущее.
    """
    if radius_km is None:
        radius_km = config.NEARBY_SHOPS_RADIUS_KM

    result = await session.execute(
        select(Shop).where(
            Shop.status == "active",
            Shop.lat.isnot(None),
            Shop.lon.isnot(None),
        )
    )
    shops = result.scalars().all()

    out = []
    for shop in shops:
        dist = helpers.distance_km(
            client_lat, client_lon,
            float(shop.lat), float(shop.lon),
        )
        if dist <= radius_km:
            out.append({
                "shop": shop,
                "distance": dist,
                "id": shop.id,
                "name": shop.name,
                "rating": float(shop.rating or 0),
                "is_open": is_shop_open(shop),
                "is_paused": shop.is_paused,
            })

    out.sort(key=lambda x: x["distance"])
    return out[:limit]


# ═══════════════════════════════════════════
#   ВСЕ АКТИВНЫЕ МАГАЗИНЫ
# ═══════════════════════════════════════════
async def get_all_shops(session: AsyncSession, limit: int = 50) -> list:
    """
    FIX Feature 4: не фильтруем is_paused.
    """
    result = await session.execute(
        select(Shop).where(Shop.status == "active")
        .order_by(Shop.rating.desc()).limit(limit)
    )
    return result.scalars().all()


# ═══════════════════════════════════════════
#   КУРЬЕРЫ НА СМЕНЕ
# ═══════════════════════════════════════════
async def get_couriers_on_shift(session: AsyncSession) -> list:
    """
    Все курьеры на смене (TG или VK).
    FIX Feature 2: фильтр tg_id | vk_id — не отсекаем ВК-курьеров.
    """
    result = await session.execute(
        select(Courier).where(
            Courier.status == "active",
            Courier.courier_state == "on",
            Courier.is_blocked == False,
            (Courier.tg_id.isnot(None)) | (Courier.vk_id.isnot(None)),
        )
    )
    return result.scalars().all()


# ═══════════════════════════════════════════
#   ОБНОВЛЕНИЕ ГЕО КУРЬЕРА
# ═══════════════════════════════════════════
async def update_courier_location(
    session: AsyncSession,
    courier_id: int,
    lat: float,
    lon: float,
):
    """
    FIX (P0): заблокированный курьер не может слать гео (и не воскресает).
    FIX: убран авто-перевод в status="active" (это про модерацию, ставит только админ).
    Авто-переход courier_state: off → on оставлен (пользователь сам вышел на смену жестом).
    """
    result = await session.execute(select(Courier).where(Courier.id == courier_id))
    courier = result.scalar_one_or_none()
    if not courier:
        return False

    # FIX (P0): заблокирован — не принимаем гео
    if courier.is_blocked or courier.status == "blocked":
        return False

    courier.lat = lat
    courier.lon = lon
    courier.loc_time = helpers.now_moscow()

    # Авто-смена: off → on (пользователь прислал гео = готов работать)
    # НО status="active" НЕ ставим — это делает только админ при одобрении заявки
    if courier.courier_state == "off":
        courier.courier_state = "on"

    await session.commit()
    return True


# ═══════════════════════════════════════════
#   РАССТОЯНИЯ ДЛЯ КУРЬЕРА
# ═══════════════════════════════════════════
async def order_distance_for_courier(
    session: AsyncSession,
    order: Order,
    courier: Courier,
) -> dict:
    shop_result = await session.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = shop_result.scalar_one_or_none()

    if not shop or not shop.lat or not shop.lon:
        return {"to_shop": 999.0, "to_client": 999.0, "total": 999.0}

    to_shop = 999.0
    if courier.lat and courier.lon:
        to_shop = helpers.distance_km(
            float(courier.lat), float(courier.lon),
            float(shop.lat), float(shop.lon),
        )

    to_client = 999.0
    if order.lat and order.lon:
        to_client = helpers.distance_km(
            float(shop.lat), float(shop.lon),
            float(order.lat), float(order.lon),
        )

    return {
        "to_shop": to_shop,
        "to_client": to_client,
        "total": round(to_shop + to_client, 2),
    }


# ═══════════════════════════════════════════
#   ПРОВЕРКА ГРАФИКА РАБОТЫ МАГАЗИНА
# ═══════════════════════════════════════════
def is_shop_open(shop: Shop) -> bool:
    """
    Работает ли магазин сейчас (МСК).
    FIX: is_paused → сразу False (единая точка правды).
    FIX: fail-safe — при ошибке парсинга графика возвращаем False (а не True).
    FIX: распознаём «выходной» в любом регистре + "off" + "-".
    Учитывает ночные смены (переход через полночь).
    """
    if not shop or shop.is_paused:
        return False

    now_dt = helpers.now_moscow()
    weekday_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_key = weekday_keys[now_dt.weekday()]

    def _parse_schedule(raw: str) -> tuple[int, int] | None:
        """Парсит 'HH:MM-HH:MM' → (start_min, end_min). None если не распознано."""
        if not raw:
            return None
        s = raw.strip().lower()
        if s in ("выходной", "off", "-", "closed"):
            return None
        try:
            parts = raw.split("-")
            if len(parts) != 2:
                return None
            sh, sm = map(int, parts[0].strip().split(":"))
            eh, em = map(int, parts[1].strip().split(":"))
            return (sh * 60 + sm, eh * 60 + em)
        except Exception:
            return None

    def _is_in_range(start_min: int, end_min: int, now_min: int) -> bool:
        if start_min > end_min:  # ночная смена
            return now_min >= start_min or now_min <= end_min
        return start_min <= now_min <= end_min

    now_min = now_dt.hour * 60 + now_dt.minute

    # Приоритет: schedule (7 дней) → work_start/work_end (legacy)
    if shop.schedule:
        schedule = helpers.str_to_schedule(shop.schedule)
        if schedule:
            today_raw = schedule.get(today_key)
            # «выходной» / пусто — закрыт (в т.ч. если магазин так настроил)
            if not today_raw:
                return False
            parsed = _parse_schedule(today_raw)
            if parsed is None:
                # «выходной» / «-» / «off» — магазин закрыт в этот день
                s = str(today_raw).strip().lower()
                if s in ("выходной", "off", "-", "closed"):
                    return False
                # Не распознали формат — fail-safe закрыт
                log.warning(f"Магазин #{shop.id}: некорректный schedule[{today_key}]='{today_raw}'")
                return False
            return _is_in_range(parsed[0], parsed[1], now_min)

    # Legacy: work_start / work_end
    parsed = _parse_schedule(f"{shop.work_start or '08:00'}-{shop.work_end or '22:00'}")
    if parsed is None:
        return False  # fail-safe
    return _is_in_range(parsed[0], parsed[1], now_min)
