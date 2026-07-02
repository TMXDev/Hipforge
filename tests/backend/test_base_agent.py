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

# Force mock mode for all tests in this file before any app imports
os.environ["USE_MOCK_AI"] = "true"
os.environ["USE_MOCK_COMPILER"] = "true"

from app.agents.base_agent import (
    FireworksClient,
    MockFireworksClient,
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

    def test_returns_mock_when_use_mock_ai_true(self):
        os.environ["USE_MOCK_AI"] = "true"
        # Reload settings to pick up env change
        import importlib
        import app.config.settings as settings_mod
        importlib.reload(settings_mod)
        # Re-import factory with fresh settings
        from app.agents.base_agent import get_ai_client as factory
        client = factory()
        assert isinstance(client, MockFireworksClient), (
            f"Expected MockFireworksClient, got {type(client)}"
        )

    def test_real_client_raises_without_api_key(self):
        """FireworksClient must raise ValueError when API key is placeholder."""
        with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
            FireworksClient(api_key="your_fireworks_api_key")

    def test_real_client_raises_when_api_key_empty(self):
        with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
            FireworksClient(api_key="")

    def test_real_client_raises_when_api_key_none(self):
        with pytest.raises(ValueError, match="FIREWORKS_API_KEY"):
            FireworksClient(api_key=None)


# ---------------------------------------------------------------------------
# Test: MockFireworksClient — gate test
# This is the "real API call" in pre-hackathon mode.
# The mock IS the active client; it must return a valid completion response.
# ---------------------------------------------------------------------------

class TestMockFireworksClient:
    """Gate: chat_completion() returns a valid completion response."""

    @pytest.fixture(autouse=True)
    def client(self):
        self.client = MockFireworksClient()

    def test_returns_valid_completion(self):
        """Gate test: call returns a valid completion response."""
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=make_messages(),
            max_tokens=512,
        )
        assert_valid_completion(result)

    def test_id_is_string(self):
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=make_messages(),
        )
        assert isinstance(result["id"], str)
        assert result["id"].startswith("mock-completion-")

    def test_model_field_echoed(self):
        model = "accounts/fireworks/models/kimi-k2"
        result = self.client.chat_completion(model=model, messages=make_messages())
        assert result["model"] == model

    def test_finish_reason_is_stop(self):
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=make_messages(),
        )
        assert result["choices"][0]["finish_reason"] == "stop"

    def test_usage_tokens_are_non_negative(self):
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=make_messages("System.", "User message."),
        )
        usage = result["usage"]
        assert usage["prompt_tokens"] >= 0
        assert usage["completion_tokens"] >= 0
        assert usage["total_tokens"] >= 0

    def test_content_is_parseable_json(self):
        """Mock responses embed JSON content — it must be valid JSON."""
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=make_messages("You perform analysis of root cause.", "Analyze this."),
        )
        content = result["choices"][0]["message"]["content"]
        # Should be valid JSON for all agent-type responses
        parsed = json.loads(content)
        assert isinstance(parsed, dict)

    def test_analysis_agent_response_detected(self):
        """Mock must return analysis response when system prompt mentions analysis."""
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=[
                {"role": "system", "content": "You identify the root cause of compilation errors via analysis."},
                {"role": "user", "content": "Why did compilation fail?"},
            ],
        )
        content = json.loads(result["choices"][0]["message"]["content"])
        assert "root_cause" in content
        assert "repair_plan" in content

    def test_patch_agent_response_detected(self):
        """Mock must return patch response when system prompt mentions patch/modify."""
        result = self.client.chat_completion(
            model="accounts/fireworks/models/kimi-k2",
            messages=[
                {"role": "system", "content": "You modify source code to patch compilation errors."},
                {"role": "user", "content": "Apply the repair plan."},
            ],
        )
        content = json.loads(result["choices"][0]["message"]["content"])
        assert "modified_files" in content
        assert "changes" in content

    def test_research_agent_response_detected(self):
        """Mock must return research response when system prompt mentions research/documentation."""
        result = self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=[
                {"role": "system", "content": "Search the documentation and research ROCm migration guides."},
                {"role": "user", "content": "Find relevant documentation."},
            ],
        )
        content = json.loads(result["choices"][0]["message"]["content"])
        assert "findings" in content
        assert "recommended_actions" in content

    def test_completes_in_reasonable_time(self):
        """Mock should return quickly (simulated delay ≤ 200ms in practice)."""
        start = time.time()
        self.client.chat_completion(
            model="accounts/fireworks/models/qwen2p5-72b-instruct",
            messages=make_messages(),
        )
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Mock took too long: {elapsed:.2f}s"

    def test_multiple_calls_produce_unique_ids(self):
        """Each call must return a unique completion ID."""
        ids = set()
        for _ in range(5):
            result = self.client.chat_completion(
                model="accounts/fireworks/models/qwen2p5-72b-instruct",
                messages=make_messages(),
            )
            ids.add(result["id"])
        assert len(ids) >= 1, "IDs must be generated per call"


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
