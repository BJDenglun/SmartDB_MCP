"""
SQL 权限检查工具
用于预检查 SQL 语句的权限，避免执行时被拒绝
"""

from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username


class CheckSQLPermissionTool(ToolsBase):
    """SQL 权限预检查工具类
    
    该工具用于在执行 SQL 之前检查当前用户是否有权限执行该 SQL 语句。
    支持数据库、表、列级别的权限检查。
    用户信息从请求头中自动获取，无需手动传入。
    """
    
    name = "check_sql_permission"
    description = (
        "SQL 权限预检查工具。在执行 SQL 之前使用此工具检查当前用户是否有权限执行该 SQL。"
        "可以检查数据库、表、列级别的访问权限。"
        "如果返回 denied=true，表示无权执行该 SQL。"
        "SQL permission checking tool. Use this tool to check if the current user has permission to execute the SQL statement before execution."
    )

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要检查权限的 SQL 语句"
                    },
                    "pool_name": {
                        "type": "string",
                        "description": "连接池名称，默认 'default'"
                    }
                },
                "required": ["sql"]
            }
        )

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            if "sql" not in arguments:
                return [TextContent(type="text", text="错误: 缺少 sql 参数")]
            
            # 从请求上下文获取当前用户
            username = get_current_username()
            
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            sql = arguments["sql"]
            pool_name = arguments.get("pool_name", "default")
            
            # 创建权限检查器
            checker = PermissionChecker(username)
            
            # 执行权限检查
            result = checker.check_sql_permission(sql, pool_name)
            
            # 格式化结果
            output = []
            output.append(f"=== SQL 权限检查结果 ===")
            output.append(f"用户名: {username}")
            output.append(f"角色: {checker.role_name}")
            output.append(f"SQL: {sql}")
            output.append(f"")
            output.append(f"检查结果: {'✅ 允许' if result.allowed else '❌ 拒绝'}")
            output.append(f"权限级别: {result.level.value if hasattr(result.level, 'value') else result.level}")
            output.append(f"说明: {result.message}")
            
            if result.denied_tables:
                output.append(f"被拒绝的表: {', '.join(result.denied_tables)}")
            
            if result.denied_columns:
                for table, cols in result.denied_columns.items():
                    output.append(f"表 {table} 被拒绝的列: {', '.join(cols)}")
            
            return [TextContent(type="text", text="\n".join(output))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"权限检查异常: {str(e)}")]