"""数据契约：全部 dataclass 数据结构 + 递归序列化辅助。

本模块定义系统设计 §5–§11 的 8 个 dataclass，是跨层传递的「合同」。
每个 dataclass 通过 `_Serializable` 基类获得 `to_dict()` / `from_dict()`
双向递归序列化能力（嵌套 dataclass 递归重建、`None` 与空集区分、
`bool | None` 三态精确保留）。
"""

from __future__ import annotations

import dataclasses
import types
import typing


# ── 递归序列化辅助 ──────────────────────────────────────────────────────


def _to_dict(obj):
    """把 dataclass / 嵌套 dataclass 递归转为 dict；其余值原样返回。"""
    if dataclasses.is_dataclass(obj):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    # dict / str / int / float / bool / None 均原样返回（dict 字段内容保持原样）
    return obj


def _coerce(value, field_type):
    """按字段类型把 `to_dict` 产出的内层值重建为对应 dataclass / 原类型。"""
    if value is None:
        return None

    origin = typing.get_origin(field_type)
    if origin is list:
        (elem_type,) = typing.get_args(field_type)
        if dataclasses.is_dataclass(elem_type):
            return [_from_dict(elem_type, item) for item in value]
        return list(value)

    if origin is typing.Union or origin is types.UnionType:
        # `bool | None` / `dict | None`：None 已在上面处理；取非 None 分支。
        args = typing.get_args(field_type)
        non_none = [a for a in args if a is not type(None)]
        if non_none and dataclasses.is_dataclass(non_none[0]):
            return _from_dict(non_none[0], value)
        return value

    if dataclasses.is_dataclass(field_type):
        return _from_dict(field_type, value)

    return value


def _from_dict(cls, d):
    """按 `cls` 的字段定义从 dict 重建实例（递归重建嵌套 dataclass）。"""
    if d is None:
        return None
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        kwargs[f.name] = _coerce(d[f.name], hints.get(f.name, f.type))
    return cls(**kwargs)


class _Serializable:
    """为所有 dataclass 提供 `to_dict` / `from_dict` 的公共基类。"""

    def to_dict(self) -> dict:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, d: dict):
        return _from_dict(cls, d)


# ── §5 Skill 数据结构 ───────────────────────────────────────────────────


@dataclasses.dataclass
class FewShot(_Serializable):
    input: str
    output: str


@dataclasses.dataclass
class ToolSpec(_Serializable):
    name: str
    description: str
    parameters: dict  # JSON Schema，描述入参


@dataclasses.dataclass
class Skill(_Serializable):
    skill_id: str           # 稳定标识，跨版本不变，如 "code-review"
    name: str
    description: str        # 语义描述，供检索用
    version: str            # "1.3.2"（见 §10）
    tags: list[str]         # ["code", "python"]
    prompt_template: str    # 系统提示词模板，含 {task} 等占位符
    few_shots: list[FewShot]
    tools: list[ToolSpec]
    status: str             # draft / candidate / active / deprecated
    parent_version: str     # 由哪个版本演化而来（溯源）
    change_log: str
    metrics: dict           # 仅 benchmark 得分快照
    created_at: str
    updated_at: str


# ── §6 Execution Trace 数据结构 ─────────────────────────────────────────


@dataclasses.dataclass
class TraceStep(_Serializable):
    step_index: int
    type: str               # "llm_call" | "tool_call" | "tool_result" | "final"
    content: str            # 消息 / 工具参数 / 观察结果
    tool_name: str = ""
    tokens: int = 0
    latency_ms: int = 0


@dataclasses.dataclass
class ExecutionTrace(_Serializable):
    trace_id: str
    task_id: str
    task_source: str        # "real" | "benchmark"
    skill_id: str
    skill_version: str
    started_at: str
    ended_at: str
    steps: list[TraceStep]
    final_output: str
    status: str             # success / error / timeout / max_steps
    error: str = ""
    error_type: str = ""    # "" | "infra" | "task"
    retrieval_fallback: bool = False
    usage: dict | None = None  # {total_tokens, total_cost, total_latency_ms}


# ── §7 EvaluationResult 数据结构 ────────────────────────────────────────


@dataclasses.dataclass
class EvaluationResult(_Serializable):
    eval_id: str
    trace_id: str
    eval_basis: str         # "objective" / "mixed" / "judge_rubric" / "judge_generic"
    passed: bool | None     # None = 不可判对错，不参与演化触发
    total_score: float      # 0~1
    objective: dict         # {status, matched, test_pass, ...}
    judge_score: float      # 0~1；跳过 judge 时记 0
    rubric_scores: dict     # {correctness: 0.8, ...}
    judge_reason: str
    evaluated_at: str


# ── §8 Experience 数据结构 ──────────────────────────────────────────────


@dataclasses.dataclass
class Experience(_Serializable):
    experience_id: str
    trace_id: str
    skill_id: str
    category: str           # missing_step / wrong_instruction / bad_example / ...
    summary: str
    target_section: str     # prompt_template / few_shots / tools
    suggestion: str
    confidence: float       # 0~1


# ── §11 BenchmarkTask 数据结构 ──────────────────────────────────────────
# 注意：`reference_answer` 为设计给出的唯一默认值字段；按 dataclass 语法
# 要求，有默认值的字段置于无默认值字段之后（字段名 / 类型与 §4.1 一致）。


@dataclasses.dataclass
class BenchmarkTask(_Serializable):
    task_id: str
    task: str               # 任务描述
    rubric: list[str]       # 评分维度
    objective_check: dict   # {"type": "exact"|"contains"|"test_script", "value": ...}
    tags: list[str]
    difficulty: str         # easy / medium / hard
    reference_answer: str = ""  # 参考答案（可选）
