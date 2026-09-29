"""Evaluator 测试：六分支 eval_basis + passed 三态 + judge 跳过（mock judge + tmp_path）。"""

import pytest

from evoagent.eval.evaluator import Evaluator
from evoagent.eval.store import EvalStore
from evoagent.models import ExecutionTrace, Task
from evoagent.storage import Storage


def _make_eval_store(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return EvalStore(storage)


def _make_trace(status="success", final_output="out", trace_id="t1"):
    return ExecutionTrace(
        trace_id=trace_id,
        task_id="task1",
        task_source="real",
        skill_id="s1",
        skill_version="1.0.0",
        started_at="2026-01-01",
        ended_at="2026-01-01",
        steps=[],
        final_output=final_output,
        status=status,
    )


class _FakeJudgeLLM:
    """暴露 chat_json 的假 judge，记录调用次数。"""

    def __init__(self, judge_data=None):
        self.judge_data = judge_data if judge_data is not None else {
            "rubric_scores": {"correctness": 5},
            "reason": "good",
        }
        self.calls = []

    def chat_json(self, prompt):
        self.calls.append(prompt)
        return self.judge_data


def test_objective_error_status_skips_judge(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM()
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(
        _make_trace(status="error", final_output=""), Task(task="x", task_source="real")
    )
    assert result.eval_basis == "objective"
    assert result.passed is False
    assert result.total_score == 0.0
    assert result.objective == {"status": "error"}
    assert judge.calls == []  # 客观定论跳过 judge


def test_objective_exact_hit_and_miss_skip_judge(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM()
    evaluator = Evaluator(llm=judge, eval_store=store)
    task = Task(task="2+2", task_source="real")

    hit = evaluator.evaluate(
        _make_trace(final_output="4"), task, objective_check={"type": "exact", "value": "4"}
    )
    assert hit.eval_basis == "objective"
    assert hit.passed is True
    assert hit.total_score == 1.0
    assert hit.objective["matched"] is True
    assert hit.objective["type"] == "exact"

    miss = evaluator.evaluate(
        _make_trace(final_output="5"), task, objective_check={"type": "exact", "value": "4"}
    )
    assert miss.eval_basis == "objective"
    assert miss.passed is False
    assert miss.total_score == 0.0
    assert miss.objective["matched"] is False

    assert judge.calls == []  # exact 定论也跳过 judge


def test_contains_with_rubric_mixed(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM({"rubric_scores": {"correctness": 3}, "reason": "ok"})
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(
        _make_trace(final_output="hello world"),
        Task(task="x", task_source="real"),
        objective_check={"type": "contains", "value": "world"},
        rubric=["correctness"],
    )
    assert result.eval_basis == "mixed"
    assert result.objective["matched"] is True
    assert result.judge_score == pytest.approx(0.6)
    # total = 0.7*1.0 + 0.3*0.6 = 0.88
    assert result.total_score == pytest.approx(0.88)
    assert result.passed is True
    assert len(judge.calls) == 1


def test_contains_no_rubric_judge_generic(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM({"rubric_scores": {"correctness": 4}, "reason": "ok"})
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(
        _make_trace(final_output="hello world"),
        Task(task="x", task_source="real"),
        objective_check={"type": "contains", "value": "world"},
    )
    assert result.eval_basis == "judge_generic"
    assert result.passed is None  # 半信号 + 无 rubric → 不判对错
    assert result.objective["matched"] is True  # matched 仍记录
    assert result.objective["type"] == "contains"


def test_judge_rubric(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM({"rubric_scores": {"correctness": 4, "completeness": 4}, "reason": "ok"})
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(
        _make_trace(final_output="out"),
        Task(task="x", task_source="real"),
        rubric=["correctness", "completeness"],
    )
    assert result.eval_basis == "judge_rubric"
    assert result.judge_score == pytest.approx(0.8)
    assert result.total_score == pytest.approx(0.8)
    assert result.passed is True
    assert result.objective == {"status": "success"}


def test_judge_generic_no_objective_no_rubric(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM({"rubric_scores": {"correctness": 1}, "reason": "meh"})
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(_make_trace(final_output="out"), Task(task="x", task_source="real"))
    assert result.eval_basis == "judge_generic"
    assert result.passed is None
    assert result.judge_score == pytest.approx(0.2)
    assert result.objective == {"status": "success"}


def test_unknown_objective_type_goes_to_judge(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM({"rubric_scores": {"correctness": 3}, "reason": "ok"})
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(
        _make_trace(final_output="out"),
        Task(task="x", task_source="real"),
        objective_check={"type": "test_script", "value": "..."},
    )
    # test_script 未知 type → 视作无客观 → judge_generic（无 rubric），不崩溃
    assert result.eval_basis == "judge_generic"
    assert result.passed is None
    assert len(judge.calls) == 1


def test_evaluate_writes_and_reads_back(tmp_path):
    store = _make_eval_store(tmp_path)
    judge = _FakeJudgeLLM({"rubric_scores": {"correctness": 5}, "reason": "ok"})
    evaluator = Evaluator(llm=judge, eval_store=store)

    result = evaluator.evaluate(
        _make_trace(final_output="out"),
        Task(task="x", task_source="real"),
        rubric=["correctness"],
    )
    got = store.get_eval(result.eval_id)
    assert got is not None
    assert got.eval_id == result.eval_id
    assert got.trace_id == "t1"
    assert got.eval_basis == result.eval_basis
    assert got.passed == result.passed
    assert got.total_score == result.total_score
    assert got.objective == result.objective
    assert got.rubric_scores == result.rubric_scores
    assert got.judge_score == result.judge_score
