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
        retry_budget = max(getattr(context, "retry_budget", 0), 0)
        current_attempt = max(getattr(context, "current_attempt", 0), 0)

        if current_attempt < retry_budget:
            return "ANALYZING"

        return "GENERATING_REPORT"

    # ponytail: confidence-based research trigger — if the analysis agent
    # is unsure and we've burned 2+ attempts, consult research before
    # wasting another patch. upgrade path: make threshold configurable
    if current_state == "ANALYZING" and success:
        analysis = getattr(context, "analysis_result", None) or {}
        confidence = analysis.get("confidence", 1.0)
        attempt = max(getattr(context, "current_attempt", 0), 0)
        already_researched = getattr(context, "researched", False)
        if confidence < 0.5 and attempt >= 2 and not already_researched:
            return "RESEARCHING"
            
    if current_state == "RESEARCHING":
        context.researched = True
        return "GENERATING_REPORT"
        
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
