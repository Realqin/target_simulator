# -*- coding: utf-8 -*-

import sys
import time
import re
import random
import json
import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGridLayout, QGroupBox, QTextEdit, QSpacerItem, QSizePolicy,
    QComboBox, QCheckBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QGraphicsView, QGraphicsScene, QDateTimeEdit, QGraphicsEllipseItem, QApplication,
    QRadioButton, QMessageBox, QButtonGroup
)
from PyQt5.QtCore import pyqtSlot, QTimer, Qt, QDateTime
from PyQt5.QtGui import QIcon, QCursor, QPen, QBrush, QColor, QPainter, QPainterPath

import zlib
import binascii
from kafka_producer import KProducer
import target_pb2
from database import Database
from location_calculator import LocationCalculator


class ZoomableView(QGraphicsView):
    """
    一个支持鼠标滚轮缩放和拖拽平移的QGraphicsView子类。
    """
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event):
        """重写滚轮事件以实现缩放"""
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        # 保存鼠标指向的场景坐标
        old_pos = self.mapToScene(event.pos())

        # 根据滚轮方向进行缩放
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

        # 获取缩放后的新场景坐标
        new_pos = self.mapToScene(event.pos())

        # 将场景移动回原来的鼠标指向位置，实现围绕鼠标指针缩放
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())


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
        self.trajectory_data = {} # 用于存储查到的轨迹数据
        self.playback_timer = QTimer(self) # 回放专用定时器
        self.playback_timer.timeout.connect(self.send_playback_data)
        self.playback_targets = []
        self.current_playback_index = 0

        # 新增：位置计算器实例
        self.location_calculator = None

        # 创建一个定时器，用于周期性地发送数据
        self.sending_timer = QTimer(self)
        self.sending_timer.timeout.connect(self.send_realtime_target_data)

        # 目标关联计时器
        self.association_timer = QTimer(self)
        self.association_timer.timeout.connect(self.update_association_timer)
        self.association_seconds = 0
        # 新增：目标关联状态
        self.association_state = "stopped"  # "sending", "paused", "terminated_associated", "stopped"
        self.keep_trend_combo = None # UI控件将在init_ui中创建

        # 模拟计算计时器
        self.simulation_timer = QTimer(self)
        self.simulation_timer.timeout.connect(self.update_simulation)

        # 为静态信息页签创建独立的状态
        self.static_inputs = {}
        self.static_sending_timer = QTimer(self)
        self.static_sending_timer.timeout.connect(self.send_static_data)
        self.static_paste_input = None
        self.static_frequency_input = None
        self.static_start_pause_btn = None
        self.static_terminate_btn = None
        self.static_data_status_checkbox = None
        self.static_log_group = None
        self.static_log_display = None

        # 新增：用于控制默认模式下首次发送状态的标志
        self.is_first_send = True

        # 定义必填字段和样式
        self.required_fields = ["course", "speed", "longitude", "latitude", "len"]
        self.invalid_style = "border: 1.5px solid red; border-radius: 4px;"
        self.default_lineedit_style = ""
        self.load_and_extract_styles()

        # 初始化UI界面
        self.init_ui()
        
        # 初始化Kafka生产者，并将UI的日志函数作为回调传递进去
        # 注意: Kafka连接日志等全局信息将显示在主（实时）日志窗口
        self.kafka_producer = KProducer(
            bootstrap_servers=self.config['kafka']['bootstrap_servers'],
            log_callback=self.log_message
        )
        
        # 初始化数据库连接
        try:
            self.db = Database(self.config.get('starrocks'))
            if not self.db.connect():
                self.log_message("错误: 应用启动时数据库连接失败。")
        except ValueError as e:
            self.log_message(f"错误: {e}")
            self.db = None

    def load_and_extract_styles(self):
        """加载QSS文件并提取QLineEdit的默认样式"""
        try:
            with open('style.qss', 'r', encoding='utf-8') as f:
                stylesheet = f.read()
                # 应用全局样式
                QApplication.instance().setStyleSheet(stylesheet)
                
                # 简单提取QLineEdit的样式
                # 注意：这是一个简化的解析，对于复杂的QSS可能不完全准确
                match = re.search(r'QLineEdit\s*{(.*?)}', stylesheet, re.DOTALL)
                if match:
                    self.default_lineedit_style = match.group(1).strip()
        except FileNotFoundError:
            self.log_message("警告: 'style.qss' 未找到，无法加载自定义样式。")
        except Exception as e:
            self.log_message(f"加载样式时出错: {e}")

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
            "kafka": {
                "bootstrap_servers": "localhost:9092", 
                "topic": "fusion_target_topic",
                "ais_static_topic": "ais_static_topic"
            },
            "starrocks": {
                "host": "localhost", "port": 9030, "user": "root", "password": "", "database": "ods"
            },
            "ui_options": {
                "eTargetType": {"OTHERS": 14}, "shiptype": {"其他": 99},
                "sost": {"正常": 1}, "dataStatus": {"new": 0, "update": 1, "delete": 2},
                "province": {"未选择": 0}
            },
            "random_generation": {
                "id": {"prefix": "11", "length": 20},
                "mmsi": {"prefix": "", "length": 9},
                "bds": {"prefix": "", "length": 9}
            }
        }

    def init_ui(self):
        """
        初始化和构建整个用户界面,现在使用QTabWidget。
        """
        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        self.setLayout(main_layout)

        # --- 创建Tab控件 ---
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # --- 创建三个标签页 ---
        self.realtime_tab = QWidget()
        self.static_info_tab = QWidget()
        self.playback_tab = QWidget()

        self.tab_widget.addTab(self.realtime_tab, "实时目标")
        self.tab_widget.addTab(self.static_info_tab, "静态信息")
        self.tab_widget.addTab(self.playback_tab, "回放目标")

        # --- 配置每个标签页的布局 ---
        self.setup_realtime_tab()
        self.setup_static_info_tab()
        self.setup_playback_tab()

        # --- 设置光标样式 ---
        self.set_cursors()

    def setup_realtime_tab(self):
        """配置“实时目标”标签页的UI内容"""
        tab_layout = QHBoxLayout(self.realtime_tab)
        
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
        # 创建并添加信息源模块
        left_v_layout.addWidget(self.create_source_input_group())
        # 创建并添加目标关联模块
        left_v_layout.addWidget(self.create_association_group())
        left_v_layout.addStretch(1)

        # --- 添加初始化按钮 ---
        init_button_layout = QHBoxLayout()
        self.save_init_btn = QPushButton("存为初始目标")
        self.load_init_btn = QPushButton("一键初始化")
        self.save_init_btn.clicked.connect(self.save_initial_target)
        self.load_init_btn.clicked.connect(self.load_initial_target)
        init_button_layout.addStretch(1)
        init_button_layout.addWidget(self.save_init_btn)
        init_button_layout.addWidget(self.load_init_btn)
        left_v_layout.addLayout(init_button_layout)

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

        # --- 组合左右布局到实时目标Tab ---
        tab_layout.addLayout(left_v_layout, stretch=3)
        tab_layout.addLayout(right_v_layout, stretch=1)

    def setup_static_info_tab(self):
        """配置“静态信息”标签页的UI内容"""
        tab_layout = QHBoxLayout(self.static_info_tab)
        
        # --- 左侧布局 (包含目标信息和AIS静态信息) ---
        left_v_layout = QVBoxLayout()

        # “快速识别”功能区
        paste_group = QGroupBox("快速识别")
        paste_layout = QHBoxLayout()
        self.static_paste_input = QTextEdit()
        self.static_paste_input.setPlaceholderText("在此粘贴内容（可多行），然后点击识别...")
        self.static_paste_input.setFixedHeight(80)
        recognize_btn = QPushButton("识别")
        recognize_btn.clicked.connect(self.recognize_and_fill_static)
        paste_layout.addWidget(self.static_paste_input)
        paste_layout.addWidget(recognize_btn)
        paste_group.setLayout(paste_layout)
        left_v_layout.addWidget(paste_group)

        # 创建并添加AIS静态信息模块
        left_v_layout.addWidget(self.create_ais_static_info_group_static())
        left_v_layout.addStretch(1)

        # --- 右侧布局 (包含控制操作和日志) ---
        right_v_layout = QVBoxLayout()
        right_v_layout.addWidget(self.create_control_group_static())
        
        # 为静态页签创建独立的日志区
        self.static_log_group = QGroupBox("发送日志 (静态)")
        self.static_log_group.setCheckable(True)
        self.static_log_group.setChecked(True)
        log_layout = QVBoxLayout()
        self.static_log_display = QTextEdit()
        self.static_log_display.setReadOnly(True)
        self.static_log_display.setMinimumHeight(200)
        self.static_log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout.addWidget(self.static_log_display)
        self.static_log_group.setLayout(log_layout)
        self.static_log_group.toggled.connect(self.static_log_display.setVisible)
        
        right_v_layout.addWidget(self.static_log_group, stretch=1)

        # --- 组合左右布局到静态信息Tab ---
        tab_layout.addLayout(left_v_layout, stretch=3)
        tab_layout.addLayout(right_v_layout, stretch=1)

    def setup_playback_tab(self):
        """配置“回放目标”标签页的UI内容"""
        main_layout = QVBoxLayout(self.playback_tab)

        # --- 上部模块：查询构建器 ---
        builder_group = QGroupBox("查询条件编辑器")
        builder_layout = QVBoxLayout()

        # 添加/删除行按钮
        builder_btn_layout = QHBoxLayout()
        add_row_btn = QPushButton("添加查询行")
        add_row_btn.clicked.connect(self.add_query_row)
        remove_row_btn = QPushButton("删除选中行")
        remove_row_btn.clicked.connect(self.remove_selected_query_row)
        builder_btn_layout.addWidget(add_row_btn)
        builder_btn_layout.addWidget(remove_row_btn)
        builder_btn_layout.addStretch()
        builder_layout.addLayout(builder_btn_layout)

        # 查询构建器表格
        self.query_builder_table = QTableWidget()
        self.query_builder_table.setColumnCount(5)
        self.query_builder_table.setHorizontalHeaderLabels(["MMSI", "ID", "省份", "开始时间", "结束时间"])
        self.query_builder_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        builder_layout.addWidget(self.query_builder_table)
        
        # 添加初始行
        self.add_query_row()

        builder_group.setLayout(builder_layout)
        main_layout.addWidget(builder_group)

        # --- 查询按钮 ---
        query_btn = QPushButton("批量查询")
        query_btn.clicked.connect(self.query_trajectory_data)
        main_layout.addWidget(query_btn)

        # --- 中部模块：结果列表 ---
        results_group = QGroupBox("查询结果")
        results_layout = QVBoxLayout()
        self.trajectory_table = QTableWidget()
        self.trajectory_table.setColumnCount(4)
        self.trajectory_table.setHorizontalHeaderLabels(["选择", "MMSI", "ID", "数据点数"])
        self.trajectory_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trajectory_table.setSelectionBehavior(QTableWidget.SelectRows)
        results_layout.addWidget(self.trajectory_table)
        results_group.setLayout(results_layout)
        main_layout.addWidget(results_group)

        # --- 下部模块：轨迹预览和发送控制 ---
        bottom_group = QGroupBox("轨迹预览与发送")
        bottom_layout = QHBoxLayout()

        self.trajectory_scene = QGraphicsScene()
        self.trajectory_preview = ZoomableView(self.trajectory_scene) # 使用新的ZoomableView
        
        bottom_layout.addWidget(self.trajectory_preview, stretch=4)

        send_control_layout = QVBoxLayout()
        send_btn = QPushButton("开始发送")
        send_btn.clicked.connect(self.start_playback)
        send_control_layout.addWidget(send_btn)
        send_control_layout.addStretch()
        bottom_layout.addLayout(send_control_layout, stretch=1)

        bottom_group.setLayout(bottom_layout)
        main_layout.addWidget(bottom_group)

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
        
        if hasattr(self, 'paste_input'):
            self.paste_input.setCursor(ibeam_cursor)
        if hasattr(self, 'log_display'):
            self.log_display.setCursor(ibeam_cursor)

    # ===================================================================
    # 实时目标 - UI 创建
    # ===================================================================

    def create_target_info_group(self):
        """创建“目标信息”模块的 GroupBox"""
        group_box = QGroupBox("目标信息（必填）")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # 初始化该模块的控件
        self.inputs = {
            "eTargetType": QComboBox(), "vesselName": QLineEdit(),
            "id": QLineEdit(), "mmsi": QLineEdit(),
            "bds": QLineEdit(), "shipName": QLineEdit(), "shiptype": QComboBox(),
            "course": QLineEdit(), "speed": QLineEdit(),
            "longitude": QLineEdit(), "latitude": QLineEdit(),
            "len": QLineEdit(), "maxLength": QLineEdit(),
            "sost": QComboBox(), "dataStatus": QComboBox(),
            "province": QComboBox()
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
        if self.config['ui_options'].get('province'):
            for province_item in self.config['ui_options']['province']:
                self.inputs['province'].addItem(province_item['name'], province_item['adapterId'])

        # --- 添加控件到网格布局 ---
        grid_layout.addWidget(QLabel("目标类型:"), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["eTargetType"], 0, 1)

        id_layout = QHBoxLayout()
        id_layout.addWidget(self.inputs["id"])
        random_id_btn = QPushButton("随机")
        random_id_btn.clicked.connect(lambda: self._generate_random_value("id", "ID", self.inputs, self.log_message))
        id_layout.addWidget(random_id_btn)
        grid_layout.addWidget(QLabel("ID:"), 0, 2, Qt.AlignRight)
        grid_layout.addLayout(id_layout, 0, 3)


        mmsi_layout = QHBoxLayout()
        mmsi_layout.addWidget(self.inputs["mmsi"])
        random_mmsi_btn = QPushButton("随机")
        random_mmsi_btn.clicked.connect(lambda: self._generate_random_value("mmsi", "MMSI", self.inputs, self.log_message))
        mmsi_layout.addWidget(random_mmsi_btn)
        grid_layout.addWidget(QLabel("MMSI:"), 1, 0, Qt.AlignRight)
        grid_layout.addLayout(mmsi_layout, 1, 1)

        grid_layout.addWidget(QLabel("AIS船名:"), 1, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["vesselName"], 1, 3)

        bds_layout = QHBoxLayout()
        bds_layout.addWidget(self.inputs["bds"])
        random_bds_btn = QPushButton("随机")
        random_bds_btn.clicked.connect(lambda: self._generate_random_value("bds", "BDS", self.inputs, self.log_message))
        bds_layout.addWidget(random_bds_btn)
        grid_layout.addWidget(QLabel("北斗号:"), 2, 0, Qt.AlignRight)
        grid_layout.addLayout(bds_layout, 2, 1)

        grid_layout.addWidget(QLabel("北斗船名:"), 2, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["shipName"], 2, 3)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["speed"])
        len_layout.addWidget(QLabel("节"))
        grid_layout.addWidget(QLabel("航速:"), 3, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 3, 1)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.inputs["course"])
        len_layout.addWidget(QLabel("度"))
        grid_layout.addWidget(QLabel("航向:"), 3, 2, Qt.AlignRight)
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

        grid_layout.addWidget(QLabel("船舶类型:"), 6, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["shiptype"], 6, 1)

        grid_layout.addWidget(QLabel("目标状态:"), 6, 2, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["sost"], 6, 3)

        grid_layout.addWidget(QLabel("省份:"), 7, 0, Qt.AlignRight)
        grid_layout.addWidget(self.inputs["province"], 7, 1)

        data_status_layout = QHBoxLayout()
        data_status_layout.addWidget(self.inputs["dataStatus"])
        self.data_status_checkbox = QCheckBox("默认")
        self.data_status_checkbox.toggled.connect(self.toggle_data_status_lock)
        data_status_layout.addWidget(self.data_status_checkbox)
        
        grid_layout.addWidget(QLabel("数据状态:"), 7, 2, Qt.AlignRight)
        grid_layout.addLayout(data_status_layout, 7, 3)

        for field_name in self.required_fields:
            widget = self.inputs.get(field_name)
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(lambda text, w=widget: self.clear_field_style(w))

        self.data_status_checkbox.setChecked(True)

        group_box.setLayout(grid_layout)
        return group_box

    def create_source_input_group(self):
        """创建信息源文本输入模块"""
        group_box = QGroupBox("信息源")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(3)

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

    def create_association_group(self):
        """创建目标关联模块"""
        group_box = QGroupBox("目标关联")
        main_layout = QHBoxLayout()
        main_layout.setSpacing(15)

        main_layout.addWidget(QLabel("保持运动趋势:"))
        self.keep_trend_combo = QComboBox()
        self.keep_trend_combo.addItems(["否", "是"])
        self.keep_trend_combo.setCurrentIndex(0)
        self.keep_trend_combo.currentIndexChanged.connect(self.on_keep_trend_changed)
        main_layout.addWidget(self.keep_trend_combo)

        main_layout.addSpacing(20)

        # 使用 QButtonGroup 来确保单选按钮的互斥性
        self.motion_button_group = QButtonGroup(self)

        self.association_options = {
            "constant": QRadioButton("匀速"),
            "decelerate": QRadioButton("均减速"),
            "accelerate": QRadioButton("均加速")
        }
        
        self.motion_button_group.addButton(self.association_options["constant"])
        self.motion_button_group.addButton(self.association_options["decelerate"])
        self.motion_button_group.addButton(self.association_options["accelerate"])
        
        self.association_options["constant"].setChecked(True)

        main_layout.addWidget(self.association_options["constant"])

        decelerate_widget = QWidget()
        decelerate_layout = QHBoxLayout(decelerate_widget)
        decelerate_layout.setContentsMargins(0, 0, 0, 0)
        decelerate_layout.setSpacing(5)
        decelerate_layout.addWidget(self.association_options["decelerate"])
        self.decelerate_input = QLineEdit("0.1")
        self.decelerate_input.setFixedWidth(50)
        decelerate_layout.addWidget(self.decelerate_input)
        decelerate_layout.addWidget(QLabel("节/分"))
        main_layout.addWidget(decelerate_widget)

        accelerate_widget = QWidget()
        accelerate_layout = QHBoxLayout(accelerate_widget)
        accelerate_layout.setContentsMargins(0, 0, 0, 0)
        accelerate_layout.setSpacing(5)
        accelerate_layout.addWidget(self.association_options["accelerate"])
        self.accelerate_input = QLineEdit("0.1")
        self.accelerate_input.setFixedWidth(50)
        accelerate_layout.addWidget(self.accelerate_input)
        accelerate_layout.addWidget(QLabel("节/分"))
        main_layout.addWidget(accelerate_widget)

        main_layout.addStretch()

        self.association_time_label = QLabel("时长: <font color='#3498db'>0</font> 秒")
        main_layout.addWidget(self.association_time_label)

        group_box.setLayout(main_layout)
        return group_box

    def create_control_group(self):
        """创建方向控制和操作按钮模块"""
        group_box = QGroupBox("控制与操作")
        v_layout = QVBoxLayout()

        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("发送频率（秒/次）"))
        self.frequency_input = QLineEdit("3")
        self.frequency_input.setFixedWidth(50)
        freq_layout.addWidget(self.frequency_input)
        freq_layout.addStretch()
        v_layout.addLayout(freq_layout)

        control_layout = QGridLayout()
        control_layout.setSpacing(5)
        up_btn, down_btn, left_btn, right_btn = QPushButton("↑"), QPushButton("↓"), QPushButton("←"), QPushButton("→")
        up_left_btn, up_right_btn, down_left_btn, down_right_btn = QPushButton("↖"), QPushButton("↗"), QPushButton("↙"), QPushButton("↘")
        
        up_btn.clicked.connect(lambda: self.update_course_from_button(0, self.inputs))
        down_btn.clicked.connect(lambda: self.update_course_from_button(180, self.inputs))
        left_btn.clicked.connect(lambda: self.update_course_from_button(270, self.inputs))
        right_btn.clicked.connect(lambda: self.update_course_from_button(90, self.inputs))
        up_left_btn.clicked.connect(lambda: self.update_course_from_button(315, self.inputs))
        up_right_btn.clicked.connect(lambda: self.update_course_from_button(45, self.inputs))
        down_left_btn.clicked.connect(lambda: self.update_course_from_button(225, self.inputs))
        down_right_btn.clicked.connect(lambda: self.update_course_from_button(135, self.inputs))

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
        control_layout.addWidget(up_left_btn, 0, 0)
        control_layout.addWidget(up_btn, 0, 1)
        control_layout.addWidget(up_right_btn, 0, 2)
        control_layout.addWidget(left_btn, 1, 0)
        control_layout.addWidget(right_btn, 1, 2)
        control_layout.addWidget(down_left_btn, 2, 0)
        control_layout.addWidget(down_btn, 2, 1)
        control_layout.addWidget(down_right_btn, 2, 2)
        v_layout.addLayout(control_layout)

        button_layout = QHBoxLayout()
        self.start_pause_btn = QPushButton("开始发送")
        self.start_pause_btn.clicked.connect(self.toggle_sending_state)
        self.terminate_btn = QPushButton("终止发送")
        self.terminate_btn.clicked.connect(self.terminate_sending)
        self.terminate_btn.setEnabled(False)
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_inputs)

        button_layout.addWidget(self.start_pause_btn)
        button_layout.addWidget(self.terminate_btn)
        button_layout.addWidget(clear_btn)
        v_layout.addLayout(button_layout)
        
        group_box.setLayout(v_layout)
        return group_box

    # ===================================================================
    # 静态信息 - UI 创建 (DUPLICATED)
    # ===================================================================

    def create_ais_static_info_group_static(self):
        group_box = QGroupBox("AIS静态信息")
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)


        self.static_inputs = {
            "mmsi": QLineEdit(), "vesselName": QLineEdit(),
            "deviceCategory": QComboBox(),"nationality": QLineEdit(),
            "imo": QLineEdit(), "callSign": QLineEdit(),
            "len": QLineEdit(),"shipWidth": QLineEdit(),
            "draught": QLineEdit(),
            "shiptype": QComboBox(), "destination": QLineEdit(),
            "eta": QDateTimeEdit(QDateTime.currentDateTime()),
        }

        for text, value in self.config['ui_options']['shiptype'].items():
            self.static_inputs['shiptype'].addItem(text, value)

        self.static_inputs["eta"].setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.static_inputs["eta"].setCalendarPopup(True)

        if 'deviceCategory' in self.config['ui_options']:
            for text, value in self.config['ui_options']['deviceCategory'].items():
                self.static_inputs['deviceCategory'].addItem(text, value)


        logger = lambda msg: self.log_message(msg, 'static')

        mmsi_layout = QHBoxLayout()
        mmsi_layout.addWidget(self.static_inputs["mmsi"])
        random_mmsi_btn = QPushButton("随机")
        random_mmsi_btn.clicked.connect(lambda: self._generate_random_value("mmsi", "MMSI", self.static_inputs, logger))
        mmsi_layout.addWidget(random_mmsi_btn)
        grid_layout.addWidget(QLabel("MMSI:"), 0, 0, Qt.AlignRight)
        grid_layout.addLayout(mmsi_layout, 0, 1)

        grid_layout.addWidget(QLabel("船名:"), 0, 2, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["vesselName"], 0, 3)

        grid_layout.addWidget(QLabel("设备分类:"), 1, 0, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["deviceCategory"], 1, 1)
        grid_layout.addWidget(QLabel("船籍:"), 1, 2, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["nationality"], 1, 3)

        grid_layout.addWidget(QLabel("IMO:"), 2, 0, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["imo"], 2, 1)
        grid_layout.addWidget(QLabel("呼号:"), 2, 2, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["callSign"], 2, 3)

        len_layout = QHBoxLayout()
        len_layout.addWidget(self.static_inputs["len"])
        len_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("船长:"), 3, 0, Qt.AlignRight)
        grid_layout.addLayout(len_layout, 3, 1)

        width_layout = QHBoxLayout()
        width_layout.addWidget(self.static_inputs["shipWidth"])
        width_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("船宽:"), 3, 2, Qt.AlignRight)
        grid_layout.addLayout(width_layout, 3, 3)

        draught_layout = QHBoxLayout()
        draught_layout.addWidget(self.static_inputs["draught"])
        draught_layout.addWidget(QLabel("米"))
        grid_layout.addWidget(QLabel("吃水:"), 4, 0, Qt.AlignRight)
        grid_layout.addLayout(draught_layout, 4, 1)


        grid_layout.addWidget(QLabel("船舶类型:"), 4, 2, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["shiptype"], 4, 3)

        grid_layout.addWidget(QLabel("预到时间:"), 5, 0, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["eta"], 5, 1)


        grid_layout.addWidget(QLabel("目的地:"), 5, 2, Qt.AlignRight)
        grid_layout.addWidget(self.static_inputs["destination"], 5, 3)

        group_box.setLayout(grid_layout)
        return group_box

    def create_control_group_static(self):
        group_box = QGroupBox("控制与操作")
        v_layout = QVBoxLayout()
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("发送频率（秒/次）"))
        self.static_frequency_input = QLineEdit("3")
        self.static_frequency_input.setFixedWidth(50)
        freq_layout.addWidget(self.static_frequency_input)
        freq_layout.addStretch()
        v_layout.addLayout(freq_layout)

        button_layout = QHBoxLayout()
        self.static_start_pause_btn = QPushButton("开始发送")
        self.static_start_pause_btn.clicked.connect(self.toggle_sending_state_static)
        self.static_terminate_btn = QPushButton("终止发送")
        self.static_terminate_btn.clicked.connect(self.terminate_sending_static)
        self.static_terminate_btn.setEnabled(False)
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_inputs_static)
        button_layout.addWidget(self.static_start_pause_btn)
        button_layout.addWidget(self.static_terminate_btn)
        button_layout.addWidget(clear_btn)
        v_layout.addLayout(button_layout)
        group_box.setLayout(v_layout)
        return group_box

    # ===================================================================
    # 通用及实时目标 - 逻辑
    # ===================================================================

    def _generate_random_value(self, field_key, field_name_for_log, inputs_dict, logger):
        """
        根据配置文件中的规则生成一个随机值。
        """
        try:
            config = self.config['random_generation'][field_key]
            prefix = config.get('prefix', '')
            length = config.get('length', 9)

            if length <= len(prefix):
                logger(f"错误: {field_name_for_log} 配置的总长度({length})必须大于前缀'{prefix}'的长度。")
                return

            random_len = length - len(prefix)
            random_part = ''.join([str(random.randint(1, 9)) for _ in range(random_len)])
            new_value = prefix + random_part
            
            inputs_dict[field_key].setText(new_value)
            logger(f"已生成随机{field_name_for_log}: {new_value}")

        except KeyError:
            logger(f"错误: 在配置文件中未找到 '{field_key}' 的随机生成规则。")
        except Exception as e:
            logger(f"生成随机{field_name_for_log}时出错: {e}")

    def update_course_from_button(self, angle, inputs_dict):
        inputs_dict["course"].setText(str(angle))

    @pyqtSlot()
    def recognize_and_fill(self):
        self._recognize_and_fill_generic(self.paste_input, self.inputs, self.log_message)

    @pyqtSlot()
    def clear_inputs(self):
        """清除所有输入和状态，恢复到默认。"""
        self.sending_timer.stop()
        self.association_timer.stop()
        self.simulation_timer.stop()

        self._clear_inputs_generic(self.paste_input, self.inputs, self.data_status_checkbox)
        for field_name in self.required_fields:
            widget = self.inputs.get(field_name)
            if widget:
                widget.setStyleSheet(self.default_lineedit_style)
        
        if self.keep_trend_combo:
            self.keep_trend_combo.setCurrentIndex(0)
        self.association_options["constant"].setChecked(True)
        self.association_seconds = 0
        self.update_association_timer_display()

        self.association_state = "stopped"
        self.location_calculator = None
        self.is_first_send = True
        self.start_pause_btn.setText("开始发送")
        self.terminate_btn.setEnabled(False)
        self.set_motion_fields_enabled(True)

        self.log_message("所有输入和状态已清除。")

    def validate_required_fields(self):
        """校验所有必填字段是否已填写。"""
        is_valid = True
        for field_name in self.required_fields:
            widget = self.inputs.get(field_name)
            if widget and isinstance(widget, QLineEdit):
                if not widget.text().strip():
                    widget.setStyleSheet(self.default_lineedit_style + self.invalid_style)
                    is_valid = False
                else:
                    widget.setStyleSheet(self.default_lineedit_style)
        
        if not is_valid:
            self.log_message("错误: 有必填项未填写，请检查红色高亮框。")
        return is_valid

    def clear_field_style(self, widget):
        """清除特定输入框的样式，恢复其默认样式。"""
        widget.setStyleSheet(self.default_lineedit_style)

    def set_motion_fields_enabled(self, enabled, lock_course=True):
        """启用或禁用与运动相关的输入字段"""
        for field in ["longitude", "latitude", "speed"]:
            self.inputs[field].setEnabled(enabled)
        if lock_course:
            self.inputs["course"].setEnabled(enabled)

    def _initialize_location_calculator(self):
        """从UI读取参数并初始化位置计算器"""
        try:
            start_lat = float(self.inputs['latitude'].text())
            start_lon = float(self.inputs['longitude'].text())
            speed = float(self.inputs['speed'].text())
            course = float(self.inputs['course'].text())
            self.location_calculator = LocationCalculator(start_lat, start_lon, speed, course)
            self.log_message("位置计算器已初始化。")
            return True
        except (ValueError, TypeError):
            self.log_message("错误: 无法初始化位置计算器。请确保经纬度、速度和航向为有效的数字。")
            return False

    def toggle_sending_state(self):
        """主状态机，处理“开始/暂停/继续”按钮的点击事件"""
        if not self.validate_required_fields():
            return

        if self.keep_trend_combo.currentText() == "是":
            self.handle_trend_sending()
        else:
            self.handle_simple_sending()

    def handle_simple_sending(self):
        """处理不保持运动趋势的发送逻辑（但仍然实时回填）"""
        if self.association_state != "sending":
            if not self._initialize_location_calculator():
                return
            try:
                interval_ms = int(float(self.frequency_input.text()) * 1000)
                if interval_ms <= 0: raise ValueError
            except (ValueError, TypeError):
                self.log_message("错误: 发送频率必须是一个大于0的数字。")
                return
            
            self.send_realtime_target_data()
            self.simulation_timer.start(1000) # 实时回填
            self.sending_timer.start(interval_ms)
            self.log_message(f"发送已开始，频率: {interval_ms/1000}s/次 (实时回填中)。")
            self.start_pause_btn.setText("暂停发送")
            self.terminate_btn.setEnabled(True)
            self.association_state = "sending"
        else:
            self.sending_timer.stop()
            self.simulation_timer.stop() # 暂停时停止回填
            self.log_message("发送已暂停，数据已停止回填。")
            self.start_pause_btn.setText("继续发送")
            self.association_state = "paused"

    def handle_trend_sending(self):
        """处理保持运动趋势的复杂状态逻辑"""
        state = self.association_state

        if state == "stopped":
            if not self._initialize_location_calculator():
                return
            self.send_realtime_target_data()
            self.simulation_timer.start(1000)
            self.sending_timer.start(int(float(self.frequency_input.text()) * 1000))
            self.association_state = "sending"
            self.start_pause_btn.setText("暂停发送")
            self.terminate_btn.setEnabled(True)
            self.log_message("已开始发送，并实时计算位移。")

        elif state == "sending":
            self.sending_timer.stop()
            self.simulation_timer.stop()
            self.association_timer.start(1000)
            self.association_state = "paused"
            self.start_pause_btn.setText("继续发送")
            self.log_message("发送已暂停，只计时，不回填数据。")

        elif state == "paused":
            self.association_timer.stop()
            self.log_message(f"暂停了 {self.association_seconds} 秒。")

            try:
                # 1. 立即从UI读取当前所有相关值
                start_lat = float(self.inputs['latitude'].text())
                start_lon = float(self.inputs['longitude'].text())
                current_speed = float(self.inputs['speed'].text())
                current_course = float(self.inputs['course'].text())
                duration_sec = self.association_seconds

                # 2. 使用当前UI值重新创建一个新的计算器实例，以确保起点正确
                self.location_calculator = LocationCalculator(start_lat, start_lon, current_speed, current_course)

                # 3. 计算新的最终航速
                new_speed = current_speed
                if self.association_options["decelerate"].isChecked():
                    rate_per_min = float(self.decelerate_input.text())
                    rate_per_sec = rate_per_min / 60.0
                    new_speed -= rate_per_sec * duration_sec
                    new_speed = max(0, new_speed)
                elif self.association_options["accelerate"].isChecked():
                    rate_per_min = float(self.accelerate_input.text())
                    rate_per_sec = rate_per_min / 60.0
                    new_speed += rate_per_sec * duration_sec
                
                # 4. 使用平均速度计算位移
                avg_speed = (current_speed + new_speed) / 2.0
                self.location_calculator.update_params(speed_knots=avg_speed) 
                new_lat, new_lon = self.location_calculator.calculate_next_point(duration_sec)
                
                # 5. 重要: 将计算器的速度更新为最终速度，以供后续模拟使用
                self.location_calculator.update_params(speed_knots=new_speed)

                # 6. 将计算出的最终航速和新位置回填到UI
                self.inputs['speed'].setText(f"{new_speed:.2f}")
                self.inputs['latitude'].setText(f"{new_lat:.8f}")
                self.inputs['longitude'].setText(f"{new_lon:.8f}")
                self.log_message(f"航速更新至 {new_speed:.2f} 节。位置更新至: {new_lat:.6f}, {new_lon:.6f}")

            except (ValueError, TypeError) as e:
                self.log_message(f"错误: 恢复发送时更新状态失败 - {e}")
                # 即使计算失败，也要尝试恢复计时器以避免卡住
                self.association_state = "sending"
                self.start_pause_btn.setText("暂停发送")
                self.simulation_timer.start(1000)
                self.sending_timer.start(int(float(self.frequency_input.text()) * 1000))
                return

            # 7. 使用回填后的新数据发送消息
            self.send_realtime_target_data()
            
            # 8. 恢复正常模拟和发送
            self.simulation_timer.start(1000)
            self.sending_timer.start(int(float(self.frequency_input.text()) * 1000))
            self.association_seconds = 0
            self.update_association_timer_display()
            self.association_state = "sending"
            self.start_pause_btn.setText("暂停发送")
            self.log_message("已继续发送。")

        elif state == "terminated_associated":
            self.association_timer.stop()
            self.log_message(f"终止后等待了 {self.association_seconds} 秒。")
            
            try:
                # 1. 从UI读取当前值，包括可能已修改的航向
                start_lat = float(self.inputs['latitude'].text())
                start_lon = float(self.inputs['longitude'].text())
                current_speed = float(self.inputs['speed'].text())
                current_course = float(self.inputs['course'].text()) # 读取最新的航向
                duration_sec = self.association_seconds

                # 2. 使用这些值重新创建计算器
                self.location_calculator = LocationCalculator(start_lat, start_lon, current_speed, current_course)

                # 3. 计算新航速
                new_speed = current_speed
                if self.association_options["decelerate"].isChecked():
                    rate_per_min = float(self.decelerate_input.text())
                    rate_per_sec = rate_per_min / 60.0
                    new_speed -= rate_per_sec * duration_sec
                    new_speed = max(0, new_speed)
                elif self.association_options["accelerate"].isChecked():
                    rate_per_min = float(self.accelerate_input.text())
                    rate_per_sec = rate_per_min / 60.0
                    new_speed += rate_per_sec * duration_sec
                
                # 4. 计算新位置
                avg_speed = (current_speed + new_speed) / 2.0
                self.location_calculator.update_params(speed_knots=avg_speed)
                new_lat, new_lon = self.location_calculator.calculate_next_point(duration_sec)
                self.location_calculator.update_params(speed_knots=new_speed)

                # 5. 回填UI
                self.inputs['speed'].setText(f"{new_speed:.2f}")
                self.inputs['latitude'].setText(f"{new_lat:.8f}")
                self.inputs['longitude'].setText(f"{new_lon:.8f}")
                self.log_message(f"根据等待时长和当前输入，状态已更新。")

            except (ValueError, TypeError) as e:
                self.log_message(f"错误: 从关联状态恢复时计算失败 - {e}")

            # 6. 解除所有锁定，恢复正常发送
            self.set_motion_fields_enabled(True)
            self.send_realtime_target_data()
            self.simulation_timer.start(1000)
            self.sending_timer.start(int(float(self.frequency_input.text()) * 1000))
            self.association_seconds = 0
            self.update_association_timer_display()
            self.association_state = "sending"
            self.start_pause_btn.setText("暂停发送")
            self.terminate_btn.setEnabled(True)
            self.log_message("已从关联状态恢复发送。")

    def terminate_sending(self):
        """处理“终止发送”按钮的点击事件"""
        self.sending_timer.stop()
        self.simulation_timer.stop()
        self.association_timer.stop()
        self.is_first_send = True

        self.log_message("发送终止消息 (delete)...")
        selected_class = self.inputs['eTargetType'].currentText()
        self._send_protobuf_data(selected_class, override_status=3)
        self.log_message("发送已终止。")

        if self.keep_trend_combo.currentText() == "是":
            reply = QMessageBox.question(self, '确认操作', 
                                           "下一个目标是否需要关联？",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.association_state = "terminated_associated"
                self.set_motion_fields_enabled(False, lock_course=False) # 只锁定部分字段
                self.association_timer.start(1000)
                self.start_pause_btn.setText("开始发送")
                self.terminate_btn.setEnabled(False)
                self.log_message("进入关联等待状态，航速和位置已锁定，航向可修改。开始计时。")
                return

        self.association_state = "stopped"
        self.location_calculator = None
        self.association_seconds = 0
        self.update_association_timer_display()
        self.start_pause_btn.setText("开始发送")
        self.terminate_btn.setEnabled(False)
        self.set_motion_fields_enabled(True)

    @pyqtSlot(int)
    def on_keep_trend_changed(self, index):
        """Handles changes in the 'Keep Motion Trend' dropdown."""
        is_trend_keeping = self.keep_trend_combo.itemText(index) == "是"

        if not is_trend_keeping:
            # Switched to "No"
            self.log_message("保持运动趋势已关闭。关联计时器已重置。")
            self.association_timer.stop()
            self.association_seconds = 0
            self.update_association_timer_display()
            # Also reset the state if it was in a waiting-for-association state
            if self.association_state == "terminated_associated":
                self.association_state = "stopped"
                self.start_pause_btn.setText("开始发送")
                self.terminate_btn.setEnabled(False)
                self.set_motion_fields_enabled(True)
        else:
            # Switched to "Yes"
            self.log_message("保持运动趋势已开启。")

    def update_association_timer(self):
        """更新目标关联时长"""
        self.association_seconds += 1
        self.update_association_timer_display()

    def update_association_timer_display(self):
        """更新时长标签的显示"""
        self.association_time_label.setText(f"时长: <font color='#3498db'>{self.association_seconds}</font> 秒")

    def update_simulation(self):
        """根据关联模式，实时计算并更新UI上的速度和位置"""
        if not self.location_calculator:
            self.simulation_timer.stop()
            return

        try:
            current_speed = float(self.inputs['speed'].text())
            current_course = float(self.inputs['course'].text())
            self.location_calculator.update_params(speed_knots=current_speed, course_degrees=current_course)

            new_speed = current_speed
            if self.association_options["decelerate"].isChecked():
                rate_per_min = float(self.decelerate_input.text())
                rate_per_sec = rate_per_min / 60.0
                new_speed -= rate_per_sec
                new_speed = max(0, new_speed)
            elif self.association_options["accelerate"].isChecked():
                rate_per_min = float(self.accelerate_input.text())
                rate_per_sec = rate_per_min / 60.0
                new_speed += rate_per_sec
            
            self.location_calculator.update_params(speed_knots=new_speed, course_degrees=current_course)
            
            new_lat, new_lon = self.location_calculator.calculate_next_point(1.0)
            
            self.inputs['speed'].setText(f"{new_speed:.2f}")
            self.inputs['latitude'].setText(f"{new_lat:.8f}")
            self.inputs['longitude'].setText(f"{new_lon:.8f}")

        except (ValueError, TypeError) as e:
            self.log_message(f"错误: 模拟计算失败 - {e}")
            self.simulation_timer.stop()

    def toggle_data_status_lock(self, is_checked):
        self._toggle_data_status_lock_generic(is_checked, self.inputs["dataStatus"])

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
            if field_name == "dataStatus" and (self.data_status_checkbox.isChecked() or widget.currentIndex() == -1):
                return default_value
            text = widget.currentText()

        if not text: return default_value
        try:
            return value_type(text)
        except (ValueError, KeyError):
            self.log_message(f"警告: 字段 '{field_name}' 的值 '{text}' 无效。使用默认值。")
            return default_value

    def send_one_time_static_info(self):
        """只发送一次AIS静态信息（用于实时目标页签）。"""
        try:
            mmsi = self.get_field_value("mmsi")
            if mmsi:
                ais_info = {
                    "MMSI": mmsi, "Vessel Name": self.get_field_value("vesselName")
                }
                json_payload = {"AisExts": [ais_info]}
                json_data = json.dumps(json_payload, ensure_ascii=False, indent=2)
                self.log_message("构造的单次静态 JSON 消息内容:\n" + json_data)
                static_topic = self.config['kafka'].get('ais_static_topic')
                if static_topic:
                    self.kafka_producer.send_message(static_topic, json_data.encode('utf-8'))
                    self.log_message(f"已向 Topic '{static_topic}' 发送单次静态 JSON 消息。")
                else:
                    self.log_message("警告: 在 config.json 中未找到 'ais_static_topic'。")
            else:
                self.log_message("信息: MMSI为空，跳过发送单次静态信息JSON。")
        except Exception as e:
            self.log_message(f"发送单次静态信息过程中发生错误: {e}")

    def send_realtime_target_data(self):
        """
        核心调度函数：读取UI上的当前值，并根据目标类型调用相应的发送函数。
        """
        try:
            selected_class = self.inputs['eTargetType'].currentText()

            if selected_class == "BDS":
                self._send_bds_json_data(selected_class)
            elif selected_class == "RADAR":
                self._send_protobuf_data(selected_class)
            else:
                self._send_protobuf_data(selected_class)
                if "AIS" in selected_class:
                    self._send_ais_static_data()
                if "BDS" in selected_class:
                    self._send_bds_json_data(selected_class)
            
            if self.is_first_send:
                self.is_first_send = False

        except Exception as e:
            self.log_message(f"发送过程中发生严重错误: {e}")

    def _send_protobuf_data(self, selected_class, override_status=None):
        """构建并发送Protobuf消息到unionTargetPb。"""
        target_list = target_pb2.TargetProtoList()
        target = target_list.list.add()

        selected_state = self.inputs['sost'].currentData()
        eTargetType_val = 0
        if 'eTargetType_mapping' in self.config['ui_options']:
            for rule in self.config['ui_options']['eTargetType_mapping']:
                if rule['ui_class'] == selected_class and rule['ui_state'] == selected_state:
                    eTargetType_val = rule['eTargetType']
                    break
        
        target.id = self.get_field_value("id", int, 0)
        if (target.id == 0) & (selected_class != "BDS"):
            self._generate_random_value("id", "ID", self.inputs, self.log_message)
            target.id = self.get_field_value("id", int, 0)
        target.lastTm = int(time.time() * 1000)
        target.sost = self.inputs['sost'].currentData()
        target.eTargetType = eTargetType_val
        if self.inputs['province'].currentIndex() > 0:
            target.adapterId = self.inputs['province'].currentData()

        if override_status is not None:
            target.status = override_status
        elif self.data_status_checkbox.isChecked():
            target.status = 1 if self.is_first_send else 2
        else:
            target.status = self.inputs['dataStatus'].currentData()

        pos_info = target.pos
        pos_info.id = target.id
        pos_info.mmsi = self.get_field_value("mmsi", int, 0)
        if (pos_info.mmsi == 0) & ("AIS" in selected_class):
            self._generate_random_value("mmsi", "MMSI", self.inputs, self.log_message)
            pos_info.mmsi = self.get_field_value("mmsi", int, 0)
        pos_info.vesselName = self.get_field_value("vesselName")
        pos_info.speed = self.get_field_value("speed", float, 0.0)
        pos_info.course = self.get_field_value("course", float, 0.0)
        pos_info.len = self.get_field_value("len", int, 0)
        pos_info.shiptype = self.inputs['shiptype'].currentData()
        pos_info.geoPtn.longitude = self.get_field_value("longitude", float, 0.0)
        pos_info.geoPtn.latitude = self.get_field_value("latitude", float, 0.0)
        target.maxLen = pos_info.len
        pos_info.displayId = int(target.id) % 100000
        if "RADAR" in selected_class:
            pos_info.id_r = 18
        pos_info.state = target.sost
        pos_info.quality = 100
        pos_info.period = 10
        pos_info.heading = pos_info.course
        pos_info.s_class = self.inputs['eTargetType'].currentData()
        pos_info.m_mmsi = pos_info.mmsi
        pos_info.aidtype = 1
        target.adapterId = self.inputs['province'].currentData()

        radar_source_text = self.inputs["radarSource"].text().strip()
        if radar_source_text:
            source = target.sources.add()
            source.provider = "HLX"
            source.type = "RADAR"
            radar_ids = [id.strip() for id in radar_source_text.split(',') if id.strip()]
            for radar_id in radar_ids:
                source.ids.append(radar_id)
                info = target.vecFusionedTargetInfo.add()
                info.uiStationType = 82
                info.ullPosUpdateTime = target.lastTm
                info.ullUniqueId = target.id
                info.uiStationId = int(radar_id)

        ais_source_text = self.inputs["aisSource"].text().strip()
        if ais_source_text:
            source = target.sources.add()
            source.provider = "HLX"
            source.type = "AIS"
            ais_ids = [id.strip() for id in ais_source_text.split(',') if id.strip()]
            for ais_id in ais_ids:
                source.ids.append(ais_id)
                info = target.vecFusionedTargetInfo.add()
                info.uiStationType = 65
                info.ullPosUpdateTime = target.lastTm
                info.ullUniqueId = target.id
                info.uiStationId = int(ais_id)

        self.log_message("构造的 Protobuf 消息内容:\n" + str(target).strip())
        pb_data = target_list.SerializeToString()
        topic = self.config['kafka']['topic']
        self.kafka_producer.send_message(topic, pb_data)
        self.log_message(f"已向 Topic '{topic}' 发送 Protobuf 消息。")

    def _send_ais_static_data(self):
        """构建并发送AIS静态信息JSON。"""
        mmsi = self.get_field_value("mmsi")
        if not mmsi:
            self.log_message("信息: MMSI为空，跳过发送AIS静态信息。")
            return
        
        static_topic = self.config['kafka'].get('ais_static_topic')
        if not static_topic:
            self.log_message("警告: 在 config.json 中未找到 'ais_static_topic'。")
            return

        ais_info = {"MMSI": mmsi, "Vessel Name": self.get_field_value("vesselName")}
        json_payload = {"AisExts": [ais_info]}
        json_data = json.dumps(json_payload, ensure_ascii=False, indent=2)
        
        self.kafka_producer.send_message(static_topic, json_data.encode('utf-8'))
        self.log_message(f"已向 Topic '{static_topic}' 发送AIS静态JSON消息。")

    def _send_bds_json_data(self, selected_class):
        """构建并发送BDS位置JSON。"""
        bds_topic = self.config['kafka'].get('bds_topic')
        if not bds_topic:
            self.log_message("警告: 在 config.json 中未找到 'bds_topic'。")
            return

        province_name_en = "Unknown"
        selected_adapter_id = self.inputs['province'].currentData()
        province_list = self.config['ui_options'].get('province', [])
        for province_item in province_list:
            if province_item['adapterId'] == selected_adapter_id:
                province_name_en = province_item['name_en']
                break

        terminal= self.get_field_value("bds", float, 0.0)
        if terminal ==0:
            self._generate_random_value("bds", "BDS", self.inputs, self.log_message)
            terminal = self.get_field_value("bds", float, 0.0)

        bds_payload = {
            "altitude": 0, "communicate": 0,
            "course": self.get_field_value("course", float, 0.0),
            "disassemble": 0, "distress": 0, "jobType": "",
            "latitude": self.get_field_value("latitude", float, 0.0),
            "longitude": self.get_field_value("longitude", float, 0.0),
            "online": 0, "power": 0, "provider": self.get_field_value("bdSource", float, 0.0),
            "province": province_name_en,
            "shipLength": self.get_field_value("len", float, 0.0),
            "shipName": self.get_field_value("shipName"),
            "source": 2, "speed": self.get_field_value("speed", float, 0.0),
            "status": 0, "terminal":self.get_field_value("bds", float, 0.0),
            "tilt": 0, "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }
        
        json_data = json.dumps(bds_payload, ensure_ascii=False, indent=2)
        self.kafka_producer.send_message(bds_topic, json_data.encode('utf-8'))
        self.log_message(f"已向 Topic '{bds_topic}' 发送 BDS JSON 消息。")
        if selected_class == "BDS":
            self.log_message("构造的 BDS JSON 消息内容:\n" + json_data)

    # ===================================================================
    # 静态信息 - 逻辑 (DUPLICATED)
    # ===================================================================

    @pyqtSlot()
    def recognize_and_fill_static(self):
        logger = lambda msg: self.log_message(msg, 'static')
        self._recognize_and_fill_generic(self.static_paste_input, self.static_inputs, logger)

    @pyqtSlot()
    def clear_inputs_static(self):
        self._clear_inputs_generic(self.static_paste_input, self.static_inputs, None)
        self.log_message("所有输入已清除 (静态)。", "static")

    def toggle_sending_state_static(self):
        logger = lambda msg: self.log_message(msg, 'static')
        self._toggle_sending_state_generic(self.static_sending_timer, self.static_frequency_input, self.static_start_pause_btn, self.static_terminate_btn, self.send_static_data, logger)

    def terminate_sending_static(self):
        logger = lambda msg: self.log_message(msg, 'static')
        self._terminate_sending_generic(self.static_sending_timer, self.static_frequency_input, self.static_start_pause_btn, self.static_terminate_btn, logger)

    def toggle_data_status_lock_static(self, is_checked):
        self._toggle_data_status_lock_generic(is_checked, self.static_inputs["dataStatus"])

    def send_static_data(self):
        """
        核心函数：收集静态信息UI数据，构建并发送AIS静态信息JSON。
        """
        try:
            def get_static_val(field_name, value_type=str, default_value=None):
                if default_value is None:
                    default_value = value_type()
                widget = self.static_inputs.get(field_name)
                if not widget:
                    return default_value
                
                text = ""
                if isinstance(widget, QLineEdit):
                    text = widget.text()
                elif isinstance(widget, QComboBox):
                    if widget.currentIndex() == -1:
                        return default_value
                    text = widget.currentText()
                elif isinstance(widget, QDateTimeEdit):
                    text = widget.dateTime().toString("yyyy-MM-dd HH:mm:ss")

                if not text: return default_value
                try:
                    return value_type(text)
                except (ValueError, KeyError):
                    self.log_message(f"警告: 字段 '{field_name}' 的值 '{text}' 无效。使用默认值。", "static")
                    return default_value

            bow = random.randint(0, get_static_val("len", int, 0))
            stern =get_static_val("len", int, 0) -bow
            port = random.randint(0, get_static_val("shipWidth", int, 0))
            starboard =get_static_val("shipWidth", int, 0) -port

            mmsi_val = get_static_val("mmsi")
            if mmsi_val:
                ais_info = {
                    "MMSI": mmsi_val,
                    "Vessel Name": get_static_val("vesselName"),
                    "Ship Class": get_static_val("deviceCategory"),
                    "Nationality": get_static_val("nationality"),
                    "IMO": get_static_val("imo"),
                    "Call_Sign": get_static_val("callSign"),
                    "LengthRealTime": str(get_static_val("len", float, 0.0)),
                    "Length": str(get_static_val("len", float, 0.0)),
                    "Wide": str(get_static_val("shipWidth",float, 0.0)),
                    "Draught": get_static_val("draught"),
                    "Ship Type": self.static_inputs["shiptype"].currentText(),
                    "Destination": get_static_val("destination"),
                    "etaTime": get_static_val("eta"),
                    "A (to Bow)": str(bow),
                    "B (to Stern)": str(stern),
                    "C (to Port)": str(port),
                    "C (to Starboard)": str(starboard),
                    "extInfo": None
                }
                json_payload = {"AisExts": [ais_info]}
                json_data = json.dumps(json_payload, ensure_ascii=False, indent=2)
                self.log_message("(静态) 构造的 JSON 消息内容:\n" + json_data, "static")
                static_topic = self.config['kafka'].get('ais_static_topic')
                if static_topic:
                    self.kafka_producer.send_message(static_topic, json_data.encode('utf-8'))
                    self.log_message(f"(静态) 已向 Topic '{static_topic}' 发送 JSON 消息。", "static")
                else:
                    self.log_message("警告: 在 config.json 中未找到 'ais_static_topic'。", "static")
            else:
                self.log_message("信息: (静态) MMSI为空，跳过发送。", "static")

        except Exception as e:
            self.log_message(f"发送静态信息过程中发生严重错误: {e}", "static")

    # ===================================================================
    # 通用逻辑实现
    # ===================================================================

    def _recognize_and_fill_generic(self, paste_widget, inputs_dict, logger):
        content = paste_widget.toPlainText()
        if not content: return
        label_map = { "目标类型": "eTargetType", "AIS船名": "vesselName", "ID": "id", "MMSI": "mmsi", "北斗号": "bds", "北斗船名": "shipName", "船舶类型": "shiptype", "航向": "course", "航速": "speed", "经度": "longitude", "纬度": "latitude", "船长": "len", "最大船长": "maxLength", "目标状态": "sost", "数据状态": "dataStatus", "设备分类": "deviceCategory", "船籍": "nationality", "IMO": "imo", "呼号": "callSign", "船宽": "shipWidth", "吃水": "draught", "艏向": "heading", "预到时间": "eta", "目的地": "destination", "AIS信息源":"aisSource","北斗信息源":"bdSource","雷达信息源":"radarSource","省份":"province" }
        numeric_fields = { "course", "speed", "longitude", "latitude", "len", "maxLength", "shipWidth", "draught", "heading" }
        filled_fields = []
        for line in content.splitlines():
            for label, field_name in label_map.items():
                if label in line:
                    value_part = line.split(label, 1)[-1].lstrip(' :：').strip()
                    raw_value = re.search(r'[-+]?\d*\.?\d+', value_part).group(0) if field_name in numeric_fields and re.search(r'[-+]?\d*\.?\d+', value_part) else (value_part.split()[0] if value_part else "")
                    widget = inputs_dict.get(field_name)
                    if widget:
                        if isinstance(widget, QLineEdit): widget.setText(raw_value)
                        elif isinstance(widget, QComboBox):
                            index = widget.findText(raw_value, Qt.MatchContains)
                            if index != -1: widget.setCurrentIndex(index)
                        elif isinstance(widget, QDateTimeEdit):
                            try:
                                dt = QDateTime.fromString(raw_value, "yyyy-MM-dd HH:mm:ss")
                                if dt.isValid():
                                    widget.setDateTime(dt)
                            except:
                                pass
                        filled_fields.append(field_name)
                        break
        logger(f"快速识别: 已填充字段 {', '.join(filled_fields)}" if filled_fields else "快速识别: 未找到可识别的数据。")

    def _clear_inputs_generic(self, paste_widget, inputs_dict, checkbox):
        if paste_widget:
            paste_widget.clear()
        for widget in inputs_dict.values():
            if isinstance(widget, QLineEdit): widget.clear()
            elif isinstance(widget, QComboBox): widget.setCurrentIndex(0)
            elif isinstance(widget, QDateTimeEdit): widget.setDateTime(QDateTime.currentDateTime())
        if checkbox: checkbox.setChecked(True)

    def _toggle_sending_state_generic(self, timer, freq_input, start_btn, stop_btn, send_func, logger):
        if not timer.isActive():
            try:
                interval_ms = int(float(freq_input.text()) * 1000)
                if interval_ms <= 0: raise ValueError
            except (ValueError, TypeError):
                logger("错误: 发送频率必须是一个大于0的数字。将使用默认值3秒。")
                interval_ms = 3000
                freq_input.setText("3")
            
            log_msg = f"开始发送数据... (频率: {interval_ms / 1000}s/次)" if not stop_btn.isEnabled() else f"继续发送数据... (频率: {interval_ms / 1000}s/次)"
            logger(log_msg)
            if not stop_btn.isEnabled(): send_func()
            
            timer.start(interval_ms)
            start_btn.setText("暂停发送")
            stop_btn.setEnabled(True)
            freq_input.setEnabled(False)
        else:
            timer.stop()
            logger("已暂停发送数据。")
            start_btn.setText("继续发送")
            freq_input.setEnabled(True)

    def _terminate_sending_generic(self, timer, freq_input, start_btn, stop_btn, logger):
        timer.stop()
        logger("已终止发送数据。")
        start_btn.setText("开始发送")
        stop_btn.setEnabled(False)
        freq_input.setEnabled(True)

    def _toggle_data_status_lock_generic(self, is_checked, data_status_combo):
        if is_checked:
            data_status_combo.setCurrentIndex(-1)
            data_status_combo.setEnabled(False)
        else:
            data_status_combo.setEnabled(True)
            data_status_combo.setCurrentIndex(0)

    # ===================================================================
    # 回放及其他
    # ===================================================================

    def query_trajectory_data(self):
        """从查询构建器表格中读取所有行，并从数据库查询轨迹数据"""
        if not self.db:
            self.log_message("错误: 数据库未初始化。")
            return

        all_identifiers = set()
        overall_start_time = QDateTime.fromString("9999-12-31 23:59:59", "yyyy-MM-dd HH:mm:ss")
        overall_end_time = QDateTime.fromString("2000-01-01 00:00:00", "yyyy-MM-dd HH:mm:ss")
        
        has_valid_query = False
        for row in range(self.query_builder_table.rowCount()):
            mmsi_item = self.query_builder_table.item(row, 0)
            id_item = self.query_builder_table.item(row, 1)
            start_time_widget = self.query_builder_table.cellWidget(row, 3)
            end_time_widget = self.query_builder_table.cellWidget(row, 4)

            mmsi = mmsi_item.text().strip() if mmsi_item else ""
            target_id = id_item.text().strip() if id_item else ""

            if mmsi: all_identifiers.add(mmsi)
            if target_id: all_identifiers.add(target_id)

            if start_time_widget and end_time_widget:
                start_dt = start_time_widget.dateTime()
                end_dt = end_time_widget.dateTime()
                if start_dt < overall_start_time:
                    overall_start_time = start_dt
                if end_dt > overall_end_time:
                    overall_end_time = end_dt
                has_valid_query = True

        if not all_identifiers:
            self.log_message("查询构建器中没有任何有效的MMSI或ID。")
            return
        
        if not has_valid_query:
            self.log_message("查询构建器中没有有效的时间范围。")
            return

        results = self.db.query_trajectories(
            criteria={
                'mmsi': self.playback_inputs['mmsi'].text(),
                'id': self.playback_inputs['id'].text()
            },
            start_time=overall_start_time.toString("yyyy-MM-dd HH:mm:ss"),
            end_time=overall_end_time.toString("yyyy-MM-dd HH:mm:ss")
        )

        if results is None:
            self.log_message("数据库查询失败，请检查日志。")
            self.trajectory_data.clear()
            self.update_trajectory_table()
            return

        self.trajectory_data.clear()
        for row in results:
            row_dict = row._asdict()
            key = row_dict.get('mmsi') if row_dict.get('mmsi') else row_dict.get('id')
            if key:
                key_str = str(key)
                if key_str not in self.trajectory_data:
                    self.trajectory_data[key_str] = []
                self.trajectory_data[key_str].append(row_dict)

        self.update_trajectory_table()
        self.log_message(f"查询完成，共找到 {len(results)} 个数据点，{len(self.trajectory_data)} 个目标。")

    def add_query_row(self):
        """向查询构建器表格中添加一个新行"""
        row_position = self.query_builder_table.rowCount()
        self.query_builder_table.insertRow(row_position)

        self.query_builder_table.setItem(row_position, 0, QTableWidgetItem(""))
        self.query_builder_table.setItem(row_position, 1, QTableWidgetItem(""))
        self.query_builder_table.setItem(row_position, 2, QTableWidgetItem(""))

        start_time_edit = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.query_builder_table.setCellWidget(row_position, 3, start_time_edit)

        end_time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        end_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.query_builder_table.setCellWidget(row_position, 4, end_time_edit)

    def remove_selected_query_row(self):
        """从查询构建器表格中删除选中的行"""
        selected_rows = sorted(list(set(index.row() for index in self.query_builder_table.selectedIndexes())), reverse=True)
        if not selected_rows:
            self.log_message("请先在查询编辑器中选择要删除的行。")
            return
        for row in selected_rows:
            self.query_builder_table.removeRow(row)
        self.log_message(f"已删除 {len(selected_rows)} 行。")

    def update_trajectory_table(self):
        """更新查询结果到UI表格"""
        self.trajectory_table.setRowCount(0)
        for key, points in self.trajectory_data.items():
            row_position = self.trajectory_table.rowCount()
            self.trajectory_table.insertRow(row_position)
            
            chk_box_item = QTableWidgetItem()
            chk_box_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_box_item.setCheckState(Qt.Unchecked)
            
            self.trajectory_table.setItem(row_position, 0, chk_box_item)
            self.trajectory_table.setItem(row_position, 1, QTableWidgetItem(str(points[0].get('mmsi', 'N/A'))))
            self.trajectory_table.setItem(row_position, 2, QTableWidgetItem(str(points[0].get('id', 'N/A'))))
            self.trajectory_table.setItem(row_position, 3, QTableWidgetItem(str(len(points))))
        
        self.trajectory_table.itemClicked.connect(self.draw_trajectories)

    def draw_trajectories(self, item):
        """在预览区绘制所有被勾选的轨迹，并应用新的样式和交互。"""
        if item.column() != 0:
            return

        self.trajectory_scene.clear()
        min_lon, max_lon, min_lat, max_lat = 181, -181, 91, -91
        
        selected_keys = []
        for i in range(self.trajectory_table.rowCount()):
            if self.trajectory_table.item(i, 0).checkState() == Qt.Checked:
                mmsi = self.trajectory_table.item(i, 1).text()
                target_id = self.trajectory_table.item(i, 2).text()
                key = mmsi if mmsi != 'N/A' else target_id
                selected_keys.append(key)

        if not selected_keys:
            self.trajectory_preview.fitInView(self.trajectory_scene.itemsBoundingRect(), Qt.KeepAspectRatio)
            return

        all_points_for_bounds = []
        for key in selected_keys:
            points = self.trajectory_data.get(key)
            if points:
                all_points_for_bounds.extend(points)

        for p in all_points_for_bounds:
            try:
                lon, lat = float(p['longitude']), float(p['latitude'])
                if 180 >= lon >= -180 and 90 >= lat >= -90:
                    min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                    min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
            except (ValueError, TypeError):
                continue

        if min_lon > 180:
            return

        lon_margin = (max_lon - min_lon) * 0.1 if max_lon > min_lon else 0.1
        lat_margin = (max_lat - min_lat) * 0.1 if max_lat > min_lat else 0.1
        scene_lon_min, scene_lon_max = min_lon - lon_margin, max_lon + lon_margin
        scene_lat_min, scene_lat_max = min_lat - lat_margin, max_lat + lat_margin
        self.trajectory_scene.setSceneRect(scene_lon_min, -scene_lat_max, scene_lon_max - scene_lon_min, scene_lat_max - scene_lat_min)

        palette = [QColor("#1f77b4"), QColor("#ff7f0e"), QColor("#2ca02c"), QColor("#d62728"),
                   QColor("#9467bd"), QColor("#8c564b"), QColor("#e377c2"), QColor("#7f7f7f")]
        
        for i, key in enumerate(selected_keys):
            points = self.trajectory_data.get(key)
            if not points: continue
            
            points.sort(key=lambda p: p.get('lastTm', 0))
            
            sampled_points = []
            if len(points) > 30:
                step = len(points) / 30.0
                for j in range(30):
                    index = int(j * step)
                    if index < len(points):
                        sampled_points.append(points[index])
            else:
                sampled_points = points

            if len(sampled_points) < 1: continue

            pen_color = palette[i % len(palette)]
            path_pen = QPen(pen_color, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            
            path = QPainterPath()
            
            valid_points = []
            for p in sampled_points:
                try:
                    lon, lat = float(p['longitude']), float(p['latitude'])
                    if 180 >= lon >= -180 and 90 >= lat >= -90:
                        valid_points.append((lon, -lat))
                except (ValueError, TypeError, KeyError):
                    continue
            
            if not valid_points: continue

            path.moveTo(valid_points[0][0], valid_points[0][1])
            
            point_brush = QBrush(pen_color)
            point_size = (scene_lon_max - scene_lon_min) / 200000.0
            
            for j in range(len(valid_points)):
                if j > 0:
                    path.lineTo(valid_points[j][0], valid_points[j][1])
                self.trajectory_scene.addEllipse(
                    valid_points[j][0] - point_size / 2, 
                    valid_points[j][1] - point_size / 2, 
                    point_size, point_size, 
                    path_pen, point_brush
                )

            self.trajectory_scene.addPath(path, path_pen)

        self.trajectory_preview.fitInView(self.trajectory_scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def start_playback(self):
        """开始回放选中的轨迹"""
        self.playback_targets.clear()
        for i in range(self.trajectory_table.rowCount()):
            if self.trajectory_table.item(i, 0).checkState() == Qt.Checked:
                mmsi = self.trajectory_table.item(i, 1).text()
                target_id = self.trajectory_table.item(i, 2).text()
                key = mmsi if mmsi != 'N/A' else target_id
                
                if key in self.trajectory_data:
                    sorted_points = sorted(self.trajectory_data[key], key=lambda p: p['lastTm'])
                    self.playback_targets.extend(sorted_points)
        
        if not self.playback_targets:
            self.log_message("没有选择要回放的目标。")
            return

        self.playback_targets.sort(key=lambda p: p['lastTm'])
        self.current_playback_index = 0
        self.log_message(f"准备回放 {len(self.playback_targets)} 个数据点。")
        self.playback_timer.start(10)

    def send_playback_data(self):
        """发送单个轨迹点并设置下一个定时器"""
        if self.current_playback_index >= len(self.playback_targets):
            self.playback_timer.stop()
            self.log_message("回放完成。")
            return

        point = self.playback_targets[self.current_playback_index]
        
        target_list = target_pb2.TargetProtoList()
        target = target_list.list.add()
        
        target.id = point.get('id', 0)
        target.lastTm = point.get('lastTm', int(time.time()))
        target.sost = 1
        target.eTargetType = 14
        
        pos_info = target.pos
        pos_info.id = target.id
        pos_info.mmsi = point.get('mmsi', 0)
        pos_info.vesselName = point.get('vesselName', '')
        pos_info.speed = point.get('speed', 0.0)
        pos_info.course = point.get('course', 0.0)
        pos_info.len = int(point.get('len', 0) or 0)
        pos_info.shiptype = int(point.get('shipType', 99) or 99)
        
        geo_ptn = pos_info.geoPtn
        geo_ptn.longitude = point.get('longitude', 0.0)
        geo_ptn.latitude = point.get('latitude', 0.0)

        pb_data = target_list.SerializeToString()
        topic = self.config['kafka']['topic']
        self.kafka_producer.send_message(topic, pb_data)
        self.log_message(f"发送回放数据点: MMSI={pos_info.mmsi}, Time={target.lastTm}")

        self.update_playback_preview(geo_ptn.longitude, geo_ptn.latitude)

        self.current_playback_index += 1
        if self.current_playback_index < len(self.playback_targets):
            next_point = self.playback_targets[self.current_playback_index]
            time_diff_ms = (next_point['lastTm'] - point['lastTm']) * 1000
            self.playback_timer.setInterval(max(50, time_diff_ms))
        else:
            self.playback_timer.stop()
            self.log_message("回放完成。")

    def update_playback_preview(self, lon, lat):
        """在预览图上高亮当前发送的点"""
        for item in self.trajectory_scene.items():
            if isinstance(item, QGraphicsEllipseItem):
                self.trajectory_scene.removeItem(item)
        
        pen = QPen(Qt.red)
        brush = QBrush(Qt.red)
        self.trajectory_scene.addEllipse(lon - 0.001, lat - 0.001, 0.002, 0.002, pen, brush)

    def log_message(self, message, tab='realtime'):
        """Logs a message to the appropriate log display based on the tab."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry = f"[{timestamp}] {message}"
        
        log_display_widget = None
        if tab == 'static' and hasattr(self, 'static_log_display'):
            log_display_widget = self.static_log_display
        elif hasattr(self, 'log_display'):
            log_display_widget = self.log_display

        if log_display_widget:
            log_display_widget.append(log_entry)
        
        print(f"({tab}) {log_entry}")

    def closeEvent(self, event):
        self.kafka_producer.close()
        if self.db:
            self.db.close()
        event.accept()

    @pyqtSlot()
    def save_initial_target(self):
        """将当前UI上的所有输入值保存到 initial_target.json 文件中。"""
        try:
            initial_data = {}
            for name, widget in self.inputs.items():
                if isinstance(widget, QLineEdit):
                    initial_data[name] = widget.text()
                elif isinstance(widget, QComboBox):
                    initial_data[name] = widget.currentText()
            
            with open('initial_target.json', 'w', encoding='utf-8') as f:
                json.dump(initial_data, f, indent=4, ensure_ascii=False)
            
            self.log_message("成功: 当前输入已保存为初始目标。")
        except Exception as e:
            self.log_message(f"错误: 保存初始目标失败 - {e}")

    @pyqtSlot()
    def load_initial_target(self, is_silent=False):
        """从 initial_target.json 文件中加载值并填充到UI控件。"""
        try:
            with open('initial_target.json', 'r', encoding='utf-8') as f:
                initial_data = json.load(f)
            
            for name, value in initial_data.items():
                widget = self.inputs.get(name)
                if not widget:
                    continue
                
                if isinstance(widget, QLineEdit):
                    widget.setText(value)
                elif isinstance(widget, QComboBox):
                    index = widget.findText(value)
                    if index != -1:
                        widget.setCurrentIndex(index)
            
            if not is_silent:
                self.log_message("成功: 已从文件加载初始目标。")
        except FileNotFoundError:
            if not is_silent:
                self.log_message("信息: 未找到 'initial_target.json' 配置文件，将使用默认值。")
        except Exception as e:
            if not is_silent:
                self.log_message(f"错误: 加载初始目标失败 - {e}")