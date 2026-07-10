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

    if current_state == "HIPIFY" and not success:
        from app.compiler.error_parser import is_recoverable_hipify_error
        import logging
        logger = logging.getLogger("transitions")

        last_stderr = getattr(context, "last_hipify_stderr", "") or context.failure_reason or ""
        retry_budget = max(getattr(context, "retry_budget", 0), 0)
        current_attempt = max(getattr(context, "current_attempt", 0), 0)

        if current_attempt < retry_budget:
            # Check invocation fingerprint to avoid repeated identical failed commands
            current_fp = getattr(context, "current_hipify_fingerprint", None)
            last_failed_fp = getattr(context, "last_failed_hipify_fingerprint", None)
            if current_fp and last_failed_fp and current_fp == last_failed_fp:
                logger.warning("[HIPIFY Retry] Fingerprint matches previous failed run. Rejecting retry to prevent loop.")
                return "GENERATING_REPORT"

            # Save the fingerprint of this failed attempt
            context.last_failed_hipify_fingerprint = current_fp

            if is_recoverable_hipify_error(last_stderr):
                # Recoverable configuration retries directly route to HIPIFY, so they increment attempt here
                context.current_attempt = current_attempt + 1
                logger.info(f"[HIPIFY Retry] Recoverable configuration error. Retrying HIPIFY (attempt {context.current_attempt}/{retry_budget}).")
                return "HIPIFY"
            else:
                # Semantic AI recovery loop increments current_attempt in handle_patching, so we DO NOT increment here
                logger.info(f"[HIPIFY Retry] Non-config/semantic error. Routing to AI analyzer (attempt {current_attempt}/{retry_budget}).")
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
        if current_state == "PATCHING":
            if getattr(context, "failed_stage", None) == "HIPIFY":
                return "HIPIFY"
            return "COMPILING"
        return success_transitions.get(current_state)
    else:
        # Failure of any non-compiling state aborts to FAILED via report generation
        return "GENERATING_REPORT"
