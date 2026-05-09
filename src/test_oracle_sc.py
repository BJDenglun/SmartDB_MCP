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
sid = oracle.get('sid', 'XE')

print(f'Testing Oracle connection as {user}...')

# 使用oracledb直接连接
try:
    conn = oracledb.connect(user=user, password=password, dsn=f'{host}:{port}/{sid}')
    print('[OK] Direct connection successful!')
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_tables")
    count = cursor.fetchone()[0]
    print(f'Tables in {user}: {count}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'[FAIL] Direct connection: {e}')

# 使用SQLAlchemy
try:
    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/{sid}"
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM user_tables"))
        count = result.fetchone()[0]
        print(f'[OK] SQLAlchemy connection successful! Tables: {count}')
except Exception as e:
    print(f'[FAIL] SQLAlchemy: {e}')
