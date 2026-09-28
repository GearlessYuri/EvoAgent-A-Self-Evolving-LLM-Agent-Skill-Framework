"""SkillRegistry 测试：注册/读取往返、JSON 归档、状态机、单 active 不变量（tmp_path 隔离）。"""

import json

import pytest

from evoagent.models import FewShot, Skill, ToolSpec
from evoagent.skills.registry import SkillRegistry
from evoagent.storage import Storage


def _make_storage(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return storage


def _make_skill(skill_id="code-review", version="1.0.0", status="active", **overrides):
    kwargs = dict(
        skill_id=skill_id,
        name="Code Review",
        description="Review code",
        version=version,
        tags=["code", "python"],
        prompt_template="Review {task}",
        few_shots=[FewShot("a", "b")],
        tools=[ToolSpec("file_rw", "read file", {"type": "object"})],
        status=status,
        parent_version="",
        change_log="init",
        metrics={"accuracy": 0.9},
        created_at="2026-01-01",
        updated_at="2026-01-02",
    )
    kwargs.update(overrides)
    return Skill(**kwargs)


# ── register / get 往返 ─────────────────────────────────────────────────


def test_register_get_roundtrip(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    skill = _make_skill()
    registry.register(skill)

    got = registry.get("code-review", "1.0.0")
    assert got is not None
    assert got == skill
    # JSON 字段反序列化、list 与嵌套 dataclass 重建
    assert isinstance(got.metrics, dict) and got.metrics == {"accuracy": 0.9}
    assert isinstance(got.tags, list) and got.tags == ["code", "python"]
    assert isinstance(got.few_shots[0], FewShot)
    assert isinstance(got.tools[0], ToolSpec)


def test_json_archive_content(tmp_path):
    storage = _make_storage(tmp_path)
    skills_dir = tmp_path / "skills"
    registry = SkillRegistry(storage, skills_dir=skills_dir)
    registry.register(_make_skill())

    path = skills_dir / "code-review" / "1.0.0.json"
    assert path.exists()
    content = json.loads(path.read_text(encoding="utf-8"))
    # 内容本体仅 3 个字段
    assert set(content.keys()) == {"prompt_template", "few_shots", "tools"}
    assert content["prompt_template"] == "Review {task}"
    assert content["few_shots"] == [{"input": "a", "output": "b"}]
    assert content["tools"] == [
        {"name": "file_rw", "description": "read file", "parameters": {"type": "object"}}
    ]


def test_register_respects_status_draft(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(status="draft"))
    assert registry.get("code-review", "1.0.0").status == "draft"


def test_register_default_status_when_empty(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(status=""))
    assert registry.get("code-review", "1.0.0").status == "active"


# ── 状态机与单 active 不变量 ─────────────────────────────────────────────


def test_promote_single_active_invariant(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(version="1.0.0", status="active"))
    registry.register(_make_skill(version="2.0.0", status="candidate"))

    registry.promote("code-review", "2.0.0")

    assert registry.get_active("code-review").version == "2.0.0"
    assert registry.get("code-review", "1.0.0").status == "deprecated"
    active_rows = storage.query(
        "skills", where="skill_id = ? AND status = ?", params=("code-review", "active")
    )
    assert len(active_rows) == 1


def test_rollback_points_to_history(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(version="1.0.0", status="active"))
    registry.register(_make_skill(version="2.0.0", status="candidate"))
    registry.promote("code-review", "2.0.0")

    registry.rollback("code-review", "1.0.0")

    assert registry.get_active("code-review").version == "1.0.0"
    assert registry.get("code-review", "2.0.0").status == "deprecated"


def test_deprecate_makes_get_active_none(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(status="active"))

    registry.deprecate("code-review")

    assert registry.get_active("code-review") is None
    assert registry.get("code-review", "1.0.0").status == "deprecated"


# ── list 按 tags 过滤 ───────────────────────────────────────────────────


def test_list_all_active_sorted(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(skill_id="code-review", tags=["code", "python"]))
    registry.register(_make_skill(skill_id="text-summarize", tags=["nlp"]))
    registry.register(_make_skill(skill_id="qa", tags=["search", "math"]))

    assert [s.skill_id for s in registry.list()] == ["code-review", "qa", "text-summarize"]


def test_list_filter_by_tags_intersection(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(skill_id="code-review", tags=["code", "python"]))
    registry.register(_make_skill(skill_id="text-summarize", tags=["nlp"]))
    registry.register(_make_skill(skill_id="qa", tags=["search", "math"]))

    assert [s.skill_id for s in registry.list(tags=["python"])] == ["code-review"]
    # 多 tag：与给定列表有交集（至少一个匹配）
    assert {s.skill_id for s in registry.list(tags=["search", "python"])} == {
        "code-review",
        "qa",
    }
    # 无交集 → 空
    assert registry.list(tags=["nonexistent"]) == []


# ── 边界 ────────────────────────────────────────────────────────────────


def test_get_missing_returns_none(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    assert registry.get("nope", "1.0.0") is None
    assert registry.get_active("nope") is None


def test_promote_missing_version_raises(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill())
    with pytest.raises(ValueError):
        registry.promote("code-review", "9.9.9")


def test_rollback_missing_version_raises(tmp_path):
    storage = _make_storage(tmp_path)
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill())
    with pytest.raises(ValueError):
        registry.rollback("code-review", "9.9.9")


def test_get_missing_json_raises(tmp_path):
    storage = _make_storage(tmp_path)
    skills_dir = tmp_path / "skills"
    registry = SkillRegistry(storage, skills_dir=skills_dir)
    registry.register(_make_skill())
    (skills_dir / "code-review" / "1.0.0.json").unlink()
    with pytest.raises(FileNotFoundError):
        registry.get("code-review", "1.0.0")
