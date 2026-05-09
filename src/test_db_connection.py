import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection.pool_manager import MultiDBPoolManager
from sqlalchemy import text

def test_connections():
    """测试数据库连接"""
    print("=" * 80)
    print("测试数据库连接")
    print("=" * 80)
    
    # 初始化连接池
    MultiDBPoolManager.init_from_config()
    print("\n连接池初始化完成")
    print(f"可用连接池: {list(MultiDBPoolManager.get_pool_names())}")
    
    # 测试每个连接池
    pools = ['mysql', 'oracle', 'default']
    
    for pool_name in pools:
        print(f"\n{'='*40}")
        print(f"测试 {pool_name} 连接")
        print(f"{'='*40}")
        
        try:
            pool = MultiDBPoolManager.get_pool(pool_name)
            if not pool:
                print(f"  [X] 连接池不存在")
                continue
                
            with pool.connection() as conn:
                # 执行简单查询
                result = conn.execute(text("SELECT 1 as test"))
                print(f"  [OK] 查询测试通过")
                
                # 根据数据库类型执行不同查询
                if pool_name == 'mysql':
                    result = conn.execute(text("SHOW DATABASES"))
                    dbs = [row[0] for row in result.fetchall()]
                    print(f"  [OK] 数据库列表: {dbs[:5]}...")
                    
                    # 选择 bitables 数据库
                    result = conn.execute(text("SHOW TABLES FROM bitables"))
                    tables = [row[0] for row in result.fetchall()]
                    print(f"  [OK] bitables 表数量: {len(tables)}")
                    if tables:
                        print(f"  [OK] 前5个表: {tables[:5]}")
                        
                elif pool_name == 'oracle':
                    result = conn.execute(text("SELECT * FROM v$version WHERE ROWNUM = 1"))
                    version = result.fetchone()
                    print(f"  [OK] Oracle版本: {version[0] if version else 'N/A'}")
                    
                elif pool_name == 'default':
                    result = conn.execute(text("SELECT * FROM V$INSTANCE"))
                    instance = result.fetchone()
                    print(f"  [OK] Dameng实例: {instance}")
                    
        except Exception as e:
            print(f"  [X] 错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_connections()