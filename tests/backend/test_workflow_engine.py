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

def test_workflow_engine_immediate_success(redis_test_client):
    migration_id = "test-success-immediate"
    workspace_path = "/app/workspace/test-success-immediate"
    
    context = WorkflowContext(migration_id, workspace_path)
    # Succeed compile immediately
    context.compilation_success = True
    
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
        
    events_received = []
    
    async def run_engine_with_pubsub():
        from app.redis.keys import events_channel
        import json
        
        pubsub = redis_test_client.pubsub()
        await pubsub.subscribe(events_channel(migration_id))
        await asyncio.sleep(0.01)
        
        final_state = await engine.run()
        
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
            if msg is None:
                break
            events_received.append(json.loads(msg["data"]))
            
        await pubsub.aclose()
        return final_state
        
    final_state = asyncio.run(run_engine_with_pubsub())
    
    expected_order = [
        "QUEUED",
        "PREPARING",
        "HIPIFY",
        "SCA",
        "COMPILING",
        "GENERATING_REPORT",
        "COMPLETED"
    ]
    
    assert visited_states == expected_order
    assert final_state == "COMPLETED"
    assert engine.context.current_state is None
    assert engine.context.current_attempt == 0
    
    # Verify Redis status key contains "COMPLETED"
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    
    async def check_redis():
        return await redis_client.get(status_key(migration_id))
        
    redis_status = asyncio.run(check_redis())
    assert redis_status == "COMPLETED"
    
    # 7 states run, 14 events total (started and completed for each)
    assert len(events_received) == 14
    for evt in events_received:
        assert evt["migration_id"] == migration_id
        assert evt["status"] in ("started", "completed")

def test_workflow_engine_retry_recovery(redis_test_client):
    migration_id = "test-retry-recovery"
    workspace_path = "/app/workspace/test-retry-recovery"
    
    # Set retry budget = 3
    context = WorkflowContext(migration_id, workspace_path, retry_budget=3)
    context.compilation_success = False
    
    engine = WorkflowEngine(context)
    visited_states = []
    
    # Wrap state handlers to record visited states
    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(ctx):
                visited_states.append(name)
                # Fail N-1 times (compilation attempts 0 and 1 fail)
                # Succeed on the Nth compile attempt (attempt 2)
                if name == "COMPILING" and ctx.current_attempt == 2:
                    ctx.compilation_success = True
                return await h(ctx)
            return wrapper
        engine.state_registry[state_name] = make_wrapper(handler, state_name)
        
    events_received = []
    
    async def run_engine_with_pubsub():
        from app.redis.keys import events_channel
        import json
        
        pubsub = redis_test_client.pubsub()
        await pubsub.subscribe(events_channel(migration_id))
        await asyncio.sleep(0.01)
        
        final_state = await engine.run()
        
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
            if msg is None:
                break
            events_received.append(json.loads(msg["data"]))
            
        await pubsub.aclose()
        return final_state
        
    final_state = asyncio.run(run_engine_with_pubsub())
    
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
        "GENERATING_REPORT",
        "COMPLETED"
    ]
    
    assert visited_states == expected_order
    assert final_state == "COMPLETED"
    assert engine.context.current_state is None
    assert engine.context.current_attempt == 2
    
    # Verify Redis status key contains "COMPLETED"
    from app.redis.client import redis_client
    from app.redis.keys import status_key
    
    async def check_redis():
        return await redis_client.get(status_key(migration_id))
        
    redis_status = asyncio.run(check_redis())
    assert redis_status == "COMPLETED"
    
    # 13 states run, 26 events total
    assert len(events_received) == 26

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
        
    events_received = []
    
    async def run_engine_with_pubsub():
        from app.redis.keys import events_channel
        import json
        
        pubsub = redis_test_client.pubsub()
        await pubsub.subscribe(events_channel(migration_id))
        await asyncio.sleep(0.01)
        
        final_state = await engine.run()
        
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
            if msg is None:
                break
            events_received.append(json.loads(msg["data"]))
            
        await pubsub.aclose()
        return final_state
        
    final_state = asyncio.run(run_engine_with_pubsub())
    
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

    # 15 states run, 30 events total
    assert len(events_received) == 30
    for evt in events_received:
        assert evt["migration_id"] == migration_id
        assert "timestamp" in evt
        assert "stage" in evt
        assert "status" in evt
        assert "message" in evt

def test_workflow_engine_constructor_parameters():
    migration_id = "param-migration-id"
    workspace_path = "/app/workspace/param"
    redis_manager = "mock-redis"
    
    engine = WorkflowEngine(migration_id, workspace_path, redis_manager)
    assert engine.context.migration_id == migration_id
    assert engine.context.workspace_path == workspace_path
    assert engine.context.redis_manager == redis_manager
    assert engine.context.current_state == "QUEUED"
