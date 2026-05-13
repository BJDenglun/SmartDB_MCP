"""
角色权限配置模块
从 role.json 加载角色权限配置
"""

import os
import json
import time
from typing import Dict, Any, Optional


def get_role_config_file() -> str:
    """获取角色配置文件路径"""
    return os.path.join(os.path.dirname(__file__), "role.json")


class RoleConfigCache:
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


def _load_role_configs_raw() -> Dict[str, Dict[str, Any]]:
    """加载所有角色配置 (无缓存)"""
    config_file = get_role_config_file()
    if not os.path.exists(config_file):
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("roles", {})
    except Exception:
        return {}


def load_role_configs() -> Dict[str, Dict[str, Any]]:
    """加载所有角色配置 (带缓存)"""
    cache_key = "role_configs"
    cached = RoleConfigCache.get(cache_key)
    if cached is not None:
        return cached

    data = _load_role_configs_raw()
    RoleConfigCache.set(cache_key, data)
    return data


def get_role_by_name(role_name: str) -> Optional[Dict[str, Any]]:
    """根据角色名称获取角色配置"""
    roles = load_role_configs()
    return roles.get(role_name)


def get_all_roles() -> Dict[str, Dict[str, Any]]:
    """获取所有角色配置"""
    return load_role_configs()


def clear_role_cache() -> None:
    """清除角色配置缓存 (用于配置热更新)"""
    RoleConfigCache.clear()