"""
认证服务模块
"""
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.schemas import UserRegisterRequest, UserResponse
from app.models.user import User

logger = logging.getLogger(__name__)

_RESET_CODE_TTL = 600


class AuthService:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._reset_codes: Dict[str, Tuple[str, float]] = {}
        self._reset_lock = threading.Lock()

    # ==================== 密码 ====================
    @staticmethod
    def hash_password(password: str) -> str:
        return hash_password(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return verify_password(plain_password, hashed_password)

    # ==================== Token ====================
    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "iat": now})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def decode_access_token(self, token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except JWTError:
            return None

    # ==================== 用户 ====================
    def register_user(self, db: Session, request: UserRegisterRequest) -> User:
        if db.query(User).filter(User.username == request.username).first():
            raise ValueError("用户名已存在")
        if db.query(User).filter(User.email == request.email).first():
            raise ValueError("邮箱已被注册")

        user = User(
            username=request.username,
            email=request.email,
            password_hash=self.hash_password(request.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def authenticate_user(self, db: Session, username: str, password: str) -> Optional[User]:
        user = db.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()
        if not user:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return user

    def get_user_by_id(self, db: Session, user_id: int) -> Optional[User]:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        return db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def to_user_response(user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    # ==================== 密码重置 ====================
    def issue_reset_code(self, email: str) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        with self._reset_lock:
            self._reset_codes[email] = (code, time.time() + _RESET_CODE_TTL)
        logger.info("已为 %s 生成密码重置验证码", email)
        return code

    def verify_reset_code(self, email: str, code: str) -> bool:
        with self._reset_lock:
            record = self._reset_codes.get(email)
        if not record:
            return False
        stored_code, expires_at = record
        if time.time() > expires_at:
            with self._reset_lock:
                self._reset_codes.pop(email, None)
            return False
        return secrets.compare_digest(stored_code, code)

    def reset_password(self, db: Session, email: str, code: str, new_password: str) -> bool:
        if not self.verify_reset_code(email, code):
            return False

        user = self.get_user_by_email(db, email)
        if not user:
            return False

        user.password_hash = self.hash_password(new_password)
        db.add(user)
        db.commit()
        with self._reset_lock:
            self._reset_codes.pop(email, None)
        return True


# 全局认证服务实例
auth_service = AuthService()