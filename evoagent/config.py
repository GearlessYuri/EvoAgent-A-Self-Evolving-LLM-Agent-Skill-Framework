"""集中配置：路径常量、纯数值阈值 / 权重与 OpenAI 兼容路径的 LLM 常量。

纯数值阈值 / 权重与路径已由系统设计钉死。LLM 常量（`LLM_BASE_URL` /
`LLM_MODEL` / `LLM_API_KEY_ENV`）提供 OpenAI 兼容 provider 的可覆盖默认值；
API key 仅通过环境变量在运行时读取、绝不以明文进入仓库。
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

# ── LLM（事务 0004 引入，OpenAI 兼容路径） ────────────────────────────────
LLM_BASE_URL = "https://api.deepseek.com"   # OpenAI 兼容 provider base_url（可覆盖）
LLM_MODEL = "deepseek-chat"                 # 默认模型
LLM_API_KEY_ENV = "DEEPSEEK_API_KEY"        # 环境变量名；key 值绝不进仓库，仅运行时读取

# ── Benchmark / test_script（事务 0007 追加） ──────────────────────────────
BENCHMARKS_DIR = "data/benchmarks"   # §13 benchmark 任务集目录（regression.json / extension.json）
TEST_SCRIPT_TIMEOUT_SEC = 5          # §7 test_script 客观判题子进程超时（秒）
