import os
import sys
import json
import zipfile
import shutil
import base64
import asyncio
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
sys.path.insert(0, "backend")

# Force mock mode before imports to prevent real external calls
os.environ["USE_MOCK_COMPILER"] = "true"
os.environ["USE_MOCK_AI"] = "true"

import app.redis.client
import app.redis.manager
import app.redis.publisher
import app.redis.subscriber
import app.agents.base_agent
from app.main import app as fastapi_app
from app.workflow_engine.context import WorkflowContext
from app.workflow_engine.state_machine import WorkflowEngine
from app.models.compiler_error import CompilerError
from app.workspace.manager import get_workspace_path
from app.redis.keys import status_key, journal_key

# ---------------------------------------------------------------------------
# Complex CUDA Source Code (Stress Test Case)
# ---------------------------------------------------------------------------
STRESS_CUDA_SOURCE = """\\
#include <cuda_runtime.h>
#include <stdio.h>
#include <cooperative_groups.h>

namespace cg = cooperative_groups;

// 1. Host function querying device properties
void query_device_properties() {
    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, 0);
    // Stress 1: Host-side query of warp size
    printf("Warp size on host: %d\\\\n", prop.warpSize);
}

// 2. Kernel demonstrating multiple stress patterns
__global__ void stress_kernel(float* out, float* in, int n) {
    // Stress 2: Multi-type dynamic shared memory casting pattern
    extern __shared__ float sdata_float[];
    int* sdata_int = (int*)&sdata_float[256];
    
    int tid = threadIdx.x;
    
    // Stress 3: Literal 32 used for warpSize indexing/assumptions
    int lane = tid % 32;
    int warp_id = tid / 32;
    
    // Stress 4: Direct warpSize symbol usage in device code
    int device_warp_size = warpSize;
    
    // Stress 5: Warp shuffles/ballots using 32-bit integer masks
    // Under HIP on CDNA, active masks must fit in uint64_t.
    unsigned int mask = 0xffffffff;
    float value = in[tid];
    float shuffled = __shfl_sync(mask, value, lane, 32);
    unsigned int active_ballot = __ballot_sync(mask, value > 0.0f);
    
    // Stress 6: Cooperative Groups
    cg::thread_block block = cg::this_thread_block();
    block.sync();
    
    // Stress 7: Inline PTX assembly block (invalid on AMD, needs to be replaced)
    unsigned int lane_id_ptx = 0;
    asm volatile("mov.u32 %0, %%laneid;" : "=r"(lane_id_ptx));
    
    if (tid < n) {
        sdata_float[lane] = shuffled + (float)active_ballot;
        sdata_int[lane] = (int)lane_id_ptx + device_warp_size;
        out[tid] = sdata_float[lane] + (float)sdata_int[lane];
    }
}
"""

# Expected patched/healed code containing the correct HIP and ROCm-compliant APIs
HEALED_HIP_SOURCE = """\\
#include <hip/hip_runtime.h>
#include <stdio.h>
#include <hip/hip_cooperative_groups.h>

namespace cg = cooperative_groups;

// 1. Host function querying device properties
void query_device_properties() {
    hipDeviceProp_t prop;
    hipGetDeviceProperties(&prop, 0);
    // Stress 1: Host-side query of warp size
    printf("Warp size on host: %d\\\\n", prop.warpSize);
}

// 2. Kernel demonstrating multiple stress patterns
__global__ void stress_kernel(float* out, float* in, int n) {
    // Stress 2: Multi-type dynamic shared memory casting pattern
    extern __shared__ float sdata_float[];
    int* sdata_int = (int*)&sdata_float[256];
    
    int tid = threadIdx.x;
    
    // Stress 3: Literal 32 used for warpSize indexing/assumptions (replaced with warpSize constant or runtime equivalent)
    int lane = tid % warpSize;
    int warp_id = tid / warpSize;
    
    // Stress 4: Direct warpSize symbol usage in device code
    int device_warp_size = warpSize;
    
    // Stress 5: Warp shuffles/ballots using 64-bit integer masks
    // Under HIP on CDNA, active masks must fit in uint64_t.
    uint64_t mask = 0xffffffffULL;
    float value = in[tid];
    float shuffled = __shfl_sync(mask, value, lane, warpSize);
    uint64_t active_ballot = __ballot_sync(mask, value > 0.0f);
    
    // Stress 6: Cooperative Groups
    cg::thread_block block = cg::this_thread_block();
    block.sync();
    
    // Stress 7: Inline PTX assembly block (replaced with hip intrinsic)
    unsigned int lane_id_ptx = __lane_id();
    
    if (tid < n) {
        sdata_float[lane] = shuffled + (float)active_ballot;
        sdata_int[lane] = (int)lane_id_ptx + device_warp_size;
        out[tid] = sdata_float[lane] + (float)sdata_int[lane];
    }
}
"""

# ---------------------------------------------------------------------------
from tests.conftest import MockRedis


@pytest.fixture(autouse=True)
def mock_redis():
    """Replace all backend Redis clients with MockRedis for the duration of the test."""
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
    with TestClient(fastapi_app) as client:
        yield client


@pytest.mark.asyncio
async def test_complex_stress_migration_workflow(http_client, mock_redis, monkeypatch):
    """
    Stress test validating that HIPForge successfully migrates a complicated CUDA file
    from A to Z, ensuring both workflow completeness and correct/logical output files.
    """
    # ── STEP 1: Submit Stress CUDA File via upload API ───────────────────────
    encoded_source = base64.b64encode(STRESS_CUDA_SOURCE.encode("utf-8")).decode("ascii")
    
    response = http_client.post(
        "/api/v1/migrate/upload",
        json={
            "file": encoded_source,
            "filename": "stress_test.cu",
            "target_gpu_architecture": "gfx90a",
            "retry_budget": 2,
            "migration_mode": "file",
        },
    )
    
    assert response.status_code == 202
    body = response.json()
    migration_id = body["migration_id"]
    assert migration_id
    
    # ── STEP 2: Configure Workspace Context and Mock Components ──────────────
    workspace_path = get_workspace_path(migration_id)
    assert workspace_path.exists()
    
    context = WorkflowContext(
        migration_id=migration_id,
        workspace_path=str(workspace_path),
        retry_budget=2,
    )
    context.current_state = "QUEUED"
    
    # Track states visited by the engine
    visited_states = []
    
    # Capture original compilation and API call functions
    original_handle_compiling = app.workflow_engine.states.handle_compiling
    
    # Simulate compiler: Fails on attempt 0 (unsupported PTX/inline assembly),
    # Succeeds on attempt 1 (after AI self-healing patches the file).
    async def mock_handle_compiling(ctx: WorkflowContext):
        # Run standard compilation handler first (simulates environment checks, creates log file structure)
        await original_handle_compiling(ctx)
        
        if ctx.current_attempt == 0:
            ctx.compilation_success = False
            ctx.compiler_errors = [
                CompilerError(
                    file=ctx.hipify_output_path or "stress_test.hip",
                    line=42,
                    column=5,
                    message="unrecognized instruction / inline assembly invalid: asm volatile('mov.u32 ...')",
                    code="E0020"
                )
            ]
        else:
            ctx.compilation_success = True
            ctx.compiler_errors = []
            
        return "COMPILING"

    # Patch the compiler handler
    monkeypatch.setattr(app.workflow_engine.states, "handle_compiling", mock_handle_compiling)
    
    # Mock Fireworks AI client chat completions
    def mock_chat_completion(self, model, messages, max_tokens=2048):
        system_text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system").lower()
        
        if "hipforge analysis agent" in system_text:
            analysis = {
                "summary": "Compilation failed due to NVIDIA-specific inline PTX assembly and 32-bit mask mismatch on wavefront shuffles.",
                "root_cause": "The inline assembly `mov.u32` is not supported on AMD CDNA/RDNA architectures. Also, __shfl_sync expects 64-bit uint64_t mask values.",
                "affected_files": ["stress_test.hip"],
                "affected_lines": [42, 33],
                "confidence": 0.95,
                "repair_plan": [
                    "Replace NVIDIA inline PTX assembly with __lane_id() intrinsic.",
                    "Cast or redefine mask parameter in __shfl_sync/__ballot_sync to uint64_t.",
                    "Replace 32 warp size assumptions with the portable warpSize variable."
                ]
            }
            return {
                "choices": [{"message": {"role": "assistant", "content": json.dumps(analysis)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
            }
        elif "hipforge patch agent" in system_text:
            return {
                "choices": [{"message": {"role": "assistant", "content": HEALED_HIP_SOURCE}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
            }
        elif "hipforge research agent" in system_text:
            research = {
                "findings": ["ROCm supports __lane_id() and requires uint64_t active masks for shuffles on CDNA architectures."],
                "recommended_actions": ["Use __lane_id() and cast mask parameter to uint64_t."]
            }
            return {
                "choices": [{"message": {"role": "assistant", "content": json.dumps(research)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
            }
        return {
            "choices": [{"message": {"role": "assistant", "content": "{}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        }

    # Patch the MockFireworksClient class method directly
    monkeypatch.setattr(app.agents.base_agent.MockFireworksClient, "chat_completion", mock_chat_completion)
    
    # ── STEP 3: Execute State Machine and Trace Execution ────────────────────
    engine = WorkflowEngine(context)
    
    # Wrap state registry to intercept and record traversed states
    for state_name, handler in list(engine.state_registry.items()):
        def make_wrapper(h, name):
            async def wrapper(ctx_arg):
                visited_states.append(name)
                return await h(ctx_arg)
            return wrapper
        engine.state_registry[state_name] = make_wrapper(handler, state_name)
        
    final_state = await engine.run()
    
    # ── STEP 4: Validate Workflow ──────────────────────────────────────────
    # Check that all canonical stages were successfully traversed in order
    expected_sequence = [
        "QUEUED",
        "PREPARING",
        "PREFLIGHT",
        "HIPIFY",
        "SCA",
        "COMPILING",  # Attempt 0 (fails)
        "ANALYZING",  # Analyzes compilation error
        "PATCHING",   # Patches the code
        "COMPILING",  # Attempt 1 (succeeds)
        "GENERATING_REPORT",
        "COMPLETED"
    ]
    
    assert visited_states == expected_sequence
    assert final_state == "COMPLETED"
    
    # ── STEP 5: Validate Correctness & Logic of Generated HIP File ───────────
    # Read the final generated HIP file path
    final_hip_path = Path(context.hipify_output_path)
    assert final_hip_path.exists()
    
    content = final_hip_path.read_text(encoding="utf-8")
    
    # 1. Assert host-side query is clean and converted
    assert "hipGetDeviceProperties" in content
    assert "hipDeviceProp_t" in content
    assert "cudaGetDeviceProperties" not in content
    assert "cudaDeviceProp" not in content
    
    # 2. Assert inline PTX assembly is replaced with portable intrinsic
    assert "__lane_id()" in content
    assert 'asm volatile("mov.u32' not in content
    
    # 3. Assert active masks for warp shuffles/ballots are defined as uint64_t for portability
    assert "uint64_t mask =" in content or "(uint64_t)" in content
    assert "uint64_t active_ballot" in content or "uint64_t" in content
    
    # 4. Assert direct CUDA APIs are translated to HIP
    assert "cudaMalloc" not in content
    assert "cudaFree" not in content
    assert "hip/hip_runtime.h" in content
    
    # ── STEP 6: Validate Output Report Artifacts ────────────────────────────
    # Check that risks JSON artifact contains identified semantic warnings
    risks_json_path = workspace_path / "artifacts" / "migration_risks.json"
    assert risks_json_path.exists()
    
    with open(risks_json_path, "r", encoding="utf-8") as f:
        risks_data = json.load(f)
    assert "issues" in risks_data
    
    # Verify that the exporter packaging step completed correctly
    zip_path = workspace_path / "exports" / "HIPForge_Migration.zip"
    assert zip_path.exists()
    
    with zipfile.ZipFile(zip_path, "r") as z:
        namelist = z.namelist()
        assert any("migration_report.md" in name for name in namelist)
        assert any("migration_report.json" in name for name in namelist)
        assert any(name.endswith(".diff") or "git_patch" in name for name in namelist)
        assert any(name.startswith("generated/") for name in namelist)
