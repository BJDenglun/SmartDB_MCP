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

print(f'Host: {host}:{port}')
print(f'User: {user}')

# 尝试直接连接，不指定 SID
print('\n[Test 1] Direct connection without SID')
try:
    # 使用 Easy Connect 格式
    dsn = f'{host}:{port}'
    print(f'DSN: {dsn}')
    connection = oracledb.connect(user=user, password=password, dsn=dsn)
    print('[OK] Connected!')
    print(f'Veersion: {connection.version}')
    connection.close()
except Exception as e:
    print(f'[FAIL] {e}')

# 尝试用 SYSDBA 连接
print('\n[Test 2] SYSDBA connection')
try:
    connection = oracledb.connect(user='sys', password=password, dsn=f'{host}:{port}', mode=oracledb.SYSDBA)
    print('[OK] Connected as SYSDBA!')
    print(f'Veersion: {connection.version}')
    
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM v$instance")
    for row in cursor:
        print(f'Instance: {row}')
    cursor.close()
    connection.close()
except Exception as e:
    print(f'[FAIL] {e}')

# 检查 tnsnames.ora
print('\n[Test 3] Check TNS')
try:
    import os
    tns_admin = os.environ.get('TNS_ADMIN')
    print(f'TNS_ADMIN: {tns_admin}')
    
    # 列出常见的 tnsnames.ora 位置
    locations = [
        'C:\\oracle\\network\\admin',
        'C:\\oracle\\product\\19c\\network\\admin',
        'C:\\app\\oracle\\network\\admin',
    ]
    for loc in locations:
        if os.path.exists(loc):
            print(f'Found: {loc}')
            files = os.listdir(loc)
            for f in files:
                print(f'  {f}')
except Exception as e:
    print(f'Check failed: {e}')
