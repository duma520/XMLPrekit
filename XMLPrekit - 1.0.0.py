# main.py
import sys
import os
import shutil
import sqlite3
import json
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
    QInputDialog, QFrame
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QDateTime, QSettings, QTimer, QMutex, QWaitCondition, QMutexLocker
)
from PySide6.QtGui import QIcon, QFont, QAction, QKeySequence, QShortcut

# 全局常量
APP_NAME = "XML预置文件编辑器"
APP_VERSION = "1.0.0"
BACKUP_DIR = "backups"
MAX_BACKUP_COUNT = 30
DEFAULT_ENCODING = "gb2312"

class DatabaseManager:
    """数据库管理器 - 统一管理所有数据库操作"""
    _instance = None
    _lock = QMutex()
    
    def __init__(self):
        self.connection = None
        self.current_user = None
        self.db_path = None
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DatabaseManager()
        return cls._instance
    
    def initialize(self, db_path: str):
        """初始化数据库连接"""
        try:
            if self.connection:
                self.connection.close()
            
            self.db_path = db_path
            self.connection = sqlite3.connect(db_path, check_same_thread=False)
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
            return True
        except Exception as e:
            print(f"数据库初始化失败: {e}")
            return False
    
    def _create_tables(self):
        """创建数据库表"""
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backups_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_name TEXT NOT NULL,
                backup_type TEXT NOT NULL,
                backup_time TEXT NOT NULL,
                file_size INTEGER,
                db_version TEXT,
                date_range TEXT,
                user_name TEXT
            )
        """)
        self.connection.commit()
    
    def execute_query(self, query: str, params: tuple = None) -> List:
        """执行查询"""
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            print(f"查询执行失败: {e}")
            return []
    
    def execute_update(self, query: str, params: tuple = None):
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
            print(f"更新执行失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

class BackupWorker(QThread):
    """备份工作线程"""
    progress_updated = Signal(int)
    backup_completed = Signal(bool, str)
    status_message = Signal(str)
    
    def __init__(self, source_db: str, backup_path: str, backup_type: str, user_name: str):
        super().__init__()
        self.source_db = source_db
        self.backup_path = backup_path
        self.backup_type = backup_type
        self.user_name = user_name
        
    def run(self):
        try:
            self.status_message.emit(f"正在创建{self.backup_type}备份...")
            self.progress_updated.emit(10)
            
            # 确保备份目录存在
            Path(self.backup_path).parent.mkdir(parents=True, exist_ok=True)
            
            # WAL模式备份
            source_conn = sqlite3.connect(self.source_db)
            backup_conn = sqlite3.connect(self.backup_path)
            
            self.progress_updated.emit(30)
            source_conn.backup(backup_conn)
            
            self.progress_updated.emit(70)
            
            # 获取备份信息
            file_size = os.path.getsize(self.backup_path)
            backup_conn.close()
            source_conn.close()
            
            self.progress_updated.emit(90)
            
            # 更新备份信息到数据库
            db_manager = DatabaseManager.get_instance()
            db_manager.execute_update(
                """INSERT INTO backups_info (backup_name, backup_type, backup_time, file_size, db_version, user_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (os.path.basename(self.backup_path), self.backup_type,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 file_size, APP_VERSION, self.user_name)
            )
            
            self.progress_updated.emit(100)
            self.backup_completed.emit(True, f"备份完成: {os.path.basename(self.backup_path)}")
            
        except Exception as e:
            self.backup_completed.emit(False, f"备份失败: {str(e)}")

class RestoreWorker(QThread):
    """恢复工作线程"""
    progress_updated = Signal(int)
    restore_completed = Signal(bool, str)
    status_message = Signal(str)
    
    def __init__(self, backup_path: str, target_db: str):
        super().__init__()
        self.backup_path = backup_path
        self.target_db = target_db
        
    def run(self):
        try:
            self.status_message.emit("正在恢复数据库...")
            self.progress_updated.emit(10)
            
            # 先创建回滚备份
            rollback_path = self.target_db + ".rollback"
            if os.path.exists(self.target_db):
                shutil.copy2(self.target_db, rollback_path)
            
            self.progress_updated.emit(30)
            
            # 关闭当前连接
            db_manager = DatabaseManager.get_instance()
            if db_manager.connection:
                db_manager.connection.close()
            
            self.progress_updated.emit(50)
            
            # 恢复备份
            backup_conn = sqlite3.connect(self.backup_path)
            target_conn = sqlite3.connect(self.target_db)
            backup_conn.backup(target_conn)
            
            self.progress_updated.emit(80)
            
            backup_conn.close()
            target_conn.close()
            
            self.progress_updated.emit(90)
            
            # 重新初始化数据库连接
            db_manager.initialize(self.target_db)
            
            self.progress_updated.emit(100)
            self.restore_completed.emit(True, "数据库恢复成功")
            
        except Exception as e:
            self.restore_completed.emit(False, f"恢复失败: {str(e)}")

class UserManager:
    """用户管理器"""
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.ensure_data_dir()
        self.load_users()
    
    def ensure_data_dir(self):
        """确保数据目录存在"""
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
    
    def load_users(self):
        """加载用户列表"""
        if os.path.exists(self.users_file):
            with open(self.users_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.users = data.get('users', [])
        else:
            self.users = []
            self.save_users()
    
    def save_users(self):
        """保存用户列表"""
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump({'users': self.users}, f, ensure_ascii=False, indent=2)
    
    def add_user(self, username: str) -> bool:
        """添加用户"""
        if username in self.users:
            return False
        self.users.append(username)
        self.save_users()
        
        # 创建用户数据库
        user_db_path = os.path.join(self.data_dir, f"{username}.db")
        db_manager = DatabaseManager.get_instance()
        if db_manager.db_path != user_db_path:
            temp_manager = DatabaseManager()
            temp_manager.initialize(user_db_path)
            temp_manager.close()
        
        return True
    
    def remove_user(self, username: str) -> bool:
        """删除用户"""
        if username not in self.users:
            return False
        self.users.remove(username)
        self.save_users()
        return True
    
    def rename_user(self, old_name: str, new_name: str) -> bool:
        """重命名用户"""
        if new_name in self.users or old_name not in self.users:
            return False
        idx = self.users.index(old_name)
        self.users[idx] = new_name
        self.save_users()
        
        # 重命名数据库文件
        old_db = os.path.join(self.data_dir, f"{old_name}.db")
        new_db = os.path.join(self.data_dir, f"{new_name}.db")
        if os.path.exists(old_db):
            shutil.move(old_db, new_db)
        
        return True
    
    def get_user_db_path(self, username: str) -> str:
        """获取用户数据库路径"""
        return os.path.join(self.data_dir, f"{username}.db")

class XMLFileEditor(QWidget):
    """XML文件编辑器"""
    file_loaded = Signal(str)
    data_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.xml_tree = None
        self.root_element = None
        self.modified = False
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        self.file_label = QLabel("当前文件: 未加载")
        toolbar.addWidget(self.file_label)
        
        toolbar.addStretch()
        
        self.load_btn = QPushButton("加载文件")
        self.load_btn.clicked.connect(self.load_file)
        toolbar.addWidget(self.load_btn)
        
        self.save_btn = QPushButton("保存文件")
        self.save_btn.clicked.connect(self.save_file)
        self.save_btn.setEnabled(False)
        toolbar.addWidget(self.save_btn)
        
        self.reload_btn = QPushButton("重新加载")
        self.reload_btn.clicked.connect(self.reload_file)
        self.reload_btn.setEnabled(False)
        toolbar.addWidget(self.reload_btn)
        
        layout.addLayout(toolbar)
        
        # 主编辑区域
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧树形结构
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["结构"])
        self.tree_widget.setColumnCount(1)
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_tree_context_menu)
        splitter.addWidget(self.tree_widget)
        
        # 右侧编辑区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 表格编辑
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(6)
        self.table_widget.setHorizontalHeaderLabels(["国家", "城市", "X坐标", "Y坐标", "ID", "名称"])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget.itemChanged.connect(self.on_table_item_changed)
        self.table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_table_context_menu)
        right_layout.addWidget(self.table_widget)
        
        # XML文本编辑
        self.xml_editor = QTextEdit()
        self.xml_editor.setFont(QFont("Consolas", 10))
        self.xml_editor.setVisible(False)
        right_layout.addWidget(self.xml_editor)
        
        # 视图切换按钮
        view_layout = QHBoxLayout()
        self.table_view_btn = QPushButton("表格视图")
        self.table_view_btn.setCheckable(True)
        self.table_view_btn.setChecked(True)
        self.table_view_btn.clicked.connect(lambda: self.switch_view(True))
        view_layout.addWidget(self.table_view_btn)
        
        self.text_view_btn = QPushButton("文本视图")
        self.text_view_btn.setCheckable(True)
        self.text_view_btn.clicked.connect(lambda: self.switch_view(False))
        view_layout.addWidget(self.text_view_btn)
        
        view_layout.addStretch()
        right_layout.addLayout(view_layout)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 700])
        
        layout.addWidget(splitter)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.add_row_btn = QPushButton("添加行")
        self.add_row_btn.clicked.connect(self.add_row)
        self.add_row_btn.setEnabled(False)
        btn_layout.addWidget(self.add_row_btn)
        
        self.remove_row_btn = QPushButton("删除行")
        self.remove_row_btn.clicked.connect(self.remove_row)
        self.remove_row_btn.setEnabled(False)
        btn_layout.addWidget(self.remove_row_btn)
        
        self.copy_rows_btn = QPushButton("复制选中行")
        self.copy_rows_btn.clicked.connect(self.copy_selected_rows)
        self.copy_rows_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_rows_btn)
        
        self.paste_rows_btn = QPushButton("粘贴行")
        self.paste_rows_btn.clicked.connect(self.paste_rows)
        self.paste_rows_btn.setEnabled(False)
        btn_layout.addWidget(self.paste_rows_btn)
        
        self.duplicate_prekeep_btn = QPushButton("复制整个prekeep")
        self.duplicate_prekeep_btn.clicked.connect(self.duplicate_prekeep)
        self.duplicate_prekeep_btn.setEnabled(False)
        btn_layout.addWidget(self.duplicate_prekeep_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # 剪贴板
        self.clipboard = []
    
    def load_file(self, file_path: str = None):
        """加载XML文件"""
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择XML文件", "", "XML文件 (*.xml);;所有文件 (*)"
            )
        
        if file_path and os.path.exists(file_path):
            try:
                self.current_file = file_path
                self.parse_xml(file_path)
                self.file_label.setText(f"当前文件: {os.path.basename(file_path)}")
                self.save_btn.setEnabled(True)
                self.reload_btn.setEnabled(True)
                self.add_row_btn.setEnabled(True)
                self.remove_row_btn.setEnabled(True)
                self.copy_rows_btn.setEnabled(True)
                self.paste_rows_btn.setEnabled(True)
                self.duplicate_prekeep_btn.setEnabled(True)
                self.file_loaded.emit(file_path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"文件加载失败: {str(e)}")
    
    def parse_xml(self, file_path: str):
        """解析XML文件"""
        with open(file_path, 'r', encoding=DEFAULT_ENCODING) as f:
            content = f.read()
        
        # 处理编码声明
        if 'encoding="gb2312"' in content:
            content = content.replace('encoding="gb2312"', 'encoding="utf-8"')
        
        self.xml_tree = ET.fromstring(content)
        self.root_element = self.xml_tree
        self.update_tree_view()
        self.update_table_view()
    
    def update_tree_view(self):
        """更新树形视图"""
        self.tree_widget.clear()
        if self.root_element is None:
            return
        
        root_item = QTreeWidgetItem(self.tree_widget, [self.root_element.tag])
        self._populate_tree(self.root_element, root_item)
        self.tree_widget.expandAll()
    
    def _populate_tree(self, element, parent_item):
        """递归填充树形视图"""
        for child in element:
            if child.tag == "prekeep":
                user = child.get("user", "Unknown")
                item = QTreeWidgetItem(parent_item, [f"prekeep [{user}]"])
                item.setData(0, Qt.UserRole, child)
            else:
                item = QTreeWidgetItem(parent_item, [child.tag])
                item.setData(0, Qt.UserRole, child)
            self._populate_tree(child, item)
    
    def update_table_view(self, prekeep_element=None):
        """更新表格视图"""
        self.table_widget.setRowCount(0)
        
        if prekeep_element is None:
            # 显示第一个prekeep的数据
            for child in self.root_element:
                if child.tag == "prekeep":
                    prekeep_element = child
                    break
        
        if prekeep_element is None:
            return
        
        for value in prekeep_element.findall("value"):
            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)
            
            items = [
                QTableWidgetItem(value.get("country", "")),
                QTableWidgetItem(value.get("city", "")),
                QTableWidgetItem(value.get("posX", "")),
                QTableWidgetItem(value.get("posY", "")),
                QTableWidgetItem(value.get("id", "")),
                QTableWidgetItem(value.text)
            ]
            
            for col, item in enumerate(items):
                self.table_widget.setItem(row, col, item)
    
    def on_tree_item_clicked(self, item, column):
        """树形视图点击事件"""
        element = item.data(0, Qt.UserRole)
        if element is not None and element.tag == "prekeep":
            self.update_table_view(element)
    
    def on_table_item_changed(self, item):
        """表格数据改变事件"""
        if not self.modified:
            self.modified = True
            self.data_changed.emit()
    
    def switch_view(self, table_view: bool):
        """切换视图"""
        self.table_widget.setVisible(table_view)
        self.xml_editor.setVisible(not table_view)
        self.table_view_btn.setChecked(table_view)
        self.text_view_btn.setChecked(not table_view)
        
        if not table_view:
            self.update_xml_editor()
    
    def update_xml_editor(self):
        """更新XML文本编辑器"""
        if self.root_element is not None:
            rough_string = ET.tostring(self.root_element, encoding='unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            self.xml_editor.setPlainText(pretty_xml)
    
    def show_tree_context_menu(self, position):
        """显示树形视图上下文菜单"""
        menu = QMenu()
        add_prekeep_action = menu.addAction("添加新用户配置")
        remove_prekeep_action = menu.addAction("删除选中配置")
        
        action = menu.exec(self.tree_widget.viewport().mapToGlobal(position))
        
        if action == add_prekeep_action:
            self.add_prekeep()
        elif action == remove_prekeep_action:
            self.remove_prekeep()
    
    def show_table_context_menu(self, position):
        """显示表格视图上下文菜单"""
        menu = QMenu()
        copy_action = menu.addAction("复制选中行")
        paste_action = menu.addAction("粘贴行")
        menu.addSeparator()
        add_action = menu.addAction("添加新行")
        remove_action = menu.addAction("删除选中行")
        
        action = menu.exec(self.table_widget.viewport().mapToGlobal(position))
        
        if action == copy_action:
            self.copy_selected_rows()
        elif action == paste_action:
            self.paste_rows()
        elif action == add_action:
            self.add_row()
        elif action == remove_action:
            self.remove_row()
    
    def add_prekeep(self):
        """添加新prekeep"""
        user_name, ok = QInputDialog.getText(self, "添加用户配置", "请输入用户名:")
        if ok and user_name:
            new_prekeep = ET.SubElement(self.root_element, "prekeep")
            new_prekeep.set("user", user_name)
            self.update_tree_view()
            self.modified = True
            self.data_changed.emit()
    
    def remove_prekeep(self):
        """删除选中的prekeep"""
        current_item = self.tree_widget.currentItem()
        if current_item:
            element = current_item.data(0, Qt.UserRole)
            if element is not None and element.tag == "prekeep":
                reply = QMessageBox.question(self, "确认删除",
                    f"确定要删除用户 {element.get('user')} 的配置吗?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.root_element.remove(element)
                    self.update_tree_view()
                    self.update_table_view()
                    self.modified = True
                    self.data_changed.emit()
    
    def add_row(self):
        """添加新行"""
        row = self.table_widget.rowCount()
        self.table_widget.insertRow(row)
        
        default_items = [
            QTableWidgetItem("唐国"),
            QTableWidgetItem("王城"),
            QTableWidgetItem("0"),
            QTableWidgetItem("0"),
            QTableWidgetItem(str(row)),
            QTableWidgetItem("新地点")
        ]
        
        for col, item in enumerate(default_items):
            self.table_widget.setItem(row, col, item)
        
        self.modified = True
        self.data_changed.emit()
    
    def remove_row(self):
        """删除选中行"""
        selected_rows = set()
        for item in self.table_widget.selectedItems():
            selected_rows.add(item.row())
        
        for row in sorted(selected_rows, reverse=True):
            self.table_widget.removeRow(row)
        
        if selected_rows:
            self.modified = True
            self.data_changed.emit()
    
    def copy_selected_rows(self):
        """复制选中行"""
        self.clipboard = []
        selected_rows = set()
        for item in self.table_widget.selectedItems():
            selected_rows.add(item.row())
        
        for row in sorted(selected_rows):
            row_data = []
            for col in range(self.table_widget.columnCount()):
                item = self.table_widget.item(row, col)
                row_data.append(item.text() if item else "")
            self.clipboard.append(row_data)
    
    def paste_rows(self):
        """粘贴行"""
        if not self.clipboard:
            return
        
        for row_data in self.clipboard:
            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)
            
            for col, text in enumerate(row_data):
                item = QTableWidgetItem(text)
                self.table_widget.setItem(row, col, item)
        
        self.modified = True
        self.data_changed.emit()
    
    def duplicate_prekeep(self):
        """复制整个prekeep配置"""
        current_item = self.tree_widget.currentItem()
        if current_item:
            element = current_item.data(0, Qt.UserRole)
            if element is not None and element.tag == "prekeep":
                user_name, ok = QInputDialog.getText(self, "复制配置", 
                    f"正在复制 {element.get('user')} 的配置，请输入新用户名:")
                if ok and user_name:
                    import copy
                    new_prekeep = copy.deepcopy(element)
                    new_prekeep.set("user", user_name)
                    self.root_element.append(new_prekeep)
                    self.update_tree_view()
                    self.modified = True
                    self.data_changed.emit()
    
    def save_file(self):
        """保存文件"""
        if not self.current_file:
            return
        
        try:
            # 从表格更新XML
            self.sync_table_to_xml()
            
            # 保存文件
            rough_string = ET.tostring(self.root_element, encoding='unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ", encoding=DEFAULT_ENCODING)
            
            # 添加XML声明
            final_xml = '<?xml version="1.0" encoding="gb2312" ?>\n' + pretty_xml.decode(DEFAULT_ENCODING)
            
            with open(self.current_file, 'w', encoding=DEFAULT_ENCODING) as f:
                f.write(final_xml)
            
            self.modified = False
            QMessageBox.information(self, "成功", "文件保存成功")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"文件保存失败: {str(e)}")
    
    def sync_table_to_xml(self):
        """同步表格数据到XML"""
        current_item = self.tree_widget.currentItem()
        if current_item:
            element = current_item.data(0, Qt.UserRole)
            if element is not None and element.tag == "prekeep":
                # 清空现有value
                for value in element.findall("value"):
                    element.remove(value)
                
                # 从表格添加value
                for row in range(self.table_widget.rowCount()):
                    country = self.table_widget.item(row, 0).text() if self.table_widget.item(row, 0) else ""
                    city = self.table_widget.item(row, 1).text() if self.table_widget.item(row, 1) else ""
                    posX = self.table_widget.item(row, 2).text() if self.table_widget.item(row, 2) else ""
                    posY = self.table_widget.item(row, 3).text() if self.table_widget.item(row, 3) else ""
                    id_val = self.table_widget.item(row, 4).text() if self.table_widget.item(row, 4) else ""
                    name = self.table_widget.item(row, 5).text() if self.table_widget.item(row, 5) else ""
                    
                    value_elem = ET.SubElement(element, "value")
                    value_elem.set("country", country)
                    value_elem.set("city", city)
                    value_elem.set("posX", posX)
                    value_elem.set("posY", posY)
                    value_elem.set("id", id_val)
                    value_elem.text = name
    
    def reload_file(self):
        """重新加载文件"""
        if self.current_file:
            self.load_file(self.current_file)
    
    def search_content(self, search_text: str):
        """搜索内容"""
        if not search_text:
            self.update_table_view()
            return
        
        # 构建搜索索引
        search_lower = search_text.lower()
        search_pinyin = ''.join(lazy_pinyin(search_text, style=Style.NORMAL)).lower()
        search_first = ''.join(lazy_pinyin(search_text, style=Style.FIRST_LETTER)).lower()
        
        # 清空表格
        self.table_widget.setRowCount(0)
        
        for child in self.root_element:
            if child.tag == "prekeep":
                for value in child.findall("value"):
                    text = value.text or ""
                    country = value.get("country", "")
                    city = value.get("city", "")
                    
                    # 检查是否匹配
                    if self._match_search(text, country, city, search_lower, search_pinyin, search_first):
                        row = self.table_widget.rowCount()
                        self.table_widget.insertRow(row)
                        
                        items = [
                            QTableWidgetItem(country),
                            QTableWidgetItem(city),
                            QTableWidgetItem(value.get("posX", "")),
                            QTableWidgetItem(value.get("posY", "")),
                            QTableWidgetItem(value.get("id", "")),
                            QTableWidgetItem(text)
                        ]
                        
                        for col, item in enumerate(items):
                            self.table_widget.setItem(row, col, item)
    
    def _match_search(self, text, country, city, search_lower, search_pinyin, search_first):
        """检查是否匹配搜索条件"""
        text_lower = text.lower()
        text_pinyin = ''.join(lazy_pinyin(text, style=Style.NORMAL)).lower()
        text_first = ''.join(lazy_pinyin(text, style=Style.FIRST_LETTER)).lower()
        
        country_lower = country.lower()
        country_pinyin = ''.join(lazy_pinyin(country, style=Style.NORMAL)).lower()
        country_first = ''.join(lazy_pinyin(country, style=Style.FIRST_LETTER)).lower()
        
        city_lower = city.lower()
        city_pinyin = ''.join(lazy_pinyin(city, style=Style.NORMAL)).lower()
        city_first = ''.join(lazy_pinyin(city, style=Style.FIRST_LETTER)).lower()
        
        return (search_lower in text_lower or search_pinyin in text_pinyin or search_first in text_first or
                search_lower in country_lower or search_pinyin in country_pinyin or search_first in country_first or
                search_lower in city_lower or search_pinyin in city_pinyin or search_first in city_first)

class BackupDialog(QDialog):
    """备份恢复对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据库备份与恢复")
        self.setMinimumSize(800, 600)
        self.db_manager = DatabaseManager.get_instance()
        self.setup_ui()
        self.load_backups()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 筛选区域
        filter_group = QGroupBox("筛选条件")
        filter_layout = QGridLayout(filter_group)
        
        filter_layout.addWidget(QLabel("时间范围:"), 0, 0)
        self.start_date = QDateTimeEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDateTime(QDateTime.currentDateTime().addMonths(-1))
        filter_layout.addWidget(self.start_date, 0, 1)
        
        filter_layout.addWidget(QLabel("至"), 0, 2)
        self.end_date = QDateTimeEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDateTime(QDateTime.currentDateTime())
        filter_layout.addWidget(self.end_date, 0, 3)
        
        filter_layout.addWidget(QLabel("备份类型:"), 1, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["全部", "自动", "手动", "回滚"])
        filter_layout.addWidget(self.type_combo, 1, 1)
        
        self.apply_filter_btn = QPushButton("应用筛选")
        self.apply_filter_btn.clicked.connect(self.load_backups)
        filter_layout.addWidget(self.apply_filter_btn, 1, 3)
        
        layout.addWidget(filter_group)
        
        # 备份列表
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(5)
        self.backup_table.setHorizontalHeaderLabels(["备份时间", "备份类型", "文件大小", "用户", "操作"])
        self.backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.backup_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.backup_table)
        
        # 详细信息
        info_group = QGroupBox("备份详细信息")
        info_layout = QVBoxLayout(info_group)
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(100)
        info_layout.addWidget(self.info_text)
        layout.addWidget(info_group)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.restore_btn = QPushButton("恢复选中备份")
        self.restore_btn.clicked.connect(self.restore_backup)
        btn_layout.addWidget(self.restore_btn)
        
        self.rollback_btn = QPushButton("回滚选中备份")
        self.rollback_btn.clicked.connect(self.rollback_backup)
        btn_layout.addWidget(self.rollback_btn)
        
        self.delete_btn = QPushButton("删除选中备份")
        self.delete_btn.clicked.connect(self.delete_backup)
        btn_layout.addWidget(self.delete_btn)
        
        btn_layout.addStretch()
        
        self.backup_now_btn = QPushButton("立即备份")
        self.backup_now_btn.clicked.connect(self.backup_now)
        btn_layout.addWidget(self.backup_now_btn)
        
        layout.addLayout(btn_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
    
    def load_backups(self):
        """加载备份列表"""
        self.backup_table.setRowCount(0)
        
        # 构建查询条件
        query = "SELECT id, backup_name, backup_type, backup_time, file_size, user_name FROM backups_info WHERE 1=1"
        params = []
        
        if self.type_combo.currentText() != "全部":
            query += " AND backup_type = ?"
            params.append(self.type_combo.currentText())
        
        query += " AND backup_time BETWEEN ? AND ?"
        params.append(self.start_date.dateTime().toString("yyyy-MM-dd hh:mm:ss"))
        params.append(self.end_date.dateTime().toString("yyyy-MM-dd hh:mm:ss"))
        
        query += " ORDER BY backup_time DESC"
        
        backups = self.db_manager.execute_query(query, tuple(params))
        
        for backup in backups:
            row = self.backup_table.rowCount()
            self.backup_table.insertRow(row)
            
            self.backup_table.setItem(row, 0, QTableWidgetItem(backup[3]))
            self.backup_table.setItem(row, 1, QTableWidgetItem(backup[2]))
            
            size_str = f"{backup[4] / 1024:.1f} KB" if backup[4] else "未知"
            self.backup_table.setItem(row, 2, QTableWidgetItem(size_str))
            self.backup_table.setItem(row, 3, QTableWidgetItem(backup[5] or ""))
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            
            info_btn = QPushButton("详情")
            info_btn.clicked.connect(lambda checked, b=backup: self.show_backup_info(b))
            btn_layout.addWidget(info_btn)
            
            self.backup_table.setCellWidget(row, 4, btn_widget)
    
    def show_backup_info(self, backup):
        """显示备份详细信息"""
        info_text = f"""
        备份名称: {backup[1]}
        备份类型: {backup[2]}
        备份时间: {backup[3]}
        文件大小: {backup[4] / 1024:.1f} KB
        数据库版本: {APP_VERSION}
        所属用户: {backup[5] or '未知'}
        """
        self.info_text.setPlainText(info_text)
    
    def backup_now(self):
        """立即备份"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        backup_name = f"manual_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        self.worker = BackupWorker(
            self.db_manager.db_path,
            backup_path,
            "手动",
            self.db_manager.current_user or "未知"
        )
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.backup_completed.connect(self.on_backup_completed)
        self.worker.start()
    
    def restore_backup(self):
        """恢复备份"""
        current_row = self.backup_table.currentRow()
        if current_row < 0:
            return
        
        backup_name = self.backup_table.item(current_row, 0).text()
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        if not os.path.exists(backup_path):
            QMessageBox.warning(self, "警告", "备份文件不存在")
            return
        
        reply = QMessageBox.question(self, "确认恢复",
            "恢复前将自动创建回滚备份，确定要继续吗?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            self.worker = RestoreWorker(backup_path, self.db_manager.db_path)
            self.worker.progress_updated.connect(self.progress_bar.setValue)
            self.worker.restore_completed.connect(self.on_restore_completed)
            self.worker.start()
    
    def rollback_backup(self):
        """回滚备份"""
        QMessageBox.information(self, "提示", "回滚功能将恢复到最近的自动备份")
    
    def delete_backup(self):
        """删除备份"""
        current_row = self.backup_table.currentRow()
        if current_row < 0:
            return
        
        backup_name = self.backup_table.item(current_row, 0).text()
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        reply = QMessageBox.question(self, "确认删除",
            f"确定要删除备份 {backup_name} 吗?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            
            self.db_manager.execute_update(
                "DELETE FROM backups_info WHERE backup_name = ?",
                (backup_name,)
            )
            self.load_backups()
    
    def on_backup_completed(self, success, message):
        """备份完成回调"""
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self, "成功", message)
            self.load_backups()
        else:
            QMessageBox.critical(self, "错误", message)
    
    def on_restore_completed(self, success, message):
        """恢复完成回调"""
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.critical(self, "错误", message)

class UserManagementDialog(QDialog):
    """用户管理对话框"""
    def __init__(self, user_manager: UserManager, parent=None):
        super().__init__(parent)
        self.user_manager = user_manager
        self.setWindowTitle("用户管理")
        self.setMinimumSize(400, 300)
        self.setup_ui()
        self.load_users()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 用户列表
        self.user_list = QListWidget()
        layout.addWidget(self.user_list)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("添加用户")
        self.add_btn.clicked.connect(self.add_user)
        btn_layout.addWidget(self.add_btn)
        
        self.rename_btn = QPushButton("重命名")
        self.rename_btn.clicked.connect(self.rename_user)
        btn_layout.addWidget(self.rename_btn)
        
        self.remove_btn = QPushButton("删除用户")
        self.remove_btn.clicked.connect(self.remove_user)
        btn_layout.addWidget(self.remove_btn)
        
        layout.addLayout(btn_layout)
    
    def load_users(self):
        """加载用户列表"""
        self.user_list.clear()
        for user in self.user_manager.users:
            self.user_list.addItem(user)
    
    def add_user(self):
        """添加用户"""
        username, ok = QInputDialog.getText(self, "添加用户", "请输入用户名:")
        if ok and username:
            if self.user_manager.add_user(username):
                self.load_users()
            else:
                QMessageBox.warning(self, "警告", "用户已存在")
    
    def rename_user(self):
        """重命名用户"""
        current_item = self.user_list.currentItem()
        if current_item:
            old_name = current_item.text()
            new_name, ok = QInputDialog.getText(self, "重命名用户", 
                f"请输入新用户名 (当前: {old_name}):")
            if ok and new_name:
                if self.user_manager.rename_user(old_name, new_name):
                    self.load_users()
                else:
                    QMessageBox.warning(self, "警告", "重命名失败")
    
    def remove_user(self):
        """删除用户"""
        current_item = self.user_list.currentItem()
        if current_item:
            username = current_item.text()
            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除用户 {username} 吗?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.user_manager.remove_user(username)
                self.load_users()

class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 800)
        
        # 设置图标
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        
        # 初始化管理器
        self.data_dir = "user_data"
        self.user_manager = UserManager(self.data_dir)
        self.db_manager = DatabaseManager.get_instance()
        self.current_user = None
        
        # 加载设置
        self.settings = QSettings("XMLPrekeepEditor", "Settings")
        self.debug_mode = self.settings.value("debug_mode", False, type=bool)
        
        # 设置UI
        self.setup_ui()
        self.setup_menu()
        self.setup_shortcuts()
        
        # 初始化备份目录
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        
        # 自动备份定时器
        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self.auto_backup)
        self.backup_timer.start(3600000)  # 每小时自动备份
        
        # 显示登录对话框
        self.show_login_dialog()
    
    def setup_ui(self):
        """设置UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部工具栏
        top_layout = QHBoxLayout()
        
        top_layout.addWidget(QLabel("当前用户:"))
        self.user_label = QLabel("未登录")
        top_layout.addWidget(self.user_label)
        
        top_layout.addStretch()
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索 (支持中文、英文、拼音首字母)...")
        self.search_input.textChanged.connect(self.on_search)
        self.search_input.setMaximumWidth(300)
        top_layout.addWidget(self.search_input)
        
        # 文件选择
        self.file_combo = QComboBox()
        self.file_combo.addItems(["alliedPrekeeps.xml", "prekeeps.xml"])
        self.file_combo.currentTextChanged.connect(self.on_file_changed)
        top_layout.addWidget(self.file_combo)
        
        main_layout.addLayout(top_layout)
        
        # XML编辑器
        self.editor = XMLFileEditor()
        self.editor.file_loaded.connect(self.on_file_loaded)
        self.editor.data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.editor)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.status_bar.showMessage("就绪")
    
    def setup_menu(self):
        """设置菜单"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        open_action = QAction("打开文件", self)
        open_action.triggered.connect(lambda: self.editor.load_file())
        file_menu.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.triggered.connect(self.editor.save_file)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 用户菜单
        user_menu = menubar.addMenu("用户")
        
        login_action = QAction("切换用户", self)
        login_action.triggered.connect(self.show_login_dialog)
        user_menu.addAction(login_action)
        
        manage_users_action = QAction("用户管理", self)
        manage_users_action.triggered.connect(self.show_user_management)
        user_menu.addAction(manage_users_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        backup_action = QAction("备份与恢复", self)
        backup_action.triggered.connect(self.show_backup_dialog)
        tools_menu.addAction(backup_action)
        
        tools_menu.addSeparator()
        
        self.debug_action = QAction("调试模式", self)
        self.debug_action.setCheckable(True)
        self.debug_action.setChecked(self.debug_mode)
        self.debug_action.toggled.connect(self.toggle_debug_mode)
        tools_menu.addAction(self.debug_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_shortcuts(self):
        """设置快捷键"""
        QShortcut(QKeySequence("Ctrl+S"), self, self.editor.save_file)
        QShortcut(QKeySequence("Ctrl+O"), self, lambda: self.editor.load_file())
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search_input.setFocus())
    
    def show_login_dialog(self):
        """显示登录对话框"""
        if not self.user_manager.users:
            # 如果没有用户，创建默认用户
            self.user_manager.add_user("默认用户")
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择用户")
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("请选择用户:"))
        
        user_combo = QComboBox()
        user_combo.addItems(self.user_manager.users)
        layout.addWidget(user_combo)
        
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
        self.user_label.setText(username)
        
        # 初始化用户数据库
        db_path = self.user_manager.get_user_db_path(username)
        if self.db_manager.initialize(db_path):
            self.status_bar.showMessage(f"用户 {username} 登录成功")
        else:
            self.status_bar.showMessage("数据库初始化失败")
    
    def show_user_management(self):
        """显示用户管理对话框"""
        dialog = UserManagementDialog(self.user_manager, self)
        dialog.exec()
    
    def show_backup_dialog(self):
        """显示备份对话框"""
        if not self.current_user:
            QMessageBox.warning(self, "警告", "请先登录")
            return
        
        dialog = BackupDialog(self)
        dialog.exec()
    
    def auto_backup(self):
        """自动备份"""
        if not self.current_user or not self.db_manager.db_path:
            return
        
        backup_name = f"auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        
        self.worker = BackupWorker(
            self.db_manager.db_path,
            backup_path,
            "自动",
            self.current_user
        )
        self.worker.status_message.connect(self.status_bar.showMessage)
        self.worker.start()
        
        # 清理旧备份
        self.cleanup_old_backups()
    
    def cleanup_old_backups(self):
        """清理旧备份"""
        max_backups = self.settings.value("max_backups", MAX_BACKUP_COUNT, type=int)
        
        backups = self.db_manager.execute_query(
            "SELECT backup_name FROM backups_info WHERE backup_type = '自动' ORDER BY backup_time DESC"
        )
        
        if len(backups) > max_backups:
            for backup in backups[max_backups:]:
                backup_path = os.path.join(BACKUP_DIR, backup[0])
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                self.db_manager.execute_update(
                    "DELETE FROM backups_info WHERE backup_name = ?",
                    (backup[0],)
                )
    
    def toggle_debug_mode(self, enabled: bool):
        """切换调试模式"""
        self.debug_mode = enabled
        self.settings.setValue("debug_mode", enabled)
        
        if enabled:
            self.status_bar.showMessage("调试模式已开启")
        else:
            self.status_bar.showMessage("调试模式已关闭")
    
    def on_file_changed(self, file_name: str):
        """文件切换事件"""
        if os.path.exists(file_name):
            self.editor.load_file(file_name)
        else:
            self.status_bar.showMessage(f"文件 {file_name} 不存在")
    
    def on_file_loaded(self, file_path: str):
        """文件加载完成事件"""
        self.status_bar.showMessage(f"文件加载完成: {file_path}")
    
    def on_data_changed(self):
        """数据改变事件"""
        self.status_bar.showMessage("数据已修改，请保存")
    
    def on_search(self, text: str):
        """搜索事件"""
        self.editor.search_content(text)
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于",
            f"{APP_NAME}\n\n"
            f"版本: {APP_VERSION}\n\n"
            "用于编辑XML预置配置文件\n"
            "支持多用户管理和数据库备份恢复")
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.editor.modified:
            reply = QMessageBox.question(self, "确认退出",
                "有未保存的修改，确定要退出吗?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
        
        self.db_manager.close()
        event.accept()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle("Fusion")
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()