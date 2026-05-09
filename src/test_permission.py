"""
权限功能测试脚本
测试表级别、列级别、行级别权限和审计日志功能
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from permission.permission_checker import PermissionChecker, PermissionLevel
from permission.audit_logger import AuditLogger, get_audit_logger, log_sql_execution

def test_permission_checker():
    """测试权限检查器"""
    print("=" * 60)
    print("测试 1: 权限检查器 - admin 用户（完全权限）")
    print("=" * 60)
    
    checker = PermissionChecker("admin")
    print(f"角色: {checker.role}")
    print(f"允许的数据库: {checker.allowed_databases}")
    print(f"允许的表: {checker.allowed_tables}")
    print(f"允许的列: {checker.allowed_columns}")
    print(f"SQL 操作: {checker.sql_operations}")
    
    # 测试 SQL 权限检查
    sql = "SELECT id, name FROM bitables.users"
    result = checker.check_sql_permission(sql)
    print(f"\nSQL: {sql}")
    print(f"结果: {'✅ 允许' if result.allowed else '❌ 拒绝'}")
    print(f"说明: {result.message}")
    
    print("\n" + "=" * 60)
    print("测试 2: 权限检查器 - analyst 用户（限制权限）")
    print("=" * 60)
    
    checker = PermissionChecker("analyst")
    print(f"角色: {checker.role}")
    print(f"允许的数据库: {checker.allowed_databases}")
    print(f"行过滤: {checker.row_filters}")
    
    # 测试表权限
    sql1 = "SELECT id, name FROM bitables.orders"
    result1 = checker.check_sql_permission(sql1)
    print(f"\nSQL: {sql1}")
    print(f"结果: {'✅ 允许' if result1.allowed else '❌ 拒绝'}")
    print(f"说明: {result1.message}")
    print(f"行过滤: {result1.row_filter}")
    
    # 测试无权限的表
    sql2 = "SELECT * FROM bitables.users"
    result2 = checker.check_sql_permission(sql2)
    print(f"\nSQL: {sql2}")
    print(f"结果: {'✅ 允许' if result2.allowed else '❌ 拒绝'}")
    print(f"说明: {result2.message}")
    
    print("\n" + "=" * 60)
    print("测试 3: 权限检查器 - developer 用户（列限制）")
    print("=" * 60)
    
    checker = PermissionChecker("developer")
    print(f"角色: {checker.role}")
    print(f"允许的列: {checker.allowed_columns}")
    
    # 测试列权限
    sql3 = "SELECT id, name, email FROM bitables.users"
    result3 = checker.check_sql_permission(sql3)
    print(f"\nSQL: {sql3}")
    print(f"结果: {'✅ 允许' if result3.allowed else '❌ 拒绝'}")
    print(f"说明: {result3.message}")
    
    # 测试无权限的列
    sql4 = "SELECT password FROM bitables.users"
    result4 = checker.check_sql_permission(sql4)
    print(f"\nSQL: {sql4}")
    print(f"结果: {'✅ 允许' if result4.allowed else '❌ 拒绝'}")
    print(f"说明: {result4.message}")
    if result4.denied_columns:
        print(f"被拒绝的列: {result4.denied_columns}")
    
    print("\n" + "=" * 60)
    print("测试 4: 审计日志记录")
    print("=" * 60)
    
    # 测试审计日志
    logger = get_audit_logger()
    logger.log_sql_execution(
        username="admin",
        sql="SELECT * FROM test_table",
        pool_name="default",
        success=True,
        result="查询成功",
        execution_time=100.5
    )
    
    logger.log_permission_denied(
        username="analyst",
        sql="SELECT * FROM secret_table",
        reason="无权访问该表",
        level="table_level"
    )
    
    print("✅ 审计日志记录成功")
    print(f"日志目录: {logger.log_dir}")
    print(f"保留天数: {logger.retention_days} 天")
    
    # 查询日志
    logs = logger.get_logs(limit=5)
    print(f"\n最近日志数量: {len(logs)}")
    for log in logs[-3:]:
        print(f"  - {log.get('timestamp')}: {log.get('action')} by {log.get('username')}")
    
    print("\n" + "=" * 60)
    print("测试 5: 验证不存在的用户")
    print("=" * 60)
    
    checker = PermissionChecker("nonexistent_user")
    result = checker.check_sql_permission("SELECT * FROM test")
    print(f"不存在的用户测试结果: {'✅ 允许' if result.allowed else '❌ 拒绝'}")
    print(f"说明: {result.message}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_permission_checker()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)