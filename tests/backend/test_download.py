import os
import pytest
import zipfile
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app as fastapi_app
import app.redis.client
from app.redis.keys import status_key
from app.workspace.manager import get_workspace_path, create_workspace, teardown_workspace
from app.services.journal_service import _patch_mock_redis

client = TestClient(fastapi_app)


@pytest.fixture()
def mock_migration(redis_test_client):
    _patch_mock_redis()
    migration_id = "migration_20260701_888888_downloadtest"
    create_workspace(migration_id)
    ws_path = get_workspace_path(migration_id)
    
    # Create the zip file inside exports/
    exports_dir = ws_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    zip_path = exports_dir / "HIPForge_Migration.zip"
    
    # Create a dummy zip file
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("test.txt", "dummy content")
        
    yield migration_id
    
    teardown_workspace(migration_id)


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_download_success(mock_migration):
    """GET /api/v1/migrate/{id}/download returns 200 and streams zip if status is COMPLETED."""
    # Set status to COMPLETED
    await app.redis.client.redis_client.set(status_key(mock_migration), "COMPLETED")
    
    # 1. Test standard endpoint
    response = client.get(f"/api/v1/migrate/{mock_migration}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == f'attachment; filename="hipforge-{mock_migration}.zip"'
    assert response.content is not None
    
    # 2. Test fallback endpoint
    response_fallback = client.get(f"/migrate/{mock_migration}/download")
    assert response_fallback.status_code == 200
    assert response_fallback.headers["content-type"] == "application/zip"
    assert response_fallback.headers["content-disposition"] == f'attachment; filename="hipforge-{mock_migration}.zip"'


@pytest.mark.anyio
async def test_download_404_not_completed(mock_migration):
    """GET /api/v1/migrate/{id}/download returns 404 if status is not COMPLETED."""
    # Set status to RUNNING
    await app.redis.client.redis_client.set(status_key(mock_migration), "RUNNING")
    
    response = client.get(f"/api/v1/migrate/{mock_migration}/download")
    assert response.status_code == 404
    assert "not complete" in response.json()["detail"]


@pytest.mark.anyio
async def test_download_404_nonexistent():
    """GET /api/v1/migrate/{id}/download returns 404 if migration doesn't exist."""
    response = client.get("/api/v1/migrate/nonexistent_id_999/download")
    assert response.status_code == 404
