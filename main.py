# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import QApplication

# 导入本地模块��的主窗口类
from main_window import MainWindow


def main():
    """
    应用程序的主入口函数。
    """
    # 1. 创建一个Qt Application实例，这是运行任何Qt程序的必需品。
    # sys.argv 参数允许将命令行参数传递给Qt应用。
    app = QApplication(sys.argv)

    # 2. 加载QSS样式表文件，美化UI。
    try:
        with open('style.qss', 'r', encoding='utf-8') as f:
            style = f.read()
        app.setStyleSheet(style)
        print("样式表 'style.qss' 加载成功。")
    except FileNotFoundError:
        print("警告: 未找到样式表文件 'style.qss'。将使用默认系统样式。")
    except Exception as e:
        print(f"加载样式表时发生错误: {e}")

    # 3. 创建主窗口的一个实例。
    main_win = MainWindow()
    
    # 4. 显示主窗口。
    main_win.show()

    # 5. 启动应用程序的事件循环。
    # 程序将在此处进入等待状态，响应用户的操作（如点击按钮、输入文本等）。
    # 当主窗口被关闭时，app.exec_() 会返回一个退出码，sys.exit() 将其传递给操作系统。
    sys.exit(app.exec_())

if __name__ == '__main__':
    # 这确保了 main() 函数只在脚本被直接执行时才运行，
    # 而不是在它被其他脚本导入时运行。
    main()
