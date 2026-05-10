from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool

from databases.database_factory import DatabaseOperationFactory
from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username


class GetTableDesc(ToolsBase):
    """数据库表结构查询工具类
    
    该类用于查询指定数据库表的结构信息，包括列名、列注释等详细信息。
    继承自ToolsBase基类，实现了获取工具描述和执行工具的核心方法。
    包含权限检查，确保用户只能查询有权限访问的表结构。
    """
    
    # 工具名称
    name = "get_table_desc"
    # 工具描述，包含中英文说明和使用注意事项
    description = (
        "数据库表结构查询工具。仅在用户明确要求查看一个或多个具体数据表的详细结构信息（包括列名、列注释等）时使用此工具。"
        "注意：此工具不应用于查询数据库中的所有表名，如需查询所有表名，请使用其他专门工具。"
        "Database table structure query tool. Use this tool only when the user explicitly requests to view the detailed "
        "structure information of one or more specific data tables (including column names, column comments, etc.)"
        "Note: This tool should not be used to query all table names in the database. To query all table names, please use other dedicated tools."
    )

    def get_tool_description(self) -> Tool:
        """获取工具的详细描述信息
        
        返回一个Tool对象，包含工具名称、描述和输入参数模式。
        该描述用于MCP服务识别和调用工具。
        
        Returns:
            Tool: 包含工具描述信息的对象
        """
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
        """检查表是否在允许列表中
        
        Args:
            table: 表名
            allowed_tables: 允许的表名列表
            
        Returns:
            True 如果表在允许列表中，或者列表为空（无限制）
        """
        if not allowed_tables:
            return True  # 无限制，允许所有表
        return table.lower() in [t.lower() for t in allowed_tables]

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """执行表结构查询工具
        
        根据传入的参数查询指定表的结构信息。
        
        Args:
            arguments: 包含执行参数的字典
                - tables (str): 要查询结构的表名，支持多个表名用逗号分隔
                - pool_name (str, optional): 数据库连接池名称，默认为"default"
                - database (str, optional): 数据库名称，默认为"default"
                - schema (str, optional): 数据库模式名称，默认为"default"

        Returns:
            Sequence[TextContent]: 包含查询结果的文本内容序列
            
        Raises:
            ValueError: 当缺少必需的tables参数时抛出
            Exception: 当执行查询过程中出现其他错误时抛出
        """

        try:
            # 检查参数中是否包含必需的tables字段
            if "tables" not in arguments:
                raise ValueError("缺少查询语句")

            # 获取要查询的表名
            text = arguments["tables"]

            # 获取连接池名称，默认为"default"
            pool_name = arguments.get("pool_name","default")

            # 获取数据库名称，默认为"default"
            database = arguments.get("database","default")
            # 如果数据库名称为"default"，则设置为None
            database = database if database != "default" else None

            # 获取数据库模式名称，默认为"default"
            schema = arguments.get("schema","default")
            # 如果模式名称为"default"，则设置为None
            schema = schema if schema != "default" else None
            
            # ========== 权限检查 ==========
            username = get_current_username()
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            checker = PermissionChecker(username)
            
            # 检查池权限
            if not checker._check_pool_access(pool_name):
                return [TextContent(type="text", text=f"错误: 无权访问连接池 {pool_name}")]
            
            # 检查数据库权限
            if database and not checker._check_database_access(pool_name, database):
                return [TextContent(type="text", text=f"错误: 无权访问数据库 {database}")]
            
            # 获取表权限配置 - 与 get_table_list 一致的逻辑
            pool_config = checker.get_pool_config(pool_name)
            
            # 优先使用数据库特定的配置，否则使用通配符配置
            if pool_config:
                tables_config = pool_config.get("allowed_tables", {})
                # 尝试数据库特定的配置
                allowed_tables = tables_config.get(database if database else "default", []) if database else []
                # 如果没有，使用通配符配置
                if not allowed_tables:
                    allowed_tables = tables_config.get("*", [])
            else:
                allowed_tables = []
            
            # 检查每个请求的表是否有权限
            table_names = [name.strip() for name in text.split(',')]
            denied_tables = []
            for table in table_names:
                if not self._is_table_allowed(table, allowed_tables):
                    denied_tables.append(table)
            
            if denied_tables:
                return [TextContent(type="text", text=f"错误: 无权访问以下表: {', '.join(denied_tables)}。可用表请先通过 get_table_list 获取")]
            # ========== 权限检查结束 ==========

            # 根据连接池名称获取对应的数据库工厂实例
            factory = DatabaseOperationFactory.get_factory_by_pool_name(pool_name)

            # 创建表结构查询处理器实例
            handler = factory.create_table_description()

            # 执行表结构查询操作
            sql_result = handler.get_table_description(pool_name,database,schema,text)

            # 将查询结果转换为文本内容并返回
            return [TextContent(type="text", text=sql_result)]

        # 捕获执行过程中的异常并返回错误信息
        except Exception as e:
            return [TextContent(type="text", text=f"执行查询时出错: {str(e)}")]
