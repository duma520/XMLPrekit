# XMLPrekit （见源码内 VERSION 常量）

> **一句话**：XMLPrekit —— 一个用 Python 写的 Windows 桌面程序，
> 主程序为 `XMLPrekit.py`，界面技术栈 PySide6（Qt6 官方 Python 绑定）。
>
> **适合谁**：想直接用现成工具、不想自己写代码的 Windows 用户。
>
> **解决什么问题**：把这件事做成开箱即用的程序 —— 下载解压、装上依赖、双击就能跑。

---

## 目录

- [1. 这是什么](#1-这是什么)
- [2. 零基础入门（5 分钟跑起来）](#2-零基础入门5-分钟跑起来)
- [3. 功能与界面](#3-功能与界面)
- [4. 命令行参数](#4-命令行参数)
- [5. 配置文件与数据](#5-配置文件与数据)
- [6. 工作原理（技术参考）](#6-工作原理技术参考)
- [7. 排错手册](#7-排错手册)
- [8. 常见问题 FAQ](#8-常见问题-faq)
- [9. 目录结构](#9-目录结构)
- [10. 开发与构建](#10-开发与构建)
- [11. 已知限制与安全说明](#11-已知限制与安全说明)
- [12. 许可](#12-许可)

## 1. 这是什么

| 项目 | 说明 |
| --- | --- |
| 程序名 | `XMLPrekit` |
| 当前版本 | （见源码内 VERSION 常量） |
| 主程序 | `XMLPrekit.py` |
| 界面技术 | PySide6（Qt6 官方 Python 绑定） |
| 语言 / 运行平台 | Python 3.10 / Windows |
| 源码规模 | 根目录及子模块共 3 个 .py 文件 |
| 仓库 | https://github.com/duma520/XMLPrekit |

## 2. 零基础入门（5 分钟跑起来）

### 第 1 步：装 Python

1. 打开 <https://www.python.org/downloads/windows/>，下载 Python 3.10 或更新版本。
2. 安装时**务必勾选** `Add python.exe to PATH`（安装向导第一页最下方）。
3. 装完按 `Win + R` 输入 `cmd`，敲 `python --version`，能看到版本号就成功了。

### 第 2 步：拿到源码

- **下载压缩包**：在本仓库 Releases 页下载 `XMLPrekit-*.zip`，解压到任意目录。
- **git 克隆**：`git clone https://github.com/duma520/XMLPrekit.git`

### 第 3 步：装依赖

在源码目录打开命令行，执行：

```
pip install PySide6 pypinyin
```

> 清单是从源码的实际 import 汇总出来的；若某个包名不准确，以 pip 报错提示的正确包名为准。

### 第 4 步：启动

```bat
python XMLPrekit.py
```

目录里还带了 `1.bat`，双击等同于上面的命令（前提是 Python 在 PATH 里）。

## 3. 功能与界面

> 本节只列源码里能确认的事实；具体按钮与交互以运行后的界面为准。

| 维度 | 实际情况 |
| --- | --- |
| 界面框架 | PySide6（Qt6 官方 Python 绑定） |
| 是否有 main 入口 | 是，可直接 python 主程序.py 运行 |
| 第三方依赖数 | 2 个 |

## 4. 命令行参数

该程序没有定义命令行参数，直接运行即可（操作都在界面里完成）。

## 5. 配置文件与数据

程序把配置写在自身目录或用户目录下；.gitignore 已排除运行期产生的配置与日志，首次运行会自动生成。

## 6. 工作原理（技术参考）

```
用户操作 → PySide6 → 业务逻辑 → 结果输出
```

- 入口文件 `XMLPrekit.py`，带 if __name__ == '__main__' 保护。
- 依赖的第三方库：`PySide6`、`pypinyin`。
- 全部业务逻辑在仓库内可见，没有编译产物、没有联网下发代码。

## 7. 排错手册

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| python 不是内部或外部命令 | 安装时没勾 PATH | 重装 Python 并勾选 Add python.exe to PATH，或改用 py 命令 |
| ModuleNotFoundError: No module named xxx | 依赖没装 | 按第 3 步 pip install 对应包 |
| 双击 .bat 一闪而过 | 出错后窗口立即关闭 | 用 cmd 进入目录再执行命令，看清报错 |
| 界面显示乱码 | 控制台编码不是 UTF-8 | 先执行 chcp 65001，或用 python -X utf8 主程序.py |
| 杀毒软件拦截 | 未签名脚本被误判 | 加入信任/白名单；本项目只提供源码，可自行审阅 |

## 8. 常见问题 FAQ

**Q1：需要装 Visual Studio 之类的编译工具吗？**
A：不需要。这里只提供 Python 源码，pip 装的是预编译轮子。

**Q2：能在 macOS / Linux 上跑吗？**
A：本项目按 Windows 环境开发与验证；其他系统未测试，可能需要改路径与系统 API 调用。

**Q3：为什么 Releases 里只有源码 zip，没有 exe？**
A：只分发源码，避免二进制被误判；需要 exe 请按第 10 节自行打包。

**Q4：改了代码怎么运行？**
A：直接 python 主程序.py，改动立即生效，无需编译。

**Q5：数据存在哪？会不会被上传？**
A：只存在本机（程序目录或用户目录）。本程序不含上传逻辑。

**Q6：怎么反馈问题？**
A：到 https://github.com/duma520/XMLPrekit/issues 提 Issue，附上报错原文与复现步骤。

## 9. 目录结构

```
backups/
0_nuitka_pyside6_clang_auto.bat
1.bat
2_debug.bat
README.md
XMLPrekit - 1.0.0.py
XMLPrekit - 1.1.0.py
XMLPrekit.py
alliedPrekeeps.xml
editor_data.db
icon.ico
plug215.xml
prekeeps.xml
backups\backup_20260424_194242_自动.db
backups\backup_20260424_195046_自动.db
backups\backup_20260424_195859_自动.db
backups\backup_20260424_205859_自动.db
backups\backup_20260424_215231_自动.db
```

## 10. 开发与构建

- 直接运行（开发态）：`python XMLPrekit.py`
- 语法自检：`python -m py_compile XMLPrekit.py`
- 打包 exe（可选）：装 pyinstaller 后执行 `pyinstaller -F -w XMLPrekit.py`

## 11. 已知限制与安全说明

- 只提供源码，不提供预编译二进制。
- 仓库不含任何凭据；.env / *.pem / *.key / 日志与运行期数据均在 .gitignore 中排除。
- 若程序需要联网，请在源码中确认目标地址后再运行。

## 12. 许可

AGPL-3.0，详见仓库根目录 LICENSE。
