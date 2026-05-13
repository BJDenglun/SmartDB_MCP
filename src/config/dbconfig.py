"""
数据库配置模块
从 database_config.json 加载数据库连接池配置
"""

import os
import json
import time
from typing import Dict, Any


DEFAULT_POOL_PARAMS = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_recycle": 3600,
    "pool_timeout": 30
}


def get_database_config_file() -> str:
    """获取数据库配置文件路径"""
    return os.path.join(os.path.dirname(__file__), "database_config.json")


class DBConfigCache:
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


def _load_database_configs_raw() -> Dict[str, Dict[str, Any]]:
    """加载数据库配置 (无缓存)"""
    config_file = get_database_config_file()
    if not os.path.exists(config_file):
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        pools = data.get("pools", {})
        default_params = data.get("default_pool_params", DEFAULT_POOL_PARAMS)

        result = {}
        for pool_name, pool_config in pools.items():
            merged_config = {**default_params, **pool_config}
            result[pool_name] = merged_config

        return result
    except Exception:
        return {}


def load_database_configs() -> Dict[str, Dict[str, Any]]:
    """加载数据库配置 (带缓存)"""
    cache_key = "db_configs"
    cached = DBConfigCache.get(cache_key)
    if cached is not None:
        return cached

    data = _load_database_configs_raw()
    DBConfigCache.set(cache_key, data)
    return data


def get_db_configs() -> Dict[str, Dict[str, Any]]:
    """获取数据库配置（兼容旧接口）"""
    return load_database_configs()


def get_db_config_by_name(pool_name: str) -> Dict[str, Any]:
    """根据连接池名称获取配置"""
    configs = load_database_configs()
    if pool_name not in configs:
        raise ValueError(f"数据库配置 '{pool_name}' 不存在")
    return configs[pool_name]


def get_pool_names() -> list:
    """获取所有连接池名称"""
    return list(load_database_configs().keys())


def clear_db_cache() -> None:
    """清除数据库配置缓存 (用于配置热更新)"""
    DBConfigCache.clear()