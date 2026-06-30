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


# Aliases with 'get_' prefix to support alternative import preferences
get_pending_queue_key = pending_queue_key
get_active_queue_key = active_queue_key
get_status_key = status_key
get_attempt_key = attempt_key
get_retry_budget_key = retry_budget_key
get_compiler_log_key = compiler_log_key
get_analysis_key = analysis_key
get_patch_key = patch_key
get_research_key = research_key
get_journal_key = journal_key
get_metadata_key = metadata_key
get_events_channel = events_channel
get_compiler_channel = compiler_channel
get_agents_channel = agents_channel
