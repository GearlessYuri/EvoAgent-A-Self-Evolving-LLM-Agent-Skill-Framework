"""Benchmark：任务集加载 + 批量「执行→评估→汇总」+ 报告（§3.3/§11）。

只编排 `AgentExecutor` + `Evaluator` 两个模块。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .. import config
from ..execution.executor import AgentExecutor
from ..models import BenchmarkTask, Skill, Task
from .evaluator import Evaluator


def load_tasks(path: str | Path) -> list[BenchmarkTask]:
    """从 JSON 文件加载任务列表（顶层为 JSON 数组，每项为 BenchmarkTask 字段）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"benchmark 文件顶层应为数组: {path}")
    return [BenchmarkTask.from_dict(d) for d in data]


def load_tasks_by_name(name: str) -> list[BenchmarkTask]:
    """按名称从默认目录加载：`{BENCHMARKS_DIR}/{name}.json`（如 regression / extension）。"""
    return load_tasks(Path(config.BENCHMARKS_DIR) / f"{name}.json")


@dataclasses.dataclass
class BenchmarkReport:
    per_task: list[tuple[str, bool | None, float]]  # (task_id, passed, total_score)
    success_rate: float      # passed is True 数 / (passed 非 None 数)；无可判对错任务 → 0.0
    avg_total_score: float   # 全部任务 total_score 均值；无任务 → 0.0

    def to_dict(self) -> dict:
        return {
            "per_task": [
                {"task_id": tid, "passed": passed, "total_score": score}
                for tid, passed, score in self.per_task
            ],
            "success_rate": self.success_rate,
            "avg_total_score": self.avg_total_score,
        }


class Benchmark:
    def __init__(self, executor: AgentExecutor, evaluator: Evaluator):
        self.executor = executor
        self.evaluator = evaluator

    def run(self, tasks: list[BenchmarkTask], skill: Skill) -> BenchmarkReport:
        per_task: list[tuple[str, bool | None, float]] = []
        for bt in tasks:
            task = Task(task=bt.task, task_source="benchmark")
            trace = self.executor.run(task, skill)
            result = self.evaluator.evaluate(
                trace, task,
                reference_answer=bt.reference_answer,
                rubric=bt.rubric,
                objective_check=bt.objective_check,
            )
            per_task.append((bt.task_id, result.passed, result.total_score))

        decided = [p for p in per_task if p[1] is not None]
        success_rate = (sum(1 for p in decided if p[1] is True) / len(decided)) if decided else 0.0
        avg_total_score = (sum(p[2] for p in per_task) / len(per_task)) if per_task else 0.0
        return BenchmarkReport(per_task=per_task, success_rate=success_rate, avg_total_score=avg_total_score)
