import pytest
import asyncio
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine

@pytest.fixture(autouse=True)
def patch_mock_redis(redis_test_client):
    """Fixture to dynamically patch MockRedis with set/get methods if they are missing."""
    if not hasattr(redis_test_client, "set"):
        async def mock_set(key, value):
            redis_test_client.lists[key] = value
        async def mock_get(key):
            return redis_test_client.lists.get(key)
        redis_test_client.set = mock_set
        redis_test_client.get = mock_get

def test_workflow_engine_traversal(redis_test_client):
    migration_id = "test-migration-id-123"
    workspace_path = "/app/workspace/test-migration-id-123"
    
    context = WorkflowContext(migration_id, workspace_path)
    engine = WorkflowEngine(context)
    
    visited_states = []
    
    # Wrap state handlers to record visited states
    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(ctx):
                visited_states.append(name)
                # Simulate compilation success on the second compile attempt (attempt 1)
                if name == "COMPILING" and ctx.current_attempt == 1:
                    ctx.compilation_success = True
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
        "GENERATING_REPORT",
        "COMPLETED"
    ]
    
    assert visited_states == expected_order
    assert final_state == "COMPLETED"
    assert engine.context.current_state is None
    assert engine.context.current_attempt == 1

    # Verify Redis status key contains "COMPLETED"
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    
    async def check_redis():
        return await redis_client.get(status_key(migration_id))
        
    redis_status = asyncio.run(check_redis())
    assert redis_status == "COMPLETED"

def test_workflow_engine_constructor_parameters():
    migration_id = "param-migration-id"
    workspace_path = "/app/workspace/param"
    redis_manager = "mock-redis"
    
    engine = WorkflowEngine(migration_id, workspace_path, redis_manager)
    assert engine.context.migration_id == migration_id
    assert engine.context.workspace_path == workspace_path
    assert engine.context.redis_manager == redis_manager
    assert engine.context.current_state == "QUEUED"

def test_workflow_engine_failure_exhausted_retries(redis_test_client):
    migration_id = "test-fail-migration-id"
    workspace_path = "/app/workspace/test-fail-migration"
    
    # Set retry budget = 2
    context = WorkflowContext(migration_id, workspace_path, retry_budget=2)
    # Ensure compilation_success is False (meaning it always fails)
    context.compilation_success = False
    
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
        "ANALYZING",
        "PATCHING",
        "COMPILING",
        "RESEARCHING",
        "COMPILING",
        "GENERATING_REPORT",
        "FAILED"
    ]
    
    assert visited_states == expected_order
    assert final_state == "FAILED"
    assert engine.context.current_state is None
    assert engine.context.current_attempt == 2
    
    # Verify Redis status key contains "FAILED"
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    
    async def check_redis():
        return await redis_client.get(status_key(migration_id))
        
    redis_status = asyncio.run(check_redis())
    assert redis_status == "FAILED"
