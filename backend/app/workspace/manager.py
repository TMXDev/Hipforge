import datetime
import os
import shutil
from pathlib import Path
from app.config.settings import settings

def get_workspace_path(migration_id: str) -> Path:
    """
    Computes the absolute Path for a given migration workspace.
    
    If the migration_id starts with 'migration_' and has a YYYYMMDD date component,
    it will extract the year and month to place the workspace in:
        WORKSPACE_PATH / YYYY / MM / migration_id
        
    Otherwise, it falls back to the current UTC date for the year and month.
    """
    root_path_str = os.getenv("WORKSPACE_PATH") or settings.WORKSPACE_PATH
    root_path = Path(root_path_str)
    
    year = None
    month = None
    
    if migration_id.startswith("migration_"):
        parts = migration_id.split("_")
        if len(parts) >= 2 and len(parts[1]) == 8 and parts[1].isdigit():
            date_part = parts[1]
            year = date_part[:4]
            month = date_part[4:6]
            
    if not year or not month:
        now = datetime.datetime.now(datetime.timezone.utc)
        year = str(now.year)
        month = f"{now.month:02d}"
        
    return root_path / year / month / migration_id

def create_workspace(migration_id: str) -> str:
    """
    Creates the directory tree for a migration workspace, including all required subdirectories:
    input/, generated/, patches/, logs/, artifacts/, reports/, exports/
    
    Returns the absolute path to the workspace root directory as a string.
    """
    workspace_path = get_workspace_path(migration_id)
    
    subdirs = ["input", "generated", "patches", "logs", "artifacts", "reports", "exports"]
    for subdir in subdirs:
        (workspace_path / subdir).mkdir(parents=True, exist_ok=True)
        
    return str(workspace_path.resolve())

def teardown_workspace(migration_id: str) -> None:
    """
    Removes the workspace directory completely.
    No errors are raised if the workspace does not exist.
    """
    workspace_path = get_workspace_path(migration_id)
    if workspace_path.exists():
        shutil.rmtree(workspace_path)

def write_source_file(migration_id: str, filename: str, content: str | bytes) -> str:
    """
    Writes content (string or binary bytes) to a file inside the 'input/' subdirectory of the workspace.
    Returns the absolute path to the written file as a string.
    """
    workspace_path = get_workspace_path(migration_id)
    file_path = workspace_path / "input" / filename
    
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    if isinstance(content, bytes):
        with open(file_path, "wb") as f:
            f.write(content)
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
    return str(file_path.resolve())

def read_file(migration_id: str, relative_path: str) -> str:
    """
    Reads and returns the contents of a file at relative_path (relative to the workspace root).
    """
    workspace_path = get_workspace_path(migration_id)
    file_path = (workspace_path / relative_path).resolve()
    
    if not os.path.normcase(str(file_path)).startswith(os.path.normcase(str(workspace_path.resolve()))):
        raise ValueError("Path traversal attempt detected.")
        
    if not file_path.exists():
        raise FileNotFoundError(f"File not found in workspace: {relative_path}")
        
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def resolve_path(migration_id: str, relative_path: str) -> str:
    """
    Resolves the relative path within the workspace and returns the absolute path as a string.
    Ensures security protection against directory traversal.
    """
    workspace_path = get_workspace_path(migration_id).resolve()
    resolved_path = (workspace_path / relative_path).resolve()
    
    if not os.path.normcase(str(resolved_path)).startswith(os.path.normcase(str(workspace_path))):
        raise ValueError("Path traversal attempt detected.")
        
    return str(resolved_path)

