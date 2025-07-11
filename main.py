# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import QApplication
from main_window import MainWindow
from database import Database
import json

def test_db_connection():
    """测试数据库连接"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        db_config = config.get('starrocks')
        
        if not db_config:
            print("错误: 在 'config.json' 中未找到StarRocks数据库配置。")
            return False
            
        db = Database(db_config)
        if db.connect():
            print("数据库连接测试成功。")
            db.close()
            return True
        else:
            print("数据库连接测试失败。")
            return False
    except FileNotFoundError:
        print("错误: 配置文件 'config.json' 未找到。")
        return False
    except Exception as e:
        print(f"测试数据库连接时发生错误: {e}")
        return False

if __name__ == '__main__':
    # 在启动主应用前测试数据库连接
    if not test_db_connection():
        # 如果你希望在连接失败时阻止应用启动，可以取消下面的注释
        # sys.exit(1)
        pass

    app = QApplication(sys.argv)
    
    # 加载并应用QSS样式文件
    try:
        with open('style.qss', 'r', encoding='utf-8') as f:
            style_sheet = f.read()
        app.setStyleSheet(style_sheet)
        print("样式表 'style.qss' 加载成功。")
    except FileNotFoundError:
        print("警告: 样式文件 'style.qss' 未找到，将使用默认样式。")

    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())