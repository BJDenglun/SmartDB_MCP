"""
用户配置模块
从 user.json 加载用户配置
"""

import os
import json
import time
from typing import Dict, Any, Optional, List


def get_user_config_file() -> str:
    """获取用户配置文件路径"""
    return os.path.join(os.path.dirname(__file__), "user.json")


class ConfigCache:
    """简单配置缓存 (TTL 5分钟)"""
    _cache: Dict[str, Any] = {}
    _timestamps: Dict[str, float] = {}
    _ttl = 300  # 5分钟

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        if key in cls._cache:
            if time.time() - cls._timestamps.get(key, 0) < cls._ttl:
                return cls._cache[key]
            cls._cache.pop(key, None)
            cls._timestamps.pop(key, None)
        return None

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        cls._cache[key] = value
        cls._timestamps[key] = time.time()

    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()
        cls._timestamps.clear()


def _load_user_configs_raw() -> List[Dict[str, Any]]:
    """加载所有用户配置 (无缓存)"""
    config_file = get_user_config_file()
    if not os.path.exists(config_file):
        return []

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def load_user_configs() -> List[Dict[str, Any]]:
    """加载所有用户配置 (带缓存)"""
    cache_key = "user_configs"
    cached = ConfigCache.get(cache_key)
    if cached is not None:
        return cached

    data = _load_user_configs_raw()
    ConfigCache.set(cache_key, data)
    return data


def get_user_by_name(name: str) -> Optional[Dict[str, Any]]:
    """根据用户名获取用户配置"""
    users = load_user_configs()
    for user in users:
        if user.get("name") == name:
            return user
    return None


def validate_user_credentials(name: str, key: str) -> Optional[Dict[str, Any]]:
    """验证用户凭证"""
    user = get_user_by_name(name)
    if not user:
        return None
    if user.get("key") != key:
        return None
    return user


def get_all_users() -> List[Dict[str, Any]]:
    """获取所有用户配置（不含密钥）"""
    users = load_user_configs()
    return [{k: v for k, v in u.items() if k != 'key'} for u in users]


def clear_user_cache() -> None:
    """清除用户配置缓存 (用于配置热更新)"""
    ConfigCache.clear()