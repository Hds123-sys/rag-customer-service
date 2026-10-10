"""
数据库连接配置

默认使用 SQLite(零配置, 开箱即用); 若配置了 MySQL 连接串则自动切换到 MySQL。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

_url = settings.DATABASE_URL

_engine_kwargs = {"echo": False, "future": True}
if _url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 3600

engine = create_engine(_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖项: 提供数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有数据表(幂等)"""
    # 确保模型已注册到 Base.metadata
    from app.models import user  # noqa: F401

    Base.metadata.create_all(bind=engine)