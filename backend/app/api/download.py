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

    # 1. Get workspace path and verify the ZIP file
    try:
        workspace_path = get_workspace_path(migration_id)
        zip_path = workspace_path / "exports" / "HIPForge_Migration.zip"
    except Exception:
        raise HTTPException(status_code=404, detail="Migration workspace not found")

    # 2. Check if ZIP exists before any other validation
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Migration package not found")

    # 3. Retrieve Redis status (skip if unavailable to avoid failure when ZIP exists)
    skip_status_validation = False
    try:
        redis_status = await app.redis.client.redis_client.get(status_key(migration_id))
        if redis_status:
            if redis_status not in ("COMPLETED", "FAILED"):
                raise HTTPException(status_code=404, detail="Migration is not complete")
        else:
            skip_status_validation = True
    except HTTPException:
        raise
    except Exception:
        skip_status_validation = True

    # 4. Return FileResponse with correct content headers
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"hipforge-{migration_id}.zip"
    )


