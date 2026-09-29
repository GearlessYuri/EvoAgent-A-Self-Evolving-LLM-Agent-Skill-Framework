# 活动事务（Active Transaction）

> 本文件标识当前开发周期，按 `workflow/state_protocol.md` 维护：事务初始化时写入条目，
> 随工作流推进更新当前阶段，事务关闭时标记为已关闭。

---

事务 ID：`0008`

目标：落地演化层核心 `SkillEvolver`（Experience[] → 候选新版本）+ `Validator`（Benchmark A/B → win_rate 判定 → promote），A/B 阈值（0.5 平局 / 0.55 win_rate / 20 题下限）严格对齐设计 §9/§11，promote 走 `SkillRegistry` 既有状态机。

状态：已关闭

当前阶段：已关闭

开始时间：2026-09-29

相关文件：
- `.agents/transactions/0008/context.md`
- `.agents/transactions/0008/plan.md`
- `.agents/transactions/0008/review.md`
- `.agents/transactions/0008/task.md`
- `.agents/transactions/0008/execution.md`
- `.agents/transactions/0008/result.md`

备注：本事务已实现并验证通过（全量 115 项测试 PASSED，含既有 104 项无回归），并按 §10 授权完成一次本地提交。承接已关闭的 `0001`–`0007`，串起「经验 → 候选 → 验证 → promote」逆向流闭环；候选为 draft 新版本（不绕过 active 指针/不可变历史）、Evolver 侧防污染（参考答案结构不可达）；不含 `EvolutionLoop`/`cli.py`/`tools.py`/真实 LLM 请求。
