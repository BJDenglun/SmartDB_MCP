import json
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(base_dir, 'config', 'database_config.json')

with open(config_path, 'r', encoding='utf-8') as f:
    configs = json.load(f)

from sqlalchemy import create_engine, text

oracle_config = configs.get('oracle', {})

print("=" * 80)
print("Oracle Connection Diagnostics")
print("=" * 80)
print("\nConfiguration:")
for k, v in oracle_config.items():
    if k == 'password':
        print(f"  {k}: {v[:4]}***")
    else:
        print(f"  {k}: {v}")

host = oracle_config['host']
port = oracle_config['port']
user = oracle_config['user']
password = oracle_config['password']
sid = oracle_config.get('sid', oracle_config.get('database', 'ORCL'))
service_name = oracle_config.get('service_name', oracle_config.get('database', 'ORCL'))

print("\n" + "=" * 80)
print("Testing Connection Methods")
print("=" * 80)

# Method 1: SID with thin mode
print("\n[Method 1] Oracle+oracledb with SID (thin mode)")
try:
    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?sid={sid}"
    print(f"  URL: {url.replace(password, '***')}")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM v$version WHERE ROWNUM = 1"))
        version = result.fetchone()[0]
        print(f"  [OK] Connected! Version: {version[:50]}")
except Exception as e:
    print(f"  [FAIL] {e}")

# Method 2: Service Name with thin mode
print("\n[Method 2] Oracle+oracledb with Service Name (thin mode)")
try:
    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/{service_name}"
    print(f"  URL: {url.replace(password, '***')}")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM v$version WHERE ROWNUM = 1"))
        version = result.fetchone()[0]
        print(f"  [OK] Connected! Version: {version[:50]}")
except Exception as e:
    print(f"  [FAIL] {e}")

# Method 3: Direct connection without pool
print("\n[Method 3] Direct oracledb connection (no pool)")
try:
    import oracledb
    print(f"  Connecting to {host}:{port}/{sid} as {user}...")
    connection = oracledb.connect(user=user, password=password, dsn=f"{host}:{port}/{sid}")
    print(f"  [OK] Connected!")
    version = connection.version
    print(f"  Version: {version}")
    connection.close()
except Exception as e:
    print(f"  [FAIL] {e}")
    print(f"  Error type: {type(e).__name__}")

print("\n" + "=" * 80)
print("Diagnostics Complete")
print("=" * 80)
