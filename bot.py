# -*- coding: utf-8 -*-
import sqlite3, threading, time, math
from datetime import datetime, date
import telebot
from telebot import types
import config

DB = "/data/flower.db"

def db(q, p=(), fetch=None):
    con = sqlite3.connect(DB); cur = con.cursor(); cur.execute(q, p)
    if fetch == "one": r = cur.fetchone()
    elif fetch == "all": r = cur.fetchall()
    else: con.commit(); r = cur.lastrowid
    con.close(); return r

def now(): return datetime.now().strftime("%d.%m.%Y %H:%M")
def today(): return date.today().strftime("%Y-%m-%d")

def db_init():
    con = sqlite3.connect(DB); c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS shops (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, name TEXT, address TEXT, phone TEXT, telegram TEXT, vk TEXT, owner_name TEXT, status TEXT DEFAULT 'pending', rating REAL DEFAULT 0, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, name TEXT, phone TEXT, city TEXT, transport TEXT, card TEXT, balance REAL DEFAULT 0, status TEXT DEFAULT 'pending', rating REAL DEFAULT 0, lat REAL, lon REAL, loc_time TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER, courier_id INTEGER, shop_name TEXT, address_from TEXT, address_to TEXT, client_name TEXT, client_phone TEXT, client_tg_id INTEGER, delivery_time TEXT, order_price REAL, delivery_price REAL, commission REAL, courier_fee REAL, comment TEXT, status TEXT DEFAULT 'new', payment_status TEXT DEFAULT 'pending', created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS shifts (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, date TEXT, slot TEXT, status TEXT DEFAULT 'booked', checked_in TEXT, penalty REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, courier_id INTEGER, amount REAL, card TEXT, status TEXT DEFAULT 'pending', created_at TEXT)")
    con.commit(); con.close()

bot_client = telebot.TeleBot(config.CLIENT_TOKEN)
bot_shop = telebot.TeleBot(config.SHOP_TOKEN)
bot_courier = telebot.TeleBot(config.COURIER_TOKEN)
bot_admin = telebot.TeleBot(config.ADMIN_TOKEN)

shop_reg, cour_reg, order_reg, withdraw_reg = {}, {}, {}, {}

def kb_shop():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🆕 Создать заявку"); k.row("📋 Мои заявки", "📊 Статистика"); k.row("⚙️ Настройки")
    return k

def kb_courier():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("📋 Свободные заявки"); k.row("🚗 Мои заказы", "💰 Заработок"); k.row("📅 Смены", "📍 Гео"); k.row("📊 Статистика")
    return k

def kb_admin():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("📝 Запросы"); k.row("🏪 Магазины", "🚚 Курьеры"); k.row("💰 Финансы", "💳 Выплаты"); k.row("📅 Смены")
    return k

def kb_admin_req():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🏪 Заявки магазинов"); k.row("🚚 Заявки курьеров"); k.row("📅 Заявки смен")
    k.row("💳 Заявки выплат"); k.row("❌ Отмены заявок"); k.row("⬅️ Назад")
    return k

def kb_client():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🏪 Магазины"); k.row("ℹ️ О сервисе")
    return k

def kb_cancel():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True); k.row("❌ Отмена")
    return k

def kb_shift_slots():
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.row("🌅 Утренняя 7–15"); k.row("☀️ Дневная 9–18"); k.row("🌆 Вечерняя 15–23")
    k.row("🌙 Ночная 18–00"); k.row("📋 Мои смены"); k.row("⬅️ Назад")
    return k

def is_cancel(m): return m.text == "❌ Отмена"
def geo_link(lat, lon): return f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"
