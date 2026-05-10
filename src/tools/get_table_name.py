"""
关键词搜索表名工具
通过关键词搜索匹配数据库中符合条件的表名
"""

from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool
from sqlalchemy import text

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username
from connection.pool_manager import MultiDBPoolManager
from config.dbconfig import get_db_configs


class GetTableNameTool(ToolsBase):
    """关键词搜索表名工具类
    
    该工具通过关键词搜索数据库中匹配的表名。
    支持模糊匹配，帮助客户端快速找到相关的表。
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
    
    name = "get_table_name"
    description = (
        "通过关键词搜索数据库中的表名。输入关键词后返回所有匹配该关键词的表名列表。 "
        "支持模糊匹配，可用于快速查找相关的表。 "
        "Search table names by keyword using fuzzy matching."
    )

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，用于模糊匹配表名"
                    },
                    "pool_name": {
                        "type": "string",
                        "description": "连接池名称"
                    },
                    "database": {
                        "type": "string",
                        "description": "数据库名称"
                    }
                },
                "required": ["keyword"]
            }
        )

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            username = get_current_username()
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            keyword = arguments.get("keyword", "").strip()
            if not keyword:
                return [TextContent(type="text", text="错误: 关键词不能为空")]
            
            pool_name = arguments.get("pool_name", "default")
            database = arguments.get("database")
            
            checker = PermissionChecker(username)
            
            # 检查池权限
            if not checker._check_pool_access(pool_name):
                return [TextContent(type="text", text=f"错误: 无权访问连接池 {pool_name}")]
            
            # 检查数据库权限
            pool_config = checker.get_pool_config(pool_name)
            if database:
                allowed_dbs = pool_config.get("allowed_databases", []) if pool_config else []
                if "*" not in allowed_dbs and database not in allowed_dbs:
                    return [TextContent(type="text", text=f"错误: 无权访问数据库 {database}")]
            
            pool_obj = MultiDBPoolManager.get_pool(pool_name)
            if not pool_obj:
                return [TextContent(type="text", text=f"错误: 连接池 {pool_name} 不存在")]
            
            db_type = self._detect_db_type(pool_name)
            
            output = []
            output.append(f"搜索关键词: {keyword}")
            output.append("")
            
            with pool_obj.connection() as conn:
                tables = self._search_tables(conn, db_type, keyword, database)
                
                if tables:
                    output.append(f"找到 {len(tables)} 个匹配的表:")
                    for table in tables:
                        output.append(f"  - {table}")
                else:
                    output.append("未找到匹配的表")
            
            return [TextContent(type="text", text="\n".join(output))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"搜索表名异常: {str(e)}")]
    
    def _search_tables(self, conn, db_type: str, keyword: str, database: str = None) -> list:
        """根据数据库类型搜索表名"""
        try:
            # 达梦/Oracle 使用 LIKE 模糊匹配
            if db_type in ['dameng', 'oracle']:
                sql = f"""
                    SELECT TABLE_NAME 
                    FROM USER_TABLES 
                    WHERE TABLE_NAME LIKE '%{keyword}%'
                    ORDER BY TABLE_NAME
                """
            elif db_type == 'mysql':
                if database:
                    sql = f"""
                        SELECT TABLE_NAME 
                        FROM INFORMATION_SCHEMA.TABLES 
                        WHERE TABLE_SCHEMA = '{database}' 
                        AND TABLE_NAME LIKE '%{keyword}%'
                        AND TABLE_TYPE = 'BASE TABLE'
                        ORDER BY TABLE_NAME
                    """
                else:
                    sql = f"""
                        SELECT TABLE_NAME 
                        FROM INFORMATION_SCHEMA.TABLES 
                        WHERE TABLE_NAME LIKE '%{keyword}%'
                        AND TABLE_TYPE = 'BASE TABLE'
                        ORDER BY TABLE_NAME
                    """
            elif db_type == 'postgresql':
                sql = f"""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_name LIKE '%{keyword}%'
                    AND table_schema = 'public'
                    ORDER BY table_name
                """
            elif db_type == 'mssqlserver':
                sql = f"""
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME LIKE '%{keyword}%'
                    AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                """
            else:
                return []
            
            result = conn.execute(text(sql))
            return [row[0] for row in result]
        except Exception as e:
            return []
