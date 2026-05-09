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


class GetAllDatabaseInfoTool(ToolsBase):
    """获取所有数据库信息工具类
    
    该工具根据当前用户的角色，返回其有权限访问的所有数据库信息。
    包含池、数据库、表、字段、行过滤等权限信息，以及数据库类型、版本、表/字段注释等元数据。
    用于大模型生成 SQL 时获取完整的数据库上下文。
    """
    
    def _detect_db_type(self, pool_obj) -> str:
        """检测数据库类型"""
        # 先尝试从 database_url 中获取类型
        if hasattr(pool_obj, 'database_url'):
            url = pool_obj.database_url.lower()
            if 'mysql' in url:
                return 'mysql'
            elif 'postgresql' in url or 'postgres' in url:
                return 'postgresql'
            elif 'oracle' in url:
                return 'oracle'
            elif 'dm' in url or 'dameng' in url:
                return 'dameng'
        # 备用：从对象字符串检测
        pool_str = str(pool_obj).lower()
        if 'mysql' in pool_str:
            return 'mysql'
        elif 'postgresql' in pool_str or 'postgres' in pool_str:
            return 'postgresql'
        elif 'dameng' in pool_str or 'dm' in pool_str:
            return 'dameng'
        elif 'oracle' in pool_str:
            return 'oracle'
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

    async def run_tool(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        try:
            # 从请求上下文获取当前用户
            username = get_current_username()
            
            if not username or username == "anonymous":
                return [TextContent(type="text", text="错误: 未提供用户认证信息。请在请求头中设置 X-Username 和 X-API-Key")]
            
            pool_name = arguments.get("pool_name")
            
            # 创建权限检查器
            checker = PermissionChecker(username)
            
            output = []
            output.append("=" * 70)
            output.append(f"数据库信息报告 - 用户: {username}, 角色: {checker.role_name}")
            output.append("=" * 70)
            
            # 获取有权限的连接池
            allowed_pools = checker.get_allowed_pools()
            server_pools = list(MultiDBPoolManager.get_pool_names())
            
            output.append(f"\n【可访问的连接池】")
            
            # 确定要处理的池
            if pool_name:
                # 如果指定了池名，检查是否有权限（* 可匹配任何池）
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
            
            for pool in pools_to_check:
                output.append(f"\n{'=' * 60}")
                output.append(f"连接池: {pool}")
                output.append(f"{'=' * 60}")
                
                # 获取池配置
                pool_config = checker.get_pool_config(pool)
                
                # 获取数据库信息
                allowed_databases = pool_config.get("allowed_databases", []) if pool_config else []
                
                # 如果权限是 *，则从数据库获取实际数据库列表
                actual_databases = []
                if "*" in allowed_databases:
                    try:
                        pool_obj = MultiDBPoolManager.get_pool(pool)
                        if pool_obj:
                            with pool_obj.connection() as conn:
                                from sqlalchemy import text
                                # 根据数据库类型获取数据库列表
                                db_type = self._detect_db_type(pool_obj)
                                if db_type == 'mysql':
                                    result = conn.execute(text("SHOW DATABASES"))
                                    actual_databases = [row[0] for row in result if row[0] not in ('information_schema', 'mysql', 'performance_schema', 'sys')]
                                elif db_type == 'postgresql':
                                    result = conn.execute(text("SELECT datname FROM pg_database WHERE datname NOT IN ('postgres', 'template0', 'template1')"))
                                    actual_databases = [row[0] for row in result]
                                elif db_type == 'dameng':
                                    # Dameng: 获取当前用户可访问的所有模式/所有者
                                    # 方案1: 从 ALL_TABLES 获取当前用户有权限访问的所有模式
                                    try:
                                        result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES ORDER BY OWNER"))
                                        actual_databases = [row[0] for row in result]
                                    except Exception as e1:
                                        actual_databases = []
                                    if not actual_databases:
                                        # 方案2: 从 USER_TABLES 获取当前模式的表
                                        try:
                                            result = conn.execute(text("SELECT DISTINCT OWNER FROM USER_TABLES ORDER BY OWNER"))
                                            actual_databases = [row[0] for row in result]
                                        except:
                                            pass
                                    if not actual_databases:
                                        # 方案3: 获取当前会话的模式
                                        try:
                                            result = conn.execute(text("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM DUAL"))
                                            schemas = [row[0] for row in result]
                                            actual_databases = schemas if schemas else ['SYSDBA']
                                        except:
                                            actual_databases = ['SYSDBA']
                                elif db_type == 'oracle':
                                    result = conn.execute(text("SELECT DISTINCT OWNER FROM ALL_TABLES WHERE OWNER NOT IN ('SYS', 'SYSTEM', 'SYSAUX')"))
                                    actual_databases = [row[0] for row in result]
                                else:
                                    actual_databases = []
                            output.append(f"\n  【数据库/模式列表】(管理员权限-获取所有)")
                            output.append(f"  数量: {len(actual_databases)}")
                            if actual_databases:
                                output.append(f"  列表: {', '.join(actual_databases[:10])}{'...' if len(actual_databases) > 10 else ''}")
                    except Exception as e:
                        output.append(f"  获取数据库列表失败: {str(e)}")
                        actual_databases = []
                else:
                    output.append(f"\n  【数据库列表】")
                    output.append(f"  允许的数据库: {', '.join(allowed_databases)}")
                    actual_databases = allowed_databases
                
                if not actual_databases:
                    output.append("  (无数据库访问权限)")
                    continue
                
                # 获取表权限
                allowed_tables = pool_config.get("allowed_tables", {}) if pool_config else {}
                allowed_columns = pool_config.get("allowed_columns", {}) if pool_config else {}
                row_filters = pool_config.get("row_filters", {}) if pool_config else {}
                
                # 获取列信息
                columns_info = []
                if allowed_columns:
                    output.append(f"\n  【列权限】")
                    for key, cols in allowed_columns.items():
                        if cols and "*" not in cols:
                            output.append(f"    {key}: {', '.join(cols)}")
                
                # 获取行过滤
                if row_filters:
                    output.append(f"\n  【行过滤条件】")
                    for table_key, filter_cond in row_filters.items():
                        output.append(f"    {table_key}: {filter_cond}")
                
                # 尝试获取实际的表信息
                output.append(f"\n  【表结构信息】(基于权限范围)")
                try:
                    pool_obj = MultiDBPoolManager.get_pool(pool)
                    if pool_obj:
                        with pool_obj.connection() as conn:
                            from sqlalchemy import text
                            
                            # 根据数据库类型获取表列表
                            db_type = self._detect_db_type(pool_obj)
                            
                            for db in actual_databases:
                                    
                                output.append(f"\n    --- 数据库: {db} ---")
                                
                                try:
                                    # 获取表列表
                                    if db_type == 'mysql':
                                        result = conn.execute(text(f"SHOW TABLES FROM `{db}`"))
                                        tables = [row[0] for row in result]
                                    elif db_type == 'postgresql':
                                        result = conn.execute(text(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db}'"))
                                        tables = [row[0] for row in result]
                                    elif db_type == 'dameng':
                                        result = conn.execute(text(f"SELECT TABLE_NAME FROM USER_TABLES"))
                                        tables = [row[0] for row in result]
                                    elif db_type == 'oracle':
                                        result = conn.execute(text(f"SELECT TABLE_NAME FROM USER_TABLES"))
                                        tables = [row[0] for row in result]
                                    else:
                                        tables = []
                                    
                                    # 过滤用户有权限的表
                                    db_tables = allowed_tables.get(db, allowed_tables.get("*", []))
                                    if "*" not in db_tables:
                                        tables = [t for t in tables if t.lower() in [x.lower() for x in db_tables]]
                                    
                                    output.append(f"    可访问表 ({len(tables)}):")
                                    for table in tables[:20]:  # 限制显示数量
                                        # 尝试获取表注释
                                        table_comment = ""
                                        try:
                                            if db_type == 'mysql':
                                                result = conn.execute(text(f"SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA='{db}' AND TABLE_NAME='{table}'"))
                                                row = result.fetchone()
                                                if row and row[0]:
                                                    table_comment = f" ({row[0]})"
                                            elif db_type in ['dameng', 'oracle']:
                                                result = conn.execute(text(f"SELECT COMMENTS FROM USER_TAB_COMMENTS WHERE TABLE_NAME='{table}'"))
                                                row = result.fetchone()
                                                if row and row[0]:
                                                    table_comment = f" ({row[0]})"
                                        except:
                                            pass
                                        
                                        output.append(f"      - {table}{table_comment}")
                                        
                                        # 获取列信息
                                        cols_allowed = allowed_columns.get(f"{db}.{table}", allowed_columns.get(f"*.{table}", []))
                                        show_all_cols = "*" in cols_allowed or not cols_allowed
                                        
                                        try:
                                            if db_type == 'mysql':
                                                result = conn.execute(text(f"SHOW FULL COLUMNS FROM `{db}`.`{table}`"))
                                                for row in result:
                                                    col_name = row[0]
                                                    col_type = row[1]
                                                    col_comment = row[8] if len(row) > 8 else ""
                                                    if show_all_cols or col_name.lower() in [c.lower() for c in cols_allowed]:
                                                        comment_str = f" ({col_comment})" if col_comment else ""
                                                        output.append(f"        {col_name} ({col_type}){comment_str}")
                                            elif db_type == 'dameng':
                                                result = conn.execute(text(f"SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH FROM USER_TAB_COLUMNS WHERE TABLE_NAME='{table}' ORDER BY COLUMN_ID"))
                                                for row in result:
                                                    col_name = row[0]
                                                    col_type = f"{row[1]}({row[2]})" if row[2] else row[1]
                                                    col_comment = ""
                                                    if show_all_cols or col_name.lower() in [c.lower() for c in cols_allowed]:
                                                        comment_str = f" ({col_comment})" if col_comment else ""
                                                        output.append(f"        {col_name} ({col_type}){comment_str}")
                                            elif db_type == 'oracle':
                                                result = conn.execute(text(f"SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, COMMENTS FROM USER_TAB_COLUMNS WHERE TABLE_NAME='{table}' ORDER BY COLUMN_ID"))
                                                for row in result:
                                                    col_name = row[0]
                                                    col_type = f"{row[1]}({row[2]})" if row[2] else row[1]
                                                    col_comment = row[3] if row[3] else ""
                                                    if show_all_cols or col_name.lower() in [c.lower() for c in cols_allowed]:
                                                        comment_str = f" ({col_comment})" if col_comment else ""
                                                        output.append(f"        {col_name} ({col_type}){comment_str}")
                                        except:
                                            pass
                                            
                                        # 检查行过滤
                                        row_filter = row_filters.get(f"{db}.{table}")
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