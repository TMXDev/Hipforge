import os
from fastapi import APIRouter, HTTPException, WebSocket
from app.schemas.migration import (
    UploadMigrationRequest,
    PasteMigrationRequest,
    MigrationResponse
)
from app.services.migration_service import initiate_migration
from app.api.security_utils import (
    validate_filename,
    validate_migration_id,
    validate_api_parameters,
    get_decoded_file_size_and_content,
    validate_zip_archive
)
from app.config.settings import settings

router = APIRouter()

@router.post("/api/v1/migrate/upload", response_model=MigrationResponse, status_code=202)
async def upload_project(request: UploadMigrationRequest):
    validate_filename(request.filename)
    if not request.file:
        raise HTTPException(status_code=400, detail="Uploaded file content cannot be empty")
    
    # Check API parameter constraints
    validate_api_parameters(request.target_gpu_architecture, request.migration_mode, request.retry_budget)

    # Check decoded file size and content against settings limit
    size_bytes, decoded_content = get_decoded_file_size_and_content(request.file)
    if size_bytes > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded file size ({size_bytes} bytes) exceeds limit of {settings.WORKSPACE_SIZE_LIMIT}."
        )

    # If it is a zip archive, perform integrity and path traversal validation.
    # Otherwise, check for null bytes in decoded file content.
    ext = os.path.splitext(request.filename)[1].lower()
    if ext == ".zip":
        validate_zip_archive(decoded_content)
    else:
        if b"\x00" in decoded_content:
            raise HTTPException(status_code=400, detail="Null bytes are not allowed in uploaded file")

    migration_id = await initiate_migration(
        file_content=request.file,
        filename=request.filename,
        target_gpu_architecture=request.target_gpu_architecture,
        retry_budget=request.retry_budget,
        migration_mode=request.migration_mode
    )
    return MigrationResponse(
        migration_id=migration_id,
        status="initializing",
        message="Migration initiated successfully."
    )

@router.post("/api/v1/migrate/paste", response_model=MigrationResponse, status_code=202)
async def paste_code(request: PasteMigrationRequest):
    validate_filename(request.filename)
    if not request.code:
        raise HTTPException(status_code=400, detail="Pasted code content cannot be empty")
        
    # Check for null bytes in pasted code
    if "\x00" in request.code:
        raise HTTPException(status_code=400, detail="Null bytes are not allowed in pasted code")
        
    # Check API parameter constraints
    validate_api_parameters(request.target_gpu_architecture, request.migration_mode, request.retry_budget)

    # Check size of pasted code
    code_bytes = request.code.encode("utf-8")
    if len(code_bytes) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Pasted code size ({len(code_bytes)} bytes) exceeds limit of {settings.WORKSPACE_SIZE_LIMIT}."
        )

    migration_id = await initiate_migration(
        file_content=request.code,
        filename=request.filename,
        target_gpu_architecture=request.target_gpu_architecture,
        retry_budget=request.retry_budget,
        migration_mode=request.migration_mode
    )
    return MigrationResponse(
        migration_id=migration_id,
        status="initializing",
        message="Migration initiated successfully."
    )

@router.post("/api/v1/migrate/{migration_id}/cancel")
async def cancel_migration(migration_id: str):
    validate_migration_id(migration_id)
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    from app.redis.publisher import publish_event
    
    # Set status to FAILED in Redis
    await redis_client.set(status_key(migration_id), "FAILED")
    # Set cancel flag
    await redis_client.set(f"migration:{migration_id}:cancelled", "true")
    
    # Publish cancellation event
    await publish_event(
        migration_id=migration_id,
        stage="FAILED",
        status="failed",
        message="Migration cancelled by user."
    )
    return {"message": "Migration cancellation request accepted."}


@router.get("/api/v1/migrate/{migration_id}/journal")
async def get_migration_journal_v1(migration_id: str):
    validate_migration_id(migration_id)
    from app.services.journal_service import get_journal
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    from app.workspace.manager import get_workspace_path

    status = await redis_client.get(status_key(migration_id))
    workspace_exists = get_workspace_path(migration_id).exists()
    if status is None and not workspace_exists:
        raise HTTPException(status_code=404, detail="Migration not found")

    return await get_journal(migration_id)




