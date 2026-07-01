import json
from fastapi import APIRouter, HTTPException, WebSocket
from app.schemas.migration import MigrationStatusResponse
import app.redis.client
from app.redis.keys import status_key, metadata_key, journal_key
from app.websocket.stream import handle_websocket_stream
from app.api.security_utils import validate_migration_id

router = APIRouter()

async def get_status_logic(migration_id: str) -> MigrationStatusResponse:
    validate_migration_id(migration_id)
    # 1. Fetch status key
    s_key = status_key(migration_id)
    redis_status = await app.redis.client.redis_client.get(s_key)
    
    # 2. Fetch metadata
    m_key = metadata_key(migration_id)
    metadata = await app.redis.client.redis_client.hgetall(m_key)
    
    # 3. Raise 404 if both status and metadata do not exist in Redis
    if not redis_status and not metadata:
        raise HTTPException(status_code=404, detail="Migration not found")
        
    status = redis_status or "QUEUED"
    stage = status
    created_at = metadata.get("created_at") or ""
    updated_at = created_at
    
    # 4. Read latest journal entry for stage & updated_at overrides
    j_key = journal_key(migration_id)
    try:
        last_journal_list = await app.redis.client.redis_client.lrange(j_key, -1, -1)
        if last_journal_list:
            last_entry = json.loads(last_journal_list[0])
            stage = last_entry.get("workflow_state", stage)
            updated_at = last_entry.get("timestamp", updated_at)
            
            # If status in Redis is QUEUED but we have journal entries, the job is RUNNING
            if status == "QUEUED":
                status = "RUNNING"
    except Exception:
        pass
        
    return MigrationStatusResponse(
        migration_id=migration_id,
        status=status,
        stage=stage,
        created_at=created_at,
        updated_at=updated_at
    )

@router.get("/api/v1/migrate/{migration_id}/status", response_model=MigrationStatusResponse)
async def get_migration_status_v1(migration_id: str):
    return await get_status_logic(migration_id)

@router.get("/api/v1/migrate/{migration_id}", response_model=MigrationStatusResponse)
async def get_migration_status_v1_short(migration_id: str):
    return await get_status_logic(migration_id)

@router.get("/migrate/{migration_id}/status", response_model=MigrationStatusResponse)
async def get_migration_status_fallback(migration_id: str):
    return await get_status_logic(migration_id)

@router.get("/migrate/{migration_id}", response_model=MigrationStatusResponse)
async def get_migration_status_fallback_short(migration_id: str):
    return await get_status_logic(migration_id)

@router.get("/ws/v1/migrate/{migration_id}/stream")
async def websocket_stream_http_fallback(migration_id: str):
    validate_migration_id(migration_id)
    raise HTTPException(status_code=400, detail="WebSocket protocol required")

@router.websocket("/ws/v1/migrate/{migration_id}/stream")
async def websocket_stream(migration_id: str, websocket: WebSocket):
    validate_migration_id(migration_id)
    await handle_websocket_stream(websocket, migration_id)

