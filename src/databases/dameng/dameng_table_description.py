from config.dbconfig import get_db_config_by_name
from databases.base.base import TableDescription
from databases.dameng.dameng_queries import DamengQueries
from utils.execute_sql_util import ExecuteSqlUtil


class DamengTableDescription(TableDescription):
    """达梦数据库表结构描述实现"""

    def get_table_description(self, pool_name: str, database: str, schema: str, table_name: str) -> str:
        """获取达梦数据库表结构描述
        
        Args:
            pool_name: 连接池名称
            database: 数据库名称（可选）
            schema: Schema 名称（可选，优先使用）
            table_name: 表名（支持多个，逗号分隔）
            
        Returns:
            表结构描述字符串
        """
        db_config = get_db_config_by_name(pool_name)

        # 获取 schema：优先使用传入的 schema，如果没有则从配置获取
        if schema is None:
            schema = db_config.get("schema")
        
        # 如果 database 不为 None 且 schema 也为 None，则使用 database 作为 schema
        if schema is None and database is not None:
            schema = database

        # 将输入的表名按逗号分割成列表
        table_names = [name.strip() for name in table_name.split(',')]
        
        # 达梦数据库使用 USER_TAB_COLUMNS 和 USER_COL_COMMENTS
        # 这些视图相对于当前连接用户，不需要额外的 schema 条件
        table_condition = "','".join(table_names)
        
        # 构建 SQL 查询 - 达梦兼容的列
        sql = f"""
            SELECT 
                A.COLUMN_NAME,
                A.DATA_TYPE,
                A.DATA_LENGTH,
                A.DATA_PRECISION,
                A.DATA_SCALE,
                A.NULLABLE,
                B.COMMENTS
            FROM USER_TAB_COLUMNS A
            LEFT JOIN USER_COL_COMMENTS B 
                ON A.TABLE_NAME = B.TABLE_NAME 
                AND A.COLUMN_NAME = B.COLUMN_NAME
            WHERE A.TABLE_NAME IN ('{table_condition}')
            ORDER BY A.COLUMN_ID
        """
        
        sql_result = ExecuteSqlUtil.execute_single_statement(pool_name, sql)

        return ExecuteSqlUtil.format_result(sql_result)
