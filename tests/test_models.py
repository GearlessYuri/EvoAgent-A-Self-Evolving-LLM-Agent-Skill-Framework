"""数据结构 round-trip 测试（设计 §5–§11 的 8 个 dataclass）。"""

import dataclasses

import pytest

from evoagent.models import (
    BenchmarkTask,
    EvaluationResult,
    ExecutionTrace,
    Experience,
    FewShot,
    Skill,
    Task,
    ToolSpec,
    TraceStep,
)

ALL_DATACLASSES = [
    FewShot,
    ToolSpec,
    Skill,
    TraceStep,
    ExecutionTrace,
    EvaluationResult,
    Experience,
    BenchmarkTask,
    Task,
]


def test_all_dataclasses_defined():
    """验收标准 2：恰好 9 个 dataclass，且均为 dataclass。"""
    assert len(ALL_DATACLASSES) == 9
    for cls in ALL_DATACLASSES:
        assert dataclasses.is_dataclass(cls), cls.__name__


# ── 每个 dataclass 的 round-trip 用例 ────────────────────────────────────


def test_task_roundtrip():
    obj = Task(task="请审查以下代码", task_source="real")
    restored = Task.from_dict(obj.to_dict())
    assert restored == obj
    assert restored.task == "请审查以下代码"
    assert restored.task_source == "real"


def test_fewshot_roundtrip():
    obj = FewShot(input="Q: 2+2?", output="A: 4")
    assert FewShot.from_dict(obj.to_dict()) == obj


def test_toolspec_roundtrip():
    obj = ToolSpec(
        name="calculator",
        description="四则运算",
        parameters={"type": "object", "properties": {"expr": {"type": "string"}}},
    )
    assert ToolSpec.from_dict(obj.to_dict()) == obj


def test_skill_roundtrip_nested():
    obj = Skill(
        skill_id="code-review",
        name="Code Review",
        description="给代码提 review 意见",
        version="1.0.0",
        tags=["code", "python"],
        prompt_template="请审查以下代码：{task}",
        few_shots=[FewShot("a", "b"), FewShot("c", "d")],
        tools=[ToolSpec("file_rw", "只读文件", {"type": "object"})],
        status="active",
        parent_version="",
        change_log="init",
        metrics={"accuracy": 0.9},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-02T00:00:00Z",
    )
    restored = Skill.from_dict(obj.to_dict())
    assert restored == obj
    # 嵌套 dataclass 必须被重建为对应类型，而非退化为 dict
    assert isinstance(restored.few_shots[0], FewShot)
    assert isinstance(restored.few_shots[1], FewShot)
    assert isinstance(restored.tools[0], ToolSpec)
    assert restored.tags == ["code", "python"]
    assert restored.metrics == {"accuracy": 0.9}


def test_tracestep_roundtrip():
    obj = TraceStep(step_index=0, type="llm_call", content="hi", tool_name="", tokens=10, latency_ms=5)
    assert TraceStep.from_dict(obj.to_dict()) == obj


def test_execution_trace_roundtrip_usage_none():
    obj = ExecutionTrace(
        trace_id="t1",
        task_id="task1",
        task_source="real",
        skill_id="code-review",
        skill_version="1.0.0",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        steps=[TraceStep(0, "final", "done")],
        final_output="ok",
        status="success",
    )
    d = obj.to_dict()
    assert d["usage"] is None
    restored = ExecutionTrace.from_dict(d)
    assert restored == obj
    assert restored.usage is None
    assert isinstance(restored.steps[0], TraceStep)


def test_execution_trace_roundtrip_usage_dict():
    obj = ExecutionTrace(
        trace_id="t2",
        task_id="task2",
        task_source="benchmark",
        skill_id="code-review",
        skill_version="1.0.0",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        steps=[TraceStep(0, "tool_call", "call", tool_name="search")],
        final_output="ok",
        status="success",
        usage={"total_tokens": 1},
    )
    restored = ExecutionTrace.from_dict(obj.to_dict())
    assert restored == obj
    assert restored.usage == {"total_tokens": 1}


def test_experience_roundtrip():
    obj = Experience(
        experience_id="e1",
        trace_id="t1",
        skill_id="code-review",
        category="missing_step",
        summary="工具入参说明不清",
        target_section="tools",
        suggestion="补充入参示例",
        confidence=0.8,
    )
    assert Experience.from_dict(obj.to_dict()) == obj


def test_benchmark_task_roundtrip():
    obj = BenchmarkTask(
        task_id="b1",
        task="计算 2+2",
        rubric=["correctness", "format"],
        objective_check={"type": "exact", "value": "4"},
        tags=["math"],
        difficulty="easy",
    )
    restored = BenchmarkTask.from_dict(obj.to_dict())
    assert restored == obj
    assert restored.rubric == ["correctness", "format"]
    assert restored.tags == ["math"]
    assert restored.reference_answer == ""


# ── EvaluationResult.passed 三态精确保留 ────────────────────────────────


@pytest.mark.parametrize("passed", [True, False, None])
def test_evaluation_result_passed_tristate(passed):
    obj = EvaluationResult(
        eval_id="ev1",
        trace_id="t1",
        eval_basis="objective",
        passed=passed,
        total_score=0.8,
        objective={"matched": True},
        judge_score=0.0,
        rubric_scores={},
        judge_reason="",
        evaluated_at="2026-01-01T00:00:00Z",
    )
    restored = EvaluationResult.from_dict(obj.to_dict())
    assert restored == obj
    # 三态精确保留：True / False / None 不得被误判
    assert restored.passed is passed


# ── None 与空集区分 ─────────────────────────────────────────────────────


def test_none_vs_empty_list_distinction():
    obj = ExecutionTrace(
        trace_id="t3",
        task_id="task3",
        task_source="real",
        skill_id="s",
        skill_version="1.0.0",
        started_at="a",
        ended_at="b",
        steps=[],  # 空列表
        final_output="",
        status="success",
        usage=None,  # None
    )
    d = obj.to_dict()
    assert d["steps"] == []
    assert d["usage"] is None
    restored = ExecutionTrace.from_dict(d)
    # 空列表仍为 []，None 仍为 None（不得相互混淆）
    assert restored.steps == []
    assert restored.usage is None


# ── 默认值用例 ──────────────────────────────────────────────────────────


def test_default_values():
    trace = ExecutionTrace(
        trace_id="t",
        task_id="task",
        task_source="real",
        skill_id="s",
        skill_version="v",
        started_at="a",
        ended_at="b",
        steps=[],
        final_output="",
        status="success",
    )
    assert trace.error == ""
    assert trace.error_type == ""
    assert trace.retrieval_fallback is False
    assert trace.usage is None

    step = TraceStep(step_index=0, type="x", content="")
    assert step.tool_name == ""
    assert step.tokens == 0
    assert step.latency_ms == 0
