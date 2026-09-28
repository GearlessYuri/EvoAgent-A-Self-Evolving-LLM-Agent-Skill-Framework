"""Trace 存储门面：ExecutionTrace 写入 / 查询 + 4000 字符截断（§3.2）。

只经 `Storage` 的通用 CRUD 持久化，不直接操作 SQLite、不访问 `storage.conn`。
`truncated` 是仅存于持久化层（`trace_steps.truncated` 列）的标志，不进入
`TraceStep` 数据契约，`get()` 不返回它；截断在写入侧完成。
"""

from __future__ import annotations

import json

from .. import config
from ..models import ExecutionTrace
from ..storage import Storage


class TraceStore:
    """ExecutionTrace 写入 / 查询（按 skill / 状态 / 时间过滤）。"""

    def __init__(self, storage: Storage):
        self.storage = storage

    def save(self, trace: ExecutionTrace) -> None:
        """写 `traces` 1 行 + `trace_steps` N 行；重复 `trace_id` 由底层上抛 IntegrityError。

        每个 step 的 `content` 超过 `config.TRACE_CONTENT_MAX_CHARS` 时截断并置
        `truncated=1`，否则原样存储 `truncated=0`。
        """
        self.storage.insert(
            "traces",
            {
                "trace_id": trace.trace_id,
                "task_id": trace.task_id,
                "task_source": trace.task_source,
                "skill_id": trace.skill_id,
                "skill_version": trace.skill_version,
                "started_at": trace.started_at,
                "ended_at": trace.ended_at,
                "final_output": trace.final_output,
                "status": trace.status,
                "error": trace.error,
                "error_type": trace.error_type,
                "retrieval_fallback": trace.retrieval_fallback,
                "usage": trace.usage,  # dict | None，由 Storage 自动 json.dumps
            },
        )

        for step in trace.steps:
            content = step.content
            truncated = 0
            if len(content) > config.TRACE_CONTENT_MAX_CHARS:
                content = content[: config.TRACE_CONTENT_MAX_CHARS]
                truncated = 1
            self.storage.insert(
                "trace_steps",
                {
                    "trace_id": trace.trace_id,
                    "step_index": step.step_index,
                    "type": step.type,
                    "content": content,
                    "tool_name": step.tool_name,
                    "tokens": step.tokens,
                    "latency_ms": step.latency_ms,
                    "truncated": truncated,
                },
            )

    def get(self, trace_id: str) -> ExecutionTrace | None:
        """合并 `traces` + `trace_steps`（按 `step_index` 升序）重建；不存在 → `None`。"""
        rows = self.storage.query("traces", where="trace_id = ?", params=(trace_id,))
        if not rows:
            return None
        row = rows[0]

        step_rows = self.storage.query(
            "trace_steps", where="trace_id = ?", params=(trace_id,), order_by="step_index"
        )
        steps = [
            {
                "step_index": s["step_index"],
                "type": s["type"],
                "content": s["content"],
                "tool_name": s["tool_name"],
                "tokens": s["tokens"],
                "latency_ms": s["latency_ms"],
            }
            for s in step_rows
        ]

        return ExecutionTrace.from_dict(
            {
                "trace_id": row["trace_id"],
                "task_id": row["task_id"],
                "task_source": row["task_source"],
                "skill_id": row["skill_id"],
                "skill_version": row["skill_version"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "steps": steps,
                "final_output": row["final_output"],
                "status": row["status"],
                "error": row["error"],
                "error_type": row["error_type"],
                "retrieval_fallback": bool(row["retrieval_fallback"]),
                "usage": json.loads(row["usage"]) if row["usage"] is not None else None,
            }
        )

    def list(
        self,
        skill_id: str | None = None,
        status: str | None = None,
        since: str | None = None,
    ) -> list[ExecutionTrace]:
        """过滤查询，返回摘要（不含 steps，`steps=[]`），按 `started_at` 升序。

        `since` 按 `started_at >= since` 过滤（用 `started_at`，不用 `ended_at`）。
        """
        where_parts = []
        params: list = []
        if skill_id is not None:
            where_parts.append("skill_id = ?")
            params.append(skill_id)
        if status is not None:
            where_parts.append("status = ?")
            params.append(status)
        if since is not None:
            where_parts.append("started_at >= ?")
            params.append(since)

        where = " AND ".join(where_parts) if where_parts else ""
        rows = self.storage.query("traces", where=where, params=tuple(params), order_by="started_at")

        return [
            ExecutionTrace(
                trace_id=row["trace_id"],
                task_id=row["task_id"],
                task_source=row["task_source"],
                skill_id=row["skill_id"],
                skill_version=row["skill_version"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                steps=[],  # 摘要：不加载 steps
                final_output=row["final_output"],
                status=row["status"],
                error=row["error"],
                error_type=row["error_type"],
                retrieval_fallback=bool(row["retrieval_fallback"]),
                usage=json.loads(row["usage"]) if row["usage"] is not None else None,
            )
            for row in rows
        ]
