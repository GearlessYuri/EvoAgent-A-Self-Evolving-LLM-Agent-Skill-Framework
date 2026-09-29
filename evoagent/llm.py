"""LLM 薄封装（OpenAI 兼容路径）。窄接口：单方法 `complete()` 文本入出。

只依赖 `config`；不实现 anthropic、多 provider 适配层、tool calling。
`openai` 仅在构建真实 client 时惰性 import，注入路径完全不触碰 openai 模块。
"""

import json
import os
import time

from . import config


def _parse_json_object(text: str) -> dict:
    """把 LLM 输出解析为 dict：先整体 `json.loads`，失败则提取首个平衡 `{...}` 再解析，仍失败抛 ValueError。"""
    def _try(s: str):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    obj = _try(text)
    if obj is not None:
        return obj

    start = text.find("{")
    if start == -1:
        raise ValueError(f"LLM 输出无法解析为 JSON 对象: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                obj = _try(text[start : i + 1])
                if obj is not None:
                    return obj
                break
    raise ValueError(f"LLM 输出无法解析为 JSON 对象: {text[:200]!r}")


class LLMClient:
    """OpenAI 兼容 LLM 客户端。`client` 可注入（测试注入 fake，不 import openai）。"""

    def __init__(self, client=None):
        self._client = client  # None = 惰性构建真实 client

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = os.environ.get(config.LLM_API_KEY_ENV)
        if not api_key:
            raise ValueError(
                f"环境变量 {config.LLM_API_KEY_ENV} 未设置，无法初始化 LLM client"
            )
        import openai  # 惰性 import：仅在构建真实 client 时
        self._client = openai.OpenAI(base_url=config.LLM_BASE_URL, api_key=api_key)
        return self._client

    def complete_with_usage(self, prompt: str) -> tuple[str, dict]:
        """返回 (content, usage)。usage 为 §6 三键：total_tokens / total_cost / total_latency_ms。"""
        start = time.monotonic()
        resp = self._get_client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        content = resp.choices[0].message.content
        content = content if content is not None else ""

        usage = getattr(resp, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) if usage is not None else 0

        return content, {
            "total_tokens": total_tokens,
            "total_cost": 0.0,          # 定价未实现，占位（见 §11.10）
            "total_latency_ms": latency_ms,
        }

    def complete(self, prompt: str) -> str:
        content, _ = self.complete_with_usage(prompt)
        return content

    def chat_json(self, prompt: str) -> dict:
        """judge 用：取文本 → 解析为 dict（§7 解析兜底）。"""
        text = self.complete(prompt + "\n\n请只输出一个 JSON 对象，不要输出任何其它内容。")
        return _parse_json_object(text)
