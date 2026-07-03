from app.workflow_engine.context import WorkflowContext

def determine_next_state(current_state: str, success: bool, context: WorkflowContext) -> str:
    """
    Determines the next state of the workflow based on the current state,
    success/failure of the current state, and retry counters in the context.
    """
    if current_state in ("COMPLETED", "FAILED"):
        return None

    if getattr(context, "infrastructure_error", False) and current_state != "GENERATING_REPORT":
        return "GENERATING_REPORT"

    if current_state == "COMPILING" and not success:
        # Check if we already researched (final try)
        if getattr(context, "researched", False):
            return "GENERATING_REPORT"
            
        if context.retry_budget <= 1:
            return "GENERATING_REPORT"
            
        if context.current_attempt + 1 < context.retry_budget:
            return "ANALYZING"
        elif context.current_attempt + 1 == context.retry_budget:
            return "RESEARCHING"
        else:
            return "GENERATING_REPORT"
            
    if current_state == "RESEARCHING":
        context.researched = True
        return "COMPILING"
        
    # Standard successful/normal transitions mapping
    success_transitions = {
        "QUEUED": "PREPARING",
        "PREPARING": "PREFLIGHT",
        "PREFLIGHT": "HIPIFY",
        "HIPIFY": "SCA",
        "SCA": "COMPILING",
        "COMPILING": "GENERATING_REPORT",
        "ANALYZING": "PATCHING",
        "PATCHING": "COMPILING",
        "GENERATING_REPORT": "COMPLETED",  # Default if success
    }
    
    if success:
        if current_state == "GENERATING_REPORT":
            # Check if compilation was ultimately successful
            if getattr(context, "compilation_success", False):
                return "COMPLETED"
            else:
                return "FAILED"
        return success_transitions.get(current_state)
    else:
        # Failure of any non-compiling state aborts to FAILED via report generation
        return "GENERATING_REPORT"
