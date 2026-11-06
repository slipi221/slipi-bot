# -*- coding: utf-8 -*-
"""
CityExpress — Подключение к базе данных (PostgreSQL)
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import config

log = logging.getLogger("cityexpress")

class Base(DeclarativeBase):
    pass

# Создаем движок для PostgreSQL
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db():
    """Создаёт все таблицы в PostgreSQL."""
    log.info("🔧 Инициализация PostgreSQL...")
    try:
        # Импортируем модели, чтобы SQLAlchemy их увидел
        import models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        log.info("✅ Таблицы успешно созданы в PostgreSQL!")
    except Exception as e:
        log.error(f"❌ Ошибка создания таблиц: {e}")
        raise e

async def load_config_from_db():
    """Заглушка для совместимости со старым кодом (настройки пока в config.py)."""
    pass

async def save_setting(key: str, value):
    """Заглушка для совместимости со старым кодом."""
    log.info(f"💾 Setting '{key}' = {value} (сохранение в БД пока отключено)")
    return True

async def get_session():
    """Фабрика сессий."""
    async with async_session() as session:
        yield session
