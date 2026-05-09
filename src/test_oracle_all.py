import json
import os
import sys

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

oracle = cfg['oracle']
host = oracle['host']
port = oracle['port']
user = oracle['user']
password = oracle['password']

print('Oracle Configuration:')
print(f'  Host: {host}:{port}')
print(f'  User: {user}')

# 尝试不同的连接方式
print('\n[Test 1] Oracle+oracledb thin mode with wallet')
try:
    from sqlalchemy import create_engine, text
    url = f'oracle+oracledb://{user}:{password}@{host}:{port}'
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT * FROM v$instance'))
        print(f'[OK] Connected! Instance: {result.fetchone()}')
except Exception as e:
    print(f'[FAIL] {e}')

print('\n[Test 2] Using Easy Connect syntax')
try:
    url = f'oracle+oracledb://{user}:{password}@{host}:{port}/?server=deviced'
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT * FROM v$instance'))
        print(f'[OK] Connected! Instance: {result.fetchone()}')
except Exception as e:
    print(f'[FAIL] {e}')

print('\n[Test 3] Check Oracle Instant Client')
try:
    import oracledb
    print(f'Oracledb version: {oracledb.__version__}')
    print(f'Default dirs: {oracledb.defaults}')
except Exception as e:
    print(f'[FAIL] {e}')

print('\n[Test 4] Direct connection without SQLAlchemy')
try:
    import oracledb
    
    # 尝试无DSN连接
    conn = oracledb.connect(user=user, password=password, host=host, port=port)
    print(f'[OK] Connected!')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM v$instance')
    print(f'Instance: {cursor.fetchone()}')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'[FAIL] {e}')

print('\n[Test 5] Check if Oracle listener is running')
try:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    if result == 0:
        print(f'[OK] Port {port} is open')
    else:
        print(f'[FAIL] Port {port} is not reachable')
    sock.close()
except Exception as e:
    print(f'[FAIL] {e}')

print('\n[Test 6] Try connecting with different protocol')
try:
    import oracledb
    
    # 使用 (DESCRIPTION=...) 格式
    dsn = f'(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port})(CONNECT_DATA=(SID=ORCL)))'
    print(f'Trying DSN: {dsn}')
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    print(f'[OK] Connected!')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM v$instance')
    print(f'Instance: {cursor.fetchone()}')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'[FAIL] {e}')

print('\n[Test 7] Using cx_Oracle if available')
try:
    import cx_Oracle
    print(f'cx_Oracle version: {cx_Oracle.version}')
    
    dsn = cx_Oracle.makedsn(host, port, 'ORCL')
    conn = cx_Oracle.connect(user, password, dsn)
    print(f'[OK] Connected with cx_Oracle!')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM v$instance')
    print(f'Instance: {cursor.fetchone()}')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'[FAIL] {e}')
