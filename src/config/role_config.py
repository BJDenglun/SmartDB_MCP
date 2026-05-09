"""
角色权限配置模块
从 role.json 加载角色权限配置
"""

import os
import json
from typing import Dict, Any, Optional


def get_role_config_file() -> str:
    """获取角色配置文件路径"""
    return os.path.join(os.path.dirname(__file__), "role.json")


def load_role_configs() -> Dict[str, Dict[str, Any]]:
    """加载所有角色配置"""
    config_file = get_role_config_file()
    if not os.path.exists(config_file):
        return {}
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("roles", {})
    except Exception:
        return {}


def get_role_by_name(role_name: str) -> Optional[Dict[str, Any]]:
    """根据角色名称获取角色配置"""
    roles = load_role_configs()
    return roles.get(role_name)


def get_all_roles() -> Dict[str, Dict[str, Any]]:
    """获取所有角色配置"""
    return load_role_configs()