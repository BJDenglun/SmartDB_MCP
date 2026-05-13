"""
获取数据库列表工具
用于查询用户可访问的数据库列表
"""

from typing import Dict, Sequence, Any

from mcp.types import TextContent, Tool

from tools.base import ToolsBase
from permission.permission_checker import PermissionChecker, PermissionLevel
from permission.context import get_current_username, get_current_user
from connection.pool_manager import MultiDBPoolManager
from config.dbconfig import get_db_configs


class GetDatabaseListTool(ToolsBase):
    """获取数据库列表工具类
    
    该工具用于获取当前用户有权访问的数据库列表。
    用户信息从请求头中自动获取，无需手动传入。
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
    
    name = "get_database_list"
    description = (
        "获取当前用户可访问的数据库列表工具。根据请求头中的用户信息获取其允许访问的数据库和连接池。 "
        "管理员可以看到所有连接池，非管理员用户只能看到配置中允许的数据库。"
        "Get user accessible database list tool. Returns databases based on current user from request header."
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
                        "description": "连接池名称，默认 'default'"
                    }
                },
                "required": []
            }
        )

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            # 从请求上下文获取当前用户
            username = get_current_username()
            
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            pool_name = arguments.get("pool_name", "default")
            
            # 创建权限检查器
            checker = PermissionChecker(username)
            
            # 获取允许的连接池列表
            allowed_pools = checker.get_allowed_pools()
            
            output = []
            output.append("=== 用户可访问的连接池和数据库 ===")
            output.append(f"用户名: {username}")
            output.append(f"角色: {checker.role_name}")
            output.append("")
            
            # 获取服务器上实际的连接池
            try:
                server_pools = list(MultiDBPoolManager.get_pool_names())
            except Exception:
                server_pools = []
            
            # 如果指定了特定池名，只处理该池
            if pool_name and pool_name != "*":
                # 检查用户是否有权限访问该池
                if "*" not in allowed_pools and pool_name not in allowed_pools:
                    return [TextContent(type="text", text=f"错误: 无权访问连接池 '{pool_name}'")]
                
                # 检查池是否在服务器上存在
                if pool_name not in server_pools:
                    return [TextContent(type="text", text=f"错误: 连接池 '{pool_name}' 不存在")]
                
                output.append(f"=== 连接池: {pool_name} ===")
                output.append(f"用户名: {username}")
                output.append(f"角色: {checker.role_name}")
                output.append("")
                
                # 只获取指定池的数据库列表
                pool_config = checker.get_pool_config(pool_name)
                if pool_config:
                    dbs = pool_config.get("allowed_databases", [])
                    if "*" in dbs:
                        # 权限是 *，获取实际的数据库列表
                        try:
                            pool_obj = MultiDBPoolManager.get_pool(pool_name)
                            if pool_obj:
                                with pool_obj.connection() as conn:
                                    from sqlalchemy import text
                                    db_type = self._detect_db_type(pool_name)
                                    output.append("数据库列表:")
                                    if db_type == 'mysql':
                                        result = conn.execute(text("SHOW DATABASES"))
                                        actual_dbs = [row[0] for row in result if row[0] not in ('information_schema', 'mysql', 'performance_schema', 'sys')]
                                        for db in actual_dbs:
                                            output.append(f"  - {db}")
                                    elif db_type == 'postgresql':
                                        result = conn.execute(text("SELECT datname FROM pg_database WHERE datname NOT IN ('postgres', 'template0', 'template1')"))
                                        actual_dbs = [row[0] for row in result]
                                        for db in actual_dbs:
                                            output.append(f"  - {db}")
                                    elif db_type == 'dameng':
                                        try:
                                            result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES ORDER BY OWNER"))
                                            actual_dbs = [row[0] for row in result]
                                        except Exception:
                                            actual_dbs = []
                                        if not actual_dbs:
                                            try:
                                                result = conn.execute(text("SELECT DISTINCT OWNER FROM USER_TABLES ORDER BY OWNER"))
                                                actual_dbs = [row[0] for row in result]
                                            except Exception:
                                                pass
                                        if not actual_dbs:
                                            try:
                                                result = conn.execute(text("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM DUAL"))
                                                actual_dbs = [row[0] for row in result]
                                            except Exception:
                                                actual_dbs = ['SYSDBA']
                                        for db in actual_dbs:
                                            output.append(f"  - {db}")
                                    elif db_type == 'oracle':
                                        result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES WHERE OWNER NOT IN ('SYS', 'SYSTEM', 'SYSAUX') ORDER BY OWNER"))
                                        actual_dbs = [row[0] for row in result]
                                        for db in actual_dbs:
                                            output.append(f"  - {db}")
                                    elif db_type == 'mssqlserver':
                                        result = conn.execute(text("SELECT name FROM sys.databases WHERE state_desc = 'ONLINE'"))
                                        actual_dbs = [row[0] for row in result]
                                        for db in actual_dbs:
                                            output.append(f"  - {db}")
                                    else:
                                        output.append("  (未知数据库类型)")
                        except Exception as e:
                            output.append(f"  (获取数据库列表失败: {str(e)})")
                    else:
                        output.append("允许的数据库:")
                        for db in dbs:
                            output.append(f"  - {db}")
            elif "*" in allowed_pools:
                # 没有指定池名且用户有 * 权限，返回所有池
                output.append("✅ 管理员权限: 可访问所有连接池")
                output.append(f"\n可用连接池 ({len(server_pools)}):")
                for p in server_pools:
                    output.append(f"  📦 {p}")
                    # 获取该池的数据库权限
                    pool_config = checker.get_pool_config(p)
                    if pool_config:
                        dbs = pool_config.get("allowed_databases", [])
                        tables = pool_config.get("allowed_tables", {})
                        # 如果权限是 *，尝试获取实际的数据库列表
                        if "*" in dbs:
                            try:
                                pool_obj = MultiDBPoolManager.get_pool(p)
                                if pool_obj:
                                    with pool_obj.connection() as conn:
                                        from sqlalchemy import text
                                        db_type = self._detect_db_type(p)
                                        if db_type == 'mysql':
                                            result = conn.execute(text("SHOW DATABASES"))
                                            actual_dbs = [row[0] for row in result if row[0] not in ('information_schema', 'mysql', 'performance_schema', 'sys')]
                                            output.append(f"     数据库列表:")
                                            for db in actual_dbs:
                                                output.append(f"       - {db}")
                                        elif db_type == 'postgresql':
                                            result = conn.execute(text("SELECT datname FROM pg_database WHERE datname NOT IN ('postgres', 'template0', 'template1')"))
                                            actual_dbs = [row[0] for row in result]
                                            output.append(f"     数据库列表:")
                                            for db in actual_dbs:
                                                output.append(f"       - {db}")
                                        elif db_type == 'dameng':
                                            try:
                                                result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES ORDER BY OWNER"))
                                                actual_dbs = [row[0] for row in result]
                                            except Exception:
                                                actual_dbs = []
                                            if not actual_dbs:
                                                try:
                                                    result = conn.execute(text("SELECT DISTINCT OWNER FROM USER_TABLES ORDER BY OWNER"))
                                                    actual_dbs = [row[0] for row in result]
                                                except Exception:
                                                    pass
                                            if not actual_dbs:
                                                try:
                                                    result = conn.execute(text("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM DUAL"))
                                                    actual_dbs = [row[0] for row in result]
                                                except Exception:
                                                    actual_dbs = ['SYSDBA']
                                            output.append(f"     数据库列表:")
                                            for db in actual_dbs:
                                                output.append(f"       - {db}")
                                        elif db_type == 'oracle':
                                            result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES WHERE OWNER NOT IN ('SYS', 'SYSTEM', 'SYSAUX') ORDER BY OWNER"))
                                            actual_dbs = [row[0] for row in result]
                                            output.append(f"     数据库列表:")
                                            for db in actual_dbs:
                                                output.append(f"       - {db}")
                                        elif db_type == 'mssqlserver':
                                            result = conn.execute(text("SELECT name FROM sys.databases WHERE state_desc = 'ONLINE'"))
                                            actual_dbs = [row[0] for row in result]
                                            output.append(f"     数据库列表:")
                                            for db in actual_dbs:
                                                output.append(f"       - {db}")
                                        else:
                                            output.append(f"     数据库: * (未知数据库类型)")
                                    continue
                            except Exception as e:
                                output.append(f"     数据库: * (获取列表失败: {str(e)})")
                                continue
                        output.append(f"     数据库: {', '.join(dbs) if dbs else '无限制'}")
                        # 只显示配置的表
                        if tables and "*" not in tables.get("*", []):
                            table_info = []
                            for db, tabs in tables.items():
                                if db != "*" and tabs:
                                    table_info.append(f"{db}: {', '.join(tabs[:10])}{'...' if len(tabs) > 10 else ''}")
                            if table_info:
                                output.append(f"     配置的表: {', '.join(table_info)}")
            else:
                # 非管理员用户
                output.append(f"允许访问的连接池 ({len(allowed_pools)}):")
                for p in allowed_pools:
                    # 检查该池是否在服务器上存在
                    if p not in server_pools:
                        output.append(f"  ⚠️ {p} (配置存在但服务器未连接)")
                        continue
                    
                    output.append(f"  📦 {p}")
                    # 获取该池的数据库权限
                    pool_config = checker.get_pool_config(p)
                    if pool_config:
                        dbs = pool_config.get("allowed_databases", [])
                        tables = pool_config.get("allowed_tables", {})
                        columns = pool_config.get("allowed_columns", {})
                        row_filters = pool_config.get("row_filters", {})
                        
                        if dbs:
                            output.append(f"     数据库: {', '.join(dbs)}")
                        else:
                            output.append(f"     数据库: 无")
                        
                        # 显示配置的表（排除通配符）
                        if tables:
                            table_info = []
                            for db, tabs in tables.items():
                                if db != "*" and tabs and "*" not in tabs:
                                    table_info.append(f"{db}: {', '.join(tabs[:5])}{'...' if len(tabs) > 5 else ''}")
                            if table_info:
                                output.append(f"     表: {', '.join(table_info)}")
                        
                        # 显示行过滤
                        if row_filters:
                            filter_info = [f"{k}={v}" for k, v in row_filters.items()]
                            output.append(f"     行过滤: {', '.join(filter_info)}")
            
            return [TextContent(type="text", text="\n".join(output))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"获取数据库列表异常: {str(e)}")]
