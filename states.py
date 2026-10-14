# -*- coding: utf-8 -*-
"""
SLIPI — FSM-состояния
"""
from aiogram.fsm.state import State, StatesGroup


# ═══════════════════════════════════════════
#   КЛИЕНТ — ОФОРМЛЕНИЕ ЗАКАЗА
# ═══════════════════════════════════════════
class OrderFSM(StatesGroup):
    address      = State()   # адрес доставки
    client_name  = State()   # имя получателя
    client_phone = State()   # телефон получателя
    date         = State()   # дата доставки
    time_period  = State()   # период (утро/день/вечер)
    time_slot    = State()   # конкретный слот
    promo        = State()   # промокод
    confirm      = State()   # подтверждение
    payment      = State()   # оплата


# ═══════════════════════════════════════════
#   КЛИЕНТ — ПРОЧЕЕ
# ═══════════════════════════════════════════
class ClientFSM(StatesGroup):
    promo_input      = State()   # ввод промокода
    review_comment   = State()   # комментарий к отзыву
    withdraw_amount  = State()   # сумма вывода с баланса
    withdraw_card    = State()   # номер карты для вывода
    event_add        = State()   # добавление события
    support_msg      = State()   # сообщение в поддержку


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
    geo          = State()   # геолокация магазина
    categories   = State()   # выбор категорий


# ═══════════════════════════════════════════
#   МАГАЗИН — РАБОТА С ТОВАРАМИ
# ═══════════════════════════════════════════
class ShopProduct(StatesGroup):
    photo        = State()   # фото
    title        = State()   # название
    description  = State()   # описание
    price        = State()   # цена
    category     = State()   # категория
    confirm      = State()   # подтверждение


class ShopEdit(StatesGroup):
    price        = State()   # правка цены
    photo        = State()   # правка фото
    name         = State()   # правка названия
    address      = State()   # правка адреса
    phone        = State()   # правка телефона
    geo          = State()   # обновление гео
    payout       = State()   # запрос выплаты


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
    verify       = State()   # проверка телефона (код)


# ═══════════════════════════════════════════
#   КУРЬЕР — РАБОТА
# ═══════════════════════════════════════════
class CourierFSM(StatesGroup):
    withdraw_amount = State()   # сумма вывода
    problem_reason  = State()   # причина проблемы
    shift_book      = State()   # запись на смену


# ═══════════════════════════════════════════
#   АДМИН — РАЗНОЕ
# ═══════════════════════════════════════════
class AdminFSM(StatesGroup):
    # Настройки
    set_commission    = State()
    set_min_withdraw  = State()
    set_bonus         = State()
    set_hours         = State()

    # Рассылка
    broadcast_text    = State()
    broadcast_confirm = State()

    # Промокоды
    promo_code        = State()
    promo_type        = State()
    promo_value       = State()
    promo_uses        = State()
    promo_until       = State()

    # Возвраты
    refund_amount     = State()

    # Boost
    boost_custom      = State()

    # Отклонение заявок
    reject_reason     = State()

    # Ответ клиенту
    reply_to_client   = State()
