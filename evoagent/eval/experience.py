"""经验提炼：Trace + EvaluationResult → Experience[]（§8）。

只调 `llm`（chat_json）；纯返回不写库，落库由未来 EvolutionLoop 调 EvalStore.save_experience。
"""

from __future__ import annotations

import uuid

from ..llm import LLMClient
from ..models import EvaluationResult, ExecutionTrace, Experience

CATEGORIES = {
    "missing_step", "wrong_instruction", "bad_example",
    "tool_misuse", "hallucination", "good_pattern", "failed_evolution",
}
TARGET_SECTIONS = {"prompt_template", "few_shots", "tools"}
_MIN_CONFIDENCE = 0.5  # 低置信度过滤阈值（extractor 内部阈值，非全局 config）


def _extract_prompt(trace: ExecutionTrace, result: EvaluationResult) -> str:
    return (
        f"技能：{trace.skill_id}\n"
        f"任务状态：{trace.status}\n"
        f"最终输出：{trace.final_output}\n"
        f"评估：total_score={result.total_score}, passed={result.passed}, reason={result.judge_reason}\n"
        f"请提炼改进经验，输出 {{\"experiences\": [{{\"category\", \"target_section\", "
        f"\"summary\", \"suggestion\", \"confidence\"}}]}}"
    )


class ExperienceExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(self, trace: ExecutionTrace, result: EvaluationResult) -> list[Experience]:
        data = self.llm.chat_json(_extract_prompt(trace, result))
        raw_items = data.get("experiences", [])
        if not isinstance(raw_items, list):
            raw_items = []

        out: list[Experience] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            target_section = item.get("target_section")
            summary = str(item.get("summary", "")).strip()
            if category not in CATEGORIES or target_section not in TARGET_SECTIONS:
                continue  # 非法枚举：丢弃该条（§4.4 裁定）
            if not summary:
                continue  # summary 必填，空则丢弃（§2.1）
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            if confidence < _MIN_CONFIDENCE:
                continue  # 低置信度过滤（§9）
            out.append(Experience(
                experience_id=uuid.uuid4().hex,
                trace_id=trace.trace_id,
                skill_id=trace.skill_id,
                category=category,
                summary=summary,
                target_section=target_section,
                suggestion=str(item.get("suggestion", "")),
                confidence=confidence,
            ))
        return out
