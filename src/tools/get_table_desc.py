from typing import Dict, Sequence, Any, List

from mcp.types import TextContent, Tool
from sqlalchemy import text

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username
from config.dbconfig import get_db_configs


class GetTableDesc(ToolsBase):
    """数据库表结构查询工具类

    该类用于查询指定数据库表的结构信息，包括列名、列注释等详细信息。
    继承自ToolsBase基类，实现了获取工具描述和执行工具的核心方法。
    包含权限检查，确保用户只能查询有权限访问的表结构。
    """

    name = "get_table_desc"
    description = (
        "数据库表结构查询工具。仅在用户明确要求查看一个或多个具体数据表的详细结构信息（包括列名、列注释等）时使用此工具。"
        "注意：此工具不应用于查询数据库中的所有表名，如需查询所有表名，请使用其他专门工具。"
        "Database table structure query tool. Use this tool only when the user explicitly requests to view the detailed "
        "structure information of one or more specific data tables (including column names, column comments, etc.)"
        "Note: This tool should not be used to query all table names in the database. To query all table names, please use other dedicated tools."
    )

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "tables": {
                        "type": "string",
                        "description": "要查询结构的具体表名，支持多个表名，用逗号分隔。注意：请确保表名准确无误"
                    },
                    "pool_name": {
                        "type": "string",
                        "description": "数据库连接池名称，默认为default"
                    },
                    "database": {
                        "type": "string",
                        "description": "数据库名称,若无指定默认为default"
                    },
                    "schema": {
                        "type": "string",
                        "description": "数据库模式名称,若无指定默认为default"
                    }
                },
                "required": ["tables"]
            }
        )

    def _is_table_allowed(self, table: str, allowed_tables: list) -> bool:
        if not allowed_tables:
            return True
        if "*" in allowed_tables:
            return True
        return table.lower() in [t.lower() for t in allowed_tables]

    def _detect_db_type(self, pool_name: str) -> str:
        try:
            db_configs = get_db_configs()
            if pool_name in db_configs:
                db_type = db_configs[pool_name].get("type", "unknown")
                return db_type.lower()
        except Exception:
            pass
        return 'unknown'

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            if "tables" not in arguments:
                raise ValueError("缺少查询语句")

            text = arguments["tables"]
            pool_name = arguments.get("pool_name","default")
            database = arguments.get("database","default")
            database = database if database != "default" else None
            schema = arguments.get("schema","default")
            schema = schema if schema != "default" else None

            username = get_current_username()
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]

            checker = PermissionChecker(username)

            if not checker._check_pool_access(pool_name):
                return [TextContent(type="text", text=f"错误: 无权访问连接池 {pool_name}")]

            if database and not checker._check_database_access(pool_name, database):
                return [TextContent(type="text", text=f"错误: 无权访问数据库 {database}")]

            pool_config = checker.get_pool_config(pool_name)

            if pool_config:
                tables_config = pool_config.get("allowed_tables", {})
                allowed_tables = tables_config.get(database if database else "default", []) if database else []
                if not allowed_tables:
                    allowed_tables = tables_config.get("*", [])
            else:
                allowed_tables = []

            table_names = [name.strip() for name in text.split(',')]
            denied_tables = []
            for table in table_names:
                if not self._is_table_allowed(table, allowed_tables):
                    denied_tables.append(table)

            if denied_tables:
                return [TextContent(type="text", text=f"错误: 无权访问以下表: {', '.join(denied_tables)}。可用表请先通过 get_table_list 获取")]

            db_type = self._detect_db_type(pool_name)

            from connection.pool_manager import MultiDBPoolManager

            pool_obj = MultiDBPoolManager.get_pool(pool_name)
            if not pool_obj:
                return [TextContent(type="text", text=f"错误: 连接池 {pool_name} 不存在")]

            outputs = []

            with pool_obj.connection() as conn:
                for table_name in table_names:
                    table_info = self._get_table_structure(conn, db_type, table_name, database)
                    if table_info:
                        outputs.append(table_info)

            if not outputs:
                return [TextContent(type="text", text="未找到表结构信息")]

            return [TextContent(type="text", text="\n\n".join(outputs))]

        except Exception as e:
            return [TextContent(type="text", text=f"执行查询时出错: {str(e)}")]

    def _get_table_structure(self, conn, db_type: str, table_name: str, database: str) -> str:
        try:
            columns = self._get_columns(conn, db_type, table_name)
            primary_keys = self._get_primary_keys(conn, db_type, table_name)
            foreign_keys = self._get_foreign_keys(conn, db_type, table_name)
            table_comment = self._get_table_comment(conn, db_type, table_name)

            lines = []
            lines.append(f"## TABLE: {table_name}")
            if table_comment:
                lines.append(f"**Comment:** {table_comment}")
            lines.append("")

            if columns:
                lines.append("### Columns")
                lines.append("| Column | Type | Nullable | Default | Comment |")
                lines.append("|--------|------|----------|---------|---------|")
                for col in columns:
                    nullable = "NOT NULL" if col['nullable'] == 'N' else "NULL"
                    default = col.get('default', '-') if col.get('default') else "-"
                    comment = col.get('comment', '-') if col.get('comment') else "-"
                    lines.append(f"| {col['name']} | {col['type']} | {nullable} | {default} | {comment} |")
                lines.append("")
            else:
                lines.append("### Columns: 无列信息")
                lines.append("")

            if primary_keys:
                lines.append("### Primary Key")
                lines.append(f"`PK: {', '.join(primary_keys)}`")
                lines.append("")
            else:
                lines.append("### Primary Key: 无主键")
                lines.append("")

            if foreign_keys:
                lines.append("### Foreign Keys")
                for fk in foreign_keys:
                    lines.append(f"`FK: {fk['column']} -> {fk['ref_table']}({fk['ref_column']})`")
                lines.append("")
            else:
                lines.append("### Foreign Keys: 无外键")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            return f"## TABLE: {table_name}\nError: {str(e)}"

    def _get_columns(self, conn, db_type: str, table_name: str) -> List[Dict]:
        columns = []
        try:
            if db_type == 'dameng':
                sql = """
                    SELECT
                        A.COLUMN_NAME,
                        A.DATA_TYPE,
                        A.DATA_LENGTH,
                        A.DATA_PRECISION,
                        A.DATA_SCALE,
                        A.NULLABLE,
                        COALESCE(A.DATA_DEFAULT, '') AS DATA_DEFAULT,
                        COALESCE(B.COMMENTS, '') AS COMMENTS
                    FROM USER_TAB_COLUMNS A
                    LEFT JOIN USER_COL_COMMENTS B
                        ON A.TABLE_NAME = B.TABLE_NAME
                        AND A.COLUMN_NAME = B.COLUMN_NAME
                    WHERE A.TABLE_NAME = :table_name
                    ORDER BY A.COLUMN_ID
                """
            elif db_type == 'oracle':
                sql = """
                    SELECT
                        A.COLUMN_NAME,
                        A.DATA_TYPE,
                        A.DATA_LENGTH,
                        A.DATA_PRECISION,
                        A.DATA_SCALE,
                        A.NULLABLE,
                        NVL(TO_CHAR(A.DATA_DEFAULT), '') AS DATA_DEFAULT,
                        NVL(B.COMMENTS, '') AS COMMENTS
                    FROM USER_TAB_COLUMNS A
                    LEFT JOIN USER_COL_COMMENTS B
                        ON A.TABLE_NAME = B.TABLE_NAME
                        AND A.COLUMN_NAME = B.COLUMN_NAME
                    WHERE A.TABLE_NAME = :table_name
                    ORDER BY A.COLUMN_ID
                """
            elif db_type == 'mysql':
                sql = """
                    SELECT
                        COLUMN_NAME,
                        DATA_TYPE,
                        CHARACTER_MAXIMUM_LENGTH,
                        NUMERIC_PRECISION,
                        NUMERIC_SCALE,
                        IS_NULLABLE,
                        IFNULL(COLUMN_DEFAULT, '') AS COLUMN_DEFAULT,
                        IFNULL(COLUMN_COMMENT, '') AS COLUMN_COMMENT
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = :table_name
                    ORDER BY ORDINAL_POSITION
                """
            elif db_type == 'postgresql':
                sql = """
                    SELECT
                        column_name,
                        data_type,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale,
                        is_nullable,
                        COALESCE(column_default::text, '') AS column_default,
                        '' AS col_comment
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                    ORDER BY ordinal_position
                """
            elif db_type == 'mssqlserver':
                sql = """
                    SELECT
                        COLUMN_NAME,
                        DATA_TYPE,
                        CHARACTER_MAXIMUM_LENGTH,
                        NUMERIC_PRECISION,
                        NUMERIC_SCALE,
                        IS_NULLABLE,
                        ISNULL(COLUMN_DEFAULT, '') AS COLUMN_DEFAULT,
                        '' AS COLUMN_COMMENT
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = :table_name
                    ORDER BY ORDINAL_POSITION
                """
            else:
                return []

            result = conn.execute(text(sql), {"table_name": table_name})
            for row in result:
                col = {
                    'name': row[0] if row[0] else '',
                    'type': self._format_data_type(row, db_type),
                    'nullable': 'Y' if (db_type in ['mysql', 'postgresql', 'mssqlserver'] and row[5] == 'YES') or (db_type in ['dameng', 'oracle'] and row[5] == 'Y') else 'N',
                    'default': str(row[6]) if len(row) > 6 and row[6] else '',
                    'comment': str(row[7]) if len(row) > 7 and row[7] else ''
                }
                columns.append(col)
        except Exception as e:
            pass
        return columns

    def _format_data_type(self, row, db_type: str) -> str:
        data_type = row[1] if row[1] else ''
        max_length = row[2] if len(row) > 2 and row[2] else None
        precision = row[3] if len(row) > 3 and row[3] else None
        scale = row[4] if len(row) > 4 and row[4] else None

        if max_length and max_length > 0:
            return f"{data_type}({max_length})"
        elif precision is not None and scale is not None:
            return f"{data_type}({precision},{scale})"
        elif precision is not None:
            return f"{data_type}({precision})"
        return data_type

    def _get_primary_keys(self, conn, db_type: str, table_name: str) -> List[str]:
        try:
            if db_type in ['dameng', 'oracle']:
                sql = """
                    SELECT B.COLUMN_NAME
                    FROM USER_CONSTRAINTS A
                    JOIN USER_CONS_COLUMNS B ON A.CONSTRAINT_NAME = B.CONSTRAINT_NAME
                    WHERE A.CONSTRAINT_TYPE = 'P'
                    AND A.TABLE_NAME = :table_name
                    ORDER BY B.POSITION
                """
            elif db_type == 'mysql':
                sql = """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_NAME = :table_name
                    AND CONSTRAINT_NAME = 'PRIMARY'
                    ORDER BY ORDINAL_POSITION
                """
            elif db_type == 'postgresql':
                sql = """
                    SELECT a.attname as column_name
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    JOIN pg_class c ON c.oid = i.indrelid
                    WHERE i.indisprimary AND c.relname = :table_name
                """
            elif db_type == 'mssqlserver':
                sql = """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_NAME = :table_name
                    AND CONSTRAINT_NAME LIKE 'PK%'
                """
            else:
                return []

            result = conn.execute(text(sql), {"table_name": table_name})
            return [row[0] for row in result]
        except Exception:
            return []

    def _get_foreign_keys(self, conn, db_type: str, table_name: str) -> List[Dict]:
        try:
            if db_type in ['dameng', 'oracle']:
                sql = """
                    SELECT
                        B.COLUMN_NAME,
                        C.TABLE_NAME AS REF_TABLE,
                        D.COLUMN_NAME AS REF_COLUMN
                    FROM USER_CONSTRAINTS A
                    JOIN USER_CONS_COLUMNS B ON A.CONSTRAINT_NAME = B.CONSTRAINT_NAME
                    JOIN USER_CONSTRAINTS C ON A.R_CONSTRAINT_NAME = C.CONSTRAINT_NAME
                    JOIN USER_CONS_COLUMNS D ON C.CONSTRAINT_NAME = D.CONSTRAINT_NAME AND B.POSITION = D.POSITION
                    WHERE A.CONSTRAINT_TYPE = 'R'
                    AND A.TABLE_NAME = :table_name
                """
            elif db_type == 'mysql':
                sql = """
                    SELECT
                        COLUMN_NAME,
                        REFERENCED_TABLE_NAME,
                        REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_NAME = :table_name
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """
            elif db_type == 'postgresql':
                sql = """
                    SELECT
                        a.attname as column_name,
                        c.relname as ref_table,
                        ad.attname as ref_column
                    FROM pg_constraint con
                    JOIN pg_class c ON c.oid = con.confrelid
                    JOIN pg_attribute ad ON ad.attrelid = con.confrelid AND ad.attnum = ANY(con.confkey)
                    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
                    WHERE con.contype = 'f' AND c.relname = :table_name
                """
            elif db_type == 'mssqlserver':
                sql = """
                    SELECT
                        fkc.COLUMN_NAME,
                        rc.TABLE_NAME AS REF_TABLE,
                        rc.COLUMN_NAME AS REF_COLUMN
                    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fkc
                        ON rc.CONSTRAINT_NAME = fkc.CONSTRAINT_NAME
                    WHERE fkc.TABLE_NAME = :table_name
                """
            else:
                return []

            result = conn.execute(text(sql), {"table_name": table_name})
            fks = []
            for row in result:
                fks.append({
                    'column': row[0],
                    'ref_table': row[1],
                    'ref_column': row[2]
                })
            return fks
        except Exception:
            return []

    def _get_table_comment(self, conn, db_type: str, table_name: str) -> str:
        try:
            if db_type in ['dameng', 'oracle']:
                sql = "SELECT COMMENTS FROM USER_TAB_COMMENTS WHERE TABLE_NAME = :table_name AND TABLE_TYPE = 'TABLE'"
            elif db_type == 'mysql':
                sql = "SELECT IFNULL(TABLE_COMMENT, '') FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = :table_name AND TABLE_TYPE = 'BASE TABLE'"
            elif db_type == 'postgresql':
                sql = "SELECT COALESCE(obj_description(relfilenode, 'pg_class'), '') FROM pg_class WHERE relname = :table_name"
            elif db_type == 'mssqlserver':
                sql = """
                    SELECT ISNULL(ep.value, '')
                    FROM sys.tables t
                    LEFT JOIN sys.extended_properties ep ON ep.major_id = t.object_id AND ep.minor_id = 0
                    WHERE t.name = :table_name
                """
            else:
                return ''

            result = conn.execute(text(sql), {"table_name": table_name})
            row = result.fetchone()
            if row and row[0]:
                return str(row[0])
        except Exception:
            pass
        return ''