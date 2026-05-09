import json
import oracledb

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

oracle = cfg['oracle']
host = oracle['host']
port = oracle['port']

print('Connecting as SYSTEM...')
conn = oracledb.connect(user='system', password=oracle['password'], dsn=f'{host}:{port}/XE')
cursor = conn.cursor()

print('\n=== All Users ===')
cursor.execute("SELECT username, account_status, created FROM dba_users ORDER BY username")
for row in cursor:
    print(f'  {row[0]}: {row[1]} (created: {row[2]})')

print('\n=== Tables in SC ===')
cursor.execute("SELECT table_name FROM dba_tables WHERE owner = 'SC' ORDER BY table_name")
tables = cursor.fetchall()
print(f'Total: {len(tables)} tables')
for t in tables[:10]:
    print(f'  {t[0]}')
if len(tables) > 10:
    print(f'  ... and {len(tables)-10} more')

cursor.close()
conn.close()
print('\n[Done]')
