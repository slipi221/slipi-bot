# -*- coding: utf-8 -*-
"""
SLIPI — бот магазина
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext

from sqlalchemy import select, update, delete

import config
import keyboards as kb
from states import ShopReg, ShopProduct, ShopEdit, ShopDelivery
from database import async_session
from models import (
    Shop, Product, ShopCategory, Order, OrderItem, Client,
    DeliveryOrder, DeliveryPayment, ChangeLog, Courier,
)
from services import orders as orders_service
from services import payments as payments_service
from utils import helpers

from bots import bot_admin, bot_client, bot_courier

router = Router(name="shop")


async def get_shop(session, tg_id: int):
    result = await session.execute(select(Shop).where(Shop.tg_id == tg_id))
    return result.scalar_one_or_none()


async def show_shop_menu(message: Message, shop: Shop, edit: bool = False):
    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"⭐ {float(shop.rating or 0):.1f} | Заказов: {shop.total_orders}\n"
        f"🕒 {shop.work_start} – {shop.work_end}"
    )
    markup = kb.shop_main()
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
        except Exception:
            await message.answer(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


# ═══════════════════════════════════════════
#   /start
# ═══════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)

    if not shop:
        await message.answer(
            "🏪 <b>Стать партнёром SLIPI</b>\n\n"
            "Отправьте команду /register чтобы зарегистрироваться."
        )
        return

    if shop.status == "pending":
        await message.answer("⏳ Ваша заявка на рассмотрении.")
        return

    if shop.status == "blocked":
        await message.answer(
            f"🚫 <b>Доступ закрыт.</b>\n\n"
            f"Напишите в поддержку: {config.SUPPORT_TG}",
            reply_markup=kb.shop_support()
        )
        return

    if shop.is_paused:
        await message.answer(
            "⏸ <b>Магазин на паузе</b>\n\nВозобновите работу.",
            reply_markup=kb.shop_paused_menu()
        )
        return

    await show_shop_menu(message, shop)


@router.callback_query(F.data == "shop_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return
    await show_shop_menu(call.message, shop, edit=True)
    await call.answer()


@router.callback_query(F.data == "shop_support")
async def shop_support_handler(call: CallbackQuery):
    await call.message.edit_text(
        f"🆘 <b>Поддержка SLIPI</b>\n\n"
        f"Напишите: {config.SUPPORT_TG}\n"
        f"📞 {config.SUPPORT_PHONE}",
        reply_markup=kb.shop_back()
    )
    await call.answer()


# ═══════════════════════════════════════════
#   РЕГИСТРАЦИЯ
# ═══════════════════════════════════════════
@router.message(Command("register"))
async def shop_register(message: Message, state: FSMContext):
    async with async_session() as session:
        existing = await get_shop(session, message.from_user.id)
        if existing:
            await message.answer("Вы уже зарегистрированы.")
            return

    await state.set_state(ShopReg.name)
    await message.answer(
        "📝 <b>Шаг 1/8:</b> Название магазина\n\n<i>Например: Цветочный рай</i>",
        reply_markup=kb.cancel_kb()
    )


@router.message(ShopReg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ShopReg.address)
    await message.answer("📝 <b>Шаг 2/8:</b> Адрес магазина", reply_markup=kb.cancel_kb())


@router.message(ShopReg.address)
async def reg_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(ShopReg.phone)
    await message.answer("📝 <b>Шаг 3/8:</b> Телефон (11 цифр)", reply_markup=kb.cancel_kb())


@router.message(ShopReg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(phone=helpers.clean_phone(message.text))
    await state.set_state(ShopReg.telegram)
    await message.answer(
        "📝 <b>Шаг 4/8:</b> Ваш Telegram\n\n"
        "📌 Как узнать свой @username?\n"
        "1. Настройки → тапните на имя\n"
        "2. Скопируйте «Имя пользователя»\n\n"
        "Отправьте или /skip",
        reply_markup=kb.cancel_kb()
    )


@router.message(ShopReg.telegram)
async def reg_tg(message: Message, state: FSMContext):
    txt = message.text.strip()
    tg = None if txt.startswith("/skip") else (txt if txt.startswith("@") else "@" + txt)
    await state.update_data(telegram=tg)
    await state.set_state(ShopReg.vk)
    await message.answer("📝 <b>Шаг 5/8:</b> ВК (ссылка) или /skip", reply_markup=kb.cancel_kb())


@router.message(ShopReg.vk)
async def reg_vk(message: Message, state: FSMContext):
    vk = None if message.text.startswith("/skip") else message.text.strip()
    await state.update_data(vk_link=vk)
    await state.set_state(ShopReg.owner_name)
    await message.answer("📝 <b>Шаг 6/8:</b> Ваше имя", reply_markup=kb.cancel_kb())


@router.message(ShopReg.owner_name)
async def reg_owner(message: Message, state: FSMContext):
    await state.update_data(owner_name=message.text.strip())
    await state.set_state(ShopReg.geo)
    await message.answer(
        "📝 <b>Шаг 7/8:</b> Геолокация магазина\n\n"
        "📍 Скрепка → Геопозиция → Отправить",
        reply_markup=kb.cancel_kb()
    )


@router.message(ShopReg.geo, F.location)
async def reg_geo(message: Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lon=message.location.longitude)
    await state.set_state(ShopReg.categories)
    await message.answer(
        "📝 <b>Шаг 8/8:</b> Что вы продаёте?\n\nВыберите категории:",
        reply_markup=kb.shop_categories_choice([], config.CATEGORIES)
    )


@router.callback_query(F.data.startswith("shop_cat_toggle_"), ShopReg.categories)
async def reg_cat_toggle(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("shop_cat_toggle_", "")
    data = await state.get_data()
    active = list(data.get("reg_cats", []))
    if cat in active:
        active.remove(cat)
    else:
        active.append(cat)
    await state.update_data(reg_cats=active)
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.shop_categories_choice(active, config.CATEGORIES)
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "shop_cat_save", ShopReg.categories)
async def reg_cat_save(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cats = data.get("reg_cats", [])
    if not cats:
        await call.answer("Выберите хотя бы одну", show_alert=True)
        return

    async with async_session() as session:
        shop = Shop(
            tg_id=call.from_user.id,
            name=data["name"],
            address=data["address"],
            phone=data["phone"],
            telegram=data.get("telegram"),
            vk_link=data.get("vk_link"),
            owner_name=data.get("owner_name"),
            lat=data["lat"], lon=data["lon"],
            status="pending",
        )
        session.add(shop)
        await session.flush()
        for cat in cats:
            session.add(ShopCategory(shop_id=shop.id, category=cat))
        await session.commit()

    await state.clear()
    await call.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\nЖдём одобрения админа.",
        reply_markup=kb.shop_back()
    )

    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🏪 <b>Новая заявка магазина</b>\n\n"
            f"📛 {data['name']}\n📍 {data['address']}\n📞 {data['phone']}"
        )
    except Exception:
        pass

    await call.answer()


# ═══════════════════════════════════════════
#   МОИ ТОВАРЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_my_products")
async def my_products(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(Product).where(Product.shop_id == shop.id).order_by(Product.id.desc())
        )
        products = result.scalars().all()

    if not products:
        await call.message.edit_text(
            "📦 Товаров нет. Нажмите «Добавить товар».",
            reply_markup=kb.shop_products_menu()
        )
        await call.answer()
        return

    items = [{
        "id": p.id, "title": p.title,
        "price": helpers.money(p.shop_price),
        "is_active": p.is_active,
        "is_draft": p.is_draft,
    } for p in products[:10]]

    await call.message.edit_text(
        f"📦 <b>Ваши товары ({len(products)})</b>",
        reply_markup=kb.shop_products_list(items)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_prod_view_"))
async def prod_view(call: CallbackQuery):
    product_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        product = r.scalar_one_or_none()
        if not product:
            await call.answer("Не найдено", show_alert=True)
            return

    text = (
        f"📦 <b>{product.title}</b>\n\n"
        f"📝 {product.description or '—'}\n\n"
        f"💰 Ваша: {helpers.money(product.shop_price)}\n"
        f"💰 Клиент: {helpers.money(product.client_price)}\n"
        f"🏷 {helpers.category_name(product.category)}"
    )
    await call.message.edit_text(
        text,
        reply_markup=kb.shop_product_manage(product_id, product.is_active, product.is_draft)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_toggle_"))
async def prod_toggle(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        p = r.scalar_one_or_none()
        if p:
            p.is_active = not p.is_active
            await session.commit()
    await call.answer("Обновлено")
    await prod_view(call)


@router.callback_query(F.data.startswith("shop_publish_"))
async def prod_publish(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        p = r.scalar_one_or_none()
        if p:
            p.is_draft = False
            p.is_active = True
            await session.commit()
    await call.answer("📤 Опубликовано", show_alert=True)
    await prod_view(call)


@router.callback_query(F.data.startswith("shop_delete_"))
async def prod_delete(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    async with async_session() as session:
        await session.execute(delete(Product).where(Product.id == product_id))
        await session.commit()
    await call.answer("🗑 Удалено", show_alert=True)
    await my_products(call)


# ═══════════════════════════════════════════
#   МАССОВОЕ ИЗМЕНЕНИЕ ЦЕН
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_mass_price")
async def mass_price_start(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(Product).where(Product.shop_id == shop.id, Product.is_active == True)
        )
        products = result.scalars().all()

    if not products:
        await call.answer("Нет товаров", show_alert=True)
        return

    total = sum(float(p.shop_price) for p in products)

    await state.set_state(ShopEdit.mass_price)
    await call.message.edit_text(
        f"💰 <b>Массовое изменение цен</b>\n\n"
        f"Товаров: {len(products)}\n"
        f"Текущая сумма: {helpers.money(total)}\n\n"
        f"Введите процент:\n"
        f"(+ поднять, − снизить)\n\n"
        f"Пример: 12 или -10",
        reply_markup=kb.cancel_kb("shop_main")
    )
    await call.answer()


@router.message(ShopEdit.mass_price)
async def mass_price_apply(message: Message, state: FSMContext):
    try:
        percent = float(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer("❌ Введите число (например 12 или -10).")
        return

    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        result = await session.execute(
            select(Product).where(Product.shop_id == shop.id, Product.is_active == True)
        )
        products = result.scalars().all()

        old_total = sum(float(p.shop_price) for p in products)
        new_total = 0

        preview = []
        for p in products:
            old_price = float(p.shop_price)
            new_price = round(old_price * (1 + percent / 100), 2)
            new_price = max(new_price, 50)  # минимум 50 ₽
            new_markup = config.get_markup(new_price)
            new_client = new_price + new_markup

            p.shop_price = Decimal(str(new_price))
            p.markup = Decimal(str(new_markup))
            p.client_price = Decimal(str(new_client))
            new_total += new_price

            if len(preview) < 3:
                preview.append(f"• {p.title}: {int(old_price)} → {int(new_price)} ₽")

        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Цены изменены на {percent:+.1f}%</b>\n\n"
        f"Было: {helpers.money(old_total)}\n"
        f"Стало: {helpers.money(new_total)}\n\n"
        + "\n".join(preview),
        reply_markup=kb.shop_main()
    )


# ═══════════════════════════════════════════
#   ДОБАВЛЕНИЕ ТОВАРА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_add_product")
async def add_product_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopProduct.photo)
    await call.message.edit_text(
        "📸 <b>Шаг 1/5:</b> Отправьте фото товара",
        reply_markup=kb.cancel_kb()
    )
    await call.answer()


@router.message(ShopProduct.photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ShopProduct.title)
    await message.answer("📝 <b>Шаг 2/5:</b> Название", reply_markup=kb.cancel_kb())


@router.message(ShopProduct.title)
async def add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ShopProduct.description)
    await message.answer("📝 <b>Шаг 3/5:</b> Описание", reply_markup=kb.cancel_kb())


@router.message(ShopProduct.description)
async def add_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(ShopProduct.price)
    await message.answer("💰 <b>Шаг 4/5:</b> Ваша цена (₽)", reply_markup=kb.cancel_kb())


@router.message(ShopProduct.price)
async def add_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    markup = config.get_markup(price)
    client_price = price + markup

    await state.update_data(shop_price=price, markup=markup, client_price=client_price)
    await state.set_state(ShopProduct.category)

    rows = [[kb.btn(info["name"], f"shop_prod_cat_{key}")] for key, info in config.CATEGORIES.items()]
    rows.append([kb.btn("❌ Отмена", "shop_main")])

    await message.answer(
        f"💰 Ваша: {helpers.money(price)}\n"
        f"💰 Клиент: {helpers.money(client_price)}\n\n"
        f"<b>Шаг 5/5:</b> Категория:",
        reply_markup=kb.kb(rows)
    )


@router.callback_query(F.data.startswith("shop_prod_cat_"), ShopProduct.category)
async def add_cat(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("shop_prod_cat_", "")
    data = await state.get_data()

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return

        product = Product(
            shop_id=shop.id, category=cat,
            title=data["title"],
            description=data.get("description"),
            photo_id=data["photo_id"],
            shop_price=data["shop_price"],
            markup=data["markup"],
            client_price=data["client_price"],
            is_active=True,
        )
        session.add(product)

        cat_check = await session.execute(
            select(ShopCategory).where(
                ShopCategory.shop_id == shop.id,
                ShopCategory.category == cat,
            )
        )
        if not cat_check.scalar_one_or_none():
            session.add(ShopCategory(shop_id=shop.id, category=cat))

        await session.commit()

    await state.clear()
    await call.message.edit_text(f"✅ Товар «{data['title']}» добавлен!",
                                 reply_markup=kb.shop_main())
    await call.answer()


# ═══════════════════════════════════════════
#   КАТЕГОРИИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_my_categories")
async def my_categories(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(ShopCategory).where(ShopCategory.shop_id == shop.id)
        )
        cats = result.scalars().all()

    text = f"🏷 <b>Категории ({len(cats)})</b>\n\n"
    for c in cats:
        text += f"✅ {helpers.category_name(c.category)}\n"
    if not cats:
        text = "🏷 Категорий нет."

    await call.message.edit_text(text, reply_markup=kb.shop_categories_menu())
    await call.answer()


@router.callback_query(F.data == "shop_cat_add")
async def cat_add(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        result = await session.execute(
            select(ShopCategory).where(ShopCategory.shop_id == shop.id)
        )
        active = [c.category for c in result.scalars().all()]

    await state.set_state(ShopReg.categories)
    await state.update_data(reg_cats=active, edit_mode=True)
    await call.message.edit_text(
        "🏷 Выберите категории:",
        reply_markup=kb.shop_categories_choice(active, config.CATEGORIES)
    )
    await call.answer()


@router.callback_query(F.data == "shop_cat_remove")
async def cat_remove_menu(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        result = await session.execute(
            select(ShopCategory).where(ShopCategory.shop_id == shop.id)
        )
        cats = result.scalars().all()

    active = [(c.category, helpers.category_name(c.category)) for c in cats]
    await call.message.edit_text("🗑 Что убрать?",
                                 reply_markup=kb.shop_categories_remove(active))
    await call.answer()


@router.callback_query(F.data.startswith("shop_cat_remove_"))
async def cat_remove(call: CallbackQuery):
    cat = call.data.replace("shop_cat_remove_", "")
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        await session.execute(
            delete(ShopCategory).where(
                ShopCategory.shop_id == shop.id,
                ShopCategory.category == cat,
            )
        )
        await session.execute(
            update(Product).where(
                Product.shop_id == shop.id,
                Product.category == cat,
            ).values(is_active=False)
        )
        await session.commit()

    await call.answer("🗑 Убрано", show_alert=True)
    await my_categories(call)


# ═══════════════════════════════════════════
#   НОВЫЕ ЗАКАЗЫ (PUSH)
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_new_orders")
async def new_orders(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(Order).where(
                Order.shop_id == shop.id,
                Order.status == "wait",
                Order.payment_status == "confirmed",
            ).order_by(Order.id.asc())
        )
        orders = result.scalars().all()

    if not orders:
        await call.message.edit_text("📋 Новых заказов нет.", reply_markup=kb.shop_back())
        await call.answer()
        return

    for o in orders[:5]:
        items_text = ""
        async with async_session() as session:
            r = await session.execute(select(OrderItem).where(OrderItem.order_id == o.id))
            for it in r.scalars().all():
                items_text += f"• {it.title} × {it.quantity}\n"

        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ #{o.id}</b>\n\n"
            f"{items_text}\n"
            f"📍 {o.address}\n"
            f"👤 {o.client_name}, {o.client_phone}\n"
            f"📅 {helpers.format_date(o.delivery_date)} | 🕒 {o.delivery_slot or '—'}\n"
            f"💰 {helpers.money(o.total_price)}"
        )
        try:
            await call.message.answer(text, reply_markup=kb.shop_order_new(o.id))
        except Exception:
            pass

    await call.answer()


@router.callback_query(F.data.startswith("shop_accept_"))
async def shop_accept(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()
        if not order:
            await call.answer("Не найден", show_alert=True)
            return

        await orders_service.update_order_status(session, order_id, "wait")

        c_r = await session.execute(select(Client).where(Client.id == order.client_id))
        client = c_r.scalar_one_or_none()

    await call.message.edit_text(f"✅ Заказ #{order_id} принят!")

    if client and client.tg_id:
        try:
            await bot_client.send_message(
                client.tg_id,
                f"🟢 <b>Магазин принял заказ #{order_id}!</b>"
            )
        except Exception:
            pass

    await call.answer()


@router.callback_query(F.data.startswith("shop_reject_") & ~F.data.startswith("shop_reject_reason_"))
async def shop_reject(call: CallbackQuery):
    order_id = int(call.data.split("_")[2])
    await call.message.edit_text(
        f"❌ Почему отклоняете заказ #{order_id}?",
        reply_markup=kb.shop_reject_reasons(order_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_reject_reason_"))
async def shop_reject_reason(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[3])
    reason = parts[4]

    async with async_session() as session:
        o_r = await session.execute(select(Order).where(Order.id == order_id))
        order = o_r.scalar_one_or_none()

        await orders_service.cancel_order(
            session, order_id, reason=reason,
            cancelled_by="shop", refund=True,
        )

        if reason == "out_of_stock" and order:
            items_r = await session.execute(
                select(OrderItem).where(OrderItem.order_id == order_id)
            )
            for oi in items_r.scalars().all():
                p_r = await session.execute(select(Product).where(Product.id == oi.product_id))
                p = p_r.scalar_one_or_none()
                if p:
                    p.is_active = False
            await session.commit()

        client = None
        if order:
            c_r = await session.execute(select(Client).where(Client.id == order.client_id))
            client = c_r.scalar_one_or_none()

    await call.message.edit_text(f"❌ Заказ #{order_id} отклонён.")

    if client and client.tg_id:
        try:
            await bot_client.send_message(
                client.tg_id,
                f"😔 <b>Магазин отклонил заказ #{order_id}</b>\n\n"
                f"💰 Деньги вернутся на баланс."
            )
        except Exception:
            pass

    await call.answer()


# ═══════════════════════════════════════════
#   СВОЯ ДОСТАВКА — СОЗДАНИЕ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_create_delivery")
async def del_start(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return

    await state.clear()
    await state.set_state(ShopDelivery.address)
    await call.message.edit_text(
        f"🚚 <b>Создание доставки</b>\n\n"
        f"📍 Откуда: <b>{shop.address}</b>\n\n"
        f"📝 <b>Шаг 1/9:</b> Куда доставить?",
        reply_markup=kb.shop_delivery_cancel()
    )
    await call.answer()


@router.message(ShopDelivery.address)
async def del_address(message: Message, state: FSMContext):
    await state.update_data(to_address=message.text.strip())
    await state.set_state(ShopDelivery.client_name)
    await message.answer("📝 <b>Шаг 2/9:</b> Как зовут получателя?",
                         reply_markup=kb.shop_delivery_cancel())


@router.message(ShopDelivery.client_name)
async def del_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(ShopDelivery.client_phone)
    await message.answer("📝 <b>Шаг 3/9:</b> Телефон получателя",
                         reply_markup=kb.shop_delivery_cancel())


@router.message(ShopDelivery.client_phone)
async def del_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(client_phone=helpers.clean_phone(message.text))
    await state.set_state(ShopDelivery.date)
    await message.answer("📝 <b>Шаг 4/9:</b> Когда доставить?",
                         reply_markup=kb.shop_delivery_date())


@router.callback_query(F.data.startswith("shop_del_date_"), ShopDelivery.date)
async def del_date(call: CallbackQuery, state: FSMContext):
    part = call.data.replace("shop_del_date_", "")
    if part == "today":
        d = date.today()
    elif part == "tomorrow":
        d = date.today() + timedelta(days=1)
    else:
        d = date.today() + timedelta(days=2)
    await state.update_data(delivery_date=str(d))
    await state.set_state(ShopDelivery.time_period)
    await call.message.edit_text("📝 <b>Шаг 5/9:</b> Период:",
                                 reply_markup=kb.shop_delivery_period())
    await call.answer()


@router.callback_query(F.data.startswith("shop_del_period_"), ShopDelivery.time_period)
async def del_period(call: CallbackQuery, state: FSMContext):
    period = call.data.replace("shop_del_period_", "")
    await state.update_data(period=period)
    await state.set_state(ShopDelivery.time_slot)
    await call.message.edit_text("🕒 Время:", reply_markup=kb.shop_delivery_slot(period))
    await call.answer()


@router.callback_query(F.data == "shop_del_back_period", ShopDelivery.time_slot)
async def del_back_period(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopDelivery.time_period)
    await call.message.edit_text("📝 Период:", reply_markup=kb.shop_delivery_period())
    await call.answer()


@router.callback_query(F.data.startswith("shop_del_slot_"), ShopDelivery.time_slot)
async def del_slot(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    slot = parts[-1]
    await state.update_data(delivery_slot=slot)
    await state.set_state(ShopDelivery.photo)
    await call.message.edit_text(
        "📸 <b>Шаг 6/9:</b> Фото букета\n\nОтправьте или пропустите.",
        reply_markup=kb.shop_delivery_photo()
    )
    await call.answer()


@router.message(ShopDelivery.photo, F.photo)
async def del_photo(message: Message, state: FSMContext):
    await state.update_data(bouquet_photo_id=message.photo[-1].file_id)
    await state.set_state(ShopDelivery.shop_comment)
    await message.answer(
        "💬 <b>Шаг 7/9:</b> Комментарий магазина\n\nНапишите или /skip",
        reply_markup=kb.shop_delivery_shop_comment_skip()
    )


@router.callback_query(F.data == "shop_del_photo_skip", ShopDelivery.photo)
async def del_photo_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(bouquet_photo_id=None)
    await state.set_state(ShopDelivery.shop_comment)
    await call.message.edit_text(
        "💬 <b>Шаг 7/9:</b> Комментарий магазина\n\nНапишите или /skip",
        reply_markup=kb.shop_delivery_shop_comment_skip()
    )
    await call.answer()


@router.message(ShopDelivery.shop_comment)
async def del_shop_comment(message: Message, state: FSMContext):
    txt = "" if message.text.startswith("/skip") else message.text.strip()
    await state.update_data(shop_comment=txt)
    await state.set_state(ShopDelivery.client_comment)
    await message.answer(
        "💬 <b>Шаг 8/9:</b> Комментарий клиента\n\nНапишите или /skip",
        reply_markup=kb.shop_delivery_client_comment_skip()
    )


@router.callback_query(F.data == "shop_del_shopcomm_skip", ShopDelivery.shop_comment)
async def del_shop_comment_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(shop_comment=None)
    await state.set_state(ShopDelivery.client_comment)
    await call.message.edit_text(
        "💬 <b>Шаг 8/9:</b> Комментарий клиента\n\nНапишите или /skip",
        reply_markup=kb.shop_delivery_client_comment_skip()
    )
    await call.answer()


@router.message(ShopDelivery.client_comment)
async def del_client_comment(message: Message, state: FSMContext):
    txt = "" if message.text.startswith("/skip") else message.text.strip()
    await state.update_data(client_comment=txt)
    await state.set_state(ShopDelivery.need_photo)
    await message.answer(
        "📸 <b>Шаг 9/9:</b> Фото вручения?",
        reply_markup=kb.shop_delivery_need_photo()
    )


@router.callback_query(F.data == "shop_del_clientcomm_skip", ShopDelivery.client_comment)
async def del_client_comment_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(client_comment=None)
    await state.set_state(ShopDelivery.need_photo)
    await call.message.edit_text(
        "📸 <b>Шаг 9/9:</b> Фото вручения?",
        reply_markup=kb.shop_delivery_need_photo()
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_del_needphoto_"), ShopDelivery.need_photo)
async def del_needphoto(call: CallbackQuery, state: FSMContext):
    need = call.data.replace("shop_del_needphoto_", "") == "yes"
    await state.update_data(need_delivery_photo=need)

    data = await state.get_data()

    # Считаем по умолчанию первую зону
    distance_km = 3
    zone = config.get_delivery_zone(distance_km)
    if zone is None:
        await call.message.edit_text("🌷 Адрес слишком далеко.", reply_markup=kb.shop_back())
        await state.clear()
        await call.answer()
        return

    await state.update_data(
        distance_km=distance_km,
        client_pays=zone["client_pays"],
        courier_fee=zone["courier_gets"],
        platform_fee=zone["platform_gets"],
    )

    text = (
        f"🧾 <b>Проверьте заявку</b>\n\n"
        f"📍 Куда: {data['to_address']}\n"
        f"👤 {data['client_name']}, {data['client_phone']}\n"
        f"📅 {data['delivery_date']} | 🕒 {data['delivery_slot']}\n"
    )
    if data.get("bouquet_photo_id"): text += "📸 Фото букета: ✅\n"
    if data.get("shop_comment"): text += f"💬 Магазин: {data['shop_comment']}\n"
    if data.get("client_comment"): text += f"💬 Клиент: {data['client_comment']}\n"
    text += f"📸 Фото вручения: {'✅ Да' if need else '⏭ Нет'}\n\n"
    text += f"💰 <b>Доставка: {helpers.money(zone['client_pays'])}</b>"

    await state.set_state(ShopDelivery.confirm)
    await call.message.edit_text(text, reply_markup=kb.shop_delivery_confirm())
    await call.answer()


@router.callback_query(F.data == "shop_del_confirm", ShopDelivery.confirm)
async def del_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return

        delivery = DeliveryOrder(
            shop_id=shop.id,
            from_address=shop.address or "",
            from_lat=float(shop.lat) if shop.lat else None,
            from_lon=float(shop.lon) if shop.lon else None,
            to_address=data["to_address"],
            client_name=data["client_name"],
            client_phone=data["client_phone"],
            delivery_date=datetime.strptime(data["delivery_date"], "%Y-%m-%d").date(),
            delivery_slot=data["delivery_slot"],
            bouquet_photo_id=data.get("bouquet_photo_id"),
            shop_comment=data.get("shop_comment"),
            client_comment=data.get("client_comment"),
            need_delivery_photo=data.get("need_delivery_photo", False),
            distance_km=data["distance_km"],
            client_pays=Decimal(str(data["client_pays"])),
            courier_fee=Decimal(str(data["courier_fee"])),
            platform_fee=Decimal(str(data["platform_fee"])),
            status="pending",
            payment_status="pending",
        )
        session.add(delivery)
        await session.flush()

        payment = DeliveryPayment(
            delivery_id=delivery.id,
            shop_id=shop.id,
            amount=Decimal(str(data["client_pays"])),
            status="pending",
        )
        session.add(payment)
        await session.commit()

        delivery_id = delivery.id

    await state.set_state(ShopDelivery.payment)
    await call.message.edit_text(
        f"💳 <b>Оплата доставки #Д-{delivery_id}</b>\n\n"
        f"Сумма: <b>{helpers.money(data['client_pays'])}</b>\n\n"
        f"Карта: <code>{config.CARD_NUMBER}</code>\n"
        f"Получатель: {config.CARD_HOLDER}\n\n"
        f"⚠️ В комментарии: <b>Д-{delivery_id}</b>\n\n"
        f"После перевода нажмите «✅ Я перевёл».",
        reply_markup=kb.shop_delivery_payment(delivery_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_del_paid_"))
async def del_paid(call: CallbackQuery, state: FSMContext):
    delivery_id = int(call.data.split("_")[3])

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        delivery = d_r.scalar_one_or_none()
        if not delivery:
            await call.answer("Не найдено", show_alert=True)
            return
        await session.commit()

    await state.clear()
    await call.message.edit_text(
        f"✅ <b>Заявка #Д-{delivery_id} создана!</b>\n\n"
        f"Ждём подтверждения админа.",
        reply_markup=kb.shop_main()
    )

    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🚚 <b>Заявка на доставку #Д-{delivery_id}</b>\n\n"
            f"🏪 {shop.name if shop else '—'}\n"
            f"💰 {helpers.money(delivery.client_pays)}\n\n"
            f"Комментарий: <b>Д-{delivery_id}</b>"
        )
    except Exception:
        pass

    await call.answer()


@router.callback_query(F.data.startswith("shop_del_cancel_"))
async def del_cancel(call: CallbackQuery, state: FSMContext):
    delivery_id = int(call.data.split("_")[3])
    async with async_session() as session:
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()
        if d:
            d.status = "cancel"
            d.cancel_reason = "shop_cancelled"
            await session.commit()

    await state.clear()
    await call.answer("❌ Отменено", show_alert=True)

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if shop:
        await show_shop_menu(call.message, shop, edit=True)


# ═══════════════════════════════════════════
#   МОИ ДОСТАВКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_my_deliveries")
async def my_deliveries(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(DeliveryOrder).where(DeliveryOrder.shop_id == shop.id)
            .order_by(DeliveryOrder.id.desc()).limit(20)
        )
        deliveries = result.scalars().all()

    if not deliveries:
        await call.message.edit_text("🚚 Доставок пока нет.", reply_markup=kb.shop_back())
        await call.answer()
        return

    items = [{"id": d.id, "to_address": d.to_address, "status": d.status} for d in deliveries]
    await call.message.edit_text(
        f"🚚 <b>Мои доставки ({len(deliveries)})</b>",
        reply_markup=kb.shop_my_deliveries(items)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_del_view_"))
async def del_view(call: CallbackQuery):
    delivery_id = int(call.data.split("_")[3])
    async with async_session() as session:
        d_r = await session.execute(select(DeliveryOrder).where(DeliveryOrder.id == delivery_id))
        d = d_r.scalar_one_or_none()
        if not d:
            await call.answer("Не найдено", show_alert=True)
            return

    status_map = {
        "pending": "⏸ Ожидает оплаты", "paid": "💳 Оплачено, ждёт админа",
        "confirmed": "✅ Ищем курьера", "going": "🚴 Курьер в пути",
        "picked": "📦 Курьер забрал", "at_client": "📍 У клиента",
        "done": "✅ Доставлено", "cancel": "❌ Отменено",
    }
    text = (
        f"🚚 <b>Доставка #Д-{d.id}</b>\n"
        f"{status_map.get(d.status, d.status)}\n\n"
        f"📍 Куда: {d.to_address}\n"
        f"👤 {d.client_name}, {d.client_phone}\n"
        f"📅 {helpers.format_date(d.delivery_date)} | 🕒 {d.delivery_slot or '—'}\n\n"
        f"💰 Оплачено: {helpers.money(d.client_pays)}"
    )

    can_cancel = d.status in ("pending", "paid")
    await call.message.edit_text(text, reply_markup=kb.shop_delivery_view(delivery_id, can_cancel))
    await call.answer()


# ═══════════════════════════════════════════
#   СТАТИСТИКА
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_stats")
async def stats(call: CallbackQuery):
    await call.message.edit_text(
        "📊 <b>Статистика</b>\n\nВыберите период:",
        reply_markup=kb.shop_stats_menu()
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_stats_"))
async def stats_period(call: CallbackQuery):
    period = call.data.replace("shop_stats_", "")
    now = datetime.now()
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "Сегодня"
    elif period == "week":
        since = now - timedelta(days=7)
        label = "За неделю"
    elif period == "month":
        since = now - timedelta(days=30)
        label = "За месяц"
    else:
        since = datetime(2020, 1, 1)
        label = "За всё время"

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        result = await session.execute(
            select(Order).where(Order.shop_id == shop.id, Order.created_at >= since)
        )
        orders = result.scalars().all()

    done = sum(1 for o in orders if o.status == "done")
    cancel = sum(1 for o in orders if o.status == "cancel")
    total_sum = sum(float(o.total_price) for o in orders if o.status == "done")

    text = (
        f"📊 <b>Статистика — {label}</b>\n\n"
        f"📦 Заказов: {len(orders)}\n"
        f"✅ Доставлено: {done}\n"
        f"❌ Отменено: {cancel}\n\n"
        f"💰 Оборот: {helpers.money(total_sum)}\n"
        f"🏦 Баланс: {helpers.money(shop.balance)}\n"
        f"⭐ {float(shop.rating or 0):.1f} ({shop.reviews_count})"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_stats_menu())
    await call.answer()


@router.callback_query(F.data == "shop_export_csv")
async def export_csv(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop:
            await call.answer("Ошибка", show_alert=True)
            return
        csv_text = await payments_service.export_shop_orders_csv(session, shop.id)

    file = BufferedInputFile(csv_text.encode("utf-8"), filename=f"orders_shop_{shop.id}.csv")
    await call.message.answer_document(file, caption="📊 Экспорт заказов")
    await call.answer()


@router.callback_query(F.data == "shop_request_payout")
async def request_payout(call: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop or float(shop.balance) <= 0:
        await call.answer("Нечего выводить", show_alert=True)
        return

    await state.set_state(ShopEdit.payout)
    await call.message.edit_text(
        f"💸 <b>Запрос выплаты</b>\n\n"
        f"Доступно: {helpers.money(shop.balance)}\n\nВведите сумму:",
        reply_markup=kb.cancel_kb("shop_stats")
    )
    await call.answer()


@router.message(ShopEdit.payout)
async def process_payout(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        if not shop or amount <= 0 or amount > shop.balance:
            await message.answer("❌ Неверная сумма.")
            return

        await payments_service.create_payout(
            session=session,
            user_type="shop", user_id=shop.id,
            amount=amount,
            method="card",
            card_number=shop.card_number,
            bank_name=shop.bank_name,
            card_holder=shop.card_holder,
            sbp_phone=shop.sbp_phone,
        )

    await state.clear()
    await message.answer(f"✅ Заявка на выплату {helpers.money(amount)} отправлена.",
                         reply_markup=kb.shop_main())


# ═══════════════════════════════════════════
#   НАСТРОЙКИ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_settings")
async def settings(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"📛 {shop.name}\n📍 {shop.address or '—'}\n"
        f"📞 {shop.phone or '—'}\n🕒 {shop.work_start} – {shop.work_end}"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_settings_menu())
    await call.answer()


@router.callback_query(F.data == "shop_pause")
async def pause_shop(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        shop.is_paused = True
        await session.commit()
    await call.message.edit_text(
        "⏸ Магазин приостановлен.",
        reply_markup=kb.shop_paused_menu()
    )
    await call.answer()


@router.callback_query(F.data == "shop_resume")
async def resume_shop(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        shop.is_paused = False
        await session.commit()
    await call.answer("▶️ Возобновлено", show_alert=True)
    await show_shop_menu(call.message, shop, edit=True)


# Изменение полей
@router.callback_query(F.data == "shop_set_name")
async def set_name_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.name)
    await call.message.edit_text("✏️ Новое название:", reply_markup=kb.cancel_kb("shop_settings"))
    await call.answer()


@router.message(ShopEdit.name)
async def set_name(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.name = message.text.strip()
        await session.commit()
    await state.clear()
    await message.answer("✅ Обновлено.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_set_address")
async def set_addr_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.address)
    await call.message.edit_text("✏️ Новый адрес:", reply_markup=kb.cancel_kb("shop_settings"))
    await call.answer()


@router.message(ShopEdit.address)
async def set_addr(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.address = message.text.strip()
        await session.commit()
    await state.clear()
    await message.answer("✅ Обновлено.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_set_phone")
async def set_phone_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.phone)
    await call.message.edit_text("✏️ Новый телефон:", reply_markup=kb.cancel_kb("shop_settings"))
    await call.answer()


@router.message(ShopEdit.phone)
async def set_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.phone = helpers.clean_phone(message.text)
        await session.commit()
    await state.clear()
    await message.answer("✅ Обновлено.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_set_geo")
async def set_geo_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.geo)
    await call.message.edit_text("📍 Отправьте новую геолокацию:", reply_markup=kb.cancel_kb("shop_settings"))
    await call.answer()


@router.message(ShopEdit.geo, F.location)
async def set_geo(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.lat = message.location.latitude
        shop.lon = message.location.longitude
        await session.commit()
    await state.clear()
    await message.answer("✅ Гео обновлено.", reply_markup=kb.shop_main())


# ═══════════════════════════════════════════
#   ГРАФИК РАБОТЫ (ПО ДНЯМ)
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_schedule")
async def schedule_menu(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return

    schedule = helpers.str_to_schedule(shop.schedule) or helpers.default_schedule()
    await call.message.edit_text(
        "📅 <b>График работы</b>\n\nНажмите на день чтобы настроить:",
        reply_markup=kb.shop_schedule_menu(schedule)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_sched_") & ~F.data.startswith("shop_sched_open_") & ~F.data.startswith("shop_sched_close_") & ~F.data.startswith("shop_sched_off_"))
async def schedule_day(call: CallbackQuery):
    day_key = call.data.replace("shop_sched_", "")
    day_name = helpers.weekday_name(day_key)
    await call.message.edit_text(
        f"📅 <b>{day_name}</b>\n\nВыберите действие:",
        reply_markup=kb.shop_schedule_day(day_key)
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_sched_open_"))
async def schedule_open(call: CallbackQuery, state: FSMContext):
    day_key = call.data.replace("shop_sched_open_", "")
    await state.update_data(schedule_day=day_key, schedule_field="open")
    await state.set_state(ShopEdit.schedule_day)
    await call.message.edit_text(
        f"✏️ Введите время открытия для {helpers.weekday_name(day_key)} (формат 08:00):",
        reply_markup=kb.cancel_kb("shop_schedule")
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_sched_close_"))
async def schedule_close(call: CallbackQuery, state: FSMContext):
    day_key = call.data.replace("shop_sched_close_", "")
    await state.update_data(schedule_day=day_key, schedule_field="close")
    await state.set_state(ShopEdit.schedule_day)
    await call.message.edit_text(
        f"✏️ Введите время закрытия для {helpers.weekday_name(day_key)} (формат 22:00):",
        reply_markup=kb.cancel_kb("shop_schedule")
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_sched_off_"))
async def schedule_off(call: CallbackQuery):
    day_key = call.data.replace("shop_sched_off_", "")
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        schedule = helpers.str_to_schedule(shop.schedule) or helpers.default_schedule()
        schedule[day_key] = "выходной"
        shop.schedule = helpers.schedule_to_str(schedule)
        await session.commit()
    await call.answer("🚫 Выходной", show_alert=True)
    await schedule_menu(call)


@router.message(ShopEdit.schedule_day)
async def schedule_set(message: Message, state: FSMContext):
    if not helpers.is_valid_time(message.text.strip()):
        await message.answer("❌ Неверный формат. Пример: 08:00")
        return

    data = await state.get_data()
    day_key = data.get("schedule_day")
    field = data.get("schedule_field")

    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        schedule = helpers.str_to_schedule(shop.schedule) or helpers.default_schedule()
        current = schedule.get(day_key, "08:00-22:00")
        if current == "выходной":
            current = "08:00-22:00"
        start, end = current.split("-")
        if field == "open":
            schedule[day_key] = f"{message.text.strip()}-{end}"
        else:
            schedule[day_key] = f"{start}-{message.text.strip()}"
        shop.schedule = helpers.schedule_to_str(schedule)
        await session.commit()

    await state.clear()
    await message.answer("✅ График обновлён.", reply_markup=kb.shop_main())


# ═══════════════════════════════════════════
#   РЕКВИЗИТЫ
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_requisites")
async def requisites(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    if not shop:
        await call.answer("Ошибка", show_alert=True)
        return

    text = (
        f"💳 <b>Реквизиты для выплат</b>\n\n"
        f"💳 Карта: {helpers.format_card(shop.card_number or '—')}\n"
        f"🏦 Банк: {shop.bank_name or '—'}\n"
        f"👤 ФИО: {shop.card_holder or '—'}\n"
        f"📱 СБП: {shop.sbp_phone or '—'}"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_requisites_menu())
    await call.answer()


@router.callback_query(F.data == "shop_req_card")
async def req_card(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.req_card)
    await call.message.edit_text("💳 Номер карты (16 цифр):", reply_markup=kb.cancel_kb("shop_requisites"))
    await call.answer()


@router.message(ShopEdit.req_card)
async def req_card_save(message: Message, state: FSMContext):
    if not helpers.is_valid_card(message.text):
        await message.answer("❌ Неверный номер карты.")
        return
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.card_number = helpers.clean_phone(message.text)
        await session.commit()
    await state.clear()
    await message.answer("✅ Карта сохранена.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_req_bank")
async def req_bank(call: CallbackQuery):
    await call.message.edit_text("🏦 Выберите банк:", reply_markup=kb.banks_kb("shopbank"))
    await call.answer()


@router.callback_query(F.data.startswith("shopbank_"))
async def req_bank_save(call: CallbackQuery):
    bank = call.data.replace("shopbank_", "")
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        shop.bank_name = bank
        await session.commit()
    await call.answer(f"✅ {bank}", show_alert=True)
    await requisites(call)


@router.callback_query(F.data == "shop_req_holder")
async def req_holder(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.req_holder)
    await call.message.edit_text(
        "👤 Введите ФИО владельца карты:",
        reply_markup=kb.cancel_kb("shop_requisites")
    )
    await call.answer()


@router.message(ShopEdit.req_holder)
async def req_holder_save(message: Message, state: FSMContext):
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.card_holder = message.text.strip()
        await session.commit()
    await state.clear()
    await message.answer("✅ ФИО сохранено.", reply_markup=kb.shop_main())


@router.callback_query(F.data == "shop_req_sbp")
async def req_sbp(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopEdit.req_sbp)
    await call.message.edit_text("📱 Телефон для СБП:", reply_markup=kb.cancel_kb("shop_requisites"))
    await call.answer()


@router.message(ShopEdit.req_sbp)
async def req_sbp_save(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    async with async_session() as session:
        shop = await get_shop(session, message.from_user.id)
        shop.sbp_phone = helpers.clean_phone(message.text)
        await session.commit()
    await state.clear()
    await message.answer("✅ СБП сохранён.", reply_markup=kb.shop_main())
