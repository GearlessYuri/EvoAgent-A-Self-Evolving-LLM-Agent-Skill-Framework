# Planner 提示词模板

> 用法：替换 `{TRANSACTION_ID}`、`{上一事务ID}`、`{DESIGN_DOCS}`（无则删除该行），
> 并在「特别关注」处按本事务实际主题增删 1–3 条针对性核对点。
> 产物流向见 `../transaction_protocol.md`。

```text
你现在作为 Planner（规划者），启动开发事务 {TRANSACTION_ID}。

首先阅读：
- .agents/roles/planner.md（你的角色定义与输出要求）
- .agents/workflow/protocol.md
- .agents/workflow/state_protocol.md
- .agents/workflow/transaction_protocol.md
- .agents/state/project_state.md
- .agents/transactions/{上一事务ID}/result.md（上一事务的结果、已知局限与后续建议）
- .agents/transactions/{上一事务ID}/execution.md（需要了解实现细节时）
- {DESIGN_DOCS}（系统设计全文）

然后检查当前代码仓库的实际状态（以实际代码为准，不要凭设计文档
想象已存在的实现）。

在此基础上：
- 识别当前最重要的未解决问题（可参考 {上一事务ID} result.md 的
  「后续问题」与「建议的下一步」等候选方向）
- 选定一个聚焦的工程目标（一个事务只做一个连贯目标）
- 产出具体的实施计划并定义验收标准

完成两个产物：
1. 新建 transactions/{TRANSACTION_ID}/context.md —— 时间胶囊：触发原因、
   事务开始时的项目状态快照、经核实的实际仓库现状、本事务依赖的
   系统设计章节
2. 新建 transactions/{TRANSACTION_ID}/plan.md —— 完整计划，含 planner.md
   要求的全部 10 个小节（当前状态/问题/目标/范围/拟议变更/依赖/风险/
   实施顺序/验收标准/验证策略）

同时更新状态文件（保持一致）：
- .agents/state/active_transaction.md —— 用 {TRANSACTION_ID} 的新条目替换
  已关闭的 {上一事务ID} 条目：事务 ID、目标、状态「进行中」、当前阶段
  「规划完成，待评审」、开始时间、相关文件、备注
- .agents/state/project_state.md —— 「当前事务」与「当前开发阶段」
  指向 {TRANSACTION_ID}

约束：
- 不要修改任何源代码或测试
- 不要修改 docs/system_design.md（若本事务需要回补设计，将其作为
  plan.md 的「拟议变更」提出，由后续流程批准，而不是现在直接改）
- 不要做任何 git 操作（收尾提交属于 Coder，由 task.md 批准）
- 不得生成多个互不相关的任务，不得在没有充分理由的情况下引入复杂度

本事务特别关注（按需增删）：
- （示例）若计划触及设计文档未定义的概念，明确标注哪些是从设计文档
  推导、哪些是自行提出，勿当作既成设计
```
