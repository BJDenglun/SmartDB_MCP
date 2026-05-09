"""
审计日志模块
记录所有 SQL 执行操作和权限违规事件，支持 7 天自动清理
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 日志保留天数
AUDIT_LOG_RETENTION_DAYS = 7


class AuditLevel(Enum):
    """审计级别"""
    SQL_EXECUTION = "sql_execution"
    PERMISSION_DENIED = "permission_denied"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    TOOL_ACCESS = "tool_access"
    ERROR = "error"


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    timestamp: str
    level: str
    username: str
    action: str
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AuditLogger:
    """审计日志记录器 - 支持 7 天自动清理"""
    
    def __init__(self, log_dir: str = None, retention_days: int = AUDIT_LOG_RETENTION_DAYS):
        if log_dir is None:
            # 默认使用项目 logs 目录
            project_root = Path(__file__).parent.parent.parent
            log_dir = project_root / "logs" / "audit"
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.retention_days = retention_days
        
        # 日志文件路径 (按日期分)
        self._current_date = datetime.now().strftime("%Y-%m-%d")
        self._log_file = self.log_dir / f"audit_{self._current_date}.log"
        
        # 确保日志文件存在
        if not self._log_file.exists():
            self._log_file.touch()
        
        # 启动时清理过期日志
        self._cleanup_old_logs()
    
    def _cleanup_old_logs(self):
        """清理超过保留期的日志文件"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            for log_file in self.log_dir.glob("audit_*.log"):
                try:
                    # 从文件名提取日期
                    date_str = log_file.stem.replace("audit_", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if file_date < cutoff_date:
                        log_file.unlink()
                        logger.info(f"已删除过期审计日志: {log_file.name}")
                except ValueError:
                    # 日期格式不正确，跳过
                    continue
        except Exception as e:
            logger.error(f"清理旧日志失败: {e}")
    
    def _rotate_if_needed(self):
        """检查是否需要轮转日志文件"""
        current_date = datetime.now().strftime("%Y-%m-%d")
        if current_date != self._current_date:
            self._current_date = current_date
            self._log_file = self.log_dir / f"audit_{self._current_date}.log"
    
    def _write_log(self, entry: AuditLogEntry):
        """写入日志条目"""
        self._rotate_if_needed()
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")
    
    def log_sql_execution(self, username: str, sql: str, pool_name: str, 
                          success: bool, result: str = "", 
                          execution_time: float = None, **kwargs):
        """记录 SQL 执行"""
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            level=AuditLevel.SQL_EXECUTION.value,
            username=username,
            action="execute_sql",
            details={
                "sql": sql,
                "pool_name": pool_name,
                "success": success,
                "result": result if result else "",
                "execution_time_ms": execution_time if execution_time else 0,
                **kwargs
            }
        )
        self._write_log(entry)
    
    def log_permission_denied(self, username: str, sql: str, 
                               reason: str = "", level: str = None, **kwargs):
        """记录权限拒绝事件"""
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            level=AuditLevel.PERMISSION_DENIED.value,
            username=username,
            action="permission_denied",
            details={
                "sql": sql,
                "reason": reason if reason else "未知原因",
                "level": level if level else "denied",
                **kwargs
            }
        )
        self._write_log(entry)
        logger.warning(f"权限拒绝: 用户 {username} 尝试执行 {sql[:100] if sql else 'N/A'}... 被拒绝: {reason}")
    
    def log_auth_success(self, username: str, **kwargs):
        """记录认证成功"""
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            level=AuditLevel.AUTH_SUCCESS.value,
            username=username,
            action="auth_success",
            details=kwargs
        )
        self._write_log(entry)
    
    def log_auth_failure(self, username: str, reason: str = "", **kwargs):
        """记录认证失败"""
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            level=AuditLevel.AUTH_FAILURE.value,
            username=username,
            action="auth_failure",
            details={
                "reason": reason if reason else "未知原因",
                **kwargs
            }
        )
        self._write_log(entry)
        logger.warning(f"认证失败: 用户 {username}, 原因: {reason}")
    
    def log_tool_access(self, username: str, tool_name: str, 
                        arguments: Dict[str, Any] = None, **kwargs):
        """记录工具访问"""
        # 隐藏敏感参数
        safe_args = self._sanitize_args(arguments) if arguments else {}
        
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            level=AuditLevel.TOOL_ACCESS.value,
            username=username,
            action=f"tool_{tool_name}",
            details={
                "tool_name": tool_name,
                "arguments": safe_args,
                **kwargs
            }
        )
        self._write_log(entry)
    
    def log_error(self, username: str, action: str, error: str = "", **kwargs):
        """记录错误"""
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            level=AuditLevel.ERROR.value,
            username=username,
            action=action,
            details={
                "error": error if error else "未知错误",
                **kwargs
            }
        )
        self._write_log(entry)
    
    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """清理敏感参数"""
        sensitive_keys = ['password', 'secret', 'token', 'apikey', 'credential']
        sanitized = {}
        for key, value in args.items():
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_keys):
                sanitized[key] = "***"
            else:
                sanitized[key] = value
        return sanitized
    
    def get_logs(self, start_date: str = None, end_date: str = None,
                 username: str = None, level: str = None,
                 limit: int = 100) -> List[Dict[str, Any]]:
        """查询审计日志"""
        logs = []
        
        # 如果没有指定日期范围，默认查询当天
        if start_date is None:
            start_date = self._current_date
        if end_date is None:
            end_date = self._current_date
        
        # 遍历日期范围内的日志文件
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            log_file = self.log_dir / f"audit_{date_str}.log"
            
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                try:
                                    entry = json.loads(line)
                                    
                                    # 应用过滤条件
                                    if username and entry.get("username") != username:
                                        continue
                                    if level and entry.get("level") != level:
                                        continue
                                    
                                    logs.append(entry)
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                    logger.error(f"读取日志文件 {log_file} 失败: {e}")
            
            current = datetime(current.year, current.month, current.day + 1)
        
        # 限制返回数量
        return logs[-limit:] if len(logs) > limit else logs


# 全局审计日志实例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取全局审计日志实例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def log_sql_execution(username: str, sql: str, pool_name: str,
                     success: bool, result: str = "", 
                     execution_time: float = None, **kwargs):
    """快捷函数：记录 SQL 执行"""
    get_audit_logger().log_sql_execution(username, sql, pool_name, success, result, execution_time, **kwargs)


def log_permission_denied(username: str, sql: str, reason: str = "", **kwargs):
    """快捷函数：记录权限拒绝"""
    get_audit_logger().log_permission_denied(username, sql, reason, **kwargs)


def log_tool_access(username: str, tool_name: str, arguments: Dict[str, Any] = None, **kwargs):
    """快捷函数：记录工具访问"""
    get_audit_logger().log_tool_access(username, tool_name, arguments, **kwargs)