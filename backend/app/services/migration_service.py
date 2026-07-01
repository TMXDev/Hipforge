import base64
import datetime
import uuid
import logging
from typing import Dict, Any

from app.workspace.manager import create_workspace, write_source_file
import app.redis.client
from app.redis.keys import status_key, attempt_key, retry_budget_key, metadata_key
from app.redis.manager import enqueue_job

logger = logging.getLogger("migration_service")

def decode_file_content(file_str: str) -> str:
    """
    Decodes the source file content. Handles data URLs, raw base64, 
    and falls back to writing the string directly if decoding fails.
    """
    # If the content is sent as a Data URL, strip the header
    if "," in file_str and (file_str.startswith("data:") or "base64" in file_str.split(",")[0]):
        file_str = file_str.split(",", 1)[1]
    
    try:
        decoded_bytes = base64.b64decode(file_str.strip(), validate=True)
        return decoded_bytes.decode("utf-8")
    except Exception:
        # Fallback to direct raw string if not valid base64 or not utf-8
        return file_str

async def initiate_migration(
    file_content: str,
    filename: str,
    target_gpu_architecture: str,
    retry_budget: int,
    migration_mode: str
) -> str:
    """
    Handles the complete orchestration of initiating a migration:
    1. Generates a unique migration_id of the form migration_YYYYMMDD_HHMMSS_<short_uuid>.
    2. Creates an isolated workspace directory structure.
    3. Writes the uploaded source file inside the workspace input/ directory.
    4. Initializes Redis state keys (status to QUEUED, attempt to 0, retry budget).
    5. Sets up the metadata hash in Redis.
    6. Enqueues the job into the Redis pending queue.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    migration_id = f"migration_{date_str}_{time_str}_{short_uuid}"
    
    logger.info(f"Initiating migration {migration_id} for file {filename}")
    
    # 1. Create workspace
    workspace_path = create_workspace(migration_id)
    
    # 2. Write source file
    content = decode_file_content(file_content)
    write_source_file(migration_id, filename, content)
    
    # 3. Set Redis status to QUEUED
    await app.redis.client.redis_client.set(status_key(migration_id), "QUEUED")
    
    # 4. Set attempts to 0
    await app.redis.client.redis_client.set(attempt_key(migration_id), "0")
    
    # 5. Set retry budget
    await app.redis.client.redis_client.set(retry_budget_key(migration_id), str(retry_budget))
    
    # 6. Initialize metadata
    metadata = {
        "project_name": filename,
        "created_at": now.isoformat(),
        "current_state": "QUEUED",
        "workspace_path": workspace_path,
        "compiler": "hipcc",
        "target_architecture": target_gpu_architecture
    }
    await app.redis.client.redis_client.hset(metadata_key(migration_id), mapping=metadata)
    
    # 7. Enqueue the migration job
    payload = {
        "workspace_path": workspace_path,
        "retry_budget": retry_budget
    }
    await enqueue_job(migration_id, payload)
    
    logger.info(f"Migration {migration_id} successfully queued.")
    return migration_id
