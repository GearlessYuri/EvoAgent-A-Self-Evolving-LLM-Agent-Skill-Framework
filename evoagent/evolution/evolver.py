"""技能演化器：Experience[] → 候选新版本（§3.4/§9）。

只调 `llm`（chat_json）。
v1 不改 `tools`（工具子集校验依赖 tools.py，未建）；版本恒 patch 递增。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..llm import LLMClient
from ..models import Experience, FewShot, Skill


def _bump_patch(version: str) -> str:
    """SemVer patch 递增：`x.y.z` → `x.y.(z+1)`；无法解析 → `"0.0.1"`。"""
    parts = version.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major, minor, patch = parts
        return f"{major}.{minor}.{int(patch) + 1}"
    return "0.0.1"


def _evolve_prompt(skill: Skill, experiences: list[Experience]) -> str:
    lines = [
        f"技能：{skill.skill_id} v{skill.version}",
        f"当前 prompt_template：{skill.prompt_template}",
        "经验：",
    ]
    for exp in experiences:
        lines.append(f"- [{exp.target_section}] {exp.summary} → {exp.suggestion}")
    lines.append(
        "请输出 JSON：{\"prompt_template\": 新模板, \"few_shots\": [{\"input\",\"output\"}], \"change_log\": 改动说明}"
    )
    return "\n".join(lines)


class SkillEvolver:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def evolve(self, skill: Skill, experiences: list[Experience]) -> Skill:
        data = self.llm.chat_json(_evolve_prompt(skill, experiences))

        prompt_template = data.get("prompt_template")
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            prompt_template = skill.prompt_template

        raw_shots = data.get("few_shots")
        if isinstance(raw_shots, list) and all(isinstance(x, dict) for x in raw_shots):
            few_shots = [FewShot.from_dict(x) for x in raw_shots]
        else:
            few_shots = list(skill.few_shots)

        change_log = str(data.get("change_log", "")).strip()
        if not change_log:
            change_log = f"基于 {len(experiences)} 条经验演化"

        now = datetime.now(timezone.utc).isoformat()
        return Skill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=_bump_patch(skill.version),
            tags=list(skill.tags),
            prompt_template=prompt_template,
            few_shots=few_shots,
            tools=list(skill.tools),
            status="draft",
            parent_version=skill.version,
            change_log=change_log,
            metrics={},
            created_at=now,
            updated_at=now,
        )
