# -*- coding: utf-8 -*-
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import config

log = logging.getLogger("slipi")

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_session():
    async with async_session() as session:
        yield session
