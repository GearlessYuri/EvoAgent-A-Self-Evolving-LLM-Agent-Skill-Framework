"""演化主循环：收集低分 real trace → 按 skill 聚合 → 提炼 → 演化 → 验证 → 更新注册表（§3.5/§9）。

只编排下层模块，不重实现。
防污染（§11 规则 1）：只挖 task_source=="real" 的 trace。
"""

from __future__ import annotations

from .. import config
from ..eval.experience import ExperienceExtractor
from ..eval.store import EvalStore
from ..execution.trace import TraceStore
from ..models import BenchmarkTask
from ..skills.registry import SkillRegistry
from .evolver import SkillEvolver
from .validator import ValidationResult, Validator


class EvolutionLoop:
    def __init__(
        self,
        trace_store: TraceStore,
        eval_store: EvalStore,
        extractor: ExperienceExtractor,
        evolver: SkillEvolver,
        validator: Validator,
        registry: SkillRegistry,
    ):
        self.trace_store = trace_store
        self.eval_store = eval_store
        self.extractor = extractor
        self.evolver = evolver
        self.validator = validator
        self.registry = registry

    def run(self, tasks: list[BenchmarkTask]) -> list[ValidationResult]:
        # 1) 收集低分 real trace（内存过滤，summary trace 够用，不逐条 get）
        low_by_skill: dict[str, list] = {}
        for trace in self.trace_store.list():
            if trace.task_source != "real":       # §11 防污染：只挖 real
                continue
            if trace.error_type == "infra":      # §9：infra 不计
                continue
            for result in self.eval_store.list_evals(trace.trace_id):
                if result.passed is False:       # §9：只挖低分
                    low_by_skill.setdefault(trace.skill_id, []).append((trace, result))

        outcomes: list[ValidationResult] = []
        for skill_id, items in low_by_skill.items():
            if len(items) < config.MIN_EVOLUTION_SAMPLES:  # 样本不足跳过
                continue
            try:
                skill = self.registry.get_active(skill_id)
                if skill is None:                        # 无 active 跳过
                    continue
                experiences = []
                for trace, result in items:
                    experiences.extend(self.extractor.extract(trace, result))
                if not experiences:                      # 全被 confidence 过滤 → 跳过
                    continue
                candidate = self.evolver.evolve(skill, experiences)
                vr = self.validator.validate(skill_id, candidate, tasks)
                outcomes.append(vr)
            except Exception:
                continue  # 单 skill 失败跳过、不阻塞、不重试
        return outcomes
