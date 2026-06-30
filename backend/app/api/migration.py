from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class UploadMigrationRequest(BaseModel):
    file: str
    filename: str
    target_gpu_architecture: str
    retry_budget: int
    migration_mode: str

class PasteMigrationRequest(BaseModel):
    code: str
    filename: str
    target_gpu_architecture: str
    retry_budget: int
    migration_mode: str

@router.post("/api/v1/migrate/upload")
async def upload_project(request: UploadMigrationRequest):
    raise HTTPException(status_code=501, detail="not implemented")

@router.post("/api/v1/migrate/paste")
async def paste_code(request: PasteMigrationRequest):
    raise HTTPException(status_code=501, detail="not implemented")

@router.post("/api/v1/migrate/{migration_id}/cancel")
async def cancel_migration(migration_id: str):
    raise HTTPException(status_code=501, detail="not implemented")


from fastapi import WebSocket
from app.websocket.stream import handle_websocket_stream

@router.websocket("/ws/v1/migrate/{migration_id}/stream")
async def websocket_stream(migration_id: str, websocket: WebSocket):
    await handle_websocket_stream(websocket, migration_id)

