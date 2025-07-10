# -*- coding: utf-8 -*-

import sys
import time
import re
import random
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGridLayout, QGroupBox, QTextEdit, QSpacerItem, QSizePolicy,
    QComboBox, QCheckBox
)
from PyQt5.QtCore import pyqtSlot, QTimer, Qt
from PyQt5.QtGui import QIcon, QCursor

from kafka_producer import KProducer
import target_pb2


class MainWindow(QWidget):
    """
    应用程序的主窗口类。
    负责构建UI界面、处理用户交互以及与后端逻辑（如Kafka生产者）的通信。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle("Simu Kafka Sender")
        self.setGeometry(100, 100, 1300, 750) # x, y, width, height

        # 加载外部配置
        self.config = self.load_config()

        # 创建一个定时器，用于周期性地发送数据
        self.sending_timer = QTimer(self)
        self.sending_timer.timeout.connect(self.send_data)

        # 初始化UI界面
        self.init_ui()

        # 初始化Kafka生产者，并将UI的日志函数作为回调传递进去
        self.kafka_producer = KProducer(
            bootstrap_servers=self.config['kafka']['bootstrap_servers'],
            log_callback=self.log_message
        )

    def load_config(self):
        """从 config.json 加载配置。如果失败则返回默认配置。"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                print("配置文件 'config.json' 加载成功。")
                return config_data
        except FileNotFoundError:
            print("错误: 配置文件 'config.json' 未找到。将使用默认设置。")
        except json.JSONDecodeError:
            print("错误: 配置文件 'config.json' 格式无效。将使用默认设置。")
        
        # 返回一个安全的默认值
        return {
            "kafka": {"bootstrap_servers": "localhost:9092", "topic": "fusion_target_topic"},
            "ui_options": {
                "eTargetType": {"OTHERS": 14},
                "shiptype": {"其他": 99},
                "sost": {"正常": 1},
                "dataStatus": {"new": 0, "update": 1, "delete": 2}
            }
        }

    def init_ui(self):
        """
        初始化和构建整个用户界面。
        """
        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        top_h_layout = QHBoxLayout()

        # --- 左侧布局 (包含目标信息和AIS静态信息) ---
        left_v_layout = QVBoxLayout()

        # “快速识别”功能区
        paste_group = QGroupBox("快速识别")
        paste_layout = QHBoxLayout()
        self.paste_input = QTextEdit()
        self.paste_input.setPlaceholderText("在此粘贴内容（可多行），然后点击识别...")
        self.paste_input.setFixedHeight(80)
        recognize_btn = QPushButton("识别")
        recognize_btn.clicked.connect(self.recognize_and_fill)
        paste_layout.addWidget(self.paste_input)
        paste_layout.addWidget(recognize_btn)
        paste_group.setLayout(paste_layout)
        left_v_layout.addWidget(paste_group)

        # 创建并添加目标信息模块
        left_v_layout.addWidget(self.create_target_info_group())
        # 创建并添加AIS静态信息模块
        left_v_layout.addWidget(self.create_ais_static_info_group())
        # 创建并添加信息源模块
        left_v_layout.addWidget(self.create_source_input_group())
        left_v_layout.addStretch(1)
        # --- 右侧布局 (包含控制操作和日志) ---
        right_v_layout = QVBoxLayout()
        right_v_layout.addWidget(self.create_control_group())
        
        # 将日志区移动到右侧
        self.log_group = QGroupBox("发送日志")
        self.log_group.setCheckable(True)
        self.log_group.setChecked(True)
        log_layout = QVBoxLayout()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumHeight(200)
        self.log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        log_layout.addWidget(self.log_display)
        self.log_group.setLayout(log_layout)
        self.log_group.toggled.connect(self.log_display.setVisible)
        
        right_v_layout.addWidget(self.log_group, stretch=1)
        
        #right_v_layout.addStretch(1)

        # --- 组合左右布局 ---
        top_h_layout.addLayout(left_v_layout, stretch=3)
        top_h_layout.addLayout(right_v_layout, stretch=1)
        main_layout.addLayout(top_h_layout)

        

        self.setLayout(main_layout)

        # --- 设置光标样式 ---
        self.set_cursors()

    def set_cursors(self):
        """统一设置所有控件的光标样式"""
        # 按钮和可点击项
        pointing_hand = QCursor(Qt.PointingHandCursor)
        # 文本输入
        ibeam_cursor = QCursor(Qt.IBeamCursor)

        # 所有按钮
        for button in self.findChildren(QPushButton):
            button.setCursor(pointing_hand)

        # 所有复选框
        for checkbox in self.findChildren(QCheckBox):
            checkbox.setCursor(pointing_hand)

        # 所有下拉列表
        for combobox in self.findChildren(QComboBox):
            combobox.setCursor(pointing_hand)

        # 所有文本输入框
        for line_edit in self.findChildren(QLineEdit):
            line_edit.setCursor(ibeam_cursor)
        
        self.paste_input.setCursor(ibeam_cursor)
        self.log_display.setCursor(ibeam_cursor)

    def create_target_info_group(self):
        """创建“目标信息”模块的 GroupBox"""
        group_box = QGroupBox("目标信息")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # 初始化该模块的控件
        self.inputs = {
            "eTargetType": QComboBox(), "vesselName": QLineEdit(),
            "id": QLineEdit(), "mmsi": QLineEdit(),
            "beidouId": QLineEdit(), "shiptype": QComboBox(),
            "course": QLineEdit(), "speed": QLineEdit(),
            "longitude": QLineEdit(), "latitude": QLineEdit(),
            "len": QLineEdit(), "maxLength": QLineEdit(),
            "sost": QComboBox(), "dataStatus": QComboBox()
        }
        
        # 填充下拉列表
        for text, value in self.config['ui_options']['eTargetType'].items():
            self.inputs['eTargetType'].addItem(text, value)
        for text, value in self.config['ui_options']['shiptype'].items():
            self.inputs['shiptype'].addItem(text, value)
        for text, value in self.config['ui_options']['sost'].items():
            self.inputs['sost'].addItem(text, value)
        for text, value in self.config['ui_options']['dataStatus'].items():
            self.inputs['dataStatus'].addItem(text, value)

        # --- 添加控件到网格布局 ---
        grid_layout.addWidget(QLabel("目标类型:"), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["eTargetType"], 0, 1)
        grid_layout.addWidget(QLabel("船名:"), 0, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["vesselName"], 0, 3)

        # ID with random button
        id_layout = QHBoxLayout()
        id_layout.addWidget(self.inputs["id"])
        random_id_btn = QPushButton("随机")
        random_id_btn.clicked.connect(self.generate_random_id)
        id_layout.addWidget(random_id_btn)
        grid_layout.addWidget(QLabel("ID:"), 1, 0, Qt.AlignRight)
        grid_layout.addLayout(id_layout, 1, 1)

        # MMSI with random button
        mmsi_layout = QHBoxLayout()
        mmsi_layout.addWidget(self.inputs["mmsi"])
        random_mmsi_btn = QPushButton("随机")
        random_mmsi_btn.clicked.connect(self.generate_random_mmsi)
        mmsi_layout.addWidget(random_mmsi_btn)
        grid_layout.addWidget(QLabel("MMSI:"), 1, 2, Qt.AlignRight)
        grid_layout.addLayout(mmsi_layout, 1, 3)

        grid_layout.addWidget(QLabel("北斗号:"), 2, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["beidouId"], 2, 1)
        grid_layout.addWidget(QLabel("船舶类型:"), 2, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["shiptype"], 2, 3)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["course"])
        len_layout.addWidget(QLabel("度"))
        grid_layout.addWidget(QLabel("航向:"), 3, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 3, 1)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["speed"])
        len_layout.addWidget(QLabel("节"))
        grid_layout.addWidget(QLabel("航速:"), 3, 2, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 3, 3)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["longitude"])
        len_layout.addWidget(QLabel("度"))
        grid_layout.addWidget(QLabel("经度:"), 4, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 4, 1)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["latitude"])
        len_layout.addWidget(QLabel("度"))
        grid_layout.addWidget(QLabel("纬度:"), 4, 2, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 4, 3)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["len"])
        len_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("船长:"), 5, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 5, 1)
        
        max_len_layout = QHBoxLayout()
        max_len_layout.addWidget(self.inputs["maxLength"])
        max_len_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("最大船长:"), 5, 2, Qt.AlignRight)
        grid_layout.addLayout(max_len_layout, 5, 3)

        grid_layout.addWidget(QLabel("目标状态:"), 6, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["sost"], 6, 1)
        
        data_status_layout = QHBoxLayout()
        data_status_layout.addWidget(self.inputs["dataStatus"])
        self.data_status_checkbox = QCheckBox("默认")
        self.data_status_checkbox.toggled.connect(self.toggle_data_status_lock)
        data_status_layout.addWidget(self.data_status_checkbox)
        grid_layout.addWidget(QLabel("数据状态:"), 6, 2, Qt.AlignRight)
        grid_layout.addLayout(data_status_layout, 6, 3)

        self.data_status_checkbox.setChecked(True)

        group_box.setLayout(grid_layout)
        return group_box

    def create_ais_static_info_group(self):
        """创建“AIS静态信息”模块的 GroupBox"""
        group_box = QGroupBox("AIS静态信息")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # 初始化该模块的控件
        self.inputs.update({
            "deviceCategory": QLineEdit(), "nationality": QLineEdit(),
            "imo": QLineEdit(), "callSign": QLineEdit(),
            "shipWidth": QLineEdit(), "draught": QLineEdit(),
            "heading": QLineEdit(), "eta": QLineEdit(),
            "destination": QLineEdit()
        })

        # --- 添加控件到网格布局 ---
        grid_layout.addWidget(QLabel("设备分类:"), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["deviceCategory"], 0, 1)
        grid_layout.addWidget(QLabel("船籍:"), 0, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["nationality"], 0, 3)

        grid_layout.addWidget(QLabel("IMO:"), 1, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["imo"], 1, 1)
        grid_layout.addWidget(QLabel("呼号:"), 1, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["callSign"], 1, 3)

        # 船宽输入框带单位
        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["shipWidth"])
        len_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("船宽:"), 2, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 2, 1)

        # 吃水输入框带单位
        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["draught"])
        len_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("吃水:"), 2, 2, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 2, 3)

        # grid_layout.addWidget(QLabel("船宽:"), 2, 0, Qt.AlignRight)
        # grid_layout.addWidget(self.inputs["shipWidth"], 2, 1)
        # grid_layout.addWidget(QLabel("吃水:"), 2, 2, Qt.AlignRight)
        # grid_layout.addWidget(self.inputs["draught"], 2, 3)

        # 艏向输入框带单位
        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["heading"])
        len_layout.addWidget(QLabel("度"))
        grid_layout.addWidget(QLabel("艏向:"), 3, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 3, 1)

        grid_layout.addWidget(QLabel("预到时间:"), 3, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["eta"], 3, 3)

        grid_layout.addWidget(QLabel("目的地:"), 4, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["destination"], 4, 1, 1, 3)

        group_box.setLayout(grid_layout)
        return group_box

    def create_source_input_group(self):
        """创建信息源文本输入模块"""
        group_box = QGroupBox("信息源")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(3)

        # 初始化该模块的控件
        self.inputs.update({
            "radarSource": QLineEdit(), "aisSource": QLineEdit(),
            "bdSource": QLineEdit()
        })

        grid_layout.addWidget(QLabel("雷达信息源:"), 1, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["radarSource"], 1, 1, 1, 4)
        grid_layout.addWidget(QLabel("AIS信息源:"), 2, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["aisSource"], 2, 1, 1, 4)
        grid_layout.addWidget(QLabel("北斗信息源:"), 3, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["bdSource"], 3, 1, 1, 4)
        group_box.setLayout(grid_layout)
        return group_box

    def create_control_group(self):
        """创建方向控制和操作按钮模块"""
        group_box = QGroupBox("控制与操作")
        v_layout = QVBoxLayout()


        # 发送频率设置
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("发送频率（秒/次）"))
        self.frequency_input = QLineEdit("3") # 默认3秒
        self.frequency_input.setFixedWidth(50)
        freq_layout.addWidget(self.frequency_input)
        freq_layout.addStretch()
        v_layout.addLayout(freq_layout)

        # 方向控制
        control_layout = QGridLayout()
        control_layout.setSpacing(5) # 减小按钮间距

        # 创建按钮
        up_btn = QPushButton("↑")
        down_btn = QPushButton("↓")
        left_btn = QPushButton("←")
        right_btn = QPushButton("→")
        up_left_btn = QPushButton("↖")
        up_right_btn = QPushButton("↗")
        down_left_btn = QPushButton("↙")
        down_right_btn = QPushButton("↘")

        # 连接信���
        up_btn.clicked.connect(lambda: self.update_course_from_button(0))
        down_btn.clicked.connect(lambda: self.update_course_from_button(180))
        left_btn.clicked.connect(lambda: self.update_course_from_button(270))
        right_btn.clicked.connect(lambda: self.update_course_from_button(90))
        up_left_btn.clicked.connect(lambda: self.update_course_from_button(315))
        up_right_btn.clicked.connect(lambda: self.update_course_from_button(45))
        down_left_btn.clicked.connect(lambda: self.update_course_from_button(225))
        down_right_btn.clicked.connect(lambda: self.update_course_from_button(135))

        # 设置样式
        cardinal_style = "background-color: #E0E0E0; font-weight: bold;"
        diagonal_style = "background-color: #D0E8FF; font-weight: bold;"
        up_btn.setStyleSheet(cardinal_style)
        down_btn.setStyleSheet(cardinal_style)
        left_btn.setStyleSheet(cardinal_style)
        right_btn.setStyleSheet(cardinal_style)
        up_left_btn.setStyleSheet(diagonal_style)
        up_right_btn.setStyleSheet(diagonal_style)
        down_left_btn.setStyleSheet(diagonal_style)
        down_right_btn.setStyleSheet(diagonal_style)

        # 添加到布局
        control_layout.addWidget(up_left_btn, 0, 0)
        control_layout.addWidget(up_btn, 0, 1)
        control_layout.addWidget(up_right_btn, 0, 2)
        control_layout.addWidget(left_btn, 1, 0)
        control_layout.addWidget(right_btn, 1, 2)
        control_layout.addWidget(down_left_btn, 2, 0)
        control_layout.addWidget(down_btn, 2, 1)
        control_layout.addWidget(down_right_btn, 2, 2)
        
        v_layout.addLayout(control_layout)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.start_pause_btn = QPushButton("开始发送")
        self.start_pause_btn.setObjectName("StartButton")
        self.start_pause_btn.clicked.connect(self.toggle_sending_state)
        self.terminate_btn = QPushButton("终止发送")
        self.terminate_btn.setObjectName("StopButton")
        self.terminate_btn.clicked.connect(self.terminate_sending)
        self.terminate_btn.setEnabled(False)
        self.clear_btn = QPushButton("清除")
        self.clear_btn.clicked.connect(self.clear_inputs)

        button_layout.addWidget(self.start_pause_btn)
        button_layout.addWidget(self.terminate_btn)
        button_layout.addWidget(self.clear_btn)
        v_layout.addLayout(button_layout)
        
        group_box.setLayout(v_layout)
        return group_box

    @pyqtSlot()
    def generate_random_id(self):
        """生成一个以99开头的20位数字ID"""
        random_part = ''.join([str(random.randint(0, 9)) for _ in range(18)])
        new_id = "11" + random_part
        self.inputs["id"].setText(new_id)
        self.log_message(f"已生成随机ID: {new_id}")

    @pyqtSlot()
    def generate_random_mmsi(self):
        """生成一个9位数字的MMSI"""
        new_mmsi = ''.join([str(random.randint(0, 9)) for _ in range(9)])
        self.inputs["mmsi"].setText(new_mmsi)
        self.log_message(f"已生成随机MMSI: {new_mmsi}")

    @pyqtSlot(int)
    def update_course_from_button(self, angle):
        self.inputs["course"].setText(str(angle))

    @pyqtSlot()
    def recognize_and_fill(self):
        """
        解析粘贴的文本并填充到UI控件中。
        """
        content = self.paste_input.toPlainText()
        if not content: return
        
        # 映射关系：UI标签 -> 内部字段名
        label_map = {
            "目标类型": "eTargetType", "船名": "vesselName", "ID": "id", "MMSI": "mmsi",
            "北斗号": "beidouId", "船舶类型": "shiptype", "航向": "course", "航速": "speed",
            "经度": "longitude", "纬度": "latitude", "船长": "len", "最大船长": "maxLength",
            "目标状态": "sost", "数据状态": "dataStatus", "设备分类": "deviceCategory",
            "船籍": "nationality", "IMO": "imo", "呼号": "callSign", "船宽": "shipWidth",
            "吃水": "draught", "艏向": "heading", "预到时间": "eta", "目的地": "destination",
            "AIS信息源":"aisSource","北斗信息源":"bdSource","雷达信息源":"radarSource"
        }
        
        # 需要特殊处理（只提取数字）的字段
        numeric_fields = {
            "course", "speed", "longitude", "latitude", "len", 
            "maxLength", "shipWidth", "draught", "heading"
        }

        filled_fields = []
        lines = content.splitlines()
        for line in lines:
            for label, field_name in label_map.items():
                if label in line:
                    # 提取冒号或标签后的值
                    value_part = line.split(label, 1)[-1]
                    value_part = value_part.lstrip(' :：').strip()

                    # 如果是需要提取数字的字段
                    if field_name in numeric_fields:
                        # 使用正则表达式查找第一个出现的整数或浮点数
                        match = re.search(r'[-+]?\d*\.?\d+', value_part)
                        if match:
                            raw_value = match.group(0)
                        else:
                            raw_value = "" # 如果没找到数字，则为空
                    else:
                        # 对于其他字段，取第一个空格前的内容
                        raw_value = value_part.split()[0] if value_part else ""

                    widget = self.inputs.get(field_name)
                    if widget:
                        if isinstance(widget, QLineEdit):
                            widget.setText(raw_value)
                        elif isinstance(widget, QComboBox):
                            index = widget.findText(raw_value, Qt.MatchContains)
                            if index != -1: widget.setCurrentIndex(index)
                        filled_fields.append(field_name)
                        break
        
        if filled_fields:
            self.log_message(f"快速识别: 已填充字段 {', '.join(filled_fields)}")
        else:
            self.log_message("快速识别: 未找到可识别的数据。")

    @pyqtSlot()
    def clear_inputs(self):
        """清除所有输入框和下拉列表到初始状态。"""
        self.paste_input.clear()
        for widget in self.inputs.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
        # 恢复 dataStatus 的默认锁定状态
        if hasattr(self, 'data_status_checkbox'):
            self.data_status_checkbox.setChecked(True)
        self.log_message("所有输入已清除。")

    def toggle_sending_state(self):
        """
        切换发送状态：开始 -> 暂停 -> 继续
        """
        # 如果当前不在发送状态（包括初始状态和暂停状态）
        if not self.sending_timer.isActive():
            try:
                # 获取频率值，并转换为毫秒
                frequency_sec = float(self.frequency_input.text())
                if frequency_sec <= 0:
                    raise ValueError
                interval_ms = int(frequency_sec * 1000)
            except (ValueError, TypeError):
                self.log_message("错误: 发送频率必须是一个大于0的数字。将使用默认值3秒。")
                interval_ms = 3000
                self.frequency_input.setText("3")

            # 如果是初始状态
            if not self.terminate_btn.isEnabled():
                self.log_message(f"开始发送数据... (频率: {interval_ms / 1000}s/次)")
                self.send_data() # 立即发送一次
            else: # 如果是暂停后继续
                self.log_message(f"继续发送数据... (频率: {interval_ms / 1000}s/次)")
            
            self.sending_timer.start(interval_ms)
            self.start_pause_btn.setText("暂停发送")
            self.terminate_btn.setEnabled(True)
            self.frequency_input.setEnabled(False) # 发送期间禁止修改频率
        # 如果当前正在发送
        else:
            self.sending_timer.stop()
            self.log_message("已暂停发送数据。")
            self.start_pause_btn.setText("继续发送")
            self.frequency_input.setEnabled(True) # 暂停时允许修改频率

    def terminate_sending(self):
        """
        终止发送流程，并重置按钮状态。
        """
        self.sending_timer.stop()
        self.log_message("已终止发送数据。")
        self.start_pause_btn.setText("开始发送")
        self.terminate_btn.setEnabled(False)
        self.frequency_input.setEnabled(True) # 终止时允许修改频率

    def toggle_data_status_lock(self, is_checked):
        """
        根据复选框状态，启用/禁用数据状态下拉列表。
        """
        if is_checked:
            self.inputs["dataStatus"].setCurrentIndex(-1) # 清除选择，显示为空
            self.inputs["dataStatus"].setEnabled(False)
        else:
            self.inputs["dataStatus"].setEnabled(True)
            self.inputs["dataStatus"].setCurrentIndex(0) # 默认选中第一个有效项 "new"

    def get_field_value(self, field_name, value_type=str, default_value=None):
        """安全地从控件获取值并进行类型转换。"""
        if default_value is None:
            default_value = value_type()

        widget = self.inputs.get(field_name)
        if not widget: return default_value

        text = ""
        if isinstance(widget, QLineEdit):
            text = widget.text()
        elif isinstance(widget, QComboBox):
            # 如果是 dataStatus 且其复选框被勾选（或索引无效），则跳过取值
            if field_name == "dataStatus" and (self.data_status_checkbox.isChecked() or widget.currentIndex() == -1):
                return default_value
            text = widget.currentText() # 使用文本值进行转换

        if not text: return default_value
        try:
            return value_type(text)
        except (ValueError, KeyError):
            self.log_message(f"警告: 字段 '{field_name}' 的值 '{text}' 无效。使用默认值。")
            return default_value

    def send_data(self):
        """
        核心函数：收集UI数据，构建protobuf消息，并调用Kafka生产者发送。
        """
        try:
            target_list = target_pb2.TargetProtoList()
            target = target_list.list.add()

            # --- 填充 Protobuf 消息 ---
            target.id = self.get_field_value("id", int, 0)
            target.lastTm = int(time.time()) # 总是使用当前时间戳
            
            target.sost = self.inputs['sost'].currentData()
            target.eTargetType = self.inputs['eTargetType'].currentData()

            # 处理数据状态，仅当复选框未勾选且有有效选择时才赋值
            if not self.data_status_checkbox.isChecked() and self.inputs['dataStatus'].currentIndex() != -1:
                target.dataStatus = self.inputs['dataStatus'].currentData()
            
            pos_info = target.pos
            pos_info.id = target.id
            pos_info.mmsi = self.get_field_value("mmsi", int, 0)
            pos_info.vesselName = self.get_field_value("vesselName")
            pos_info.speed = self.get_field_value("speed", float, 0.0)
            pos_info.course = self.get_field_value("course", float, 0.0)
            pos_info.len = self.get_field_value("len", int, 0)
            pos_info.shiptype = self.inputs['shiptype'].currentData()
            
            geo_ptn = pos_info.geoPtn
            geo_ptn.longitude = self.get_field_value("longitude", float, 0.0)
            geo_ptn.latitude = self.get_field_value("latitude", float, 0.0)

            # 根据文本框内容添加 source
            if self.inputs["radarSource"].text():
                source = target.sources.add()
                source.provider = "雷达"
                source.type = "RADAR"
                source.ids.append(self.inputs["radarSource"].text())
            if self.inputs["aisSource"].text():
                source = target.sources.add()
                source.provider = "AIS"
                source.type = "AIS"
                source.ids.append(self.inputs["aisSource"].text())
            if self.inputs["bdSource"].text():
                source = target.sources.add()
                source.provider = "北斗"
                source.type = "BEIDOU"
                source.ids.append(self.inputs["bdSource"].text())

            self.log_message("构造的消息内容:\n" + str(target).strip())

            pb_data = target_list.SerializeToString()
            
            topic = self.config['kafka']['topic']
            self.kafka_producer.send_message(topic, pb_data)

        except Exception as e:
            self.log_message(f"创建或发送消息时发生严重错误: {e}")

    def log_message(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry = f"[{timestamp}] {message}"
        if hasattr(self, 'log_display'):
            self.log_display.append(log_entry)
        print(log_entry)

    def closeEvent(self, event):
        self.kafka_producer.close()
        event.accept()