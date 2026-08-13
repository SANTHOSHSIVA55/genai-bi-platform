"""Tests for the AI-completion cache in ``ai.provider.chat``.

The cache turns repeated/re-tried NL->SQL prompts into instant responses (the
LLM round-trip is the slowest component of the pipeline). Guarantees:

- a successful completion for a given (system, user) prompt is served from cache;
- failures and empty responses are NEVER cached, so a transient error is retried.
"""
import pytest

import query_cache
from ai import provider


class _FakeResponse:
    def __init__(self, content):
        class _Choice:
            pass
        class _Message:
            pass
        choice = _Choice()
        msg = _Message()
        msg.content = content
        choice.message = msg
        self.choices = [choice]


class _FakeCompletions:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(1)
        if self._owner._raise is not None:
            exc = self._owner._raise
            self._owner._raise = None
            raise exc
        content = next(self._owner.contents, "SELECT 1")
        return _FakeResponse(content)


class _FakeChat:
    def __init__(self, owner):
        self.completions = _FakeCompletions(owner)


class _FakeClient:
    def __init__(self, contents=None):
        self.contents = iter(contents or [])
        self.calls = []
        self._raise = None
        self.chat = _FakeChat(self)


@pytest.fixture(autouse=True)
def _clean_ai_cache():
    with query_cache._ai_lock:
        query_cache._ai_store.clear()
    yield
    with query_cache._ai_lock:
        query_cache._ai_store.clear()


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(provider, "_client", client)
    return client


def test_successful_completion_is_cached(fake_client):
    result1 = provider.chat("system", "question")
    result2 = provider.chat("system", "question")
    assert result1 == result2 == "SELECT 1"
    assert len(fake_client.calls) == 1


def test_different_prompts_not_cached_together(fake_client):
    provider.chat("system", "question a")
    provider.chat("system", "question b")
    assert len(fake_client.calls) == 2


def test_ai_error_is_not_cached(fake_client):
    fake_client._raise = RuntimeError("timeout")
    result = provider.chat("system", "question")
    assert result.startswith("AI_ERROR")
    # Next attempt must hit the provider again, not the cache.
    provider.chat("system", "question")
    assert len(fake_client.calls) == 2


def test_empty_response_is_not_cached(fake_client):
    fake_client.contents = iter([""])
    assert provider.chat("system", "question") == ""
    provider.chat("system", "question")
    assert len(fake_client.calls) == 2
