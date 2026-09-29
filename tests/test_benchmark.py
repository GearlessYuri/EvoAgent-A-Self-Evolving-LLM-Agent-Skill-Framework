"""Benchmark 测试：汇总口径、防污染三规则、load_tasks（mock executor/evaluator + 真实 executor/TraceStore）。"""

import json
from types import SimpleNamespace

import pytest

from evoagent.eval.benchmark import Benchmark, load_tasks, load_tasks_by_name
from evoagent.execution.executor import AgentExecutor
from evoagent.execution.trace import TraceStore
from evoagent.models import BenchmarkTask, Skill
from evoagent.storage import Storage


def _make_skill():
    return Skill(
        skill_id="s1",
        name="s",
        description="d",
        version="1.0.0",
        tags=[],
        prompt_template="处理 {task}",
        few_shots=[],
        tools=[],
        status="active",
        parent_version="",
        change_log="",
        metrics={},
        created_at="",
        updated_at="",
    )


def _make_task(task_id, task, reference_answer="", rubric=None, objective_check=None):
    return BenchmarkTask(
        task_id=task_id,
        task=task,
        reference_answer=reference_answer,
        rubric=rubric or [],
        objective_check=objective_check or {},
        tags=[],
        difficulty="easy",
    )


class _FakeExecutor:
    def run(self, task, skill):
        return SimpleNamespace(trace_id="t", task_source=task.task_source)


class _FakeEvaluator:
    def __init__(self, results):
        self.results = list(results)  # 每项 (passed, total_score)

    def evaluate(self, trace, task, **kwargs):
        passed, score = self.results.pop(0)
        return SimpleNamespace(passed=passed, total_score=score)


class _FakeLLM:
    def complete_with_usage(self, prompt):
        return "out", {"total_tokens": 1, "total_cost": 0.0, "total_latency_ms": 5}


def _make_real_store(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return TraceStore(storage)


# ── 汇总口径 ────────────────────────────────────────────────────────────


def test_run_aggregates_report():
    executor = _FakeExecutor()
    evaluator = _FakeEvaluator([(True, 0.9), (False, 0.4), (None, 0.5)])
    benchmark = Benchmark(executor=executor, evaluator=evaluator)

    tasks = [
        _make_task("a", "task a"),
        _make_task("b", "task b"),
        _make_task("c", "task c"),
    ]
    report = benchmark.run(tasks, _make_skill())

    # success_rate = True 数(1) / 非 None 数(2) = 0.5；passed=None 不计分母
    assert report.success_rate == 0.5
    # avg_total_score = (0.9+0.4+0.5)/3 = 0.6
    assert report.avg_total_score == pytest.approx(0.6)
    assert [p[0] for p in report.per_task] == ["a", "b", "c"]
    assert [p[1] for p in report.per_task] == [True, False, None]

    d = report.to_dict()
    assert d["per_task"][0] == {"task_id": "a", "passed": True, "total_score": 0.9}
    assert d["success_rate"] == 0.5


def test_run_empty_tasks():
    benchmark = Benchmark(executor=_FakeExecutor(), evaluator=_FakeEvaluator([]))
    report = benchmark.run([], _make_skill())
    assert report.per_task == []
    assert report.success_rate == 0.0
    assert report.avg_total_score == 0.0


# ── 防污染①：来源隔离（真实 executor + 真实 TraceStore） ────────────────


def test_source_isolation_real_executor(tmp_path):
    trace_store = _make_real_store(tmp_path)
    executor = AgentExecutor(llm=_FakeLLM(), trace_store=trace_store)
    evaluator = _FakeEvaluator([(True, 1.0)])
    benchmark = Benchmark(executor=executor, evaluator=evaluator)

    benchmark.run([_make_task("a", "hello")], _make_skill())

    traces = trace_store.list()
    assert len(traces) == 1
    assert all(t.task_source == "benchmark" for t in traces)


# ── 防污染②：答案隔离（reference_answer 哨兵不进执行 prompt） ───────────


def test_answer_isolation_sentinel_not_in_prompt(tmp_path):
    trace_store = _make_real_store(tmp_path)
    executor = AgentExecutor(llm=_FakeLLM(), trace_store=trace_store)
    evaluator = _FakeEvaluator([(True, 1.0)])
    benchmark = Benchmark(executor=executor, evaluator=evaluator)

    benchmark.run(
        [_make_task("a", "hello", reference_answer="SENTINEL_XYZ", rubric=["correctness"])],
        _make_skill(),
    )

    traces = trace_store.list()
    assert len(traces) == 1
    full = trace_store.get(traces[0].trace_id)
    prompt = full.steps[0].content  # llm_call 步骤内容即渲染后的 prompt
    assert "SENTINEL_XYZ" not in prompt


# ── 防污染③：regression/extension 分文件加载 + 无导出经验接口 ───────────


def test_load_tasks_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr("evoagent.config.BENCHMARKS_DIR", str(tmp_path / "benchmarks"))
    (tmp_path / "benchmarks").mkdir(parents=True)
    (tmp_path / "benchmarks" / "regression.json").write_text(
        json.dumps([{"task_id": "r1", "task": "t", "reference_answer": "", "rubric": [], "objective_check": {}, "tags": [], "difficulty": "easy"}]),
        encoding="utf-8",
    )
    (tmp_path / "benchmarks" / "extension.json").write_text(
        json.dumps([{"task_id": "e1", "task": "t", "reference_answer": "", "rubric": [], "objective_check": {}, "tags": [], "difficulty": "easy"}]),
        encoding="utf-8",
    )

    assert [t.task_id for t in load_tasks_by_name("regression")] == ["r1"]
    assert [t.task_id for t in load_tasks_by_name("extension")] == ["e1"]


def test_benchmark_has_no_export_api():
    benchmark = Benchmark(executor=_FakeExecutor(), evaluator=_FakeEvaluator([]))
    assert not hasattr(benchmark, "export_experiences")


# ── load_tasks 边界 ─────────────────────────────────────────────────────


def test_load_tasks_non_array_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"tasks": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_tasks(path)
