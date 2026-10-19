# -*- coding: utf-8 -*-
"""
Flowers Express — подключение к базе данных.
Поддерживает SQLite (по умолчанию) и PostgreSQL (при наличии DATABASE_URL).

FIX (P0): PRAGMA foreign_keys=ON через event listener на "connect" — иначе CASCADE/RESTRICT
          не работают (SQLite выключает FK по умолчанию, PRAGMA per-connection).
FIX: PRAGMA journal_mode=WAL вынесен ДО транзакции — иначе на некоторых версиях
     падает «cannot change into wal mode from within a transaction».
NEW: load_config_from_db() — грузит Setting (праздничная наценка и т.д.) в config.
"""
import logging
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import config

log = logging.getLogger("flowers_express")


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════
#   НАСТРОЙКА ДВИЖКА
# ═══════════════════════════════════════════
is_sqlite = config.DATABASE_URL.startswith("sqlite")

connect_args = {"timeout": 30} if is_sqlite else {}

# Для PostgreSQL — явные размеры пула (на будущее). Для SQLite не критично.
engine_kwargs = dict(
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True,
)
if not is_sqlite:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(config.DATABASE_URL, **engine_kwargs)

# FIX (P0): PRAGMA foreign_keys=ON на КАЖДОЕ новое соединение.
# Без этого ON DELETE CASCADE / RESTRICT / SET NULL не работают — SQLite их игнорирует!
if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_on_connect(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
        # КРИТИЧНО: импорт моделей внутри функции,
        # чтобы SQLAlchemy видел их перед create_all
        import models  # noqa: F401

        if is_sqlite:
            # FIX: WAL и synchronous применяем на ОТДЕЛЬНОМ соединении в AUTOCOMMIT,
            # ДО основной транзакции — иначе на некоторых версиях SQLite
            # «cannot change into wal mode from within a transaction».
            async with engine.connect() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        log.info("✅ Таблицы успешно созданы!")

    except Exception as e:
        log.error(f"❌ Ошибка создания таблиц: {e}")
        raise e


# ═══════════════════════════════════════════
#   ЗАГРУЗКА НАСТРОЕК ИЗ БД В CONFIG
# ═══════════════════════════════════════════
async def load_config_from_db():
    """
    Читает таблицу Setting и обновляет config.<KEY>.
    Пример: Setting("HOLIDAY_MARKUP_PERCENT", "15") → config.HOLIDAY_MARKUP_PERCENT = 15.0
    Вызывать при старте, после init_db(). И после изменений в админке.
    """
    try:
        from models import Setting
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(select(Setting))
            settings = result.scalars().all()

        for s in settings:
            key = s.key
            raw = s.value
            # Пробуем привести к числу (int/float), иначе оставляем строкой
            val = raw
            try:
                val = float(raw)
                if val.is_integer():
                    val = int(val)
            except (TypeError, ValueError):
                pass

            if hasattr(config, key):
                setattr(config, key, val)
                log.info(f"⚙️ config.{key} = {val} (из БД)")
            else:
                log.warning(f"⚠️ Setting '{key}' — нет такого поля в config.py")
    except Exception as e:
        log.error(f"❌ Ошибка загрузки настроек из БД: {e}")


async def save_setting(key: str, value):
    """
    Сохраняет/обновляет одну настройку в БД и в config.
    Админ меняет → вызываем save_setting() → значение в БД + в памяти.
    """
    from models import Setting
    from sqlalchemy import select
    from utils.helpers import now_moscow

    try:
        async with async_session() as session:
            result = await session.execute(select(Setting).where(Setting.key == key))
            s = result.scalar_one_or_none()
            if s:
                s.value = str(value)
                s.updated_at = now_moscow()
            else:
                s = Setting(key=key, value=str(value), updated_at=now_moscow())
                session.add(s)
            await session.commit()

        # Обновляем config в памяти
        if hasattr(config, key):
            try:
                v = float(value)
                if v.is_integer():
                    v = int(v)
            except (TypeError, ValueError):
                v = value
            setattr(config, key, v)

        log.info(f"💾 Setting '{key}' = {value}")
        return True
    except Exception as e:
        log.error(f"❌ Ошибка сохранения Setting '{key}': {e}")
        return False


# ═══════════════════════════════════════════
#   ФАБРИКА СЕССИЙ
# ═══════════════════════════════════════════
async def get_session():
    """Фабрика сессий (используется в хэндлерах)."""
    async with async_session() as session:
        yield session
