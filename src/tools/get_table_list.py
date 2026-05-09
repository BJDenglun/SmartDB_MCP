"""
获取表列表工具
根据 pool 和 database 名称，返回当前用户有权限的 table 名称和注释列表，以及表结构信息
"""

from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username
from connection.pool_manager import MultiDBPoolManager


class GetTableListTool(ToolsBase):
    """获取表列表工具类
    
    该工具根据连接池和数据库名称，返回当前用户有权限访问的表名称、注释和结构信息。
    用户信息从请求头中的认证信息获取。
    """
    
    name = "get_table_list"
    description = (
        "获取指定连接池和数据库下，当前用户有权限访问的表名称和注释列表，以及表结构信息。"
        "根据 pool_name 和 database 参数返回表列表。"
        "Get table list with comments for specified pool and database."
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
                        "description": "连接池名称"
                    },
                    "database": {
                        "type": "string",
                        "description": "数据库名称"
                    }
                },
                "required": ["pool_name", "database"]
            }
        )

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            # 从请求上下文获取当前用户
            username = get_current_username()
            
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            pool_name = arguments.get("pool_name")
            database = arguments.get("database")
            
            if not pool_name or not database:
                return [TextContent(type="text", text="错误: 缺少必需参数 pool_name 和 database")]
            
            # 创建权限检查器
            checker = PermissionChecker(username)
            
            # 检查池权限
            if not checker._check_pool_access(pool_name):
                return [TextContent(type="text", text=f"错误: 无权访问连接池 {pool_name}")]
            
            # 检查数据库权限
            pool_config = checker.get_pool_config(pool_name)
            allowed_dbs = pool_config.get("allowed_databases", []) if pool_config else []
            
            # 如果权限是 *，则允许访问任何数据库
            if "*" not in allowed_dbs and database not in allowed_dbs:
                return [TextContent(type="text", text=f"错误: 无权访问数据库 {database}。允许的数据库: {', '.join(allowed_dbs)}")]
            
            # 获取表权限
            allowed_tables = pool_config.get("allowed_tables", {}).get(database, []) if pool_config else []
            allowed_columns = pool_config.get("allowed_columns", {}) if pool_config else {}
            
            output = []
            output.append(f"=== 表列表 - 连接池: {pool_name}, 数据库: {database} ===")
            output.append(f"用户名: {username}")
            output.append("")
            
            try:
                pool_obj = MultiDBPoolManager.get_pool(pool_name)
                if not pool_obj:
                    return [TextContent(type="text", text=f"错误: 连接池 {pool_name} 不存在")]
                
                with pool_obj.connection() as conn:
                    from sqlalchemy import text
                    
                    # 获取数据库类型
                    db_type = 'unknown'
                    try:
                        result = conn.execute(text("SELECT 1"))
                        # 尝试检测数据库类型
                        if 'mysql' in str(pool_obj).lower():
                            db_type = 'mysql'
                        elif 'postgresql' in str(pool_obj).lower():
                            db_type = 'postgresql'
                        elif 'dameng' in str(pool_obj).lower():
                            db_type = 'dameng'
                        elif 'oracle' in str(pool_obj).lower():
                            db_type = 'oracle'
                    except:
                        pass
                    
                    # 获取表列表
                    tables = []
                    try:
                        if db_type == 'mysql' or 'mysql' in str(pool_obj).lower():
                            result = conn.execute(text(f"SHOW TABLES FROM `{database}`"))
                            tables = [row[0] for row in result]
                        elif 'postgresql' in str(pool_obj).lower():
                            result = conn.execute(text(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{database}'"))
                            tables = [row[0] for row in result]
                        elif 'dameng' in str(pool_obj).lower() or 'oracle' in str(pool_obj).lower():
                            result = conn.execute(text("SELECT TABLE_NAME FROM USER_TABLES"))
                            tables = [row[0] for row in result]
                    except Exception as e:
                        output.append(f"获取表列表失败: {str(e)}")
                        return [TextContent(type="text", text="\n".join(output))]
                    
                    # 过滤用户有权限的表
                    if "*" not in allowed_tables:
                        tables = [t for t in tables if t.lower() in [x.lower() for x in allowed_tables]]
                    
                    if not tables:
                        output.append("没有可访问的表")
                        return [TextContent(type="text", text="\n".join(output))]
                    
                    output.append(f"可访问的表 ({len(tables)}):")
                    output.append("")
                    
                    for table in tables:
                        # 获取表注释
                        table_comment = ""
                        try:
                            if 'mysql' in str(pool_obj).lower():
                                result = conn.execute(text(f"SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA='{database}' AND TABLE_NAME='{table}'"))
                                row = result.fetchone()
                                if row and row[0]:
                                    table_comment = f" - {row[0]}"
                            elif 'dameng' in str(pool_obj).lower() or 'oracle' in str(pool_obj).lower():
                                result = conn.execute(text(f"SELECT COMMENTS FROM USER_TAB_COMMENTS WHERE TABLE_NAME='{table}'"))
                                row = result.fetchone()
                                if row and row[0]:
                                    table_comment = f" - {row[0]}"
                        except:
                            pass
                        
                        output.append(f"📋 {table}{table_comment}")
                        
                        # 获取列信息
                        cols_allowed = allowed_columns.get(f"{database}.{table}", allowed_columns.get(f"*.{table}", []))
                        show_all_cols = "*" in cols_allowed or not cols_allowed
                        
                        try:
                            if 'mysql' in str(pool_obj).lower():
                                result = conn.execute(text(f"SHOW FULL COLUMNS FROM `{database}`.`{table}`"))
                                for row in result:
                                    col_name = row[0]
                                    col_type = row[1]
                                    col_null = "NULL" if row[3] == "YES" else "NOT NULL"
                                    col_key = row[4] if row[4] else ""
                                    col_comment = row[8] if len(row) > 8 and row[8] else ""
                                    
                                    if show_all_cols or col_name.lower() in [c.lower() for c in cols_allowed]:
                                        key_marker = f" [{col_key}]" if col_key else ""
                                        comment_str = f" ({col_comment})" if col_comment else ""
                                        output.append(f"   - {col_name} ({col_type}) {col_null}{key_marker}{comment_str}")
                            elif 'dameng' in str(pool_obj).lower() or 'oracle' in str(pool_obj).lower():
                                result = conn.execute(text(f"SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_DEFAULT, NULLABLE, COMMENTS FROM USER_COL_TAB_COLUMNS WHERE TABLE_NAME='{table}' ORDER BY COLUMN_ID"))
                                for row in result:
                                    col_name = row[0]
                                    col_type = f"{row[1]}({row[2]})" if row[2] else row[1]
                                    col_null = "NULL" if row[4] == 'Y' else "NOT NULL"
                                    col_comment = row[5] if row[5] else ""
                                    
                                    if show_all_cols or col_name.lower() in [c.lower() for c in cols_allowed]:
                                        comment_str = f" ({col_comment})" if col_comment else ""
                                        output.append(f"   - {col_name} ({col_type}) {col_null}{comment_str}")
                        except:
                            pass
                        
                        output.append("")
                    
                    # 显示行过滤信息
                    row_filters = pool_config.get("row_filters", {}) if pool_config else {}
                    if row_filters:
                        output.append("\n【行过滤条件】")
                        for table_key, filter_cond in row_filters.items():
                            if database in table_key:
                                output.append(f"  {table_key}: {filter_cond}")
                    
            except Exception as e:
                output.append(f"连接错误: {str(e)}")
            
            return [TextContent(type="text", text="\n".join(output))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"获取表列表异常: {str(e)}")]