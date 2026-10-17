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
from aiogram.exceptions import TelegramBadRequest
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
from services import notify
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
        f"🕒 {shop.work_start} – {shop.work_end}\n"
        f"{'🟢 На смене' if shop.is_on_shift else '🔴 Не на смене'}"
    )
    markup = kb.shop_main(shop.is_on_shift)
    if edit:
        try: await message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest: await message.answer(text, reply_markup=markup)
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
        await message.answer("🏪 <b>Стать партнёром SLIPI</b>\n\nОтправьте команду /register чтобы зарегистрироваться.")
        return
    if shop.status == "pending":
        await message.answer("⏳ Ваша заявка на рассмотрении.")
        return
    if shop.status == "blocked":
        await message.answer(f"🚫 <b>Доступ закрыт.</b>\n\nНапишите в поддержку: {config.SUPPORT_TG}", reply_markup=kb.shop_support())
        return
    if shop.is_paused:
        await message.answer("⏸ <b>Магазин на паузе</b>\n\nВозобновите работу.", reply_markup=kb.shop_paused_menu())
        return
    await show_shop_menu(message, shop)

# ИСПРАВЛЕНО: Теперь отмена работает даже во время регистрации
@router.callback_query(F.data == "shop_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
    
    if not shop:
        await call.message.edit_text("❌ Регистрация отменена.\n\nОтправьте /register чтобы начать заново.")
        await call.answer()
        return
        
    await show_shop_menu(call.message, shop, edit=True)
    await call.answer()

@router.callback_query(F.data == "shop_support")
async def shop_support_handler(call: CallbackQuery):
    await call.message.edit_text(f"🆘 <b>Поддержка SLIPI</b>\n\nНапишите: {config.SUPPORT_TG}\n📞 {config.SUPPORT_PHONE}", reply_markup=kb.shop_back())
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
    await message.answer("📝 <b>Шаг 1/10:</b> Название магазина\n\n<i>Например: Цветочный рай</i>", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ShopReg.city)
    await message.answer("📝 <b>Шаг 2/10:</b> Город", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.city)
async def reg_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(ShopReg.street)
    await message.answer("📝 <b>Шаг 3/10:</b> Улица", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.street)
async def reg_street(message: Message, state: FSMContext):
    await state.update_data(street=message.text.strip())
    await state.set_state(ShopReg.house)
    await message.answer("📝 <b>Шаг 4/10:</b> Номер дома", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.house)
async def reg_house(message: Message, state: FSMContext):
    await state.update_data(house=message.text.strip())
    await state.set_state(ShopReg.phone)
    await message.answer("📝 <b>Шаг 5/10:</b> Телефон (11 цифр)", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not helpers.is_valid_phone(message.text):
        await message.answer("❌ Неверный номер.")
        return
    await state.update_data(phone=helpers.clean_phone(message.text))
    await state.set_state(ShopReg.telegram)
    await message.answer("📝 <b>Шаг 6/10:</b> Ваш Telegram\n\nОтправьте или напишите «скип»", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.telegram)
async def reg_tg(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текст или напишите «скип»")
        return
    txt = message.text.strip().lower()
    if txt in ("/skip", "скип", "пропустить", "нет"):
        tg = None
    else:
        tg = message.text.strip() if message.text.strip().startswith("@") else "@" + message.text.strip()
    await state.update_data(telegram=tg)
    await state.set_state(ShopReg.vk)
    await message.answer("📝 <b>Шаг 7/10:</b> ВК (ссылка) или напишите «скип»", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.vk)
async def reg_vk(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Отправьте текст или напишите «скип»")
        return
    txt = message.text.strip().lower()
    vk = None if txt in ("/skip", "скип", "пропустить", "нет") else message.text.strip()
    await state.update_data(vk_link=vk)
    await state.set_state(ShopReg.owner_name)
    await message.answer("📝 <b>Шаг 8/10:</b> Ваше имя", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.owner_name)
async def reg_owner(message: Message, state: FSMContext):
    await state.update_data(owner_name=message.text.strip())
    await state.set_state(ShopReg.geo)
    await message.answer(
        "📝 <b>Шаг 9/10:</b> Геолокация магазина\n\n"
        "⚠️ <b>ВНИМАНИЕ!</b> Нажмите на скрепку и выберите «Геопозиция». "
        "Без этого мы не сможем строить маршруты для курьеров!",
        reply_markup=kb.cancel_kb("shop_main")
    )

@router.message(ShopReg.geo, F.location)
async def reg_geo(message: Message, state: FSMContext):
    await state.update_data(lat=message.location.latitude, lon=message.location.longitude)
    await state.set_state(ShopReg.schedule_weekdays)
    await message.answer(
        "📝 <b>Шаг 10/10:</b> График работы\n\n"
        "Введите время для <b>Пн–Пт</b> (например: 08:00-20:00)\n"
        "Или напишите «выходной»:",
        reply_markup=kb.cancel_kb("shop_main")
    )

@router.message(ShopReg.schedule_weekdays)
async def reg_schedule_wd(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Введите время (например 08:00-20:00) или «выходной»")
        return
    val = message.text.strip()
    val_lower = val.lower()
    
    if val_lower in ("скип", "пропустить", "/skip", "выходной"):
        val = "выходной"
    else:
        parts = val.split("-")
        if len(parts) != 2 or not helpers.is_valid_time(parts[0]) or not helpers.is_valid_time(parts[1]):
            await message.answer("❌ Неверный формат. Пример: 08:00-20:00")
            return
            
    await state.update_data(schedule_wd=val)
    await state.set_state(ShopReg.schedule_sat)
    await message.answer("📝 Введите время для <b>Субботы</b> (или «выходной»):", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.schedule_sat)
async def reg_schedule_sat(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Введите время (например 08:00-20:00) или «выходной»")
        return
    val = message.text.strip()
    val_lower = val.lower()
    
    if val_lower in ("скип", "пропустить", "/skip", "выходной"):
        val = "выходной"
    else:
        parts = val.split("-")
        if len(parts) != 2 or not helpers.is_valid_time(parts[0]) or not helpers.is_valid_time(parts[1]):
            await message.answer("❌ Неверный формат. Пример: 08:00-20:00")
            return

    await state.update_data(schedule_sat=val)
    await state.set_state(ShopReg.schedule_sun)
    await message.answer("📝 Введите время для <b>Воскресенья</b> (или «выходной»):", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopReg.schedule_sun)
async def reg_schedule_sun(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Введите время (например 08:00-20:00) или «выходной»")
        return
    val = message.text.strip()
    val_lower = val.lower()
    
    if val_lower in ("скип", "пропустить", "/skip", "выходной"):
        val = "выходной"
    else:
        parts = val.split("-")
        if len(parts) != 2 or not helpers.is_valid_time(parts[0]) or not helpers.is_valid_time(parts[1]):
            await message.answer("❌ Неверный формат. Пример: 08:00-20:00")
            return

    await state.update_data(schedule_sun=val)
    data = await state.get_data()

    schedule = {
        "mon": data["schedule_wd"], "tue": data["schedule_wd"], "wed": data["schedule_wd"],
        "thu": data["schedule_wd"], "fri": data["schedule_wd"],
        "sat": data["schedule_sat"], "sun": data["schedule_sun"],
    }

    full_address = f"{data['city']}, ул. {data['street']}, д. {data['house']}"

    async with async_session() as session:
        shop = Shop(
            tg_id=message.from_user.id, name=data["name"],
            city=data["city"], street=data["street"], house=data["house"], address=full_address,
            phone=data["phone"], telegram=data.get("telegram"), vk_link=data.get("vk_link"),
            owner_name=data.get("owner_name"), lat=data["lat"], lon=data["lon"],
            schedule=helpers.schedule_to_str(schedule), status="pending",
        )
        session.add(shop)
        await session.commit()

    await state.clear()
    await message.answer(
        "✅ <b>Заявка отправлена!</b>\n\nЖдём одобрения админа.",
        reply_markup=kb.shop_back()
    )

    try:
        await bot_admin.send_message(
            config.ADMIN_ID,
            f"🏪 <b>Новая заявка магазина</b>\n\n📛 {data['name']}\n📍 {full_address}\n📞 {data['phone']}",
            reply_markup=kb.admin_approve_shop(shop.id)
        )
    except Exception: pass

# ═══════════════════════════════════════════
#   ОСТАЛЬНЫЕ ХЭНДЛЕРЫ (СМЕНА, ТОВАРЫ, ЗАКАЗЫ И Т.Д.)
# ═══════════════════════════════════════════
@router.callback_query(F.data == "shop_on_shift")
async def on_shift(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop: return
        shop.is_on_shift = True
        await session.commit()
        await notify.flush_outbox_for_shop(session, shop.id)

    await call.answer("🟢 Вы на смене! Накопленные заказы отправлены.")
    await show_shop_menu(call.message, shop, edit=True)

@router.callback_query(F.data == "shop_off_shift")
async def off_shift(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop: return
        shop.is_on_shift = False
        await session.commit()
    await call.answer("🔴 Вы ушли со смены.")
    await show_shop_menu(call.message, shop, edit=True)

@router.callback_query(F.data == "shop_my_products")
async def my_products(call: CallbackQuery):
    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop: return
        result = await session.execute(select(Product).where(Product.shop_id == shop.id).order_by(Product.id.desc()))
        products = result.scalars().all()

    if not products:
        await call.message.edit_text("📦 Товаров нет. Нажмите «Добавить товар».", reply_markup=kb.shop_products_menu())
        await call.answer()
        return

    items = [{"id": p.id, "title": p.title, "price": helpers.money(p.shop_price), "is_active": p.is_active, "is_draft": p.is_draft} for p in products[:10]]
    await call.message.edit_text(f"📦 <b>Ваши товары ({len(products)})</b>", reply_markup=kb.shop_products_list(items))
    await call.answer()

@router.callback_query(F.data.startswith("shop_prod_view_"))
async def prod_view(call: CallbackQuery):
    product_id = int(call.data.split("_")[3])
    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        product = r.scalar_one_or_none()
        if not product: return

    text = (
        f"📦 <b>{product.title}</b>\n\n📝 {product.description or '—'}\n\n"
        f"💰 Ваша: {helpers.money(product.shop_price)}\n💰 Клиент: {helpers.money(product.client_price)}\n"
        f"🏷 {helpers.category_name(product.category)}"
    )
    await call.message.edit_text(text, reply_markup=kb.shop_product_manage(product_id, product.is_active, product.is_draft))
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

@router.callback_query(F.data == "shop_add_product")
async def add_product_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopProduct.photo)
    await call.message.edit_text("📸 <b>Шаг 1/5:</b> Отправьте фото товара", reply_markup=kb.cancel_kb("shop_main"))
    await call.answer()

@router.message(ShopProduct.photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ShopProduct.title)
    await message.answer("📝 <b>Шаг 2/5:</b> Название", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopProduct.title)
async def add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ShopProduct.description)
    await message.answer("📝 <b>Шаг 3/5:</b> Описание", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopProduct.description)
async def add_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(ShopProduct.price)
    await message.answer("💰 <b>Шаг 4/5:</b> Ваша цена (₽)", reply_markup=kb.cancel_kb("shop_main"))

@router.message(ShopProduct.price)
async def add_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
        if price <= 0: raise ValueError
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
        f"💰 Ваша: {helpers.money(price)}\n💰 Клиент: {helpers.money(client_price)}\n\n<b>Шаг 5/5:</b> Категория:",
        reply_markup=kb.kb(rows)
    )

@router.callback_query(F.data.startswith("shop_prod_cat_"), ShopProduct.category)
async def add_cat(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("shop_prod_cat_", "")
    data = await state.get_data()

    async with async_session() as session:
        shop = await get_shop(session, call.from_user.id)
        if not shop: return

        product = Product(
            shop_id=shop.id, category=cat, title=data["title"],
            description=data.get("description"), photo_id=data["photo_id"],
            shop_price=data["shop_price"], markup=data["markup"],
            client_price=data["client_price"], is_active=True,
        )
        session.add(product)

        cat_check = await session.execute(select(ShopCategory).where(ShopCategory.shop_id == shop.id, ShopCategory.category == cat))
        if not cat_check.scalar_one_or_none():
            session.add(ShopCategory(shop_id=shop.id, category=cat))
        await session.commit()

    await state.clear()
    await call.message.edit_text(f"✅ Товар «{data['title']}» добавлен!", reply_markup=kb.shop_main(shop.is_on_shift))
    await call.answer()

# ... ОСТАЛЬНЫЕ ФУНКЦИИ (СВОЯ ДОСТАВКА, СТАТИСТИКА, НАСТРОЙКИ И Т.Д.) ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ ...
# (Вставь остаток кода из предыдущего сообщения, начиная с раздела НОВЫЕ ЗАКАЗЫ)
# ═══════════════════════════════════════════
#   УПРАВЛЕНИЕ ТОВАРОМ (РАБОЧИЕ КНОПКИ)
# ═══════════════════════════════════════════
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

# ── ИЗМЕНЕНИЕ ЦЕНЫ ──
@router.callback_query(F.data.startswith("shop_edit_price_"))
async def edit_price_start(call: CallbackQuery, state: FSMContext):
    product_id = int(call.data.split("_")[3])
    await state.update_data(edit_product_id=product_id)
    await state.set_state(ShopEdit.price)
    await call.message.edit_text("💰 Введите новую цену (₽):", reply_markup=kb.cancel_kb("shop_my_products"))
    await call.answer()

@router.message(ShopEdit.price)
async def edit_price_save(message: Message, state: FSMContext):
    try:
        new_price = float(message.text.replace(",", ".").strip())
        if new_price <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Введите число больше 0.")
        return

    data = await state.get_data()
    product_id = data.get("edit_product_id")

    markup = config.get_markup(new_price)
    client_price = new_price + markup

    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        p = r.scalar_one_or_none()
        if p:
            p.shop_price = Decimal(str(new_price))
            p.markup = Decimal(str(markup))
            p.client_price = Decimal(str(client_price))
            await session.commit()

    await state.clear()
    await message.answer("✅ Цена обновлена.", reply_markup=kb.shop_products_menu())

# ── ИЗМЕНЕНИЕ ФОТО ──
@router.callback_query(F.data.startswith("shop_edit_photo_"))
async def edit_photo_start(call: CallbackQuery, state: FSMContext):
    product_id = int(call.data.split("_")[3])
    await state.update_data(edit_product_id=product_id)
    await state.set_state(ShopEdit.photo)
    await call.message.edit_text("📸 Отправьте новое фото товара:", reply_markup=kb.cancel_kb("shop_my_products"))
    await call.answer()

@router.message(ShopEdit.photo, F.photo)
async def edit_photo_save(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    photo_id = message.photo[-1].file_id

    async with async_session() as session:
        r = await session.execute(select(Product).where(Product.id == product_id))
        p = r.scalar_one_or_none()
        if p:
            p.photo_id = photo_id
            await session.commit()

    await state.clear()
    await message.answer("✅ Фото обновлено.", reply_markup=kb.shop_products_menu())
