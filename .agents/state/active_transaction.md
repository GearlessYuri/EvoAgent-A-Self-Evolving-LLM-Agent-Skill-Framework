# 活动事务（Active Transaction）

> 本文件标识当前开发周期，按 `workflow/state_protocol.md` 维护：事务初始化时写入条目，
> 随工作流推进更新当前阶段，事务关闭时标记为已关闭。

---

事务 ID：`0009`（项目收官事务）

目标：收官——落地 `EvolutionLoop`（主循环编排）与 `cli.py`（run/evolve/bench/list），修复打包（子包纳入 `pip install .`），回补 `docs/system_design.md` 的 `Task` 定义（仅此一处），补 `README.md`，把项目补成可交付成品。

状态：已关闭

当前阶段：已关闭

开始时间：2026-09-29

相关文件：
- `.agents/transactions/0009/context.md`
- `.agents/transactions/0009/plan.md`
- `.agents/transactions/0009/review.md`
- `.agents/transactions/0009/task.md`
- `.agents/transactions/0009/execution.md`
- `.agents/transactions/0009/result.md`

备注：本事务已实现并验证通过（全量 126 项测试 PASSED，含既有 115 项无回归；打包验证 `pip install .` 后四子包 import 成功），并按 §10 授权完成一次本地提交。承接已关闭的 `0001`–`0008`，把「可用闭环」补成「可交付成品」；Loop 只编排不重实现、只挖 `task_source=="real"` 低分 trace（防污染）、失败不阻塞；不含 `tools.py`/真实 LLM 请求/新第三方依赖。
