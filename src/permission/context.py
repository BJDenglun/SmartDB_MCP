"""
请求上下文管理模块
用于存储当前请求的用户信息
"""

from contextvars import ContextVar
from typing import Optional, Dict, Any

# 使用 ContextVar 存储当前用户信息
_current_user: ContextVar[Optional[Dict[str, Any]]] = ContextVar('current_user', default=None)


def set_current_user(user_info: Dict[str, Any]) -> None:
    """设置当前用户信息
    
    Args:
        user_info: 用户信息字典，包含 username 和 api_key
    """
    _current_user.set(user_info)


def get_current_user() -> Optional[Dict[str, Any]]:
    """获取当前用户信息
    
    Returns:
        用户信息字典，如果未设置则返回 None
    """
    return _current_user.get()


def get_current_username() -> Optional[str]:
    """获取当前用户名
    
    Returns:
        用户名，如果未设置则返回 None
    """
    user = _current_user.get()
    return user.get("username") if user else None


def get_current_user_role() -> Optional[str]:
    """获取当前用户角色
    
    Returns:
        角色名，如果未设置则返回 None
    """
    user = _current_user.get()
    return user.get("role") if user else None


def clear_current_user() -> None:
    """清除当前用户信息"""
    _current_user.set(None)