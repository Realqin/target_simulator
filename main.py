# -*- coding: utf-8 -*-

import sys
import traceback
from PyQt5.QtWidgets import QApplication
from main_window import MainWindow


def main():
    """
    主函数，用于启动PyQt5应用程序。
    """
    # 添加全局异常捕获
    def exception_hook(exctype, value, tb):
        print("捕获到未处理的异常:")
        traceback.print_exception(exctype, value, tb)
        sys.exit(1)

    sys.excepthook = exception_hook

    try:
        app = QApplication(sys.argv)

        # 加载QSS样式表
        try:
            with open('style.qss', 'r', encoding='utf-8') as f:
                app.setStyleSheet(f.read())
                print("样式表 'style.qss' 加载成功。")
        except FileNotFoundError:
            print("警告: 样式表 'style.qss' 未找到，将使用默认样式。")

        main_win = MainWindow()
        main_win.show()
        sys.exit(app.exec_())

    except Exception as e:
        print("在应用程序启动期间发生致命错误:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
