# 活动事务（Active Transaction）

> 本文件标识当前开发周期，按 `workflow/state_protocol.md` 维护：事务初始化时写入条目，
> 随工作流推进更新当前阶段，事务关闭时标记为已关闭。

---

事务 ID：`0004`

目标：落地底座层最后一块 `llm.py`（OpenAI 兼容的 LLM 薄封装，窄接口单方法 `complete()`、可注入 mock client），并首次引入运行时第三方依赖 `openai`，配套 mock-first 单测。

状态：已关闭

当前阶段：已关闭

开始时间：2026-09-28

相关文件：
- `.agents/transactions/0004/context.md`
- `.agents/transactions/0004/plan.md`
- `.agents/transactions/0004/review.md`
- `.agents/transactions/0004/task.md`
- `.agents/transactions/0004/execution.md`
- `.agents/transactions/0004/result.md`

备注：本事务已实现并验证通过（全量 68 项测试 PASSED，含既有 63 项无回归），并按 §10 授权完成一次本地提交。按用户 5 条裁定落地：只走 OpenAI 兼容路径、`config.py` 加 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV`（key 仅环境变量）、窄接口单方法文本入出、mock-first 全单测不发真实请求、运行时新增 `openai` 一个第三方依赖。不含 `AgentExecutor`/`chat_json`/tool calling 及 anthropic/numpy。
