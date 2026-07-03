import os
import json
import pytest
import shutil
import asyncio
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app as fastapi_app
import app.redis.client
from app.redis.keys import status_key, attempt_key, retry_budget_key, metadata_key, journal_key
from app.workspace.manager import get_workspace_path, create_workspace, teardown_workspace
from app.redis.publisher import publish_event

client = TestClient(fastapi_app)

def patch_mock_redis_full(redis_client):
    if not redis_client:
        return
    if not (hasattr(redis_client, "lists") or hasattr(redis_client, "db")):
        return
        
    cls = redis_client.__class__
    db_attr = "lists" if hasattr(redis_client, "lists") else "db"
    
    if not hasattr(cls, "get"):
        async def mock_get(self, key: str):
            db = getattr(self, db_attr)
            val = db.get(key)
            if isinstance(val, list):
                return None
            return val
        cls.get = mock_get
        
    if not hasattr(cls, "set"):
        async def mock_set(self, key: str, value: str):
            db = getattr(self, db_attr)
            db[key] = value
            return True
        cls.set = mock_set
        
    if not hasattr(cls, "hset"):
        async def mock_hset(self, key: str, mapping: dict = None, **kwargs):
            db = getattr(self, db_attr)
            if key not in db:
                db[key] = {}
            if not isinstance(db[key], dict):
                db[key] = {}
            if mapping:
                db[key].update(mapping)
            if kwargs:
                db[key].update(kwargs)
            return len(mapping) if mapping else 0
        cls.hset = mock_hset
        
    if not hasattr(cls, "hgetall"):
        async def mock_hgetall(self, key: str):
            db = getattr(self, db_attr)
            val = db.get(key)
            if isinstance(val, dict):
                return val
            return {}
        cls.hgetall = mock_hgetall
        
    if not hasattr(cls, "rpush"):
        async def mock_rpush(self, key: str, value: str) -> int:
            db = getattr(self, db_attr)
            if key not in db:
                db[key] = []
            if not isinstance(db[key], list):
                db[key] = [db[key]]
            db[key].append(value)
            return len(db[key])
        cls.rpush = mock_rpush
        
    if not hasattr(cls, "llen"):
        async def mock_llen(self, key: str) -> int:
            db = getattr(self, db_attr)
            val = db.get(key)
            if isinstance(val, list):
                return len(val)
            return 0
        cls.llen = mock_llen

@pytest.fixture(autouse=True)
def setup_mock_redis_methods(redis_test_client):
    patch_mock_redis_full(redis_test_client)
    yield

@pytest.fixture()
def mock_migration_id():
    migration_id = "migration_20260701_999999_statustest"
    create_workspace(migration_id)
    yield migration_id
    teardown_workspace(migration_id)

@pytest.mark.anyio
async def test_get_status_not_found():
    response = client.get("/api/v1/migrate/nonexistent-id-xyz/status")
    assert response.status_code == 404
    assert "Migration not found" in response.json()["detail"]

@pytest.mark.anyio
async def test_get_status_queued(redis_test_client, mock_migration_id):
    # Set status key to QUEUED
    await app.redis.client.redis_client.set(status_key(mock_migration_id), "QUEUED")
    # Set metadata
    metadata = {
        "created_at": "2026-07-01T17:00:00Z",
        "current_state": "QUEUED"
    }
    await app.redis.client.redis_client.hset(metadata_key(mock_migration_id), mapping=metadata)
    
    # Request status
    response = client.get(f"/api/v1/migrate/{mock_migration_id}/status")
    assert response.status_code == 200
    
    data = response.json()
    assert data["migration_id"] == mock_migration_id
    assert data["status"] == "QUEUED"
    assert data["stage"] == "QUEUED"
    assert data["created_at"] == "2026-07-01T17:00:00Z"
    assert data["updated_at"] == "2026-07-01T17:00:00Z"

@pytest.mark.anyio
async def test_get_status_running_with_journal(redis_test_client, mock_migration_id):
    # Set status key to QUEUED (or RUNNING) in Redis
    await app.redis.client.redis_client.set(status_key(mock_migration_id), "QUEUED")
    
    # Set metadata
    metadata = {
        "created_at": "2026-07-01T17:00:00Z",
        "current_state": "QUEUED"
    }
    await app.redis.client.redis_client.hset(metadata_key(mock_migration_id), mapping=metadata)
    
    # Append journal entry representing COMPILING stage progress
    journal_entry = {
        "attempt": 1,
        "timestamp": "2026-07-01T17:02:15Z",
        "workflow_state": "COMPILING"
    }
    await app.redis.client.redis_client.rpush(journal_key(mock_migration_id), json.dumps(journal_entry))
    
    # Request status
    response = client.get(f"/api/v1/migrate/{mock_migration_id}/status")
    assert response.status_code == 200
    
    data = response.json()
    assert data["migration_id"] == mock_migration_id
    # Should resolve status to RUNNING because there is journal progress
    assert data["status"] == "RUNNING"
    assert data["stage"] == "COMPILING"
    assert data["created_at"] == "2026-07-01T17:00:00Z"
    # Should take updated_at from the latest journal entry timestamp
    assert data["updated_at"] == "2026-07-01T17:02:15Z"

@pytest.mark.anyio
async def test_get_status_completed(redis_test_client, mock_migration_id):
    # Set status key to COMPLETED in Redis
    await app.redis.client.redis_client.set(status_key(mock_migration_id), "COMPLETED")
    
    metadata = {
        "created_at": "2026-07-01T17:00:00Z",
        "current_state": "COMPLETED"
    }
    await app.redis.client.redis_client.hset(metadata_key(mock_migration_id), mapping=metadata)
    
    # Request status
    response = client.get(f"/api/v1/migrate/{mock_migration_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["migration_id"] == mock_migration_id
    assert data["status"] == "COMPLETED"
    assert data["stage"] == "COMPLETED"

@pytest.mark.anyio
async def test_websocket_stream_events(redis_test_client):
    migration_id = "test-ws-migration-123"
    
    # Synchronous function executing inside worker thread
    def run_websocket_client():
        print("\n[Client] Connecting to websocket...")
        with client.websocket_connect(f"/ws/v1/migrate/{migration_id}/stream") as ws:
            print("[Client] Connected! Waiting for handshake...")
            # Receive initial connection message
            conn_msg = ws.receive_json()
            print(f"[Client] Received handshake: {conn_msg}")
            assert conn_msg["type"] == "connected"
            assert conn_msg["migration_id"] == migration_id
            
            # Receive 10 stages
            stages_received = []
            for i in range(10):
                print(f"[Client] Waiting for stage {i+1}...")
                msg = ws.receive_json()
                print(f"[Client] Received stage {i+1}: {msg}")
                assert msg["type"] == "event"
                stages_received.append(msg["stage"])
                
            return stages_received

    # Start the sync client thread
    import anyio
    client_future = asyncio.create_task(anyio.to_thread.run_sync(run_websocket_client))
    
    # Wait for the client to connect and subscribe
    print("[Test] Waiting for client to connect and subscribe...")
    from app.redis.keys import events_channel
    channel = events_channel(migration_id)
    print(f"[Test] Target channel: {channel}")
    print(f"[Test] Before loop, pubsub_channels keys: {list(getattr(redis_test_client, 'pubsub_channels', {}).keys())}")
    for i in range(100):
        if hasattr(redis_test_client, "pubsub_channels"):
            if channel in redis_test_client.pubsub_channels:
                print(f"[Test] Found channel in pubsub_channels after {i} iterations!")
                break
        else:
            from app.websocket.manager import manager
            if migration_id in manager.active_connections:
                print(f"[Test] Found migration in active_connections after {i} iterations!")
                break
        await asyncio.sleep(0.05)
    
    print("[Test] Connection established! Publishing stages...")
    
    expected_stages = [
        "QUEUED", "PREPARING", "PREFLIGHT", "HIPIFY", "SCA", "COMPILING",
        "ANALYZING", "PATCHING", "RESEARCHING", "GENERATING_REPORT", "COMPLETED"
    ]
    
    # Publish all lifecycle stages
    for stage in expected_stages:
        print(f"[Test] Publishing stage {stage}...")
        await publish_event(
            migration_id=migration_id,
            stage=stage,
            status="completed" if stage == "COMPLETED" else "started",
            message=f"Stage {stage} transitioned successfully"
        )
        await asyncio.sleep(0.1)
        
    # Await the test results from thread
    print("[Test] Awaiting client thread future...")
    try:
        stages_received = await asyncio.wait_for(client_future, timeout=5.0)
        print(f"[Test] Client thread finished. Stages: {stages_received}")
        assert stages_received == expected_stages
    except asyncio.TimeoutError:
        print("[Test] TIMEOUT waiting for client thread future!")
        raise

