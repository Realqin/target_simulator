# -*- coding: utf-8 -*-

import os
import subprocess
import sys

def generate_proto_files():
    """
    使用 grpc_tools.protoc 工具，将 .proto 文件编译成 Python 代码。
    这是开发流程中的一个辅助脚本，在修改了 .proto 文件后需要运行一次。
    """
    proto_file = 'target.proto'
    output_file = 'target_pb2.py'

    # 检查 .proto 文件是否存在
    if not os.path.exists(proto_file):
        print(f"错误: 未找到 '{proto_file}' 文件。请确保它在当前目录中。")
        sys.exit(1)

    print(f"正在从 '{proto_file}' 生成 Python 代码...")
    
    try:
        # 构造并执行 protoc 命令
        # sys.executable 指的是当前正在运行的 Python 解释器
        # -m grpc_tools.protoc 是官方推荐的、跨平台的调用方式
        command = [
            sys.executable,
            '-m',
            'grpc_tools.protoc',
            '-I.',  # -I 指定 .proto 文件的搜索路径，'.' 表示当前目录
            '--python_out=.',  # --python_out 指定生成的Python文件的输出目录
            proto_file
        ]
        
        result = subprocess.run(
            command,
            check=True,          # 如果命令返回非零退出码（表示错误），则抛出异常
            capture_output=True, # 捕获标准输出和标准错误
            text=True,           # 以文本模式处理输出
            encoding='utf-8'     # 指定编码
        )
        
        print(f"成功生成: {output_file}")
        
        # 如果 protoc 有任何输出，也打印出来
        if result.stdout:
            print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

    except FileNotFoundError:
        print("错误: 'python' 或 'grpc_tools.protoc' 命令未找到。")
        print("请确保已通过 'pip install -r requirements.txt' 安装了所有依赖。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        # 如果 protoc 命令执行失败，打印详细的错误信息
        print(f"Protobuf 代码生成失败:")
        print(e.stdout)
        print(e.stderr)
        sys.exit(1)

if __name__ == '__main__':
    # 当该脚本被直接执行时，调用生成函数
    generate_proto_files()
