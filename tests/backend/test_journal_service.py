import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.workflow_engine.context import WorkflowContext
from app.services.journal_service import (
    append_journal_entry,
    get_journal,
    write_state_journal_entry
)
from app.workspace.manager import get_workspace_path, create_workspace, teardown_workspace

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_migration():
    migration_id = "migration_20260701_123456_journaltest"
    create_workspace(migration_id)
    yield migration_id
    teardown_workspace(migration_id)


@pytest.fixture()
def ctx(sample_migration):
    c = WorkflowContext(
        migration_id=sample_migration,
        workspace_path=str(get_workspace_path(sample_migration)),
    )
    c.current_state = "HIPIFY"
    return c


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_append_and_get_journal(sample_migration, redis_test_client):
    """append_journal_entry must write to Redis AND the filesystem workspace."""
    entry = {
        "attempt": 1,
        "timestamp": "2026-07-01T12:00:00Z",
        "workflow_state": "HIPIFY",
        "compiler_result": "N/A"
    }

    # Append entry
    await append_journal_entry(sample_migration, entry)

    # 1. Verify get_journal returns it
    journal = await get_journal(sample_migration)
    assert len(journal) == 1
    assert journal[0]["workflow_state"] == "HIPIFY"
    assert journal[0]["attempt"] == 1

    # 2. Verify it is written to the filesystem reports dir
    workspace_path = get_workspace_path(sample_migration)
    journal_file = workspace_path / "reports" / "migration_journal.json"
    assert journal_file.exists()
    
    with open(journal_file, "r", encoding="utf-8") as f:
        fs_data = json.load(f)
        assert len(fs_data) == 1
        assert fs_data[0]["workflow_state"] == "HIPIFY"


@pytest.mark.anyio
async def test_write_state_journal_entry(ctx, sample_migration, redis_test_client):
    """write_state_journal_entry must map context fields to the schema correctly."""
    ctx.current_state = "COMPILING"
    ctx.compilation_success = False
    ctx.last_compile_stderr = "mock compiler error output"
    ctx.current_attempt = 2

    # Write entry
    await write_state_journal_entry(ctx)

    journal = await get_journal(sample_migration)
    assert len(journal) == 1
    
    entry = journal[0]
    assert entry["attempt"] == 2
    assert entry["workflow_state"] == "COMPILING"
    assert entry["compiler_result"] == "FAILED"
    assert entry["compiler_error_hash"] is not None
    assert len(entry["compiler_error_hash"]) == 64  # SHA-256 hex length
    assert entry["prompt_versions"]["analysis"] == "analysis_v1"


def test_api_get_journal_success(sample_migration, redis_test_client):
    """GET /api/v1/migrate/{id}/journal must return journal entries as JSON list."""
    # Write a mock entry to Redis and filesystem first using event loop
    entry = {
        "attempt": 1,
        "timestamp": "2026-07-01T12:00:00Z",
        "workflow_state": "SCA",
        "compiler_result": "N/A"
    }
    
    # Set status key to simulate a valid active/existing migration
    from app.redis.keys import status_key
    import asyncio
    asyncio.run(redis_test_client.set(status_key(sample_migration), "SCA"))
    asyncio.run(append_journal_entry(sample_migration, entry))

    # Test standard endpoint v1
    path = f"/api/v1/migrate/{sample_migration}/journal"
    response = client.get(path)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["workflow_state"] == "SCA"


def test_api_get_journal_404_not_found(redis_test_client):
    """GET /api/v1/migrate/{id}/journal must return 404 if migration doesn't exist."""
    invalid_id = "migration_nonexistent_12345"
    
    path = f"/api/v1/migrate/{invalid_id}/journal"
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["detail"] == "Migration not found"
