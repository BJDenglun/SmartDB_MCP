"""
API 用户配置模块
使用 user.json 进行 API Key 认证
"""
from config.user_config import validate_user_credentials

def validate_api_credentials(name: str, key: str):
    """验证 API 凭证 - 兼容 middleware.py 的接口"""
    return validate_user_credentials(name, key)

__all__ = ['validate_api_credentials']
