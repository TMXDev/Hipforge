"""
backend/app/agents/analysis_agent.py

Analysis Agent — Session 9.2

The Analysis Agent determines WHY compilation failed.
It does NOT modify source code.

Per docs/09_AI_AGENTS.md:
  - Input: HIP source, compiler errors, attempt number, Migration Journal
  - Output: structured JSON with summary, root_cause, affected_files,
            affected_lines, confidence, repair_plan
  - Prompt structure (6 sections per spec):
      1. System Prompt
      2. Current Task
      3. Source Code
      4. Compiler Diagnostics
      5. Migration Journal
      6. Expected JSON Schema

Per docs/04_TECHNOLOGY_DECISIONS.md:
  - Analysis Agent uses Qwen (strong reasoning, technical understanding)

Per .agent/MOCK_SERVICES.md:
  - Must call get_ai_client() — never instantiate client directly.
  - In pre-hackathon mode (USE_MOCK_AI=true), MockFireworksClient is returned.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.agents.base_agent import get_ai_client

logger = logging.getLogger("analysis_agent")

# ---------------------------------------------------------------------------
# Model selection (per docs/04_TECHNOLOGY_DECISIONS.md)
# ---------------------------------------------------------------------------
ANALYSIS_MODEL = "accounts/fireworks/models/deepseek-v4-pro"

# ---------------------------------------------------------------------------
# Prompt template — exact 6-section structure from docs/09_AI_AGENTS.md
#
#   1. System Prompt
#   2. Current Task
#   3. Source Code
#   4. Compiler Diagnostics
#   5. Migration Journal
#   6. Expected JSON Schema
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the HIPForge Analysis Agent — a specialized AI for diagnosing CUDA-to-HIP \
migration failures.

Your ONLY responsibility is to identify the root cause of a compilation failure \
and produce a structured repair strategy. You do NOT modify source code.

Rules you must follow:
- Base your analysis exclusively on the compiler diagnostics and source code provided.
- Never invent APIs or guess at missing information.
- Never repeat a repair strategy that has already been attempted and failed \
(see Migration Journal).
- Classify the error type: syntax | API mismatch | compiler intrinsic | architecture.
- Identify every affected file and line number precisely.
- Produce a ranked repair_plan list (most promising fix first).
- Respond ONLY with valid JSON matching the schema exactly — no prose, no markdown.\
"""

_EXPECTED_SCHEMA = """\
{
  "summary": "<one-sentence summary of what went wrong>",
  "root_cause": "<detailed explanation of the underlying cause>",
  "affected_files": ["<filename>"],
  "affected_lines": [<line_number>, ...],
  "confidence": <float 0.0-1.0>,
  "repair_plan": [
    "<step 1 — most likely fix>",
    "<step 2 — alternative if step 1 fails>"
  ]
}\
"""


def _build_messages(
    source_code: str,
    compiler_errors: List[Any],
    attempt: int,
    migration_journal: Optional[List[Dict[str, Any]]],
    previous_research: Optional[str],
) -> List[Dict[str, str]]:
    """
    Construct the 6-section prompt message list per docs/09_AI_AGENTS.md.

    Returns a list of {role, content} dicts for the Fireworks chat API.
    """
    # Format compiler errors for the prompt
    if compiler_errors:
        error_lines = []
        for err in compiler_errors:
            if hasattr(err, "model_dump"):
                # Pydantic CompilerError model
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
        diagnostics_text = "(no structured errors — see raw stderr)"

    # Format Migration Journal
    if migration_journal:
        journal_text = json.dumps(migration_journal, indent=2)
    else:
        journal_text = "[]  (first attempt — no prior history)"

    # Format previous research if available
    research_section = ""
    if previous_research:
        research_section = f"\n\n## Previous Research\n{previous_research}"

    # Assemble the user message as the 6-section template
    user_content = f"""\
## 2. Current Task
Compilation attempt #{attempt + 1} has failed.
Identify the root cause and produce a ranked repair plan.
Do not repeat strategies already in the Migration Journal.

## 3. Source Code
```hip
{source_code}
```

## 4. Compiler Diagnostics
```
{diagnostics_text}
```

## 5. Migration Journal
```json
{journal_text}
```{research_section}

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
    Parse the AI completion content into the Analysis Agent output schema.

    Handles:
    - Raw JSON string
    - JSON embedded in markdown code fences

    Returns the parsed dict, or raises ValueError if JSON is invalid.
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
        # Remove first line (```json or ```) and last line (```)
        inner = [line for line in lines[1:] if line.strip() != "```"]
        content = "\n".join(inner).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Analysis Agent returned invalid JSON: {e}\n"
            f"Raw content (first 500 chars): {raw_content[:500]}"
        ) from e

    # Validate required fields
    required = {"summary", "root_cause", "affected_files", "affected_lines",
                "confidence", "repair_plan"}
    missing = required - set(parsed.keys())
    if missing:
        raise ValueError(
            f"Analysis Agent response is missing required fields: {missing}\n"
            f"Got fields: {set(parsed.keys())}"
        )

    return parsed


def analyze(
    compiler_errors: List[Any],
    source_code: str,
    attempt: int = 0,
    migration_journal: Optional[List[Dict[str, Any]]] = None,
    previous_research: Optional[str] = None,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """
    Run the Analysis Agent to diagnose a HIP compilation failure.

    This is the main entry point used by the ANALYZING workflow state handler.

    Args:
        compiler_errors:   List of CompilerError models or dicts from hipcc output.
        source_code:       The current HIP source code that failed to compile.
        attempt:           Zero-indexed current repair attempt number.
        migration_journal: List of previous attempt records (may be None/empty).
        previous_research: Research findings from the Research Agent (optional).
        max_tokens:        Maximum tokens for the AI completion response.

    Returns:
        Dict with the Analysis Agent output schema:
        {
            "summary":        str   — one-sentence description of what went wrong,
            "root_cause":     str   — detailed root cause explanation,
            "affected_files": list  — filenames involved in the error,
            "affected_lines": list  — line numbers where errors occur,
            "confidence":     float — agent's confidence in its diagnosis (0–1),
            "repair_plan":    list  — ordered list of repair steps to try,
        }

    Raises:
        ValueError: if the AI response is not valid JSON or missing required fields.
        RuntimeError: if the AI client exhausts all retries.
    """
    client = get_ai_client()
    messages = _build_messages(
        source_code=source_code,
        compiler_errors=compiler_errors,
        attempt=attempt,
        migration_journal=migration_journal,
        previous_research=previous_research,
    )

    logger.info(
        "[AnalysisAgent] Sending analysis request to %s (attempt %d, %d error(s))",
        ANALYSIS_MODEL, attempt + 1, len(compiler_errors),
    )

    completion = client.chat_completion(
        model=ANALYSIS_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )

    raw_content = completion["choices"][0]["message"]["content"]

    logger.debug("[AnalysisAgent] Raw response (first 300 chars): %s", raw_content[:300])

    result = _parse_response(raw_content)

    logger.info(
        "[AnalysisAgent] Analysis complete. confidence=%.2f, repair_plan_steps=%d",
        result.get("confidence", 0.0),
        len(result.get("repair_plan", [])),
    )

    return result
