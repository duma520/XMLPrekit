# specialized_editor.py
import sys
import os
import shutil
import sqlite3
import json
import copy
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
from pypinyin import lazy_pinyin, Style

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QSplitter, QStatusBar, QProgressBar,
    QDialog, QDialogButtonBox, QLineEdit, QFormLayout, QMessageBox,
    QCheckBox, QSpinBox, QHeaderView, QMenu, QFileDialog,
    QDateTimeEdit, QRadioButton, QButtonGroup, QGroupBox, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QInputDialog, QFrame, QAbstractItemView, QStyle, QStyleFactory,
    QToolBar, QToolButton, QSizePolicy
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QDateTime, QSettings, QTimer, QMutex, 
    QWaitCondition, QMutexLocker, QSize
)
from PySide6.QtGui import (
    QIcon, QFont, QAction, QKeySequence, QShortcut, QColor, 
    QBrush, QPalette
)

# 全局常量
APP_NAME = "XML预置文件专用编辑器"
APP_VERSION = "2.0.0"
BACKUP_DIR = "backups"
MAX_BACKUP_COUNT = 30
DEFAULT_ENCODING = "gb2312"

# 预定义数据结构
PREDEFINED_COUNTRIES = ["唐国", "周国", "楚国", "燕国", "赵国", "汉国", "魏国", "吴国", "宋国", "齐国"]
PREDEFINED_CITIES = ["王城", "边境"]
PREDEFINED_LOCATIONS = {
    "王城": {
        "北通": ("632", "19", "0"),
        "南通": ("619", "972", "1"),
        "家镖": ("794", "495", "3"),
        "华英雄": ("822", "457", "4"),
        "家族管理员": ("804", "513", "0"),
        "慕容": ("848", "457", "1")
    },
    "边境": {
        "无妄之海": ("311", "76", "2")
    }
}

class DatabaseManagerX:
    """数据库管理器 - 统一管理所有数据库操作"""
    _instance = None
    _mutex = QMutex()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.connection = None
            self.current_user = None
            self.db_path = None
            self.initialized = True
    
    def initialize_database(self, db_path: str) -> bool:
        """初始化数据库连接"""
        try:
            if self.connection:
                self.connection.close()
            
            self.db_path = db_path
            self.connection = sqlite3.connect(db_path, check_same_thread=False)
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA synchronous=NORMAL")
            self.connection.execute("PRAGMA cache_size=-2000")
            self._create_tables_x()
            return True
        except Exception as e:
            if self.debug_mode:
                print(f"数据库初始化失败: {e}")
            return False
    
    def _create_tables_x(self):
        """创建数据库表"""
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_records (
                backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_filename TEXT NOT NULL,
                backup_type TEXT NOT NULL CHECK(backup_type IN ('自动', '手动', '回滚')),
                backup_timestamp TEXT NOT NULL,
                file_size_bytes INTEGER,
                app_version TEXT,
                data_date_range TEXT,
                user_name TEXT,
                description TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edit_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                edit_timestamp TEXT NOT NULL,
                edit_action TEXT NOT NULL,
                edit_details TEXT,
                user_name TEXT,
                file_name TEXT
            )
        """)
        self.connection.commit()
    
    def execute_query_x(self, query: str, params: tuple = None) -> List:
        """执行查询"""
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            if self.debug_mode:
                print(f"查询执行失败: {e}")
            return []
    
    def execute_update_x(self, query: str, params: tuple = None) -> bool:
        """执行更新"""
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            return True
        except Exception as e:
            if self.debug_mode:
                print(f"更新执行失败: {e}")
            return False
    
    def close_connection(self):
        """关闭数据库连接"""
        if self.connection:
            try:
                self.connection.execute("PRAGMA optimize")
                self.connection.close()
            except:
                pass
            self.connection = None

class BackupWorkerX(QThread):
    """备份工作线程"""
    progress_signal = Signal(int)
    completion_signal = Signal(bool, str, str)
    status_signal = Signal(str)
    
    def __init__(self, source_db: str, backup_path: str, backup_type: str, user_name: str):
        super().__init__()
        self.source_db = source_db
        self.backup_path = backup_path
        self.backup_type = backup_type
        self.user_name = user_name
        
    def run(self):
        try:
            self.status_signal.emit(f"开始创建{self.backup_type}备份...")
            self.progress_signal.emit(10)
            
            # 确保备份目录存在
            Path(self.backup_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 使用SQLite备份API
            source_conn = sqlite3.connect(self.source_db)
            backup_conn = sqlite3.connect(self.backup_path)
            
            self.progress_signal.emit(30)
            source_conn.backup(backup_conn)
            
            self.progress_signal.emit(70)
            
            # 获取文件大小
            file_size = os.path.getsize(self.backup_path)
            
            backup_conn.close()
            source_conn.close()
            
            self.progress_signal.emit(90)
            
            # 记录备份信息
            db_manager = DatabaseManagerX()
            if db_manager.connection:
                db_manager.execute_update_x(
                    """INSERT INTO backup_records 
                       (backup_filename, backup_type, backup_timestamp, file_size_bytes, 
                        app_version, user_name)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (os.path.basename(self.backup_path), self.backup_type,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     file_size, APP_VERSION, self.user_name)
                )
            
            self.progress_signal.emit(100)
            backup_name = os.path.basename(self.backup_path)
            self.completion_signal.emit(True, f"备份成功: {backup_name}", backup_name)
            
        except Exception as e:
            self.completion_signal.emit(False, f"备份失败: {str(e)}", "")

class RestoreWorkerX(QThread):
    """恢复工作线程"""
    progress_signal = Signal(int)
    completion_signal = Signal(bool, str)
    status_signal = Signal(str)
    
    def __init__(self, backup_path: str, target_db: str):
        super().__init__()
        self.backup_path = backup_path
        self.target_db = target_db
        
    def run(self):
        try:
            self.status_signal.emit("准备恢复数据库...")
            self.progress_signal.emit(10)
            
            # 创建回滚备份
            if os.path.exists(self.target_db):
                rollback_path = self.target_db + f".rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.target_db, rollback_path)
            
            self.progress_signal.emit(30)
            
            # 关闭现有连接
            db_manager = DatabaseManagerX()
            if db_manager.connection:
                db_manager.connection.close()
                db_manager.connection = None
            
            self.progress_signal.emit(50)
            
            # 恢复备份
            backup_conn = sqlite3.connect(self.backup_path)
            target_conn = sqlite3.connect(self.target_db)
            backup_conn.backup(target_conn)
            
            self.progress_signal.emit(80)
            
            backup_conn.close()
            target_conn.close()
            
            # 重新初始化
            db_manager.initialize_database(self.target_db)
            
            self.progress_signal.emit(100)
            self.completion_signal.emit(True, "数据库恢复成功")
            
        except Exception as e:
            self.completion_signal.emit(False, f"恢复失败: {str(e)}")

class UserManagerX:
    """用户管理器"""
    def __init__(self, data_directory: str):
        self.data_directory = data_directory
        self.users_config_file = os.path.join(data_directory, "users_config.json")
        self.user_list = []
        self.ensure_data_directory()
        self.load_user_list()
    
    def ensure_data_directory(self):
        """确保数据目录存在"""
        Path(self.data_directory).mkdir(parents=True, exist_ok=True)
    
    def load_user_list(self):
        """加载用户列表"""
        if os.path.exists(self.users_config_file):
            try:
                with open(self.users_config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.user_list = data.get('users', [])
            except:
                self.user_list = []
        
        if not self.user_list:
            self.user_list = ["默认管理员"]
            self.save_user_list()
    
    def save_user_list(self):
        """保存用户列表"""
        with open(self.users_config_file, 'w', encoding='utf-8') as f:
            json.dump({'users': self.user_list}, f, ensure_ascii=False, indent=2)
    
    def add_new_user(self, username: str) -> bool:
        """添加新用户"""
        if username in self.user_list:
            return False
        
        self.user_list.append(username)
        self.save_user_list()
        
        # 创建用户数据库
        user_db_path = os.path.join(self.data_directory, f"user_{username}.db")
        temp_manager = DatabaseManagerX()
        temp_manager.initialize_database(user_db_path)
        temp_manager.close_connection()
        
        return True
    
    def remove_existing_user(self, username: str) -> bool:
        """删除用户"""
        if username not in self.user_list:
            return False
        
        self.user_list.remove(username)
        self.save_user_list()
        return True
    
    def rename_existing_user(self, old_name: str, new_name: str) -> bool:
        """重命名用户"""
        if new_name in self.user_list or old_name not in self.user_list:
            return False
        
        idx = self.user_list.index(old_name)
        self.user_list[idx] = new_name
        self.save_user_list()
        
        # 重命名数据库文件
        old_db = os.path.join(self.data_directory, f"user_{old_name}.db")
        new_db = os.path.join(self.data_directory, f"user_{new_name}.db")
        if os.path.exists(old_db):
            try:
                shutil.move(old_db, new_db)
            except:
                pass
        
        return True
    
    def get_user_database_path(self, username: str) -> str:
        """获取用户数据库路径"""
        return os.path.join(self.data_directory, f"user_{username}.db")

class PrekeepDataModel:
    """Prekeep数据模型 - 管理XML数据结构"""
    def __init__(self):
        self.prekeeps = {}  # key: username, value: list of value dicts
        self.file_path = None
        self.modified = False
    
    def load_from_file(self, file_path: str) -> bool:
        """从文件加载数据"""
        try:
            with open(file_path, 'r', encoding=DEFAULT_ENCODING) as f:
                content = f.read()
            
            # 处理编码
            if 'encoding="gb2312"' in content:
                content = content.replace('encoding="gb2312"', 'encoding="utf-8"')
            
            root = ET.fromstring(content)
            self.prekeeps.clear()
            
            for prekeep_elem in root.findall("prekeep"):
                user = prekeep_elem.get("user", "")
                values = []
                
                for value_elem in prekeep_elem.findall("value"):
                    value_dict = {
                        'country': value_elem.get("country", ""),
                        'city': value_elem.get("city", ""),
                        'posX': value_elem.get("posX", ""),
                        'posY': value_elem.get("posY", ""),
                        'id': value_elem.get("id", ""),
                        'name': value_elem.text or ""
                    }
                    values.append(value_dict)
                
                self.prekeeps[user] = values
            
            self.file_path = file_path
            self.modified = False
            return True
            
        except Exception as e:
            print(f"加载文件失败: {e}")
            return False
    
    def save_to_file(self, file_path: str = None) -> bool:
        """保存到文件"""
        if file_path:
            self.file_path = file_path
        
        if not self.file_path:
            return False
        
        try:
            root = ET.Element("prekeeps")
            
            for user, values in self.prekeeps.items():
                prekeep_elem = ET.SubElement(root, "prekeep")
                prekeep_elem.set("user", user)
                
                for value_dict in values:
                    value_elem = ET.SubElement(prekeep_elem, "value")
                    value_elem.set("country", value_dict['country'])
                    value_elem.set("city", value_dict['city'])
                    value_elem.set("posX", value_dict['posX'])
                    value_elem.set("posY", value_dict['posY'])
                    value_elem.set("id", value_dict['id'])
                    value_elem.text = value_dict['name']
            
            # 格式化输出
            rough_string = ET.tostring(root, encoding='unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="    ", encoding=DEFAULT_ENCODING)
            
            # 添加XML声明
            final_xml = '<?xml version="1.0" encoding="gb2312" ?>\n' + pretty_xml.decode(DEFAULT_ENCODING)
            
            with open(self.file_path, 'w', encoding=DEFAULT_ENCODING) as f:
                f.write(final_xml)
            
            self.modified = False
            return True
            
        except Exception as e:
            print(f"保存文件失败: {e}")
            return False
    
    def add_prekeep_user(self, username: str, template_data: List[Dict] = None):
        """添加prekeep用户"""
        if template_data:
            self.prekeeps[username] = copy.deepcopy(template_data)
        else:
            self.prekeeps[username] = []
        self.modified = True
    
    def remove_prekeep_user(self, username: str):
        """删除prekeep用户"""
        if username in self.prekeeps:
            del self.prekeeps[username]
            self.modified = True
    
    def duplicate_prekeep_user(self, source_user: str, new_user: str):
        """复制prekeep用户配置"""
        if source_user in self.prekeeps:
            self.prekeeps[new_user] = copy.deepcopy(self.prekeeps[source_user])
            self.modified = True
    
    def add_value_to_user(self, username: str, value_dict: Dict):
        """为用户添加值"""
        if username in self.prekeeps:
            self.prekeeps[username].append(value_dict)
            self.modified = True
    
    def remove_value_from_user(self, username: str, index: int):
        """删除用户的值"""
        if username in self.prekeeps and 0 <= index < len(self.prekeeps[username]):
            del self.prekeeps[username][index]
            self.modified = True
    
    def update_value_for_user(self, username: str, index: int, value_dict: Dict):
        """更新用户的值"""
        if username in self.prekeeps and 0 <= index < len(self.prekeeps[username]):
            self.prekeeps[username][index] = value_dict
            self.modified = True
    
    def get_all_users(self) -> List[str]:
        """获取所有用户名"""
        return list(self.prekeeps.keys())
    
    def get_user_values(self, username: str) -> List[Dict]:
        """获取用户的配置值"""
        return self.prekeeps.get(username, [])
    
    def search_values(self, search_text: str) -> Dict[str, List[Dict]]:
        """搜索值"""
        results = {}
        search_lower = search_text.lower()
        
        for user, values in self.prekeeps.items():
            matched_values = []
            for value in values:
                if self._match_value(value, search_lower):
                    matched_values.append(value)
            if matched_values:
                results[user] = matched_values
        
        return results
    
    def _match_value(self, value: Dict, search_text: str) -> bool:
        """匹配值"""
        # 检查所有字段
        for key in ['country', 'city', 'name', 'posX', 'posY', 'id']:
            field_text = value.get(key, "").lower()
            if search_text in field_text:
                return True
            
            # 检查拼音
            field_pinyin = ''.join(lazy_pinyin(field_text, style=Style.NORMAL)).lower()
            if search_text in field_pinyin:
                return True
            
            # 检查拼音首字母
            field_first = ''.join(lazy_pinyin(field_text, style=Style.FIRST_LETTER)).lower()
            if search_text in field_first:
                return True
        
        return False

class PrekeepEditorWidget(QWidget):
    """Prekeep编辑器控件"""
    data_modified_signal = Signal()
    status_message_signal = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_model = PrekeepDataModel()
        self.current_user = None
        self.clipboard_data = []
        self.setup_ui_components()
    
    def setup_ui_components(self):
        """设置UI组件"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        toolbar.addWidget(QLabel("文件:"))
        self.file_path_label = QLabel("未加载")
        self.file_path_label.setStyleSheet("font-weight: bold;")
        toolbar.addWidget(self.file_path_label)
        
        toolbar.addStretch()
        
        self.load_file_btn = QPushButton("加载文件")
        self.load_file_btn.clicked.connect(self.on_load_file)
        toolbar.addWidget(self.load_file_btn)
        
        self.save_file_btn = QPushButton("保存")
        self.save_file_btn.clicked.connect(self.on_save_file)
        self.save_file_btn.setEnabled(False)
        toolbar.addWidget(self.save_file_btn)
        
        self.reload_file_btn = QPushButton("重新加载")
        self.reload_file_btn.clicked.connect(self.on_reload_file)
        self.reload_file_btn.setEnabled(False)
        toolbar.addWidget(self.reload_file_btn)
        
        main_layout.addLayout(toolbar)
        
        # 主分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧用户列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("用户列表:"))
        
        self.user_list_widget = QListWidget()
        self.user_list_widget.setAlternatingRowColors(True)
        self.user_list_widget.currentItemChanged.connect(self.on_user_selected)
        self.user_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.user_list_widget.customContextMenuRequested.connect(self.show_user_context_menu)
        left_layout.addWidget(self.user_list_widget)
        
        # 用户操作按钮
        user_btn_layout = QHBoxLayout()
        
        self.add_user_btn = QPushButton("添加用户")
        self.add_user_btn.clicked.connect(self.on_add_user)
        user_btn_layout.addWidget(self.add_user_btn)
        
        self.copy_user_btn = QPushButton("复制用户")
        self.copy_user_btn.clicked.connect(self.on_copy_user)
        user_btn_layout.addWidget(self.copy_user_btn)
        
        self.remove_user_btn = QPushButton("删除用户")
        self.remove_user_btn.clicked.connect(self.on_remove_user)
        user_btn_layout.addWidget(self.remove_user_btn)
        
        left_layout.addLayout(user_btn_layout)
        
        splitter.addWidget(left_widget)
        
        # 右侧编辑区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 用户信息
        self.user_info_label = QLabel("请选择用户")
        self.user_info_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        right_layout.addWidget(self.user_info_label)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索内容 (支持中英文、拼音)...")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        search_layout.addWidget(self.search_input)
        
        self.clear_search_btn = QPushButton("清除")
        self.clear_search_btn.clicked.connect(self.on_clear_search)
        search_layout.addWidget(self.clear_search_btn)
        
        right_layout.addLayout(search_layout)
        
        # 数据表格
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(6)
        self.data_table.setHorizontalHeaderLabels(["国家", "城市", "X坐标", "Y坐标", "ID", "名称"])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.itemChanged.connect(self.on_table_item_changed)
        self.data_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self.show_table_context_menu)
        right_layout.addWidget(self.data_table)
        
        # 操作按钮
        operation_layout = QHBoxLayout()
        
        self.add_row_btn = QPushButton("添加行")
        self.add_row_btn.clicked.connect(self.on_add_row)
        self.add_row_btn.setEnabled(False)
        operation_layout.addWidget(self.add_row_btn)
        
        self.remove_row_btn = QPushButton("删除选中行")
        self.remove_row_btn.clicked.connect(self.on_remove_row)
        self.remove_row_btn.setEnabled(False)
        operation_layout.addWidget(self.remove_row_btn)
        
        self.copy_rows_btn = QPushButton("复制选中行")
        self.copy_rows_btn.clicked.connect(self.on_copy_rows)
        self.copy_rows_btn.setEnabled(False)
        operation_layout.addWidget(self.copy_rows_btn)
        
        self.paste_rows_btn = QPushButton("粘贴行")
        self.paste_rows_btn.clicked.connect(self.on_paste_rows)
        self.paste_rows_btn.setEnabled(False)
        operation_layout.addWidget(self.paste_rows_btn)
        
        self.batch_add_btn = QPushButton("批量添加模板")
        self.batch_add_btn.clicked.connect(self.on_batch_add_template)
        self.batch_add_btn.setEnabled(False)
        operation_layout.addWidget(self.batch_add_btn)
        
        operation_layout.addStretch()
        
        self.import_csv_btn = QPushButton("导入CSV")
        self.import_csv_btn.clicked.connect(self.on_import_csv)
        self.import_csv_btn.setEnabled(False)
        operation_layout.addWidget(self.import_csv_btn)
        
        self.export_csv_btn = QPushButton("导出CSV")
        self.export_csv_btn.clicked.connect(self.on_export_csv)
        self.export_csv_btn.setEnabled(False)
        operation_layout.addWidget(self.export_csv_btn)
        
        right_layout.addLayout(operation_layout)
        
        # 快速添加模板区域
        template_group = QGroupBox("快速添加模板")
        template_layout = QGridLayout(template_group)
        
        row = 0
        col = 0
        for city, locations in PREDEFINED_LOCATIONS.items():
            for name, (posX, posY, id_val) in locations.items():
                btn = QPushButton(f"{city}-{name}")
                btn.setMaximumWidth(150)
                btn.clicked.connect(lambda checked, c=city, n=name, x=posX, y=posY, i=id_val: 
                                  self.on_quick_add_location(c, n, x, y, i))
                template_layout.addWidget(btn, row, col)
                col += 1
                if col >= 4:
                    col = 0
                    row += 1
        
        right_layout.addWidget(template_group)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 950])
        
        main_layout.addWidget(splitter)
    
    def on_load_file(self):
        """加载文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择XML文件", "", "XML文件 (*.xml);;所有文件 (*)"
        )
        if file_path:
            self.load_file(file_path)
    
    def load_file(self, file_path: str):
        """加载指定文件"""
        if self.data_model.modified:
            reply = QMessageBox.question(self, "未保存的更改",
                "当前文件有未保存的更改，是否继续?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        if self.data_model.load_from_file(file_path):
            self.file_path_label.setText(os.path.basename(file_path))
            self.save_file_btn.setEnabled(True)
            self.reload_file_btn.setEnabled(True)
            self.refresh_user_list()
            self.status_message_signal.emit(f"文件加载成功: {file_path}")
        else:
            QMessageBox.critical(self, "错误", "文件加载失败")
    
    def on_save_file(self):
        """保存文件"""
        if self.data_model.save_to_file():
            self.status_message_signal.emit("文件保存成功")
        else:
            QMessageBox.critical(self, "错误", "文件保存失败")
    
    def on_reload_file(self):
        """重新加载文件"""
        if self.data_model.file_path:
            self.load_file(self.data_model.file_path)
    
    def refresh_user_list(self):
        """刷新用户列表"""
        self.user_list_widget.blockSignals(True)
        self.user_list_widget.clear()
        
        users = self.data_model.get_all_users()
        for user in users:
            item = QListWidgetItem(f"{user} ({len(self.data_model.get_user_values(user))}条)")
            self.user_list_widget.addItem(item)
        
        self.user_list_widget.blockSignals(False)
    
    def on_user_selected(self, current, previous):
        """用户选择事件"""
        if current:
            self.current_user = current.text().split(" (")[0]
            self.user_info_label.setText(f"当前用户: {self.current_user}")
            self.refresh_data_table()
            self.add_row_btn.setEnabled(True)
            self.remove_row_btn.setEnabled(True)
            self.copy_rows_btn.setEnabled(True)
            self.paste_rows_btn.setEnabled(True)
            self.batch_add_btn.setEnabled(True)
            self.import_csv_btn.setEnabled(True)
            self.export_csv_btn.setEnabled(True)
    
    def refresh_data_table(self, search_text: str = None):
        """刷新数据表格"""
        self.data_table.blockSignals(True)
        self.data_table.setRowCount(0)
        
        if not self.current_user:
            self.data_table.blockSignals(False)
            return
        
        values = self.data_model.get_user_values(self.current_user)
        
        if search_text:
            search_lower = search_text.lower()
            values = [v for v in values if self._filter_value(v, search_lower)]
        
        for value in values:
            row = self.data_table.rowCount()
            self.data_table.insertRow(row)
            
            items = [
                QTableWidgetItem(value['country']),
                QTableWidgetItem(value['city']),
                QTableWidgetItem(value['posX']),
                QTableWidgetItem(value['posY']),
                QTableWidgetItem(value['id']),
                QTableWidgetItem(value['name'])
            ]
            
            for col, item in enumerate(items):
                self.data_table.setItem(row, col, item)
        
        self.data_table.blockSignals(False)
    
    def _filter_value(self, value: Dict, search_text: str) -> bool:
        """过滤值"""
        for key in ['country', 'city', 'name']:
            field_text = value.get(key, "").lower()
            if search_text in field_text:
                return True
            
            field_pinyin = ''.join(lazy_pinyin(field_text, style=Style.NORMAL)).lower()
            if search_text in field_pinyin:
                return True
            
            field_first = ''.join(lazy_pinyin(field_text, style=Style.FIRST_LETTER)).lower()
            if search_text in field_first:
                return True
        
        return False
    
    def on_search_text_changed(self, text: str):
        """搜索文本改变"""
        self.refresh_data_table(text if text else None)
    
    def on_clear_search(self):
        """清除搜索"""
        self.search_input.clear()
    
    def on_table_item_changed(self, item):
        """表格数据改变"""
        row = item.row()
        col = item.column()
        
        if self.current_user and row < len(self.data_model.get_user_values(self.current_user)):
            values = self.data_model.get_user_values(self.current_user)
            if row < len(values):
                value = values[row]
                
                field_map = {0: 'country', 1: 'city', 2: 'posX', 3: 'posY', 4: 'id', 5: 'name'}
                field = field_map.get(col)
                
                if field:
                    value[field] = item.text()
                    self.data_model.modified = True
                    self.data_modified_signal.emit()
    
    def show_user_context_menu(self, position):
        """显示用户右键菜单"""
        menu = QMenu()
        add_action = menu.addAction("添加用户")
        copy_action = menu.addAction("复制用户配置")
        rename_action = menu.addAction("重命名用户")
        remove_action = menu.addAction("删除用户")
        
        action = menu.exec(self.user_list_widget.viewport().mapToGlobal(position))
        
        if action == add_action:
            self.on_add_user()
        elif action == copy_action:
            self.on_copy_user()
        elif action == rename_action:
            self.on_rename_user()
        elif action == remove_action:
            self.on_remove_user()
    
    def show_table_context_menu(self, position):
        """显示表格右键菜单"""
        menu = QMenu()
        
        add_action = menu.addAction("添加行")
        remove_action = menu.addAction("删除选中行")
        menu.addSeparator()
        copy_action = menu.addAction("复制选中行")
        paste_action = menu.addAction("粘贴行")
        menu.addSeparator()
        duplicate_action = menu.addAction("复制选中行到末尾")
        
        action = menu.exec(self.data_table.viewport().mapToGlobal(position))
        
        if action == add_action:
            self.on_add_row()
        elif action == remove_action:
            self.on_remove_row()
        elif action == copy_action:
            self.on_copy_rows()
        elif action == paste_action:
            self.on_paste_rows()
        elif action == duplicate_action:
            self.on_duplicate_rows()
    
    def on_add_user(self):
        """添加用户"""
        username, ok = QInputDialog.getText(self, "添加用户", "请输入用户名:")
        if ok and username:
            if username in self.data_model.get_all_users():
                QMessageBox.warning(self, "警告", "用户已存在")
                return
            
            # 询问是否复制现有用户的数据
            reply = QMessageBox.question(self, "复制数据",
                "是否从现有用户复制数据?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                # 选择源用户
                source_user, ok = QInputDialog.getItem(self, "选择源用户",
                    "请选择要复制的用户:", self.data_model.get_all_users(), 0, False)
                if ok and source_user:
                    self.data_model.duplicate_prekeep_user(source_user, username)
            else:
                self.data_model.add_prekeep_user(username, [])
            
            self.refresh_user_list()
            self.data_modified_signal.emit()
            self.status_message_signal.emit(f"用户 {username} 添加成功")
    
    def on_copy_user(self):
        """复制用户配置"""
        if self.current_user:
            new_name, ok = QInputDialog.getText(self, "复制用户",
                f"复制 {self.current_user} 的配置，请输入新用户名:")
            if ok and new_name:
                if new_name in self.data_model.get_all_users():
                    QMessageBox.warning(self, "警告", "用户名已存在")
                    return
                
                self.data_model.duplicate_prekeep_user(self.current_user, new_name)
                self.refresh_user_list()
                self.data_modified_signal.emit()
                self.status_message_signal.emit(f"用户配置复制成功: {new_name}")
    
    def on_rename_user(self):
        """重命名用户"""
        if self.current_user:
            new_name, ok = QInputDialog.getText(self, "重命名用户",
                f"重命名 {self.current_user}，请输入新用户名:")
            if ok and new_name and new_name != self.current_user:
                if new_name in self.data_model.get_all_users():
                    QMessageBox.warning(self, "警告", "用户名已存在")
                    return
                
                # 复制数据到新名称
                self.data_model.duplicate_prekeep_user(self.current_user, new_name)
                # 删除旧名称
                self.data_model.remove_prekeep_user(self.current_user)
                
                self.current_user = new_name
                self.refresh_user_list()
                self.data_modified_signal.emit()
                self.status_message_signal.emit(f"用户重命名成功: {new_name}")
    
    def on_remove_user(self):
        """删除用户"""
        if self.current_user:
            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除用户 {self.current_user} 及其所有配置吗?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.data_model.remove_prekeep_user(self.current_user)
                self.current_user = None
                self.user_info_label.setText("请选择用户")
                self.refresh_user_list()
                self.refresh_data_table()
                self.data_modified_signal.emit()
                self.status_message_signal.emit(f"用户已删除")
    
    def on_add_row(self):
        """添加行"""
        if not self.current_user:
            return
        
        # 使用默认值
        new_value = {
            'country': PREDEFINED_COUNTRIES[0] if PREDEFINED_COUNTRIES else "唐国",
            'city': PREDEFINED_CITIES[0] if PREDEFINED_CITIES else "王城",
            'posX': "0",
            'posY': "0",
            'id': str(len(self.data_model.get_user_values(self.current_user))),
            'name': "新地点"
        }
        
        self.data_model.add_value_to_user(self.current_user, new_value)
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit("添加行成功")
    
    def on_quick_add_location(self, city: str, name: str, posX: str, posY: str, id_val: str):
        """快速添加预设位置"""
        if not self.current_user:
            QMessageBox.warning(self, "警告", "请先选择用户")
            return
        
        # 获取选中国家
        country, ok = QInputDialog.getItem(self, "选择国家",
            "请选择国家:", PREDEFINED_COUNTRIES, 0, False)
        if not ok:
            return
        
        new_value = {
            'country': country,
            'city': city,
            'posX': posX,
            'posY': posY,
            'id': id_val,
            'name': name
        }
        
        self.data_model.add_value_to_user(self.current_user, new_value)
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit(f"快速添加 {city}-{name} 成功")
    
    def on_remove_row(self):
        """删除选中行"""
        selected_rows = set()
        for item in self.data_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        for row in sorted(selected_rows, reverse=True):
            self.data_model.remove_value_from_user(self.current_user, row)
        
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit(f"删除 {len(selected_rows)} 行成功")
    
    def on_copy_rows(self):
        """复制选中行到剪贴板"""
        self.clipboard_data = []
        selected_rows = set()
        for item in self.data_table.selectedItems():
            selected_rows.add(item.row())
        
        values = self.data_model.get_user_values(self.current_user)
        for row in sorted(selected_rows):
            if row < len(values):
                self.clipboard_data.append(copy.deepcopy(values[row]))
        
        self.status_message_signal.emit(f"复制 {len(self.clipboard_data)} 行到剪贴板")
    
    def on_paste_rows(self):
        """粘贴剪贴板数据"""
        if not self.clipboard_data:
            QMessageBox.information(self, "提示", "剪贴板为空")
            return
        
        for value in self.clipboard_data:
            self.data_model.add_value_to_user(self.current_user, copy.deepcopy(value))
        
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit(f"粘贴 {len(self.clipboard_data)} 行成功")
    
    def on_duplicate_rows(self):
        """复制选中行到末尾"""
        selected_rows = set()
        for item in self.data_table.selectedItems():
            selected_rows.add(item.row())
        
        values = self.data_model.get_user_values(self.current_user)
        for row in sorted(selected_rows):
            if row < len(values):
                new_value = copy.deepcopy(values[row])
                # 修改ID避免冲突
                new_value['id'] = str(int(new_value['id']) + 100)
                self.data_model.add_value_to_user(self.current_user, new_value)
        
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit(f"复制 {len(selected_rows)} 行到末尾")
    
    def on_batch_add_template(self):
        """批量添加模板数据"""
        if not self.current_user:
            return
        
        # 选择模板类型
        template_type, ok = QInputDialog.getItem(self, "选择模板",
            "请选择要添加的模板类型:",
            ["全国家模板", "单个国家模板", "自定义模板"], 0, False)
        
        if not ok:
            return
        
        if template_type == "全国家模板":
            self._add_all_countries_template()
        elif template_type == "单个国家模板":
            self._add_single_country_template()
        elif template_type == "自定义模板":
            self._add_custom_template()
    
    def _add_all_countries_template(self):
        """添加所有国家的模板"""
        for country in PREDEFINED_COUNTRIES:
            for city, locations in PREDEFINED_LOCATIONS.items():
                for name, (posX, posY, id_val) in locations.items():
                    value = {
                        'country': country,
                        'city': city,
                        'posX': posX,
                        'posY': posY,
                        'id': id_val,
                        'name': name
                    }
                    self.data_model.add_value_to_user(self.current_user, value)
        
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit("全国家模板添加完成")
    
    def _add_single_country_template(self):
        """添加单个国家模板"""
        country, ok = QInputDialog.getItem(self, "选择国家",
            "请选择国家:", PREDEFINED_COUNTRIES, 0, False)
        if not ok:
            return
        
        for city, locations in PREDEFINED_LOCATIONS.items():
            for name, (posX, posY, id_val) in locations.items():
                value = {
                    'country': country,
                    'city': city,
                    'posX': posX,
                    'posY': posY,
                    'id': id_val,
                    'name': name
                }
                self.data_model.add_value_to_user(self.current_user, value)
        
        self.refresh_data_table()
        self.refresh_user_list()
        self.data_modified_signal.emit()
        self.status_message_signal.emit(f"{country}模板添加完成")
    
    def _add_custom_template(self):
        """添加自定义模板"""
        # 这里可以实现更复杂的模板选择逻辑
        pass
    
    def on_import_csv(self):
        """从CSV导入"""
        if not self.current_user:
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择CSV文件", "", "CSV文件 (*.csv);;所有文件 (*)"
        )
        
        if file_path:
            try:
                import csv
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader)  # 跳过表头
                    
                    for row in reader:
                        if len(row) >= 6:
                            value = {
                                'country': row[0],
                                'city': row[1],
                                'posX': row[2],
                                'posY': row[3],
                                'id': row[4],
                                'name': row[5]
                            }
                            self.data_model.add_value_to_user(self.current_user, value)
                
                self.refresh_data_table()
                self.refresh_user_list()
                self.data_modified_signal.emit()
                self.status_message_signal.emit("CSV导入成功")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"CSV导入失败: {str(e)}")
    
    def on_export_csv(self):
        """导出到CSV"""
        if not self.current_user:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存CSV文件", f"{self.current_user}_export.csv", "CSV文件 (*.csv)"
        )
        
        if file_path:
            try:
                import csv
                values = self.data_model.get_user_values(self.current_user)
                
                with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['国家', '城市', 'X坐标', 'Y坐标', 'ID', '名称'])
                    
                    for value in values:
                        writer.writerow([
                            value['country'],
                            value['city'],
                            value['posX'],
                            value['posY'],
                            value['id'],
                            value['name']
                        ])
                
                self.status_message_signal.emit("CSV导出成功")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"CSV导出失败: {str(e)}")

class BackupDialogX(QDialog):
    """备份恢复对话框"""
    def __init__(self, db_manager: DatabaseManagerX, current_user: str, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_user = current_user
        self.setWindowTitle("数据库备份与恢复")
        self.setMinimumSize(900, 700)
        self.setup_ui_x()
        self.refresh_backup_list()
    
    def setup_ui_x(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 筛选区域
        filter_group = QGroupBox("筛选条件")
        filter_layout = QGridLayout(filter_group)
        
        filter_layout.addWidget(QLabel("开始时间:"), 0, 0)
        self.start_time_edit = QDateTimeEdit()
        self.start_time_edit.setCalendarPopup(True)
        self.start_time_edit.setDateTime(QDateTime.currentDateTime().addMonths(-1))
        filter_layout.addWidget(self.start_time_edit, 0, 1)
        
        filter_layout.addWidget(QLabel("结束时间:"), 0, 2)
        self.end_time_edit = QDateTimeEdit()
        self.end_time_edit.setCalendarPopup(True)
        self.end_time_edit.setDateTime(QDateTime.currentDateTime())
        filter_layout.addWidget(self.end_time_edit, 0, 3)
        
        filter_layout.addWidget(QLabel("备份类型:"), 1, 0)
        self.backup_type_combo = QComboBox()
        self.backup_type_combo.addItems(["全部", "自动", "手动", "回滚"])
        filter_layout.addWidget(self.backup_type_combo, 1, 1)
        
        self.apply_filter_btn = QPushButton("应用筛选")
        self.apply_filter_btn.clicked.connect(self.refresh_backup_list)
        filter_layout.addWidget(self.apply_filter_btn, 1, 3)
        
        layout.addWidget(filter_group)
        
        # 备份列表
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(6)
        self.backup_table.setHorizontalHeaderLabels([
            "备份时间", "备份类型", "文件大小", "用户", "版本", "操作"
        ])
        self.backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.backup_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.backup_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.backup_table.setAlternatingRowColors(True)
        layout.addWidget(self.backup_table)
        
        # 详细信息
        info_group = QGroupBox("备份详情")
        info_layout = QVBoxLayout(info_group)
        self.backup_info_text = QTextEdit()
        self.backup_info_text.setReadOnly(True)
        self.backup_info_text.setMaximumHeight(120)
        info_layout.addWidget(self.backup_info_text)
        layout.addWidget(info_group)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.restore_btn = QPushButton("恢复选中备份")
        self.restore_btn.clicked.connect(self.on_restore_backup)
        btn_layout.addWidget(self.restore_btn)
        
        self.delete_btn = QPushButton("删除选中备份")
        self.delete_btn.clicked.connect(self.on_delete_backup)
        btn_layout.addWidget(self.delete_btn)
        
        btn_layout.addStretch()
        
        self.manual_backup_btn = QPushButton("立即备份")
        self.manual_backup_btn.clicked.connect(self.on_manual_backup)
        btn_layout.addWidget(self.manual_backup_btn)
        
        self.settings_btn = QPushButton("备份设置")
        self.settings_btn.clicked.connect(self.on_backup_settings)
        btn_layout.addWidget(self.settings_btn)
        
        layout.addLayout(btn_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
    
    def refresh_backup_list(self):
        """刷新备份列表"""
        self.backup_table.setRowCount(0)
        
        # 构建查询
        query = """
            SELECT backup_filename, backup_type, backup_timestamp, 
                   file_size_bytes, user_name, app_version, backup_id
            FROM backup_records 
            WHERE 1=1
        """
        params = []
        
        # 类型筛选
        if self.backup_type_combo.currentText() != "全部":
            query += " AND backup_type = ?"
            params.append(self.backup_type_combo.currentText())
        
        # 时间筛选
        query += " AND backup_timestamp BETWEEN ? AND ?"
        params.append(self.start_time_edit.dateTime().toString("yyyy-MM-dd hh:mm:ss"))
        params.append(self.end_time_edit.dateTime().toString("yyyy-MM-dd hh:mm:ss"))
        
        query += " ORDER BY backup_timestamp DESC"
        
        backups = self.db_manager.execute_query_x(query, tuple(params))
        
        for backup in backups:
            row = self.backup_table.rowCount()
            self.backup_table.insertRow(row)
            
            self.backup_table.setItem(row, 0, QTableWidgetItem(backup[2]))
            self.backup_table.setItem(row, 1, QTableWidgetItem(backup[1]))
            
            size_str = f"{backup[3] / 1024:.1f} KB" if backup[3] else "未知"
            self.backup_table.setItem(row, 2, QTableWidgetItem(size_str))
            self.backup_table.setItem(row, 3, QTableWidgetItem(backup[4] or "未知"))
            self.backup_table.setItem(row, 4, QTableWidgetItem(backup[5] or "未知"))
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            
            info_btn = QPushButton("详情")
            info_btn.clicked.connect(lambda checked, b=backup: self.show_backup_details(b))
            btn_layout.addWidget(info_btn)
            
            self.backup_table.setCellWidget(row, 5, btn_widget)
    
    def show_backup_details(self, backup):
        """显示备份详情"""
        details = f"""
        文件名: {backup[0]}
        类型: {backup[1]}
        时间: {backup[2]}
        大小: {backup[3] / 1024:.1f} KB
        用户: {backup[4] or '未知'}
        版本: {backup[5] or '未知'}
        """
        self.backup_info_text.setPlainText(details)
    
    def on_restore_backup(self):
        """恢复备份"""
        current_row = self.backup_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "提示", "请先选择要恢复的备份")
            return
        
        backup_filename = self.backup_table.item(current_row, 0).text()
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        if not os.path.exists(backup_path):
            QMessageBox.warning(self, "警告", "备份文件不存在")
            return
        
        reply = QMessageBox.question(self, "确认恢复",
            "恢复前将自动创建回滚备份，确定要继续吗?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            self.restore_worker = RestoreWorkerX(backup_path, self.db_manager.db_path)
            self.restore_worker.progress_signal.connect(self.progress_bar.setValue)
            self.restore_worker.completion_signal.connect(self.on_restore_completed)
            self.restore_worker.start()
    
    def on_restore_completed(self, success, message):
        """恢复完成"""
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self, "成功", message)
            self.accept()  # 关闭对话框
        else:
            QMessageBox.critical(self, "错误", message)
    
    def on_delete_backup(self):
        """删除备份"""
        current_row = self.backup_table.currentRow()
        if current_row < 0:
            return
        
        backup_filename = self.backup_table.item(current_row, 0).text()
        
        reply = QMessageBox.question(self, "确认删除",
            f"确定要删除备份 '{backup_filename}' 吗?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            backup_path = os.path.join(BACKUP_DIR, backup_filename)
            if os.path.exists(backup_path):
                os.remove(backup_path)
            
            self.db_manager.execute_update_x(
                "DELETE FROM backup_records WHERE backup_filename = ?",
                (backup_filename,)
            )
            self.refresh_backup_list()
    
    def on_manual_backup(self):
        """手动备份"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        backup_name = f"manual_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        self.backup_worker = BackupWorkerX(
            self.db_manager.db_path,
            backup_path,
            "手动",
            self.current_user
        )
        self.backup_worker.progress_signal.connect(self.progress_bar.setValue)
        self.backup_worker.completion_signal.connect(self.on_manual_backup_completed)
        self.backup_worker.start()
    
    def on_manual_backup_completed(self, success, message, backup_name):
        """手动备份完成"""
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self, "成功", message)
            self.refresh_backup_list()
        else:
            QMessageBox.critical(self, "错误", message)
    
    def on_backup_settings(self):
        """备份设置"""
        max_backups, ok = QInputDialog.getInt(self, "备份设置",
            "最大自动备份数量:", MAX_BACKUP_COUNT, 1, 100)
        if ok:
            # 保存设置
            pass

class UserManagementDialogX(QDialog):
    """用户管理对话框"""
    def __init__(self, user_manager: UserManagerX, parent=None):
        super().__init__(parent)
        self.user_manager = user_manager
        self.setWindowTitle("用户管理")
        self.setMinimumSize(500, 400)
        self.setup_ui_x()
        self.refresh_user_list()
    
    def setup_ui_x(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 用户列表
        self.user_list_widget = QListWidget()
        self.user_list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.user_list_widget)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.add_user_btn = QPushButton("添加用户")
        self.add_user_btn.clicked.connect(self.on_add_user)
        btn_layout.addWidget(self.add_user_btn)
        
        self.rename_user_btn = QPushButton("重命名")
        self.rename_user_btn.clicked.connect(self.on_rename_user)
        btn_layout.addWidget(self.rename_user_btn)
        
        self.remove_user_btn = QPushButton("删除用户")
        self.remove_user_btn.clicked.connect(self.on_remove_user)
        btn_layout.addWidget(self.remove_user_btn)
        
        layout.addLayout(btn_layout)
    
    def refresh_user_list(self):
        """刷新用户列表"""
        self.user_list_widget.clear()
        for user in self.user_manager.user_list:
            item = QListWidgetItem(user)
            item.setData(Qt.UserRole, user)
            self.user_list_widget.addItem(item)
    
    def on_add_user(self):
        """添加用户"""
        username, ok = QInputDialog.getText(self, "添加用户", "请输入用户名:")
        if ok and username:
            if self.user_manager.add_new_user(username):
                self.refresh_user_list()
            else:
                QMessageBox.warning(self, "警告", "用户已存在")
    
    def on_rename_user(self):
        """重命名用户"""
        current_item = self.user_list_widget.currentItem()
        if current_item:
            old_name = current_item.text()
            new_name, ok = QInputDialog.getText(self, "重命名用户",
                f"请输入新用户名 (当前: {old_name}):")
            if ok and new_name:
                if self.user_manager.rename_existing_user(old_name, new_name):
                    self.refresh_user_list()
                else:
                    QMessageBox.warning(self, "警告", "重命名失败")
    
    def on_remove_user(self):
        """删除用户"""
        current_item = self.user_list_widget.currentItem()
        if current_item:
            username = current_item.text()
            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除用户 {username} 吗?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.user_manager.remove_existing_user(username)
                self.refresh_user_list()

class MainWindowX(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1400, 900)
        
        # 设置图标
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        
        # 初始化管理器
        self.data_directory = "user_data"
        self.user_manager = UserManagerX(self.data_directory)
        self.db_manager = DatabaseManagerX()
        self.current_user = None
        
        # 加载设置
        self.app_settings = QSettings("XMLPrekeepSpecialEditor", "Settings")
        self.debug_mode_enabled = self.app_settings.value("debug_mode", False, type=bool)
        self.auto_backup_enabled = self.app_settings.value("auto_backup", True, type=bool)
        self.max_backup_count = self.app_settings.value("max_backups", MAX_BACKUP_COUNT, type=int)
        
        # 设置UI
        self.setup_main_ui()
        self.setup_menu_bar()
        self.setup_shortcut_keys()
        self.setup_status_bar()
        
        # 初始化备份目录
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        
        # 自动备份定时器
        self.auto_backup_timer = QTimer()
        self.auto_backup_timer.timeout.connect(self.perform_auto_backup)
        if self.auto_backup_enabled:
            self.auto_backup_timer.start(3600000)  # 每小时
        
        # 显示登录对话框
        QTimer.singleShot(100, self.show_login_dialog)
    
    def setup_main_ui(self):
        """设置主UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # 顶部信息栏
        top_layout = QHBoxLayout()
        
        top_layout.addWidget(QLabel("当前用户:"))
        self.current_user_label = QLabel("未登录")
        self.current_user_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        top_layout.addWidget(self.current_user_label)
        
        top_layout.addStretch()
        
        # 文件切换
        top_layout.addWidget(QLabel("编辑文件:"))
        self.file_selector = QComboBox()
        self.file_selector.addItems(["alliedPrekeeps.xml", "prekeeps.xml"])
        self.file_selector.setMinimumWidth(200)
        top_layout.addWidget(self.file_selector)
        
        self.switch_file_btn = QPushButton("切换文件")
        self.switch_file_btn.clicked.connect(self.on_switch_file)
        top_layout.addWidget(self.switch_file_btn)
        
        main_layout.addLayout(top_layout)
        
        # Prekeep编辑器
        self.prekeep_editor = PrekeepEditorWidget()
        self.prekeep_editor.status_message_signal.connect(self.statusBar().showMessage)
        self.prekeep_editor.data_modified_signal.connect(self.on_data_modified)
        main_layout.addWidget(self.prekeep_editor)
        
        # 加载默认文件
        QTimer.singleShot(200, self.load_default_file)
    
    def setup_menu_bar(self):
        """设置菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        open_action = QAction("打开文件(&O)", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.prekeep_editor.on_load_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存文件(&S)", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.prekeep_editor.on_save_file)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 用户菜单
        user_menu = menubar.addMenu("用户(&U)")
        
        login_action = QAction("切换用户(&L)", self)
        login_action.setShortcut(QKeySequence("Ctrl+L"))
        login_action.triggered.connect(self.show_login_dialog)
        user_menu.addAction(login_action)
        
        manage_action = QAction("用户管理(&M)", self)
        manage_action.triggered.connect(self.show_user_management_dialog)
        user_menu.addAction(manage_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")
        
        backup_action = QAction("备份与恢复(&B)", self)
        backup_action.setShortcut(QKeySequence("Ctrl+B"))
        backup_action.triggered.connect(self.show_backup_dialog)
        tools_menu.addAction(backup_action)
        
        tools_menu.addSeparator()
        
        self.debug_action = QAction("调试模式(&D)", self)
        self.debug_action.setCheckable(True)
        self.debug_action.setChecked(self.debug_mode_enabled)
        self.debug_action.toggled.connect(self.on_toggle_debug_mode)
        tools_menu.addAction(self.debug_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
    
    def setup_shortcut_keys(self):
        """设置快捷键"""
        QShortcut(QKeySequence("Ctrl+F"), self, 
                 lambda: self.prekeep_editor.search_input.setFocus())
        QShortcut(QKeySequence("Ctrl+N"), self,
                 lambda: self.prekeep_editor.on_add_row())
        QShortcut(QKeySequence("Delete"), self,
                 lambda: self.prekeep_editor.on_remove_row())
    
    def setup_status_bar(self):
        """设置状态栏"""
        self.statusBar().showMessage("就绪")
        
        # 进度条
        self.status_progress = QProgressBar()
        self.status_progress.setMaximumWidth(200)
        self.status_progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.status_progress)
        
        # 文件状态
        self.file_status_label = QLabel("")
        self.statusBar().addPermanentWidget(self.file_status_label)
    
    def load_default_file(self):
        """加载默认文件"""
        default_file = self.file_selector.currentText()
        if os.path.exists(default_file):
            self.prekeep_editor.load_file(default_file)
        else:
            self.statusBar().showMessage(f"默认文件 {default_file} 不存在")
    
    def on_switch_file(self):
        """切换文件"""
        file_name = self.file_selector.currentText()
        if os.path.exists(file_name):
            self.prekeep_editor.load_file(file_name)
        else:
            QMessageBox.warning(self, "警告", f"文件 {file_name} 不存在")
    
    def show_login_dialog(self):
        """显示登录对话框"""
        if not self.user_manager.user_list:
            self.user_manager.add_new_user("默认管理员")
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择用户")
        dialog.setMinimumWidth(350)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("请选择要登录的用户:"))
        
        user_combo = QComboBox()
        user_combo.addItems(self.user_manager.user_list)
        layout.addWidget(user_combo)
        
        layout.addWidget(QLabel("(无需密码，直接登录)"))
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            username = user_combo.currentText()
            self.login_user(username)
    
    def login_user(self, username: str):
        """登录用户"""
        self.current_user = username
        self.current_user_label.setText(username)
        
        # 初始化用户数据库
        db_path = self.user_manager.get_user_database_path(username)
        if self.db_manager.initialize_database(db_path):
            self.statusBar().showMessage(f"用户 {username} 登录成功，数据库已初始化")
        else:
            self.statusBar().showMessage(f"用户 {username} 登录成功")
    
    def show_user_management_dialog(self):
        """显示用户管理对话框"""
        dialog = UserManagementDialogX(self.user_manager, self)
        if dialog.exec() == QDialog.Accepted:
            self.statusBar().showMessage("用户管理已完成")
    
    def show_backup_dialog(self):
        """显示备份对话框"""
        if not self.current_user:
            QMessageBox.warning(self, "警告", "请先登录")
            return
        
        dialog = BackupDialogX(self.db_manager, self.current_user, self)
        if dialog.exec() == QDialog.Accepted:
            # 备份恢复后可能需要重新加载数据
            self.statusBar().showMessage("备份操作完成")
    
    def perform_auto_backup(self):
        """执行自动备份"""
        if not self.current_user or not self.db_manager.db_path:
            return
        
        # 检查是否需要备份（避免频繁备份）
        backup_name = f"auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        self.backup_worker = BackupWorkerX(
            self.db_manager.db_path,
            backup_path,
            "自动",
            self.current_user
        )
        self.backup_worker.status_signal.connect(
            lambda msg: self.statusBar().showMessage(msg, 3000)
        )
        self.backup_worker.start()
        
        # 清理旧备份
        QTimer.singleShot(5000, self.clean_old_backups)
    
    def clean_old_backups(self):
        """清理旧备份"""
        backups = self.db_manager.execute_query_x(
            """SELECT backup_filename FROM backup_records 
               WHERE backup_type = '自动' 
               ORDER BY backup_timestamp DESC"""
        )
        
        if len(backups) > self.max_backup_count:
            for backup in backups[self.max_backup_count:]:
                backup_path = os.path.join(BACKUP_DIR, backup[0])
                if os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except:
                        pass
                self.db_manager.execute_update_x(
                    "DELETE FROM backup_records WHERE backup_filename = ?",
                    (backup[0],)
                )
    
    def on_toggle_debug_mode(self, enabled: bool):
        """切换调试模式"""
        self.debug_mode_enabled = enabled
        self.app_settings.setValue("debug_mode", enabled)
        
        if enabled:
            self.statusBar().showMessage("调试模式已开启")
        else:
            self.statusBar().showMessage("调试模式已关闭")
    
    def on_data_modified(self):
        """数据修改事件"""
        self.file_status_label.setText("已修改")
        self.file_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        # 5秒后恢复
        QTimer.singleShot(5000, lambda: self.file_status_label.setText(""))
    
    def show_about_dialog(self):
        """显示关于对话框"""
        about_text = f"""
        <h2>{APP_NAME}</h2>
        <p>版本: {APP_VERSION}</p>
        <hr>
        <p>专门用于编辑alliedPrekeeps.xml和prekeeps.xml文件</p>
        <p>功能特点:</p>
        <ul>
            <li>多用户管理</li>
            <li>数据库自动备份与恢复</li>
            <li>快速模板添加</li>
            <li>搜索过滤功能</li>
            <li>CSV导入导出</li>
            <li>批量操作支持</li>
        </ul>
        <hr>
        <p>© 2024 XML Prekeep Editor</p>
        """
        
        QMessageBox.about(self, "关于", about_text)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.prekeep_editor.data_model.modified:
            reply = QMessageBox.question(self, "确认退出",
                "文件有未保存的更改，确定要退出吗?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.No:
                event.ignore()
                return
        
        self.db_manager.close_connection()
        event.accept()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle(QStyleFactory.create("Fusion"))
    
    # 设置调色板
    palette = app.palette()
    palette.setColor(QPalette.Highlight, QColor(0, 102, 204))
    app.setPalette(palette)
    
    # 创建主窗口
    window = MainWindowX()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()