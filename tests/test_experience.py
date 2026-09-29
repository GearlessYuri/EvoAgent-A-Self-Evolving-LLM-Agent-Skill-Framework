"""ExperienceExtractor 测试：结构化提取 + confidence 过滤 + 非法字段丢弃（mock LLM）。"""

import pytest

from evoagent.eval.experience import ExperienceExtractor
from evoagent.models import EvaluationResult, ExecutionTrace


def _make_trace():
    return ExecutionTrace(
        trace_id="t1",
        task_id="task1",
        task_source="real",
        skill_id="s1",
        skill_version="1.0.0",
        started_at="a",
        ended_at="b",
        steps=[],
        final_output="out",
        status="success",
    )


def _make_result():
    return EvaluationResult(
        eval_id="e1",
        trace_id="t1",
        eval_basis="mixed",
        passed=True,
        total_score=0.8,
        objective={},
        judge_score=0.8,
        rubric_scores={},
        judge_reason="ok",
        evaluated_at="2026-01-01",
    )


class _FakeLLM:
    def __init__(self, data):
        self.data = data

    def chat_json(self, prompt):
        return self.data


def test_extract_returns_experiences():
    llm = _FakeLLM({"experiences": [
        {"category": "missing_step", "target_section": "tools",
         "summary": "缺一步", "suggestion": "补一步", "confidence": 0.9},
    ]})
    extractor = ExperienceExtractor(llm=llm)
    exps = extractor.extract(_make_trace(), _make_result())

    assert len(exps) == 1
    exp = exps[0]
    assert exp.category == "missing_step"
    assert exp.target_section == "tools"
    assert exp.summary == "缺一步"
    assert exp.suggestion == "补一步"
    assert exp.confidence == 0.9
    assert exp.trace_id == "t1"
    assert exp.skill_id == "s1"


def test_extract_filters_low_confidence():
    llm = _FakeLLM({"experiences": [
        {"category": "good_pattern", "target_section": "prompt_template",
         "summary": "好", "confidence": 0.3},  # 低置信度，丢弃
        {"category": "good_pattern", "target_section": "prompt_template",
         "summary": "好", "confidence": 0.8},
    ]})
    extractor = ExperienceExtractor(llm=llm)
    exps = extractor.extract(_make_trace(), _make_result())

    assert len(exps) == 1
    assert exps[0].confidence == 0.8


def test_extract_drops_invalid_enum_and_empty_summary():
    llm = _FakeLLM({"experiences": [
        {"category": "unknown_cat", "target_section": "tools", "summary": "x", "confidence": 0.9},
        {"category": "missing_step", "target_section": "unknown_sec", "summary": "x", "confidence": 0.9},
        {"category": "missing_step", "target_section": "tools", "summary": "", "confidence": 0.9},
        {"category": "missing_step", "target_section": "tools", "summary": "ok", "confidence": 0.9},
    ]})
    extractor = ExperienceExtractor(llm=llm)
    exps = extractor.extract(_make_trace(), _make_result())

    assert len(exps) == 1
    assert exps[0].summary == "ok"


def test_extract_non_list_experiences_returns_empty():
    llm = _FakeLLM({"experiences": "not a list"})
    extractor = ExperienceExtractor(llm=llm)
    assert extractor.extract(_make_trace(), _make_result()) == []


def test_extract_propagates_chat_json_error():
    class _RaisingLLM:
        def chat_json(self, prompt):
            raise ValueError("non-json")

    extractor = ExperienceExtractor(llm=_RaisingLLM())
    with pytest.raises(ValueError):
        extractor.extract(_make_trace(), _make_result())
