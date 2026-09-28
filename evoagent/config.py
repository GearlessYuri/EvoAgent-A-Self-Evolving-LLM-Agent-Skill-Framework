"""集中配置：路径常量与纯数值阈值 / 权重。

本模块只承载已由系统设计钉死的纯数值常量与路径，不含任何 LLM provider /
model / API key 等参数（这些随 `llm.py` / evaluator 事务引入）。
"""

# ── 路径 ────────────────────────────────────────────────────────────────
DATA_DIR = "data"
DB_PATH = "data/evoagent.db"

# ── 阈值 / 权重（纯数值，非 LLM 参数） ───────────────────────────────────
RETRIEVAL_FALLBACK_THRESHOLD = 0.3  # §3.2 检索兜底阈值
OBJECTIVE_WEIGHT = 0.7              # §7 评估融合权重（客观信号）
JUDGE_WEIGHT = 0.3                  # §7 评估融合权重（LLM-as-judge）
PASS_THRESHOLD = 0.6                # §7 `passed` 判定阈值

# ── WAL 开关 ───────────────────────────────────────────────────────────
SQLITE_WAL_ENABLED = True           # §12/§14 单进程单写者，SQLite 开 WAL

# ── 存储门面（事务 0002 追加） ───────────────────────────────────────────
SKILLS_DIR = "data/skills"        # §5/§13 Skill 内容 JSON 归档根目录
TRACE_CONTENT_MAX_CHARS = 4000    # §6 trace_steps.content 截断阈值
