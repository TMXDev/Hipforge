class WorkflowContext:
    """
    Stores the runtime in-memory state for a migration job execution.
    Passed to all states in the Workflow Engine.
    """
    def __init__(self, migration_id: str, workspace_path: str, redis_manager=None, retry_budget: int = 5):
        self.migration_id = migration_id
        self.workspace_path = workspace_path
        self.redis_manager = redis_manager
        self.retry_budget = retry_budget
        
        # Runtime fields
        self.current_state = "QUEUED"
        self.current_attempt = 0
