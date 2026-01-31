"""
认证相关路由

用户注册、登录、登出等。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()


# ============================================
# Models
# ============================================

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """认证响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


# ============================================
# Endpoints
# ============================================

@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """
    用户注册

    TODO: 实现密码哈希、用户创建、JWT 生成
    """
    # 临时实现
    return AuthResponse(
        access_token="temp_token",
        user_id="temp_user_id",
        username=request.username
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    用户登录

    TODO: 验证密码、生成 JWT
    """
    # 临时实现
    return AuthResponse(
        access_token="temp_token",
        user_id="temp_user_id",
        username="temp_user"
    )


@router.post("/logout")
async def logout():
    """
    用户登出

    TODO: 实现 token 黑名单机制
    """
    return {"message": "Logged out successfully"}
