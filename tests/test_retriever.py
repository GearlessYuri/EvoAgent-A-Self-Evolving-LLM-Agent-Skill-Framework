"""SkillRetriever 测试：检索正确性、兜底阈值、tag 过滤、边界（tmp_path 隔离）。"""

import pytest

from evoagent.models import Skill, Task
from evoagent.skills.registry import SkillRegistry
from evoagent.skills.retriever import (
    DEFAULT_SKILL,
    RetrievalHit,
    RetrievalResult,
    SkillRetriever,
)
from evoagent.storage import Storage


def _make_registry(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return SkillRegistry(storage, skills_dir=tmp_path / "skills")


def _register_skill(registry, skill_id, description, tags=None):
    registry.register(
        Skill(
            skill_id=skill_id,
            name=skill_id,
            description=description,
            version="1.0.0",
            tags=tags or [],
            prompt_template="dummy",
            few_shots=[],
            tools=[],
            status="active",
            parent_version="",
            change_log="",
            metrics={},
            created_at="",
            updated_at="",
        )
    )


# ── 检索正确性 ──────────────────────────────────────────────────────────


def test_retrieve_most_relevant_first_and_reproducible(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "code-review", "review and critique source code", ["code"])
    _register_skill(registry, "text-summarize", "summarize long text documents", ["nlp"])

    retriever = SkillRetriever(registry)
    task = Task(task="please review the source code", task_source="real")

    hits1 = retriever.retrieve(task, k=1)
    hits2 = retriever.retrieve(task, k=1)  # 确定性：同输入跑两次结果一致
    assert hits1 == hits2
    assert len(hits1) == 1
    assert hits1[0].skill_id == "code-review"
    assert hits1[0].score > 0

    # 分数降序（多候选）
    hits_all = retriever.retrieve(task, k=10)
    scores = [h.score for h in hits_all]
    assert scores == sorted(scores, reverse=True)


# ── 兜底 ────────────────────────────────────────────────────────────────


def test_retrieve_top1_relevant_returns_hit(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "code-review", "review and critique source code")
    retriever = SkillRetriever(registry)

    result = retriever.retrieve_top1(Task(task="review the source code", task_source="real"))
    assert result.fallback is False
    assert result.skill.skill_id == "code-review"
    assert result.score > 0


def test_retrieve_top1_fallback_no_shared_tokens(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "code-review", "review and critique source code")
    retriever = SkillRetriever(registry)

    result = retriever.retrieve_top1(Task(task="zzzz qqqq", task_source="real"))
    assert result.fallback is True
    assert result.score == 0.0
    assert result.skill is DEFAULT_SKILL


def test_retrieve_top1_empty_registry_fallback(tmp_path):
    registry = _make_registry(tmp_path)
    retriever = SkillRetriever(registry)

    result = retriever.retrieve_top1(Task(task="anything", task_source="real"))
    assert result.fallback is True
    assert result.score == 0.0
    assert result.skill is DEFAULT_SKILL


# ── tag 过滤 ────────────────────────────────────────────────────────────


def test_retrieve_tag_filter(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "code-review", "review and critique source code", ["code"])
    _register_skill(registry, "text-summarize", "summarize long text documents", ["nlp"])
    retriever = SkillRetriever(registry)

    hits = retriever.retrieve(Task(task="review source code", task_source="real"), k=10, tags=["code"])
    assert [h.skill_id for h in hits] == ["code-review"]


# ── 边界 ────────────────────────────────────────────────────────────────


def test_retrieve_k_less_than_one_raises(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "code-review", "review source code")
    retriever = SkillRetriever(registry)
    with pytest.raises(ValueError):
        retriever.retrieve(Task(task="x", task_source="real"), k=0)


def test_retrieve_k_greater_than_candidates(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "a", "review source code")
    _register_skill(registry, "b", "summarize text")
    _register_skill(registry, "c", "calculate math")
    retriever = SkillRetriever(registry)

    hits = retriever.retrieve(Task(task="x", task_source="real"), k=10)
    assert len(hits) == 3  # k 大于候选数 → 返回全部


def test_retrieve_empty_registry_returns_empty(tmp_path):
    registry = _make_registry(tmp_path)
    retriever = SkillRetriever(registry)
    assert retriever.retrieve(Task(task="x", task_source="real"), k=1) == []


def test_retrieve_empty_description_scores_zero(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "empty", "")  # 空 description
    retriever = SkillRetriever(registry)

    hits = retriever.retrieve(Task(task="some task", task_source="real"), k=1)
    assert len(hits) == 1
    assert hits[0].score == 0.0  # 零范数 → 0.0，不崩溃


# ── RetrievalHit / RetrievalResult 形态 ─────────────────────────────────


def test_retrieval_hit_and_result_shape(tmp_path):
    registry = _make_registry(tmp_path)
    _register_skill(registry, "code-review", "review and critique source code")
    retriever = SkillRetriever(registry)
    task = Task(task="review source code", task_source="real")

    hits = retriever.retrieve(task, k=1)
    assert isinstance(hits[0], RetrievalHit)
    assert hits[0].skill_id == "code-review"
    assert hits[0].version == "1.0.0"
    assert isinstance(hits[0].score, float)

    result = retriever.retrieve_top1(task)
    assert isinstance(result, RetrievalResult)
    assert isinstance(result.skill, Skill)
    assert isinstance(result.score, float)
    assert isinstance(result.fallback, bool)
