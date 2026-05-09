import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection.pool_manager import MultiDBPoolManager


class DatabaseMigration:
    """数据库迁移工具"""
    
    def __init__(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'database_config.json'
        )
        with open(config_path, 'r', encoding='utf-8') as f:
            self.configs = json.load(f)
        MultiDBPoolManager.init_from_config()
        self.pool_manager = MultiDBPoolManager.get_instance()
    
    def execute_query(self, pool_name: str, sql: str) -> List[List]:
        """执行查询并返回数据"""
        pool = self.pool_manager.get_pool(pool_name)
        if not pool:
            raise ValueError(f"Pool '{pool_name}' not found")
        
        try:
            with pool.connection() as conn:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    return [list(row) for row in result.fetchall()]
                return []
        except Exception as e:
            print(f"      [错误] 查询失败: {str(e)}")
            return []
    
    def execute_dml(self, pool_name: str, sql: str):
        """执行 DML 语句（INSERT/UPDATE/DELETE）"""
        pool = self.pool_manager.get_pool(pool_name)
        if not pool:
            raise ValueError(f"Pool '{pool_name}' not found")
        
        try:
            with pool.connection() as conn:
                result = conn.execute(text(sql))
                conn.commit()
                return True, "Success"
        except Exception as e:
            error_msg = str(e)
            # 检查是否是达梦或 Oracle 的特定错误
            if "ORA-" in error_msg:
                return False, f"Oracle错误: {error_msg}"
            elif "DM_" in error_msg:
                return False, f"达梦错误: {error_msg}"
            elif "returned a result with an exception set" in error_msg:
                # 这是达梦的典型错误，可能是语法问题
                return False, f"数据库执行错误: {error_msg}"
            else:
                return False, f"执行失败: {error_msg}"
    
    def get_all_tables(self, database: str) -> List[List]:
        """获取数据库所有表"""
        sql = f"""
        SELECT TABLE_NAME, TABLE_COMMENT 
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = '{database}' 
        AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
        return self.execute_query('mysql', sql)
    
    def get_table_columns(self, table_name: str, database: str) -> List[List]:
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
            NUMERIC_SCALE,
            EXTRA
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = '{database}' AND TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
        """
        return self.execute_query('mysql', sql)
    
    def get_table_data(self, table_name: str, database: str) -> Tuple[List[str], List[List]]:
        """获取表数据"""
        columns_sql = f"""
        SELECT COLUMN_NAME 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = '{database}' AND TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
        """
        cols_result = self.execute_query('mysql', columns_sql)
        columns = [row[0] for row in cols_result]
        
        data_sql = f"SELECT * FROM `{table_name}`"
        data_result = self.execute_query('mysql', data_sql)
        
        return columns, data_result
    
    def convert_mysql_to_oracle_type(self, mysql_type: str, col_length: int = None, col_precision: int = None, col_scale: int = None) -> str:
        """MySQL 类型转换为 Oracle 类型"""
        mysql_type_lower = mysql_type.lower()
        
        # 先处理带长度的类型
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
            'varchar': 'VARCHAR2(255)',
            'char': 'CHAR(1)',
            'text': 'CLOB',
            'longtext': 'CLOB',
            'mediumtext': 'CLOB',
            'tinytext': 'CLOB',
            'int': 'NUMBER(10)',
            'bigint': 'NUMBER(20)',
            'smallint': 'NUMBER(5)',
            'tinyint': 'NUMBER(3)',
            'decimal': 'NUMBER(10,2)',
            'float': 'FLOAT',
            'double': 'FLOAT',
            'datetime': 'TIMESTAMP',
            'timestamp': 'TIMESTAMP',
            'date': 'DATE',
            'time': 'VARCHAR2(20)',
            'year': 'VARCHAR2(4)',
            'blob': 'BLOB',
            'longblob': 'BLOB',
            'mediumblob': 'BLOB',
            'tinyblob': 'BLOB',
            'enum': 'VARCHAR2(100)',
            'set': 'VARCHAR2(100)',
            'json': 'CLOB',
            'bit': 'NUMBER(1)',
            'bool': 'NUMBER(1)',
            'boolean': 'NUMBER(1)',
        }
        
        for mysql_t, oracle_t in type_mapping.items():
            if mysql_type_lower.startswith(mysql_t):
                return oracle_t
        
        return 'VARCHAR2(4000)'
    
    def convert_mysql_to_dameng_type(self, mysql_type: str, col_length: int = None, col_precision: int = None, col_scale: int = None) -> str:
        """MySQL 类型转换为达梦类型"""
        mysql_type_lower = mysql_type.lower()
        
        # 先处理带长度的类型
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
            'varchar': 'VARCHAR(255)',
            'char': 'CHAR(1)',
            'text': 'CLOB',
            'longtext': 'CLOB',
            'mediumtext': 'CLOB',
            'tinytext': 'CLOB',
            'int': 'INT',
            'bigint': 'BIGINT',
            'smallint': 'SMALLINT',
            'tinyint': 'SMALLINT',
            'decimal': 'DEC(10,2)',
            'float': 'FLOAT',
            'double': 'DOUBLE',
            'datetime': 'DATETIME',
            'timestamp': 'TIMESTAMP',
            'date': 'DATE',
            'time': 'VARCHAR(20)',
            'year': 'VARCHAR(4)',
            'blob': 'BLOB',
            'longblob': 'BLOB',
            'mediumblob': 'BLOB',
            'tinyblob': 'BLOB',
            'enum': 'VARCHAR(100)',
            'set': 'VARCHAR(100)',
            'json': 'CLOB',
            'bit': 'INT',
            'bool': 'INT',
            'boolean': 'INT',
        }
        
        for mysql_t, dameng_t in type_mapping.items():
            if mysql_type_lower.startswith(mysql_t):
                return dameng_t
        
        return 'VARCHAR(4000)'
    
    def generate_oracle_ddl(self, table_name: str, columns: List[List]) -> str:
        """生成 Oracle DDL"""
        if not columns:
            return f"CREATE TABLE {table_name} (id NUMBER(10))"
        
        lines = []
        col_lines = []
        
        for col in columns:
            col_name = col[0]
            col_type_mysql = col[1]  # DATA_TYPE
            col_type_raw = col[2] if len(col) > 2 else col_type_mysql  # COLUMN_TYPE (可能有长度)
            nullable = col[3] if len(col) > 3 else 'YES'
            col_default = col[6] if len(col) > 6 and col[6] else None
            col_length = col[7] if len(col) > 7 else None
            col_precision = col[8] if len(col) > 8 else None
            col_scale = col[9] if len(col) > 9 else None
            
            # 使用 COLUMN_TYPE 来提取精确的类型信息
            col_type_oracle = self.convert_mysql_to_oracle_type(col_type_raw, col_length, col_precision, col_scale)
            
            line = f"    {col_name} {col_type_oracle}"
            
            if nullable == 'NO':
                line += " NOT NULL"
            
            if col_default is not None and col_default != '':
                if col_default == 'CURRENT_TIMESTAMP' or col_default == 'CURRENT_TIMESTAMP(6)':
                    line += " DEFAULT SYSTIMESTAMP"
                elif col_default.replace('.','').replace('-','').isdigit():
                    line += f" DEFAULT {col_default}"
                else:
                    line += f" DEFAULT '{col_default}'"
            
            col_lines.append(line)
        
        # 检查主键
        primary_keys = [col[0] for col in columns if len(col) > 4 and col[4] == 'PRI']
        
        # 组装所有行
        for i, line in enumerate(col_lines):
            if i == len(col_lines) - 1 and primary_keys:
                lines.append(line)
            else:
                lines.append(line + ",")
        
        # 添加主键约束
        if primary_keys:
            lines.append(f"    CONSTRAINT PK_{table_name} PRIMARY KEY ({', '.join(primary_keys)})")
        
        return f"CREATE TABLE {table_name} (\n" + "\n".join(lines) + "\n)"
    
    def generate_dameng_ddl(self, table_name: str, columns: List[List]) -> str:
        """生成达梦 DDL"""
        if not columns:
            return f"CREATE TABLE {table_name} (id INT)"
        
        lines = []
        col_lines = []
        
        for col in columns:
            col_name = col[0]
            col_type_mysql = col[1]  # DATA_TYPE
            col_type_raw = col[2] if len(col) > 2 else col_type_mysql  # COLUMN_TYPE (可能有长度)
            nullable = col[3] if len(col) > 3 else 'YES'
            col_default = col[6] if len(col) > 6 and col[6] else None
            col_length = col[7] if len(col) > 7 else None
            col_precision = col[8] if len(col) > 8 else None
            col_scale = col[9] if len(col) > 9 else None
            
            # 使用 COLUMN_TYPE 来提取精确的类型信息
            col_type_dameng = self.convert_mysql_to_dameng_type(col_type_raw, col_length, col_precision, col_scale)
            
            line = f"    {col_name} {col_type_dameng}"
            
            if nullable == 'NO':
                line += " NOT NULL"
            
            if col_default is not None and col_default != '':
                if col_default == 'CURRENT_TIMESTAMP' or col_default == 'CURRENT_TIMESTAMP(6)':
                    line += " DEFAULT SYSDATE"
                elif col_default.replace('.','').replace('-','').isdigit():
                    line += f" DEFAULT {col_default}"
                else:
                    line += f" DEFAULT '{col_default}'"
            
            col_lines.append(line)
        
        # 检查主键
        primary_keys = [col[0] for col in columns if len(col) > 4 and col[4] == 'PRI']
        
        # 组装所有行
        for i, line in enumerate(col_lines):
            if i == len(col_lines) - 1 and primary_keys:
                lines.append(line)
            else:
                lines.append(line + ",")
        
        # 添加主键约束
        if primary_keys:
            lines.append(f"    PRIMARY KEY({', '.join(primary_keys)})")
        
        return f"CREATE TABLE {table_name} (\n" + "\n".join(lines) + "\n)"
    
    def table_exists(self, pool_name: str, table_name: str) -> bool:
        """检查表是否存在"""
        if pool_name == 'oracle':
            sql = f"SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER('{table_name}')"
        elif pool_name == 'default':
            sql = f"SELECT COUNT(*) FROM user_tables WHERE table_name = '{table_name}'"
        else:
            sql = f"SELECT COUNT(*) FROM information_schema.TABLES WHERE table_name = '{table_name}'"
        
        result = self.execute_query(pool_name, sql)
        return result and result[0][0] > 0
    
    def test_connections(self):
        """测试所有数据库连接"""
        print("\n[测试连接]")
        for pool_name in ['mysql', 'oracle', 'default']:
            try:
                pool = self.pool_manager.get_pool(pool_name)
                if pool:
                    with pool.connection() as conn:
                        result = conn.execute(text("SELECT 1 as test"))
                        print(f"  {pool_name}: OK")
                else:
                    print(f"  {pool_name}: 连接池不存在")
            except Exception as e:
                print(f"  {pool_name}: 失败 - {str(e)}")
    
    def migrate(self, source_db: str, migrate_data: bool = True):
        """执行迁移"""
        print("=" * 80)
        print(f"开始数据库迁移: MySQL bitables → Oracle + Dameng")
        print(f"模式: {'完整迁移（结构+数据）' if migrate_data else '仅迁移表结构'}")
        print("=" * 80)
        
        # 先测试连接
        self.test_connections()
        
        print("\n[步骤 1] 连接源数据库 MySQL...")
        tables = self.get_all_tables(source_db)
        print(f"      找到 {len(tables)} 个表")
        
        if not tables:
            print("错误: 未找到任何表!")
            return
        
        print("\n[步骤 2] 获取所有表结构...")
        table_info_list = []
        for table_record in tables:
            table_name = table_record[0] if table_record else ''
            table_comment = table_record[1] if table_record and len(table_record) > 1 else ''
            
            if not table_name:
                continue
            
            columns = self.get_table_columns(table_name, source_db)
            data = []
            columns_list = [c[0] for c in columns]
            
            if migrate_data:
                cols, data = self.get_table_data(table_name, source_db)
                columns_list = cols
            
            table_info_list.append({
                'name': table_name,
                'comment': table_comment,
                'columns': columns,
                'data': data,
                'columns_list': columns_list
            })
        
        print(f"      获取了 {len(table_info_list)} 个表的结构信息")
        
        # 只测试第一个表的迁移
        test_table = table_info_list[0] if table_info_list else None
        
        if test_table:
            print(f"\n[测试] 尝试创建第一个表: {test_table['name']}")
            print(f"      字段数: {len(test_table['columns'])}")
            
            # 先尝试达梦
            print(f"\n      到达梦:")
            ddl = self.generate_dameng_ddl(test_table['name'], test_table['columns'])
            print(f"      DDL:\n{ddl}")
            success, msg = self.execute_dml('default', ddl)
            print(f"      结果: {'成功' if success else '失败 - ' + msg}")
            
            # 如果成功，再尝试 Oracle
            if success:
                print(f"\n      到Oracle:")
                ddl = self.generate_oracle_ddl(test_table['name'], test_table['columns'])
                print(f"      DDL:\n{ddl}")
                success, msg = self.execute_dml('oracle', ddl)
                print(f"      结果: {'成功' if success else '失败 - ' + msg}")
        
        print("\n" + "=" * 80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='数据库迁移工具')
    parser.add_argument('--source', default='bitables', help='源数据库名称')
    parser.add_argument('--structure-only', action='store_true', help='仅迁移表结构，不迁移数据')
    
    args = parser.parse_args()
    
    migration = DatabaseMigration()
    migration.migrate(args.source, migrate_data=not args.structure_only)


if __name__ == "__main__":
    main()