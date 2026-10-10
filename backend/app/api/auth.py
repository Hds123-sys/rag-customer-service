"""
认证API路由
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.schemas import (
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.models.user import User
from app.services.auth import auth_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/register", response_model=TokenResponse, summary="用户注册")
async def register(request: UserRegisterRequest, db: Session = Depends(get_db)):
    try:
        user = auth_service.register_user(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("注册失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"注册失败: {exc}"
        ) from exc

    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=auth_service.to_user_response(user),
    )


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    try:
        user = auth_service.authenticate_user(db, request.username, request.password)
    except Exception as exc:  # noqa: BLE001
        logger.exception("登录失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"登录失败: {exc}"
        ) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )

    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=auth_service.to_user_response(user),
    )


@router.post("/logout", response_model=MessageResponse, summary="退出登录")
async def logout(current_user: User = Depends(get_current_user)):
    # JWT 为无状态令牌, 客户端清除本地 Token 即可
    return MessageResponse(message="退出成功")


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return auth_service.to_user_response(current_user)


@router.post("/reset-password", response_model=PasswordResetResponse, summary="请求密码重置验证码")
async def request_password_reset(request: PasswordResetRequest, db: Session = Depends(get_db)):
    user = auth_service.get_user_by_email(db, request.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邮箱未注册")

    code = auth_service.issue_reset_code(request.email)
    # 未接入邮件服务: 开发模式下直接返回验证码, 便于自测
    dev_code = code if settings.DEBUG else None
    return PasswordResetResponse(
        message="验证码已发送到邮箱" if not settings.DEBUG else "验证码已生成(开发模式)",
        email=request.email,
        dev_code=dev_code,
    )


@router.post("/reset-password/confirm", response_model=MessageResponse, summary="确认重置密码")
async def confirm_password_reset(request: PasswordResetConfirm, db: Session = Depends(get_db)):
    user = auth_service.get_user_by_email(db, request.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邮箱未注册")

    if not auth_service.reset_password(db, request.email, request.code, request.new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期")

    return MessageResponse(message="密码重置成功，请使用新密码登录")