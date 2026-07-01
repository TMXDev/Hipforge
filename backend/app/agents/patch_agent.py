"""
backend/app/agents/patch_agent.py

Patch Agent — Session 9.3

The Patch Agent applies targeted modifications to HIP source code based on
the Analysis Agent's repair plan.

Per docs/09_AI_AGENTS.md:
  - Input: current HIP source, analysis JSON, compiler errors, Migration Journal
  - Output: full corrected source file as a string
  - Prompt structure (6 sections per spec):
      1. System Prompt
      2. Current Task  (repair plan from analysis)
      3. Source Code
      4. Compiler Diagnostics
      5. Migration Journal
      6. Expected Output (full corrected source)

Per docs/04_TECHNOLOGY_DECISIONS.md:
  - Patch Agent uses Kimi K2.7 Code (optimized for code generation/editing)

Restrictions (from spec):
  - Must NOT rewrite entire files unnecessarily.
  - Must NOT remove working functionality.
  - Must NOT introduce unrelated optimizations.
  - Must NOT ignore the repair plan.
  - Must generate minimal patches.
  - Must explain every modification.

The patch function returns the FULL corrected source file as a string.
The PATCHING state handler is responsible for writing it to disk.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.agents.base_agent import get_ai_client

logger = logging.getLogger("patch_agent")

# ---------------------------------------------------------------------------
# Model selection (per docs/04_TECHNOLOGY_DECISIONS.md)
# Kimi K2 is optimized for code generation and editing.
# ---------------------------------------------------------------------------
PATCH_MODEL = "accounts/fireworks/models/kimi-k2p6"

# ---------------------------------------------------------------------------
# Prompt template — exact 6-section structure from docs/09_AI_AGENTS.md
#
#   1. System Prompt
#   2. Current Task  (repair plan + analysis summary)
#   3. Source Code
#   4. Compiler Diagnostics
#   5. Migration Journal
#   6. Expected Output format
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the HIPForge Patch Agent — a specialized AI for applying targeted \
source code fixes to HIP GPU code that has failed to compile.

Your ONLY responsibility is to apply the repair plan produced by the Analysis Agent \
and return the full corrected source file.

Rules you must follow:
- Apply ONLY the changes described in the repair plan. Do not refactor or restructure.
- Preserve ALL existing formatting, indentation, and whitespace conventions.
- Preserve ALL working code that is not related to the identified error.
- Generate the MINIMAL patch required to address the compiler error.
- Do NOT add unsolicited optimizations, comments, or features.
- Do NOT remove functionality that compiles correctly.
- Do NOT repeat a fix that is already recorded in the Migration Journal as failed.
- Respond with ONLY the complete corrected source file — no explanation, \
no markdown fences, no commentary. Just the raw source code.\
"""


def _format_analysis(analysis: Dict[str, Any]) -> str:
    """Format the Analysis Agent output into a readable prompt section."""
    repair_steps = analysis.get("repair_plan", [])
    numbered = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(repair_steps))
    return (
        f"Root Cause: {analysis.get('root_cause', '(not provided)')}\n"
        f"Affected Files: {', '.join(analysis.get('affected_files', []) or ['(unknown)'])}\n"
        f"Affected Lines: {analysis.get('affected_lines', [])}\n"
        f"Confidence: {analysis.get('confidence', 0.0):.0%}\n\n"
        f"Repair Plan (apply in order):\n{numbered}"
    )


def _format_errors(compiler_errors: List[Any]) -> str:
    """Format CompilerError models or dicts into a diagnostics string."""
    if not compiler_errors:
        return "(no structured errors — apply repair plan based on analysis)"
    lines = []
    for err in compiler_errors:
        if hasattr(err, "model_dump"):
            d = err.model_dump()
        elif isinstance(err, dict):
            d = err
        else:
            lines.append(f"  {err}")
            continue
        lines.append(
            f"  {d.get('file', '?')}:{d.get('line', '?')}:{d.get('column', '?')}: "
            f"error: {d.get('message', '?')} [{d.get('code', '')}]"
        )
    return "\n".join(lines)


def _build_messages(
    source_code: str,
    analysis: Dict[str, Any],
    compiler_errors: List[Any],
    migration_journal: Optional[List[Dict[str, Any]]],
    previous_patches: Optional[List[str]],
) -> List[Dict[str, str]]:
    """
    Construct the 6-section prompt message list per docs/09_AI_AGENTS.md.

    Returns a list of {role, content} dicts for the Fireworks chat API.
    """
    analysis_text = _format_analysis(analysis)
    diagnostics_text = _format_errors(compiler_errors)

    if migration_journal:
        journal_text = json.dumps(migration_journal, indent=2)
    else:
        journal_text = "[]  (first attempt — no prior history)"

    if previous_patches:
        patches_text = "\n\n".join(previous_patches)
    else:
        patches_text = "(none)"

    user_content = f"""\
## 2. Current Task
Apply the following repair plan to fix the compilation failure.
Return ONLY the full corrected source file — nothing else.

### Analysis Summary
{analysis_text}

## 3. Source Code (current — contains the error)
{source_code}

## 4. Compiler Diagnostics
```
{diagnostics_text}
```

## 5. Migration Journal (prior attempts — do NOT repeat these strategies)
```json
{journal_text}
```

### Previous Patches Applied (for reference)
{patches_text}

## 6. Expected Output
Return the COMPLETE corrected source file as raw text.
Do NOT wrap it in markdown fences.
Do NOT add any explanation before or after the code.
The output will be written directly to the .hip source file.\
"""

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_source(raw_content: str, original_source: str) -> str:
    """
    Extract the corrected source code from the AI response.

    The Patch Agent is instructed to return raw source, but may occasionally
    wrap it in code fences. Strip them if present.

    Returns the extracted source code string.
    Raises ValueError if the response appears to be empty.
    """
    content = raw_content.strip()

    # Strip markdown code fences if the model disobeys the prompt
    if content.startswith("```"):
        lines = content.splitlines()
        # Remove the opening fence (first line: ```hip, ```cpp, or ```)
        # and the closing fence (last non-empty line: ```)
        inner_lines = []
        in_fence = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") and not in_fence:
                in_fence = True
                continue
            if stripped == "```" and in_fence:
                in_fence = False
                continue
            if in_fence:
                inner_lines.append(line)
        content = "\n".join(inner_lines).strip()

    if not content:
        raise ValueError(
            "Patch Agent returned an empty response. "
            "Cannot write empty content to source file."
        )

    return content


def _build_patch_metadata(
    original_source: str,
    patched_source: str,
    filename: str,
    analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the patch metadata dict matching the spec output schema.

    Schema (from docs/09_AI_AGENTS.md):
    {
        "summary": str,
        "modified_files": [str],
        "changes": [{"file": str, "reason": str, "lines": [int]}]
    }

    This metadata is stored in context for the Migration Journal.
    """
    # Compute which lines changed between original and patched
    orig_lines = original_source.splitlines()
    patched_lines = patched_source.splitlines()

    changed_line_nums = []
    max_len = max(len(orig_lines), len(patched_lines))
    for idx in range(max_len):
        orig_line = orig_lines[idx] if idx < len(orig_lines) else None
        patch_line = patched_lines[idx] if idx < len(patched_lines) else None
        if orig_line != patch_line:
            changed_line_nums.append(idx + 1)  # 1-indexed

    repair_plan = analysis.get("repair_plan", [])
    summary = (
        analysis.get("summary", "Patch applied based on Analysis Agent repair plan.")
    )

    return {
        "summary": summary,
        "modified_files": [filename],
        "changes": [
            {
                "file": filename,
                "reason": repair_plan[0] if repair_plan else "Apply repair plan",
                "lines": changed_line_nums[:20],  # cap at 20 for readability
            }
        ],
    }


def patch(
    source_code: str,
    analysis: Dict[str, Any],
    compiler_errors: Optional[List[Any]] = None,
    migration_journal: Optional[List[Dict[str, Any]]] = None,
    previous_patches: Optional[List[str]] = None,
    max_tokens: int = 4096,
) -> str:
    """
    Run the Patch Agent to produce a corrected HIP source file.

    This is the main entry point used by the PATCHING workflow state handler.

    Args:
        source_code:       The current HIP source code that failed to compile.
        analysis:          The Analysis Agent output dict (root_cause, repair_plan, etc.)
        compiler_errors:   List of CompilerError models or dicts from hipcc output.
        migration_journal: List of previous attempt records (may be None/empty).
        previous_patches:  List of raw source strings from prior patch attempts.
        max_tokens:        Maximum tokens for the AI completion response.

    Returns:
        The full corrected source file as a raw string.
        The caller (PATCHING state) is responsible for writing this to disk.

    Raises:
        ValueError:  if the AI response is empty or cannot be extracted.
        RuntimeError: if the AI client exhausts all retries.
    """
    if compiler_errors is None:
        compiler_errors = []
    if migration_journal is None:
        migration_journal = []
    if previous_patches is None:
        previous_patches = []

    client = get_ai_client()
    messages = _build_messages(
        source_code=source_code,
        analysis=analysis,
        compiler_errors=compiler_errors,
        migration_journal=migration_journal,
        previous_patches=previous_patches,
    )

    logger.info(
        "[PatchAgent] Sending patch request to %s. "
        "repair_plan_steps=%d, attempt_history=%d",
        PATCH_MODEL,
        len(analysis.get("repair_plan", [])),
        len(migration_journal),
    )

    completion = client.chat_completion(
        model=PATCH_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )

    raw_content = completion["choices"][0]["message"]["content"]

    logger.debug("[PatchAgent] Raw response length: %d chars", len(raw_content))

    patched_source = _extract_source(raw_content, source_code)

    logger.info(
        "[PatchAgent] Patch complete. Original: %d lines → Patched: %d lines",
        len(source_code.splitlines()),
        len(patched_source.splitlines()),
    )

    return patched_source
