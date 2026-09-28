"""存储底座：SQLite 连接 / 建表 / 通用 CRUD。

本模块是**全项目唯一写 SQL（`import sqlite3`）** 的地方（系统设计 §2 分层约束）：
上层领域门面只调用本模块的 `Storage`，不得直接 `import sqlite3`。

通用 CRUD 一律参数化（`?` 占位符绑定值）；表名 / 列名 / where 子句作为结构件
由调用方以字符串传入（SQLite 无法参数化标识符）。JSON 字段（`metrics` / `usage` /
`objective` / `rubric_scores`）以 TEXT 存储，写入时由 `insert` / `update` 用标准库
`json` 序列化 dict / list 值。
"""

import json
import sqlite3
from pathlib import Path

from . import config

# 设计 §4.5 逐列锁定的 5 张表结构。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    skill_id       TEXT NOT NULL,
    version        TEXT NOT NULL,
    status         TEXT NOT NULL,
    parent_version TEXT NOT NULL DEFAULT '',
    change_log     TEXT NOT NULL DEFAULT '',
    metrics        TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS traces (
    trace_id          TEXT PRIMARY KEY,
    task_id           TEXT NOT NULL,
    task_source       TEXT NOT NULL,
    skill_id          TEXT NOT NULL,
    skill_version     TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    ended_at          TEXT NOT NULL,
    final_output      TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL,
    error             TEXT NOT NULL DEFAULT '',
    error_type        TEXT NOT NULL DEFAULT '',
    retrieval_fallback INTEGER NOT NULL DEFAULT 0,
    usage             TEXT
);

CREATE TABLE IF NOT EXISTS trace_steps (
    trace_id   TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    type       TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tool_name  TEXT NOT NULL DEFAULT '',
    tokens     INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    truncated  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (trace_id, step_index),
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
);

CREATE TABLE IF NOT EXISTS evals (
    eval_id       TEXT PRIMARY KEY,
    trace_id      TEXT NOT NULL,
    eval_basis    TEXT NOT NULL,
    passed        INTEGER,
    total_score   REAL NOT NULL,
    objective     TEXT NOT NULL DEFAULT '{}',
    judge_score   REAL NOT NULL DEFAULT 0,
    rubric_scores TEXT NOT NULL DEFAULT '{}',
    judge_reason  TEXT NOT NULL DEFAULT '',
    evaluated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiences (
    experience_id  TEXT PRIMARY KEY,
    trace_id       TEXT NOT NULL,
    skill_id       TEXT NOT NULL,
    category       TEXT NOT NULL,
    summary        TEXT NOT NULL DEFAULT '',
    target_section TEXT NOT NULL DEFAULT '',
    suggestion     TEXT NOT NULL DEFAULT '',
    confidence     REAL NOT NULL
);
"""


def _serialize_value(value):
    """把 dict / list 值序列化为 JSON 文本，便于存入 TEXT 列。"""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


class Storage:
    """SQLite 存储底座：连接（WAL）、建表（5 表）、通用参数化 CRUD。"""

    def __init__(self, db_path: str | Path = config.DB_PATH):
        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """建立连接：自动创建父目录（mkdir -p 语义）并启用 WAL。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        if config.SQLITE_WAL_ENABLED:
            self.conn.execute("PRAGMA journal_mode=WAL")
        return self.conn

    def init_schema(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` 建齐 5 张表（幂等，可重复调用）。"""
        if self.conn is None:
            raise RuntimeError("必须先调用 connect() 建立连接")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def insert(self, table: str, row: dict) -> int:
        """插入一行，返回 `lastrowid`。dict / list 值自动 JSON 序列化。"""
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        values = [_serialize_value(v) for v in row.values()]
        cur = self.conn.execute(sql, values)
        self.conn.commit()
        return cur.lastrowid

    def query(
        self, table: str, where: str = "", params: tuple = (), order_by: str = ""
    ) -> list[dict]:
        """查询并返回行列表（`sqlite3.Row` 转 dict）。"""
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def update(self, table: str, set_values: dict, where: str, params: tuple) -> int:
        """更新行，返回受影响行数（`rowcount`）。"""
        assignments = ", ".join(f"{col} = ?" for col in set_values)
        sql = f"UPDATE {table} SET {assignments} WHERE {where}"
        values = [_serialize_value(v) for v in set_values.values()]
        cur = self.conn.execute(sql, [*values, *params])
        self.conn.commit()
        return cur.rowcount

    def delete(self, table: str, where: str, params: tuple) -> int:
        """删除行，返回受影响行数。"""
        sql = f"DELETE FROM {table} WHERE {where}"
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.rowcount
