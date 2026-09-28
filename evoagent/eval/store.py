"""评估结果 / 经验持久化门面（§3.3 evals / experiences 表门面）。

只经 `Storage` 的通用 CRUD 持久化，不直接操作 SQLite、不访问 `storage.conn`。
`passed` 三态在门面侧做 `True→1` / `False→0` / `None→NULL` 及读回逆转换；
JSON 字段（`objective` / `rubric_scores`）读回时 `json.loads` 还原为 dict。
"""

from __future__ import annotations

import json

from ..models import EvaluationResult, Experience
from ..storage import Storage


def _passed_to_int(passed: bool | None):
    """`passed` 三态 → 存储值：True→1、False→0、None→NULL。"""
    return None if passed is None else (1 if passed else 0)


def _passed_from_row(value):
    """存储值 → `passed` 三态：1→True、0→False、NULL→None。"""
    return None if value is None else bool(value)


class EvalStore:
    """evals / experiences 表门面（§3.3）。"""

    def __init__(self, storage: Storage):
        self.storage = storage

    # ── 评估结果 ────────────────────────────────────────────────────────

    def save_eval(self, result: EvaluationResult) -> None:
        """写 `evals` 表；重复 `eval_id` 由底层上抛 IntegrityError。"""
        self.storage.insert(
            "evals",
            {
                "eval_id": result.eval_id,
                "trace_id": result.trace_id,
                "eval_basis": result.eval_basis,
                "passed": _passed_to_int(result.passed),
                "total_score": result.total_score,
                "objective": result.objective,  # dict，由 Storage 自动 json.dumps
                "judge_score": result.judge_score,
                "rubric_scores": result.rubric_scores,  # dict，自动 json.dumps
                "judge_reason": result.judge_reason,
                "evaluated_at": result.evaluated_at,
            },
        )

    def get_eval(self, eval_id: str) -> EvaluationResult | None:
        """读 `evals` 行并逆转换（`passed` 三态 + JSON 反序列化）；不存在 → `None`。"""
        rows = self.storage.query("evals", where="eval_id = ?", params=(eval_id,))
        if not rows:
            return None
        return self._eval_from_row(rows[0])

    def list_evals(self, trace_id: str | None = None) -> list[EvaluationResult]:
        """按 `trace_id`（若给）过滤，返回完整 `EvaluationResult` 列表。"""
        if trace_id is None:
            rows = self.storage.query("evals")
        else:
            rows = self.storage.query("evals", where="trace_id = ?", params=(trace_id,))
        return [self._eval_from_row(row) for row in rows]

    def _eval_from_row(self, row: dict) -> EvaluationResult:
        return EvaluationResult.from_dict(
            {
                "eval_id": row["eval_id"],
                "trace_id": row["trace_id"],
                "eval_basis": row["eval_basis"],
                "passed": _passed_from_row(row["passed"]),
                "total_score": row["total_score"],
                "objective": json.loads(row["objective"]),
                "judge_score": row["judge_score"],
                "rubric_scores": json.loads(row["rubric_scores"]),
                "judge_reason": row["judge_reason"],
                "evaluated_at": row["evaluated_at"],
            }
        )

    # ── 经验 ────────────────────────────────────────────────────────────

    def save_experience(self, exp: Experience) -> None:
        """写 `experiences` 表（全标量字段）；重复 `experience_id` 上抛 IntegrityError。"""
        self.storage.insert(
            "experiences",
            {
                "experience_id": exp.experience_id,
                "trace_id": exp.trace_id,
                "skill_id": exp.skill_id,
                "category": exp.category,
                "summary": exp.summary,
                "target_section": exp.target_section,
                "suggestion": exp.suggestion,
                "confidence": exp.confidence,
            },
        )

    def list_experiences(self, skill_id: str | None = None) -> list[Experience]:
        """按 `skill_id`（若给）过滤，返回 `Experience` 列表。"""
        if skill_id is None:
            rows = self.storage.query("experiences")
        else:
            rows = self.storage.query("experiences", where="skill_id = ?", params=(skill_id,))
        return [
            Experience.from_dict(
                {
                    "experience_id": row["experience_id"],
                    "trace_id": row["trace_id"],
                    "skill_id": row["skill_id"],
                    "category": row["category"],
                    "summary": row["summary"],
                    "target_section": row["target_section"],
                    "suggestion": row["suggestion"],
                    "confidence": row["confidence"],
                }
            )
            for row in rows
        ]
