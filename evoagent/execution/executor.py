"""执行器 v1：单轮、无工具调用（§3.2 骨架）。

拼 prompt（模板 `{task}` 替换 + few-shot 追加）→ 调 `LLMClient.complete_with_usage` →
写 `TraceStore`。只依赖 `llm` / `trace_store` 两个模块。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..llm import LLMClient
from ..models import ExecutionTrace, Skill, Task, TraceStep
from .trace import TraceStore


def _render_prompt(skill: Skill, task: Task) -> str:
    """拼 prompt：`{task}` 替换为任务文本 + few-shot 追加（确定性格式）。"""
    prompt = skill.prompt_template.replace("{task}", task.task)
    if skill.few_shots:
        shots = []
        for i, fs in enumerate(skill.few_shots, start=1):
            shots.append(f"示例 {i}：\n输入：{fs.input}\n输出：{fs.output}")
        prompt = prompt + "\n\n" + "\n\n".join(shots)
    return prompt


class AgentExecutor:
    def __init__(self, llm: LLMClient, trace_store: TraceStore):
        self.llm = llm
        self.trace_store = trace_store

    def run(self, task: Task, skill: Skill, *, retrieval_fallback: bool = False) -> ExecutionTrace:
        trace_id = uuid.uuid4().hex
        task_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()

        prompt = _render_prompt(skill, task)

        try:
            answer, usage = self.llm.complete_with_usage(prompt)
        except Exception as exc:  # 仅捕获 LLM 调用异常；模板渲染已用 replace，不会抛
            ended_at = datetime.now(timezone.utc).isoformat()
            trace = ExecutionTrace(
                trace_id=trace_id,
                task_id=task_id,
                task_source=task.task_source,
                skill_id=skill.skill_id,
                skill_version=skill.version,
                started_at=started_at,
                ended_at=ended_at,
                steps=[TraceStep(step_index=0, type="llm_call", content=prompt)],
                final_output="",
                status="error",
                error=str(exc),
                error_type="infra",
                retrieval_fallback=retrieval_fallback,
                usage=None,
            )
            self.trace_store.save(trace)
            return trace

        ended_at = datetime.now(timezone.utc).isoformat()
        trace = ExecutionTrace(
            trace_id=trace_id,
            task_id=task_id,
            task_source=task.task_source,
            skill_id=skill.skill_id,
            skill_version=skill.version,
            started_at=started_at,
            ended_at=ended_at,
            steps=[
                TraceStep(step_index=0, type="llm_call", content=prompt),
                TraceStep(step_index=1, type="final", content=answer),
            ],
            final_output=answer,
            status="success",
            error="",
            error_type="",
            retrieval_fallback=retrieval_fallback,
            usage=usage,
        )
        self.trace_store.save(trace)
        return trace
