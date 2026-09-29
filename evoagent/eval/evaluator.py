"""评估器：客观信号 + LLM-as-judge 融合 + passed 三态（§7）。

只调 `llm` / `eval_store` 两个模块。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime, timezone

from .. import config
from ..llm import LLMClient
from ..models import EvaluationResult, ExecutionTrace, Task
from .store import EvalStore

GENERIC_RUBRIC = ["correctness", "completeness", "format", "follow_skill"]  # §7 通用 rubric


def _judge_prompt(task_text: str, final_output: str, rubric_dims: list[str], reference_answer: str) -> str:
    dims = "、".join(rubric_dims)
    ref = f"\n参考答案：{reference_answer}" if reference_answer else ""
    return (
        f"任务：{task_text}\n"
        f"执行输出：{final_output}\n"
        f"评分维度：{dims}{ref}\n"
        f"请对每个维度打 0~5 分，并以 JSON 输出 {{'rubric_scores': {{维度: 分数}}, 'reason': '理由'}}。"
    )


def _run_test_script(script: str, output: str) -> tuple[bool, str]:
    """子进程隔离执行判题脚本：脚本从 stdin 读 `output`（final_output），exit 0 为通过。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            input=output,
            text=True,
            capture_output=True,
            timeout=config.TEST_SCRIPT_TIMEOUT_SEC,
        )
        return proc.returncode == 0, f"exit_code={proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:  # OSError 等一律捕获，绝不逃逸到 evaluate 外
        return False, str(exc)


class Evaluator:
    def __init__(self, llm: LLMClient, eval_store: EvalStore):
        self.llm = llm
        self.eval_store = eval_store

    def _judge(self, task_text, final_output, rubric_dims, reference_answer) -> tuple[float, dict, str]:
        data = self.llm.chat_json(_judge_prompt(task_text, final_output, rubric_dims, reference_answer))
        raw = data.get("rubric_scores") or {}
        numeric = {k: v for k, v in raw.items() if isinstance(v, (int, float))}
        judge_score = (sum(numeric.values()) / len(numeric)) / 5.0 if numeric else 0.0
        return judge_score, numeric, str(data.get("reason", ""))

    def evaluate(
        self,
        trace: ExecutionTrace,
        task: Task,
        *,
        reference_answer: str = "",
        rubric: list[str] | None = None,
        objective_check: dict | None = None,
    ) -> EvaluationResult:
        status = trace.status
        final_output = trace.final_output

        def _result(eval_basis, passed, total_score, objective, judge_score, rubric_scores, judge_reason):
            r = EvaluationResult(
                eval_id=uuid.uuid4().hex,
                trace_id=trace.trace_id,
                eval_basis=eval_basis,
                passed=passed,
                total_score=total_score,
                objective=objective,
                judge_score=judge_score,
                rubric_scores=rubric_scores,
                judge_reason=judge_reason,
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )
            self.eval_store.save_eval(r)
            return r

        # 分支 1：执行状态 error/timeout → 客观失败定论（跳过 judge）
        if status in ("error", "timeout"):
            return _result("objective", False, 0.0, {"status": status}, 0.0, {}, "")

        otype = objective_check.get("type") if objective_check else None
        if otype not in ("exact", "contains", "test_script"):
            otype = None  # 未知 type 视为「无客观」，走 judge 分支

        # 分支 2：exact → 客观定论（跳过 judge）
        if otype == "exact":
            matched = final_output == objective_check.get("value")
            return _result(
                "objective", matched, 1.0 if matched else 0.0,
                {"status": status, "type": "exact", "matched": matched}, 0.0, {}, "",
            )

        # 分支 2.5：test_script → 客观定论（跳过 judge），子进程执行
        if otype == "test_script":
            value = objective_check.get("value")
            if not (isinstance(value, str) and value.strip()):
                otype = None  # value 非字符串/空 → 视为「无客观」，走 judge 分支
            else:
                test_pass, _ = _run_test_script(value, final_output)
                return _result(
                    "objective", test_pass, 1.0 if test_pass else 0.0,
                    {"status": status, "type": "test_script", "test_pass": test_pass},
                    0.0, {}, "",
                )

        # 分支 3：contains 半信号 + rubric → mixed（0.7*obj + 0.3*judge）
        if otype == "contains" and rubric:
            matched = objective_check.get("value") in final_output
            obj_score = 1.0 if matched else 0.0
            judge_score, rubric_scores, reason = self._judge(task.task, final_output, rubric, reference_answer)
            total = config.OBJECTIVE_WEIGHT * obj_score + config.JUDGE_WEIGHT * judge_score
            return _result(
                "mixed", total >= config.PASS_THRESHOLD, total,
                {"status": status, "type": "contains", "matched": matched},
                judge_score, rubric_scores, reason,
            )

        # 分支 4：contains 半信号 + 无 rubric → 归入 judge_generic（passed=None）
        if otype == "contains" and not rubric:
            matched = objective_check.get("value") in final_output
            judge_score, rubric_scores, reason = self._judge(task.task, final_output, GENERIC_RUBRIC, reference_answer)
            return _result(
                "judge_generic", None, judge_score,
                {"status": status, "type": "contains", "matched": matched},
                judge_score, rubric_scores, reason,
            )

        # 分支 5：无客观 + rubric → judge_rubric
        if rubric:
            judge_score, rubric_scores, reason = self._judge(task.task, final_output, rubric, reference_answer)
            return _result(
                "judge_rubric", judge_score >= config.PASS_THRESHOLD, judge_score,
                {"status": status}, judge_score, rubric_scores, reason,
            )

        # 分支 6：无客观 + 无 rubric → judge_generic（passed=None）
        judge_score, rubric_scores, reason = self._judge(task.task, final_output, GENERIC_RUBRIC, reference_answer)
        return _result(
            "judge_generic", None, judge_score,
            {"status": status}, judge_score, rubric_scores, reason,
        )
