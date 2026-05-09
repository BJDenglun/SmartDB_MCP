import json
import oracledb

with open('config/database_config.json', 'r') as f:
    cfg = json.load(f)

oracle = cfg['oracle']

print(f'Connecting as {oracle["user"]}...')
conn = oracledb.connect(user=oracle['user'], password=oracle['password'], dsn=f'{oracle["host"]}:{oracle["port"]}/XE')
cursor = conn.cursor()

print('\n=== Tables in current user ===')
cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
tables = cursor.fetchall()
print(f'Total: {len(tables)} tables\n')

for t in tables:
    table_name = t[0]
    cursor.execute(f"SELECT COUNT(*) FROM \"{table_name}\"")
    count = cursor.fetchone()[0]
    print(f'  {table_name}: {count} rows')

cursor.close()
conn.close()
print('\n[Done]')
