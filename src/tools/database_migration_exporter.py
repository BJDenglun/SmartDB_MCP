import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection.pool_manager import MultiDBPoolManager


class DatabaseMigrationExporter:
    """数据库迁移导出工具 - 导出 MySQL 数据到 SQL 文件"""
    
    def __init__(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'database_config.json'
        )
        with open(config_path, 'r', encoding='utf-8') as f:
            self.configs = json.load(f)
        MultiDBPoolManager.init_from_config()
        self.pool_manager = MultiDBPoolManager.get_instance()
    
    def get_mysql_connection(self):
        """获取 MySQL 连接"""
        pool = self.pool_manager.get_pool('mysql')
        if not pool:
            raise ValueError("MySQL 连接池不存在")
        return pool
    
    def get_all_tables(self, database: str) -> List[Tuple]:
        """获取数据库所有表"""
        sql = f"""
        SELECT TABLE_NAME, TABLE_COMMENT 
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = '{database}' 
        AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
        pool = self.get_mysql_connection()
        with pool.connection() as conn:
            result = conn.execute(text(sql))
            return result.fetchall()
    
    def get_table_columns(self, table_name: str, database: str) -> List[Tuple]:
        """获取表字段信息"""
        sql = f"""
        SELECT 
            COLUMN_NAME,
            DATA_TYPE,
            COLUMN_TYPE,
            IS_NULLABLE,
            COLUMN_KEY,
            COLUMN_COMMENT,
            COLUMN_DEFAULT,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = '{database}' AND TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
        """
        pool = self.get_mysql_connection()
        with pool.connection() as conn:
            result = conn.execute(text(sql))
            return result.fetchall()
    
    def get_table_data(self, table_name: str) -> Tuple[List[str], List[Tuple]]:
        """获取表数据"""
        pool = self.get_mysql_connection()
        
        # 获取列名
        cols_sql = f"""
        SELECT COLUMN_NAME 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
        """
        with pool.connection() as conn:
            cols_result = conn.execute(text(cols_sql))
            columns = [row[0] for row in cols_result.fetchall()]
            
            # 获取数据
            data_sql = f"SELECT * FROM `{table_name}`"
            data_result = conn.execute(text(data_sql))
            data = data_result.fetchall()
            
            return columns, data
    
    def convert_mysql_to_oracle_type(self, mysql_type: str, col_length=None, col_precision=None, col_scale=None) -> str:
        """MySQL 类型转换为 Oracle 类型"""
        mysql_type_lower = mysql_type.lower()
        
        if mysql_type_lower.startswith('varchar('):
            return f"VARCHAR2({col_length or 255})"
        elif mysql_type_lower.startswith('char('):
            return f"CHAR({col_length or 1})"
        elif mysql_type_lower.startswith('decimal('):
            if col_precision and col_scale is not None:
                return f"NUMBER({col_precision},{col_scale})"
            elif col_precision:
                return f"NUMBER({col_precision})"
            return "NUMBER(10,2)"
        
        type_mapping = {
            'varchar': 'VARCHAR2(255)', 'char': 'CHAR(1)',
            'text': 'CLOB', 'longtext': 'CLOB', 'mediumtext': 'CLOB', 'tinytext': 'CLOB',
            'int': 'NUMBER(10)', 'bigint': 'NUMBER(20)', 'smallint': 'NUMBER(5)', 'tinyint': 'NUMBER(3)',
            'decimal': 'NUMBER(10,2)', 'float': 'FLOAT', 'double': 'FLOAT',
            'datetime': 'TIMESTAMP', 'timestamp': 'TIMESTAMP', 'date': 'DATE',
            'time': 'VARCHAR2(20)', 'year': 'VARCHAR2(4)',
            'blob': 'BLOB', 'longblob': 'BLOB', 'mediumblob': 'BLOB', 'tinyblob': 'BLOB',
            'enum': 'VARCHAR2(100)', 'set': 'VARCHAR2(100)', 'json': 'CLOB',
            'bit': 'NUMBER(1)', 'bool': 'NUMBER(1)', 'boolean': 'NUMBER(1)',
        }
        
        for mysql_t, oracle_t in type_mapping.items():
            if mysql_type_lower.startswith(mysql_t):
                return oracle_t
        return 'VARCHAR2(4000)'
    
    def convert_mysql_to_dameng_type(self, mysql_type: str, col_length=None, col_precision=None, col_scale=None) -> str:
        """MySQL 类型转换为达梦类型"""
        mysql_type_lower = mysql_type.lower()
        
        if mysql_type_lower.startswith('varchar('):
            return f"VARCHAR({col_length or 255})"
        elif mysql_type_lower.startswith('char('):
            return f"CHAR({col_length or 1})"
        elif mysql_type_lower.startswith('decimal('):
            if col_precision and col_scale is not None:
                return f"DEC({col_precision},{col_scale})"
            elif col_precision:
                return f"DEC({col_precision})"
            return "DEC(10,2)"
        
        type_mapping = {
            'varchar': 'VARCHAR(255)', 'char': 'CHAR(1)',
            'text': 'CLOB', 'longtext': 'CLOB', 'mediumtext': 'CLOB', 'tinytext': 'CLOB',
            'int': 'INT', 'bigint': 'BIGINT', 'smallint': 'SMALLINT', 'tinyint': 'SMALLINT',
            'decimal': 'DEC(10,2)', 'float': 'FLOAT', 'double': 'DOUBLE',
            'datetime': 'DATETIME', 'timestamp': 'TIMESTAMP', 'date': 'DATE',
            'time': 'VARCHAR(20)', 'year': 'VARCHAR(4)',
            'blob': 'BLOB', 'longblob': 'BLOB', 'mediumblob': 'BLOB', 'tinyblob': 'BLOB',
            'enum': 'VARCHAR(100)', 'set': 'VARCHAR(100)', 'json': 'CLOB',
            'bit': 'INT', 'bool': 'INT', 'boolean': 'INT',
        }
        
        for mysql_t, dameng_t in type_mapping.items():
            if mysql_type_lower.startswith(mysql_t):
                return dameng_t
        return 'VARCHAR(4000)'
    
    def generate_oracle_ddl(self, table_name: str, columns: List[Tuple]) -> str:
        """生成 Oracle DDL"""
        if not columns:
            return f"CREATE TABLE {table_name} (id NUMBER(10));\n"
        
        lines = []
        for col in columns:
            col_name = col[0]
            col_type_mysql = col[1]
            col_type_raw = col[2] if len(col) > 2 else col_type_mysql
            nullable = col[3] if len(col) > 3 else 'YES'
            col_default = col[6] if len(col) > 6 and col[6] else None
            col_length = col[7] if len(col) > 7 else None
            col_precision = col[8] if len(col) > 8 else None
            col_scale = col[9] if len(col) > 9 else None
            
            col_type = self.convert_mysql_to_oracle_type(col_type_raw, col_length, col_precision, col_scale)
            line = f"    {col_name} {col_type}"
            
            if nullable == 'NO':
                line += " NOT NULL"
            
            if col_default:
                if col_default == 'CURRENT_TIMESTAMP':
                    line += " DEFAULT SYSTIMESTAMP"
                elif str(col_default).replace('.','').replace('-','').isdigit():
                    line += f" DEFAULT {col_default}"
                else:
                    line += f" DEFAULT '{col_default}'"
            
            lines.append(line + ",")
        
        primary_keys = [col[0] for col in columns if len(col) > 4 and col[4] == 'PRI']
        if primary_keys:
            lines.append(f"    CONSTRAINT PK_{table_name} PRIMARY KEY ({', '.join(primary_keys)})")
        else:
            lines[-1] = lines[-1].rstrip(',')
        
        return f"CREATE TABLE {table_name} (\n" + "\n".join(lines) + "\n);\n\n"
    
    def generate_dameng_ddl(self, table_name: str, columns: List[Tuple]) -> str:
        """生成达梦 DDL"""
        if not columns:
            return f"CREATE TABLE {table_name} (id INT);\n"
        
        lines = []
        for col in columns:
            col_name = col[0]
            col_type_mysql = col[1]
            col_type_raw = col[2] if len(col) > 2 else col_type_mysql
            nullable = col[3] if len(col) > 3 else 'YES'
            col_default = col[6] if len(col) > 6 and col[6] else None
            col_length = col[7] if len(col) > 7 else None
            col_precision = col[8] if len(col) > 8 else None
            col_scale = col[9] if len(col) > 9 else None
            
            col_type = self.convert_mysql_to_dameng_type(col_type_raw, col_length, col_precision, col_scale)
            line = f"    {col_name} {col_type}"
            
            if nullable == 'NO':
                line += " NOT NULL"
            
            if col_default:
                if col_default == 'CURRENT_TIMESTAMP':
                    line += " DEFAULT SYSDATE"
                elif str(col_default).replace('.','').replace('-','').isdigit():
                    line += f" DEFAULT {col_default}"
                else:
                    line += f" DEFAULT '{col_default}'"
            
            lines.append(line + ",")
        
        primary_keys = [col[0] for col in columns if len(col) > 4 and col[4] == 'PRI']
        if primary_keys:
            lines.append(f"    PRIMARY KEY({', '.join(primary_keys)})")
        else:
            lines[-1] = lines[-1].rstrip(',')
        
        return f"CREATE TABLE {table_name} (\n" + "\n".join(lines) + "\n);\n\n"
    
    def generate_insert_sql(self, table_name: str, columns: List[str], data: List[Tuple], db_type: str = 'mysql') -> List[str]:
        """生成 INSERT 语句"""
        inserts = []
        for row in data:
            values = []
            for val in row:
                if val is None:
                    values.append('NULL')
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                elif isinstance(val, datetime):
                    if db_type == 'oracle':
                        values.append(f"TO_TIMESTAMP('{val.strftime('%Y-%m-%d %H:%M:%S')}', 'YYYY-MM-DD HH24:MI:SS')")
                    elif db_type == 'dameng':
                        values.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                    else:
                        values.append(f"'{val}'")
                else:
                    val_str = str(val).replace("'", "''")
                    values.append(f"'{val_str}'")
            
            if db_type == 'oracle':
                inserts.append(f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)});")
            else:
                inserts.append(f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)});")
        
        return inserts
    
    def export(self, source_db: str = 'bitables'):
        """导出数据库结构和数据"""
        print("=" * 80)
        print(f"开始导出 MySQL {source_db} 数据库")
        print("=" * 80)
        
        # 获取所有表
        print("\n[步骤 1] 获取所有表...")
        tables = self.get_all_tables(source_db)
        print(f"找到 {len(tables)} 个表")
        
        if not tables:
            print("错误: 未找到任何表!")
            return
        
        # 创建输出目录
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migration_output'
        )
        os.makedirs(output_dir, exist_ok=True)
        
        # 导出 Oracle SQL
        oracle_sql_file = os.path.join(output_dir, 'oracle_migration.sql')
        dameng_sql_file = os.path.join(output_dir, 'dameng_migration.sql')
        
        print(f"\n[步骤 2] 生成 Oracle DDL...")
        with open(oracle_sql_file, 'w', encoding='utf-8') as f:
            f.write("-- Oracle 迁移 SQL\n")
            f.write(f"-- 源数据库: MySQL {source_db}\n")
            f.write(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for table_info in tables:
                table_name = table_info[0]
                table_comment = table_info[1] if len(table_info) > 1 else ''
                
                if table_comment:
                    f.write(f"-- 表: {table_name} ({table_comment})\n")
                
                print(f"  处理表: {table_name}")
                
                columns = self.get_table_columns(table_name, source_db)
                ddl = self.generate_oracle_ddl(table_name, columns)
                f.write(ddl)
                
                if columns:
                    cols, data = self.get_table_data(table_name)
                    if data:
                        inserts = self.generate_insert_sql(table_name, cols, data, 'oracle')
                        for insert in inserts[:100]:  # 限制每个表最多100条 INSERT
                            f.write(insert + "\n")
                        if len(data) > 100:
                            f.write(f"-- 注意: 数据超过100条，仅导出前100条，共 {len(data)} 条\n")
        
        print(f"\n[步骤 3] 生成达梦 DDL...")
        with open(dameng_sql_file, 'w', encoding='utf-8') as f:
            f.write("-- 达梦迁移 SQL\n")
            f.write(f"-- 源数据库: MySQL {source_db}\n")
            f.write(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for table_info in tables:
                table_name = table_info[0]
                table_comment = table_info[1] if len(table_info) > 1 else ''
                
                if table_comment:
                    f.write(f"-- 表: {table_name} ({table_comment})\n")
                
                columns = self.get_table_columns(table_name, source_db)
                ddl = self.generate_dameng_ddl(table_name, columns)
                f.write(ddl)
                
                if columns:
                    cols, data = self.get_table_data(table_name)
                    if data:
                        inserts = self.generate_insert_sql(table_name, cols, data, 'dameng')
                        for insert in inserts[:100]:  # 限制每个表最多100条 INSERT
                            f.write(insert + "\n")
                        if len(data) > 100:
                            f.write(f"-- 注意: 数据超过100条，仅导出前100条，共 {len(data)} 条\n")
        
        print(f"\n" + "=" * 80)
        print("导出完成!")
        print(f"Oracle SQL: {oracle_sql_file}")
        print(f"达梦 SQL: {dameng_sql_file}")
        print("=" * 80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='数据库迁移导出工具')
    parser.add_argument('--source', default='bitables', help='源数据库名称')
    
    args = parser.parse_args()
    
    exporter = DatabaseMigrationExporter()
    exporter.export(args.source)


if __name__ == "__main__":
    main()