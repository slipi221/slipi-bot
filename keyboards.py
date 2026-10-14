# -*- coding: utf-8 -*-
"""
SLIPI — все клавиатуры (Inline-кнопки)
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config


# ═══════════════════════════════════════════
#   ХЕЛПЕРЫ
# ═══════════════════════════════════════════
def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def btn_url(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def kb(rows: list) -> InlineKeyboardMarkup:
    """rows — список списков кнопок."""
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═══════════════════════════════════════════
#   КЛИЕНТ — ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
def client_main():
    return kb([
        [btn("🛍 Каталог", "client_catalog")],
        [btn("📦 Мои заказы", "client_orders"),
         btn("❤️ Избранное", "client_favorites")],
        [btn("📅 Мои события", "client_events"),
         btn("🎁 Промокод", "client_promo")],
        [btn("💰 Мой баланс", "client_balance"),
         btn("🆘 Поддержка", "client_support")],
        [btn("ℹ️ О сервисе", "client_about")],
    ])


def client_back(to: str = "client_main"):
    return kb([[btn("🔙 Назад", to)]])


def client_geo():
    return kb([
        [btn("📍 Отправить геолокацию", "client_send_geo")],
        [btn("🏙 Показать все", "client_all_shops")],
        [btn("🔙 Назад", "client_main")],
    ])


def client_shops(shops: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    for i, s in enumerate(shops, start=1):
        builder.row(btn(f"{i}. {s['name']} ⭐ {s['rating']}", f"shop_{s['id']}"))
    nav = []
    if page > 0:
        nav.append(btn("⬅️ Пред", f"shops_page_{page - 1}"))
    nav.append(btn("🔄 Обновить", "client_catalog"))
    if len(shops) == 5:
        nav.append(btn("След ➡️", f"shops_page_{page + 1}"))
    builder.row(*nav)
    builder.row(btn("🔙 Назад", "client_main"))
    return builder.as_markup()


def shop_card(shop_id: int):
    return kb([
        [btn("💐 Товары", f"shop_products_{shop_id}")],
        [btn("🔥 Хиты", f"shop_hits_{shop_id}")],
        [btn("⭐ Отзывы", f"shop_reviews_{shop_id}")],
        [btn("❤️ Подписаться", f"shop_subscribe_{shop_id}")],
        [btn("🔙 К магазинам", "client_catalog")],
    ])


def shop_categories(shop_id: int, categories: list):
    rows = []
    for key, name, count in categories:
        rows.append([btn(f"{name} ({count})", f"cat_{shop_id}_{key}")])
    rows.append([btn("🔥 Хиты продаж", f"shop_hits_{shop_id}")])
    rows.append([btn("📦 Все товары", f"cat_{shop_id}_all")])
    rows.append([btn("🔙 Назад", f"shop_{shop_id}")])
    return kb(rows)


def products_list(shop_id: int, category: str, products: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    for i, p in enumerate(products, start=1):
        builder.row(btn(f"{i}. {p['title']} — {p['price']}₽", f"product_{p['id']}"))
    nav = []
    if page > 0:
        nav.append(btn("⬅️ Пред", f"prods_{shop_id}_{category}_{page - 1}"))
    if len(products) == 5:
        nav.append(btn("След ➡️", f"prods_{shop_id}_{category}_{page + 1}"))
    if nav:
        builder.row(*nav)
    builder.row(btn("🔙 Назад", f"shop_products_{shop_id}"))
    return builder.as_markup()


def product_card(product_id: int, in_fav: bool = False):
    fav_text = "💔 Убрать из избранного" if in_fav else "❤️ В избранное"
    return kb([
        [btn("🛒 В корзину", f"cart_add_{product_id}")],
        [btn(fav_text, f"fav_toggle_{product_id}")],
        [btn("🔙 К списку", "back_to_products")],
    ])


# ═══════════════════════════════════════════
#   КОРЗИНА
# ═══════════════════════════════════════════
def cart_view():
    return kb([
        [btn("✅ Оформить заказ", "cart_checkout")],
        [btn("✏️ Изменить кол-во", "cart_edit")],
        [btn("🗑 Удалить товар", "cart_remove_menu")],
        [btn("🔙 В меню", "client_main")],
    ])


def cart_edit(items: list):
    rows = []
    for item_id, title, qty in items:
        rows.append([
            btn(f"{title[:15]} — {qty}шт", "noop"),
            btn("➖", f"cart_minus_{item_id}"),
            btn("➕", f"cart_plus_{item_id}"),
        ])
    rows.append([btn("🔙 Готово", "cart_view")])
    return kb(rows)


def cart_remove_menu(items: list):
    rows = []
    for item_id, title in items:
        rows.append([btn(f"🗑 {title[:25]}", f"cart_del_{item_id}")])
    rows.append([btn("❌ Удалить всё", "cart_clear")])
    rows.append([btn("🔙 Назад", "cart_view")])
    return kb(rows)


def cart_empty():
    return kb([
        [btn("🛍 В каталог", "client_catalog")],
        [btn("🔙 В меню", "client_main")],
    ])


# ═══════════════════════════════════════════
#   ОФОРМЛЕНИЕ ЗАКАЗА (FSM)
# ═══════════════════════════════════════════
def order_cancel():
    return kb([[btn("❌ Отмена", "order_cancel")]])


def order_addresses(addresses: list):
    rows = []
    for a_id, title, _ in addresses:
        rows.append([btn(f"🏠 {title}", f"order_addr_{a_id}")])
    rows.append([btn("➕ Новый адрес", "order_new_addr")])
    rows.append([btn("❌ Отмена", "order_cancel")])
    return kb(rows)


def order_date():
    return kb([
        [btn("📆 Сегодня", "order_date_today")],
        [btn("📆 Завтра", "order_date_tomorrow")],
        [btn("📆 Послезавтра", "order_date_after")],
        [btn("❌ Отмена", "order_cancel")],
    ])


def order_time_period():
    rows = []
    for key, period in config.DELIVERY_SLOTS.items():
        rows.append([btn(f"{period['name']} ({period['hours']})", f"order_period_{key}")])
    rows.append([btn("❌ Отмена", "order_cancel")])
    return kb(rows)


def order_time_slot(period_key: str):
    period = config.DELIVERY_SLOTS[period_key]
    rows = []
    for slot in period["slots"]:
        rows.append([btn(f"🕒 {slot}", f"order_slot_{period_key}_{slot}")])
    rows.append([btn("🔙 Назад", "order_time_back")])
    return kb(rows)


def order_promo():
    return kb([
        [btn("⏭ Пропустить", "order_skip_promo")],
        [btn("❌ Отмена", "order_cancel")],
    ])


def order_confirm():
    return kb([
        [btn("💳 Оплатить", "order_pay")],
        [btn("✏️ Изменить", "order_edit")],
        [btn("❌ Отмена", "order_cancel")],
    ])


def order_payment():
    return kb([
        [btn("✅ Я оплатил", "order_paid")],
        [btn("❌ Отмена", "order_cancel")],
    ])


# ═══════════════════════════════════════════
#   ТРЕКИНГ ЗАКАЗА
# ═══════════════════════════════════════════
def track_order(order_id: int, courier_phone: str | None = None,
                lat: float | None = None, lon: float | None = None):
    rows = []
    if lat and lon:
        rows.append([btn_url("🗺 Открыть карту",
                             f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map")])
    if courier_phone:
        rows.append([btn_url("📞 Позвонить курьеру", f"tel:{courier_phone}")])
    rows.append([btn("🔄 Обновить", f"track_refresh_{order_id}")])
    rows.append([btn("🆘 Проблема", f"track_problem_{order_id}")])
    rows.append([btn("🔙 В меню", "client_main")])
    return kb(rows)


# ═══════════════════════════════════════════
#   ОТЗЫВ
# ═══════════════════════════════════════════
def rating_kb(target: str, order_id: int):
    rows = [
        [btn("⭐", f"rate_{target}_{order_id}_1"),
         btn("⭐⭐", f"rate_{target}_{order_id}_2"),
         btn("⭐⭐⭐", f"rate_{target}_{order_id}_3")],
        [btn("⭐⭐⭐⭐", f"rate_{target}_{order_id}_4"),
         btn("⭐⭐⭐⭐⭐", f"rate_{target}_{order_id}_5")],
    ]
    return kb(rows)


def skip_comment():
    return kb([[btn("⏭ Пропустить", "review_skip")]])


# ═══════════════════════════════════════════
#   БАЛАНС КЛИЕНТА
# ═══════════════════════════════════════════
def client_balance():
    return kb([
        [btn("💸 Вывести на карту", "balance_withdraw")],
        [btn("🛍 Потратить на заказ", "client_catalog")],
        [btn("📜 История", "balance_history")],
        [btn("🔙 Назад", "client_main")],
    ])


# ═══════════════════════════════════════════
#   ИЗБРАННОЕ
# ═══════════════════════════════════════════
def favorites_list(items: list):
    rows = []
    for i, p in enumerate(items, start=1):
        rows.append([btn(f"{i}. {p['title']}", f"product_{p['id']}")])
    rows.append([btn("🔙 Назад", "client_main")])
    return kb(rows)


# ═══════════════════════════════════════════
#   СОБЫТИЯ
# ═══════════════════════════════════════════
def events_menu():
    return kb([
        [btn("➕ Добавить событие", "event_add")],
        [btn("🗑 Удалить", "event_remove_menu")],
        [btn("🔙 Назад", "client_main")],
    ])


# ═══════════════════════════════════════════
#   МАГАЗИН — ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
def shop_main():
    return kb([
        [btn("📦 Мои товары", "shop_my_products")],
        [btn("🏷 Категории", "shop_my_categories")],
        [btn("📋 Новые заказы", "shop_new_orders")],
        [btn("📊 Статистика и финансы", "shop_stats")],
        [btn("⚙️ Настройки", "shop_settings")],
    ])


def shop_back(to: str = "shop_main"):
    return kb([[btn("🔙 Назад", to)]])


def shop_products_menu():
    return kb([
        [btn("➕ Добавить товар", "shop_add_product")],
        [btn("🔙 Назад", "shop_main")],
    ])


def shop_product_card(product_id: int, is_active: bool = True):
    toggle = "⏸ Скрыть" if is_active else "▶️ Показать"
    return kb([
        [btn("✏️ Изменить цену", f"shop_edit_price_{product_id}")],
        [btn("📸 Изменить фото", f"shop_edit_photo_{product_id}")],
        [btn(toggle, f"shop_toggle_{product_id}")],
        [btn("🗑 Удалить", f"shop_delete_{product_id}")],
        [btn("🔙 Назад", "shop_my_products")],
    ])


def shop_categories_menu():
    return kb([
        [btn("➕ Добавить категорию", "shop_cat_add")],
        [btn("➖ Убрать категорию", "shop_cat_remove")],
        [btn("🔙 Назад", "shop_main")],
    ])


def shop_categories_choice(active: list, all_cats: dict):
    rows = []
    for key, info in all_cats.items():
        mark = "✅" if key in active else "☐"
        rows.append([btn(f"{mark} {info['name']}", f"shop_cat_toggle_{key}")])
    rows.append([btn("💾 Сохранить", "shop_cat_save")])
    rows.append([btn("🔙 Назад", "shop_my_categories")])
    return kb(rows)


def shop_order_new(order_id: int):
    return kb([
        [btn("✅ Принять", f"shop_accept_{order_id}")],
        [btn("📸 Отправить фото", f"shop_send_photo_{order_id}")],
        [btn("❌ Отклонить", f"shop_reject_{order_id}")],
    ])


def shop_reject_reasons(order_id: int):
    return kb([
        [btn("💐 Нет в наличии", f"shop_reject_reason_{order_id}_out_of_stock")],
        [btn("⏰ Не успеваем", f"shop_reject_reason_{order_id}_too_long")],
        [btn("🚫 Технические проблемы", f"shop_reject_reason_{order_id}_tech")],
        [btn("💬 Другое", f"shop_reject_reason_{order_id}_other")],
        [btn("🔙 Назад", f"shop_new_orders")],
    ])


def shop_stats_menu():
    return kb([
        [btn("📥 Запросить выплату", "shop_request_payout")],
        [btn("📅 За неделю", "shop_stats_week")],
        [btn("📅 За месяц", "shop_stats_month")],
        [btn("🔙 Назад", "shop_main")],
    ])


def shop_settings_menu():
    return kb([
        [btn("✏️ Название", "shop_set_name")],
        [btn("✏️ Адрес", "shop_set_address")],
        [btn("✏️ Телефон", "shop_set_phone")],
        [btn("📍 Обновить гео", "shop_set_geo")],
        [btn("⏸ Приостановить", "shop_pause")],
        [btn("🔙 Назад", "shop_main")],
    ])


# ═══════════════════════════════════════════
#   КУРЬЕР — ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
def courier_main_on_shift():
    return kb([
        [btn("📦 Свободные заказы", "courier_free_orders")],
        [btn("🚗 Мои активные", "courier_my_orders")],
        [btn("💰 Баланс и вывод", "courier_balance"),
         btn("📊 Статистика", "courier_stats")],
        [btn("🎁 Рефералка", "courier_referral"),
         btn("📅 Мои смены", "courier_shifts")],
        [btn("🔴 Уйти со смены", "courier_off_shift")],
    ])


def courier_main_off_shift():
    return kb([
        [btn("🟢 Выйти на смену", "courier_on_shift")],
        [btn("💰 Баланс и вывод", "courier_balance"),
         btn("📊 Статистика", "courier_stats")],
        [btn("🎁 Рефералка", "courier_referral"),
         btn("📅 Мои смены", "courier_shifts")],
    ])


def courier_back(to: str = "courier_menu"):
    return kb([[btn("🔙 Назад", to)]])


def courier_free_orders_list(orders: list, page: int = 0):
    rows = []
    for o in orders:
        rows.append([btn(f"🔥 #{o['id']} — {o['fee']}₽ — {o['distance']}км",
                         f"courier_order_{o['id']}")])
    nav = []
    if page > 0:
        nav.append(btn("⬅️", f"courier_page_{page - 1}"))
    nav.append(btn("🔄", "courier_free_orders"))
    if len(orders) == 3:
        nav.append(btn("➡️", f"courier_page_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn("🔙 В меню", "courier_menu")])
    return kb(rows)


def courier_order_view(order_id: int):
    return kb([
        [btn("🤝 Взять заказ", f"courier_take_{order_id}")],
        [btn("🔄 Обновить", "courier_free_orders")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_active_order(order_id: int, status: str):
    rows = []
    if status == "going":
        rows.append([btn("📦 Забрал", f"courier_picked_{order_id}")])
    elif status == "picked":
        rows.append([btn("📍 Еду к клиенту", f"courier_delivering_{order_id}")])
    elif status == "delivering":
        rows.append([btn("📍 У клиента", f"courier_at_client_{order_id}")])
    elif status == "at_client":
        rows.append([btn("✅ Доставлено", f"courier_done_{order_id}")])
    rows.append([btn("🗺 Маршрут", f"courier_map_{order_id}")])
    rows.append([btn("❌ Проблема", f"courier_problem_{order_id}")])
    rows.append([btn("🔙 Назад", "courier_my_orders")])
    return kb(rows)


def courier_balance_menu():
    return kb([
        [btn("💸 Обычный вывод", "courier_withdraw_normal")],
        [btn("⚡ Мгновенный вывод", "courier_withdraw_instant")],
        [btn("📜 История", "courier_tx_history")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_stats_menu():
    return kb([
        [btn("📅 За неделю", "courier_stats_week")],
        [btn("📅 За месяц", "courier_stats_month")],
        [btn("🏆 Достижения", "courier_achievements")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_referral_menu(ref_link: str):
    return kb([
        [btn_url("📤 Поделиться", f"https://t.me/share/url?url={ref_link}")],
        [btn("📋 Скопировать", "courier_ref_copy")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_shifts_menu():
    return kb([
        [btn("📅 Записаться на смену", "courier_book_shift")],
        [btn("📋 Мои смены", "courier_my_shifts")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_shift_slots():
    rows = []
    for key, info in config.SHIFT_SLOTS.items():
        rows.append([btn(f"{info['name']} ({info['start']}–{info['end']})",
                         f"courier_shift_book_{key}")])
    rows.append([btn("🔙 Назад", "courier_shifts")])
    return kb(rows)


# ═══════════════════════════════════════════
#   АДМИН — ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
def admin_main():
    return kb([
        [btn("📨 Заявки", "admin_requests")],
        [btn("🏪 Магазины", "admin_shops"),
         btn("🚴 Курьеры", "admin_couriers")],
        [btn("💳 Переводы", "admin_payments"),
         btn("💰 Финансы", "admin_finance")],
        [btn("⏰ Зависшие заказы", "admin_stuck_orders")],
        [btn("🎁 Промокоды", "admin_promos"),
         btn("🆘 Жалобы", "admin_complaints")],
        [btn("📢 Рассылка", "admin_broadcast")],
        [btn("📊 Аналитика", "admin_analytics"),
         btn("⚙️ Настройки", "admin_settings")],
        [btn("📜 Логи", "admin_logs")],
    ])


def admin_back(to: str = "admin_main"):
    return kb([[btn("🔙 Назад", to)]])


# ═══════════════════════════════════════════
#   АДМИН — ЗАЯВКИ
# ═══════════════════════════════════════════
def admin_requests_menu():
    return kb([
        [btn("🏪 Магазины", "admin_req_shops")],
        [btn("🚴 Курьеры", "admin_req_couriers")],
        [btn("💸 Выплаты", "admin_req_payouts")],
        [btn("🕒 Смены", "admin_req_shifts")],
        [btn("🔙 Назад", "admin_main")],
    ])


def admin_approve_shop(shop_id: int):
    return kb([
        [btn("✅ Одобрить", f"admin_shop_ok_{shop_id}")],
        [btn("❌ Отклонить", f"admin_shop_no_{shop_id}")],
    ])


def admin_approve_courier(courier_id: int):
    return kb([
        [btn("✅ Одобрить", f"admin_cour_ok_{courier_id}")],
        [btn("❌ Отклонить", f"admin_cour_no_{courier_id}")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ПЕРЕВОДЫ
# ═══════════════════════════════════════════
def admin_payments_menu():
    return kb([
        [btn("📥 Входящие", "admin_pay_incoming")],
        [btn("📤 Выплаты", "admin_pay_outgoing")],
        [btn("📜 История", "admin_pay_history")],
        [btn("⚡ Быстрое подтверждение", "admin_pay_fast")],
        [btn("💸 Возвраты", "admin_pay_refunds")],
        [btn("🔙 Назад", "admin_main")],
    ])


def admin_confirm_payment(order_id: int):
    return kb([
        [btn("✅ Подтвердить", f"admin_pay_ok_{order_id}")],
        [btn("❌ Отклонить", f"admin_pay_no_{order_id}")],
        [btn("🔙 Назад", "admin_payments")],
    ])


def admin_payout_actions(payout_id: int):
    return kb([
        [btn("💳 Перевести", f"admin_payout_transfer_{payout_id}")],
        [btn("✅ Подтвердить", f"admin_payout_ok_{payout_id}")],
        [btn("❌ Отклонить", f"admin_payout_no_{payout_id}")],
        [btn("🔙 Назад", "admin_payments")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — НАСТРОЙКИ
# ═══════════════════════════════════════════
def admin_settings_menu():
    return kb([
        [btn("✏️ Комиссия", "admin_set_commission")],
        [btn("✏️ Мин. вывод курьера", "admin_set_min_withdraw")],
        [btn("✏️ Бонус за 10 заказов", "admin_set_bonus")],
        [btn("✏️ Часы работы", "admin_set_hours")],
        [btn("🔙 Назад", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ЗАВИСШИЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
def admin_stuck_order(order_id: int):
    return kb([
        [btn("💰 Поднять ставку", f"admin_boost_{order_id}")],
        [btn("📞 Магазину", f"admin_call_shop_{order_id}")],
        [btn("❌ Отменить заказ", f"admin_cancel_order_{order_id}")],
        [btn("🔙 Назад", "admin_stuck_orders")],
    ])


def admin_boost_amount(order_id: int):
    return kb([
        [btn("+50 ₽", f"admin_boost_set_{order_id}_50")],
        [btn("+100 ₽", f"admin_boost_set_{order_id}_100")],
        [btn("+200 ₽", f"admin_boost_set_{order_id}_200")],
        [btn("✏️ Своя сумма", f"admin_boost_custom_{order_id}")],
        [btn("🔙 Назад", f"admin_boost_back_{order_id}")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — РАССЫЛКА
# ═══════════════════════════════════════════
def admin_broadcast_menu():
    return kb([
        [btn("👥 Клиентам", "admin_bc_clients")],
        [btn("🚴 Курьерам", "admin_bc_couriers")],
        [btn("🏪 Магазинам", "admin_bc_shops")],
        [btn("🔙 Назад", "admin_main")],
    ])


def admin_cancel():
    return kb([[btn("❌ Отмена", "admin_main")]])


# ═══════════════════════════════════════════
#   ОБЩИЕ
# ═══════════════════════════════════════════
def cancel_kb(to: str = "client_main"):
    return kb([[btn("❌ Отмена", to)]])


def skip_kb(to: str = "client_main"):
    return kb([
        [btn("⏭ Пропустить", "skip")],
        [btn("❌ Отмена", to)],
    ])
