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
                "Please configure a valid Fireworks API key in your .env file."
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

        from app.config.settings import settings

        url = f"{settings.FIREWORKS_API_BASE}/chat/completions"
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
# Factory function — always use this; never instantiate a client directly
# ---------------------------------------------------------------------------

class MockFireworksClient(FireworksClient):
    """
    Offline Fireworks-compatible client used for tests and demo/mock mode.
    """

    def __init__(self):
        pass

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        system_text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system").lower()
        user_text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        user_lower = user_text.lower()

        if "research agent" in system_text or "documentation" in system_text:
            content = {
                "summary": "ROCm documentation confirms a portable HIP replacement strategy.",
                "problem": "A CUDA API or warp-level assumption needs a HIP-compatible equivalent.",
                "sources": ["https://rocm.docs.amd.com/projects/HIP/en/latest/"],
                "findings": [
                    "ROCm documentation confirms HIP APIs should use hip/hip_runtime.h and HIP runtime types.",
                    "Wavefront-sensitive code should avoid hard-coding NVIDIA warp width assumptions.",
                ],
                "recommended_actions": [
                    "Use HIP runtime APIs and compile for the requested AMD GPU architecture.",
                    "Re-run semantic validation after the patch to catch portability issues.",
                ],
                "confidence": 0.86,
            }
        elif "analysis agent" in system_text or "root cause" in user_lower:
            content = {
                "summary": "Compilation failed after CUDA-to-HIP translation and needs a targeted source patch.",
                "root_cause": "The translated source still contains an API or semantic pattern that HIP cannot compile as written.",
                "affected_files": ["kernel.hip"],
                "affected_lines": [1],
                "confidence": 0.82,
                "repair_plan": [
                    "Replace remaining CUDA-only APIs with HIP equivalents.",
                    "Preserve the existing kernel structure and retry compilation.",
                ],
            }
        elif "patch agent" in system_text or "source code" in user_lower:
            content = user_text
            if "```hip" in content:
                content = content.split("```hip", 1)[1].split("```", 1)[0].strip()
            elif "```" in content:
                content = content.split("```", 1)[1].split("```", 1)[0].strip()
            if not content:
                content = "#include <hip/hip_runtime.h>\n"
            content = content.replace("HIPFORGE_MOCK_COMPILE_ERROR", "HIPFORGE_MOCK_COMPILE_FIXED")
        else:
            content = {"result": "Mock Fireworks response"}

        if not isinstance(content, str):
            import json
            content = json.dumps(content)

        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        completion_tokens = len(content.split())
        return {
            "id": "mock-fireworks-completion",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


def get_ai_client() -> FireworksClient | MockFireworksClient:
    """
    Return the configured AI client.
    """
    from app.config.settings import settings

    env_value = os.getenv("USE_MOCK_AI")
    use_mock_ai = settings.USE_MOCK_AI
    if env_value is not None:
        use_mock_ai = env_value.strip().lower() in {"1", "true", "yes", "on"}

    if use_mock_ai:
        return MockFireworksClient()
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
