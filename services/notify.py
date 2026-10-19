# -*- coding: utf-8 -*-
"""
Flowers Express — единая система уведомлений (Outbox)

FIX: TelegramForbiddenError → bot_blocked (не is_blocked — не перетираем бан админа).
FIX Feature 2: Outbox.platform (tg/vk), универсальный _get_recipient, VK-адаптер.
FIX: reply_markup корректно обрабатывает InlineKeyboardMarkup / dict / str.
FIX: log.exception вместо print, не молчим на ошибках.
NEW: flush_outbox — универсальный для всех ролей.
NEW Feature 1: log_action_to_channel() — хелпер для middleware (пишет в канал роли).
"""
import json
import asyncio
import logging
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardMarkup
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from models import Outbox, Shop, Client, Courier
from utils import helpers
from bots import bot_client, bot_shop, bot_courier, bot_admin
import config

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#   ПОЛУЧАТЕЛЬ: (platform, external_id)
# ═══════════════════════════════════════════
async def _get_recipient(session: AsyncSession, r_type: str, r_id: int) -> tuple[str, int] | tuple[None, None]:
    """
    Возвращает (platform, external_id):
    - ("tg", tg_id) — если у получателя есть tg_id
    - ("vk", vk_id) — если только vk_id (Feature 2)
    - (None, None) — не найден
    Для admin: ("tg", ADMIN_CHANNEL_ID) если задан, иначе ("tg", ADMIN_ID).
    """
    if r_type == "client":
        r = await session.execute(select(Client.tg_id, Client.vk_id).where(Client.id == r_id))
    elif r_type == "shop":
        r = await session.execute(select(Shop.tg_id, Shop.vk_id).where(Shop.id == r_id))
    elif r_type == "courier":
        r = await session.execute(select(Courier.tg_id, Courier.vk_id).where(Courier.id == r_id))
    elif r_type == "admin":
        if config.ADMIN_CHANNEL_ID:
            try:
                return ("tg", int(config.ADMIN_CHANNEL_ID))
            except ValueError:
                pass
        return ("tg", config.ADMIN_ID) if config.ADMIN_ID else (None, None)
    else:
        return (None, None)

    row = r.first()
    if not row:
        return (None, None)
    tg_id, vk_id = row
    if tg_id:
        return ("tg", tg_id)
    if vk_id:
        return ("vk", vk_id)
    return (None, None)


def _get_bot(r_type: str):
    if r_type == "client": return bot_client
    if r_type == "shop": return bot_shop
    if r_type == "courier": return bot_courier
    return bot_admin


# ═══════════════════════════════════════════
#   КЛАВИАТУРА: нормализуем любой формат в InlineKeyboardMarkup
# ═══════════════════════════════════════════
def _normalize_markup(reply_markup) -> tuple[Optional[InlineKeyboardMarkup], Optional[str]]:
    """
    Возвращает (kb_obj, kb_json):
    - kb_obj — InlineKeyboardMarkup для отправки
    - kb_json — строка для сохранения в БД
    Принимает: InlineKeyboardMarkup | dict | str | None.
    """
    if reply_markup is None:
        return (None, None)

    if isinstance(reply_markup, InlineKeyboardMarkup):
        try:
            kb_json = json.dumps(reply_markup.model_dump(exclude_none=True), ensure_ascii=False)
        except Exception:
            kb_json = None
        return (reply_markup, kb_json)

    if isinstance(reply_markup, dict):
        try:
            kb = InlineKeyboardMarkup(**reply_markup)
            kb_json = json.dumps(reply_markup, ensure_ascii=False)
            return (kb, kb_json)
        except Exception:
            return (None, None)

    if isinstance(reply_markup, str):
        try:
            data = json.loads(reply_markup)
            kb = InlineKeyboardMarkup(**data)
            return (kb, reply_markup)
        except Exception:
            return (None, None)

    return (None, None)


# ═══════════════════════════════════════════
#   ОТПРАВКА
# ═══════════════════════════════════════════
async def _send_via_platform(
    platform: str,
    external_id: int,
    text: str,
    kb: Optional[InlineKeyboardMarkup],
    photo_id: Optional[str],
):
    """Отправляет через TG или VK. Для VK — заглушка (см. services/vk_send.py)."""
    if platform == "vk":
        try:
            from services import vk_send
            await vk_send.send_message(external_id, text, photo_id=photo_id)
            return True
        except ImportError:
            log.warning("⚠️ services/vk_send.py не найден — VK-отправка пропущена")
            return False
        except Exception as e:
            log.error(f"VK отправка #{external_id}: {e}")
            return False

    # TG
    bot = _get_bot(  # роль влияет только на бота — но фактически TG API одинаков
        "client"  # placeholder, ниже переопределяется через external_id? нет — используем bot_admin как fallback
    )
    # На самом деле для TG нужен правильный бот по роли — его передаёт caller.
    # Здесь вызывается из send_notification, где bot уже определён.
    return False  # ← сюда не попадаем, см. send_notification


async def send_notification(
    session: AsyncSession,
    recipient_type: str,
    recipient_id: int,
    text: str,
    reply_markup=None,
    photo_id: str = None,
    force_outbox: bool = False,
):
    """
    Отправляет уведомление.
    force_outbox=True — сразу в БД (для отложенных, например магазин не на смене).
    Нет tg_id/vk_id — в БД.
    """
    kb, kb_json = _normalize_markup(reply_markup)

    # 1. Принудительно в Outbox
    if force_outbox:
        session.add(Outbox(
            recipient_type=recipient_type, recipient_id=recipient_id,
            platform="tg",  # определим при flush
            message_text=text, reply_markup=kb_json, photo_id=photo_id,
            status="pending",
        ))
        await session.commit()
        return

    # 2. Получаем платформу и ID
    platform, external_id = await _get_recipient(session, recipient_type, recipient_id)

    if not platform:
        # Нет ID — в Outbox
        session.add(Outbox(
            recipient_type=recipient_type, recipient_id=recipient_id,
            platform="tg",
            message_text=text, reply_markup=kb_json, photo_id=photo_id,
            status="pending",
        ))
        await session.commit()
        return

    # 3. Отправка
    try:
        if platform == "vk":
            from services import vk_send
            await vk_send.send_message(external_id, text, photo_id=photo_id)
        else:
            bot = _get_bot(recipient_type)
            if photo_id:
                await bot.send_photo(chat_id=external_id, photo=photo_id, caption=text, reply_markup=kb)
            else:
                await bot.send_message(chat_id=external_id, text=text, reply_markup=kb)

    except TelegramForbiddenError:
        # FIX: bot_blocked, НЕ is_blocked (не перетираем бан админа)
        log.warning(f"🚫 {recipient_type} #{recipient_id} заблокировал бота")
        if recipient_type == "client":
            await session.execute(update(Client).where(Client.id == recipient_id).values(bot_blocked=True))
        elif recipient_type == "courier":
            await session.execute(update(Courier).where(Courier.id == recipient_id).values(bot_blocked=True))
        elif recipient_type == "shop":
            await session.execute(update(Shop).where(Shop.id == recipient_id).values(is_paused=True))
        await session.commit()

    except TelegramBadRequest as e:
        log.error(f"TelegramBadRequest {recipient_type} #{recipient_id}: {e}")
        if photo_id and ("wrong file" in str(e).lower() or "image" in str(e).lower()):
            # Fallback: пробуем без фото
            try:
                bot = _get_bot(recipient_type)
                await bot.send_message(chat_id=external_id, text=text, reply_markup=kb)
                return
            except Exception as e2:
                log.error(f"Fallback без фото тоже упал: {e2}")
        # В Outbox
        session.add(Outbox(
            recipient_type=recipient_type, recipient_id=recipient_id,
            platform=platform,
            message_text=text, reply_markup=kb_json, photo_id=photo_id, status="pending",
        ))
        await session.commit()

    except Exception as e:
        log.exception(f"Неизвестная ошибка отправки {recipient_type} #{recipient_id}: {e}")
        session.add(Outbox(
            recipient_type=recipient_type, recipient_id=recipient_id,
            platform=platform,
            message_text=text, reply_markup=kb_json, photo_id=photo_id, status="pending",
        ))
        await session.commit()


# ═══════════════════════════════════════════
#   FLUSH OUTBOX (универсальный)
# ═══════════════════════════════════════════
async def flush_outbox(session: AsyncSession, recipient_type: str, recipient_id: int):
    """
    Отправляет все pending-сообщения получателю.
    FIX: универсально для client/shop/courier/admin.
    """
    res = await session.execute(
        select(Outbox).where(
            Outbox.recipient_type == recipient_type,
            Outbox.recipient_id == recipient_id,
            Outbox.status == "pending",
        ).order_by(Outbox.created_at.asc())
    )
    messages = res.scalars().all()
    if not messages:
        return 0

    platform, external_id = await _get_recipient(session, recipient_type, recipient_id)
    if not platform:
        return 0

    sent_count = 0
    for msg in messages:
        try:
            kb, _ = _normalize_markup(msg.reply_markup)

            if platform == "vk":
                from services import vk_send
                await vk_send.send_message(external_id, msg.message_text, photo_id=msg.photo_id)
            else:
                bot = _get_bot(recipient_type)
                if msg.photo_id:
                    await bot.send_photo(chat_id=external_id, photo=msg.photo_id, caption=msg.message_text, reply_markup=kb)
                else:
                    await bot.send_message(chat_id=external_id, text=msg.message_text, reply_markup=kb)

            msg.status = "sent"
            msg.sent_at = helpers.now_moscow()
            msg.platform = platform
            sent_count += 1
            await asyncio.sleep(0.05)  # rate-limit
        except Exception as e:
            log.error(f"Outbox #{msg.id} ({recipient_type} #{recipient_id}): {e}")
            msg.status = "failed"

    await session.commit()
    return sent_count


async def flush_outbox_for_shop(session: AsyncSession, shop_id: int):
    """Совместимость: обёртка над flush_outbox."""
    return await flush_outbox(session, "shop", shop_id)


# ═══════════════════════════════════════════
#   FEATURE 1: логирование в канал роли
# ═══════════════════════════════════════════
CHANNEL_BY_ROLE = {
    "client":  lambda: config.ADMIN_CHANNEL_ID_CLIENT,
    "shop":    lambda: config.ADMIN_CHANNEL_ID_SHOP,
    "courier": lambda: config.ADMIN_CHANNEL_ID_COURIER,
    "admin":   lambda: config.ADMIN_CHANNEL_ID_ADMIN,
}


async def log_action_to_channel(role: str, user_id: int, action: str, extra: str = None):
    """
    Feature 1: пишет лог в канал роли (4 отдельных канала).
    Используется middleware. Батчинг НЕ делаем здесь — делаем в middleware.
    """
    channel = CHANNEL_BY_ROLE.get(role, lambda: config.ADMIN_CHANNEL_ID)()
    if not channel:
        return
    text = f"[{role.upper()}] #{user_id} → {action}"
    if extra:
        text += f"\n{extra}"
    try:
        await bot_admin.send_message(channel, text)
    except Exception as e:
        log.debug(f"Лог в канал не отправлен: {e}")
