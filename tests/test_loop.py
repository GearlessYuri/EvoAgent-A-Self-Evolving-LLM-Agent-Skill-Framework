"""EvolutionLoop 测试：全链路 + 防污染 + 边界（mock 六模块）。"""

from evoagent.evolution.loop import EvolutionLoop
from evoagent.evolution.validator import ValidationResult
from evoagent.models import BenchmarkTask, EvaluationResult, ExecutionTrace, Experience, Skill


def _make_trace(trace_id, skill_id, task_source="real", error_type=""):
    return ExecutionTrace(
        trace_id=trace_id,
        task_id="t",
        task_source=task_source,
        skill_id=skill_id,
        skill_version="1.0.0",
        started_at="a",
        ended_at="b",
        steps=[],
        final_output="out",
        status="success",
        error_type=error_type,
    )


def _make_result(trace_id, passed=False):
    return EvaluationResult(
        eval_id="e", trace_id=trace_id, eval_basis="objective", passed=passed,
        total_score=0.0, objective={}, judge_score=0.0, rubric_scores={},
        judge_reason="", evaluated_at="2026-01-01",
    )


def _make_experience():
    return Experience(
        experience_id="x", trace_id="t", skill_id="s1", category="missing_step",
        summary="缺一步", target_section="tools", suggestion="补一步", confidence=0.9,
    )


def _make_skill(skill_id="s1", version="1.0.0", status="active"):
    return Skill(
        skill_id=skill_id, name="s", description="d", version=version, tags=[],
        prompt_template="处理 {task}", few_shots=[], tools=[], status=status,
        parent_version="", change_log="", metrics={}, created_at="", updated_at="",
    )


def _make_task(task_id="b1"):
    return BenchmarkTask(
        task_id=task_id, task="t", reference_answer="", rubric=[], objective_check={},
        tags=[], difficulty="easy",
    )


class _FakeTraceStore:
    def __init__(self, traces):
        self.traces = traces

    def list(self):
        return self.traces


class _FakeEvalStore:
    def __init__(self, evals_by_trace):
        self.evals_by_trace = evals_by_trace

    def list_evals(self, trace_id):
        return self.evals_by_trace.get(trace_id, [])


class _FakeExtractor:
    def __init__(self, experiences):
        self.experiences = experiences
        self.calls = []

    def extract(self, trace, result):
        self.calls.append((trace, result))
        return list(self.experiences)


class _FakeEvolver:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = []

    def evolve(self, skill, experiences):
        self.calls.append((skill, experiences))
        return self.candidate


class _FakeValidator:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def validate(self, skill_id, candidate, tasks):
        self.calls.append((skill_id, candidate, tasks))
        return self.results.pop(0)


class _FakeRegistry:
    def __init__(self, active):
        self.active = active

    def get_active(self, skill_id):
        return self.active


def _make_loop(trace_store, eval_store, extractor, evolver, validator, registry):
    return EvolutionLoop(trace_store, eval_store, extractor, evolver, validator, registry)


def test_run_full_chain():
    trace = _make_trace("t1", "s1", task_source="real", error_type="")
    trace_store = _FakeTraceStore([trace])
    eval_store = _FakeEvalStore({"t1": [_make_result("t1", passed=False)]})
    extractor = _FakeExtractor([_make_experience()])
    evolver = _FakeEvolver(_make_skill(version="2.0.0", status="draft"))
    validator = _FakeValidator([ValidationResult(False, 0.4, 0.5, 0.4, 20, "regression")])
    registry = _FakeRegistry(_make_skill(version="1.0.0", status="active"))

    outcomes = _make_loop(trace_store, eval_store, extractor, evolver, validator, registry).run([_make_task()])

    assert len(outcomes) == 1
    assert outcomes[0].reason == "regression"
    assert len(extractor.calls) == 1
    assert len(evolver.calls) == 1
    assert len(validator.calls) == 1
    assert validator.calls[0][0] == "s1"


def test_run_excludes_benchmark_and_infra():
    real_trace = _make_trace("t1", "s1", task_source="real", error_type="")
    bench_trace = _make_trace("t2", "s1", task_source="benchmark", error_type="")
    infra_trace = _make_trace("t3", "s1", task_source="real", error_type="infra")

    trace_store = _FakeTraceStore([bench_trace, infra_trace, real_trace])
    eval_store = _FakeEvalStore({
        "t1": [_make_result("t1", passed=False)],
        "t2": [_make_result("t2", passed=False)],
        "t3": [_make_result("t3", passed=False)],
    })
    extractor = _FakeExtractor([_make_experience()])
    evolver = _FakeEvolver(_make_skill(version="2.0.0", status="draft"))
    validator = _FakeValidator([ValidationResult(False, 0.4, 0.5, 0.4, 20, "regression")])
    registry = _FakeRegistry(_make_skill(version="1.0.0", status="active"))

    _make_loop(trace_store, eval_store, extractor, evolver, validator, registry).run([_make_task()])

    # 只有 real 且非 infra 的 t1 触发 extract
    assert len(extractor.calls) == 1
    assert extractor.calls[0][0].trace_id == "t1"


def test_run_sample_threshold_skips(monkeypatch):
    monkeypatch.setattr("evoagent.config.MIN_EVOLUTION_SAMPLES", 2)
    trace = _make_trace("t1", "s1", task_source="real", error_type="")
    trace_store = _FakeTraceStore([trace])
    eval_store = _FakeEvalStore({"t1": [_make_result("t1", passed=False)]})
    extractor = _FakeExtractor([_make_experience()])
    evolver = _FakeEvolver(_make_skill(version="2.0.0", status="draft"))
    validator = _FakeValidator([])
    registry = _FakeRegistry(_make_skill(version="1.0.0", status="active"))

    outcomes = _make_loop(trace_store, eval_store, extractor, evolver, validator, registry).run([_make_task()])

    assert outcomes == []  # 1 < 2 跳过
    assert extractor.calls == []


def test_run_get_active_none_skips():
    trace = _make_trace("t1", "s1", task_source="real", error_type="")
    trace_store = _FakeTraceStore([trace])
    eval_store = _FakeEvalStore({"t1": [_make_result("t1", passed=False)]})
    extractor = _FakeExtractor([_make_experience()])
    evolver = _FakeEvolver(_make_skill(version="2.0.0", status="draft"))
    validator = _FakeValidator([])
    registry = _FakeRegistry(None)  # 无 active

    outcomes = _make_loop(trace_store, eval_store, extractor, evolver, validator, registry).run([_make_task()])

    assert outcomes == []
    assert extractor.calls == []


def test_run_extract_empty_skips():
    trace = _make_trace("t1", "s1", task_source="real", error_type="")
    trace_store = _FakeTraceStore([trace])
    eval_store = _FakeEvalStore({"t1": [_make_result("t1", passed=False)]})
    extractor = _FakeExtractor([])  # 返回空
    evolver = _FakeEvolver(_make_skill(version="2.0.0", status="draft"))
    validator = _FakeValidator([])
    registry = _FakeRegistry(_make_skill(version="1.0.0", status="active"))

    outcomes = _make_loop(trace_store, eval_store, extractor, evolver, validator, registry).run([_make_task()])

    assert outcomes == []
    assert evolver.calls == []


class _RaisingEvolver:
    def __init__(self):
        self.calls = []

    def evolve(self, skill, experiences):
        self.calls.append(skill.skill_id)
        if skill.skill_id == "s2":
            raise RuntimeError("boom")
        return _make_skill(version="2.0.0", status="draft")


def test_run_single_skill_exception_does_not_block():
    t1 = _make_trace("t1", "s1", task_source="real", error_type="")
    t2 = _make_trace("t2", "s2", task_source="real", error_type="")
    trace_store = _FakeTraceStore([t1, t2])
    eval_store = _FakeEvalStore({
        "t1": [_make_result("t1", passed=False)],
        "t2": [_make_result("t2", passed=False)],
    })
    extractor = _FakeExtractor([_make_experience()])
    evolver = _RaisingEvolver()
    validator = _FakeValidator([ValidationResult(False, 0.4, 0.5, 0.4, 20, "regression")])

    class _SkillIdRegistry:
        def get_active(self, skill_id):
            return _make_skill(skill_id=skill_id, version="1.0.0", status="active")

    outcomes = _make_loop(trace_store, eval_store, extractor, evolver, validator, _SkillIdRegistry()).run([_make_task()])

    # s2 抛异常被跳过，s1 正常 → 1 个 outcome
    assert len(outcomes) == 1
    assert evolver.calls == ["s1", "s2"]
