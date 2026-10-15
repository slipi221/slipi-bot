# -*- coding: utf-8 -*-
"""
SLIPI — единые объекты ботов
"""
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config


def _make(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


bot_client  = _make(config.CLIENT_TOKEN)
bot_shop    = _make(config.SHOP_TOKEN)
bot_courier = _make(config.COURIER_TOKEN)
bot_admin   = _make(config.ADMIN_TOKEN)
