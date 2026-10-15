# -*- coding: utf-8 -*-
"""
SLIPI — FSM-состояния
"""
from aiogram.fsm.state import State, StatesGroup


# ═══════════════════════════════════════════
#   КЛИЕНТ — ОФОРМЛЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
class OrderFSM(StatesGroup):
    address         = State()
    save_address    = State()
    address_title   = State()
    client_name     = State()
    client_phone    = State()
    date            = State()
    time_period     = State()
    time_slot       = State()
    promo           = State()
    delivery_photo  = State()
    confirm         = State()
    payment         = State()


class ClientFSM(StatesGroup):
    promo_input       = State()
    review_comment    = State()
    withdraw_amount   = State()
    withdraw_card     = State()
    event_whom        = State()
    event_date        = State()
    event_type        = State()
    support_msg       = State()
    chat_message      = State()
    address_manage    = State()
    address_add       = State()
    address_add_title = State()


# ═══════════════════════════════════════════
#   МАГАЗИН — РЕГИСТРАЦИЯ
# ═══════════════════════════════════════════
class ShopReg(StatesGroup):
    name         = State()
    address      = State()
    phone        = State()
    telegram     = State()
    vk           = State()
    owner_name   = State()
    geo          = State()
    categories   = State()


# ═══════════════════════════════════════════
#   МАГАЗИН — ТОВАРЫ
# ═══════════════════════════════════════════
class ShopProduct(StatesGroup):
    photo        = State()
    title        = State()
    description  = State()
    price        = State()
    category     = State()


class ShopEdit(StatesGroup):
    price        = State()
    photo        = State()
    name         = State()
    address      = State()
    phone        = State()
    geo          = State()
    payout       = State()
    open_time    = State()
    close_time   = State()
    support_msg  = State()
    chat_message = State()


# ═══════════════════════════════════════════
#   МАГАЗИН — СВОЯ ДОСТАВКА
# ═══════════════════════════════════════════
class ShopDelivery(StatesGroup):
    address       = State()
    client_name   = State()
    client_phone  = State()
    date          = State()
    time_period   = State()
    time_slot     = State()
    photo         = State()
    shop_comment  = State()
    client_comment = State()
    need_photo    = State()
    confirm       = State()
    payment       = State()


# ═══════════════════════════════════════════
#   КУРЬЕР — РЕГИСТРАЦИЯ
# ═══════════════════════════════════════════
class CourierReg(StatesGroup):
    name         = State()
    phone        = State()
    city         = State()
    transport    = State()
    card         = State()
    referral     = State()


# ═══════════════════════════════════════════
#   КУРЬЕР — РАБОТА
# ═══════════════════════════════════════════
class CourierFSM(StatesGroup):
    withdraw_amount  = State()
    problem_reason   = State()
    delivery_photo   = State()
    chat_message     = State()
    support_msg      = State()


# ═══════════════════════════════════════════
#   АДМИН
# ═══════════════════════════════════════════
class AdminFSM(StatesGroup):
    set_commission    = State()
    set_min_withdraw  = State()
    set_bonus         = State()
    set_hours         = State()

    broadcast_text    = State()
    broadcast_confirm = State()

    promo_code        = State()
    promo_type        = State()
    promo_value       = State()
    promo_uses        = State()

    refund_amount     = State()
    boost_custom      = State()

    reply_to_client   = State()

    # Блокировка / разблокировка по ID
    block_by_id       = State()
    unblock_by_id     = State()

    # Пополнение баланса
    topup_shop_id     = State()
    topup_amount      = State()
