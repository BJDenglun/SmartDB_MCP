import json
from sqlalchemy import create_engine, text

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

# 删除达梦老表
print('=== Deleting Dameng old tables ===')
try:
    from sqlalchemy import create_engine, text
    host = cfg['default']['host']
    port = cfg['default']['port']
    user = cfg['default']['user']
    password = cfg['default']['password']
    
    url = f"dm+dmPython://{user}:{password}@{host}:{port}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        # 获取所有表
        result = conn.execute(text("SELECT table_name FROM user_tables WHERE table_name LIKE 'S26_%' OR table_name LIKE 's26_%'"))
        tables = result.fetchall()
        print(f'Found {len(tables)} tables')
        
        for table in tables:
            table_name = table[0]
            try:
                conn.execute(text(f'DROP TABLE "{table_name}"'))
                print(f'Dropped {table_name}')
            except Exception as e:
                print(f'Failed to drop {table_name}: {e}')
        
        conn.commit()
        print(f'\nDeleted {len(tables)} tables')
        
except Exception as e:
    print(f'Dameng error: {e}')

print('\n=== Checking Oracle ===')
try:
    host = cfg['oracle']['host']
    port = cfg['oracle']['port']
    user = cfg['oracle']['user']
    password = cfg['oracle']['password']
    sid = cfg['oracle']['sid']
    
    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/{sid}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        result = conn.execute(text('SELECT * FROM v$instance'))
        instance = result.fetchone()
        print(f'Oracle connected! Instance: {instance[1]}')
        
        # 检查SC用户表
        result = conn.execute(text("SELECT COUNT(*) FROM user_tables WHERE table_name LIKE 'S26_%'"))
        count = result.fetchone()[0]
        print(f'SC user tables: {count}')
        
except Exception as e:
    print(f'Oracle error: {e}')

print('\n[Done]')
