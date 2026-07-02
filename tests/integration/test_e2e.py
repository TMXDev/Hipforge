"""
tests/integration/test_e2e.py

Full end-to-end integration test for HIPForge.

Scenario
--------
1. Submit a CUDA file via POST /api/v1/migrate/upload (FastAPI TestClient).
2. Run the WorkflowEngine inline with mocked compiler & AI services.
3. Assert the job reaches COMPLETED state.
4. Assert all 10 canonical states were traversed.
5. Assert the Migration Journal has entries for each processing state.
6. Assert the download ZIP contains the required report files and translated source.

Mode: pre-hackathon (USE_MOCK_COMPILER=true, USE_MOCK_AI=true)
"""

import os
import sys
import base64
import asyncio
import zipfile
import shutil
from pathlib import Path
from typing import List

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Environment — must be set BEFORE any backend module is imported
# ---------------------------------------------------------------------------
os.environ["USE_MOCK_COMPILER"] = "true"
os.environ["USE_MOCK_AI"] = "true"

sys.path.insert(0, "backend")

# ---------------------------------------------------------------------------
# Backend imports (after env vars are set)
# ---------------------------------------------------------------------------
import app.redis.client
import app.redis.manager
import app.redis.publisher
import app.redis.subscriber
from app.main import app as fastapi_app
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine
from app.models.compiler_error import CompilerError
import app.workflow_engine.states
from app.redis.keys import status_key, journal_key
from app.workspace.manager import get_workspace_path


# ---------------------------------------------------------------------------
# FIXTURE: Path to the E2E CUDA source file
# ---------------------------------------------------------------------------
FIXTURE_DIR = Path(__file__).parent / "fixtures"
E2E_CUDA_FILE = FIXTURE_DIR / "e2e_sample.cu"


# ---------------------------------------------------------------------------
# MockRedis — in-memory Redis simulation
# ---------------------------------------------------------------------------
class MockRedis:
    """Full in-memory Redis mock supporting all operations used in E2E flow."""

    def __init__(self):
        self._db: dict = {}
        self._lists: dict = {}
        self._hashes: dict = {}
        self._pubsub_channels: dict = {}

    async def ping(self):
        return True

    # ----- String ops -----
    async def set(self, key, value):
        self._db[key] = str(value)
        return True

    async def get(self, key):
        return self._db.get(key)

    # ----- Hash ops -----
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

    # ----- List ops -----
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
        return lst[start:end + 1]

    async def brpop(self, key, timeout=0):
        lst = self._lists.get(key, [])
        if not lst:
            if timeout > 0:
                await asyncio.sleep(min(timeout, 0.01))
            return None
        val = self._lists[key].pop()
        return (key, val)

    async def lrem(self, key, count, value):
        if key not in self._lists:
            return 0
        original = len(self._lists[key])
        self._lists[key] = [v for v in self._lists[key] if v != value]
        return original - len(self._lists[key])

    # ----- Pub/Sub ops -----
    async def publish(self, channel, message):
        subs = self._pubsub_channels.get(channel, [])
        for q in subs:
            await q.put({"type": "message", "channel": channel, "data": message})
        return len(subs)

    def pubsub(self):
        return _MockPubSub(self)

    # ----- Cleanup -----
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
        self._queue: asyncio.Queue = asyncio.Queue()
        self._channels: List[str] = []

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_redis():
    """Replace all backend Redis clients with MockRedis for the duration of each test."""
    mock = MockRedis()

    originals = {
        "client": app.redis.client.redis_client,
        "manager": app.redis.manager.redis_client,
        "publisher": app.redis.publisher.redis_client,
        "subscriber": app.redis.subscriber.redis_client,
    }

    app.redis.client.redis_client = mock
    app.redis.manager.redis_client = mock
    app.redis.publisher.redis_client = mock
    app.redis.subscriber.redis_client = mock

    yield mock

    app.redis.client.redis_client = originals["client"]
    app.redis.manager.redis_client = originals["manager"]
    app.redis.publisher.redis_client = originals["publisher"]
    app.redis.subscriber.redis_client = originals["subscriber"]


@pytest.fixture()
def http_client():
    """FastAPI TestClient wrapping the real application."""
    with TestClient(fastapi_app) as client:
        yield client


@pytest.fixture()
def cuda_source() -> str:
    """Reads the E2E CUDA fixture and returns its content as a string."""
    assert E2E_CUDA_FILE.exists(), (
        f"E2E CUDA fixture not found at {E2E_CUDA_FILE}. "
        "Create tests/integration/fixtures/e2e_sample.cu"
    )
    return E2E_CUDA_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ALL_10_STATES = [
    "QUEUED",
    "PREPARING",
    "HIPIFY",
    "SCA",
    "COMPILING",
    "ANALYZING",
    "PATCHING",
    "RESEARCHING",
    "GENERATING_REPORT",
    "COMPLETED",
]


def _make_mock_handle_compiling(original_handle):
    """
    Returns a mock handle_compiling that:
    - Fails compilation until context.researched is True
    - Sets structured errors for the analysis/patching chain
    - Succeeds after RESEARCHING stage completes
    """
    async def mock_handle_compiling(context: WorkflowContext):
        await original_handle(context)
        if not getattr(context, "researched", False):
            context.compilation_success = False
            if not getattr(context, "compiler_errors", None):
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


# ---------------------------------------------------------------------------
# End-to-End Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_e2e_migration(http_client, cuda_source, mock_redis, tmp_path):
    """
    Full end-to-end integration test for HIPForge.

    Step 1 — Submit CUDA file via POST /api/v1/migrate/upload.
    Step 2 — Run WorkflowEngine inline (mocked compiler & AI).
    Step 3 — Assert COMPLETED state.
    Step 4 — Assert all 10 states traversed.
    Step 5 — Assert journal entries cover all processing states.
    Step 6 — Assert ZIP package contains required files.
    """

    # ── STEP 1: Submit via HTTP ──────────────────────────────────────────────
    # Encode source file as base64 (as the upload endpoint expects)
    encoded = base64.b64encode(cuda_source.encode("utf-8")).decode("ascii")

    response = http_client.post(
        "/api/v1/migrate/upload",
        json={
            "file": encoded,
            "filename": "e2e_sample.cu",
            "target_gpu_architecture": "gfx1100",
            "retry_budget": 1,
            "migration_mode": "file",
        },
    )

    # Assertion 1: HTTP 202 Accepted
    assert response.status_code == 202, (
        f"Expected 202, got {response.status_code}: {response.text}"
    )

    body = response.json()

    # Assertion 2: Response contains migration_id
    assert "migration_id" in body, f"Response missing migration_id: {body}"
    migration_id: str = body["migration_id"]
    assert migration_id, "migration_id must not be empty"

    # ── STEP 2: Run WorkflowEngine inline ───────────────────────────────────
    # Get the workspace path created during upload
    workspace_path = get_workspace_path(migration_id)
    assert workspace_path.exists(), (
        f"Workspace not created at {workspace_path}"
    )

    # Build context using the real migration_id so state_machine uses real handlers
    context = WorkflowContext(
        migration_id=migration_id,
        workspace_path=str(workspace_path),
        retry_budget=1,
    )
    context.current_state = "QUEUED"

    # Patch handle_compiling to drive the full repair loop
    original_handle_compiling = app.workflow_engine.states.handle_compiling
    mock_compiling = _make_mock_handle_compiling(original_handle_compiling)
    app.workflow_engine.states.handle_compiling = mock_compiling

    # Build engine and wrap state registry to record visited states
    engine = WorkflowEngine(context)
    engine.state_registry["COMPILING"] = mock_compiling
    visited_states: List[str] = []

    for state_name, handler in list(engine.state_registry.items()):
        def _make_wrapper(h, name):
            async def _wrapper(ctx):
                visited_states.append(name)
                return await h(ctx)
            return _wrapper
        engine.state_registry[state_name] = _make_wrapper(handler, state_name)

    try:
        final_state = await engine.run()
    finally:
        app.workflow_engine.states.handle_compiling = original_handle_compiling

    # ── STEP 3: Assert COMPLETED state ──────────────────────────────────────
    redis_status = await mock_redis.get(status_key(migration_id))

    # Assertion 3: Final state is COMPLETED
    assert final_state == "COMPLETED", (
        f"Expected COMPLETED, got {final_state}. Visited: {visited_states}"
    )

    # Assertion 4: Redis status key is COMPLETED
    assert redis_status == "COMPLETED", (
        f"Expected Redis status COMPLETED, got {redis_status!r}"
    )

    # ── STEP 4: Assert all 10 states traversed ───────────────────────────────
    visited_unique = set(visited_states)

    # Assertion 5: All 10 canonical states appear in visited list
    for state in ALL_10_STATES:
        assert state in visited_unique, (
            f"State {state!r} was never visited. Visited states: {sorted(visited_unique)}"
        )

    # Assertion 6: COMPILING visited >= 3 times (initial fail, patch fail, final success)
    compiling_count = visited_states.count("COMPILING")
    assert compiling_count >= 3, (
        f"COMPILING should appear at least 3× (initial, post-patch, final), "
        f"but appeared {compiling_count}× in: {visited_states}"
    )

    # Assertion 7: COMPLETED is the final state in the visited list
    assert visited_states[-1] == "COMPLETED", (
        f"Last visited state should be COMPLETED, got {visited_states[-1]!r}"
    )

    # ── STEP 5: Assert Migration Journal ────────────────────────────────────
    # Fetch journal entries from Redis (written by write_state_journal_entry)
    j_key = journal_key(migration_id)
    raw_journal = await mock_redis.lrange(j_key, 0, -1)

    # Assertion 8: Journal has at least one entry
    assert len(raw_journal) >= 1, (
        "Migration Journal must have at least one entry"
    )

    import json
    journal_entries = [json.loads(e) for e in raw_journal]

    # Collect the set of workflow_state values recorded in the journal
    journal_states = {e.get("workflow_state", "") for e in journal_entries}

    # States that must appear in the journal (all states that execute handlers)
    EXPECTED_JOURNAL_STATES = {
        "COMPILING",
        "ANALYZING",
        "PATCHING",
        "RESEARCHING",
        "GENERATING_REPORT",
        "COMPLETED",
    }

    # Assertion 9: All expected states have at least one journal entry
    for state in EXPECTED_JOURNAL_STATES:
        assert state in journal_states, (
            f"Journal missing entry for state {state!r}. "
            f"Journal states present: {sorted(journal_states)}"
        )

    # Assertion 10: Each journal entry has required fields
    for entry in journal_entries:
        assert "attempt" in entry, f"Journal entry missing 'attempt': {entry}"
        assert "timestamp" in entry, f"Journal entry missing 'timestamp': {entry}"
        assert "workflow_state" in entry, f"Journal entry missing 'workflow_state': {entry}"
        assert "compiler_result" in entry, f"Journal entry missing 'compiler_result': {entry}"

    # ── STEP 6: Assert ZIP package ──────────────────────────────────────────
    zip_path = workspace_path / "exports" / "HIPForge_Migration.zip"

    # Assertion 11: ZIP file was created
    assert zip_path.exists(), (
        f"ZIP archive not found at {zip_path}. "
        "Ensure GENERATING_REPORT state creates the exports/ ZIP."
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        names_in_zip = zf.namelist()
        names_set = set(names_in_zip)

    # Assertion 12: ZIP contains Markdown report
    assert any("migration_report.md" in n for n in names_set), (
        f"ZIP missing migration_report.md. Contents: {sorted(names_in_zip)}"
    )

    # Assertion 13: ZIP contains JSON report
    assert any("migration_report.json" in n for n in names_set), (
        f"ZIP missing migration_report.json. Contents: {sorted(names_in_zip)}"
    )

    # Assertion 14: ZIP contains git patch diff
    assert any(n.endswith(".diff") or "git_patch" in n for n in names_set), (
        f"ZIP missing git patch (.diff). Contents: {sorted(names_in_zip)}"
    )

    # Assertion 15: ZIP contains at least one translated source file (generated/)
    generated_files = [n for n in names_in_zip if n.startswith("generated/") and not n.endswith("/")]
    assert len(generated_files) >= 1, (
        f"ZIP missing translated source in generated/. Contents: {sorted(names_in_zip)}"
    )
