"""TraceStore 测试：写入/读取往返、4000 字符截断、list 过滤（tmp_path 隔离）。"""

import sqlite3

import pytest

from evoagent import config
from evoagent.execution.trace import TraceStore
from evoagent.models import ExecutionTrace, TraceStep
from evoagent.storage import Storage


def _make_storage(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return storage


def _make_trace(trace_id="t1", **overrides):
    kwargs = dict(
        trace_id=trace_id,
        task_id="task1",
        task_source="real",
        skill_id="code-review",
        skill_version="1.0.0",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        steps=[TraceStep(0, "llm_call", "hello")],
        final_output="ok",
        status="success",
    )
    kwargs.update(overrides)
    return ExecutionTrace(**kwargs)


# ── save / get 往返 ─────────────────────────────────────────────────────


def test_save_get_roundtrip_usage_none(tmp_path):
    storage = _make_storage(tmp_path)
    store = TraceStore(storage)
    trace = _make_trace(
        steps=[TraceStep(0, "llm_call", "hi"), TraceStep(1, "final", "done")]
    )
    store.save(trace)

    got = store.get("t1")
    assert got is not None
    assert got == trace
    assert got.usage is None
    assert [s.step_index for s in got.steps] == [0, 1]
    assert isinstance(got.steps[0], TraceStep)


def test_save_get_roundtrip_usage_dict(tmp_path):
    storage = _make_storage(tmp_path)
    store = TraceStore(storage)
    store.save(_make_trace(usage={"total_tokens": 1}))

    got = store.get("t1")
    assert got.usage == {"total_tokens": 1}


def test_save_duplicate_trace_raises(tmp_path):
    storage = _make_storage(tmp_path)
    store = TraceStore(storage)
    store.save(_make_trace(trace_id="t1"))
    with pytest.raises(sqlite3.IntegrityError):
        store.save(_make_trace(trace_id="t1"))


# ── 4000 字符截断（直查 trace_steps 表断言 truncated） ───────────────────


def test_truncation_boundary(tmp_path):
    storage = _make_storage(tmp_path)
    store = TraceStore(storage)

    exact = "a" * config.TRACE_CONTENT_MAX_CHARS  # 恰好 4000，不截断
    over = "b" * (config.TRACE_CONTENT_MAX_CHARS + 10)  # 超过 4000，截断
    store.save(
        _make_trace(
            trace_id="t-boundary",
            steps=[
                TraceStep(0, "tool_result", exact),
                TraceStep(1, "tool_result", over),
            ],
        )
    )

    rows = storage.query(
        "trace_steps", where="trace_id = ?", params=("t-boundary",), order_by="step_index"
    )
    assert len(rows) == 2
    assert rows[0]["truncated"] == 0
    assert len(rows[0]["content"]) == config.TRACE_CONTENT_MAX_CHARS
    assert rows[1]["truncated"] == 1
    assert len(rows[1]["content"]) == config.TRACE_CONTENT_MAX_CHARS
    assert rows[1]["content"] == "b" * config.TRACE_CONTENT_MAX_CHARS


# ── list 过滤（返回摘要，steps=[]） ──────────────────────────────────────


def test_list_filters_by_skill_status_since(tmp_path):
    storage = _make_storage(tmp_path)
    store = TraceStore(storage)
    store.save(_make_trace(trace_id="t1", skill_id="s1", status="success", started_at="2026-01-01"))
    store.save(_make_trace(trace_id="t2", skill_id="s2", status="error", started_at="2026-01-02"))
    store.save(_make_trace(trace_id="t3", skill_id="s1", status="success", started_at="2026-01-03"))

    by_skill = store.list(skill_id="s1")
    assert [t.trace_id for t in by_skill] == ["t1", "t3"]
    assert all(t.steps == [] for t in by_skill)  # 摘要，不加载 steps

    by_status = store.list(status="error")
    assert [t.trace_id for t in by_status] == ["t2"]

    by_since = store.list(since="2026-01-02")  # started_at >= since
    assert [t.trace_id for t in by_since] == ["t2", "t3"]


def test_list_missing_returns_empty(tmp_path):
    storage = _make_storage(tmp_path)
    store = TraceStore(storage)
    assert store.get("nope") is None
    assert store.list(skill_id="nope") == []
