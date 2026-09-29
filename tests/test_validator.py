"""Validator 测试：三支结局 + win_rate 口径 + promote 状态机 + failed_evolution（mock Benchmark + tmp_path）。"""

import pytest

from evoagent.eval.benchmark import BenchmarkReport
from evoagent.eval.store import EvalStore
from evoagent.evolution.validator import Validator, _win_rate
from evoagent.models import BenchmarkTask, Skill
from evoagent.skills.registry import SkillRegistry
from evoagent.storage import Storage


def _make_skill(skill_id="s1", version="1.0.0", status="active"):
    return Skill(
        skill_id=skill_id,
        name="s",
        description="d",
        version=version,
        tags=[],
        prompt_template="处理 {task}",
        few_shots=[],
        tools=[],
        status=status,
        parent_version="",
        change_log="",
        metrics={},
        created_at="",
        updated_at="",
    )


def _make_task(task_id):
    return BenchmarkTask(
        task_id=task_id, task="t", reference_answer="", rubric=[], objective_check={},
        tags=[], difficulty="easy",
    )


def _make_registry_and_store(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    eval_store = EvalStore(storage)
    return registry, eval_store


class _FakeBenchmark:
    def __init__(self, old_report, new_report):
        self.old_report = old_report
        self.new_report = new_report
        self.calls = []

    def run(self, tasks, skill):
        self.calls.append(skill)
        if len(self.calls) == 1:
            return self.old_report
        return self.new_report


def _report(scores, success_rate, avg):
    return BenchmarkReport(
        per_task=[("t", None, s) for s in scores],
        success_rate=success_rate,
        avg_total_score=avg,
    )


# ── win_rate 口径 ───────────────────────────────────────────────────────


def test_win_rate_computation():
    old_report = _report([0.5, 0.5, 0.5, 0.5], 0.5, 0.5)
    new_report = _report([0.7, 0.5, 0.4, 0.3], 0.5, 0.475)
    # a: 1, b: 0.5, c: 0, d: 0 → (1 + 0.5)/4 = 0.375
    assert _win_rate(old_report, new_report) == pytest.approx(0.375)


# ── 结局 1：样本不足 → 转人工 ───────────────────────────────────────────


def test_validate_sample_insufficient(tmp_path):
    registry, eval_store = _make_registry_and_store(tmp_path)
    registry.register(_make_skill(skill_id="s1", version="1.0.0", status="active"))
    candidate = _make_skill(skill_id="s1", version="1.0.1", status="draft")

    benchmark = _FakeBenchmark(_report([], 0.0, 0.0), _report([], 0.0, 0.0))
    validator = Validator(benchmark=benchmark, registry=registry, eval_store=eval_store)
    result = validator.validate("s1", candidate, [])  # 0 题 < 20

    assert result.promoted is False
    assert result.reason == "sample_insufficient"
    assert registry.get("s1", "1.0.1") is not None  # 候选已注册（draft 供人工）
    assert eval_store.list_experiences(skill_id="s1") == []  # 不写 failed_evolution


# ── 结局 2：通过 → promote + metrics 快照 ────────────────────────────────


def test_validate_promoted(tmp_path):
    registry, eval_store = _make_registry_and_store(tmp_path)
    registry.register(_make_skill(skill_id="s1", version="1.0.0", status="active"))
    candidate = _make_skill(skill_id="s1", version="1.0.1", status="draft")

    old_report = _report([0.5] * 20, 0.5, 0.5)
    new_report = _report([0.8] * 20, 0.8, 0.8)
    benchmark = _FakeBenchmark(old_report, new_report)
    validator = Validator(benchmark=benchmark, registry=registry, eval_store=eval_store)

    result = validator.validate("s1", candidate, [_make_task(f"t{i}") for i in range(20)])

    assert result.promoted is True
    assert result.reason == "promoted"
    assert result.win_rate == pytest.approx(1.0)
    assert registry.get_active("s1").version == "1.0.1"  # 候选成为 active
    assert registry.get("s1", "1.0.0").status == "deprecated"  # 旧版 deprecated

    got = registry.get("s1", "1.0.1")  # 历史版本可 get
    assert got.metrics["benchmark"]["win_rate"] == pytest.approx(1.0)
    assert got.metrics["benchmark"]["success_rate"] == 0.8
    assert got.metrics["benchmark"]["avg_total_score"] == 0.8


# ── 结局 3：不显著 → 丢弃 + failed_evolution ─────────────────────────────


def test_validate_insignificant(tmp_path):
    registry, eval_store = _make_registry_and_store(tmp_path)
    registry.register(_make_skill(skill_id="s1", version="1.0.0", status="active"))
    candidate = _make_skill(skill_id="s1", version="1.0.1", status="draft")

    # 19 持平 + 1 更高 → win_rate = (19*0.5 + 1)/20 = 0.525；new_avg 0.505 >= old_avg 0.5
    old_report = _report([0.5] * 20, 0.5, 0.5)
    new_report = _report([0.5] * 19 + [0.6], 0.5, 0.505)
    benchmark = _FakeBenchmark(old_report, new_report)
    validator = Validator(benchmark=benchmark, registry=registry, eval_store=eval_store)

    result = validator.validate("s1", candidate, [_make_task(f"t{i}") for i in range(20)])

    assert result.promoted is False
    assert result.reason == "insignificant"
    assert result.win_rate == pytest.approx(0.525)
    assert registry.get("s1", "1.0.1") is None  # 候选未注册（丢弃）

    exps = eval_store.list_experiences(skill_id="s1")
    assert len(exps) == 1
    assert exps[0].category == "failed_evolution"
    assert exps[0].trace_id == ""
    assert exps[0].suggestion == "insignificant"


# ── 结局 4：回归 → 丢弃 + failed_evolution ───────────────────────────────


def test_validate_regression(tmp_path):
    registry, eval_store = _make_registry_and_store(tmp_path)
    registry.register(_make_skill(skill_id="s1", version="1.0.0", status="active"))
    candidate = _make_skill(skill_id="s1", version="1.0.1", status="draft")

    old_report = _report([0.8] * 20, 0.8, 0.8)
    new_report = _report([0.4] * 20, 0.4, 0.4)  # 全部更低 → win_rate 0.0
    benchmark = _FakeBenchmark(old_report, new_report)
    validator = Validator(benchmark=benchmark, registry=registry, eval_store=eval_store)

    result = validator.validate("s1", candidate, [_make_task(f"t{i}") for i in range(20)])

    assert result.promoted is False
    assert result.reason == "regression"
    assert registry.get("s1", "1.0.1") is None  # 候选未注册

    exps = eval_store.list_experiences(skill_id="s1")
    assert len(exps) == 1
    assert exps[0].suggestion == "regression"
