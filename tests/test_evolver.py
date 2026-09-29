"""SkillEvolver 测试：候选字段 + 缺键兜底 + 防污染（mock LLMClient.chat_json）。"""

import inspect

from evoagent.evolution.evolver import SkillEvolver, _bump_patch
from evoagent.models import Experience, FewShot, Skill


def _make_skill(version="1.2.3", **overrides):
    kwargs = dict(
        skill_id="code-review",
        name="Code Review",
        description="review code",
        version=version,
        tags=["code"],
        prompt_template="旧模板 {task}",
        few_shots=[FewShot("a", "b")],
        tools=[],
        status="active",
        parent_version="",
        change_log="init",
        metrics={},
        created_at="",
        updated_at="",
    )
    kwargs.update(overrides)
    return Skill(**kwargs)


def _make_experience(summary="缺一步", suggestion="补一步"):
    return Experience(
        experience_id="e1",
        trace_id="t1",
        skill_id="code-review",
        category="missing_step",
        summary=summary,
        target_section="tools",
        suggestion=suggestion,
        confidence=0.9,
    )


class _FakeLLM:
    def __init__(self, data):
        self.data = data
        self.prompts = []

    def chat_json(self, prompt):
        self.prompts.append(prompt)
        return self.data


def test_evolve_candidate_fields():
    llm = _FakeLLM({
        "prompt_template": "新模板 {task}",
        "few_shots": [{"input": "x", "output": "y"}],
        "change_log": "改 prompt",
    })
    evolver = SkillEvolver(llm=llm)
    skill = _make_skill(version="1.2.3")
    candidate = evolver.evolve(skill, [_make_experience()])

    assert candidate.version == "1.2.4"  # patch 递增
    assert candidate.parent_version == "1.2.3"
    assert candidate.status == "draft"
    assert candidate.change_log == "改 prompt"
    assert candidate.tools == []  # tools 原样
    assert candidate.metrics == {}
    assert candidate.prompt_template == "新模板 {task}"
    assert candidate.few_shots == [FewShot("x", "y")]


def test_bump_patch():
    assert _bump_patch("1.2.3") == "1.2.4"
    assert _bump_patch("0.0.9") == "0.0.10"
    assert _bump_patch("invalid") == "0.0.1"
    assert _bump_patch("1.2") == "0.0.1"


def test_evolve_fallback_on_missing_keys():
    llm = _FakeLLM({})  # 缺所有键
    evolver = SkillEvolver(llm=llm)
    skill = _make_skill(version="1.0.0", few_shots=[FewShot("a", "b")])
    candidate = evolver.evolve(skill, [_make_experience(), _make_experience()])

    assert candidate.prompt_template == "旧模板 {task}"  # 回退旧模板
    assert candidate.few_shots == [FewShot("a", "b")]  # 回退旧 few_shots
    assert candidate.change_log  # 默认非空
    assert "2 条经验" in candidate.change_log


def test_evolve_fallback_few_shots_not_list():
    llm = _FakeLLM({"prompt_template": "新", "few_shots": "not a list", "change_log": "c"})
    evolver = SkillEvolver(llm=llm)
    skill = _make_skill(few_shots=[FewShot("a", "b")])
    candidate = evolver.evolve(skill, [])
    assert candidate.few_shots == [FewShot("a", "b")]  # 回退旧 few_shots


def test_evolve_signature_has_no_reference_answer():
    sig = inspect.signature(SkillEvolver.evolve)
    params = list(sig.parameters)
    assert "reference_answer" not in params
    assert "rubric" not in params
    assert "benchmark" not in params


def test_evolve_prompt_excludes_reference_answer():
    llm = _FakeLLM({"prompt_template": "新模板", "change_log": "c"})
    evolver = SkillEvolver(llm=llm)
    skill = _make_skill()
    evolver.evolve(skill, [_make_experience(summary="某经验", suggestion="某建议")])

    prompt = llm.prompts[0]
    assert "code-review" in prompt  # 含 skill 内容
    assert "旧模板" in prompt
    assert "某经验" in prompt  # 含 experience 内容
    assert "SENTINEL_ANSWER" not in prompt  # 参考答案哨兵不进 prompt
