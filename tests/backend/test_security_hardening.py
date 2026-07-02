import base64
import io
import zipfile
import pytest
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app as fastapi_app
from app.config.settings import settings
import app.redis.client

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

def test_secure_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "no-referrer-when-downgrade"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]

def test_upload_invalid_file_size():
    original_limit = settings.WORKSPACE_SIZE_LIMIT
    settings.WORKSPACE_SIZE_LIMIT = "10KB"
    try:
        # 11KB of data
        large_data = base64.b64encode(b"a" * 11264).decode("utf-8")
        payload = {
            "file": large_data,
            "filename": "test.cu",
            "target_gpu_architecture": "gfx90a",
            "retry_budget": 5,
            "migration_mode": "standard"
        }
        response = client.post("/api/v1/migrate/upload", json=payload)
        assert response.status_code == 400
        assert "exceeds limit" in response.json()["detail"]
    finally:
        settings.WORKSPACE_SIZE_LIMIT = original_limit

def test_paste_invalid_file_size():
    original_limit = settings.WORKSPACE_SIZE_LIMIT
    settings.WORKSPACE_SIZE_LIMIT = "10KB"
    try:
        # 11KB of data
        large_code = "a" * 11264
        payload = {
            "code": large_code,
            "filename": "test.cu",
            "target_gpu_architecture": "gfx90a",
            "retry_budget": 5,
            "migration_mode": "standard"
        }
        response = client.post("/api/v1/migrate/paste", json=payload)
        assert response.status_code == 400
        assert "exceeds limit" in response.json()["detail"]
    finally:
        settings.WORKSPACE_SIZE_LIMIT = original_limit

def test_null_bytes_rejection():
    # Null byte in pasted code
    payload = {
        "code": "int main() { \x00 return 0; }",
        "filename": "test.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "Null bytes" in response.json()["detail"]

    # Null byte in file content
    encoded_null = base64.b64encode(b"code with \x00 null").decode("utf-8")
    payload = {
        "file": encoded_null,
        "filename": "test.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/upload", json=payload)
    assert response.status_code == 400
    assert "Null bytes" in response.json()["detail"]

    # Null byte in filename
    payload = {
        "code": "int main() { return 0; }",
        "filename": "test\x00.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "Null bytes" in response.json()["detail"]

def test_invalid_parameters():
    # Bad arch with semicolons
    payload = {
        "code": "int main() {}",
        "filename": "test.cu",
        "target_gpu_architecture": "gfx90a; rm -rf /",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "Invalid target GPU architecture" in response.json()["detail"]

    # Bad mode
    payload = {
        "code": "int main() {}",
        "filename": "test.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard; inject"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "Invalid migration mode" in response.json()["detail"]

    # Bad retry budget
    payload = {
        "code": "int main() {}",
        "filename": "test.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 25,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/paste", json=payload)
    assert response.status_code == 400
    assert "Retry budget must be between" in response.json()["detail"]

def test_invalid_migration_id():
    response = client.get("/api/v1/migrate/test-id-with-../status")
    assert response.status_code == 400
    assert "Invalid migration ID format" in response.json()["detail"]

    response = client.get("/api/v1/migrate/id;inject/download")
    assert response.status_code == 400
    assert "Invalid migration ID format" in response.json()["detail"]

def test_zip_integrity_and_traversal():
    # 1. Invalid/corrupted zip file
    payload = {
        "file": base64.b64encode(b"not a zip file").decode("utf-8"),
        "filename": "test.zip",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/upload", json=payload)
    assert response.status_code == 400
    assert "Invalid zip archive" in response.json()["detail"]

    # 2. Zip file with path traversal entry
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../outside.txt", "insecure content")
    payload = {
        "file": base64.b64encode(zip_buffer.getvalue()).decode("utf-8"),
        "filename": "test.zip",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/upload", json=payload)
    assert response.status_code == 400
    assert "Path traversal" in response.json()["detail"]

    # 3. Zip file with absolute path entry
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("/etc/passwd", "insecure content")
    payload = {
        "file": base64.b64encode(zip_buffer.getvalue()).decode("utf-8"),
        "filename": "test.zip",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 5,
        "migration_mode": "standard"
    }
    response = client.post("/api/v1/migrate/upload", json=payload)
    assert response.status_code == 400
    assert "Absolute path or invalid path prefix" in response.json()["detail"]

def test_settings_validation_error():
    from app.config.settings import Settings
    s = Settings()
    s.USE_MOCK_AI = False
    s.FIREWORKS_API_KEY = "your_fireworks_api_key"
    with pytest.raises(ValueError, match="FIREWORKS_API_KEY must be set"):
        s.validate()
