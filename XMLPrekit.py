# -*- coding: utf-8 -*-
import sys
import os
import shutil
import sqlite3
import json
import traceback
import io
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pypinyin import pinyin, Style

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QTextEdit, QSplitter,
    QStatusBar, QProgressBar, QMessageBox, QFileDialog, QDialog,
    QDialogButtonBox, QFormLayout, QGroupBox, QHeaderView, QMenu,
    QListWidget, QListWidgetItem, QAbstractItemView, QDateEdit,
    QRadioButton, QButtonGroup, QFrame, QScrollArea, QSizePolicy,
    QToolBar, QTreeWidget, QTreeWidgetItem, QStackedWidget, QGridLayout,
    QInputDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QDateTime, QDate, QSettings
from PySide6.QtGui import QIcon, QFont, QColor, QAction, QKeySequence

# 全局常量
APP_NAME = "配置文件编辑器"
APP_VERSION = "1.0.0"
DEFAULT_BACKUP_COUNT = 30
BACKUP_DIR = Path("backups")
DATABASE_NAME = "editor_data.db"
ICON_FILE = "icon.ico"

DEBUG_MODE = False


class DebugLogger:
    """调试日志管理器"""
    
    @staticmethod
    def log(message: str, module: str = "GENERAL"):
        if DEBUG_MODE:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"[{timestamp}][{module}] {message}")
    
    @staticmethod
    def error(message: str, module: str = "GENERAL"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}][{module}][ERROR] {message}")
    
    @staticmethod
    def traceback(module: str = "GENERAL"):
        if DEBUG_MODE:
            traceback.print_exc()


class XmlSimpleParser:
    """简化的XML解析器 - 使用正则表达式直接解析，避免编码问题"""
    
    @staticmethod
    def parse_attributes(tag_text: str) -> Dict[str, str]:
        """解析XML标签属性"""
        attrs = {}
        pattern = r'(\w+)="([^"]*)"'
        for match in re.finditer(pattern, tag_text):
            attrs[match.group(1)] = match.group(2)
        return attrs
    
    @staticmethod
    def parse_allied_prekeeps(file_path: str) -> List[Dict]:
        """解析alliedPrekeeps.xml"""
        try:
            with open(file_path, 'r', encoding='gb2312', errors='replace') as f:
                content = f.read()
            
            results = []
            current_user = ""
            
            # 匹配prekeep标签
            prekeep_pattern = r'<prekeep\s+user="([^"]*)"\s*>'
            value_pattern = r'<value\s+([^>]+)>(.*?)</value>'
            
            for line in content.split('\n'):
                # 检查prekeep标签
                prekeep_match = re.search(prekeep_pattern, line)
                if prekeep_match:
                    current_user = prekeep_match.group(1)
                    continue
                
                # 检查value标签
                value_match = re.search(value_pattern, line)
                if value_match:
                    attrs_str = value_match.group(1)
                    text = value_match.group(2).strip()
                    
                    attrs = XmlSimpleParser.parse_attributes(attrs_str)
                    
                    record = {
                        'user': current_user,
                        'country': attrs.get('country', ''),
                        'city': attrs.get('city', ''),
                        'posX': attrs.get('posX', ''),
                        'posY': attrs.get('posY', ''),
                        'id': attrs.get('id', ''),
                        'text': text
                    }
                    results.append(record)
            
            DebugLogger.log(f"解析alliedPrekeeps.xml完成，记录数: {len(results)}", "PARSER")
            return results
        except Exception as e:
            DebugLogger.error(f"解析alliedPrekeeps.xml失败: {str(e)}", "PARSER")
            DebugLogger.traceback("PARSER")
            return []
    
    @staticmethod
    def save_allied_prekeeps(file_path: str, data: List[Dict]):
        """保存alliedPrekeeps.xml"""
        try:
            lines = ['<?xml version="1.0" encoding="gb2312" ?>', '<prekeeps>']
            
            # 按用户分组
            user_groups = {}
            for record in data:
                user = record['user']
                if user not in user_groups:
                    user_groups[user] = []
                user_groups[user].append(record)
            
            for user, records in user_groups.items():
                lines.append(f'    <prekeep user="{user}">')
                for record in records:
                    value_line = f'        <value country="{record["country"]}" city="{record["city"]}" posX="{record["posX"]}" posY="{record["posY"]}" id="{record["id"]}">{record["text"]}</value>'
                    lines.append(value_line)
                lines.append('    </prekeep>')
            
            lines.append('</prekeeps>')
            
            content = '\n'.join(lines)
            with open(file_path, 'w', encoding='gb2312', errors='replace') as f:
                f.write(content)
            
            DebugLogger.log(f"保存alliedPrekeeps.xml成功", "PARSER")
        except Exception as e:
            DebugLogger.error(f"保存alliedPrekeeps.xml失败: {str(e)}", "PARSER")
            raise
    
    @staticmethod
    def parse_plug215(file_path: str) -> Dict[str, Any]:
        """解析plug215.xml"""
        try:
            # 尝试多种编码读取
            content = None
            for encoding in ['gb2312', 'gbk', 'utf-8', 'latin1']:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        content = f.read()
                    break
                except:
                    continue
            
            if content is None:
                raise ValueError("无法读取文件")
            
            # 清理内容 - 移除可能存在的BOM
            content = content.lstrip('\ufeff')
            
            result = {
                'global_teammembers': [],
                'plugsettings': []
            }
            
            # 查找所有plugsetting块
            plugsetting_blocks = re.findall(r'<plugsetting\s+name="([^"]*)"[^>]*>(.*?)</plugsetting>', content, re.DOTALL)
            
            for setting_name, setting_content in plugsetting_blocks:
                setting_data = {
                    'name': setting_name,
                    'basicsetting': {},
                    'highsetting': {},
                    'awsetting': {},
                    'teammembers': []
                }
                
                # 解析basicsetting
                basic_match = re.search(r'<basicsetting\s+([^>]+)/>', setting_content)
                if basic_match:
                    attrs = XmlSimpleParser.parse_attributes(basic_match.group(1))
                    # 确保所有必要属性存在
                    defaults = {
                        'bAutoAttackNpc': '1', 'bPickItem': '1', 'bAutoTeam': '1',
                        'teamInfo': '', 'pickItemInfo': '', 'fliterItem': '0', 'fixPosAttackNpc': '0'
                    }
                    for key, val in defaults.items():
                        attrs.setdefault(key, val)
                    setting_data['basicsetting'] = attrs
                
                # 解析highsetting
                high_match = re.search(r'<highsetting\s+([^>]+)/>', setting_content)
                if high_match:
                    attrs = XmlSimpleParser.parse_attributes(high_match.group(1))
                    attrs.setdefault('autobegin', '1')
                    setting_data['highsetting'] = attrs
                
                # 解析awsetting
                aw_match = re.search(r'<awsetting\s+([^>]+)>', setting_content)
                if aw_match:
                    attrs = XmlSimpleParser.parse_attributes(aw_match.group(1))
                    aw_defaults = {
                        'bUseAwMagic': '1', 'bSit': '0', 'bChangeLife': '1', 
                        'bAutoHideSkill': '1', 'sitPosX': '0', 'sitPosY': '0'
                    }
                    for key, val in aw_defaults.items():
                        attrs.setdefault(key, val)
                    setting_data['awsetting'] = attrs
                    
                    # 解析aw子元素
                    aw_child_match = re.search(r'<aw\s+([^>]+)/>', setting_content)
                    if aw_child_match:
                        aw_attrs = XmlSimpleParser.parse_attributes(aw_child_match.group(1))
                        setting_data['awsetting']['aw'] = aw_attrs
                
                # 解析teammembers
                teammember_matches = re.findall(r'<teammember\s+([^>]+)/>', setting_content)
                for member_attrs_str in teammember_matches:
                    member = XmlSimpleParser.parse_attributes(member_attrs_str)
                    member.setdefault('bloodNum', '5')
                    member.setdefault('magicNum', '1')
                    member.setdefault('AuxMagic', '0')
                    setting_data['teammembers'].append(member)
                
                result['plugsettings'].append(setting_data)
            
            # 解析不在plugsetting中的全局teammember
            # 先移除所有plugsetting内容
            content_without_settings = re.sub(r'<plugsetting.*?</plugsetting>', '', content, flags=re.DOTALL)
            global_members = re.findall(r'<teammember\s+([^>]+)/>', content_without_settings)
            for member_attrs_str in global_members:
                member = XmlSimpleParser.parse_attributes(member_attrs_str)
                member.setdefault('bloodNum', '5')
                member.setdefault('magicNum', '1')
                member.setdefault('AuxMagic', '0')
                result['global_teammembers'].append(member)
            
            DebugLogger.log(f"解析plug215.xml完成，配置数: {len(result['plugsettings'])}", "PARSER")
            return result
        except Exception as e:
            DebugLogger.error(f"解析plug215.xml失败: {str(e)}", "PARSER")
            DebugLogger.traceback("PARSER")
            return {'global_teammembers': [], 'plugsettings': []}
    
    @staticmethod
    def save_plug215(file_path: str, data: Dict[str, Any]):
        """保存plug215.xml"""
        try:
            lines = ['<?xml version="1.0" encoding="gb2312" ?>']
            
            # 全局teammember
            for member in data.get('global_teammembers', []):
                line = f'<teammember name="{member["name"]}" bloodNum="{member["bloodNum"]}" magicNum="{member["magicNum"]}" AuxMagic="{member["AuxMagic"]}" />'
                lines.append(line)
            
            # plugsettings
            if data.get('plugsettings'):
                lines.append('')
                
            for idx, setting in enumerate(data.get('plugsettings', [])):
                if idx > 0:
                    lines.append('')
                
                lines.append(f'<plugsetting name="{setting["name"]}">')
                
                # basicsetting
                basic = setting.get('basicsetting', {})
                basic_str = ' '.join([f'{k}="{v}"' for k, v in basic.items()])
                lines.append(f'    <basicsetting {basic_str} />')
                
                # highsetting
                high = setting.get('highsetting', {})
                high_str = ' '.join([f'{k}="{v}"' for k, v in high.items()])
                lines.append(f'    <highsetting {high_str} />')
                
                # awsetting
                aw = setting.get('awsetting', {})
                aw_child = aw.pop('aw', None) if 'aw' in aw else None
                aw_str = ' '.join([f'{k}="{v}"' for k, v in aw.items()])
                lines.append(f'    <awsetting {aw_str}>')
                
                if aw_child:
                    aw_child_str = ' '.join([f'{k}="{v}"' for k, v in aw_child.items()])
                    lines.append(f'        <aw {aw_child_str} />')
                
                lines.append('    </awsetting>')
                
                # teammembers
                for member in setting.get('teammembers', []):
                    member_line = f'    <teammember name="{member["name"]}" bloodNum="{member["bloodNum"]}" magicNum="{member["magicNum"]}" AuxMagic="{member["AuxMagic"]}" />'
                    lines.append(member_line)
                
                lines.append('</plugsetting>')
            
            content = '\n'.join(lines) + '\n'
            with open(file_path, 'w', encoding='gb2312', errors='replace') as f:
                f.write(content)
            
            DebugLogger.log(f"保存plug215.xml成功", "PARSER")
        except Exception as e:
            DebugLogger.error(f"保存plug215.xml失败: {str(e)}", "PARSER")
            raise
    
    @staticmethod
    def parse_prekeeps(file_path: str) -> List[Dict]:
        """解析prekeeps.xml"""
        try:
            with open(file_path, 'r', encoding='gb2312', errors='replace') as f:
                content = f.read()
            
            results = []
            current_user = ""
            
            prekeep_pattern = r'<prekeep\s+user="([^"]*)"\s*>'
            value_pattern = r'<value\s+([^>]+)>(.*?)</value>'
            
            for line in content.split('\n'):
                prekeep_match = re.search(prekeep_pattern, line)
                if prekeep_match:
                    current_user = prekeep_match.group(1)
                    continue
                
                value_match = re.search(value_pattern, line)
                if value_match:
                    attrs_str = value_match.group(1)
                    text = value_match.group(2).strip()
                    
                    attrs = XmlSimpleParser.parse_attributes(attrs_str)
                    
                    record = {
                        'user': current_user,
                        'country': attrs.get('country', ''),
                        'city': attrs.get('city', ''),
                        'posX': attrs.get('posX', ''),
                        'posY': attrs.get('posY', ''),
                        'id': attrs.get('id', ''),
                        'text': text
                    }
                    results.append(record)
            
            DebugLogger.log(f"解析prekeeps.xml完成，记录数: {len(results)}", "PARSER")
            return results
        except Exception as e:
            DebugLogger.error(f"解析prekeeps.xml失败: {str(e)}", "PARSER")
            DebugLogger.traceback("PARSER")
            return []
    
    @staticmethod
    def save_prekeeps(file_path: str, data: List[Dict]):
        """保存prekeeps.xml"""
        try:
            lines = ['<?xml version="1.0" encoding="gb2312" ?>', '<prekeeps>']
            
            user_groups = {}
            for record in data:
                user = record['user']
                if user not in user_groups:
                    user_groups[user] = []
                user_groups[user].append(record)
            
            for user, records in user_groups.items():
                lines.append(f'    <prekeep user="{user}">')
                for record in records:
                    value_line = f'        <value country="{record["country"]}" city="{record["city"]}" posX="{record["posX"]}" posY="{record["posY"]}" id="{record["id"]}">{record["text"]}</value>'
                    lines.append(value_line)
                lines.append('    </prekeep>')
            
            lines.append('</prekeeps>')
            
            content = '\n'.join(lines)
            with open(file_path, 'w', encoding='gb2312', errors='replace') as f:
                f.write(content)
            
            DebugLogger.log(f"保存prekeeps.xml成功", "PARSER")
        except Exception as e:
            DebugLogger.error(f"保存prekeeps.xml失败: {str(e)}", "PARSER")
            raise


class DatabaseManager:
    """数据库管理器 - SQLite WAL模式"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        DebugLogger.log(f"初始化数据库管理器: {db_path}", "DB")
    
    def connect(self):
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=NORMAL")
            self.connection.execute("PRAGMA cache_size=-2000")
            self.connection.execute("PRAGMA temp_store=MEMORY")
            self.connection.row_factory = sqlite3.Row
            DebugLogger.log("数据库连接成功", "DB")
        except Exception as e:
            DebugLogger.error(f"数据库连接失败: {str(e)}", "DB")
            raise
    
    def disconnect(self):
        if self.connection:
            try:
                self.connection.close()
                DebugLogger.log("数据库连接已断开", "DB")
            except Exception as e:
                DebugLogger.error(f"断开数据库连接失败: {str(e)}", "DB")
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        if not self.connection:
            self.connect()
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor
    
    def commit(self):
        if self.connection:
            self.connection.commit()
    
    def rollback(self):
        if self.connection:
            self.connection.rollback()
    
    def initialize_tables(self):
        try:
            self.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS backup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_time DATETIME NOT NULL,
                    backup_type TEXT NOT NULL,
                    file_size INTEGER,
                    file_path TEXT NOT NULL,
                    db_version TEXT,
                    date_range_start TEXT,
                    date_range_end TEXT,
                    note TEXT
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS directory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    directory_path TEXT UNIQUE NOT NULL,
                    last_access_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1
                )
            """)
            
            self.commit()
            DebugLogger.log("数据库表初始化完成", "DB")
        except Exception as e:
            DebugLogger.error(f"数据库表初始化失败: {str(e)}", "DB")
            raise


class BackupManager:
    """备份管理器"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.backup_dir = BACKUP_DIR
        self.backup_dir.mkdir(exist_ok=True)
    
    def create_backup(self, backup_type: str = "自动", note: str = "") -> Optional[str]:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{timestamp}_{backup_type}.db"
            backup_path = self.backup_dir / backup_filename
            
            self.db_manager.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            shutil.copy2(self.db_manager.db_path, backup_path)
            
            file_size = backup_path.stat().st_size
            self.db_manager.execute("""
                INSERT INTO backup_history 
                (backup_time, backup_type, file_size, file_path, db_version, note)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), backup_type, file_size, 
                  str(backup_path), APP_VERSION, note))
            self.db_manager.commit()
            
            self._cleanup_old_backups()
            DebugLogger.log(f"备份创建成功: {backup_path}", "BACKUP")
            return str(backup_path)
        except Exception as e:
            DebugLogger.error(f"备份创建失败: {str(e)}", "BACKUP")
            return None
    
    def _cleanup_old_backups(self):
        try:
            max_backups = int(self._get_setting("max_backups", str(DEFAULT_BACKUP_COUNT)))
            
            cursor = self.db_manager.execute("""
                SELECT file_path FROM backup_history 
                ORDER BY backup_time DESC
                LIMIT -1 OFFSET ?
            """, (max_backups,))
            
            for row in cursor.fetchall():
                file_path = Path(row[0])
                if file_path.exists():
                    file_path.unlink()
            
            self.db_manager.execute("""
                DELETE FROM backup_history WHERE id NOT IN (
                    SELECT id FROM backup_history 
                    ORDER BY backup_time DESC 
                    LIMIT ?
                )
            """, (max_backups,))
            self.db_manager.commit()
        except Exception as e:
            DebugLogger.error(f"清理旧备份失败: {str(e)}", "BACKUP")
    
    def get_backup_list(self, start_date=None, end_date=None, backup_type=None) -> List[Dict]:
        try:
            query = "SELECT * FROM backup_history WHERE 1=1"
            params = []
            
            if start_date:
                query += " AND backup_time >= ?"
                params.append(start_date.toString(Qt.ISODate) + "T00:00:00")
            
            if end_date:
                query += " AND backup_time <= ?"
                params.append(end_date.toString(Qt.ISODate) + "T23:59:59")
            
            if backup_type and backup_type != "全部":
                query += " AND backup_type = ?"
                params.append(backup_type)
            
            query += " ORDER BY backup_time DESC"
            
            cursor = self.db_manager.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            DebugLogger.error(f"获取备份列表失败: {str(e)}", "BACKUP")
            return []
    
    def restore_backup(self, backup_path: str) -> bool:
        try:
            self.create_backup("回滚", "恢复前自动备份")
            self.db_manager.disconnect()
            shutil.copy2(backup_path, self.db_manager.db_path)
            self.db_manager.connect()
            DebugLogger.log(f"数据库恢复成功: {backup_path}", "BACKUP")
            return True
        except Exception as e:
            DebugLogger.error(f"数据库恢复失败: {str(e)}", "BACKUP")
            return False
    
    def _get_setting(self, key: str, default: str = "") -> str:
        try:
            cursor = self.db_manager.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else default
        except:
            return default


class SearchUtil:
    """搜索工具类"""
    
    @staticmethod
    def get_pinyin_initials(text: str) -> str:
        try:
            if not text:
                return ""
            result = []
            for char in text:
                if '\u4e00' <= char <= '\u9fff':
                    py = pinyin(char, style=Style.FIRST_LETTER)
                    if py and py[0]:
                        result.append(py[0][0].upper())
                else:
                    result.append(char.upper())
            return ''.join(result)
        except:
            return text.upper()
    
    @staticmethod
    def match_text(source: str, search: str) -> bool:
        if not search:
            return True
        
        search_lower = search.lower()
        source_lower = str(source).lower()
        
        if search_lower in source_lower:
            return True
        
        source_pinyin = SearchUtil.get_pinyin_initials(str(source))
        if search_lower in source_pinyin.lower():
            return True
        
        return False


class WorkerThread(QThread):
    """工作线程基类"""
    finished_signal = Signal(object)
    error_signal = Signal(str)
    progress_signal = Signal(int, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = True
    
    def stop(self):
        self.is_running = False


class FileLoadWorker(WorkerThread):
    """文件加载工作线程"""
    
    def __init__(self, directory: str, parent=None):
        super().__init__(parent)
        self.directory = directory
    
    def run(self):
        try:
            result = {
                'allied_prekeeps': [],
                'plug215': {},
                'prekeeps': []
            }
            
            allied_path = os.path.join(self.directory, 'alliedPrekeeps.xml')
            plug_path = os.path.join(self.directory, 'plug215.xml')
            prekeeps_path = os.path.join(self.directory, 'prekeeps.xml')
            
            if os.path.exists(allied_path):
                self.progress_signal.emit(30, "正在加载alliedPrekeeps.xml...")
                result['allied_prekeeps'] = XmlSimpleParser.parse_allied_prekeeps(allied_path)
            
            if os.path.exists(plug_path):
                self.progress_signal.emit(60, "正在加载plug215.xml...")
                result['plug215'] = XmlSimpleParser.parse_plug215(plug_path)
            
            if os.path.exists(prekeeps_path):
                self.progress_signal.emit(90, "正在加载prekeeps.xml...")
                result['prekeeps'] = XmlSimpleParser.parse_prekeeps(prekeeps_path)
            
            self.progress_signal.emit(100, "加载完成")
            self.finished_signal.emit(result)
        except Exception as e:
            DebugLogger.error(f"文件加载失败: {str(e)}", "WORKER")
            self.error_signal.emit(str(e))


class FileSaveWorker(WorkerThread):
    """文件保存工作线程"""
    
    def __init__(self, directory: str, data: Dict, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.data = data
    
    def run(self):
        try:
            allied_path = os.path.join(self.directory, 'alliedPrekeeps.xml')
            plug_path = os.path.join(self.directory, 'plug215.xml')
            prekeeps_path = os.path.join(self.directory, 'prekeeps.xml')
            
            os.makedirs(self.directory, exist_ok=True)
            
            if 'allied_prekeeps' in self.data:
                self.progress_signal.emit(30, "正在保存alliedPrekeeps.xml...")
                XmlSimpleParser.save_allied_prekeeps(allied_path, self.data['allied_prekeeps'])
            
            if 'plug215' in self.data:
                self.progress_signal.emit(60, "正在保存plug215.xml...")
                XmlSimpleParser.save_plug215(plug_path, self.data['plug215'])
            
            if 'prekeeps' in self.data:
                self.progress_signal.emit(90, "正在保存prekeeps.xml...")
                XmlSimpleParser.save_prekeeps(prekeeps_path, self.data['prekeeps'])
            
            self.progress_signal.emit(100, "保存完成")
            self.finished_signal.emit(True)
        except Exception as e:
            DebugLogger.error(f"文件保存失败: {str(e)}", "WORKER")
            self.error_signal.emit(str(e))


class BackupRestoreDialog(QDialog):
    """数据库备份恢复对话框"""
    
    def __init__(self, backup_manager: BackupManager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.selected_backup_path = None
        self.init_ui()
        self.load_backup_list()
    
    def init_ui(self):
        self.setWindowTitle("数据库备份与恢复")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(self)
        
        filter_group = QGroupBox("筛选条件")
        filter_layout = QHBoxLayout(filter_group)
        
        filter_layout.addWidget(QLabel("开始日期:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.start_date_edit)
        
        filter_layout.addWidget(QLabel("结束日期:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        filter_layout.addWidget(self.end_date_edit)
        
        filter_layout.addWidget(QLabel("备份类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["全部", "自动", "手动", "回滚"])
        filter_layout.addWidget(self.type_combo)
        
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.load_backup_list)
        filter_layout.addWidget(search_btn)
        
        layout.addWidget(filter_group)
        
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(7)
        self.backup_table.setHorizontalHeaderLabels(
            ["备份时间", "备份类型", "文件大小(KB)", "数据库版本", "操作", "日期范围", "备注"]
        )
        self.backup_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.backup_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.backup_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.backup_table)
        
        preview_group = QGroupBox("备份详情")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        preview_layout.addWidget(self.preview_text)
        layout.addWidget(preview_group)
        
        button_layout = QHBoxLayout()
        
        self.create_backup_btn = QPushButton("手动备份")
        self.create_backup_btn.clicked.connect(self.create_manual_backup)
        button_layout.addWidget(self.create_backup_btn)
        
        self.restore_btn = QPushButton("恢复选中备份")
        self.restore_btn.clicked.connect(self.restore_selected_backup)
        self.restore_btn.setEnabled(False)
        button_layout.addWidget(self.restore_btn)
        
        self.delete_btn = QPushButton("删除选中备份")
        self.delete_btn.clicked.connect(self.delete_selected_backup)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def load_backup_list(self):
        start_date = self.start_date_edit.date()
        end_date = self.end_date_edit.date()
        backup_type = self.type_combo.currentText()
        
        backups = self.backup_manager.get_backup_list(start_date, end_date, backup_type)
        
        self.backup_table.setRowCount(len(backups))
        for i, backup in enumerate(backups):
            backup_time = backup.get('backup_time', '')
            if backup_time:
                try:
                    dt = datetime.fromisoformat(backup_time)
                    backup_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            
            file_size = round(backup.get('file_size', 0) / 1024, 2)
            
            self.backup_table.setItem(i, 0, QTableWidgetItem(backup_time))
            self.backup_table.setItem(i, 1, QTableWidgetItem(backup.get('backup_type', '')))
            self.backup_table.setItem(i, 2, QTableWidgetItem(str(file_size)))
            self.backup_table.setItem(i, 3, QTableWidgetItem(backup.get('db_version', '')))
            
            select_btn = QPushButton("选择")
            path = backup.get('file_path', '')
            select_btn.clicked.connect(lambda checked, p=path: self.select_backup(p))
            self.backup_table.setCellWidget(i, 4, select_btn)
            
            self.backup_table.setItem(i, 5, QTableWidgetItem("N/A"))
            self.backup_table.setItem(i, 6, QTableWidgetItem(backup.get('note', '')))
        
        self.backup_table.resizeColumnsToContents()
    
    def select_backup(self, path: str):
        self.selected_backup_path = path
        self.restore_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        
        if os.path.exists(path):
            file_size = os.path.getsize(path) / 1024
            self.preview_text.setText(
                f"已选择备份文件:\n"
                f"路径: {path}\n"
                f"大小: {file_size:.2f} KB\n"
                f"创建时间: {datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')}"
            )
    
    def create_manual_backup(self):
        result = self.backup_manager.create_backup("手动", "用户手动备份")
        if result:
            QMessageBox.information(self, "成功", f"备份创建成功!\n{result}")
            self.load_backup_list()
        else:
            QMessageBox.warning(self, "失败", "备份创建失败!")
    
    def restore_selected_backup(self):
        if not self.selected_backup_path:
            return
        
        reply = QMessageBox.question(
            self, "确认恢复", 
            "恢复操作将替换当前数据库，系统会在恢复前自动创建回滚备份。\n确认继续?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.backup_manager.restore_backup(self.selected_backup_path):
                QMessageBox.information(self, "成功", "数据库恢复成功!")
                self.accept()
            else:
                QMessageBox.warning(self, "失败", "数据库恢复失败!")
    
    def delete_selected_backup(self):
        if not self.selected_backup_path:
            return
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确认删除备份文件?\n{self.selected_backup_path}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                os.remove(self.selected_backup_path)
                self.selected_backup_path = None
                self.restore_btn.setEnabled(False)
                self.delete_btn.setEnabled(False)
                self.load_backup_list()
                QMessageBox.information(self, "成功", "备份文件已删除!")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {str(e)}")


class Plugin215Editor(QWidget):
    """plug215.xml编辑器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {'global_teammembers': [], 'plugsettings': []}
        self.current_setting = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        toolbar = QHBoxLayout()
        
        self.setting_combo = QComboBox()
        self.setting_combo.currentIndexChanged.connect(self.on_setting_changed)
        toolbar.addWidget(QLabel("选择配置:"))
        toolbar.addWidget(self.setting_combo)
        
        add_setting_btn = QPushButton("添加配置")
        add_setting_btn.clicked.connect(self.add_setting)
        toolbar.addWidget(add_setting_btn)
        
        delete_setting_btn = QPushButton("删除配置")
        delete_setting_btn.clicked.connect(self.delete_setting)
        toolbar.addWidget(delete_setting_btn)
        
        copy_setting_btn = QPushButton("复制配置")
        copy_setting_btn.clicked.connect(self.copy_setting)
        toolbar.addWidget(copy_setting_btn)
        
        toolbar.addStretch()
        
        toolbar.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入搜索内容...")
        self.search_edit.textChanged.connect(self.filter_data)
        self.search_edit.setMaximumWidth(200)
        toolbar.addWidget(self.search_edit)
        
        layout.addLayout(toolbar)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("团队成员:"))
        
        self.member_table = QTableWidget()
        self.member_table.setColumnCount(5)
        self.member_table.setHorizontalHeaderLabels(["角色名", "血量", "魔法", "辅助魔法", "操作"])
        self.member_table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self.member_table)
        
        member_btn_layout = QHBoxLayout()
        add_member_btn = QPushButton("添加成员")
        add_member_btn.clicked.connect(self.add_member)
        member_btn_layout.addWidget(add_member_btn)
        
        delete_member_btn = QPushButton("删除选中")
        delete_member_btn.clicked.connect(self.delete_member)
        member_btn_layout.addWidget(delete_member_btn)
        
        left_layout.addLayout(member_btn_layout)
        splitter.addWidget(left_widget)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        basic_group = QGroupBox("基本设置")
        basic_layout = QFormLayout(basic_group)
        
        self.auto_attack_check = QCheckBox("自动攻击NPC")
        basic_layout.addRow(self.auto_attack_check)
        
        self.pick_item_check = QCheckBox("自动拾取物品")
        basic_layout.addRow(self.pick_item_check)
        
        self.auto_team_check = QCheckBox("自动组队")
        basic_layout.addRow(self.auto_team_check)
        
        team_info_layout = QHBoxLayout()
        team_info_layout.addWidget(QLabel("组队信息:"))
        self.team_info_edit = QLineEdit()
        team_info_layout.addWidget(self.team_info_edit)
        basic_layout.addRow(team_info_layout)
        
        pick_item_layout = QHBoxLayout()
        pick_item_layout.addWidget(QLabel("拾取物品:"))
        self.pick_item_edit = QLineEdit()
        pick_item_layout.addWidget(self.pick_item_edit)
        basic_layout.addRow(pick_item_layout)
        
        right_layout.addWidget(basic_group)
        
        high_group = QGroupBox("高级设置")
        high_layout = QFormLayout(high_group)
        self.auto_begin_check = QCheckBox("自动开始")
        high_layout.addRow(self.auto_begin_check)
        right_layout.addWidget(high_group)
        
        aw_group = QGroupBox("辅助设置")
        aw_layout = QFormLayout(aw_group)
        
        self.use_aw_check = QCheckBox("使用辅助魔法")
        aw_layout.addRow(self.use_aw_check)
        
        self.sit_check = QCheckBox("自动打坐")
        aw_layout.addRow(self.sit_check)
        
        self.change_life_check = QCheckBox("自动转换生命")
        aw_layout.addRow(self.change_life_check)
        
        self.hide_skill_check = QCheckBox("自动隐藏技能")
        aw_layout.addRow(self.hide_skill_check)
        
        right_layout.addWidget(aw_group)
        right_layout.addStretch()
        
        splitter.addWidget(right_widget)
        layout.addWidget(splitter)
    
    def load_data(self, data: Dict):
        self.data = data
        self.refresh_setting_combo()
    
    def refresh_setting_combo(self):
        self.setting_combo.blockSignals(True)
        self.setting_combo.clear()
        for setting in self.data.get('plugsettings', []):
            self.setting_combo.addItem(setting.get('name', 'Unknown'))
        self.setting_combo.blockSignals(False)
        
        if self.setting_combo.count() > 0:
            self.setting_combo.setCurrentIndex(0)
    
    def on_setting_changed(self, index: int):
        if index >= 0 and index < len(self.data.get('plugsettings', [])):
            self.save_setting_data()
            self.current_setting = self.data['plugsettings'][index]
            self.load_setting_data()
    
    def load_setting_data(self):
        if not self.current_setting:
            return
        
        basic = self.current_setting.get('basicsetting', {})
        self.auto_attack_check.setChecked(basic.get('bAutoAttackNpc', '1') == '1')
        self.pick_item_check.setChecked(basic.get('bPickItem', '1') == '1')
        self.auto_team_check.setChecked(basic.get('bAutoTeam', '1') == '1')
        self.team_info_edit.setText(basic.get('teamInfo', ''))
        self.pick_item_edit.setText(basic.get('pickItemInfo', ''))
        
        high = self.current_setting.get('highsetting', {})
        self.auto_begin_check.setChecked(high.get('autobegin', '1') == '1')
        
        aw = self.current_setting.get('awsetting', {})
        self.use_aw_check.setChecked(aw.get('bUseAwMagic', '1') == '1')
        self.sit_check.setChecked(aw.get('bSit', '0') == '1')
        self.change_life_check.setChecked(aw.get('bChangeLife', '1') == '1')
        self.hide_skill_check.setChecked(aw.get('bAutoHideSkill', '1') == '1')
        
        self.load_member_table()
    
    def load_member_table(self):
        if not self.current_setting:
            return
        
        members = self.current_setting.get('teammembers', [])
        search_text = self.search_edit.text().strip()
        
        filtered_members = []
        for member in members:
            if search_text:
                if SearchUtil.match_text(member.get('name', ''), search_text):
                    filtered_members.append(member)
            else:
                filtered_members.append(member)
        
        self.member_table.setRowCount(len(filtered_members))
        for i, member in enumerate(filtered_members):
            self.member_table.setItem(i, 0, QTableWidgetItem(member.get('name', '')))
            self.member_table.setItem(i, 1, QTableWidgetItem(member.get('bloodNum', '')))
            self.member_table.setItem(i, 2, QTableWidgetItem(member.get('magicNum', '')))
            self.member_table.setItem(i, 3, QTableWidgetItem(member.get('AuxMagic', '')))
            
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, row=i: self.edit_member(row))
            self.member_table.setCellWidget(i, 4, edit_btn)
    
    def add_setting(self):
        name, ok = QInputDialog.getText(self, "添加配置", "请输入配置名称:")
        if ok and name:
            new_setting = {
                'name': name,
                'basicsetting': {
                    'bAutoAttackNpc': '1', 'bPickItem': '1', 'bAutoTeam': '1',
                    'teamInfo': '', 'pickItemInfo': '', 'fliterItem': '0', 'fixPosAttackNpc': '0'
                },
                'highsetting': {'autobegin': '1'},
                'awsetting': {
                    'bUseAwMagic': '1', 'bSit': '0', 'bChangeLife': '1', 'bAutoHideSkill': '1',
                    'sitPosX': '0', 'sitPosY': '0',
                    'aw': {
                        'skillId': '0', 'bloodNum': '5', 'magicNum': '1', 'AuxMagic': '0',
                        'selfskillId': '0', 'slefbloodNum': '5', 'selfmagicNum': '0', 'selfAuxMagic': '7'
                    }
                },
                'teammembers': []
            }
            self.data['plugsettings'].append(new_setting)
            self.refresh_setting_combo()
            self.setting_combo.setCurrentIndex(len(self.data['plugsettings']) - 1)
    
    def delete_setting(self):
        if self.current_setting:
            reply = QMessageBox.question(self, "确认删除", 
                f"确认删除配置 '{self.current_setting.get('name')}'?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.data['plugsettings'].remove(self.current_setting)
                self.current_setting = None
                self.refresh_setting_combo()
                self.member_table.setRowCount(0)
    
    def copy_setting(self):
        if self.current_setting:
            import copy
            new_setting = copy.deepcopy(self.current_setting)
            new_setting['name'] = self.current_setting['name'] + "_副本"
            self.data['plugsettings'].append(new_setting)
            self.refresh_setting_combo()
            self.setting_combo.setCurrentIndex(len(self.data['plugsettings']) - 1)
    
    def add_member(self):
        if not self.current_setting:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("添加成员")
        layout = QFormLayout(dialog)
        
        name_edit = QLineEdit()
        layout.addRow("角色名:", name_edit)
        
        blood_spin = QSpinBox()
        blood_spin.setRange(0, 100)
        blood_spin.setValue(5)
        layout.addRow("血量:", blood_spin)
        
        magic_spin = QSpinBox()
        magic_spin.setRange(0, 100)
        magic_spin.setValue(1)
        layout.addRow("魔法:", magic_spin)
        
        aux_spin = QSpinBox()
        aux_spin.setRange(0, 100)
        aux_spin.setValue(0)
        layout.addRow("辅助魔法:", aux_spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            member = {
                'name': name_edit.text(),
                'bloodNum': str(blood_spin.value()),
                'magicNum': str(magic_spin.value()),
                'AuxMagic': str(aux_spin.value())
            }
            self.current_setting.setdefault('teammembers', []).append(member)
            self.load_member_table()
    
    def edit_member(self, row: int):
        if not self.current_setting:
            return
        
        members = self.current_setting.get('teammembers', [])
        search_text = self.search_edit.text().strip()
        
        if search_text:
            filtered = [m for m in members if SearchUtil.match_text(m.get('name', ''), search_text)]
        else:
            filtered = members
        
        if row >= len(filtered):
            return
        
        member = filtered[row]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑成员")
        layout = QFormLayout(dialog)
        
        name_edit = QLineEdit(member.get('name', ''))
        layout.addRow("角色名:", name_edit)
        
        blood_spin = QSpinBox()
        blood_spin.setRange(0, 100)
        blood_spin.setValue(int(member.get('bloodNum', '5')))
        layout.addRow("血量:", blood_spin)
        
        magic_spin = QSpinBox()
        magic_spin.setRange(0, 100)
        magic_spin.setValue(int(member.get('magicNum', '1')))
        layout.addRow("魔法:", magic_spin)
        
        aux_spin = QSpinBox()
        aux_spin.setRange(0, 100)
        aux_spin.setValue(int(member.get('AuxMagic', '0')))
        layout.addRow("辅助魔法:", aux_spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            member['name'] = name_edit.text()
            member['bloodNum'] = str(blood_spin.value())
            member['magicNum'] = str(magic_spin.value())
            member['AuxMagic'] = str(aux_spin.value())
            self.load_member_table()
    
    def delete_member(self):
        if not self.current_setting:
            return
        
        current_row = self.member_table.currentRow()
        members = self.current_setting.get('teammembers', [])
        
        if current_row >= 0 and current_row < len(members):
            reply = QMessageBox.question(self, "确认删除", "确认删除选中成员?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                del members[current_row]
                self.load_member_table()
    
    def filter_data(self):
        self.load_member_table()
    
    def save_setting_data(self):
        if not self.current_setting:
            return
        
        basic = self.current_setting.setdefault('basicsetting', {})
        basic['bAutoAttackNpc'] = '1' if self.auto_attack_check.isChecked() else '0'
        basic['bPickItem'] = '1' if self.pick_item_check.isChecked() else '0'
        basic['bAutoTeam'] = '1' if self.auto_team_check.isChecked() else '0'
        basic['teamInfo'] = self.team_info_edit.text()
        basic['pickItemInfo'] = self.pick_item_edit.text()
        
        high = self.current_setting.setdefault('highsetting', {})
        high['autobegin'] = '1' if self.auto_begin_check.isChecked() else '0'
        
        aw = self.current_setting.setdefault('awsetting', {})
        aw['bUseAwMagic'] = '1' if self.use_aw_check.isChecked() else '0'
        aw['bSit'] = '1' if self.sit_check.isChecked() else '0'
        aw['bChangeLife'] = '1' if self.change_life_check.isChecked() else '0'
        aw['bAutoHideSkill'] = '1' if self.hide_skill_check.isChecked() else '0'
    
    def get_data(self) -> Dict:
        self.save_setting_data()
        return self.data


class PrekeepEditor(QWidget):
    """Prekeep编辑器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        toolbar = QHBoxLayout()
        
        add_btn = QPushButton("添加记录")
        add_btn.clicked.connect(self.add_record)
        toolbar.addWidget(add_btn)
        
        delete_btn = QPushButton("删除选中")
        delete_btn.clicked.connect(self.delete_record)
        toolbar.addWidget(delete_btn)
        
        copy_btn = QPushButton("复制记录")
        copy_btn.clicked.connect(self.copy_record)
        toolbar.addWidget(copy_btn)
        
        toolbar.addStretch()
        
        toolbar.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入搜索内容...")
        self.search_edit.textChanged.connect(self.filter_data)
        self.search_edit.setMaximumWidth(200)
        toolbar.addWidget(self.search_edit)
        
        layout.addLayout(toolbar)
        
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["用户", "国家", "城市", "X坐标", "Y坐标", "ID", "文本", "操作"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
    
    def load_data(self, data: List[Dict]):
        self.data = data
        self.refresh_table()
    
    def refresh_table(self):
        search_text = self.search_edit.text().strip()
        
        filtered_data = []
        for record in self.data:
            if search_text:
                match = False
                for key, value in record.items():
                    if SearchUtil.match_text(str(value), search_text):
                        match = True
                        break
                if match:
                    filtered_data.append(record)
            else:
                filtered_data.append(record)
        
        self.table.setRowCount(len(filtered_data))
        for i, record in enumerate(filtered_data):
            self.table.setItem(i, 0, QTableWidgetItem(record.get('user', '')))
            self.table.setItem(i, 1, QTableWidgetItem(record.get('country', '')))
            self.table.setItem(i, 2, QTableWidgetItem(record.get('city', '')))
            self.table.setItem(i, 3, QTableWidgetItem(record.get('posX', '')))
            self.table.setItem(i, 4, QTableWidgetItem(record.get('posY', '')))
            self.table.setItem(i, 5, QTableWidgetItem(record.get('id', '')))
            self.table.setItem(i, 6, QTableWidgetItem(record.get('text', '')))
            
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, row=i: self.edit_record(row))
            self.table.setCellWidget(i, 7, edit_btn)
        
        self.table.resizeColumnsToContents()
    
    def add_record(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加记录")
        layout = QFormLayout(dialog)
        
        user_edit = QLineEdit()
        layout.addRow("用户:", user_edit)
        
        country_edit = QLineEdit()
        layout.addRow("国家:", country_edit)
        
        city_edit = QLineEdit()
        layout.addRow("城市:", city_edit)
        
        posx_spin = QSpinBox()
        posx_spin.setRange(0, 9999)
        layout.addRow("X坐标:", posx_spin)
        
        posy_spin = QSpinBox()
        posy_spin.setRange(0, 9999)
        layout.addRow("Y坐标:", posy_spin)
        
        id_spin = QSpinBox()
        id_spin.setRange(0, 9999)
        layout.addRow("ID:", id_spin)
        
        text_edit = QLineEdit()
        layout.addRow("文本:", text_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            record = {
                'user': user_edit.text(),
                'country': country_edit.text(),
                'city': city_edit.text(),
                'posX': str(posx_spin.value()),
                'posY': str(posy_spin.value()),
                'id': str(id_spin.value()),
                'text': text_edit.text()
            }
            self.data.append(record)
            self.refresh_table()
    
    def edit_record(self, row: int):
        search_text = self.search_edit.text().strip()
        if search_text:
            filtered = [r for r in self.data if any(
                SearchUtil.match_text(str(v), search_text) for v in r.values()
            )]
            if row < len(filtered):
                record = filtered[row]
            else:
                return
        else:
            if row >= len(self.data):
                return
            record = self.data[row]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑记录")
        layout = QFormLayout(dialog)
        
        user_edit = QLineEdit(record.get('user', ''))
        layout.addRow("用户:", user_edit)
        
        country_edit = QLineEdit(record.get('country', ''))
        layout.addRow("国家:", country_edit)
        
        city_edit = QLineEdit(record.get('city', ''))
        layout.addRow("城市:", city_edit)
        
        posx_spin = QSpinBox()
        posx_spin.setRange(0, 9999)
        posx_spin.setValue(int(record.get('posX', '0')))
        layout.addRow("X坐标:", posx_spin)
        
        posy_spin = QSpinBox()
        posy_spin.setRange(0, 9999)
        posy_spin.setValue(int(record.get('posY', '0')))
        layout.addRow("Y坐标:", posy_spin)
        
        id_spin = QSpinBox()
        id_spin.setRange(0, 9999)
        id_spin.setValue(int(record.get('id', '0')))
        layout.addRow("ID:", id_spin)
        
        text_edit = QLineEdit(record.get('text', ''))
        layout.addRow("文本:", text_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            record['user'] = user_edit.text()
            record['country'] = country_edit.text()
            record['city'] = city_edit.text()
            record['posX'] = str(posx_spin.value())
            record['posY'] = str(posy_spin.value())
            record['id'] = str(id_spin.value())
            record['text'] = text_edit.text()
            self.refresh_table()
    
    def delete_record(self):
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row < len(self.data):
            reply = QMessageBox.question(self, "确认删除", "确认删除选中记录?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                del self.data[current_row]
                self.refresh_table()
    
    def copy_record(self):
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row < len(self.data):
            import copy
            new_record = copy.deepcopy(self.data[current_row])
            new_record['text'] = new_record.get('text', '') + "_副本"
            self.data.append(new_record)
            self.refresh_table()
    
    def filter_data(self):
        self.refresh_table()
    
    def get_data(self) -> List[Dict]:
        return self.data


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager(str(Path(DATABASE_NAME).absolute()))
        self.db_manager.initialize_tables()
        self.backup_manager = BackupManager(self.db_manager)
        
        self.current_directory = ""
        self.allied_data = []
        self.plug215_data = {}
        self.prekeeps_data = []
        self.directory_history = []
        
        self.workers = []
        
        self.init_ui()
        self.load_directory_history()
        
        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self.auto_backup)
        self.backup_timer.start(3600000)
        
        # 首次启动自动备份
        self.backup_manager.create_backup("自动", "程序启动时自动备份")
    
    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 800)
        
        if os.path.exists(ICON_FILE):
            self.setWindowIcon(QIcon(ICON_FILE))
        
        self.create_menu_bar()
        self.create_toolbar()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        dir_group = QGroupBox("工作目录")
        dir_layout = QHBoxLayout(dir_group)
        
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("选择工作目录...")
        self.dir_edit.setReadOnly(True)
        dir_layout.addWidget(self.dir_edit)
        
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self.browse_directory)
        dir_layout.addWidget(browse_btn)
        
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(200)
        dir_layout.addWidget(QLabel("历史目录:"))
        dir_layout.addWidget(self.history_combo)
        self.history_combo.activated.connect(self.on_history_selected)
        
        load_btn = QPushButton("一键导入")
        load_btn.clicked.connect(self.import_files)
        dir_layout.addWidget(load_btn)
        
        main_layout.addWidget(dir_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        self.tab_widget = QTabWidget()
        
        self.allied_editor = PrekeepEditor()
        self.tab_widget.addTab(self.allied_editor, "alliedPrekeeps.xml")
        
        self.plug215_editor = Plugin215Editor()
        self.tab_widget.addTab(self.plug215_editor, "plug215.xml")
        
        self.prekeeps_editor = PrekeepEditor()
        self.tab_widget.addTab(self.prekeeps_editor, "prekeeps.xml")
        
        main_layout.addWidget(self.tab_widget)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        
        self.set_editors_enabled(False)
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件(&F)")
        
        open_action = QAction("打开目录(&O)", self)
        open_action.triggered.connect(self.browse_directory)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        file_menu.addAction(open_action)
        
        save_action = QAction("保存所有(&S)", self)
        save_action.triggered.connect(self.save_all_files)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&X)", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menubar.addMenu("编辑(&E)")
        
        search_action = QAction("搜索(&F)", self)
        search_action.triggered.connect(self.focus_search)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        edit_menu.addAction(search_action)
        
        db_menu = menubar.addMenu("数据库(&D)")
        
        backup_action = QAction("备份管理(&B)", self)
        backup_action.triggered.connect(self.open_backup_dialog)
        db_menu.addAction(backup_action)
        
        manual_backup_action = QAction("手动备份(&M)", self)
        manual_backup_action.triggered.connect(self.manual_backup)
        db_menu.addAction(manual_backup_action)
        
        settings_menu = menubar.addMenu("设置(&S)")
        
        debug_action = QAction("调试模式", self)
        debug_action.setCheckable(True)
        debug_action.setChecked(DEBUG_MODE)
        debug_action.toggled.connect(self.toggle_debug_mode)
        settings_menu.addAction(debug_action)
        
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_toolbar(self):
        toolbar = self.addToolBar("主工具栏")
        toolbar.setMovable(False)
        
        open_action = QAction("打开", self)
        open_action.triggered.connect(self.browse_directory)
        toolbar.addAction(open_action)
        
        save_action = QAction("保存", self)
        save_action.triggered.connect(self.save_all_files)
        toolbar.addAction(save_action)
        
        import_action = QAction("导入", self)
        import_action.triggered.connect(self.import_files)
        toolbar.addAction(import_action)
        
        toolbar.addSeparator()
        
        backup_action = QAction("备份", self)
        backup_action.triggered.connect(self.open_backup_dialog)
        toolbar.addAction(backup_action)
    
    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择工作目录", self.current_directory or os.path.expanduser("~"))
        if directory:
            self.current_directory = directory
            self.dir_edit.setText(directory)
            self.add_directory_to_history(directory)
            self.status_bar.showMessage(f"已选择目录: {directory}")
    
    def add_directory_to_history(self, directory: str):
        try:
            cursor = self.db_manager.execute(
                "SELECT id FROM directory_history WHERE directory_path = ?",
                (directory,)
            )
            row = cursor.fetchone()
            
            if row:
                self.db_manager.execute(
                    "UPDATE directory_history SET last_access_time = CURRENT_TIMESTAMP, "
                    "access_count = access_count + 1 WHERE directory_path = ?",
                    (directory,)
                )
            else:
                self.db_manager.execute(
                    "INSERT INTO directory_history (directory_path) VALUES (?)",
                    (directory,)
                )
            
            self.db_manager.commit()
            self.load_directory_history()
        except Exception as e:
            DebugLogger.error(f"添加目录历史失败: {str(e)}", "HISTORY")
    
    def load_directory_history(self):
        try:
            cursor = self.db_manager.execute(
                "SELECT directory_path FROM directory_history "
                "ORDER BY last_access_time DESC LIMIT 10"
            )
            directories = [row[0] for row in cursor.fetchall()]
            
            self.history_combo.clear()
            self.history_combo.addItem("-- 选择历史目录 --")
            for directory in directories:
                self.history_combo.addItem(directory)
        except Exception as e:
            DebugLogger.error(f"加载目录历史失败: {str(e)}", "HISTORY")
    
    def on_history_selected(self, index: int):
        if index > 0:
            directory = self.history_combo.currentText()
            self.current_directory = directory
            self.dir_edit.setText(directory)
    
    def import_files(self):
        if not self.current_directory:
            self.status_bar.showMessage("请先选择工作目录")
            return
        
        self.load_files_from_directory(self.current_directory)
    
    def load_files_from_directory(self, directory: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("正在加载文件...")
        
        self.worker = FileLoadWorker(directory)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_files_loaded)
        self.worker.error_signal.connect(self.on_load_error)
        self.workers.append(self.worker)
        self.worker.start()
    
    def update_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.status_bar.showMessage(message)
    
    def on_files_loaded(self, result: Dict):
        self.allied_data = result.get('allied_prekeeps', [])
        self.plug215_data = result.get('plug215', {})
        self.prekeeps_data = result.get('prekeeps', [])
        
        self.allied_editor.load_data(self.allied_data)
        self.plug215_editor.load_data(self.plug215_data)
        self.prekeeps_editor.load_data(self.prekeeps_data)
        
        self.set_editors_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("文件加载完成")
    
    def on_load_error(self, error: str):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"加载失败: {error}")
        QMessageBox.critical(self, "错误", f"文件加载失败:\n{error}")
    
    def save_all_files(self):
        if not self.current_directory:
            self.status_bar.showMessage("请先选择工作目录")
            return
        
        self.allied_data = self.allied_editor.get_data()
        self.plug215_data = self.plug215_editor.get_data()
        self.prekeeps_data = self.prekeeps_editor.get_data()
        
        data = {
            'allied_prekeeps': self.allied_data,
            'plug215': self.plug215_data,
            'prekeeps': self.prekeeps_data
        }
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("正在保存文件...")
        
        self.worker = FileSaveWorker(self.current_directory, data)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_files_saved)
        self.worker.error_signal.connect(self.on_save_error)
        self.workers.append(self.worker)
        self.worker.start()
    
    def on_files_saved(self, result):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("文件保存完成")
        self.backup_manager.create_backup("自动", "保存文件后自动备份")
    
    def on_save_error(self, error: str):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"保存失败: {error}")
        QMessageBox.critical(self, "错误", f"文件保存失败:\n{error}")
    
    def set_editors_enabled(self, enabled: bool):
        self.allied_editor.setEnabled(enabled)
        self.plug215_editor.setEnabled(enabled)
        self.prekeeps_editor.setEnabled(enabled)
    
    def focus_search(self):
        current_index = self.tab_widget.currentIndex()
        if current_index == 0:
            self.allied_editor.search_edit.setFocus()
        elif current_index == 1:
            self.plug215_editor.search_edit.setFocus()
        elif current_index == 2:
            self.prekeeps_editor.search_edit.setFocus()
    
    def open_backup_dialog(self):
        dialog = BackupRestoreDialog(self.backup_manager, self)
        dialog.exec()
    
    def manual_backup(self):
        result = self.backup_manager.create_backup("手动", "用户手动备份")
        if result:
            self.status_bar.showMessage(f"手动备份成功")
        else:
            self.status_bar.showMessage("手动备份失败")
    
    def auto_backup(self):
        try:
            self.backup_manager.create_backup("自动", "定时自动备份")
        except Exception as e:
            DebugLogger.error(f"自动备份失败: {str(e)}", "BACKUP")
    
    def toggle_debug_mode(self, enabled: bool):
        global DEBUG_MODE
        DEBUG_MODE = enabled
        self.status_bar.showMessage(f"调试模式: {'开启' if enabled else '关闭'}")
    
    def show_about(self):
        QMessageBox.about(self, "关于", 
            f"<h3>{APP_NAME}</h3>"
            f"<p>版本: {APP_VERSION}</p>"
            f"<p>XML配置文件专用编辑器</p>")
    
    def closeEvent(self, event):
        for worker in self.workers:
            worker.stop()
        
        self.backup_timer.stop()
        
        try:
            self.backup_manager.create_backup("自动", "程序退出时自动备份")
        except:
            pass
        
        self.db_manager.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()