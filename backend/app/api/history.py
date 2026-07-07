"""
backend/app/api/history.py

Migration History API — durable file-backed history endpoints.

GET /api/v1/migrations/history             list, newest first, ?limit=20
GET /api/v1/migrations/history/{job_id}    single entry + live path checks
"""

import os
import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from app.config.settings import settings
from app.workspace.manager import get_workspace_path
from app.api.security_utils import validate_migration_id

router = APIRouter()
logger = logging.getLogger("history_api")


def _history_dir() -> Path:
    root = os.getenv("WORKSPACE_PATH") or settings.WORKSPACE_PATH
    return Path(root) / "history"


def _read_history_file(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _enrich(entry: dict) -> dict:
    """Add live report_exists / artifact_exists checks at read time."""
    report_md = entry.get("report_md_path") or ""
    artifact = entry.get("artifact_path") or ""
    entry["report_exists"] = bool(report_md and Path(report_md).exists())
    entry["artifact_exists"] = bool(artifact and Path(artifact).exists())
    return entry


@router.get("/api/v1/migrations/history")
async def list_migration_history(limit: int = Query(default=20, ge=1, le=200)):
    """
    Returns the most recent migrations, newest first.
    Reads only small history summary files — not full reports.
    """
    hdir = _history_dir()
    if not hdir.exists():
        return []

    files = sorted(hdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for path in files[:limit]:
        try:
            entry = _read_history_file(path)
            # Lightweight list view: skip path fields, keep key status fields
            results.append({
                "job_id": entry.get("job_id"),
                "finished_at": entry.get("finished_at"),
                "input_name": entry.get("input_name"),
                "target_architecture": entry.get("target_architecture"),
                "final_state": entry.get("final_state"),
                "compile_status": entry.get("compile_status"),
                "validation_confidence": entry.get("validation_confidence"),
                "error_category": entry.get("error_category"),
                "main_error": entry.get("main_error"),
                "report_missing": entry.get("report_missing", True),
                "artifact_missing": entry.get("artifact_missing", True),
            })
        except Exception as exc:
            logger.warning("[HistoryAPI] Skipping unreadable history file %s: %s", path, exc)
    return results


@router.get("/api/v1/migrations/history/{job_id}")
async def get_migration_history_detail(job_id: str):
    """
    Returns the full history summary for a single migration.
    Augments with live report_exists / artifact_exists checks.
    Returns 404 if the history file does not exist.
    """
    validate_migration_id(job_id)
    hdir = _history_dir()
    path = hdir / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="History entry not found")
    try:
        entry = _read_history_file(path)
    except Exception as exc:
        logger.error("[HistoryAPI] Failed to read history file %s: %s", path, exc)
        raise HTTPException(status_code=500, detail="Failed to read history entry")
    return _enrich(entry)
