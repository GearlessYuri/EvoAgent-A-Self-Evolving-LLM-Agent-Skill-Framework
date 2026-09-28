"""EvalStore 测试：评估结果 / 经验读写、passed 三态、JSON 反序列化（tmp_path 隔离）。"""

import sqlite3

import pytest

from evoagent.eval.store import EvalStore
from evoagent.models import EvaluationResult, Experience
from evoagent.storage import Storage


def _make_storage(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return storage


def _make_eval(eval_id="e1", trace_id="t1", passed=None, **overrides):
    kwargs = dict(
        eval_id=eval_id,
        trace_id=trace_id,
        eval_basis="objective",
        passed=passed,
        total_score=0.8,
        objective={"matched": True},
        judge_score=0.0,
        rubric_scores={"correctness": 0.8},
        judge_reason="",
        evaluated_at="2026-01-01",
    )
    kwargs.update(overrides)
    return EvaluationResult(**kwargs)


# ── save_eval / get_eval 往返（passed 三态精确保留） ─────────────────────


@pytest.mark.parametrize("passed", [True, False, None])
def test_save_eval_get_eval_tristate(tmp_path, passed):
    storage = _make_storage(tmp_path)
    store = EvalStore(storage)
    ev = _make_eval(passed=passed)
    store.save_eval(ev)

    got = store.get_eval("e1")
    assert got is not None
    assert got == ev
    assert got.passed is passed
    assert isinstance(got.objective, dict) and got.objective == {"matched": True}
    assert isinstance(got.rubric_scores, dict) and got.rubric_scores == {"correctness": 0.8}


def test_get_eval_missing_returns_none(tmp_path):
    storage = _make_storage(tmp_path)
    store = EvalStore(storage)
    assert store.get_eval("nope") is None


def test_save_eval_duplicate_raises(tmp_path):
    storage = _make_storage(tmp_path)
    store = EvalStore(storage)
    store.save_eval(_make_eval(eval_id="e1"))
    with pytest.raises(sqlite3.IntegrityError):
        store.save_eval(_make_eval(eval_id="e1"))


def test_list_evals_by_trace(tmp_path):
    storage = _make_storage(tmp_path)
    store = EvalStore(storage)
    store.save_eval(_make_eval(eval_id="e1", trace_id="t1"))
    store.save_eval(_make_eval(eval_id="e2", trace_id="t2"))

    assert [e.eval_id for e in store.list_evals(trace_id="t1")] == ["e1"]
    assert len(store.list_evals()) == 2


# ── save_experience / list_experiences ──────────────────────────────────


def test_save_experience_list_roundtrip(tmp_path):
    storage = _make_storage(tmp_path)
    store = EvalStore(storage)
    exp = Experience(
        experience_id="x1",
        trace_id="t1",
        skill_id="s1",
        category="missing_step",
        summary="sum",
        target_section="tools",
        suggestion="sug",
        confidence=0.8,
    )
    store.save_experience(exp)

    exps = store.list_experiences(skill_id="s1")
    assert len(exps) == 1
    assert exps[0] == exp
    assert exps[0].confidence == 0.8
    assert store.list_experiences(skill_id="other") == []
