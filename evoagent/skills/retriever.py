"""技能检索器：按任务语义挑最相关 Skill（简单版：词频 + 余弦相似度，§3.2）。

只读 `SkillRegistry` 门面接口，不直接操作 SQLite / `Storage`。
评分信号仅用 `skill.description` 与 `task.task` 的词频余弦；top-1 低于阈值时走
内置 `DEFAULT_SKILL` 兜底（仅检索器常量，不写注册表、不落 JSON 归档）。
"""

from __future__ import annotations

import math
import re
import typing
from collections import Counter

from .. import config
from ..models import Skill, Task
from .registry import SkillRegistry

# 内置兜底技能（§3.2 检索无匹配兜底；不写库、不落 JSON 归档，种子写库属 §12 后续事务）
DEFAULT_SKILL: Skill = Skill(
    skill_id="_default",
    name="Default",
    description="通用任务兜底技能",
    version="0.0.0",
    tags=[],
    prompt_template="你是一个通用助手，请完成以下任务：{task}",
    few_shots=[],
    tools=[],
    status="active",
    parent_version="",
    change_log="",
    metrics={},
    created_at="",
    updated_at="",
)


class RetrievalHit(typing.NamedTuple):
    skill_id: str
    version: str
    score: float  # 余弦相似度，0~1


class RetrievalResult(typing.NamedTuple):
    skill: Skill  # 命中技能 或 DEFAULT_SKILL（兜底时）
    score: float  # 命中为其余弦分数；兜底为 0.0
    fallback: bool  # True=走 default 兜底；False=正常命中


def _tokenize(text: str) -> list[str]:
    """小写 + 按非字母数字切分（`\\w` 含 Unicode，中英文均可）。"""
    return re.findall(r"\w+", text.lower())


def _term_frequency(tokens: list[str]) -> dict[str, int]:
    """词频向量。"""
    return dict(Counter(tokens))


def _cosine_similarity(a: dict[str, int], b: dict[str, int]) -> float:
    """余弦相似度；任一向量零范数（空文本 / 无共享 token）→ 0.0，不抛异常。"""
    dot = sum(a[t] * b[t] for t in a if t in b)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SkillRetriever:
    """任务 → top-k skill（§3.2 简单版，纯标准库、确定性）。"""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def retrieve(
        self, task: Task, k: int = 1, tags: list[str] | None = None
    ) -> list[RetrievalHit]:
        """对候选 active Skill 按余弦相似度降序返回 top-k（无兜底、不含 default）。

        `tags` 非空时先按交集过滤（复用 `registry.list(tags=...)`）。
        `k < 1` → `ValueError`；`k` 大于候选数 → 返回全部；空注册表 → `[]`。
        """
        if k < 1:
            raise ValueError("k must be >= 1")

        task_vec = _term_frequency(_tokenize(task.task))
        hits = []
        for skill in self.registry.list(tags=tags):
            desc_vec = _term_frequency(_tokenize(skill.description))
            score = _cosine_similarity(task_vec, desc_vec)
            hits.append(RetrievalHit(skill.skill_id, skill.version, score))

        hits.sort(key=lambda h: (-h.score, h.skill_id))
        return hits[:k]

    def retrieve_top1(self, task: Task) -> RetrievalResult:
        """top-1 + 阈值兜底：命中且 `score >= 阈值` 返回命中；否则返回 DEFAULT_SKILL。"""
        hits = self.retrieve(task, k=1)
        if hits and hits[0].score >= config.RETRIEVAL_FALLBACK_THRESHOLD:
            skill = self.registry.get(hits[0].skill_id, hits[0].version)
            return RetrievalResult(skill, hits[0].score, fallback=False)
        return RetrievalResult(DEFAULT_SKILL, 0.0, fallback=True)
