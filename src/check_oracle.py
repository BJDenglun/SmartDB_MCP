import json
from sqlalchemy import create_engine, text

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

oracle = cfg['oracle']
print('Oracle Config:')
for k, v in oracle.items():
    if k == 'password':
        print(f'  {k}: ***')
    else:
        print(f'  {k}: {v}')

host = oracle['host']
port = oracle['port']
user = oracle['user']
password = oracle['password']
sid = oracle.get('sid', 'ORCL')

print(f'\nTesting connection to {host}:{port}/{sid} as {user}')

# Method 1: SID
print('\n[Method 1] Using SID')
try:
    url = f'oracle+oracledb://{user}:{password}@{host}:{port}/?sid={sid}'
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT * FROM v$version WHERE ROWNUM = 1'))
        ver = result.fetchone()[0]
        print(f'[OK] Connected! Version: {ver[:50]}')
except Exception as e:
    print(f'[FAIL] {e}')

# Method 2: Service Name
print('\n[Method 2] Using Service Name')
try:
    service = oracle.get('service_name', oracle.get('database', 'ORCL'))
    url = f'oracle+oracledb://{user}:{password}@{host}:{port}/{service}'
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT * FROM v$version WHERE ROWNUM = 1'))
        ver = result.fetchone()[0]
        print(f'[OK] Connected! Version: {ver[:50]}')
except Exception as e:
    print(f'[FAIL] {e}')
