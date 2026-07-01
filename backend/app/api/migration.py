import os
from fastapi import APIRouter, HTTPException
from app.schemas.migration import (
    UploadMigrationRequest,
    PasteMigrationRequest,
    MigrationResponse
)
from app.services.migration_service import initiate_migration

router = APIRouter()

def validate_filename(filename: str) -> None:
    if not filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")
    ext = os.path.splitext(filename)[1]
    if ext.lower() not in (".cu", ".hip", ".cpp", ".cuh", ".h", ".hpp"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Supported extensions: .cu, .hip, .cpp, .cuh, .h, .hpp"
        )

@router.post("/api/v1/migrate/upload", response_model=MigrationResponse, status_code=202)
async def upload_project(request: UploadMigrationRequest):
    validate_filename(request.filename)
    if not request.file:
        raise HTTPException(status_code=400, detail="Uploaded file content cannot be empty")
    
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
    raise HTTPException(status_code=501, detail="not implemented")


@router.get("/api/v1/migrate/{migration_id}/journal")
async def get_migration_journal_v1(migration_id: str):
    from app.services.journal_service import get_journal
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    from app.workspace.manager import get_workspace_path

    status = await redis_client.get(status_key(migration_id))
    workspace_exists = get_workspace_path(migration_id).exists()
    if status is None and not workspace_exists:
        raise HTTPException(status_code=404, detail="Migration not found")

    return await get_journal(migration_id)


@router.get("/migrate/{migration_id}/journal")
async def get_migration_journal_fallback(migration_id: str):
    return await get_migration_journal_v1(migration_id)


from fastapi import WebSocket
from app.websocket.stream import handle_websocket_stream

@router.websocket("/ws/v1/migrate/{migration_id}/stream")
async def websocket_stream(migration_id: str, websocket: WebSocket):
    await handle_websocket_stream(websocket, migration_id)

