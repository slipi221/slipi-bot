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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb(to: str = "client_main"):
    return kb([[btn("❌ Отмена", to)]])


# ═══════════════════════════════════════════
#   КЛИЕНТ — ГЛАВНОЕ
# ═══════════════════════════════════════════
def client_main():
    return kb([
        [btn("🛍 Каталог", "client_catalog")],
        [btn("🛒 Корзина", "client_cart")],
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


def shop_card(shop_id: int, is_subscribed: bool = False):
    sub = "💔 Отписаться" if is_subscribed else "❤️ Подписаться"
    return kb([
        [btn("💐 Товары", f"shop_products_{shop_id}")],
        [btn("🔥 Хиты", f"shop_hits_{shop_id}"),
         btn("⭐ Отзывы", f"shop_reviews_{shop_id}")],
        [btn("📞 Позвонить", f"shop_call_{shop_id}")],
        [btn(sub, f"shop_subscribe_{shop_id}")],
        [btn("🔙 К магазинам", "client_catalog")],
    ])


def shop_categories(shop_id: int, categories: list):
    rows = []
    for key, name, count in categories:
        rows.append([btn(f"{name} ({count})", f"cat_{shop_id}_{key}")])
    rows.append([btn("📦 Все товары", f"cat_{shop_id}_all")])
    rows.append([btn("🔙 Назад", f"shop_{shop_id}")])
    return kb(rows)


def products_list(shop_id: int, category: str, products: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    for i, p in enumerate(products, start=1):
        builder.row(btn(f"{i}. {p['title']} — {p['price']}", f"product_{p['id']}"))
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
    fav = "💔 Убрать" if in_fav else "❤️ В избранное"
    return kb([
        [btn("🛒 В корзину", f"cart_add_{product_id}")],
        [btn(fav, f"fav_toggle_{product_id}")],
        [btn("🛒 Моя корзина", "client_cart")],
        [btn("🔙 В каталог", "client_catalog")],
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
#   ОФОРМЛЕНИЕ ЗАКАЗА
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


def order_save_address():
    return kb([
        [btn("🏠 Дом", "save_addr_Дом"), btn("🏢 Работа", "save_addr_Работа")],
        [btn("❤️ Любимый", "save_addr_Любимый"), btn("✏️ Своё", "save_addr_custom")],
        [btn("⏭ Не сохранять", "save_addr_no")],
    ])


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


def order_delivery_photo():
    return kb([
        [btn("✅ Да, нужно фото", "order_photo_yes")],
        [btn("⏭ Нет, спасибо", "order_photo_no")],
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
def track_order(order_id: int, status: str, courier_phone: str = None,
                lat: float = None, lon: float = None):
    rows = []
    if lat and lon and status in ("delivering", "picked", "at_client", "going"):
        rows.append([btn_url("🗺 Карта курьера",
                             f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map")])
    if courier_phone and status in ("going", "picked", "delivering", "at_client"):
        rows.append([btn_url("📞 Позвонить курьеру", f"tel:{courier_phone}")])
        rows.append([btn("💬 Написать курьеру", f"chat_courier_{order_id}")])
    if status == "pending":
        rows.append([btn("❌ Отменить заказ", f"track_cancel_{order_id}")])
    if status in ("pending", "wait"):
        rows.append([btn("✏️ Изменить заказ", f"track_edit_{order_id}")])
        rows.append([btn("💬 Написать магазину", f"chat_shop_{order_id}")])
    rows.append([btn("🔄 Обновить", f"track_refresh_{order_id}")])
    rows.append([btn("🆘 Проблема", f"track_problem_{order_id}")])
    rows.append([btn("🔙 В меню", "client_main")])
    return kb(rows)


def cancel_confirm(order_id: int):
    return kb([
        [btn("✅ Да, отменить", f"track_cancel_yes_{order_id}")],
        [btn("❌ Нет, оставить", f"track_refresh_{order_id}")],
    ])


# Редактирование заказа
def order_edit_menu(order_id: int):
    return kb([
        [btn("📍 Адрес", f"oe_addr_{order_id}")],
        [btn("👤 Имя получателя", f"oe_name_{order_id}")],
        [btn("📞 Телефон", f"oe_phone_{order_id}")],
        [btn("🕒 Время", f"oe_time_{order_id}")],
        [btn("💬 Комментарий", f"oe_comment_{order_id}")],
        [btn("🔙 Назад", f"track_refresh_{order_id}")],
    ])


# ═══════════════════════════════════════════
#   ОТЗЫВ
# ═══════════════════════════════════════════
def rating_kb(target: str, order_id: int):
    return kb([
        [btn("⭐", f"rate_{target}_{order_id}_1"),
         btn("⭐⭐", f"rate_{target}_{order_id}_2"),
         btn("⭐⭐⭐", f"rate_{target}_{order_id}_3")],
        [btn("⭐⭐⭐⭐", f"rate_{target}_{order_id}_4"),
         btn("⭐⭐⭐⭐⭐", f"rate_{target}_{order_id}_5")],
        [btn("⏭ Пропустить", f"rate_skip_{target}_{order_id}")],
    ])


def skip_comment():
    return kb([[btn("⏭ Пропустить", "review_skip")]])


# ═══════════════════════════════════════════
#   МОИ ЗАКАЗЫ
# ═══════════════════════════════════════════
def orders_list(orders: list):
    rows = []
    for o in orders[:10]:
        em = config.STATUS_EMOJI.get(o["status"], "❓")
        if o.get("can_rate"):
            rows.append([btn(f"{em} #{o['id']} — {o['price']} — ⭐ Оценить", f"rate_start_{o['id']}")])
        else:
            rows.append([btn(f"{em} #{o['id']} — {o['price']}", f"track_refresh_{o['id']}")])
    rows.append([btn("🔙 Назад", "client_main")])
    return kb(rows)


# ═══════════════════════════════════════════
#   БАЛАНС
# ═══════════════════════════════════════════
def client_balance():
    return kb([
        [btn("💸 Вывести на карту", "balance_withdraw")],
        [btn("🛍 Потратить на заказ", "client_catalog")],
        [btn("📜 История", "balance_history")],
        [btn("🔙 Назад", "client_main")],
    ])


def withdraw_method():
    return kb([
        [btn("💳 На карту", "wd_card")],
        [btn("📱 По СБП", "wd_sbp")],
        [btn("❌ Отмена", "client_balance")],
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
        [btn("🔙 Назад", "client_main")],
    ])


def event_whom():
    return kb([
        [btn("👩 Мама", "event_whom_Мама"), btn("👨 Папа", "event_whom_Папа")],
        [btn("💑 Любимая", "event_whom_Любимая"), btn("👶 Ребёнок", "event_whom_Ребёнок")],
        [btn("✏️ Своё", "event_whom_custom")],
        [btn("❌ Отмена", "client_main")],
    ])


def event_type():
    return kb([
        [btn("🎂 День рождения", "event_type_День рождения")],
        [btn("💍 Годовщина", "event_type_Годовщина")],
        [btn("💐 8 марта", "event_type_8 марта")],
        [btn("💝 14 февраля", "event_type_14 февраля")],
        [btn("✏️ Другое", "event_type_custom")],
        [btn("❌ Отмена", "client_main")],
    ])


# ═══════════════════════════════════════════
#   МАГАЗИН — ГЛАВНОЕ
# ═══════════════════════════════════════════
def shop_main():
    return kb([
        [btn("📦 Мои товары", "shop_my_products")],
        [btn("🏷 Категории", "shop_my_categories")],
        [btn("📋 Новые заказы", "shop_new_orders")],
        [btn("🚚 Создать доставку", "shop_create_delivery")],
        [btn("📋 Мои доставки", "shop_my_deliveries")],
        [btn("📊 Статистика", "shop_stats")],
        [btn("⚙️ Настройки", "shop_settings")],
        [btn("🆘 Поддержка", "shop_support")],
    ])


def shop_back(to: str = "shop_main"):
    return kb([[btn("🔙 Назад", to)]])


def shop_products_menu():
    return kb([
        [btn("➕ Добавить товар", "shop_add_product")],
        [btn("✏️ Изменить цены на %", "shop_mass_price")],
        [btn("🔙 Назад", "shop_main")],
    ])


def shop_products_list(products: list):
    rows = []
    for p in products:
        status = "📝" if p.get("is_draft") else ("✅" if p["is_active"] else "⏸")
        rows.append([btn(f"{status} {p['title']} — {p['price']}", f"shop_prod_view_{p['id']}")])
    rows.append([btn("➕ Добавить товар", "shop_add_product")])
    rows.append([btn("✏️ Изменить цены на %", "shop_mass_price")])
    rows.append([btn("🔙 Назад", "shop_main")])
    return kb(rows)


def shop_product_manage(product_id: int, is_active: bool = True, is_draft: bool = False):
    toggle = "⏸ Скрыть" if is_active else "▶️ Показать"
    rows = [
        [btn("✏️ Изменить цену", f"shop_edit_price_{product_id}")],
        [btn("📸 Изменить фото", f"shop_edit_photo_{product_id}")],
        [btn(toggle, f"shop_toggle_{product_id}")],
    ]
    if is_draft:
        rows.append([btn("📤 Опубликовать", f"shop_publish_{product_id}")])
    rows.append([btn("🗑 Удалить", f"shop_delete_{product_id}")])
    rows.append([btn("🔙 Назад", "shop_my_products")])
    return kb(rows)


def shop_mass_price_confirm():
    return kb([
        [btn("✅ Применить", "shop_mass_apply")],
        [btn("❌ Отмена", "shop_main")],
    ])


# ═══════════════════════════════════════════
#   МАГАЗИН — НАСТРОЙКИ
# ═══════════════════════════════════════════
def shop_settings_menu():
    return kb([
        [btn("✏️ Название", "shop_set_name")],
        [btn("✏️ Адрес", "shop_set_address")],
        [btn("✏️ Телефон", "shop_set_phone")],
        [btn("📍 Обновить гео", "shop_set_geo")],
        [btn("📅 График работы", "shop_schedule")],
        [btn("💳 Реквизиты", "shop_requisites")],
        [btn("⏸ Приостановить", "shop_pause")],
        [btn("🔙 Назад", "shop_main")],
    ])


def shop_schedule_menu(schedule: dict):
    rows = []
    for key, day in config.WEEKDAYS.items():
        time_str = schedule.get(key, "выходной")
        rows.append([btn(f"{day}: {time_str}", f"shop_sched_{key}")])
    rows.append([btn("💾 Готово", "shop_main")])
    return kb(rows)


def shop_schedule_day(day_key: str):
    return kb([
        [btn("✏️ Открытие", f"shop_sched_open_{day_key}")],
        [btn("✏️ Закрытие", f"shop_sched_close_{day_key}")],
        [btn("🚫 Выходной", f"shop_sched_off_{day_key}")],
        [btn("🔙 Назад", "shop_schedule")],
    ])


def shop_requisites_menu():
    return kb([
        [btn("💳 Карта", "shop_req_card")],
        [btn("🏦 Банк", "shop_req_bank")],
        [btn("👤 ФИО владельца", "shop_req_holder")],
        [btn("📱 СБП", "shop_req_sbp")],
        [btn("🔙 Назад", "shop_settings")],
    ])


def banks_kb(prefix: str = "bank"):
    rows = []
    for bank in config.BANKS:
        rows.append([btn(bank, f"{prefix}_{bank}")])
    rows.append([btn("🔙 Назад", "shop_requisites")])
    return kb(rows)


def shop_paused_menu():
    return kb([
        [btn("▶️ Возобновить", "shop_resume")],
        [btn("🆘 Поддержка", "shop_support")],
    ])


# ═══════════════════════════════════════════
#   МАГАЗИН — КАТЕГОРИИ
# ═══════════════════════════════════════════
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


def shop_categories_remove(active_cats: list):
    rows = []
    for key, name in active_cats:
        rows.append([btn(f"🗑 {name}", f"shop_cat_remove_{key}")])
    rows.append([btn("🔙 Назад", "shop_my_categories")])
    return kb(rows)


# ═══════════════════════════════════════════
#   МАГАЗИН — ЗАКАЗЫ
# ═══════════════════════════════════════════
def shop_order_new(order_id: int):
    return kb([
        [btn("✅ Принять", f"shop_accept_{order_id}")],
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


def shop_order_manage(order_id: int):
    return kb([
        [btn("✏️ Изменить заказ", f"shop_edit_order_{order_id}")],
        [btn("🔄 Обновить", f"shop_view_order_{order_id}")],
        [btn("🔙 Назад", "shop_new_orders")],
    ])


def shop_order_edit_menu(order_id: int):
    return kb([
        [btn("📍 Адрес", f"soe_addr_{order_id}")],
        [btn("👤 Имя получателя", f"soe_name_{order_id}")],
        [btn("📞 Телефон", f"soe_phone_{order_id}")],
        [btn("🕒 Время", f"soe_time_{order_id}")],
        [btn("💬 Комментарий", f"soe_comment_{order_id}")],
        [btn("🔙 Назад", f"shop_view_order_{order_id}")],
    ])


# ═══════════════════════════════════════════
#   МАГАЗИН — СТАТИСТИКА
# ═══════════════════════════════════════════
def shop_stats_menu():
    return kb([
        [btn("📅 Сегодня", "shop_stats_today")],
        [btn("📅 Неделя", "shop_stats_week")],
        [btn("📅 Месяц", "shop_stats_month")],
        [btn("📅 Всё время", "shop_stats_all")],
        [btn("📥 Запросить выплату", "shop_request_payout")],
        [btn("📊 Экспорт CSV", "shop_export_csv")],
        [btn("🔙 Назад", "shop_main")],
    ])


# ═══════════════════════════════════════════
#   МАГАЗИН — СВОЯ ДОСТАВКА
# ═══════════════════════════════════════════
def shop_delivery_cancel():
    return kb([[btn("❌ Отмена", "shop_main")]])


def shop_delivery_date():
    return kb([
        [btn("📆 Сегодня", "shop_del_date_today")],
        [btn("📆 Завтра", "shop_del_date_tomorrow")],
        [btn("📆 Послезавтра", "shop_del_date_after")],
        [btn("❌ Отмена", "shop_main")],
    ])


def shop_delivery_period():
    rows = []
    for key, period in config.DELIVERY_SLOTS.items():
        rows.append([btn(f"{period['name']} ({period['hours']})", f"shop_del_period_{key}")])
    rows.append([btn("❌ Отмена", "shop_main")])
    return kb(rows)


def shop_delivery_slot(period_key: str):
    period = config.DELIVERY_SLOTS[period_key]
    rows = []
    for slot in period["slots"]:
        rows.append([btn(f"🕒 {slot}", f"shop_del_slot_{period_key}_{slot}")])
    rows.append([btn("🔙 Назад", "shop_del_back_period")])
    return kb(rows)


def shop_delivery_photo():
    return kb([
        [btn("⏭ Пропустить", "shop_del_photo_skip")],
        [btn("❌ Отмена", "shop_main")],
    ])


def shop_delivery_shop_comment_skip():
    return kb([
        [btn("⏭ Пропустить", "shop_del_shopcomm_skip")],
        [btn("❌ Отмена", "shop_main")],
    ])


def shop_delivery_client_comment_skip():
    return kb([
        [btn("⏭ Пропустить", "shop_del_clientcomm_skip")],
        [btn("❌ Отмена", "shop_main")],
    ])


def shop_delivery_need_photo():
    return kb([
        [btn("✅ Да, нужно фото", "shop_del_needphoto_yes")],
        [btn("⏭ Нет", "shop_del_needphoto_no")],
        [btn("❌ Отмена", "shop_main")],
    ])


def shop_delivery_confirm():
    return kb([
        [btn("✅ Создать заявку", "shop_del_confirm")],
        [btn("❌ Отмена", "shop_main")],
    ])


def shop_delivery_payment(delivery_id: int):
    return kb([
        [btn("✅ Я перевёл", f"shop_del_paid_{delivery_id}")],
        [btn("❌ Отмена", f"shop_del_cancel_{delivery_id}")],
    ])


def shop_my_deliveries(deliveries: list):
    rows = []
    for d in deliveries:
        em = {
            "pending": "⏸", "paid": "💳", "confirmed": "✅",
            "going": "🚴", "picked": "📦", "at_client": "📍",
            "done": "✅", "cancel": "❌",
        }.get(d["status"], "❓")
        rows.append([btn(f"{em} #Д-{d['id']} — {d['to_address'][:25]}", f"shop_del_view_{d['id']}")])
    rows.append([btn("🚚 Создать новую", "shop_create_delivery")])
    rows.append([btn("🔙 Назад", "shop_main")])
    return kb(rows)


def shop_delivery_view(delivery_id: int, can_cancel: bool = False):
    rows = [[btn("✏️ Изменить", f"shop_del_edit_{delivery_id}")]]
    if can_cancel:
        rows.append([btn("❌ Отменить", f"shop_del_cancel_{delivery_id}")])
    rows.append([btn("🔙 Назад", "shop_my_deliveries")])
    return kb(rows)


def shop_delivery_edit_menu(delivery_id: int):
    return kb([
        [btn("📍 Адрес", f"sde_addr_{delivery_id}")],
        [btn("👤 Имя получателя", f"sde_name_{delivery_id}")],
        [btn("📞 Телефон", f"sde_phone_{delivery_id}")],
        [btn("🕒 Время", f"sde_time_{delivery_id}")],
        [btn("💬 Комментарий магазина", f"sde_shopcomm_{delivery_id}")],
        [btn("💬 Комментарий клиента", f"sde_clientcomm_{delivery_id}")],
        [btn("🔙 Назад", f"shop_del_view_{delivery_id}")],
    ])


# ═══════════════════════════════════════════
#   КУРЬЕР
# ═══════════════════════════════════════════
def courier_main_on_shift():
    return kb([
        [btn("📦 Свободные заказы", "courier_free_orders")],
        [btn("🚗 Мои активные", "courier_my_orders")],
        [btn("💰 Баланс и вывод", "courier_balance"), btn("📊 Статистика", "courier_stats")],
        [btn("🎁 Рефералка", "courier_referral")],
        [btn("🏆 Достижения", "courier_achievements")],
        [btn("💳 Реквизиты", "courier_requisites")],
        [btn("🆘 Поддержка", "courier_support")],
        [btn("🔴 Уйти со смены", "courier_off_shift")],
    ])


def courier_main_off_shift():
    return kb([
        [btn("🟢 Выйти на смену", "courier_on_shift")],
        [btn("💰 Баланс и вывод", "courier_balance"), btn("📊 Статистика", "courier_stats")],
        [btn("🎁 Рефералка", "courier_referral")],
        [btn("🏆 Достижения", "courier_achievements")],
        [btn("💳 Реквизиты", "courier_requisites")],
        [btn("🆘 Поддержка", "courier_support")],
    ])


def courier_back(to: str = "courier_menu"):
    return kb([[btn("🔙 Назад", to)]])


def courier_support():
    return kb([[btn("🔙 Назад", "courier_menu")]])


def courier_free_orders_list(orders: list, page: int = 0):
    rows = []
    for o in orders:
        emoji = "🔥" if o["wait_min"] < 5 else ("🟢" if o["wait_min"] < 10 else "🟡")
        prefix = "🚚" if o["type"] == "delivery" else emoji
        rows.append([btn(
            f"{prefix} {o['id']} — {o['fee']}₽ — {o['distance']}км",
            f"courier_order_{o['id']}"
        )])
    rows.append([btn("🔄 Обновить", "courier_free_orders")])
    rows.append([btn("🔙 В меню", "courier_menu")])
    return kb(rows)


def courier_active_order(order_id: int, status: str):
    rows = []
    if status == "going":
        rows.append([btn("📦 Забрал", f"courier_picked_{order_id}")])
    elif status == "picked":
        rows.append([btn("🏠 У клиента", f"courier_at_client_{order_id}")])
    elif status == "at_client":
        rows.append([btn("✅ Доставлено", f"courier_done_{order_id}")])
    rows.append([btn("🗺 Маршрут", f"courier_map_{order_id}")])
    rows.append([btn("🆘 Проблема", f"courier_problem_{order_id}")])
    rows.append([btn("🔙 Назад", "courier_my_orders")])
    return kb(rows)


def courier_balance_menu():
    return kb([
        [btn("💸 Вывести", "courier_withdraw")],
        [btn("📜 История", "courier_tx_history")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_withdraw_method():
    return kb([
        [btn("💳 На карту", "cw_card")],
        [btn("📱 По СБП", "cw_sbp")],
        [btn("❌ Отмена", "courier_balance")],
    ])


def courier_stats_menu():
    return kb([
        [btn("📅 Сегодня", "courier_stats_today")],
        [btn("📅 Неделя", "courier_stats_week")],
        [btn("📅 Месяц", "courier_stats_month")],
        [btn("📅 Всё время", "courier_stats_all")],
        [btn("🏆 Достижения", "courier_achievements")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_referral_menu(ref_link: str):
    return kb([
        [btn_url("📤 Поделиться", f"https://t.me/share/url?url={ref_link}")],
        [btn("📋 Скопировать", "courier_ref_copy")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_requisites_menu():
    return kb([
        [btn("💳 Карта", "courier_req_card")],
        [btn("🏦 Банк", "courier_req_bank")],
        [btn("👤 ФИО владельца", "courier_req_holder")],
        [btn("📱 СБП", "courier_req_sbp")],
        [btn("🔙 Назад", "courier_menu")],
    ])


def courier_banks_kb():
    rows = []
    for bank in config.BANKS:
        rows.append([btn(bank, f"cour_bank_{bank}")])
    rows.append([btn("🔙 Назад", "courier_requisites")])
    return kb(rows)


# ═══════════════════════════════════════════
#   АДМИН — ГЛАВНОЕ
# ═══════════════════════════════════════════
def admin_main(permissions: dict | None = None):
    """Главное меню админа. Если permissions None — показываем всё (главный)."""
    if permissions is None:
        permissions = {k: True for k in config.ADMIN_PERMISSIONS.keys()}

    rows = []
    if permissions.get("requests"):
        rows.append([btn("📨 Заявки", "admin_requests")])
    if permissions.get("shops") and permissions.get("couriers"):
        rows.append([btn("🏪 Магазины", "admin_shops"), btn("🚴 Курьеры", "admin_couriers")])
    elif permissions.get("shops"):
        rows.append([btn("🏪 Магазины", "admin_shops")])
    elif permissions.get("couriers"):
        rows.append([btn("🚴 Курьеры", "admin_couriers")])
    if permissions.get("payments") and permissions.get("finance"):
        rows.append([btn("🚚 Доставки", "admin_deliveries"), btn("💳 Переводы", "admin_payments")])
        rows.append([btn("💰 Финансы", "admin_finance")])
    elif permissions.get("payments"):
        rows.append([btn("🚚 Доставки", "admin_deliveries"), btn("💳 Переводы", "admin_payments")])
    elif permissions.get("finance"):
        rows.append([btn("💰 Финансы", "admin_finance")])
    rows.append([btn("⏰ Зависшие заказы", "admin_stuck_orders")])
    if permissions.get("settings"):
        rows.append([btn("🎁 Промокоды", "admin_promos"), btn("🆘 Жалобы", "admin_complaints")])
        rows.append([btn("📢 Рассылка", "admin_broadcast")])
        rows.append([btn("📊 Аналитика", "admin_analytics"), btn("⚙️ Настройки", "admin_settings")])
    if permissions.get("admins"):
        rows.append([btn("🔑 Админы", "admin_admins")])
    rows.append([btn("📜 Логи", "admin_logs")])
    return kb(rows)


def admin_back(to: str = "admin_main"):
    return kb([[btn("🔙 Назад", to)]])


def admin_cancel():
    return kb([[btn("❌ Отмена", "admin_main")]])


# ═══════════════════════════════════════════
#   АДМИН — ЗАЯВКИ
# ═══════════════════════════════════════════
def admin_requests_menu():
    return kb([
        [btn("🏪 Магазины", "admin_req_shops")],
        [btn("🚴 Курьеры", "admin_req_couriers")],
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
#   АДМИН — МАГАЗИНЫ
# ═══════════════════════════════════════════
def admin_shops_list(shops: list, page: int = 0):
    rows = []
    for s in shops:
        status = "🟢" if s["status"] == "active" else ("🟡" if s["status"] == "pending" else "🔴")
        rows.append([btn(f"{status} {s['name']}", f"admin_shop_view_{s['id']}")])
    nav = []
    if page > 0:
        nav.append(btn("⬅️", f"admin_shops_page_{page - 1}"))
    nav.append(btn("🔄", "admin_shops"))
    if len(shops) == 10:
        nav.append(btn("➡️", f"admin_shops_page_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn("🔙 Назад", "admin_main")])
    return kb(rows)


def admin_shop_card(shop_id: int, status: str):
    rows = []
    if status == "active":
        rows.append([btn("🚫 Заблокировать", f"admin_shop_block_{shop_id}")])
    elif status == "blocked":
        rows.append([btn("✅ Разблокировать", f"admin_shop_unblock_{shop_id}")])
    elif status == "pending":
        rows.append([btn("✅ Одобрить", f"admin_shop_ok_{shop_id}")])
        rows.append([btn("❌ Отклонить", f"admin_shop_no_{shop_id}")])
    rows.append([btn("💰 Пополнить баланс", f"admin_shop_topup_{shop_id}")])
    rows.append([btn("✏️ Изменить данные", f"admin_shop_edit_{shop_id}")])
    rows.append([btn("📊 Статистика", f"admin_shop_stats_{shop_id}")])
    rows.append([btn("✉️ Написать", f"admin_shop_msg_{shop_id}")])
    rows.append([btn("🔙 Назад", "admin_shops")])
    return kb(rows)


def admin_shop_edit_menu(shop_id: int):
    return kb([
        [btn("📛 Название", f"ase_name_{shop_id}")],
        [btn("📍 Адрес", f"ase_address_{shop_id}")],
        [btn("📞 Телефон", f"ase_phone_{shop_id}")],
        [btn("📍 Гео", f"ase_geo_{shop_id}")],
        [btn("🔙 Назад", f"admin_shop_view_{shop_id}")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — КУРЬЕРЫ
# ═══════════════════════════════════════════
def admin_couriers_list(couriers: list, page: int = 0):
    rows = []
    for c in couriers:
        status = "🟢" if c["status"] == "active" else ("🟡" if c["status"] == "pending" else "🔴")
        rows.append([btn(f"{status} {c['name']} — {c['balance']}", f"admin_cour_view_{c['id']}")])
    nav = []
    if page > 0:
        nav.append(btn("⬅️", f"admin_couriers_page_{page - 1}"))
    nav.append(btn("🔄", "admin_couriers"))
    if len(couriers) == 10:
        nav.append(btn("➡️", f"admin_couriers_page_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn("🔙 Назад", "admin_main")])
    return kb(rows)


def admin_courier_card(courier_id: int, status: str):
    rows = []
    if status == "active":
        rows.append([btn("🚫 Заблокировать", f"admin_cour_block_{courier_id}")])
    elif status == "blocked":
        rows.append([btn("✅ Разблокировать", f"admin_cour_unblock_{courier_id}")])
    elif status == "pending":
        rows.append([btn("✅ Одобрить", f"admin_cour_ok_{courier_id}")])
        rows.append([btn("❌ Отклонить", f"admin_cour_no_{courier_id}")])
    rows.append([btn("💰 Пополнить баланс", f"admin_cour_topup_{courier_id}")])
    rows.append([btn("✏️ Изменить данные", f"admin_cour_edit_{courier_id}")])
    rows.append([btn("📊 Статистика", f"admin_cour_stats_{courier_id}")])
    rows.append([btn("✉️ Написать", f"admin_cour_msg_{courier_id}")])
    rows.append([btn("🔙 Назад", "admin_couriers")])
    return kb(rows)


def admin_courier_edit_menu(courier_id: int):
    return kb([
        [btn("👤 Имя", f"ace_name_{courier_id}")],
        [btn("📞 Телефон", f"ace_phone_{courier_id}")],
        [btn("🏙 Город", f"ace_city_{courier_id}")],
        [btn("🚗 Транспорт", f"ace_transport_{courier_id}")],
        [btn("🔙 Назад", f"admin_cour_view_{courier_id}")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ПЕРЕВОДЫ
# ═══════════════════════════════════════════
def admin_payments_menu():
    return kb([
        [btn("📥 Входящие заказы", "admin_pay_incoming")],
        [btn("🚚 Входящие доставки", "admin_pay_deliveries")],
        [btn("📤 Выплаты", "admin_pay_outgoing")],
        [btn("📜 История", "admin_pay_history")],
        [btn("💸 Возвраты", "admin_pay_refunds")],
        [btn("🔙 Назад", "admin_main")],
    ])


def admin_confirm_payment(order_id: int):
    return kb([
        [btn("✅ Подтвердить", f"admin_pay_ok_{order_id}")],
        [btn("❌ Отклонить", f"admin_pay_no_{order_id}")],
    ])


def admin_confirm_delivery(delivery_id: int):
    return kb([
        [btn("✅ Подтвердить", f"admin_del_pay_ok_{delivery_id}")],
        [btn("❌ Отклонить", f"admin_del_pay_no_{delivery_id}")],
    ])


def admin_payout_actions(payout_id: int):
    return kb([
        [btn("💳 Перевести", f"admin_payout_transfer_{payout_id}")],
        [btn("✅ Подтвердить", f"admin_payout_ok_{payout_id}")],
        [btn("❌ Отклонить", f"admin_payout_no_{payout_id}")],
        [btn("🔙 Назад", "admin_payments")],
    ])


def admin_pay_history_menu():
    return kb([
        [btn("📥 Входящие", "admin_hist_in")],
        [btn("📤 Исходящие", "admin_hist_out")],
        [btn("🔙 Назад", "admin_payments")],
    ])


def admin_refunds_list(refunds: list):
    rows = []
    for r in refunds:
        rows.append([btn(f"💸 #{r['order_id']} — {r['amount']}", f"admin_refund_view_{r['order_id']}")])
    rows.append([btn("🔙 Назад", "admin_payments")])
    return kb(rows)


def admin_refund_card(order_id: int):
    return kb([
        [btn("💳 Вернуть на карту", f"admin_refund_card_{order_id}")],
        [btn("💰 На баланс", f"admin_refund_balance_{order_id}")],
        [btn("❌ Отклонить", f"admin_refund_reject_{order_id}")],
        [btn("🔙 Назад", "admin_pay_refunds")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ЗАВИСШИЕ ЗАКАЗЫ
# ═══════════════════════════════════════════
def admin_stuck_order(order_id: int):
    return kb([
        [btn("💰 Поднять ставку", f"admin_boost_{order_id}")],
        [btn("❌ Отменить заказ", f"admin_cancel_order_{order_id}")],
        [btn("🔙 Назад", "admin_stuck_orders")],
    ])


def admin_boost_amount(order_id: int):
    return kb([
        [btn("+50 ₽", f"admin_boost_set_{order_id}_50")],
        [btn("+100 ₽", f"admin_boost_set_{order_id}_100")],
        [btn("+200 ₽", f"admin_boost_set_{order_id}_200")],
        [btn("✏️ Своя сумма", f"admin_boost_custom_{order_id}")],
        [btn("🔙 Назад", "admin_stuck_orders")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ПРОМОКОДЫ
# ═══════════════════════════════════════════
def admin_promo_list(promos: list):
    rows = [[btn("➕ Создать промокод", "admin_promo_create")]]
    for p in promos[:8]:
        status = "✅" if p["is_active"] else "⏸"
        rows.append([btn(f"{status} {p['code']} — {p['discount_text']}", f"admin_promo_view_{p['id']}")])
    rows.append([btn("🔙 Назад", "admin_main")])
    return kb(rows)


def admin_promo_view(promo_id: int):
    return kb([
        [btn("🗑 Удалить", f"admin_promo_del_{promo_id}")],
        [btn("🔙 Назад", "admin_promos")],
    ])


def admin_promo_type():
    return kb([
        [btn("💯 Процент", "promo_type_percent")],
        [btn("💵 Фиксированная", "promo_type_fixed")],
        [btn("❌ Отмена", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ЖАЛОБЫ
# ═══════════════════════════════════════════
def admin_complaints_list(complaints: list):
    rows = []
    for c in complaints:
        rows.append([btn(f"🆘 #{c['id']} — {c['type']}", f"admin_complaint_view_{c['id']}")])
    rows.append([btn("🔙 Назад", "admin_main")])
    return kb(rows)


def admin_complaint_card(complaint_id: int):
    return kb([
        [btn("💰 Вернуть деньги", f"admin_comp_refund_{complaint_id}")],
        [btn("❌ Отклонить", f"admin_comp_reject_{complaint_id}")],
        [btn("🔙 Назад", "admin_complaints")],
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


def admin_broadcast_confirm():
    return kb([
        [btn("✅ Отправить", "admin_bc_send")],
        [btn("❌ Отмена", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — АНАЛИТИКА
# ═══════════════════════════════════════════
def admin_analytics_menu():
    return kb([
        [btn("📅 Сегодня", "admin_analytics_today")],
        [btn("📅 Неделя", "admin_analytics_week")],
        [btn("📅 Месяц", "admin_analytics_month")],
        [btn("📅 Всё время", "admin_analytics_all")],
        [btn("🏆 Топ-магазины", "admin_top_shops")],
        [btn("🏆 Топ-курьеры", "admin_top_couriers")],
        [btn("📊 Дашборд смен", "admin_shifts_dashboard")],
        [btn("🔙 Назад", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — НАСТРОЙКИ
# ═══════════════════════════════════════════
def admin_settings_menu():
    return kb([
        [btn("🌍 Мультигород", "admin_multicity")],
        [btn("🔄 Обновление бота", "admin_update_bot")],
        [btn("🔙 Назад", "admin_main")],
    ])


def admin_update_bot_menu():
    return kb([
        [btn("📝 Новое обновление", "admin_update_new")],
        [btn("📜 История", "admin_update_history")],
        [btn("🔙 Назад", "admin_settings")],
    ])


def admin_update_confirm():
    return kb([
        [btn("✅ Отправить всем", "admin_update_send")],
        [btn("❌ Отмена", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — МУЛЬТИАДМИН
# ═══════════════════════════════════════════
def admin_admins_menu():
    return kb([
        [btn("➕ Добавить админа", "admin_add_admin")],
        [btn("📋 Список админов", "admin_list_admins")],
        [btn("🔙 Назад", "admin_main")],
    ])


def admin_permissions_menu(admin_id: int, active: list):
    rows = []
    for key, name in config.ADMIN_PERMISSIONS.items():
        mark = "✅" if key in active else "☐"
        rows.append([btn(f"{mark} {name}", f"perm_toggle_{admin_id}_{key}")])
    rows.append([btn("💾 Сохранить", f"perm_save_{admin_id}")])
    rows.append([btn("🗑 Удалить админа", f"admin_del_{admin_id}")])
    rows.append([btn("🔙 Назад", "admin_list_admins")])
    return kb(rows)


# ═══════════════════════════════════════════
#   АДМИН — ДОСТУП ПО ID
# ═══════════════════════════════════════════
def admin_access_menu():
    return kb([
        [btn("🚫 Заблокировать по ID", "admin_block_by_id")],
        [btn("✅ Разблокировать по ID", "admin_unblock_by_id")],
        [btn("🔙 Назад", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ЛОГИ
# ═══════════════════════════════════════════
def admin_logs_menu():
    return kb([
        [btn("🔄 Обновить", "admin_logs")],
        [btn("🗑 Очистить", "admin_logs_clear")],
        [btn("🔙 Назад", "admin_main")],
    ])


# ═══════════════════════════════════════════
#   АДМИН — ДОСТАВКИ
# ═══════════════════════════════════════════
def admin_deliveries_list(deliveries: list):
    rows = []
    for d in deliveries:
        em = {
            "pending": "⏸", "paid": "💳", "confirmed": "✅",
            "going": "🚴", "picked": "📦", "at_client": "📍",
            "done": "✅", "cancel": "❌",
        }.get(d["status"], "❓")
        rows.append([btn(f"{em} #Д-{d['id']} — {d['shop_name']}", f"admin_del_view_{d['id']}")])
    rows.append([btn("🔙 Назад", "admin_main")])
    return kb(rows)


def admin_delivery_view(delivery_id: int):
    return kb([
        [btn("❌ Отменить доставку", f"admin_del_cancel_{delivery_id}")],
        [btn("🔙 Назад", "admin_deliveries")],
    ])
