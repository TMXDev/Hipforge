from app.workflow_engine.context import WorkflowContext
from app.workflow_engine import states
from app.workflow_engine.transitions import determine_next_state
from app.redis.publisher import publish_event

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
            
            # Intercept COMPLETED and FAILED states to execute Redis operations
            if state == "COMPLETED":
                from app.redis.client import redis_client
                from app.redis.keys import status_key
                await redis_client.set(status_key(self.context.migration_id), "COMPLETED")
                
            elif state == "FAILED":
                from app.redis.client import redis_client
                from app.redis.keys import status_key
                await redis_client.set(status_key(self.context.migration_id), "FAILED")
                
            handler = self.state_registry.get(state)
            if not handler:
                raise ValueError(f"No handler registered for state: {state}")
                
            # Publish started event before calling the handler
            await publish_event(
                migration_id=self.context.migration_id,
                stage=state,
                status="started",
                message=f"Starting stage {state}..."
            )
            
            try:
                # Call state handler to run its stub side effects (like patching incrementing attempts)
                await handler(self.context)
                
                if state == "COMPILING":
                    success = getattr(self.context, "compilation_success", False)
                else:
                    success = True
                error_msg = "State execution failed."
            except Exception as e:
                success = False
                error_msg = str(e)
                
            if success:
                # Publish completed event after each state succeeds
                await publish_event(
                    migration_id=self.context.migration_id,
                    stage=state,
                    status="completed",
                    message=f"Completed stage {state} successfully."
                )
            else:
                # Publish failed event with error message on failure
                await publish_event(
                    migration_id=self.context.migration_id,
                    stage=state,
                    status="failed",
                    message=f"Stage {state} failed: {error_msg}"
                )
                
            next_state = determine_next_state(state, success, self.context)
            
            previous_state = state
            self.context.current_state = next_state
            
        return previous_state


