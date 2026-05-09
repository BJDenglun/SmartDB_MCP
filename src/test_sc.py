import json
from sqlalchemy import create_engine, text

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

print('=== Checking Oracle SC User ===')
try:
    host = cfg['oracle']['host']
    port = cfg['oracle']['port']
    user = cfg['oracle']['user']
    password = cfg['oracle']['password']
    sid = cfg['oracle']['sid']
    
    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/{sid}"
    print(f'Trying: {user}@{host}:{port}/{sid}')
    
    engine = create_engine(url)
    
    with engine.connect() as conn:
        # 使用SC用户自己的表查询
        result = conn.execute(text("SELECT COUNT(*) FROM user_tables WHERE table_name LIKE 'S26_%'"))
        count = result.fetchone()[0]
        print(f'[OK] Connected! SC user tables: {count}')
        
except Exception as e:
    print(f'[FAIL] Oracle SC connection failed: {e}')
    print(f'\nCreating new SC user with proper privileges...')
    
    # 使用system用户创建SC
    print('\n=== Creating new SC user with SYSTEM connection ===')
    try:
        import oracledb
        conn = oracledb.connect(user='system', password=cfg['oracle']['password'], dsn=f'{host}:{port}/{sid}')
        cursor = conn.cursor()
        
        # 删除旧SC用户
        try:
            cursor.execute('DROP USER SC CASCADE')
            print('[OK] Dropped old SC user')
        except:
            pass
        
        # 创建新SC用户
        cursor.execute("""
            CREATE USER SC IDENTIFIED BY SC123456
            DEFAULT TABLESPACE USERS
            TEMPORARY TABLESPACE TEMP
            QUOTA UNLIMITED ON USERS
        """)
        conn.commit()
        print('[OK] Created new SC user')
        
        # 授权
        cursor.execute('GRANT CONNECT, RESOURCE TO SC')
        conn.commit()
        print('[OK] Granted CONNECT, RESOURCE')
        
        cursor.close()
        conn.close()
        
        # 重新连接SC用户
        print('\n=== Testing SC connection ===')
        conn = oracledb.connect(user='SC', password='SC123456', dsn=f'{host}:{port}/{sid}')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_tables WHERE table_name LIKE 'S26_%'")
        count = cursor.fetchone()[0]
        print(f'[OK] SC connected! Tables: {count}')
        cursor.close()
        conn.close()
        
    except Exception as e2:
        print(f'[FAIL] {e2}')
