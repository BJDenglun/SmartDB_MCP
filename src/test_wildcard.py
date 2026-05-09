"""测试通配符权限返回数据库信息"""
import sys
sys.path.insert(0, 'src')

from permission.permission_checker import PermissionChecker
from connection.pool_manager import MultiDBPoolManager

# 初始化连接池
MultiDBPoolManager.init_from_config()
print("池列表:", list(MultiDBPoolManager.get_pool_names()))

# 创建 admin 用户的权限检查器
checker = PermissionChecker("admin")
print(f"\n用户角色: {checker.role_name}")
print(f"允许的池: {checker.allowed_pools}")

# 获取池配置
pool_config = checker.get_pool_config("default")
print(f"\n池配置: {pool_config}")
print(f"允许的数据库: {pool_config.get('allowed_databases', [])}")

# 测试：如果权限是 *，尝试获取实际数据库列表
if "*" in pool_config.get("allowed_databases", []):
    print("\n权限是 *，尝试获取实际数据库...")
    try:
        pool_obj = MultiDBPoolManager.get_pool("default")
        if pool_obj:
            # 打印池对象的详细信息
            print(f"池对象类型: {type(pool_obj)}")
            print(f"池对象: {pool_obj}")
            
            # 尝试检测数据库类型
            pool_str = str(pool_obj).lower()
            print(f"池字符串: {pool_str}")
            
            # 根据字符串判断
            if 'mysql' in pool_str:
                db_type = 'mysql'
            elif 'postgresql' in pool_str or 'postgres' in pool_str:
                db_type = 'postgresql'
            elif 'dameng' in pool_str or 'dm' in pool_str:
                db_type = 'dameng'
            elif 'oracle' in pool_str:
                db_type = 'oracle'
            else:
                # 尝试从连接获取数据库类型
                db_type = 'unknown'
                try:
                    with pool_obj.connection() as conn:
                        # 尝试执行一个简单的查询来检测类型
                        result = conn.execute("SELECT 1")
                        # 检查 dialect
                        dialect_name = str(conn.dialect).lower()
                        print(f"Dialect: {dialect_name}")
                        if 'mysql' in dialect_name:
                            db_type = 'mysql'
                        elif 'postgresql' in dialect_name or 'postgres' in dialect_name:
                            db_type = 'postgresql'
                        elif 'oracle' in dialect_name:
                            db_type = 'oracle'
                        elif 'dm' in dialect_name:
                            db_type = 'dameng'
                except Exception as e:
                    print(f"检测异常: {e}")
            
            print(f"检测到的数据库类型: {db_type}")
            
            with pool_obj.connection() as conn:
                from sqlalchemy import text
                if db_type == 'mysql':
                    result = conn.execute(text("SHOW DATABASES"))
                    actual_dbs = [row[0] for row in result if row[0] not in ('information_schema', 'mysql', 'performance_schema', 'sys')]
                    print(f"实际数据库: {actual_dbs[:5]}... (共 {len(actual_dbs)} 个)")
                elif db_type == 'dameng':
                    try:
                        result = conn.execute(text("SELECT NAME FROM V$DATABASE"))
                        actual_dbs = [row[0] for row in result]
                        print(f"DM 数据库: {actual_dbs}")
                    except Exception as e1:
                        print(f"V$DATABASE 失败: {e1}")
                        try:
                            result = conn.execute(text("SELECT DISTINCT OWNER FROM USER_TABLES"))
                            actual_dbs = [row[0] for row in result]
                            print(f"用户表所有者: {actual_dbs}")
                        except Exception as e2:
                            print(f"USER_TABLES 失败: {e2}")
    except Exception as e:
        print(f"获取失败: {e}")