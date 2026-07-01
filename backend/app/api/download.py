import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import app.redis.client
from app.redis.keys import status_key
from app.workspace.manager import get_workspace_path
from app.api.security_utils import validate_migration_id

router = APIRouter()


@router.get("/api/v1/migrate/{migration_id}/download")
async def download_migration_package(migration_id: str):
    """
    Streams the migration ZIP archive for a completed migration.
    Returns 404 if the migration is not complete or does not exist.
    """
    validate_migration_id(migration_id)
    # 1. Retrieve Redis status
    try:
        redis_status = await app.redis.client.redis_client.get(status_key(migration_id))
    except Exception:
        redis_status = None

    # 2. Get workspace path and verify the ZIP file
    try:
        workspace_path = get_workspace_path(migration_id)
        zip_path = workspace_path / "exports" / "HIPForge_Migration.zip"
    except Exception:
        raise HTTPException(status_code=404, detail="Migration workspace not found")

    # 3. Validation: status must be COMPLETED (if status key exists)
    if redis_status and redis_status != "COMPLETED":
        raise HTTPException(status_code=404, detail="Migration is not complete")

    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Migration package not found")

    # 4. Return FileResponse with correct content headers
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"hipforge-{migration_id}.zip"
    )


@router.get("/migrate/{migration_id}/download")
async def download_migration_package_fallback(migration_id: str):
    """
    Fallback GET route matching GET /migrate/{id}/download format.
    """
    validate_migration_id(migration_id)
    return await download_migration_package(migration_id)

