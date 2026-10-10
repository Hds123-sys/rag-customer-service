"""
核心配置模块

所有配置项均可通过环境变量或 .env 文件覆盖。
加载顺序（后者覆盖前者）: 项目根目录/.env -> backend/.env -> 环境变量
"""
from pathlib import Path
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（本文件位于 backend/app/core/config.py）
BACKEND_DIR = Path(__file__).resolve().parents[2]
# 项目根目录（backend/ 的上一级）
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==================== 应用配置 ====================
    APP_NAME: str = "智能客服RAG系统"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True

    # ==================== 服务器配置 ====================
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ==================== 大模型配置(OpenAI 兼容接口) ====================
    API_BASE_URL: str = "https://token.uino.com/v1"
    API_KEY: str = ""
    API_MODEL: str = "gpt-6-sol"
    API_TIMEOUT: float = 120.0

    # ==================== 向量化配置 ====================
    # local: 使用内置的离线向量化算法(无需外部服务)
    # openai: 调用 OpenAI 兼容的 /v1/embeddings 接口
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIM: int = 1024
    EMBEDDING_API_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""

    # ==================== 向量库配置 ====================
    # auto: 优先连接 Qdrant 服务, 失败则回退到内置本地向量库(无需 Docker)
    # local: 强制使用内置本地向量库
    # qdrant: 强制连接 Qdrant 服务
    VECTOR_STORE_MODE: str = "auto"
    # 本地向量库数据目录, 留空则使用 backend/data
    VECTOR_STORE_PATH: str = ""
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "documents"

    # ==================== 检索配置 ====================
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 80
    TOP_K_RESULTS: int = 4
    VECTOR_WEIGHT: float = 0.6
    KEYWORD_WEIGHT: float = 0.4
    MIN_SCORE: float = 0.05

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: str = ".pdf,.txt,.md"

    # ==================== 对话配置 ====================
    MAX_CONTEXT_LENGTH: int = 4000
    TEMPERATURE: float = 0.3
    CHAT_HISTORY_MAX_TURNS: int = 6
    CHAT_SESSION_TTL: int = 3600

    # ==================== 数据库配置 ====================
    DATABASE_URL: str = "sqlite:///./rag_system.db"

    # ==================== JWT配置 ====================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    RESET_CODE_TTL_SECONDS: int = 600

    # ==================== 限流配置 ====================
    # 规则格式: "次数/窗口秒数"; 填 "0/0" 表示不限制
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REGISTER: str = "30/3600"
    RATE_LIMIT_LOGIN: str = "30/60"
    RATE_LIMIT_RESET_REQUEST: str = "10/600"
    RATE_LIMIT_RESET_CONFIRM: str = "20/600"
    RATE_LIMIT_CHAT: str = "60/60"

    # ==================== CORS配置 ====================
    CORS_ORIGINS: str = "*"

    @model_validator(mode="after")
    def _normalize(self) -> "Settings":
        # sqlite 相对路径统一转换为绝对路径, 避免受启动目录影响
        if self.DATABASE_URL.startswith("sqlite"):
            prefix = "sqlite:///"
            if self.DATABASE_URL.startswith(prefix):
                raw = self.DATABASE_URL[len(prefix):]
                p = Path(raw)
                if not p.is_absolute():
                    p = (BACKEND_DIR / p).resolve()
                    self.DATABASE_URL = f"sqlite:///{p.as_posix()}"

        if not self.EMBEDDING_API_BASE_URL:
            self.EMBEDDING_API_BASE_URL = self.API_BASE_URL
        if not self.EMBEDDING_API_KEY:
            self.EMBEDDING_API_KEY = self.API_KEY
        return self

    @property
    def allowed_extensions(self) -> set:
        """允许上传的文件扩展名集合"""
        raw = (self.ALLOWED_EXTENSIONS or "").replace(";", ",").replace(" ", ",")
        result = set()
        for item in raw.split(","):
            item = item.strip().lower()
            if not item:
                continue
            result.add(item if item.startswith(".") else f".{item}")
        return result

    @property
    def cors_origins(self) -> List[str]:
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        return p

    @property
    def vector_store_path(self) -> Path:
        p = Path(self.VECTOR_STORE_PATH) if self.VECTOR_STORE_PATH else (BACKEND_DIR / "data")
        if not p.is_absolute():
            p = BACKEND_DIR / p
        return p


settings = Settings()