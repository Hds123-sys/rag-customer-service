"""
FastAPI 主应用入口
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, chat, documents
from app.core.config import settings
from app.core.database import engine, init_db
from app.services.document import document_service
from app.services.rag import rag_service

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
# 第三方 HTTP 库在 DEBUG 级别会把每次 TCP/TLS 连接、请求体都打出来,
# 日志量极大且会拖慢写入, 统一压到 WARNING
for _noisy_logger in ("httpcore", "httpx", "urllib3"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _warn_insecure_settings() -> None:
    """启动时提示不安全的默认配置, 避免把开发配置直接带上生产环境"""
    if settings.DEBUG:
        logger.warning(
            "DEBUG=True: 找回密码接口会直接返回验证码(dev_code), 仅供开发自测; 上线前请设为 False"
        )
    if "*" in settings.cors_origins:
        logger.warning("CORS_ORIGINS=*: 允许任意来源跨域访问, 上线前请收紧为实际前端域名")
    if not settings.SECRET_KEY or "change" in settings.SECRET_KEY.lower():
        logger.warning("SECRET_KEY 仍为示例值, 上线前请更换为强随机密钥")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动: 初始化数据库表、上传目录
    _warn_insecure_settings()
    init_db()
    document_service.touch()
    logger.info("%s v%s 启动完成", settings.APP_NAME, settings.APP_VERSION)
    yield
    # 关闭: 释放向量库资源
    rag_service.close()
    logger.info("服务已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    description="基于大语言模型与检索增强生成(RAG)的智能客服系统",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ---------------- CORS ----------------
_origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---------------- 路由 ----------------
app.include_router(auth.router, prefix="/api/auth", tags=["用户认证"])
app.include_router(documents.router, prefix="/api/documents", tags=["文档管理"])
app.include_router(chat.router, prefix="/api/chat", tags=["智能问答"])


# ---------------- 异常处理 ----------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first.get("loc", []) if item != "body")
    message = first.get("msg", "请求参数校验失败")
    detail = f"{location}: {message}" if location else message
    return JSONResponse(status_code=422, content={"detail": detail, "errors": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("未处理的异常: %s", exc)
    # 统一返回通用提示, 详细堆栈仅记录在服务端日志中
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ---------------- 基础接口 ----------------
@app.get("/", tags=["系统"], summary="服务信息")
async def root():
    return {
        "message": f"{settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


def _check_database() -> str:
    """探测数据库连通性"""
    try:
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据库健康检查失败: %s", exc)
        # 只返回状态, 不把底层异常细节暴露给客户端
        return "error"


@app.get("/health", tags=["系统"], summary="健康检查")
async def health_check():
    stats = rag_service.stats()
    database = _check_database()
    healthy = rag_service.ready and database == "ok"
    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": time.time(),
        "database": database,
        "knowledge_base": stats,
    }