"""LLMClient 测试：mock-first，全程不发真实请求。"""

import builtins
from types import SimpleNamespace

import openai
import pytest

from evoagent import config
from evoagent.llm import LLMClient


def _fake_client(response_text):
    """构造一个记录调用参数的 OpenAI 兼容 fake client。"""
    calls = []

    def create(model=None, messages=None, **kwargs):
        calls.append({"model": model, "messages": messages})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return client, calls


def test_complete_uses_injected_fake():
    client, calls = _fake_client("hello world")
    llm = LLMClient(client=client)
    assert llm.complete("hello") == "hello world"
    assert calls[0]["model"] == config.LLM_MODEL
    assert calls[0]["messages"] == [{"role": "user", "content": "hello"}]


def test_complete_content_none_returns_empty_string():
    client, _ = _fake_client(None)
    llm = LLMClient(client=client)
    assert llm.complete("hi") == ""


def test_complete_missing_key_raises(monkeypatch):
    monkeypatch.delenv(config.LLM_API_KEY_ENV, raising=False)
    with pytest.raises(ValueError):
        LLMClient().complete("x")


def test_lazy_build_real_client(monkeypatch):
    monkeypatch.setenv(config.LLM_API_KEY_ENV, "test-key")
    received = {}

    def fake_factory(**kwargs):
        received.update(kwargs)
        client, _ = _fake_client("hi")
        return client

    monkeypatch.setattr(openai, "OpenAI", fake_factory)
    assert LLMClient().complete("hi") == "hi"
    assert received["base_url"] == config.LLM_BASE_URL
    assert received["api_key"] == "test-key"


def test_injection_does_not_import_openai(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai":
            raise AssertionError("注入路径不应 import openai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    client, _ = _fake_client("hi")
    assert LLMClient(client=client).complete("hi") == "hi"
