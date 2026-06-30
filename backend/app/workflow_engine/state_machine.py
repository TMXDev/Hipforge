from app.workflow_engine.context import WorkflowContext
from app.workflow_engine import states

class WorkflowEngine:
    """
    Workflow Engine coordinating state machine transitions for migration jobs.
    """
    def __init__(self, context_or_id, workspace_path: str = None, redis_manager = None):
        if isinstance(context_or_id, WorkflowContext):
            self.context = context_or_id
        else:
            self.context = WorkflowContext(
                migration_id=context_or_id,
                workspace_path=workspace_path,
                redis_manager=redis_manager
            )
            
        self.state_registry = {
            "QUEUED": states.handle_queued,
            "PREPARING": states.handle_preparing,
            "HIPIFY": states.handle_hipify,
            "SCA": states.handle_sca,
            "COMPILING": states.handle_compiling,
            "ANALYZING": states.handle_analyzing,
            "PATCHING": states.handle_patching,
            "RESEARCHING": states.handle_researching,
            "GENERATING_REPORT": states.handle_generating_report,
            "COMPLETED": states.handle_completed,
            "FAILED": states.handle_failed,
        }

    async def run(self) -> str:
        """
        Executes the state machine loop starting from the context's current state
        until a terminal state is reached (next state is None).
        Returns the final non-None state name.
        """
        previous_state = None
        while self.context.current_state is not None:
            state = self.context.current_state
            handler = self.state_registry.get(state)
            if not handler:
                raise ValueError(f"No handler registered for state: {state}")
            
            # Execute handler
            next_state = await handler(self.context)
            
            # Transition
            previous_state = state
            self.context.current_state = next_state
            
        return previous_state
