"""
获取连接池列表工具
用于获取当前用户有权限访问的连接池名称列表
不需要输入参数，使用连接认证的 username 和 api_key
"""

from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker
from permission.context import get_current_username
from connection.pool_manager import MultiDBPoolManager


class GetConnectionListTool(ToolsBase):
    """获取连接池列表工具类
    
    该工具用于获取当前用户有权限访问的连接池名称列表。
    不需要输入参数，用户信息从请求头中的认证信息获取。
    """
    
    name = "get_connection_list"
    description = (
        "获取当前用户有权限访问的连接池名称列表工具。不需要输入参数，"
        "自动根据请求头中的用户名获取其有权限访问的连接池。"
        "Get accessible connection pools list. No input required, returns pools based on user permissions."
    )

    def get_tool_description(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            # 从请求上下文获取当前用户
            username = get_current_username()
            
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            # 创建权限检查器
            checker = PermissionChecker(username)
            
            # 获取有权限的连接池
            allowed_pools = checker.get_allowed_pools()
            server_pools = list(MultiDBPoolManager.get_pool_names())
            
            output = []
            output.append("=== 用户可访问的连接池列表 ===")
            output.append(f"用户名: {username}")
            output.append(f"角色: {checker.role_name}")
            output.append("")
            
            # 确定可见的池
            if "*" in allowed_pools:
                # 管理员可以看到所有服务器上的池
                visible_pools = server_pools
            else:
                # 普通用户只看到配置中有权限且服务器上存在的池
                visible_pools = [p for p in allowed_pools if p in server_pools]
            
            if visible_pools:
                output.append(f"可访问的连接池 ({len(visible_pools)}):")
                for i, pool in enumerate(visible_pools, 1):
                    output.append(f"  {i}. {pool}")
                    # 显示该池的简要信息
                    pool_config = checker.get_pool_config(pool)
                    if pool_config:
                        dbs = pool_config.get("allowed_databases", [])
                        if dbs:
                            output.append(f"     数据库: {', '.join(dbs) if dbs else '无限制'}")
            else:
                output.append("❌ 没有可访问的连接池")
                if allowed_pools:
                    output.append(f"  配置的池: {', '.join(allowed_pools)}")
                    not_on_server = [p for p in allowed_pools if p not in server_pools]
                    if not_on_server:
                        output.append(f"  未连接到服务器: {', '.join(not_on_server)}")
            
            return [TextContent(type="text", text="\n".join(output))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"获取连接池列表异常: {str(e)}")]