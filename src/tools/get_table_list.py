"""
获取表列表工具
根据连接池和数据库名称，返回当前用户有权限访问的表名称列表
"""

from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username
from connection.pool_manager import MultiDBPoolManager
from config.dbconfig import get_db_configs


class GetTableListTool(ToolsBase):
    """获取表列表工具类
    
    该工具根据连接池和数据库名称，返回当前用户有权限访问的表名称列表。
    只返回表名，不返回表结构（表结构由 get_table_desc 提供）。
    用户信息从请求头中的认证信息获取。
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
    
    name = "get_table_list"
    description = (
        "获取指定连接池和数据库下，当前用户有权限访问的表名称列表。"
        "根据 pool_name 和 database 参数返回表名列表（不含结构信息）。"
        "表结构信息请使用 get_table_desc 工具获取。"
        "Get table name list for specified pool and database (without structure info)."
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

    def _is_table_allowed(self, table: str, allowed_tables: list) -> bool:
        """检查表是否在允许列表中
        
        Args:
            table: 表名
            allowed_tables: 允许的表名列表
            
        Returns:
            True 如果表在允许列表中，或者列表为空/包含*（无限制）
        """
        if not allowed_tables:
            return True  # 无限制，允许所有表
        if "*" in allowed_tables:
            return True  # 通配符，允许所有表
        return table.lower() in [t.lower() for t in allowed_tables]

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
            
            # 如果权限不是 *，则检查数据库是否在允许列表中
            if "*" not in allowed_dbs and database not in allowed_dbs:
                return [TextContent(type="text", text=f"错误: 无权访问数据库 {database}。允许的数据库: {', '.join(allowed_dbs)}")]
            
            # 获取表权限 - 优先使用数据库特定的配置，否则使用通配符配置
            allowed_tables = pool_config.get("allowed_tables", {}).get(database, []) if pool_config else []
            if not allowed_tables:
                allowed_tables = pool_config.get("allowed_tables", {}).get("*", []) if pool_config else []
            
            try:
                pool_obj = MultiDBPoolManager.get_pool(pool_name)
                if not pool_obj:
                    return [TextContent(type="text", text=f"错误: 连接池 {pool_name} 不存在")]
                
                # 从配置获取数据库类型
                db_type = self._detect_db_type(pool_name)
                
                with pool_obj.connection() as conn:
                    from sqlalchemy import text
                    
                    # 获取表列表 - 根据数据库类型使用不同的查询
                    tables = []
                    try:
                        if db_type == 'mysql':
                            result = conn.execute(text(f"SHOW TABLES FROM `{database}`"))
                            tables = [row[0] for row in result]
                        elif db_type == 'postgresql':
                            result = conn.execute(text(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{database}'"))
                            tables = [row[0] for row in result]
                        elif db_type == 'dameng':
                            # Dameng: 达梦按模式获取表列表，使用 ALL_TABLES 并指定 OWNER
                            result = conn.execute(text(f"SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = '{database}' ORDER BY TABLE_NAME"))
                            tables = [row[0] for row in result]
                        elif db_type == 'oracle':
                            result = conn.execute(text(f"SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = '{database}' ORDER BY TABLE_NAME"))
                            tables = [row[0] for row in result]
                        elif db_type == 'mssqlserver':
                            result = conn.execute(text(f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '{database}'"))
                            tables = [row[0] for row in result]
                        else:
                            # 未知数据库类型，尝试通用的 USER_TABLES
                            try:
                                result = conn.execute(text("SELECT TABLE_NAME FROM USER_TABLES"))
                                tables = [row[0] for row in result]
                            except:
                                return [TextContent(type="text", text=f"错误: 不支持未知数据库类型 '{db_type}'")]
                    except Exception as e:
                        return [TextContent(type="text", text=f"获取表列表失败: {str(e)}")]
                    
                    # 权限过滤：只返回用户有权限访问的表
                    if allowed_tables and "*" not in allowed_tables:
                        tables = [t for t in tables if self._is_table_allowed(t, allowed_tables)]
                    
                    if not tables:
                        return [TextContent(type="text", text=f"连接池: {pool_name}, 数据库: {database} - 没有可访问的表")]
                    
                    # 返回简洁的表名列表
                    output = []
                    output.append(f"[{pool_name}] {database}")
                    for table in sorted(tables):
                        output.append(table)
                    
                    return [TextContent(type="text", text="\n".join(output))]
                    
            except Exception as e:
                return [TextContent(type="text", text=f"连接错误: {str(e)}")]
            
        except Exception as e:
            return [TextContent(type="text", text=f"获取表列表异常: {str(e)}")]
