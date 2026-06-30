import pytest
import asyncio
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine

def test_workflow_engine_traversal():
    migration_id = "test-migration-id-123"
    workspace_path = "/app/workspace/test-migration-id-123"
    redis_manager = object()
    
    context = WorkflowContext(migration_id, workspace_path, redis_manager)
    engine = WorkflowEngine(context)
    
    visited_states = []
    
    # Wrap state handlers to record visited states
    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(ctx):
                visited_states.append(name)
                return await h(ctx)
            return wrapper
            
        engine.state_registry[state_name] = make_wrapper(handler, state_name)
        
    async def run_engine():
        return await engine.run()
        
    final_state = asyncio.run(run_engine())
    
    expected_order = [
        "QUEUED",
        "PREPARING",
        "HIPIFY",
        "SCA",
        "COMPILING",
        "ANALYZING",
        "PATCHING",
        "COMPILING",
        "RESEARCHING",
        "GENERATING_REPORT",
        "COMPLETED"
    ]
    
    assert visited_states == expected_order
    assert final_state == "COMPLETED"
    assert engine.context.current_state is None
    assert engine.context.current_attempt == 1

def test_workflow_engine_constructor_parameters():
    migration_id = "param-migration-id"
    workspace_path = "/app/workspace/param"
    redis_manager = "mock-redis"
    
    engine = WorkflowEngine(migration_id, workspace_path, redis_manager)
    assert engine.context.migration_id == migration_id
    assert engine.context.workspace_path == workspace_path
    assert engine.context.redis_manager == redis_manager
    assert engine.context.current_state == "QUEUED"
