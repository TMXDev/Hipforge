"""
backend/app/agents/research_agent.py

Research Agent — Session 9.4

The Research Agent provides external technical knowledge when deterministic repair attempts fail.
It does NOT modify source code.

Per docs/11_RESEARCH_AGENT.md and docs/09_AI_AGENTS.md:
  - Input: search query, compiler diagnostics, Migration Journal, source code
  - Output: structured JSON with summary, problem, sources, findings, recommended_actions, confidence
  - Prompt structure (6 sections per spec):
      1. System Prompt
      2. Current Task
      3. Source Code
      4. Compiler Diagnostics
      5. Migration Journal
      6. Expected JSON Schema

Per docs/04_TECHNOLOGY_DECISIONS.md:
  - Uses Fireworks AI Client Wrapper.
  - In pre-hackathon mode (USE_MOCK_AI=true), MockFireworksClient is returned.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.agents.base_agent import get_ai_client

logger = logging.getLogger("research_agent")

# Model selection for reasoning/documentation lookup tasks.
RESEARCH_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/deepseek-v4-flash")

# ---------------------------------------------------------------------------
# Prompt template — exact 6-section structure from docs/09_AI_AGENTS.md
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the HIPForge Research Agent — a specialized AI for gathering ROCm/HIP documentation \
and technical knowledge to resolve CUDA-to-HIP migration failures.

Your ONLY responsibility is to research documentation, alternative APIs, and migration guides \
to find correct HIP equivalents. You do NOT generate source code or write code fixes.

Rules you must follow:
- Prioritize official AMD ROCm/HIP documentation and official examples.
- Focus heavily on thread-grouping and wavefront portability. Look for solutions that accommodate variable AMD wavefront sizes (32 or 64 threads) using 'warpSize' built-ins or 'hipGetDeviceProperties' queries.
- Ensure that researched instructions for shuffles and ballots specify uint64_t masks instead of 32-bit types, adhering to CDNA/RDNA cross-architecture requirements.
- Never repeat a recommendation that has already been attempted and failed \
(see Migration Journal).
- Respond ONLY with valid JSON matching the schema exactly — no prose, no markdown.\
"""

_EXPECTED_SCHEMA = """\
{
  "summary": "<summary of documentation findings>",
  "problem": "<description of the target compatibility problem>",
  "sources": [
    "<reference url or documentation source>"
  ],
  "findings": [
    "<finding 1 — specific API or documentation detail>",
    "<finding 2 — additional details or reference link>"
  ],
  "recommended_actions": [
    "<action 1 — recommended API call or replacement>",
    "<action 2 — compile/runtime verification step>"
  ],
  "confidence": <float between 0.0 and 1.0>
}\
"""


def _build_messages(
    query: str,
    source_code: Optional[str],
    compiler_errors: Optional[List[Any]],
    migration_journal: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, str]]:
    """
    Construct the 6-section prompt message list per docs/09_AI_AGENTS.md.
    """
    # Format compiler errors for the prompt
    if compiler_errors:
        error_lines = []
        for err in compiler_errors:
            if hasattr(err, "model_dump"):
                d = err.model_dump()
                error_lines.append(
                    f"  {d.get('file', '?')}:{d.get('line', '?')}:{d.get('column', '?')}: "
                    f"error: {d.get('message', '?')} [{d.get('code', '')}]"
                )
            elif isinstance(err, dict):
                error_lines.append(
                    f"  {err.get('file', '?')}:{err.get('line', '?')}:{err.get('column', '?')}: "
                    f"error: {err.get('message', '?')} [{err.get('code', '')}]"
                )
            else:
                error_lines.append(f"  {err}")
        diagnostics_text = "\n".join(error_lines)
    else:
        diagnostics_text = "(no structured errors)"

    # Format Migration Journal
    if migration_journal:
        journal_text = json.dumps(migration_journal, indent=2)
    else:
        journal_text = "[]  (first attempt — no prior history)"

    # Source code section
    source_section = source_code if source_code else "(no source code context available)"

    # Assemble the user message as the 6-section template
    user_content = f"""\
## 2. Current Task
Research the following query or API incompatibility:
{query}

## 3. Source Code
```hip
{source_section}
```

## 4. Compiler Diagnostics
```
{diagnostics_text}
```

## 5. Migration Journal
```json
{journal_text}
```

## 6. Expected JSON Schema
Respond ONLY with valid JSON matching this schema exactly:
```
{_EXPECTED_SCHEMA}
```\
"""

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _parse_response(raw_content: str) -> Dict[str, Any]:
    """
    Parse the AI completion content into the Research Agent output schema.
    """
    content = raw_content.strip()

    # Strip <think>...</think> tags if present (from reasoning models like DeepSeek)
    if "<think>" in content:
        think_end = content.find("</think>")
        if think_end != -1:
            content = content[think_end + 8:].strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.splitlines()
        inner = [line for line in lines[1:] if line.strip() != "```"]
        content = "\n".join(inner).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Research Agent returned invalid JSON: {e}\n"
            f"Raw content (first 500 chars): {raw_content[:500]}"
        ) from e

    # Core required fields (present in both docs/09_AI_AGENTS.md and MockFireworksClient)
    required = {"summary", "findings", "recommended_actions"}
    missing = required - set(parsed.keys())
    if missing:
        raise ValueError(
            f"Research Agent response is missing required fields: {missing}\n"
            f"Got fields: {set(parsed.keys())}"
        )

    # Concurrently populate fields from docs/11_RESEARCH_AGENT.md to be fully compliant
    if "problem" not in parsed:
        parsed["problem"] = ""
    if "sources" not in parsed:
        parsed["sources"] = []
    if "confidence" not in parsed:
        parsed["confidence"] = 1.0

    return parsed


def research(
    query: str,
    source_code: Optional[str] = None,
    compiler_errors: Optional[List[Any]] = None,
    migration_journal: Optional[List[Dict[str, Any]]] = None,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """
    Run the Research Agent to gather AMD equivalent APIs or documentation details.

    Args:
        query:             The search query string representing the compatibility issue.
        source_code:       The current source code (optional).
        compiler_errors:   List of compiler errors (optional).
        migration_journal: List of previous attempts/journal records (optional).
        max_tokens:        Maximum completion tokens.

    Returns:
        Dict conforming to the Research Output schema:
        {
            "summary":             str,
            "problem":             str,
            "sources":             list,
            "findings":            list,
            "recommended_actions": list,
            "confidence":          float
        }
    """
    client = get_ai_client()
    messages = _build_messages(
        query=query,
        source_code=source_code,
        compiler_errors=compiler_errors,
        migration_journal=migration_journal,
    )

    logger.info(
        "[ResearchAgent] Sending research request to %s (query: '%s')",
        RESEARCH_MODEL, query
    )

    completion = client.chat_completion(
        model=RESEARCH_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )

    raw_content = completion["choices"][0]["message"]["content"]
    logger.debug("[ResearchAgent] Raw response: %s", raw_content[:300])

    result = _parse_response(raw_content)
    logger.info(
        "[ResearchAgent] Research complete. summary='%s', confidence=%.2f",
        result.get("summary", "")[:120], result.get("confidence", 1.0)
    )

    return result
