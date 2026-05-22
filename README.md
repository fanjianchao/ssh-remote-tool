# SSH Remote Tool

一款基于 Python 的 SSH 远程运维工具，提供可视化 UI 界面，支持批量远程主机管理、文件传输和命令执行，操作可按配置顺序编排执行。

## 功能特性

- **主机管理**：配置远程主机信息（主机名/IP、端口、用户名、密码/密钥），支持增删改查和导入导出
- **多主机选择**：支持同时勾选多个远程主机执行统一操作
- **文件传输**：基于 SFTP 实现本地与远程之间的文件/目录上传下载，支持进度展示
- **命令执行**：在选中主机上批量执行 Shell 命令，实时回显输出结果
- **任务编排**：将文件传输和命令执行按顺序组合为任务流，支持顺序执行和多主机并行分发
- **结果查看**：任务执行状态跟踪、日志查看和执行结果汇总

## 技术栈

| 组件 | 技术 |
|------|------|
| UI 框架 | PySide6 (Qt6) |
| SSH/SFTP | paramiko |
| 数据库 ORM | SQLAlchemy + SQLite |
| 密码加密 | cryptography (Fernet) |
| 日志 | Python logging + colorlog |
| 测试 | pytest + pytest-qt |
| 打包 | PyInstaller |

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

### 运行测试

```bash
pytest tests/ -v
```

## 项目结构

```
ssh-remote-tool/
├── main.py                  # 程序入口
├── requirements.txt         # 依赖清单
├── config/                  # 配置模块
│   ├── settings.py          # 全局配置
│   └── constants.py         # 常量定义
├── data/                    # 数据层
│   ├── models.py            # ORM 模型
│   ├── database.py          # 数据库管理
│   ├── host_repository.py   # 主机数据访问
│   └── task_repository.py   # 任务数据访问
├── core/                    # 业务逻辑层
│   ├── host_service.py      # 主机管理服务
│   ├── task_service.py      # 任务编排服务
│   └── task_engine.py       # 任务执行引擎
├── executors/               # 执行器层
│   ├── base_executor.py     # 执行器基类
│   ├── ssh_executor.py      # SSH 命令执行
│   └── sftp_executor.py     # SFTP 文件传输
├── views/                   # UI 层
│   ├── main_window.py       # 主窗口
│   └── components/          # UI 组件
├── utils/                   # 工具模块
│   ├── logger.py            # 日志工具
│   ├── crypto.py            # 加密工具
│   ├── ssh_helpers.py       # SSH 辅助
│   └── validators.py        # 输入验证
├── signals/                 # Qt 信号定义
└── tests/                   # 测试
```

## 安全说明

- 所有密码通过 Fernet 对称加密后存储，密钥派生自机器标识
- SSH 连接支持密码和密钥两种认证方式
- 加密数据存储在用户目录下的 `~/.ssh-remote-tool/` 中
