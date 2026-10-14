"""
数据模型定义(Pydantic)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


# ==================== 文档相关模型 ====================

class DocumentResponse(BaseModel):
    """文档响应模型"""
    id: str = Field(..., description="文档ID(文件内容哈希)")
    filename: str = Field(..., description="原始文件名")
    size: int = Field(..., description="文件字节数")
    created_at: float = Field(..., description="上传时间(Unix 秒)")
    modified_at: float = Field(..., description="修改时间(Unix 秒)")
    status: str = Field(default="processed", description="处理状态")
    chunks: int = Field(default=0, description="切分后的片段数量")
    file_type: str = Field(default="", description="文件类型")


# ==================== 聊天相关模型 ====================

class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="角色: user/assistant/system")
    content: str = Field(..., description="消息内容")
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


class SourceItem(BaseModel):
    """检索来源"""
    id: str
    score: float
    filename: str = ""
    text: str = ""
    page: Optional[int] = None
    chunk_index: int = 0


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., min_length=1, description="用户消息")
    chat_history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="对话历史")
    session_id: Optional[str] = Field(default=None, description="会话ID")


class ChatResponse(BaseModel):
    """聊天响应模型"""
    answer: str
    sources: List[SourceItem] = Field(default_factory=list)
    session_id: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


# ==================== 通用模型 ====================

class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str
    detail: Optional[str] = None


class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


# ==================== 认证相关模型 ====================

class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: str
    email: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    """Token响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PasswordResetRequest(BaseModel):
    """密码重置请求"""
    email: EmailStr = Field(..., description="邮箱")


class PasswordResetConfirm(BaseModel):
    """密码重置确认"""
    email: EmailStr = Field(..., description="邮箱")
    code: str = Field(..., min_length=4, max_length=8, description="验证码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class PasswordResetResponse(BaseModel):
    """密码重置请求响应"""
    message: str
    email: str
    dev_code: Optional[str] = Field(default=None, description="开发模式下返回的验证码")