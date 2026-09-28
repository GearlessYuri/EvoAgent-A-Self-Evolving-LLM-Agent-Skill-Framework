"""LLM 薄封装（OpenAI 兼容路径）。窄接口：单方法 `complete()` 文本入出。

只依赖 `config`；不实现 anthropic、多 provider 适配层、chat_json、tool calling。
`openai` 仅在构建真实 client 时惰性 import，注入路径完全不触碰 openai 模块。
"""

import os

from . import config


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

    def complete(self, prompt: str) -> str:
        resp = self._get_client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content
        return content if content is not None else ""
