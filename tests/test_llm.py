"""LLMClient 测试：mock-first，全程不发真实请求。"""

import builtins
from types import SimpleNamespace

import openai
import pytest

from evoagent import config
from evoagent.llm import LLMClient


def _fake_client(response_text, usage=None):
    """构造一个记录调用参数的 OpenAI 兼容 fake client（可指定 resp.usage）。"""
    calls = []

    def create(model=None, messages=None, **kwargs):
        calls.append({"model": model, "messages": messages})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))],
            usage=usage,
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


def test_complete_with_usage_returns_three_keys():
    client, _ = _fake_client("hi", usage=SimpleNamespace(total_tokens=42))
    llm = LLMClient(client=client)
    content, usage = llm.complete_with_usage("hello")
    assert content == "hi"
    assert set(usage.keys()) == {"total_tokens", "total_cost", "total_latency_ms"}
    assert usage["total_tokens"] == 42
    assert usage["total_cost"] == 0.0
    assert isinstance(usage["total_latency_ms"], int)
    assert usage["total_latency_ms"] >= 0


def test_complete_with_usage_missing_usage_records_zero_tokens():
    client, _ = _fake_client("hi")  # usage=None
    llm = LLMClient(client=client)
    _, usage = llm.complete_with_usage("hello")
    assert usage["total_tokens"] == 0


def test_complete_matches_complete_with_usage_content():
    client, _ = _fake_client("hi", usage=SimpleNamespace(total_tokens=7))
    llm = LLMClient(client=client)
    assert isinstance(llm.complete("hello"), str)
    assert llm.complete("hello") == llm.complete_with_usage("hello")[0]
