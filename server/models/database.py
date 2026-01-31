"""
数据库连接模块

管理 MongoDB 和 DashVector 的连接。
"""

import os
from typing import Dict, Any

# MongoDB client (延迟导入)
_mongo_client = None
_mongo_db = None

# DashVector client (延迟导入)
_dashvector_client = None


async def connect_db():
    """
    连接所有数据库

    TODO:
    - 初始化 MongoDB Motor client
    - 初始化 DashVector client
    """
    global _mongo_client, _mongo_db, _dashvector_client

    # MongoDB 连接
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DATABASE", "entrocut")

    # TODO: 实际连接
    # from motor.motor_asyncio import AsyncIOMotorClient
    # _mongo_client = AsyncIOMotorClient(mongodb_uri)
    # _mongo_db = _mongo_client[db_name]

    # DashVector 连接
    # TODO: 实际连接
    # from dashvector import Client
    # dashvector_api_key = os.getenv("DASHVECTOR_API_KEY")
    # dashvector_endpoint = os.getenv("DASHVECTOR_ENDPOINT")
    # _dashvector_client = Client(api_key=dashvector_api_key, endpoint=dashvector_endpoint)

    print(f"✓ Database connections initialized (MongoDB: {mongodb_uri})")


async def close_db():
    """关闭所有数据库连接"""
    global _mongo_client, _dashvector_client

    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None

    # DashVector client 不需要显式关闭
    _dashvector_client = None

    print("✓ Database connections closed")


async def get_db_status() -> Dict[str, bool]:
    """
    获取数据库连接状态

    Returns:
        Dict: {"mongodb": bool, "dashvector": bool}
    """
    return {
        "mongodb": _mongo_client is not None,
        "dashvector": _dashvector_client is not None
    }


def get_db():
    """
    获取 MongoDB 数据库实例

    用于在路由中访问数据库。
    """
    return _mongo_db


def get_vector_client():
    """
    获取 DashVector 客户端实例

    用于在路由中访问向量数据库。
    """
    return _dashvector_client
