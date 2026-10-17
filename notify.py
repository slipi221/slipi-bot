# -*- coding: utf-8 -*-
"""
SLIPI — единая система уведомлений (Outbox)
"""
import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardMarkup

from models import Outbox, Shop, Client, Courier
from bots import bot_client, bot_shop, bot_courier, bot_admin

async def _get_tg_id(session: AsyncSession, r_type: str, r_id: int) -> int | None:
    """Достает tg_id получателя по типу и ID."""
    if r_type == "client":
        res = await session.execute(select(Client.tg_id).where(Client.id == r_id))
    elif r_type == "shop":
        res = await session.execute(select(Shop.tg_id).where(Shop.id == r_id))
    elif r_type == "courier":
        res = await session.execute(select(Courier.tg_id).where(Courier.id == r_id))
    else:
        return None
    return res.scalar_one_or_none()

def _get_bot(r_type: str):
    if r_type == "client": return bot_client
    if r_type == "shop": return bot_shop
    if r_type == "courier": return bot_courier
    return bot_admin

async def send_notification(
    session: AsyncSession,
    recipient_type: str,
    recipient_id: int,
    text: str,
    reply_markup: dict = None,
    force_outbox: bool = False
):
    """
    Отправляет уведомление. Если force_outbox=True (или магазин спит), сохраняет в БД.
    """
    kb_json = json.dumps(reply_markup) if reply_markup else None
    
    # 1. Сохраняем в Outbox, если принудительно или если это магазин не на смене
    if force_outbox:
        outbox = Outbox(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            message_text=text,
            reply_markup=kb_json,
            status="pending"
        )
        session.add(outbox)
        await session.commit()
        return

    # 2. Пытаемся отправить сразу
    tg_id = await _get_tg_id(session, recipient_type, recipient_id)
    
    # Если нет tg_id, сохраняем в Outbox (на случай если привяжет позже)
    if not tg_id:
        outbox = Outbox(
            recipient_type=recipient_type, recipient_id=recipient_id,
            message_text=text, reply_markup=kb_json, status="pending"
        )
        session.add(outbox)
        await session.commit()
        return

    bot = _get_bot(recipient_type)
    try:
        # Конвертируем JSON обратно в InlineKeyboardMarkup
        kb = None
        if reply_markup:
            kb = InlineKeyboardMarkup(**reply_markup)
            
        await bot.send_message(chat_id=tg_id, text=text, reply_markup=kb)
    except Exception:
        # Если не смогли доставить (заблокировали бота), кладем в Outbox
        outbox = Outbox(
            recipient_type=recipient_type, recipient_id=recipient_id,
            message_text=text, reply_markup=kb_json, status="pending"
        )
        session.add(outbox)
        await session.commit()

async def flush_outbox_for_shop(session: AsyncSession, shop_id: int):
    """
    Отправляет все накопленные сообщения магазину (когда он выходит на смену).
    ИСПРАВЛЕНО (Баг #3).
    """
    res = await session.execute(
        select(Outbox).where(
            Outbox.recipient_type == "shop",
            Outbox.recipient_id == shop_id,
            Outbox.status == "pending"
        ).order_by(Outbox.created_at.asc())
    )
    messages = res.scalars().all()
    
    if not messages:
        return

    tg_id = await _get_tg_id(session, "shop", shop_id)
    if not tg_id:
        return

    for msg in messages:
        try:
            markup = json.loads(msg.reply_markup) if msg.reply_markup else None
            kb = InlineKeyboardMarkup(**markup) if markup else None
            
            await bot_shop.send_message(chat_id=tg_id, text=msg.message_text, reply_markup=kb)
            msg.status = "sent"
            msg.sent_at = datetime.now()
        except Exception as e:
            print(f"Ошибка отправки из Outbox магазину {shop_id}: {e}")
    
    await session.commit()
