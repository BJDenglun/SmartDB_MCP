"""
获取所有数据库信息工具
根据当前用户的 role，返回有权限的 pool、数据库、表、字段和行权限信息
用于大模型生成 SQL，包含数据库类型、版本、表注释、字段注释等元数据
"""

from typing import Dict, Sequence, Any, List, Optional

from mcp.types import TextContent, Tool

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username
from connection.pool_manager import MultiDBPoolManager
from config.dbconfig import get_db_configs


class GetAllDatabaseInfoTool(ToolsBase):
    """获取所有数据库信息工具类

    该工具根据当前用户的角色，返回其有权限访问的所有数据库信息。
    包含池、数据库、表、字段、行过滤等权限信息，以及数据库类型、版本、表/字段注释等元数据。
    用于大模型生成 SQL 时获取完整的数据库上下文。
    """

    def _detect_db_type(self, pool_name: str) -> str:
        """检测数据库类型 - 从配置中获取"""
        try:
            db_configs = get_db_configs()
            if pool_name in db_configs:
                db_type = db_configs[pool_name].get("type", "unknown")
                return db_type.lower()
        except Exception:
            pass
        return 'unknown'

    name = "get_all_database_info"
    description = (
        "获取当前用户有权限访问的完整数据库信息工具。返回有权限的 pool、数据库、表、字段和行权限信息，"
        "包含数据库类型、版本、表注释、字段注释等元数据。用于大模型生成 SQL 时获取完整的数据库上下文。"
        "此工具返回的信息限制了 AI 的生成范围，只能在权限范围内生成 SQL，超出权限的 SQL 将在后台被拒绝。"
    )

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "pool_name": {
                        "type": "string",
                        "description": "连接池名称，若不指定则返回所有有权限池的信息"
                    }
                },
                "required": []
            }
        )

    def _is_table_allowed(self, table: str, allowed_tables: list) -> bool:
        """检查表是否在允许列表中"""
        if not allowed_tables:
            return True
        return table.lower() in [t.lower() for t in allowed_tables]

    def _filter_databases_by_permission(self, databases: list, pool_config: dict, db_type: str) -> list:
        """根据权限配置过滤数据库列表"""
        allowed_dbs = pool_config.get("allowed_databases", []) if pool_config else []
        if "*" in allowed_dbs:
            return databases
        return [db for db in databases if db in allowed_dbs or db.upper() in [d.upper() for d in allowed_dbs]]

    def _get_tables_list(self, conn, db_type: str, db: str) -> List[str]:
        """获取指定数据库/模式下的表列表 (参数化SQL)"""
        from sqlalchemy import text

        if db_type == 'mysql':
            # SHOW TABLES 使用标识符，db 来自数据库自身查询结果
            result = conn.execute(text(f"SHOW TABLES FROM `{db}`"))
            return [row[0] for row in result]
        elif db_type == 'postgresql':
            result = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :db"
            ), {"db": db})
            return [row[0] for row in result]
        elif db_type in ('dameng', 'oracle'):
            result = conn.execute(text(
                "SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = :db ORDER BY TABLE_NAME"
            ), {"db": db})
            return [row[0] for row in result]
        elif db_type == 'mssqlserver':
            result = conn.execute(text(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = :db"
            ), {"db": db})
            return [row[0] for row in result]
        return []

    def _get_table_comments_batch(self, conn, db_type: str, db: str, tables: List[str]) -> Dict[str, str]:
        """批量获取表注释 (一次查询)"""
        from sqlalchemy import text

        if not tables:
            return {}

        placeholders = ", ".join([f":t{i}" for i in range(len(tables))])
        params = {"db": db}
        for i, t in enumerate(tables):
            params[f"t{i}"] = t

        try:
            if db_type == 'mysql':
                result = conn.execute(text(
                    f"SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA = :db AND TABLE_NAME IN ({placeholders})"
                ), params)
                return {row[0]: (row[1] or "") for row in result}
            elif db_type in ('dameng', 'oracle'):
                result = conn.execute(text(
                    f"SELECT TABLE_NAME, COMMENTS FROM USER_TAB_COMMENTS WHERE TABLE_NAME IN ({placeholders})"
                ), params)
                return {row[0]: (row[1] or "") for row in result}
        except Exception:
            pass
        return {}

    def _get_columns_batch(self, conn, db_type: str, db: str, table: str) -> List[Dict[str, str]]:
        """获取单个表的列信息 (参数化SQL)"""
        from sqlalchemy import text

        try:
            if db_type == 'mysql':
                result = conn.execute(text(f"SHOW FULL COLUMNS FROM `{db}`.`{table}`"))
                return [{"name": row[0], "type": row[1], "comment": (row[8] if len(row) > 8 and row[8] else "")} for row in result]
            elif db_type == 'dameng':
                result = conn.execute(text(
                    "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :table ORDER BY COLUMN_ID"
                ), {"table": table})
                return [{"name": row[0], "type": f"{row[1]}({row[2]})" if row[2] else row[1]} for row in result]
            elif db_type == 'oracle':
                result = conn.execute(text(
                    "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, COMMENTS FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :table ORDER BY COLUMN_ID"
                ), {"table": table})
                return [{"name": row[0], "type": f"{row[1]}({row[2]})" if row[2] else row[1], "comment": (row[3] or "")} for row in result]
            elif db_type == 'postgresql':
                result = conn.execute(text(
                    "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_schema = :db AND table_name = :table ORDER BY ordinal_position"
                ), {"db": db, "table": table})
                return [{"name": row[0], "type": row[1], "nullable": row[2]} for row in result]
            elif db_type == 'mssqlserver':
                result = conn.execute(text(
                    "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE "
                    "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :table ORDER BY ORDINAL_POSITION"
                ), {"db": db, "table": table})
                return [{"name": row[0], "type": f"{row[1]}({row[2]})" if row[2] else row[1], "nullable": row[3]} for row in result]
        except Exception:
            pass
        return []

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            username = get_current_username()

            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]

            pool_name = arguments.get("pool_name")

            checker = PermissionChecker(username)

            output = []
            output.append("=" * 70)
            output.append(f"数据库信息报告 - 用户: {username}, 角色: {checker.role_name}")
            output.append("=" * 70)

            allowed_pools = checker.get_allowed_pools()
            server_pools = list(MultiDBPoolManager.get_pool_names())

            output.append("\n【可访问的连接池】")

            if pool_name:
                if "*" in allowed_pools or pool_name in allowed_pools:
                    pools_to_check = [pool_name]
                else:
                    pools_to_check = []
            elif "*" in allowed_pools:
                pools_to_check = server_pools
            else:
                pools_to_check = [p for p in allowed_pools if p in server_pools]

            if not pools_to_check:
                return [TextContent(type="text", text="错误: 无权访问指定的连接池")]

            from sqlalchemy import text

            for pool in pools_to_check:
                output.append(f"\n{'=' * 60}")
                output.append(f"连接池: {pool}")
                output.append(f"{'=' * 60}")

                pool_config = checker.get_pool_config(pool)
                allowed_databases = pool_config.get("allowed_databases", []) if pool_config else []
                db_type = self._detect_db_type(pool)

                actual_databases = []
                if "*" in allowed_databases:
                    try:
                        pool_obj = MultiDBPoolManager.get_pool(pool)
                        if pool_obj:
                            with pool_obj.connection() as conn:
                                if db_type == 'mysql':
                                    result = conn.execute(text("SHOW DATABASES"))
                                    actual_databases = [row[0] for row in result if row[0] not in ('information_schema', 'mysql', 'performance_schema', 'sys')]
                                elif db_type == 'postgresql':
                                    result = conn.execute(text("SELECT datname FROM pg_database WHERE datname NOT IN ('postgres', 'template0', 'template1')"))
                                    actual_databases = [row[0] for row in result]
                                elif db_type == 'dameng':
                                    try:
                                        result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES ORDER BY OWNER"))
                                        actual_databases = [row[0] for row in result]
                                    except Exception:
                                        actual_databases = []
                                    if not actual_databases:
                                        try:
                                            result = conn.execute(text("SELECT DISTINCT OWNER FROM USER_TABLES ORDER BY OWNER"))
                                            actual_databases = [row[0] for row in result]
                                        except Exception:
                                            pass
                                    if not actual_databases:
                                        try:
                                            result = conn.execute(text("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM DUAL"))
                                            schemas = [row[0] for row in result]
                                            actual_databases = schemas if schemas else ['SYSDBA']
                                        except Exception:
                                            actual_databases = ['SYSDBA']
                                elif db_type == 'oracle':
                                    result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES WHERE OWNER NOT IN ('SYS', 'SYSTEM', 'SYSAUX')"))
                                    actual_databases = [row[0] for row in result]
                                elif db_type == 'mssqlserver':
                                    result = conn.execute(text("SELECT name FROM sys.databases WHERE state_desc = 'ONLINE'"))
                                    actual_databases = [row[0] for row in result]
                            output.append("\n  【数据库/模式列表】(管理员权限-获取所有)")
                            output.append(f"  数量: {len(actual_databases)}")
                            if actual_databases:
                                output.append(f"  列表: {', '.join(actual_databases[:10])}{'...' if len(actual_databases) > 10 else ''}")
                    except Exception as e:
                        output.append(f"  获取数据库列表失败: {str(e)}")
                        actual_databases = []
                else:
                    output.append("\n  【数据库列表】")
                    output.append(f"  允许的数据库: {', '.join(allowed_databases)}")
                    actual_databases = allowed_databases

                if not actual_databases:
                    output.append("  (无数据库访问权限)")
                    continue

                allowed_tables = pool_config.get("allowed_tables", {}) if pool_config else {}
                allowed_columns = pool_config.get("allowed_columns", {}) if pool_config else {}
                row_filters = pool_config.get("row_filters", {}) if pool_config else {}

                if allowed_columns:
                    output.append("\n  【列权限】")
                    for key, cols in allowed_columns.items():
                        if cols and "*" not in cols:
                            output.append(f"    {key}: {', '.join(cols)}")

                if row_filters:
                    output.append("\n  【行过滤条件】")
                    for table_key, filter_cond in row_filters.items():
                        output.append(f"    {table_key}: {filter_cond}")

                output.append("\n  【表结构信息】(基于权限范围)")
                try:
                    pool_obj = MultiDBPoolManager.get_pool(pool)
                    if pool_obj:
                        with pool_obj.connection() as conn:
                            for db in actual_databases:
                                output.append(f"\n    --- 数据库: {db} ---")

                                try:
                                    tables = self._get_tables_list(conn, db_type, db)

                                    db_tables = allowed_tables.get(db, []) if allowed_tables else []
                                    if not db_tables:
                                        db_tables = allowed_tables.get("*", []) if allowed_tables else []

                                    if db_tables and "*" not in db_tables:
                                        tables = [t for t in tables if self._is_table_allowed(t, db_tables)]

                                    output.append(f"    可访问表 ({len(tables)}):")

                                    # 批量获取表注释 (N+1优化)
                                    tables_display = tables[:20]
                                    comments_map = self._get_table_comments_batch(conn, db_type, db, tables_display)

                                    for table in tables_display:
                                        table_comment = comments_map.get(table, "")
                                        comment_str = f" ({table_comment})" if table_comment else ""
                                        output.append(f"      - {table}{comment_str}")

                                        cols_allowed = allowed_columns.get(f"{db}.{table}", allowed_columns.get(f"*.{table}", []))
                                        show_all_cols = "*" in cols_allowed or not cols_allowed

                                        try:
                                            columns = self._get_columns_batch(conn, db_type, db, table)
                                            for col in columns:
                                                col_name = col["name"]
                                                if show_all_cols or col_name.lower() in [c.lower() for c in cols_allowed]:
                                                    col_type = col["type"]
                                                    if "comment" in col and col["comment"]:
                                                        output.append(f"        {col_name} ({col_type}) ({col['comment']})")
                                                    elif "nullable" in col:
                                                        null_str = "NULL" if col["nullable"] == "YES" else "NOT NULL"
                                                        output.append(f"        {col_name} ({col_type}) {null_str}")
                                                    else:
                                                        output.append(f"        {col_name} ({col_type})")
                                        except Exception:
                                            pass

                                        row_filter = row_filters.get(f"{db}.{table}", row_filters.get(f"*.{table}"))
                                        if row_filter:
                                            output.append(f"        [行过滤: {row_filter}]")

                                    if len(tables) > 20:
                                        output.append(f"        ... 还有 {len(tables) - 20} 个表")

                                except Exception as e:
                                    output.append(f"    获取表信息失败: {str(e)}")

                except Exception as e:
                    output.append(f"  连接池访问失败: {str(e)}")

            output.append("\n" + "=" * 70)
            output.append("【说明】")
            output.append("1. AI 生成的 SQL 必须在上述权限范围内")
            output.append("2. 超出权限的 SQL 将被拒绝执行")
            output.append("3. 行过滤条件会自动应用到查询中")
            output.append("4. 列权限限制不允许访问未授权的列")
            output.append("=" * 70)

            return [TextContent(type="text", text="\n".join(output))]

        except Exception as e:
            return [TextContent(type="text", text=f"获取数据库信息异常: {str(e)}")]