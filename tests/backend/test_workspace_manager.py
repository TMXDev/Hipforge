import os
import shutil
import datetime
from pathlib import Path
import pytest
from app.workspace.manager import (
    get_workspace_path,
    create_workspace,
    teardown_workspace,
    write_source_file,
    read_file,
    resolve_path
)
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

def test_write_source_file(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    create_workspace(migration_id)
    
    filename = "vector_add.cu"
    content = "__global__ void add() {}"
    
    filepath_str = write_source_file(migration_id, filename, content)
    filepath = Path(filepath_str)
    
    assert filepath.exists()
    assert filepath.is_file()
    assert filepath.parent.name == "input"
    
    with open(filepath, "r", encoding="utf-8") as f:
        assert f.read() == content

def test_read_file(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    create_workspace(migration_id)
    
    # Write a file manually to the workspace
    workspace_path = get_workspace_path(migration_id)
    rel_path = "logs/hipify.log"
    file_path = workspace_path / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    log_content = "Translation success"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(log_content)
        
    read_content = read_file(migration_id, rel_path)
    assert read_content == log_content

def test_read_file_not_found(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    create_workspace(migration_id)
    
    with pytest.raises(FileNotFoundError):
        read_file(migration_id, "logs/nonexistent.log")

def test_resolve_path(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    create_workspace(migration_id)
    
    rel_path = "generated/kernel.hip"
    resolved_path_str = resolve_path(migration_id, rel_path)
    
    expected_path = get_workspace_path(migration_id) / rel_path
    assert resolved_path_str == str(expected_path.resolve())

def test_resolve_path_traversal_prevention(temp_workspace_env):
    migration_id = "migration_20260701_143522_4fd4d857"
    create_workspace(migration_id)
    
    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        resolve_path(migration_id, "../../outside.txt")
        
    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        read_file(migration_id, "../../outside.txt")

