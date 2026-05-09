import json
from sqlalchemy import create_engine, text
import oracledb

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

oracle = cfg['oracle']
host = oracle['host']
port = oracle['port']
user = oracle['user']
password = oracle['password']

print('Connecting to Oracle...')
conn = oracledb.connect(user=user, password=password, dsn=f'{host}:{port}/XE')
cursor = conn.cursor()

print('\n=== Creating SC User ===')

try:
    # 创建用户
    print('Creating SC user...')
    cursor.execute("""
        CREATE USER SC IDENTIFIED BY SC123456
        DEFAULT TABLESPACE USERS
        TEMPORARY TABLESPACE TEMP
    """)
    conn.commit()
    print('[OK] User SC created')
except Exception as e:
    if 'ORA-01920' in str(e) or 'already exists' in str(e).lower():
        print('[OK] User SC already exists')
    else:
        print(f'[WARN] {e}')

try:
    # 授权
    print('Granting privileges...')
    cursor.execute('GRANT CONNECT, RESOURCE TO SC')
    conn.commit()
    print('[OK] Privileges granted')
except Exception as e:
    print(f'[WARN] {e}')

try:
    # 授予表空间配额
    print('Granting tablespace quota...')
    cursor.execute("ALTER USER SC QUOTA UNLIMITED ON USERS")
    conn.commit()
    print('[OK] Tablespace quota granted')
except Exception as e:
    print(f'[WARN] {e}')

print('\n=== Deleting old tables ===')
cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'S26_%'")
tables = cursor.fetchall()
print(f'Found {len(tables)} tables to delete')

for table in tables:
    table_name = table[0]
    try:
        cursor.execute(f'DROP TABLE {table_name}')
        print(f'[OK] Dropped {table_name}')
    except Exception as e:
        print(f'[WARN] {e}')

conn.commit()
print(f'\nDeleted {len(tables)} tables')

cursor.close()
conn.close()
print('\n[OK] Done!')
