"""
SQL执行工具类，使用数据库连接池执行SQL语句
"""

import logging
import re
from enum import Enum
from typing import List, Tuple, Optional, Dict, Any, Set
from dataclasses import dataclass
from contextlib import contextmanager

from pymysql import MySQLError
from sqlalchemy import text

from connection.pool_manager import MultiDBPoolManager
from core.exceptions import SQLPermissionError

logger = logging.getLogger(__name__)


class SQLOperation(str, Enum):
    """SQL 操作类型枚举"""
    SELECT = 'SELECT'
    INSERT = 'INSERT'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    CREATE = 'CREATE'
    ALTER = 'ALTER'
    DROP = 'DROP'
    TRUNCATE = 'TRUNCATE'
    SHOW = 'SHOW'
    DESCRIBE = 'DESCRIBE'
    EXPLAIN = 'EXPLAIN'

    @classmethod
    def from_str(cls, value: str) -> 'SQLOperation':
        try:
            return cls(value.upper())
        except ValueError:
            raise ValueError(f"不支持的SQL操作类型: {value}")


@dataclass
class SQLResult:
    success: bool
    message: str
    columns: Optional[List[str]] = None
    rows: Optional[List[Tuple]] = None
    affected_rows: int = 0


class ExecuteSqlUtil:
    """使用数据库连接池的SQL执行工具类"""

    # SQL注释正则模式（单行和多行注释）
    SQL_COMMENT_PATTERN = re.compile(r'--.*$|/\*.*?\*/', re.MULTILINE | re.DOTALL)

    # 危险 SQL 模式检测：
    # 1. 分号后跟非空白字符（多语句）
    # 2. 以分号结尾（可能的注释注入终止符）
    # 3. 孤立的单行注释标记（-- 后无内容但可能被用于注入）
    DANGEROUS_MULTI_STATEMENT_PATTERN = re.compile(r';\s*\S|;$')

    # 注释注入检测 - 注释符号后面跟着 SQL 关键字
    COMMENT_INJECTION_PATTERN = re.compile(r'/\*.*?\*/\s*(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)', re.IGNORECASE | re.DOTALL)

    # 检测孤立的 SQL 注释标记（可能被用来终止合法 SQL 然后注入）
    TRAILING_COMMENT_PATTERN = re.compile(r';\s*--\s*$|;\s*/\*\s*$')

    # 检测块注释（安全加固：阻止可能被用于注入的注释模式）
    BLOCK_COMMENT_PATTERN = re.compile(r'/\*.*?\*/', re.DOTALL)

    # 布尔注入检测 - 检测 'OR' 或 'AND' 后跟永真条件
    # 模式: ' OR ...=... 或 ' AND ...=... (引号开头, OR/AND, 空格, 表达式=表达式)
    BOOLEAN_INJECTION_PATTERN = re.compile(r"'\s+(OR|AND)\s+", re.IGNORECASE)

    @classmethod
    def validate_sql_structure(cls, sql: str) -> Tuple[bool, str]:
        """验证 SQL 语句结构安全性

        Returns:
            (是否安全, 错误消息)
        """
        if not sql or not sql.strip():
            return False, "SQL语句为空"

        # 检查原始 SQL 中是否有危险的分号模式（注释注入）
        # 防止 "SELECT * FROM users;--" 这类注入
        if cls.TRAILING_COMMENT_PATTERN.search(sql):
            return False, "禁止使用注释注入"

        # 检查是否包含多语句（分号后跟非空白字符）
        sql_no_comments = cls.SQL_COMMENT_PATTERN.sub('', sql)
        if cls.DANGEROUS_MULTI_STATEMENT_PATTERN.search(sql_no_comments):
            return False, "禁止执行多条SQL语句"

        # 检查注释注入模式
        if cls.COMMENT_INJECTION_PATTERN.search(sql_no_comments):
            return False, "检测到潜在的注释注入"

        # 检查块注释（可能被用于注入）
        if cls.BLOCK_COMMENT_PATTERN.search(sql):
            return False, "禁止使用块注释"

        # 检查布尔注入（如 ' OR '1'='1', ' AND 1=1）
        if cls.BOOLEAN_INJECTION_PATTERN.search(sql):
            return False, "检测到潜在的布尔注入"

        # 检查不完整的字符串字面量（可能表示注入）
        quote_count = sql_no_comments.count("'")
        if quote_count % 2 != 0:
            return False, "SQL语句包含未闭合的单引号"

        return True, ""

    @classmethod
    def clean_sql(cls, sql: str) -> str:
        """清理SQL语句，移除注释和多余空白"""
        sql = cls.SQL_COMMENT_PATTERN.sub('', sql)
        return ' '.join(sql.split())

    @classmethod
    def sanitize_sql_input(cls, sql: str) -> str:
        """对 SQL 输入进行安全清理，防止注入"""
        if not sql:
            return sql
        sql = cls.SQL_COMMENT_PATTERN.sub('', sql)
        sql = ' '.join(sql.split())
        return sql

    @classmethod
    def execute_single_statement(cls, pool_name: str, statement, params: Dict[str, Any] = None) -> SQLResult:
        """执行单条SQL语句"""
        if isinstance(statement, tuple):
            statement, params = statement

        try:
            pool = MultiDBPoolManager.get_pool(pool_name)

            with pool.connection() as conn:
                cleaned_statement = cls.clean_sql(statement)
                upper_statement = cleaned_statement.upper().strip()

                is_select = upper_statement.startswith('SELECT') or upper_statement.startswith('WITH')
                is_show = upper_statement.startswith('SHOW')
                is_explain = upper_statement.startswith('EXPLAIN') and not upper_statement.startswith('EXPLAIN PLAN FOR ')
                is_describe = upper_statement.startswith('DESCRIBE') or upper_statement.startswith('DESC ')

                is_query_type = is_select or is_show or is_explain or is_describe

                try:
                    result = conn.execute(text(statement), params or {})

                    if is_query_type:
                        columns = list(result.keys())
                        rows = result.fetchall()
                        return SQLResult(
                            success=True,
                            message="查询执行成功",
                            columns=columns,
                            rows=rows
                        )
                    else:
                        conn.commit()
                        return SQLResult(
                            success=True,
                            message="执行成功",
                            affected_rows=result.rowcount
                        )
                except Exception as e:
                    if not is_query_type:
                        conn.rollback()
                    raise

        except MySQLError as e:
            logger.error(f"SQL执行错误: {e}, SQL: {statement}")
            return SQLResult(success=False, message=f"执行失败: {str(e)}")
        except Exception as e:
            logger.error(f"未知错误: {e}, SQL: {statement}")
            return SQLResult(success=False, message=f"执行失败: {str(e)}")

    @classmethod
    def execute_multiple_statements(cls, pool_name: str, query: str) -> List[SQLResult]:
        """执行多条SQL语句（仅在验证通过后执行单条）"""
        # 验证 SQL 结构安全性
        is_safe, error_msg = cls.validate_sql_structure(query)
        if not is_safe:
            return [SQLResult(success=False, message=f"SQL安全检查失败: {error_msg}")]

        # 只取第一条语句，忽略分号后的内容
        statements = [stmt.strip() for stmt in query.split(';') if stmt.strip()]
        if not statements:
            return [SQLResult(success=False, message="没有可执行的SQL语句")]

        # 只执行第一条语句（安全措施）
        results = []
        try:
            result = cls.execute_single_statement(pool_name, statements[0])
            results.append(result)
        except Exception as e:
            logger.warning(f"SQL执行警告: {e}, SQL: {statements[0]}")
            results.append(SQLResult(success=False, message=f"执行失败: {str(e)}"))

        return results

    @classmethod
    def format_result(cls, result: SQLResult) -> str:
        if not result.success:
            return result.message

        if result.columns and result.rows:
            formatted_rows = [
                ",".join("NULL" if v is None else str(v) for v in row)
                for row in result.rows
            ]
            return "\n".join([",".join(result.columns)] + formatted_rows)
        else:
            return f"{result.message}。影响行数: {result.affected_rows}"

    @staticmethod
    def extract_operations(sql: str) -> Set[SQLOperation]:
        sql = ExecuteSqlUtil.clean_sql(sql.upper())
        return {
            op for op in SQLOperation
            if re.search(rf'\b{op.value}\b', sql)
        }