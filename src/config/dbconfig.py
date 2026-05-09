"""
数据库配置模块
从 database_config.json 加载数据库连接池配置
"""

import os
import json
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


def load_database_configs() -> Dict[str, Dict[str, Any]]:
    """加载所有数据库连接池配置"""
    config_file = get_database_config_file()
    if not os.path.exists(config_file):
        return {}
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        pools = data.get("pools", {})
        default_params = data.get("default_pool_params", DEFAULT_POOL_PARAMS)
        
        # 合并默认参数
        result = {}
        for pool_name, pool_config in pools.items():
            merged_config = {**default_params, **pool_config}
            result[pool_name] = merged_config
        
        return result
    except Exception:
        return {}


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