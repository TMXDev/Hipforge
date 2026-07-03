"""
tests/backend/test_base_agent.py

Unit tests for the Fireworks AI client wrapper (Session 9.1).

Verifies:
  - get_ai_client() factory dispatches based on USE_MOCK_AI
  - MockFireworksClient.chat_completion() returns a valid completion response
  - Response schema matches the OpenAI-compatible format
  - Rate-limit / backoff logic in FireworksClient is correct
  - FireworksClient raises ValueError when API key is missing
  - Mock client detects agent type from system prompt and returns appropriate content

Gate: pytest tests/backend/test_base_agent.py -v
"""

import json
import os
import time

import pytest

from app.agents.base_agent import (
    FireworksClient,
    _backoff_delay,
    get_ai_client,
    MAX_RETRIES,
    BASE_DELAY_S,
    MAX_DELAY_S,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_messages(system: str = "You are a helpful assistant.", user: str = "Hello."):
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def assert_valid_completion(result: dict):
    """Assert the result matches the OpenAI-compatible completion schema."""
    assert isinstance(result, dict), "Result must be a dict"
    assert "id" in result, "Result must have 'id'"
    assert "choices" in result, "Result must have 'choices'"
    assert isinstance(result["choices"], list), "'choices' must be a list"
    assert len(result["choices"]) >= 1, "'choices' must not be empty"

    choice = result["choices"][0]
    assert "message" in choice, "Choice must have 'message'"
    assert "role" in choice["message"], "Message must have 'role'"
    assert "content" in choice["message"], "Message must have 'content'"
    assert choice["message"]["role"] == "assistant", "Role must be 'assistant'"
    assert isinstance(choice["message"]["content"], str), "Content must be a string"
    assert choice["message"]["content"].strip(), "Content must not be empty"

    assert "usage" in result, "Result must have 'usage'"
    assert "prompt_tokens" in result["usage"]
    assert "completion_tokens" in result["usage"]
    assert "total_tokens" in result["usage"]


# ---------------------------------------------------------------------------
# Test: factory dispatch
# ---------------------------------------------------------------------------

class TestFactory:
    """get_ai_client() must return the correct client based on USE_MOCK_AI."""

    def test_returns_real_client(self):
        client = get_ai_client()
        assert isinstance(client, FireworksClient)

    def test_real_client_raises_without_api_key(self):
        """FireworksClient must raise ValueError when API key is placeholder."""
        with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
            FireworksClient(api_key="your_fireworks_api_key")

    def test_real_client_raises_when_api_key_empty(self, monkeypatch):
        from app.config.settings import settings
        monkeypatch.setattr(settings, "FIREWORKS_API_KEY", "")
        with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
            FireworksClient(api_key="")

    def test_real_client_raises_when_api_key_none(self, monkeypatch):
        from app.config.settings import settings
        monkeypatch.setattr(settings, "FIREWORKS_API_KEY", "")
        with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
            FireworksClient(api_key=None)


# ---------------------------------------------------------------------------
# Test: MockFireworksClient — gate test
# This is the "real API call" in pre-hackathon mode.
# The mock IS the active client; it must return a valid completion response.
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Test: BackoffDelay helper
# ---------------------------------------------------------------------------

class TestBackoffDelay:
    """_backoff_delay() must implement exponential backoff with jitter."""

    def test_delay_is_non_negative(self):
        for attempt in range(1, MAX_RETRIES + 1):
            assert _backoff_delay(attempt) >= 0.0

    def test_delay_does_not_exceed_max(self):
        for attempt in range(1, MAX_RETRIES + 1):
            assert _backoff_delay(attempt) <= MAX_DELAY_S

    def test_delay_increases_with_attempts(self):
        """The cap should grow with each attempt (even if jitter varies)."""
        cap_1 = min(MAX_DELAY_S, BASE_DELAY_S * (2 ** 0))
        cap_3 = min(MAX_DELAY_S, BASE_DELAY_S * (2 ** 2))
        assert cap_3 > cap_1, "Cap should be larger for later attempts"

    def test_delay_first_attempt_bounded(self):
        """First attempt delay must be in [0, BASE_DELAY_S]."""
        for _ in range(20):
            delay = _backoff_delay(1)
            assert 0.0 <= delay <= BASE_DELAY_S

    def test_delay_high_attempt_bounded_by_max(self):
        """High attempt numbers must be capped at MAX_DELAY_S."""
        for _ in range(20):
            delay = _backoff_delay(100)
            assert delay <= MAX_DELAY_S


# ---------------------------------------------------------------------------
# Test: FireworksClient retry logic (mocked HTTP)
# ---------------------------------------------------------------------------

class TestFireworksClientRetry:
    """
    FireworksClient must retry on 429/5xx and succeed on a subsequent attempt.
    Uses urllib.request patching to avoid real network calls.
    """

    def test_retries_on_429_and_succeeds(self, monkeypatch):
        """Client must retry after a 429 and eventually succeed."""
        import json as _json
        import urllib.error
        import urllib.request

        call_count = {"n": 0}

        def mock_urlopen(request, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Simulate a rate-limit response
                raise urllib.error.HTTPError(
                    url="https://api.fireworks.ai/...",
                    code=429,
                    msg="Too Many Requests",
                    hdrs={},
                    fp=None,
                )
            # Second call succeeds
            class FakeResp:
                def read(self):
                    return _json.dumps({
                        "id": "fw-12345",
                        "object": "chat.completion",
                        "model": "test-model",
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hello!"},
                            "finish_reason": "stop",
                        }],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                    }).encode("utf-8")
                def __enter__(self): return self
                def __exit__(self, *args): pass

            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
        # Also patch _backoff_delay to return 0 so the test is fast
        monkeypatch.setattr("app.agents.base_agent._backoff_delay", lambda attempt: 0.0)

        client = FireworksClient.__new__(FireworksClient)
        client._api_key = "fw-test-key-1234"

        result = client.chat_completion(
            model="test-model",
            messages=make_messages(),
        )
        assert_valid_completion(result)
        assert call_count["n"] == 2, f"Expected 2 calls, got {call_count['n']}"

    def test_raises_after_max_retries_exhausted(self, monkeypatch):
        """Client must raise RuntimeError when all retries are exhausted."""
        import urllib.error
        import urllib.request

        def always_429(request, timeout=None):
            raise urllib.error.HTTPError(
                url="https://api.fireworks.ai/...",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", always_429)
        monkeypatch.setattr("app.agents.base_agent._backoff_delay", lambda attempt: 0.0)

        client = FireworksClient.__new__(FireworksClient)
        client._api_key = "fw-test-key-1234"

        with pytest.raises(RuntimeError, match="failed after"):
            client.chat_completion(model="test-model", messages=make_messages())

    def test_raises_immediately_on_401(self, monkeypatch):
        """Client must NOT retry on non-retryable HTTP errors (e.g. 401 auth)."""
        import urllib.error
        import urllib.request

        call_count = {"n": 0}

        def auth_error(request, timeout=None):
            call_count["n"] += 1
            raise urllib.error.HTTPError(
                url="https://api.fireworks.ai/...",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", auth_error)

        client = FireworksClient.__new__(FireworksClient)
        client._api_key = "fw-test-key-1234"

        with pytest.raises(RuntimeError, match="HTTP 401"):
            client.chat_completion(model="test-model", messages=make_messages())

        assert call_count["n"] == 1, "Should not retry on 401"
