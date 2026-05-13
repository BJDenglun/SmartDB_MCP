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

        sql, params = DamengQueries.get_table_description(schema, table_names)

        sql_result = ExecuteSqlUtil.execute_single_statement(pool_name, sql, params)

        return ExecuteSqlUtil.format_result(sql_result)
