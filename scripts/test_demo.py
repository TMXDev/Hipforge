import os
import sys
import base64
import asyncio
import json
import zipfile
from pathlib import Path

# 1. Setup Environment
os.environ["USE_MOCK_COMPILER"] = "true"
os.environ["USE_MOCK_AI"] = "true"
sys.path.insert(0, "backend")

# 2. Setup mock redis
import app.redis.client
import app.redis.manager
import app.redis.publisher
import app.redis.subscriber
from app.main import app as fastapi_app
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine
from app.models.compiler_error import CompilerError
import app.workflow_engine.states
from app.redis.keys import status_key, journal_key, events_channel
from app.workspace.manager import get_workspace_path

class MockRedis:
    def __init__(self):
        self._db = {}
        self._lists = {}
        self._hashes = {}
        self._pubsub_channels = {}

    async def ping(self):
        return True

    async def set(self, key, value):
        self._db[key] = str(value)
        return True

    async def get(self, key):
        return self._db.get(key)

    async def hset(self, key, mapping=None, **kwargs):
        if key not in self._hashes:
            self._hashes[key] = {}
        if mapping:
            self._hashes[key].update(mapping)
        self._hashes[key].update(kwargs)
        return len(mapping or kwargs)

    async def hgetall(self, key):
        return self._hashes.get(key, {})

    async def hget(self, key, field):
        return self._hashes.get(key, {}).get(field)

    async def lpush(self, key, value):
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].insert(0, value)
        return len(self._lists[key])

    async def rpush(self, key, value):
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].append(value)
        return len(self._lists[key])

    async def lrange(self, key, start, end):
        lst = self._lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start:end+1]

    async def brpop(self, key, timeout=0):
        lst = self._lists.get(key, [])
        if not lst:
            if timeout > 0:
                await asyncio.sleep(min(timeout, 0.05))
            return None
        val = self._lists[key].pop()
        return (key, val)

    async def lrem(self, key, count, value):
        if key not in self._lists:
            return 0
        original = len(self._lists[key])
        self._lists[key] = [v for v in self._lists[key] if v != value]
        return original - len(self._lists[key])

    async def publish(self, channel, message):
        subs = self._pubsub_channels.get(channel, [])
        for q in subs:
            await q.put({"type": "message", "channel": channel, "data": message})
        return len(subs)

    def pubsub(self):
        return _MockPubSub(self)

    async def delete(self, *keys):
        for k in keys:
            self._db.pop(k, None)
            self._lists.pop(k, None)
            self._hashes.pop(k, None)

    async def keys(self, pattern):
        import fnmatch
        all_keys = list(self._db) + list(self._lists) + list(self._hashes)
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]

    async def aclose(self):
        pass

class _MockPubSub:
    def __init__(self, client: MockRedis):
        self._client = client
        self._queue = asyncio.Queue()
        self._channels = []

    async def subscribe(self, channel):
        self._channels.append(channel)
        self._client._pubsub_channels.setdefault(channel, []).append(self._queue)

    async def get_message(self, ignore_subscribe_messages=False, timeout=0):
        try:
            if timeout > 0:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return self._queue.get_nowait()
        except (asyncio.QueueEmpty, asyncio.TimeoutError):
            return None

    async def unsubscribe(self, channel=None):
        pass

    async def aclose(self):
        pass

mock_redis_instance = MockRedis()
app.redis.client.redis_client = mock_redis_instance
app.redis.manager.redis_client = mock_redis_instance
app.redis.publisher.redis_client = mock_redis_instance
app.redis.subscriber.redis_client = mock_redis_instance

# 3. Patch compiler function
def _make_mock_handle_compiling(original_handle):
    async def mock_handle_compiling(context: WorkflowContext):
        await original_handle(context)
        # Check if research stage has set researched=True (which MockResearchAgent does)
        # Or check research context
        is_researched = getattr(context, "researched", False) or "ROCm" in getattr(context, "research_context", "")
        if not is_researched:
            context.compilation_success = False
            context.compiler_errors = [
                CompilerError(
                    file=getattr(context, "hipify_output_path", None) or "e2e_sample.hip",
                    line=25,
                    column=5,
                    message="use of undeclared identifier 'hipMalloc_WRONG'",
                    code="E0020",
                )
            ]
        else:
            context.compilation_success = True
            context.compiler_errors = []
    return mock_handle_compiling

original_handle_compiling = app.workflow_engine.states.handle_compiling
mock_compiling = _make_mock_handle_compiling(original_handle_compiling)
app.workflow_engine.states.handle_compiling = mock_compiling

async def listen_to_events(migration_id):
    pubsub = mock_redis_instance.pubsub()
    await pubsub.subscribe(events_channel(migration_id))
    print("\n--- Event Listener Activated ---")
    
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                payload = json.loads(msg["data"])
                print(f"[{payload.get('timestamp')}] {payload.get('stage')} -> {payload.get('status').upper()}: {payload.get('message')}")
                if payload.get("stage") in ("COMPLETED", "FAILED"):
                    print(f"--- Finished Event Listener on State: {payload.get('stage')} ---\n")
                    break
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass

async def run_demo():
    print("==================================================")
    print("       HIPFORGE E2E SIMULATION DEMO START         ")
    print("==================================================")
    
    # Get CUDA file path
    fixture_dir = Path("tests/integration/fixtures")
    cuda_path = fixture_dir / "e2e_sample.cu"
    
    if not cuda_path.exists():
        print(f"Error: Fixture file {cuda_path} does not exist!")
        return

    cuda_source = cuda_path.read_text(encoding="utf-8")
    print(f"Loaded source file: {cuda_path} ({len(cuda_source)} bytes)")

    # Simulate submission endpoint POST /api/v1/migrate/upload
    print("\n[API] Simulating POST /api/v1/migrate/upload...")
    from fastapi.testclient import TestClient
    with TestClient(fastapi_app) as client:
        encoded = base64.b64encode(cuda_source.encode("utf-8")).decode("ascii")
        response = client.post(
            "/api/v1/migrate/upload",
            json={
                "file": encoded,
                "filename": "e2e_sample.cu",
                "target_gpu_architecture": "gfx1100",
                "retry_budget": 2,
                "migration_mode": "file",
            },
        )
        assert response.status_code == 202
        body = response.json()
        migration_id = body["migration_id"]
        print(f"[API] Response status: 202 Accepted. Migration ID: {migration_id}")

    # Start event listener in background task
    listener_task = asyncio.create_task(listen_to_events(migration_id))
    await asyncio.sleep(0.2) # Allow listener to subscribe

    # Run the WorkflowEngine
    print(f"\n[Worker] Initializing Workflow Engine context for job: {migration_id}")
    workspace_path = get_workspace_path(migration_id)
    print(f"[Worker] Workspace derived: {workspace_path}")
    
    context = WorkflowContext(
        migration_id=migration_id,
        workspace_path=str(workspace_path),
        retry_budget=2,
    )
    context.current_state = "QUEUED"
    
    engine = WorkflowEngine(context)
    engine.state_registry["COMPILING"] = mock_compiling

    print("\n[Engine] Starting Workflow execution loop...")
    final_state = await engine.run()
    print(f"[Engine] Workflow Execution finished with terminal state: {final_state}")
    
    # Wait for listener to process final message
    await asyncio.sleep(0.5)
    listener_task.cancel()

    # Validate output package
    zip_path = workspace_path / "exports" / "HIPForge_Migration.zip"
    print("==================================================")
    print("               VERIFYING EXPORTS                  ")
    print("==================================================")
    if zip_path.exists():
        print(f"[SUCCESS] Generated ZIP package found at:\n   {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            print("\nFiles contained in exported ZIP package:")
            for name in zf.namelist():
                print(f"  - {name}")
    else:
        print("[ERROR] ZIP package was not found!")

    # Cleanup workspace
    print("\nCleaning up workspace directory...")
    from app.workspace.manager import teardown_workspace
    teardown_workspace(migration_id)
    print("Workspace cleaned up.")
    print("\n==================================================")
    print("         HIPFORGE DEMO COMPLETED SUCCESSFULLY     ")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_demo())
