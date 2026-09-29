"""验证器：Benchmark A/B → win_rate 判定 → promote / 丢弃 / 转人工（§9/§11）。

只调 `benchmark` / `registry` / `eval_store`。
"""

from __future__ import annotations

import dataclasses
import uuid

from .. import config
from ..eval.benchmark import Benchmark, BenchmarkTask
from ..eval.store import EvalStore
from ..models import Experience, Skill
from ..skills.registry import SkillRegistry


@dataclasses.dataclass
class ValidationResult:
    promoted: bool
    win_rate: float
    old_avg: float
    new_avg: float
    sample_size: int
    reason: str  # "promoted" | "sample_insufficient" | "insignificant" | "regression"


def _win_rate(old_report, new_report) -> float:
    """逐任务配对：new_score 更高记 1、持平记 0.5、更低记 0，取均值（§11）。"""
    n = len(old_report.per_task)
    if n == 0:
        return 0.0
    wins = 0.0
    for (_, _, old_score), (_, _, new_score) in zip(old_report.per_task, new_report.per_task):
        if new_score > old_score:
            wins += 1.0
        elif new_score == old_score:
            wins += 0.5
    return wins / n


class Validator:
    def __init__(self, benchmark: Benchmark, registry: SkillRegistry, eval_store: EvalStore):
        self.benchmark = benchmark
        self.registry = registry
        self.eval_store = eval_store

    def validate(self, skill_id: str, candidate: Skill, tasks: list[BenchmarkTask]) -> ValidationResult:
        old = self.registry.get_active(skill_id)
        old_report = self.benchmark.run(tasks, old)
        new_report = self.benchmark.run(tasks, candidate)

        win_rate = _win_rate(old_report, new_report)
        old_avg = old_report.avg_total_score
        new_avg = new_report.avg_total_score
        sample_size = len(tasks)

        # 结局 1：样本不足 → 转人工（register 留 draft，不写 failed_evolution）
        if sample_size < config.MIN_REGRESSION_TASKS:
            self.registry.register(candidate)
            return ValidationResult(False, win_rate, old_avg, new_avg, sample_size, "sample_insufficient")

        # 结局 2：通过 → register(draft) + promote，metrics 快照
        if win_rate >= config.PROMOTE_WIN_RATE_THRESHOLD and new_avg >= old_avg:
            candidate.metrics = {
                "benchmark": {
                    "win_rate": win_rate,
                    "success_rate": new_report.success_rate,
                    "avg_total_score": new_avg,
                }
            }
            self.registry.register(candidate)
            self.registry.promote(skill_id, candidate.version)
            return ValidationResult(True, win_rate, old_avg, new_avg, sample_size, "promoted")

        # 结局 3：不显著（0.5 < win_rate < 0.55 且 avg 不降）→ 丢弃 + failed_evolution
        if win_rate > 0.5 and new_avg >= old_avg:
            self._record_failed_evolution(skill_id, win_rate, old_avg, new_avg, "insignificant")
            return ValidationResult(False, win_rate, old_avg, new_avg, sample_size, "insignificant")

        # 结局 4：回归（win_rate ≤ 0.5 或 avg 下降）→ 丢弃 + failed_evolution
        self._record_failed_evolution(skill_id, win_rate, old_avg, new_avg, "regression")
        return ValidationResult(False, win_rate, old_avg, new_avg, sample_size, "regression")

    def _record_failed_evolution(self, skill_id, win_rate, old_avg, new_avg, reason):
        self.eval_store.save_experience(Experience(
            experience_id=uuid.uuid4().hex,
            trace_id="",  # 演化失败无关联 trace（§3.3 裁定）
            skill_id=skill_id,
            category="failed_evolution",
            summary=f"演化验证未通过：win_rate={win_rate:.3f}, old_avg={old_avg:.3f}, new_avg={new_avg:.3f}",
            target_section="",
            suggestion=reason,  # "insignificant" / "regression"
            confidence=1.0,
        ))
