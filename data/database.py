from __future__ import annotations
# -*- coding: utf-8 -*-
"""
数据库连接管理

SQLite 数据库连接、会话管理、表初始化。
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from data.models import Base
from utils.logger import setup_logger

logger = setup_logger("database")


class Database:
    """数据库管理器"""

    def __init__(self, db_path: str = "ssh_manager.db"):
        """
        Args:
            db_path: 数据库文件路径
        """
        self._db_path = db_path
        self._engine = None
        self._session_factory = None

    def initialize(self) -> None:
        """初始化数据库引擎和会话工厂"""
        # 确保数据库目录存在
        db_file = Path(self._db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # 创建 SQLite 引擎
        # check_same_thread=False 允许跨线程访问（配合 session 管理）
        db_url = f"sqlite:///{self._db_path}"
        self._engine = create_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        # 启用 SQLite 外键约束
        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # 创建所有表
        Base.metadata.create_all(self._engine)

        # 兼容旧数据库：添加新增列（SQLite 不支持 ALTER ADD IF NOT EXISTS）
        self._migrate_add_columns()

        logger.info(f"Database initialized: {self._db_path}")

        # 创建会话工厂
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )

    def get_session(self) -> Session:
        """获取一个新的数据库会话"""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._session_factory()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        提供事务范围的会话上下文管理器。

        用法:
            with db.session_scope() as session:
                session.add(host)
                # 自动 commit 或 rollback
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _migrate_add_columns(self) -> None:
        """兼容旧数据库：安全地添加新增列（列已存在则跳过）"""
        from sqlalchemy import inspect, text
        inspector = inspect(self._engine)

        migrations = [
            ("task_steps", "continue_on_error", "BOOLEAN DEFAULT 0"),
        ]

        with self._engine.connect() as conn:
            for table, column, col_def in migrations:
                existing = [c["name"] for c in inspector.get_columns(table)]
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added column {table}.{column}")

    def dispose(self) -> None:
        """释放数据库引擎资源"""
        if self._engine:
            self._engine.dispose()
            logger.info("Database engine disposed")


# ============ 全局实例 ============

_db: Database | None = None


def init_db(db_path: str = "ssh_manager.db") -> Database:
    """初始化全局数据库实例"""
    global _db
    _db = Database(db_path)
    _db.initialize()
    return _db


def get_db() -> Database:
    """获取全局数据库实例"""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


def get_db_session() -> Session:
    """获取一个数据库会话（便捷方法）"""
    return get_db().get_session()
