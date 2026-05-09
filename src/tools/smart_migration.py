import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

class SmartDatabaseMigration:
    def __init__(self):
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'database_config.json'
        )
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.configs = json.load(f)
        
        self.connections = {}
        self.mysql_ok = False
        self.oracle_ok = False
        self.dameng_ok = False
        
        print("=" * 80)
        print("Smart Database Migration Tool")
        print("=" * 80)
    
    def try_connect_mysql(self) -> bool:
        print("\n[Step 1] Connecting to MySQL...")
        config = self.configs.get('mysql', {})
        
        try:
            host = config['host']
            port = config['port']
            user = config['user']
            password = config['password']
            database = config['database']
            
            url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT DATABASE()"))
                db_name = result.fetchone()[0]
                print(f"  [OK] MySQL connected! Database: {db_name}")
                
                result = conn.execute(text("SHOW TABLES"))
                tables = [row[0] for row in result.fetchall()]
                print(f"  [OK] Found {len(tables)} tables")
                print(f"  Sample: {tables[:5]}")
                
                self.connections['mysql'] = engine
                self.mysql_ok = True
                return True
                
        except Exception as e:
            print(f"  [FAIL] MySQL connection failed: {e}")
            return False
    
    def try_connect_oracle(self) -> bool:
        print("\n[Step 2] Connecting to Oracle...")
        config = self.configs.get('oracle', {})
        
        try:
            host = config['host']
            port = config['port']
            user = config['user']
            password = config['password']
            sid = config.get('sid', config.get('database', 'XE'))
            
            try:
                url = f"oracle+oracledb://{user}:{password}@{host}:{port}/{sid}"
                engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT COUNT(*) FROM user_tables"))
                    count = result.fetchone()[0]
                    print(f"  [OK] Oracle connected! User: {user}, Tables: {count}")
                    self.connections['oracle'] = engine
                    self.oracle_ok = True
                    return True
            except Exception as e1:
                print(f"    Method 1 failed: {str(e1)[:100]}")
            
            try:
                url = f"oracle+oracledb://{user}:{password}@{host}:{port}"
                engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT COUNT(*) FROM user_tables"))
                    count = result.fetchone()[0]
                    print(f"  [OK] Oracle connected (method 2)! User: {user}, Tables: {count}")
                    self.connections['oracle'] = engine
                    self.oracle_ok = True
                    return True
            except Exception as e2:
                print(f"    Method 2 failed: {str(e2)[:100]}")
            
            print(f"  [FAIL] Oracle all methods failed")
            return False
        except Exception as e:
            print(f"  [FAIL] Oracle connection failed: {e}")
            return False
    
    def try_connect_dameng(self) -> bool:
        print("\n[Step 3] Connecting to Dameng...")
        config = self.configs.get('default', {})
        
        try:
            host = config['host']
            port = config['port']
            user = config['user']
            password = config['password']
            
            try:
                url = f"dm+dmPython://{user}:{password}@{host}:{port}"
                engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
                
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT * FROM V$INSTANCE"))
                    instance = result.fetchone()
                    print(f"  [OK] Dameng connected! Instance: {instance}")
                    self.connections['dameng'] = engine
                    self.dameng_ok = True
                    return True
            except Exception as e1:
                print(f"    Method 1 failed: {str(e1)[:100]}")
            
            try:
                database = config.get('database', '')
                url = f"dm+dmPython://{user}:{password}@{host}:{port}/{database}"
                engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
                
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT * FROM V$INSTANCE"))
                    instance = result.fetchone()
                    print(f"  [OK] Dameng connected (method 2)! Instance: {instance}")
                    self.connections['dameng'] = engine
                    self.dameng_ok = True
                    return True
            except Exception as e2:
                print(f"    Method 2 failed: {str(e2)[:100]}")
            
            print(f"  [FAIL] Dameng all methods failed")
            return False
                
        except Exception as e:
            print(f"  [FAIL] Dameng connection failed: {e}")
            return False
    
    def get_mysql_tables(self) -> List[str]:
        if not self.mysql_ok:
            return []
        
        engine = self.connections['mysql']
        config = self.configs['mysql']
        database = config['database']
        
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT TABLE_NAME 
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = '{database}' 
                AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """))
            return [row[0] for row in result.fetchall()]
    
    def get_mysql_table_structure(self, table_name: str) -> Tuple[List[Dict], List[Tuple]]:
        if not self.mysql_ok:
            return [], []
        
        engine = self.connections['mysql']
        config = self.configs['mysql']
        database = config['database']
        
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT 
                    COLUMN_NAME, DATA_TYPE, COLUMN_TYPE,
                    IS_NULLABLE, COLUMN_KEY, COLUMN_COMMENT,
                    COLUMN_DEFAULT, CHARACTER_MAXIMUM_LENGTH,
                    NUMERIC_PRECISION, NUMERIC_SCALE
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = '{database}' AND TABLE_NAME = '{table_name}'
                ORDER BY ORDINAL_POSITION
            """))
            columns = [dict(row._mapping) for row in result.fetchall()]
            
            result = conn.execute(text(f"SELECT * FROM `{table_name}`"))
            data = result.fetchall()
            
            return columns, data
    
    def create_oracle_table(self, table_name: str, columns: List[Dict]) -> bool:
        if not self.oracle_ok:
            return False
        
        engine = self.connections['oracle']
        
        col_defs = []
        primary_keys = []
        
        for col in columns:
            name = col['COLUMN_NAME']
            data_type = col['DATA_TYPE']
            col_type = col['COLUMN_TYPE']
            nullable = col['IS_NULLABLE']
            default = col['COLUMN_DEFAULT']
            
            oracle_type = self._convert_to_oracle_type(data_type, col)
            
            col_def = f"    {name} {oracle_type}"
            
            if nullable == 'NO':
                col_def += " NOT NULL"
            
            if default:
                if default == 'CURRENT_TIMESTAMP':
                    col_def += " DEFAULT SYSTIMESTAMP"
                else:
                    col_def += f" DEFAULT {default}"
            
            col_defs.append(col_def)
            
            if col.get('COLUMN_KEY') == 'PRI':
                primary_keys.append(name)
        
        if primary_keys:
            col_defs.append(f"    CONSTRAINT PK_{table_name} PRIMARY KEY ({', '.join(primary_keys)})")
        
        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(col_defs) + "\n)"
        
        try:
            with engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
            return True
        except Exception as e:
            err_msg = str(e)
            err_lower = err_msg.lower()
            if 'ora-' in err_lower or 'already exists' in err_lower or 'dm_' in err_lower or '对象' in err_msg or 'already exist' in err_lower or 'code:-2124' in err_lower or 'code:-2007' in err_lower:
                return True  # 表已存在，视为成功
            print(f"      Create table failed: {e}")
            return False
    
    def create_dameng_table(self, table_name: str, columns: List[Dict]) -> bool:
        if not self.dameng_ok:
            return False
        
        engine = self.connections['dameng']
        
        col_defs = []
        primary_keys = []
        
        for col in columns:
            name = col['COLUMN_NAME']
            data_type = col['DATA_TYPE']
            nullable = col['IS_NULLABLE']
            default = col['COLUMN_DEFAULT']
            
            dameng_type = self._convert_to_dameng_type(data_type, col)
            
            col_def = f"    {name} {dameng_type}"
            
            if nullable == 'NO':
                col_def += " NOT NULL"
            
            if default:
                if default == 'CURRENT_TIMESTAMP':
                    col_def += " DEFAULT SYSDATE"
                else:
                    col_def += f" DEFAULT {default}"
            
            col_defs.append(col_def)
            
            if col.get('COLUMN_KEY') == 'PRI':
                primary_keys.append(name)
        
        if primary_keys:
            col_defs.append(f"    PRIMARY KEY ({', '.join(primary_keys)})")
        
        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(col_defs) + "\n)"
        
        try:
            with engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
            return True
        except Exception as e:
            err_msg = str(e)
            if 'dm_' in err_msg.lower() or '对象已存在' in err_msg or 'already exists' in err_msg.lower():
                return True  # 表已存在，视为成功
            print(f"      Create table failed: {e}")
            return False
    
    def insert_oracle_data(self, table_name: str, columns: List[str], data: List[Tuple]) -> int:
        if not self.oracle_ok or not data:
            return 0
        
        engine = self.connections['oracle']
        inserted = 0
        
        with engine.connect() as conn:
            for row in data:
                values = []
                for val in row:
                    if val is None:
                        values.append('NULL')
                    elif isinstance(val, (int, float)):
                        values.append(str(val))
                    elif isinstance(val, datetime):
                        values.append(f"TO_TIMESTAMP('{val.strftime('%Y-%m-%d %H:%M:%S')}', 'YYYY-MM-DD HH24:MI:SS')")
                    else:
                        val_str = str(val).replace("'", "''")
                        values.append(f"'{val_str}'")
                
                sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)})"
                try:
                    conn.execute(text(sql))
                    inserted += 1
                except:
                    break
            
            conn.commit()
        
        return inserted
    
    def insert_dameng_data(self, table_name: str, columns: List[str], data: List[Tuple]) -> int:
        if not self.dameng_ok or not data:
            return 0
        
        engine = self.connections['dameng']
        inserted = 0
        
        with engine.connect() as conn:
            for row in data:
                values = []
                for val in row:
                    if val is None:
                        values.append('NULL')
                    elif isinstance(val, (int, float)):
                        values.append(str(val))
                    elif isinstance(val, datetime):
                        values.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                    else:
                        val_str = str(val).replace("'", "''")
                        values.append(f"'{val_str}'")
                
                sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)})"
                try:
                    conn.execute(text(sql))
                    inserted += 1
                except:
                    break
            
            conn.commit()
        
        return inserted
    
    def _convert_to_oracle_type(self, mysql_type: str, col_info: Dict) -> str:
        t = mysql_type.lower()
        
        if t.startswith('varchar'):
            return f"VARCHAR2({col_info.get('CHARACTER_MAXIMUM_LENGTH') or 255})"
        elif t.startswith('char'):
            return f"CHAR({col_info.get('CHARACTER_MAXIMUM_LENGTH') or 1})"
        elif t == 'text' or 'text' in t:
            return 'CLOB'
        elif t == 'int':
            return 'NUMBER(10)'
        elif t == 'bigint':
            return 'NUMBER(20)'
        elif t == 'smallint':
            return 'NUMBER(5)'
        elif t == 'decimal':
            p = col_info.get('NUMERIC_PRECISION')
            s = col_info.get('NUMERIC_SCALE')
            if p and s is not None:
                return f"NUMBER({p},{s})"
            return 'NUMBER(10,2)'
        elif t in ('float', 'double'):
            return 'FLOAT'
        elif t in ('datetime', 'timestamp'):
            return 'TIMESTAMP'
        elif t == 'date':
            return 'DATE'
        elif 'blob' in t:
            return 'BLOB'
        else:
            return 'VARCHAR2(4000)'
    
    def _convert_to_dameng_type(self, mysql_type: str, col_info: Dict) -> str:
        t = mysql_type.lower()
        
        if t.startswith('varchar'):
            return f"VARCHAR({col_info.get('CHARACTER_MAXIMUM_LENGTH') or 255})"
        elif t.startswith('char'):
            return f"CHAR({col_info.get('CHARACTER_MAXIMUM_LENGTH') or 1})"
        elif t == 'text' or 'text' in t:
            return 'CLOB'
        elif t == 'int':
            return 'INT'
        elif t == 'bigint':
            return 'BIGINT'
        elif t == 'smallint':
            return 'SMALLINT'
        elif t == 'decimal':
            p = col_info.get('NUMERIC_PRECISION')
            s = col_info.get('NUMERIC_SCALE')
            if p and s is not None:
                return f"DEC({p},{s})"
            return 'DEC(10,2)'
        elif t in ('float', 'double'):
            return 'FLOAT'
        elif t in ('datetime', 'timestamp'):
            return 'DATETIME'
        elif t == 'date':
            return 'DATE'
        elif 'blob' in t:
            return 'BLOB'
        else:
            return 'VARCHAR(4000)'
    
    def run(self):
        self.try_connect_mysql()
        self.try_connect_oracle()
        self.try_connect_dameng()
        
        if not self.mysql_ok:
            print("\n[FAIL] MySQL connection failed, cannot migrate!")
            return
        
        print("\n[Step 4] Getting MySQL tables...")
        tables = self.get_mysql_tables()
        print(f"  Found {len(tables)} tables")
        
        if not tables:
            print("  [FAIL] No tables to migrate")
            return
        
        print("\n[Step 5] Starting migration...")
        
        oracle_success = 0
        oracle_total = 0
        dameng_success = 0
        dameng_total = 0
        
        for i, table_name in enumerate(tables, 1):
            print(f"\n  [{i}/{len(tables)}] Processing table: {table_name}")
            
            columns_info, data = self.get_mysql_table_structure(table_name)
            column_names = [col['COLUMN_NAME'] for col in columns_info]
            
            print(f"      Fields: {len(columns_info)}, Rows: {len(data)}")
            
            if self.oracle_ok:
                oracle_total += 1
                if self.create_oracle_table(table_name, columns_info):
                    inserted = self.insert_oracle_data(table_name, column_names, data)
                    print(f"      [OK] Oracle: Created, inserted {inserted} rows")
                    oracle_success += 1
                else:
                    print(f"      [FAIL] Oracle: Creation failed")
            
            if self.dameng_ok:
                dameng_total += 1
                if self.create_dameng_table(table_name, columns_info):
                    inserted = self.insert_dameng_data(table_name, column_names, data)
                    print(f"      [OK] Dameng: Created, inserted {inserted} rows")
                    dameng_success += 1
                else:
                    print(f"      [FAIL] Dameng: Creation failed")
        
        print("\n" + "=" * 80)
        print("Migration Results")
        print("=" * 80)
        print(f"  MySQL source tables: {len(tables)}")
        print(f"  Oracle: {oracle_success}/{oracle_total} tables succeeded")
        print(f"  Dameng: {dameng_success}/{dameng_total} tables succeeded")
        print("=" * 80)


if __name__ == "__main__":
    migration = SmartDatabaseMigration()
    migration.run()