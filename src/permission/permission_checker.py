"""
权限检查模块
实现池级别、数据库、表、列级别的权限验证，支持行级别过滤
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from config.user_config import get_user_by_name
from config.role_config import get_role_by_name

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """权限级别枚举"""
    DENIED = "denied"
    POOL_LEVEL = "pool_level"
    DATABASE_LEVEL = "database_level"
    TABLE_LEVEL = "table_level"
    COLUMN_LEVEL = "column_level"
    FULL_ACCESS = "full_access"


@dataclass
class PermissionResult:
    """权限检查结果"""
    allowed: bool
    level: PermissionLevel
    message: str
    denied_pools: List[str] = field(default_factory=list)
    denied_tables: List[str] = field(default_factory=list)
    denied_columns: Dict[str, List[str]] = field(default_factory=dict)
    row_filter: Optional[str] = None
    max_rows: int = 1000  # 最大返回行数


class PermissionChecker:
    """权限检查器 - 支持池、数据库、表、列、行级别权限"""
    
    def __init__(self, username: str):
        self.username = username
        self.user_config = get_user_by_name(username)
        self._role_config = None
        
    @property
    def role_name(self) -> str:
        """获取用户角色名称"""
        if self.user_config:
            return self.user_config.get("role", "")
        return ""
    
    @property
    def role_config(self) -> Dict[str, Any]:
        """获取角色权限配置"""
        if self._role_config is None:
            self._role_config = get_role_by_name(self.role_name) or {}
        return self._role_config
    
    @property
    def max_rows(self) -> int:
        """获取最大返回行数"""
        return self.role_config.get("max_rows", 1000)
    
    @property
    def sql_operations(self) -> Set[str]:
        """获取允许的 SQL 操作列表"""
        operations = self.role_config.get("sql_operations", [])
        if "*" in operations:
            return {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE", "SHOW", "DESCRIBE", "EXPLAIN"}
        return set(operations)
    
    @property
    def allowed_pools(self) -> List[str]:
        """获取允许访问的连接池列表，* 表示全部"""
        return self.role_config.get("allowed_pools", [])
    
    @property
    def pool_configs(self) -> Dict[str, Dict[str, Any]]:
        """获取各连接池的权限配置"""
        return self.role_config.get("pools", {})
    
    def _match_pattern(self, pattern: str, target: str) -> bool:
        """匹配通配符模式"""
        if pattern == "*":
            return True
        return pattern.lower() == target.lower()
    
    def _parse_table_key(self, key: str) -> Tuple[str, str]:
        """解析表键为 (database, table) 元组"""
        parts = key.split(".", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "default", parts[0]
    
    def _get_pool_config(self, pool_name: str) -> Optional[Dict[str, Any]]:
        """获取指定连接池的配置"""
        pools = self.pool_configs
        # 先查找具体 pool_name
        if pool_name in pools:
            return pools[pool_name]
        # 再查找通配符 *
        if "*" in pools:
            return pools["*"]
        return None
    
    def _check_pool_access(self, pool_name: str) -> bool:
        """检查连接池访问权限，* 表示全部连接池"""
        allowed = self.allowed_pools
        if not allowed:
            return False
        if "*" in allowed:
            return True
        return any(self._match_pattern(p, pool_name) for p in allowed)
    
    def _get_database_config(self, pool_name: str, database: str) -> Optional[Dict[str, Any]]:
        """获取指定池和数据库的配置"""
        pool_config = self._get_pool_config(pool_name)
        if not pool_config:
            return None
        
        databases = pool_config.get("allowed_databases", [])
        if "*" in databases:
            return pool_config
        
        if database in databases:
            return pool_config
        return None
    
    def _check_database_access(self, pool_name: str, database: str) -> bool:
        """检查数据库访问权限"""
        pool_config = self._get_pool_config(pool_name)
        if not pool_config:
            return False
        
        allowed = pool_config.get("allowed_databases", [])
        if not allowed:
            return False
        if "*" in allowed:
            return True
        return any(self._match_pattern(p, database) for p in allowed)
    
    def _check_table_access(self, pool_name: str, database: str, table: str) -> bool:
        """检查表访问权限"""
        pool_config = self._get_pool_config(pool_name)
        if not pool_config:
            return False
        
        # 检查数据库是否允许
        if not self._check_database_access(pool_name, database):
            return False
        
        # 获取该数据库允许的表 - 优先使用数据库特定的配置
        tables_config = pool_config.get("allowed_tables", {})
        
        # 尝试直接匹配（不区分大小写）
        tables_for_db = []
        database_lower = database.lower()
        for key, value in tables_config.items():
            if key.lower() == database_lower:
                tables_for_db = value
                break
        
        # 如果没有找到特定配置，尝试通配符
        if not tables_for_db:
            tables_for_db = tables_config.get("*", [])
        
        # 检查通配符
        if "*" in tables_for_db:
            return True
        
        # 检查具体表名（不区分大小写）
        table_lower = table.lower()
        allowed_lower = [t.lower() for t in tables_for_db]
        return table_lower in allowed_lower
    
    def _check_column_access(self, pool_name: str, database: str, table: str, columns: List[str]) -> Tuple[bool, List[str]]:
        """检查列访问权限，返回 (是否允许, 被拒绝的列列表)"""
        # 先检查表权限
        if not self._check_table_access(pool_name, database, table):
            return False, ["表无权限"]
        
        pool_config = self._get_pool_config(pool_name)
        if not pool_config:
            return False, ["池配置无效"]
        
        # 构建可能的键名
        keys = [
            f"{database}.{table}",
            f"*.{table}",
            f"{database}.*"
        ]
        
        # 查找列配置
        allowed_cols = []
        for key in keys:
            if key in pool_config.get("allowed_columns", {}):
                allowed_cols = pool_config["allowed_columns"][key]
                break
        
        # 如果没有配置列权限且不是通配符配置，则允许所有列
        if not allowed_cols:
            return True, []
        
        # 如果是通配符
        if "*" in allowed_cols:
            return True, []
        
        # 检查每个请求的列
        denied = []
        for col in columns:
            if col.upper() not in [c.upper() for c in allowed_cols]:
                denied.append(col)
        
        return len(denied) == 0, denied
    
    def _get_row_filter(self, pool_name: str, database: str, table: str) -> Optional[str]:
        """获取表级别的行过滤条件"""
        pool_config = self._get_pool_config(pool_name)
        if not pool_config:
            return None
        
        keys = [
            f"{database}.{table}",
            f"*.{table}"
        ]
        
        row_filters = pool_config.get("row_filters", {})
        for key in keys:
            if key in row_filters:
                return row_filters[key]
        return None
    
    def _extract_tables_from_sql(self, sql: str) -> List[Tuple[str, str]]:
        """从 SQL 语句中提取表名 (database.table 格式)"""
        tables = []
        sql_upper = sql.upper()
        
        # 匹配 FROM 和 JOIN 后面的表名，支持 schema.table 格式
        # 处理 FETCH FIRST, ORDER BY, WHERE 等子句
        # 移除 FETCH FIRST、ORDER BY 等子句以便于解析
        clean_sql = re.sub(r'\s+FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY', '', sql_upper, flags=re.IGNORECASE)
        clean_sql = re.sub(r'\s+ORDER\s+BY\s+.*', '', clean_sql, flags=re.IGNORECASE)
        clean_sql = re.sub(r'\s+WHERE\s+.*', '', clean_sql, flags=re.IGNORECASE)
        
        # 匹配 FROM/JOIN 后面的表名 (可能带有 schema.)
        pattern = r'(?:FROM|JOIN)\s+(?:(\w+)\.)?(\w+)'
        matches = re.findall(pattern, clean_sql)
        
        for db, table in matches:
            database = db if db else "default"
            if database == "DEFAULT":
                database = "default"
            tables.append((database.lower(), table.lower()))
        
        return list(set(tables))  # 去重
    
    def _extract_columns_from_select(self, sql: str) -> List[str]:
        """从 SELECT 语句中提取列名"""
        columns = []
        sql_upper = sql.upper()
        
        # 简单提取 SELECT 和 FROM 之间的内容
        match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.DOTALL)
        if match:
            cols_str = match.group(1)
            # 分割列，可能有别名
            for col in cols_str.split(','):
                col = col.strip()
                # 处理表名.列名格式
                if '.' in col:
                    col = col.split('.')[-1]
                # 移除别名
                if ' AS ' in col.upper():
                    col = re.split(r'\s+AS\s+', col, flags=re.IGNORECASE)[0].strip()
                # 移除函数
                col = re.sub(r'^[A-Z_]+\s*\(', '', col).rstrip(')')
                if col and col != '*':
                    columns.append(col.strip())
        
        return columns
    
    def check_sql_permission(self, sql: str, pool_name: str = "default") -> PermissionResult:
        """
        检查 SQL 语句的权限
        
        Args:
            sql: SQL 语句
            pool_name: 连接池名称
            
        Returns:
            PermissionResult: 权限检查结果
        """
        try:
            if not self.user_config:
                return PermissionResult(
                    allowed=False,
                    level=PermissionLevel.DENIED,
                    message=f"用户 '{self.username}' 不存在"
                )
            
            # 检查连接池权限
            if not self._check_pool_access(pool_name):
                return PermissionResult(
                    allowed=False,
                    level=PermissionLevel.POOL_LEVEL,
                    message=f"无权访问连接池: {pool_name}",
                    denied_pools=[pool_name]
                )
            
            # 提取 SQL 操作类型
            sql_upper = sql.strip().upper()
            operation_match = re.match(r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|SHOW|DESCRIBE|EXPLAIN)', sql_upper)
            if not operation_match:
                return PermissionResult(
                    allowed=False,
                    level=PermissionLevel.DENIED,
                    message="无法识别的 SQL 操作类型"
                )
            
            operation = operation_match.group(1)
            
            # 检查 SQL 操作权限
            if operation not in self.sql_operations:
                return PermissionResult(
                    allowed=False,
                    level=PermissionLevel.DENIED,
                    message=f"角色 '{self.role_name}' 无权执行 '{operation}' 操作"
                )
            
            # 检查表访问权限
            tables = self._extract_tables_from_sql(sql)
            denied_tables = []
            
            for database, table in tables:
                if not self._check_table_access(pool_name, database, table):
                    denied_tables.append(f"{database}.{table}")
            
            if denied_tables:
                return PermissionResult(
                    allowed=False,
                    level=PermissionLevel.TABLE_LEVEL,
                    message=f"无权访问以下表: {', '.join(denied_tables)}",
                    denied_tables=denied_tables
                )
            
            # 检查列访问权限（仅 SELECT 操作）
            row_filter = None
            if operation == "SELECT":
                columns = self._extract_columns_from_select(sql)
                
                # 检查是否使用 SELECT *
                has_wildcard = any(c == '*' for c in sql_upper.split('FROM')[0].replace('SELECT', '').split(','))
                
                for database, table in tables:
                    if has_wildcard:
                        pool_config = self._get_pool_config(pool_name)
                        if pool_config:
                            key = f"{database}.{table}"
                            allowed_cols = pool_config.get("allowed_columns", {}).get(key, [])
                            if allowed_cols and "*" not in allowed_cols:
                                return PermissionResult(
                                    allowed=False,
                                    level=PermissionLevel.COLUMN_LEVEL,
                                    message=f"表 {database}.{table} 不允许使用 SELECT *",
                                    denied_columns={key: ["* (需指定具体列)"]}
                                )
                    else:
                        allowed, denied = self._check_column_access(pool_name, database, table, columns)
                        if not allowed:
                            return PermissionResult(
                                allowed=False,
                                level=PermissionLevel.COLUMN_LEVEL,
                                message=f"无权访问以下列: {', '.join(denied)}",
                                denied_columns={f"{database}.{table}": denied}
                            )
                
                # 获取行过滤条件
                for database, table in tables:
                    row_filter = self._get_row_filter(pool_name, database, table)
                    if row_filter:
                        break
            
            return PermissionResult(
                allowed=True,
                level=PermissionLevel.FULL_ACCESS,
                message="权限检查通过",
                row_filter=row_filter,
                max_rows=self.max_rows
            )
            
        except Exception as e:
            logger.error(f"权限检查异常: {e}")
            return PermissionResult(
                allowed=False,
                level=PermissionLevel.DENIED,
                message=f"权限检查异常: {str(e)}"
            )
    
    def get_allowed_pools(self) -> List[str]:
        """获取当前用户允许访问的连接池列表"""
        return self.allowed_pools
    
    def get_allowed_databases(self, pool_name: str = None) -> List[str]:
        """获取当前用户允许访问的数据库列表"""
        if pool_name:
            pool_config = self._get_pool_config(pool_name)
            if pool_config:
                return pool_config.get("allowed_databases", [])
        return []
    
    def get_allowed_tables(self, pool_name: str = None, database: str = None) -> Dict[str, List[str]]:
        """获取当前用户允许访问的表"""
        if pool_name:
            pool_config = self._get_pool_config(pool_name)
            if pool_config:
                tables = pool_config.get("allowed_tables", {})
                if database:
                    return {database: tables.get(database, tables.get("*", []))}
                return tables
        return {}
    
    def get_pool_config(self, pool_name: str) -> Optional[Dict[str, Any]]:
        """获取指定连接池的权限配置"""
        return self._get_pool_config(pool_name)
