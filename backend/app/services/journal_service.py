"""
backend/app/services/journal_service.py

Migration Journal Service — Session 10.1

Provides read/write persistence operations for the Migration Journal,
writing to both Redis list keys and the workspace filesystem reports directory.
"""

import os
import json
import datetime
import hashlib
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

import app.redis.client
from app.redis.keys import journal_key, metadata_key
from app.workspace.manager import get_workspace_path

logger = logging.getLogger("journal_service")


async def append_journal_entry(migration_id: str, entry: Dict[str, Any]) -> None:
    """
    Appends a new journal entry to both the Redis list key
    and the migration workspace's filesystem (reports/migration_journal.json).
    """

    # 1. Write to Redis List
    redis_list_key = journal_key(migration_id)
    serialized_entry = json.dumps(entry)
    await app.redis.client.redis_client.rpush(redis_list_key, serialized_entry)
    logger.debug("[JournalService] Appended entry to Redis key %s", redis_list_key)

    # 2. Write to Filesystem
    workspace_path = get_workspace_path(migration_id)
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    journal_file = reports_dir / "migration_journal.json"

    existing_entries = []
    if journal_file.exists():
        try:
            with open(journal_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_entries = data
        except Exception as exc:
            logger.warning("[JournalService] Could not read existing filesystem journal: %s", exc)

    existing_entries.append(entry)

    try:
        with open(journal_file, "w", encoding="utf-8") as f:
            json.dump(existing_entries, f, indent=2)
        logger.debug("[JournalService] Serialized journal list to %s", journal_file)
    except Exception as exc:
        logger.error("[JournalService] Failed to write journal list to filesystem: %s", exc)


async def get_journal(migration_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves all journal entries for a given migration.
    Tries loading from Redis list first, falling back to workspace reports file.
    """
    redis_list_key = journal_key(migration_id)
    try:
        raw_entries = await app.redis.client.redis_client.lrange(redis_list_key, 0, -1)
        if raw_entries:
            return [json.loads(e) for e in raw_entries]
    except Exception as exc:
        logger.warning("[JournalService] Redis lookup failed: %s", exc)

    # Fallback to filesystem
    workspace_path = get_workspace_path(migration_id)
    journal_file = workspace_path / "reports" / "migration_journal.json"
    if journal_file.exists():
        try:
            with open(journal_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as exc:
            logger.error("[JournalService] Filesystem lookup failed: %s", exc)

    return []


async def write_state_journal_entry(context: Any) -> None:
    """
    Constructs a standard journal entry from WorkflowContext and appends it.
    Usually called right after each state execution terminates in WorkflowEngine.
    """
    # 1-indexed attempt number
    attempt = context.current_attempt
    if attempt == 0:
        attempt = 1

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    compiler_result = "N/A"
    if context.current_state == "COMPILING":
        compiler_result = "SUCCESS" if context.compilation_success else "FAILED"

    analysis_summary = None
    if context.analysis_result:
        analysis_summary = context.analysis_result.get("root_cause") or context.analysis_result.get("summary")

    patch_summary = None
    if getattr(context, "patch_metadata", None):
        patch_summary = context.patch_metadata.get("summary")

    research_summary = None
    if context.research_context:
        research_summary = context.research_context
    elif context.migration_journal:
        # Check if the latest in-memory journal entry contains research info
        latest_entry = context.migration_journal[-1]
        if isinstance(latest_entry, dict) and "research_summary" in latest_entry:
            research_summary = latest_entry["research_summary"]

    files_modified = []
    if context.patched_source_path:
        files_modified = [os.path.basename(context.patched_source_path)]

    compiler_error_hash = None
    if context.last_compile_stderr:
        compiler_error_hash = hashlib.sha256(context.last_compile_stderr.encode("utf-8")).hexdigest()

    main_error = None
    if context.current_state == "COMPILING" and not context.compilation_success:
        from app.compiler.error_parser import extract_main_error
        main_error = extract_main_error(context.last_compile_stderr)
    elif context.failure_reason:
        main_error = context.failure_reason[:500]

    error_category = getattr(context, "error_category", "NONE")

    entry = {
        "attempt": attempt,
        "timestamp": timestamp,
        "workflow_state": context.current_state,
        "compiler_result": compiler_result,
        "main_error": main_error,
        "error_category": error_category,
        "analysis_summary": analysis_summary,
        "patch_summary": patch_summary,
        "research_summary": research_summary,
        "files_modified": files_modified,
        "compiler_error_hash": compiler_error_hash,
        "prompt_versions": {
            "analysis": "analysis_v1",
            "patch": "patch_v1",
            "research": "research_v1"
        }
    }

    await append_journal_entry(context.migration_id, entry)
