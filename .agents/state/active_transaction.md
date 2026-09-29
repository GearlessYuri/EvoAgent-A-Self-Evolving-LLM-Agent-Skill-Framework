# 活动事务（Active Transaction）

> 本文件标识当前开发周期，按 `workflow/state_protocol.md` 维护：事务初始化时写入条目，
> 随工作流推进更新当前阶段，事务关闭时标记为已关闭。

---

事务 ID：`0006`

目标：落地评估层核心 `Evaluator`（客观信号 + LLM-as-judge + 融合 + passed 三态）与 `ExperienceExtractor`（经验提炼），并给 `LLMClient` 新增 `chat_json()` judge 扩展；`Benchmark` 顺延至 `0007`。

状态：已关闭

当前阶段：已关闭

开始时间：2026-09-29

相关文件：
- `.agents/transactions/0006/context.md`
- `.agents/transactions/0006/plan.md`
- `.agents/transactions/0006/review.md`
- `.agents/transactions/0006/task.md`
- `.agents/transactions/0006/execution.md`
- `.agents/transactions/0006/result.md`

备注：本事务已实现并验证通过（全量 92 项测试 PASSED，含既有 75 项无回归），并按 §10 授权完成一次本地提交。承接已关闭的 `0001`–`0005`，复用 `0004` 预留的 `chat_json` 扩展点，闭合 §7 的「客观可判跳过 judge / 无客观且无 rubric 不判 pass（三态）」信号边界；不含 `Benchmark`/演化层/`test_script` 客观类型及任何真实 LLM 请求。
