from app.workflow_engine.context import WorkflowContext

async def handle_queued(context: WorkflowContext) -> str:
    return "PREPARING"

async def handle_preparing(context: WorkflowContext) -> str:
    return "HIPIFY"

async def handle_hipify(context: WorkflowContext) -> str:
    return "SCA"

async def handle_sca(context: WorkflowContext) -> str:
    return "COMPILING"

async def handle_compiling(context: WorkflowContext) -> str:
    # First time around, compile fails and we transition to ANALYZING to trigger the repair loop.
    # Second time, it goes to RESEARCHING (simulating repair attempt limit reached).
    if context.current_attempt == 0:
        return "ANALYZING"
    else:
        return "RESEARCHING"

async def handle_analyzing(context: WorkflowContext) -> str:
    return "PATCHING"

async def handle_patching(context: WorkflowContext) -> str:
    # Increment attempt to transition path next time COMPILING is reached
    context.current_attempt += 1
    return "COMPILING"

async def handle_researching(context: WorkflowContext) -> str:
    return "GENERATING_REPORT"

async def handle_generating_report(context: WorkflowContext) -> str:
    return "COMPLETED"

async def handle_completed(context: WorkflowContext) -> str:
    return None

async def handle_failed(context: WorkflowContext) -> str:
    return None
