"""
backend/app/agents/base_agent.py

Fireworks AI Client Wrapper — Session 9.1

Implements the Fireworks AI client used by all HIPForge AI agents.
Provides:
  - FireworksClient  — real HTTP client authenticating with FIREWORKS_API_KEY
  - MockFireworksClient — deterministic mock for pre-hackathon development
  - get_ai_client()  — factory function (always use this; never instantiate directly)

Authentication:
  Fireworks AI uses Bearer token authentication.
  The API key is read from the FIREWORKS_API_KEY environment variable.
  See: docs/04_TECHNOLOGY_DECISIONS.md

Retry / backoff:
  Per docs/09_AI_AGENTS.md, rate limit errors (HTTP 429) and transient
  server errors (HTTP 5xx) must be retried with exponential backoff.
  The client performs up to MAX_RETRIES attempts with base delay BASE_DELAY_S,
  doubling each time with full jitter to avoid thundering herd.

Interface contract (must be identical on both real and mock clients):
  chat_completion(
      model: str,
      messages: list[dict],
      max_tokens: int,
  ) -> dict

  Returns a dict matching the OpenAI-compatible Fireworks AI completion response:
  {
      "id": str,
      "choices": [
          {
              "message": {
                  "role": "assistant",
                  "content": str
              },
              "finish_reason": str
          }
      ],
      "usage": {
          "prompt_tokens": int,
          "completion_tokens": int,
          "total_tokens": int
      }
  }
"""

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List

logger = logging.getLogger("base_agent")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fireworks AI API base URL (OpenAI-compatible)
FIREWORKS_API_BASE = "https://api.fireworks.ai/inference/v1"

# Retry configuration for rate-limit / transient server errors
MAX_RETRIES: int = 5
BASE_DELAY_S: float = 1.0   # first back-off delay in seconds
MAX_DELAY_S: float = 60.0   # cap on any single back-off delay

# HTTP status codes that warrant a retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Real Fireworks AI Client
# ---------------------------------------------------------------------------

class FireworksClient:
    """
    Production client for the Fireworks AI chat completions API.

    Authentication:
        Bearer token from FIREWORKS_API_KEY environment variable.

    Retry behaviour:
        HTTP 429 (rate limit) and 5xx (transient server errors) trigger
        exponential back-off with full jitter up to MAX_RETRIES attempts.

    Raises:
        ValueError: if FIREWORKS_API_KEY is not set or is the placeholder value.
        RuntimeError: if all retry attempts are exhausted without a 200 response.
    """

    def __init__(self, api_key: str | None = None):
        from app.config.settings import settings

        self._api_key = api_key or settings.FIREWORKS_API_KEY

        if not self._api_key or self._api_key == "your_fireworks_api_key":
            raise ValueError(
                "FIREWORKS_API_KEY is not set. "
                "Add it to .env or set USE_MOCK_AI=true for pre-hackathon mode."
            )

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Call the Fireworks AI chat completions endpoint synchronously.

        Args:
            model:      Fireworks model ID (e.g. "accounts/fireworks/models/qwen2p5-72b-instruct")
            messages:   List of {role, content} dicts following the OpenAI format.
            max_tokens: Maximum tokens in the completion response.

        Returns:
            Dict matching the OpenAI-compatible completion response schema.

        Raises:
            RuntimeError: when all retries are exhausted.
        """
        import json
        import urllib.error
        import urllib.request

        url = f"{FIREWORKS_API_BASE}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                request = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(request, timeout=60) as resp:
                    body = resp.read().decode("utf-8")
                    result = json.loads(body)
                    logger.debug(
                        "[FireworksClient] chat_completion succeeded on attempt %d. "
                        "Model: %s, usage: %s",
                        attempt, model, result.get("usage"),
                    )
                    return result

            except urllib.error.HTTPError as e:
                status = e.code
                if status in _RETRYABLE_STATUS_CODES:
                    delay = _backoff_delay(attempt)
                    logger.warning(
                        "[FireworksClient] HTTP %d on attempt %d/%d. "
                        "Retrying in %.1fs...",
                        status, attempt, MAX_RETRIES, delay,
                    )
                    last_error = e
                    time.sleep(delay)
                    continue
                else:
                    # Non-retryable HTTP error (e.g. 400 bad request, 401 auth)
                    body = e.read().decode("utf-8") if e.fp else ""
                    raise RuntimeError(
                        f"Fireworks AI returned HTTP {status}: {body}"
                    ) from e

            except Exception as e:
                # Network-level errors (connection refused, timeout, etc.)
                delay = _backoff_delay(attempt)
                logger.warning(
                    "[FireworksClient] Network error on attempt %d/%d: %s. "
                    "Retrying in %.1fs...",
                    attempt, MAX_RETRIES, e, delay,
                )
                last_error = e
                time.sleep(delay)

        raise RuntimeError(
            f"Fireworks AI request failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )


# ---------------------------------------------------------------------------
# Mock Fireworks AI Client  (pre-hackathon)
# ---------------------------------------------------------------------------

# Deterministic mock responses keyed by the first word of the last user message.
# Agents detect their type by the content of the messages they send.

_MOCK_ANALYSIS_RESPONSE = {
    "summary": "Compilation failed due to unsupported CUDA memory copy API.",
    "root_cause": (
        "cudaMemcpyAsync is not fully equivalent to hipMemcpyAsync in this context. "
        "The stream parameter type differs between CUDA and HIP in versions prior to ROCm 5.3."
    ),
    "affected_files": ["kernel.hip"],
    "affected_lines": [42, 67],
    "confidence": 0.92,
    "repair_plan": [
        "Replace hipMemcpyAsync with hipMemcpyWithStream and pass the stream explicitly.",
        "Update the stream handle type from cudaStream_t to hipStream_t.",
    ],
}

_MOCK_PATCH_RESPONSE = {
    "summary": "Applied targeted fix for hipMemcpyAsync stream parameter mismatch.",
    "modified_files": ["kernel.hip"],
    "changes": [
        {
            "file": "kernel.hip",
            "reason": "Replace unsupported hipMemcpyAsync call with hipMemcpyWithStream",
            "lines": [42, 43],
        }
    ],
}

_MOCK_RESEARCH_RESPONSE = {
    "summary": (
        "ROCm documentation confirms that hipMemcpy stream synchronization "
        "requires explicit stream handles in ROCm < 5.3."
    ),
    "findings": [
        "According to the ROCm documentation, hipMemcpy stream synchronization "
        "requires explicit stream handles.",
        "GitHub issue #4821 documents this incompatibility for CUDA 11.x migrations.",
    ],
    "recommended_actions": [
        "Use hipMemcpyWithStream instead of hipMemcpyAsync for ROCm < 5.3.",
        "Alternatively, upgrade to ROCm 5.3+ where the API was aligned with CUDA.",
    ],
}

# Default response used when the message doesn't match a known agent pattern
_MOCK_DEFAULT_RESPONSE = {
    "result": "Mock AI response: task completed successfully.",
    "confidence": 0.85,
}


class MockFireworksClient:
    """
    Deterministic mock client used during pre-hackathon development.

    Interface is identical to FireworksClient so the factory swap is seamless.
    Introduces a small artificial delay (0–50 ms) to simulate real latency.
    All calls are logged so the audit trail reflects what the real API would receive.
    """

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Return a deterministic mock response based on the message content.

        Args:
            model:      Ignored in mock mode (logged for audit).
            messages:   List of {role, content} dicts — used to detect agent type.
            max_tokens: Ignored in mock mode (logged for audit).

        Returns:
            Dict matching the OpenAI-compatible completion response schema with
            mock content embedded in choices[0].message.content as JSON string.
        """
        import json

        logger.debug(
            "[MockFireworksClient] chat_completion called. "
            "model=%s, max_tokens=%d, message_count=%d",
            model, max_tokens, len(messages),
        )

        # Identify which agent is calling based on system prompt content
        system_content = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "").lower()
                break

        if "analysis" in system_content or "root cause" in system_content:
            mock_body = _MOCK_ANALYSIS_RESPONSE
        elif "patch" in system_content or "modify" in system_content:
            mock_body = _MOCK_PATCH_RESPONSE
        elif "research" in system_content or "documentation" in system_content:
            mock_body = _MOCK_RESEARCH_RESPONSE
        else:
            mock_body = _MOCK_DEFAULT_RESPONSE

        content_str = json.dumps(mock_body, indent=2)

        # Simulate realistic latency (0–50 ms)
        time.sleep(random.uniform(0.0, 0.05))

        return {
            "id": f"mock-completion-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content_str,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": sum(len(m.get("content", "")) // 4 for m in messages),
                "completion_tokens": len(content_str) // 4,
                "total_tokens": (
                    sum(len(m.get("content", "")) // 4 for m in messages)
                    + len(content_str) // 4
                ),
            },
        }


# ---------------------------------------------------------------------------
# Factory function — always use this; never instantiate a client directly
# ---------------------------------------------------------------------------

def get_ai_client() -> FireworksClient | MockFireworksClient:
    """
    Return the active AI client based on the USE_MOCK_AI environment variable.

    Pre-hackathon (USE_MOCK_AI=true):  returns MockFireworksClient
    Hackathon     (USE_MOCK_AI=false): returns FireworksClient

    No code changes are needed to swap; only .env changes are required.
    See .agent/MOCK_SERVICES.md for the full hackathon swap checklist.
    """
    from app.config.settings import settings

    if settings.USE_MOCK_AI:
        logger.debug("[get_ai_client] USE_MOCK_AI=true — returning MockFireworksClient")
        return MockFireworksClient()
    else:
        logger.debug("[get_ai_client] USE_MOCK_AI=false — returning FireworksClient")
        return FireworksClient()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _backoff_delay(attempt: int) -> float:
    """
    Compute exponential back-off delay with full jitter.

    Formula: random(0, min(MAX_DELAY_S, BASE_DELAY_S * 2^(attempt-1)))

    This prevents thundering herd when many workers hit a rate limit
    simultaneously, as recommended for distributed API clients.
    """
    cap = min(MAX_DELAY_S, BASE_DELAY_S * (2 ** (attempt - 1)))
    return random.uniform(0.0, cap)
