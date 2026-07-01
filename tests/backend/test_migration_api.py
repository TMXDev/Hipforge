import os
import json
import pytest
import shutil
import base64
import time
import asyncio
import threading
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app as fastapi_app
import app.redis.client
from app.redis.keys import status_key, attempt_key, retry_budget_key, metadata_key
from app.workspace.manager import get_workspace_path
from app.redis.manager import dequeue_job
from app.workers.migration_worker import run_worker
import app.workers.migration_worker

client = TestClient(fastapi_app)

def patch_mock_redis_full(redis_client):
    if not redis_client:
        return
    # Check if it is a MockRedis instance
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

@pytest.fixture(autouse=True)
def setup_mock_redis_methods(redis_test_client):
    patch_mock_redis_full(redis_test_client)
    yield

@pytest.fixture(autouse=True)
def cleanup_workspaces():
    yield
    # Cleanup any generated test workspaces
    root_path = Path("workspace")
    if root_path.exists():
        for year_dir in root_path.iterdir():
            if year_dir.is_dir():
                shutil.rmtree(year_dir)

@pytest.mark.anyio
async def test_paste_migration_success(redis_test_client):
    # 1. Post code to the API
    payload = {
        "code": "__global__ void kernel() {}",
        "filename": "kernel.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 3,
        "migration_mode": "standard"
    }
    
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 202
    
    data = response.json()
    assert "migration_id" in data
    assert data["status"] == "initializing"
    assert data["message"] == "Migration initiated successfully."
    
    migration_id = data["migration_id"]
    
    # 2. Verify status key in Redis
    status = await app.redis.client.redis_client.get(status_key(migration_id))
    assert status == "QUEUED"
    
    # 3. Verify attempt and retry budget keys
    attempt = await app.redis.client.redis_client.get(attempt_key(migration_id))
    assert attempt == "0"
    retry_budget = await app.redis.client.redis_client.get(retry_budget_key(migration_id))
    assert retry_budget == "3"
    
    # 4. Verify metadata
    metadata = await app.redis.client.redis_client.hgetall(metadata_key(migration_id))
    assert metadata["project_name"] == "kernel.cu"
    assert metadata["current_state"] == "QUEUED"
    assert metadata["compiler"] == "hipcc"
    assert metadata["target_architecture"] == "gfx90a"
    
    # 5. Verify file written in workspace input directory
    ws_path = get_workspace_path(migration_id)
    input_file = ws_path / "input" / "kernel.cu"
    assert input_file.exists()
    assert input_file.read_text() == "__global__ void kernel() {}"
    
    # 6. Dequeue the job and verify payload matches
    job = await dequeue_job()
    assert job is not None
    job_id, job_payload = job
    assert job_id == migration_id
    assert job_payload["workspace_path"] == str(ws_path.resolve())
    assert job_payload["retry_budget"] == 3

@pytest.mark.anyio
async def test_upload_migration_success(redis_test_client):
    # 1. Base64 encode the code
    code_bytes = b"__global__ void kernel() {}"
    encoded_file = base64.b64encode(code_bytes).decode("utf-8")
    
    payload = {
        "file": encoded_file,
        "filename": "kernel.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 2,
        "migration_mode": "standard"
    }
    
    response = client.post("/api/v1/migrate/upload", json=payload)
    assert response.status_code == 202
    
    data = response.json()
    migration_id = data["migration_id"]
    
    # 2. Dequeue and verify
    job = await dequeue_job()
    assert job is not None
    job_id, job_payload = job
    assert job_id == migration_id
    
    ws_path = get_workspace_path(migration_id)
    input_file = ws_path / "input" / "kernel.cu"
    assert input_file.exists()
    assert input_file.read_text() == "__global__ void kernel() {}"

@pytest.mark.anyio
async def test_migration_invalid_file_type():
    payload = {
        "code": "__global__ void kernel() {}",
        "filename": "kernel.txt",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 3,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]

@pytest.mark.anyio
async def test_migration_empty_content():
    payload = {
        "code": "",
        "filename": "kernel.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 3,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "content cannot be empty" in response.json()["detail"]

@pytest.mark.anyio
async def test_migration_api_to_worker_integration(redis_test_client):
    # Configure fast timeout check for the worker loop
    os.environ["MIGRATION_WORKER_TIMEOUT"] = "1"
    
    # Start worker loop in a background thread
    worker_loop = asyncio.new_event_loop()
    def worker_target():
        asyncio.set_event_loop(worker_loop)
        worker_loop.run_until_complete(run_worker())
        
    thread = threading.Thread(target=worker_target, daemon=True)
    app.workers.migration_worker.running = True
    thread.start()
    
    try:
        # Submit job via API with 'test-' prefix so that state machine uses stub handlers
        payload = {
            "code": "__global__ void kernel() {}",
            "filename": "test-api-kernel.cu",
            "target_gpu_architecture": "gfx90a",
            "retry_budget": 1,
            "migration_mode": "standard"
        }
        response = client.post("/api/v1/migrate/paste", json=payload)
        assert response.status_code == 202
        migration_id = response.json()["migration_id"]
        
        # Wait for the job status to transition to COMPLETED (with timeout)
        timeout = 5.0
        start_time = time.time()
        completed = False
        
        while time.time() - start_time < timeout:
            status = await app.redis.client.redis_client.get(status_key(migration_id))
            if status == "COMPLETED":
                completed = True
                break
            await asyncio.sleep(0.1)
            
        assert completed, f"Job failed to reach COMPLETED state. Last status: {await app.redis.client.redis_client.get(status_key(migration_id))}"
    
    finally:
        # Graceful shutdown of the worker thread
        app.workers.migration_worker.running = False
        worker_loop.call_soon_threadsafe(worker_loop.stop)
        thread.join(timeout=2.0)
        if "MIGRATION_WORKER_TIMEOUT" in os.environ:
            del os.environ["MIGRATION_WORKER_TIMEOUT"]
