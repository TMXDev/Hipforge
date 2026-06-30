import os
import shutil
import datetime
from pathlib import Path
import pytest
from app.workspace.manager import get_workspace_path, create_workspace, teardown_workspace
from app.config.settings import settings

@pytest.fixture
def temp_workspace_env(tmp_path):
    """Fixture to dynamically override WORKSPACE_PATH env var during tests."""
    original_val = os.getenv("WORKSPACE_PATH")
    os.environ["WORKSPACE_PATH"] = str(tmp_path)
    yield tmp_path
    if original_val is not None:
        os.environ["WORKSPACE_PATH"] = original_val
    else:
        os.environ.pop("WORKSPACE_PATH", None)

def test_get_workspace_path_standard(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    expected_path = temp_workspace_env / "2026" / "07" / migration_id
    assert get_workspace_path(migration_id) == expected_path

def test_get_workspace_path_fallback(temp_workspace_env):
    migration_id = "test-id"
    now = datetime.datetime.now(datetime.timezone.utc)
    expected_path = temp_workspace_env / str(now.year) / f"{now.month:02d}" / migration_id
    assert get_workspace_path(migration_id) == expected_path

def test_create_workspace_creates_all_subdirs(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    workspace_path_str = create_workspace(migration_id)
    workspace_path = Path(workspace_path_str)
    
    assert workspace_path.exists()
    assert workspace_path.is_dir()
    
    subdirs = ["input", "generated", "patches", "logs", "artifacts", "reports", "exports"]
    for subdir in subdirs:
        subdir_path = workspace_path / subdir
        assert subdir_path.exists()
        assert subdir_path.is_dir()

def test_teardown_workspace_deletes_directory(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    workspace_path_str = create_workspace(migration_id)
    workspace_path = Path(workspace_path_str)
    
    assert workspace_path.exists()
    
    teardown_workspace(migration_id)
    assert not workspace_path.exists()

def test_teardown_nonexistent_workspace_no_error(temp_workspace_env):
    migration_id = "migration_nonexistent_123"
    # Should not raise any exception
    teardown_workspace(migration_id)
