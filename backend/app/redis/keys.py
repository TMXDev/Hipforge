def pending_queue_key(migration_id: str = None) -> str:
    """Returns the key for the pending job queue."""
    return "hipforge:queue:pending"

def active_queue_key(migration_id: str = None) -> str:
    """Returns the key for the active job queue."""
    return "hipforge:queue:active"

def status_key(migration_id: str) -> str:
    """Returns the key for the migration job status."""
    return f"migration:{migration_id}:status"

def attempt_key(migration_id: str) -> str:
    """Returns the key for the migration current attempt counter."""
    return f"migration:{migration_id}:attempt"

def retry_budget_key(migration_id: str) -> str:
    """Returns the key for the migration retry budget."""
    return f"migration:{migration_id}:retry_budget"

def compiler_log_key(migration_id: str) -> str:
    """Returns the key for raw compiler logs."""
    return f"migration:{migration_id}:compiler_log"

def analysis_key(migration_id: str) -> str:
    """Returns the key for AI Analysis Agent output."""
    return f"migration:{migration_id}:analysis"

def patch_key(migration_id: str) -> str:
    """Returns the key for AI Patch Agent output."""
    return f"migration:{migration_id}:patch"

def research_key(migration_id: str) -> str:
    """Returns the key for AI Research Agent output."""
    return f"migration:{migration_id}:research"

def journal_key(migration_id: str) -> str:
    """Returns the key for the migration execution journal."""
    return f"migration:{migration_id}:journal"

def metadata_key(migration_id: str) -> str:
    """Returns the key for the migration metadata hash."""
    return f"migration:{migration_id}:metadata"

def events_channel(migration_id: str) -> str:
    """Returns the channel name for migration workflow events."""
    return f"migration:{migration_id}:events"

def compiler_channel(migration_id: str) -> str:
    """Returns the channel name for streaming compiler logs."""
    return f"migration:{migration_id}:compiler"

def agents_channel(migration_id: str) -> str:
    """Returns the channel name for streaming AI agent activity updates."""
    return f"migration:{migration_id}:agents"

