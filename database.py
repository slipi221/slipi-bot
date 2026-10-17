# -*- coding: utf-8 -*-
"""
Flowers Express — подключение к базе данных.
Поддерживает SQLite (по умолчанию) и PostgreSQL (при наличии DATABASE_URL).
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import config

log = logging.getLogger("flowers_express")

class Base(DeclarativeBase):
    pass

# ═══════════════════════════════════════════
#   НАСТРОЙКА ДВИЖКА
# ═══════════════════════════════════════════
# Проверяем, какая база используется (SQLite или PostgreSQL)
is_sqlite = config.DATABASE_URL.startswith("sqlite")

# Для SQLite нужен timeout, чтобы 4 бота не блокировали друг друга.
# Для PostgreSQL timeout не нужен (там своя система блокировок).
connect_args = {"timeout": 30} if is_sqlite else {}

engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True, # Проверка соединения перед использованием (защита от обрывов)
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ═══════════════════════════════════════════
#   ИНИЦИАЛИЗАЦИЯ И СОЗДАНИЕ ТАБЛИЦ
# ═══════════════════════════════════════════
async def init_db():
    """Создаёт все таблицы и включает WAL-режим (для SQLite)."""
    log.info(f"🔧 Инициализация БД: {config.DATABASE_URL}")
    
    try:
        # КРИТИЧНО: Импорт моделей внутри функции, чтобы SQLAlchemy видел их перед create_all
        import models  
        
        async with engine.begin() as conn:
            if is_sqlite:
                # Включаем WAL-режим только для SQLite (для PostgreSQL это не нужно)
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
            
            # Создаем все таблицы, которые описаны в models.py
            await conn.run_sync(Base.metadata.create_all)
            
        log.info("✅ Таблицы успешно созданы!")
    except Exception as e:
        log.error(f"❌ Ошибка создания таблиц: {e}")
        raise e

async def get_session():
    """Фабрика сессий (используется в хэндлерах)."""
    async with async_session() as session:
        yield session
