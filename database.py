# -*- coding: utf-8 -*-

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

class Database:
    """
    用于处理与StarRocks数据库所有交互的类。
    """
    def __init__(self, db_config):
        """
        初始化数据库连接。
        :param db_config: 包含 'host', 'port', 'user', 'password', 'database' 的字典。
        """
        if not db_config:
            raise ValueError("数据库配置不能为空。")
            
        self.db_url = (
            f"mysql+pymysql://{db_config.get('user')}:{db_config.get('password')}"
            f"@{db_config.get('host')}:{db_config.get('port')}"
            f"/{db_config.get('database')}"
        )
        self.engine = create_engine(self.db_url, pool_size=5, pool_recycle=3600, echo=False)
        self.Session = sessionmaker(bind=self.engine)
        self.session = None

    def connect(self):
        """
        建立并测试数据库连接。
        :return: 如果连接成功则返回 True，否则返回 False。
        """
        try:
            self.session = self.Session()
            # 执行一个简单的查询来验证连接
            self.session.execute(text("SELECT 1"))
            print("数据库连接成功。")
            return True
        except SQLAlchemyError as e:
            print(f"数据库连接失败: {e}")
            self.session = None
            return False

    def query_trajectories(self, criteria=None, start_time=None, end_time=None):
        """
        根据提供的精确参数查询轨迹数据。
        :param criteria: 一个包含查询条件的字典，如 {'mmsi': '123', 'id': '456'}
        :param start_time: 开始时间 (YYYY-MM-DD HH:MM:SS)
        :param end_time: 结束时间 (YYYY-MM-DD HH:MM:SS)
        :return: 查询结果列表，如果出错则返回空列表。
        """
        if not self.session:
            if not self.connect():
                return []

        try:
            params = {}
            query_conditions = []

            if criteria:
                for key, value in criteria.items():
                    if value: # 确保值不为空
                        query_conditions.append(f"{key} = :{key}")
                        params[key] = value
            
            if start_time and end_time:
                query_conditions.append("lastDT BETWEEN :start_time AND :end_time")
                params['start_time'] = start_time
                params['end_time'] = end_time

            if not query_conditions:
                print("警告: 查询条件为空，不执行查询。")
                return []

            query_str = f"SELECT * FROM ods_original_trajectory WHERE {' AND '.join(query_conditions)} ORDER BY lastTm"
            
            print(f"执行查询: {query_str} with params {params}")
            result = self.session.execute(text(query_str), params).fetchall()
            return result

        except SQLAlchemyError as e:
            print(f"数据库查询错误: {e}")
            return []

    def close(self):
        """
        关闭数据库会话。
        """
        if self.session:
            self.session.close()
            print("数据库会话已关闭。")

