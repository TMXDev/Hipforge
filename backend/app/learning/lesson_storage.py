import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("lesson_storage")

LESSON_PREFIX = "learning"

def normalize_error_signature(stderr: str) -> str:
    return hashlib.sha256((stderr or "").encode("utf-8")).hexdigest()[:16]

def lesson_key(category: str, signature: str) -> str:
    return f"{LESSON_PREFIX}:{category}:{signature}"

async def store_lesson(
    redis_client,
    category: str,
    stderr: str,
    target_architecture: str = "",
    recommended_action: str = "",
    patch_attempted: bool = False,
    patch_skipped_reason: str = "",
) -> str:
    sig = normalize_error_signature(stderr)
    key = lesson_key(category, sig)
    lesson = {
        "category": category,
        "error_signature": sig,
        "target_architecture": target_architecture,
        "main_error_text": (stderr or "")[:500],
        "recommended_action": recommended_action,
        "patch_attempted": patch_attempted,
        "patch_skipped_reason": patch_skipped_reason,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        await redis_client.set(key, json.dumps(lesson))
        logger.info("[LessonStorage] Stored: %s", key)
    except Exception as exc:
        logger.warning("[LessonStorage] Failed to store %s: %s", key, exc)
    return key

async def find_lesson(redis_client, stderr: str) -> Optional[dict]:
    if not stderr:
        return None
    sig = normalize_error_signature(stderr)
    categories = [
        "UNSUPPORTED_FEATURE",
        "UNRESOLVED_SYMBOL",
        "PATCH_NOOP",
        "AI_ERROR",
        "USER_CODE_ERROR",
        "COMPILATION_ERROR",
    ]
    for cat in categories:
        key = lesson_key(cat, sig)
        try:
            raw = await redis_client.get(key)
            if raw:
                lesson = json.loads(raw)
                logger.info("[LessonStorage] Found lesson: %s", key)
                return lesson
        except Exception:
            pass
    return None
