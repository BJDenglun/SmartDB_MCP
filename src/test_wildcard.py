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
            # 检测数据库类型
            def detect_db_type(pool_obj):
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
                return 'unknown'
            
            db_type = detect_db_type(pool_obj)
            print(f"数据库 URL: {getattr(pool_obj, 'database_url', 'N/A')}")
            print(f"检测到的数据库类型: {db_type}")
            
            with pool_obj.connection() as conn:
                from sqlalchemy import text
                actual_databases = []
                if db_type == 'mysql':
                    result = conn.execute(text("SHOW DATABASES"))
                    actual_databases = [row[0] for row in result if row[0] not in ('information_schema', 'mysql', 'performance_schema', 'sys')]
                    print(f"实际数据库: {actual_databases[:5]}... (共 {len(actual_databases)} 个)")
                elif db_type == 'dameng':
                    try:
                        result = conn.execute(text("SELECT NAME FROM V$DATABASE"))
                        actual_databases = [row[0] for row in result]
                        print(f"DM 数据库: {actual_databases}")
                    except Exception as e1:
                        print(f"V$DATABASE 失败: {e1}")
                        try:
                            result = conn.execute(text("SELECT DISTINCT OWNER FROM USER_TABLES"))
                            actual_databases = [row[0] for row in result]
                            print(f"用户表所有者: {actual_databases}")
                        except Exception as e2:
                            print(f"USER_TABLES 失败: {e2}")
                
                # 获取表信息
                print(f"\n获取表信息...")
                if db_type == 'dameng':
                    result = conn.execute(text("SELECT TABLE_NAME FROM USER_TABLES"))
                    tables = [row[0] for row in result]
                    print(f"表数量: {len(tables)}")
                    print(f"表列表: {tables[:10]}...")
                    
                    # 获取列信息
                    if tables:
                        table = tables[0]
                        result = conn.execute(text(f"SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, COMMENTS FROM USER_COL_TAB_COLUMNS WHERE TABLE_NAME='{table}' ORDER BY COLUMN_ID"))
                        columns = list(result)
                        print(f"\n表 '{table}' 的列:")
                        for col in columns[:5]:
                            print(f"  - {col[0]}: {col[1]}({col[2]}) {col[3] if col[3] else ''}")
    except Exception as e:
        import traceback
        print(f"获取失败: {e}")
        traceback.print_exc()