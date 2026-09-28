"""Storage 底座测试：连接 / 建表 / CRUD / schema 锁定（全部用 tmp_path 隔离）。"""

import json

from evoagent.storage import Storage

EXPECTED_TABLES = {"skills", "traces", "trace_steps", "evals", "experiences"}


def _columns(conn, table):
    """返回某表 `PRAGMA table_info` 的列名列表。"""
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _table_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_connect_creates_parent_dir(tmp_path):
    db_path = tmp_path / "nested" / "x.db"
    storage = Storage(db_path)
    conn = storage.connect()
    assert (tmp_path / "nested").is_dir()
    assert db_path.exists()
    conn.close()


def test_init_schema_creates_five_tables(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    conn = storage.connect()
    storage.init_schema()
    assert EXPECTED_TABLES.issubset(_table_names(conn))


def test_init_schema_idempotent(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    storage.init_schema()  # 重复调用不应报错
    assert EXPECTED_TABLES.issubset(_table_names(storage.conn))


def test_wal_enabled(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    conn = storage.connect()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


# ── schema 关键列锁定（用 PRAGMA table_info，避免与实现共用同一 schema 的循环论证）──


def test_skills_columns(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    cols = _columns(storage.conn, "skills")
    for name in ["skill_id", "version", "status"]:
        assert name in cols


def test_traces_columns(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    cols = _columns(storage.conn, "traces")
    for name in ["trace_id", "task_source", "status", "error_type", "retrieval_fallback", "usage"]:
        assert name in cols


def test_trace_steps_columns(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    cols = _columns(storage.conn, "trace_steps")
    for name in ["trace_id", "step_index", "content", "truncated"]:
        assert name in cols


def test_evals_columns(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    cols = _columns(storage.conn, "evals")
    for name in ["eval_id", "passed", "total_score"]:
        assert name in cols


def test_experiences_columns(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    cols = _columns(storage.conn, "experiences")
    for name in ["experience_id", "confidence"]:
        assert name in cols


def test_truncated_column_is_integer_default_zero(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    rows = storage.conn.execute("PRAGMA table_info(trace_steps)").fetchall()
    truncated = [r for r in rows if r["name"] == "truncated"][0]
    assert truncated["type"] == "INTEGER"
    assert truncated["dflt_value"] == "0"


# ── CRUD round-trip ─────────────────────────────────────────────────────


def test_crud_roundtrip(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()

    row = {
        "skill_id": "code-review",
        "version": "1.0.0",
        "status": "active",
        "parent_version": "",
        "change_log": "init",
        "metrics": {"accuracy": 0.9},  # JSON 字段，写入时序列化为 TEXT
        "created_at": "2026-01-01",
        "updated_at": "2026-01-02",
    }
    rowid = storage.insert("skills", row)
    assert rowid == 1

    rows = storage.query("skills", where="skill_id = ?", params=("code-review",))
    assert len(rows) == 1
    got = rows[0]
    assert got["skill_id"] == "code-review"
    assert got["version"] == "1.0.0"
    assert got["status"] == "active"
    assert got["parent_version"] == ""
    assert got["change_log"] == "init"
    assert json.loads(got["metrics"]) == {"accuracy": 0.9}

    # update
    affected = storage.update(
        "skills", {"status": "deprecated"}, "skill_id = ?", ("code-review",)
    )
    assert affected == 1
    rows = storage.query("skills", where="skill_id = ?", params=("code-review",))
    assert rows[0]["status"] == "deprecated"

    # delete
    affected = storage.delete("skills", "skill_id = ?", ("code-review",))
    assert affected == 1
    assert storage.query("skills", where="skill_id = ?", params=("code-review",)) == []


def test_crud_experiences_scalar_roundtrip(tmp_path):
    """纯标量表的 CRUD round-trip（无 JSON 字段，字段值完全一致）。"""
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()

    storage.insert(
        "experiences",
        {
            "experience_id": "e1",
            "trace_id": "t1",
            "skill_id": "s1",
            "category": "missing_step",
            "summary": "sum",
            "target_section": "tools",
            "suggestion": "sug",
            "confidence": 0.8,
        },
    )
    rows = storage.query("experiences", where="experience_id = ?", params=("e1",))
    assert len(rows) == 1
    assert rows[0]["experience_id"] == "e1"
    assert rows[0]["confidence"] == 0.8
    assert rows[0]["category"] == "missing_step"
