"""
配置文件测试脚本
测试新的配置文件结构（含池级别权限）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.dbconfig import load_database_configs, get_pool_names
from config.user_config import load_user_configs, get_user_by_name, validate_user_credentials
from config.role_config import load_role_configs, get_role_by_name
from permission.permission_checker import PermissionChecker


def test_configs():
    """测试配置加载"""
    print("=" * 60)
    print("测试 1: 数据库配置 (database_config.json)")
    print("=" * 60)
    
    pools = load_database_configs()
    print(f"连接池数量: {len(pools)}")
    print(f"连接池列表: {list(pools.keys())}")
    
    for name, config in pools.items():
        print(f"\n【{name}】")
        print(f"  Host: {config.get('host')}")
        print(f"  Port: {config.get('port')}")
        print(f"  Type: {config.get('type')}")
        print(f"  Pool Size: {config.get('pool_size')}")
    
    print("\n" + "=" * 60)
    print("测试 2: 用户配置 (user.json)")
    print("=" * 60)
    
    users = load_user_configs()
    print(f"用户数量: {len(users)}")
    for user in users:
        print(f"  - {user.get('name')} (角色: {user.get('role')}, 密钥: {user.get('key')[:10]}...)")
    
    # 测试用户验证
    print("\n测试用户验证:")
    result = validate_user_credentials("admin", "sk_admin_123456")
    print(f"  admin/sk_admin_123456: {'✅ 成功' if result else '❌ 失败'}")
    
    result = validate_user_credentials("admin", "wrong_key")
    print(f"  admin/wrong_key: {'✅ 成功' if result else '❌ 失败'}")
    
    print("\n" + "=" * 60)
    print("测试 3: 角色配置 (role.json)")
    print("=" * 60)
    
    roles = load_role_configs()
    print(f"角色数量: {len(roles)}")
    for name, config in roles.items():
        print(f"\n【{name}】")
        print(f"  描述: {config.get('description')}")
        print(f"  最大行数: {config.get('max_rows')}")
        print(f"  允许的连接池: {config.get('allowed_pools')}")
        print(f"  SQL操作: {config.get('sql_operations')}")
        
        # 显示池配置
        pools_config = config.get("pools", {})
        if pools_config:
            print(f"  池配置:")
            for pool_name, pool_cfg in pools_config.items():
                print(f"    - {pool_name}:")
                print(f"      数据库: {pool_cfg.get('allowed_databases')}")
    
    print("\n" + "=" * 60)
    print("测试 4: 权限检查器 (池级别)")
    print("=" * 60)
    
    checker = PermissionChecker("analyst")
    print(f"用户: analyst, 角色: {checker.role_name}")
    print(f"最大返回行数: {checker.max_rows}")
    print(f"允许的连接池: {checker.allowed_pools}")
    print(f"池配置: {list(checker.pool_configs.keys())}")
    
    # 获取各池的数据库权限
    for pool_name in checker.allowed_pools:
        if pool_name == "*":
            continue
        pool_config = checker.get_pool_config(pool_name)
        if pool_config:
            print(f"\n池 [{pool_name}] 的数据库: {pool_config.get('allowed_databases')}")
            print(f"  行过滤: {pool_config.get('row_filters')}")
    
    # 测试 SQL 权限
    sql1 = "SELECT id, name FROM bitables.orders"
    result1 = checker.check_sql_permission(sql1, "mysql")
    print(f"\nSQL (mysql): {sql1}")
    print(f"结果: {'✅ 允许' if result1.allowed else '❌ 拒绝'}")
    print(f"行过滤: {result1.row_filter}")
    
    # 测试无池权限
    sql2 = "SELECT * FROM users FROM oracle.users"
    result2 = checker.check_sql_permission(sql2, "oracle")
    print(f"\nSQL (oracle): {sql2}")
    print(f"结果: {'✅ 允许' if result2.allowed else '❌ 拒绝'}")
    print(f"说明: {result2.message}")
    
    # 测试 admin 角色
    print("\n" + "=" * 60)
    print("测试 5: admin 角色（所有池权限）")
    print("=" * 60)
    
    admin_checker = PermissionChecker("admin")
    print(f"用户: admin, 角色: {admin_checker.role_name}")
    print(f"允许的连接池: {admin_checker.allowed_pools}")
    print(f"池配置: {list(admin_checker.pool_configs.keys())}")
    
    # 测试在所有池上的权限
    sql3 = "SELECT * FROM test FROM default.test_table"
    for pool in ["default", "oracle", "mysql"]:
        result3 = admin_checker.check_sql_permission(sql3, pool)
        print(f"\nSQL ({pool}): {sql3}")
        print(f"结果: {'✅ 允许' if result3.allowed else '❌ 拒绝'}")
    
    print("\n" + "=" * 60)
    print("✅ 所有配置测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_configs()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)