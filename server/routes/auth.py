"""
认证相关路由

用户注册、登录、登出等。

Round 4: 认证功能未实现，返回 501 Not Implemented
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from middleware.error_handler import NotImplementedException

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

    Round 4: 认证功能未实现，返回 501
    计划在 Round 5+ 实现 MongoDB + JWT
    """
    raise NotImplementedException("Authentication: User Registration")


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    用户登录

    Round 4: 认证功能未实现，返回 501
    计划在 Round 5+ 实现 MongoDB + JWT
    """
    raise NotImplementedException("Authentication: User Login")


@router.post("/logout")
async def logout():
    """
    用户登出

    Round 4: 认证功能未实现，返回 501
    计划在 Round 5+ 实现 Token 黑名单
    """
    raise NotImplementedException("Authentication: User Logout")
