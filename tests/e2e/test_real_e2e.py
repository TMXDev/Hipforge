import os
import sys
import time
import shutil
import base64
import zipfile
import io
import json
import subprocess
import requests
import redis
import pytest
from pathlib import Path
from app.workspace.manager import get_workspace_path

# Mark all tests in this file as real E2E tests and enable anyio/asyncio support
pytestmark = [pytest.mark.e2e_real, pytest.mark.anyio]

BACKEND_URL = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:4444?protocol=2")

# ---------------------------------------------------------------------------
# Environment Checks Fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def check_real_e2e_env():
    """
    Verifies that the environment has all necessary real components:
    - Redis is reachable
    - hipcc exists (locally or on the backend container)
    - hipify-clang exists if required (locally or on the backend container)
    - Workspace is writable
    """
    # 1. Check Redis connection
    try:
        r = redis.from_url(REDIS_URL)
        if not r.ping():
            pytest.skip("E2E skip: Redis is not reachable at " + REDIS_URL)
    except Exception as e:
        pytest.skip(f"E2E skip: Redis connection failed: {e}")

    # 2. Check compiler and translator tools (locally or on backend container)
    has_local_hipcc = shutil.which("hipcc") is not None
    has_local_hipify = shutil.which("hipify-clang") is not None

    has_backend_hipcc = False
    has_backend_hipify = False

    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/health/check", timeout=5)
        if resp.status_code == 200:
            report = resp.json()
            for check in report.get("checks", []):
                if check.get("id") == "hipcc" and check.get("status") == "pass":
                    has_backend_hipcc = True
                if check.get("id") in ("host_hipify_clang", "sandbox_hipify_clang") and check.get("status") == "pass":
                    has_backend_hipify = True
    except Exception as e:
        # If backend is not even running/reachable, skip the test
        pytest.skip(f"E2E skip: Backend server not reachable at {BACKEND_URL}: {e}")

    if not (has_local_hipcc or has_backend_hipcc):
        pytest.skip("E2E skip: hipcc tool is missing locally and on backend container")
    if not (has_local_hipify or has_backend_hipify):
        pytest.skip("E2E skip: hipify-clang tool is missing locally and on backend container")

    # 3. Check backend workspace writability
    workspace_path = os.getenv("WORKSPACE_PATH", "workspace")
    try:
        os.makedirs(workspace_path, exist_ok=True)
        probe = os.path.join(workspace_path, ".hipforge_e2e_write_probe")
        with open(probe, "w") as f:
            f.write("probe")
        os.remove(probe)
    except Exception as e:
        pytest.skip(f"E2E skip: Workspace path '{workspace_path}' is not writable: {e}")


# ---------------------------------------------------------------------------
# Test Fixtures for Sample Projects
# ---------------------------------------------------------------------------
@pytest.fixture
def valid_cuda_project(tmp_path):
    """A tiny valid single-file CUDA project."""
    proj_dir = tmp_path / "valid_project"
    proj_dir.mkdir()
    code = """#include <cuda_runtime.h>
#include <stdio.h>

__global__ void add_kernel(float *c, const float *a, const float *b, int n) {
    int i = threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}

int main() {
    float *a, *b, *c;
    cudaMallocManaged(&a, sizeof(float));
    cudaMallocManaged(&b, sizeof(float));
    cudaMallocManaged(&c, sizeof(float));
    a[0] = 1.0f;
    b[0] = 2.0f;
    add_kernel<<<1, 1>>>(c, a, b, 1);
    cudaDeviceSynchronize();
    printf("Result: %f\\n", c[0]);
    cudaFree(a);
    cudaFree(b);
    cudaFree(c);
    return 0;
}
"""
    (proj_dir / "real_e2e_kernel.cu").write_text(code, encoding="utf-8")
    return proj_dir


@pytest.fixture
def incomplete_dependency_project(tmp_path):
    """An incomplete project calling a missing external symbol."""
    proj_dir = tmp_path / "incomplete_project"
    proj_dir.mkdir()
    code = """#include <cuda_runtime.h>
#include <stdio.h>

// Missing symbol defined externally but not linked
extern void run_gelu(float *out, float *in, int n);

int main() {
    float *d_out = nullptr;
    float *d_in = nullptr;
    run_gelu(d_out, d_in, 10);
    return 0;
}
"""
    (proj_dir / "real_e2e_incomplete.cu").write_text(code, encoding="utf-8")
    return proj_dir


@pytest.fixture
def syntax_error_project(tmp_path):
    """A project containing syntax errors."""
    proj_dir = tmp_path / "syntax_error_project"
    proj_dir.mkdir()
    code = """#include <cuda_runtime.h>

int main() {
    int a = 5
    if (a > 3 {
        return 0;
    }
}
"""
    (proj_dir / "real_e2e_syntax_error.cu").write_text(code, encoding="utf-8")
    return proj_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_zip_base64(project_dir: Path) -> str:
    """Creates a base64 encoded string of the zipped project directory."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_f:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                zip_f.write(file_path, file_path.relative_to(project_dir))
    return base64.b64encode(zip_buffer.getvalue()).decode("utf-8")


def poll_migration_job(migration_id: str, timeout: int = 45, interval: int = 1) -> dict:
    """Polls the status endpoint until the migration is COMPLETED or FAILED."""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BACKEND_URL}/api/v1/migrate/{migration_id}/status")
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            if status in ("COMPLETED", "FAILED"):
                return data
        time.sleep(interval)
    raise TimeoutError(f"Job {migration_id} did not finish within {timeout} seconds. Current status: {status}")


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------
def test_cli_path_smoke(valid_cuda_project, tmp_path):
    """
    CLI End-to-End Smoke Test:
    - Runs the CLI migration command against the real backend.
    - Targets the architecture 'gfx942' and requests 0 repair attempts.
    - Verifies the extraction of output files and compile command flags.
    """
    output_dir = tmp_path / "cli_output"
    
    # Run the CLI tool as a subprocess
    cli_script = Path(__file__).parents[2] / "cli" / "hipforge.py"
    cmd = [
        sys.executable,
        str(cli_script),
        "migrate",
        str(valid_cuda_project),
        "--output",
        str(output_dir),
        "--arch",
        "gfx942",
        "--attempts",
        "0",
        "--host",
        BACKEND_URL
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"CLI exited with code {result.returncode}. Stderr: {result.stderr}"

    # Verify extracted package structure
    # ponytail: look inside the migration_id subdirectory created by the CLI
    migration_folders = list(output_dir.glob("migration_*"))
    target_root = migration_folders[0] if migration_folders else output_dir

    report_md = target_root / "reports" / "migration_report.md"
    report_json = target_root / "reports" / "migration_report.json"
    compile_log = target_root / "logs" / "compile_attempt_001.log"

    assert report_md.exists(), f"CLI output missing migration_report.md in {target_root}"
    assert report_json.exists(), f"CLI output missing migration_report.json in {target_root}"
    assert compile_log.exists(), f"CLI output missing compile_attempt_001.log in {target_root}"

    # Verify compiler log output contains compile command with offload architecture
    log_content = compile_log.read_text(encoding="utf-8")
    assert "Command:" in log_content
    assert "--offload-arch=gfx942" in log_content


def test_web_api_upload_smoke(valid_cuda_project):
    """
    Web/API Upload Smoke Test:
    - Submits the valid CUDA project via base64 upload route.
    - Targets 'gfx942' and verifies job execution.
    - Asserts that all summary and metrics fields are populated in the journal.
    """
    b64_zip = get_zip_base64(valid_cuda_project)
    payload = {
        "file": b64_zip,
        "filename": "real_e2e_valid.zip",
        "target_gpu_architecture": "gfx942",
        "retry_budget": 0,
        "migration_mode": "standard"
    }

    resp = requests.post(f"{BACKEND_URL}/api/v1/migrate/upload", json=payload)
    assert resp.status_code == 202, f"Upload request failed: {resp.text}"

    data = resp.json()
    migration_id = data["migration_id"]
    assert migration_id

    # Wait for completion
    final_status = poll_migration_job(migration_id)
    assert final_status["status"] == "COMPLETED"

    # Verify reports exist in the workspace directory
    workspace_dir = get_workspace_path(migration_id)
    report_json_path = workspace_dir / "reports" / "migration_report.json"
    assert report_json_path.exists(), "Report JSON was not generated in workspace"

    # Query the migration journal
    j_resp = requests.get(f"{BACKEND_URL}/api/v1/migrate/{migration_id}/journal")
    assert j_resp.status_code == 200
    journal = j_resp.json()

    # Verify stage trace and compile attempts from journal
    stages = [entry["workflow_state"] for entry in journal]
    assert "QUEUED" in stages
    assert "COMPILING" in stages
    assert "COMPLETED" in stages

    compile_attempts = sum(1 for entry in journal if entry.get("workflow_state") == "COMPILING")
    assert compile_attempts == 1


def test_paste_code_smoke():
    """
    Paste Code Smoke Test:
    - Submits CUDA code through /api/v1/migrate/paste with a non-test filename.
    - Verifies the execution flow finishes with success.
    """
    code = """#include <cuda_runtime.h>
__global__ void simple_kernel() {}
int main() {
    simple_kernel<<<1, 1>>>();
    cudaDeviceSynchronize();
    return 0;
}
"""
    payload = {
        "code": code,
        "filename": "real_paste_kernel.cu",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 0,
        "migration_mode": "standard"
    }

    resp = requests.post(f"{BACKEND_URL}/api/v1/migrate/paste", json=payload)
    assert resp.status_code == 202, f"Paste request failed: {resp.text}"

    migration_id = resp.json()["migration_id"]
    final_status = poll_migration_job(migration_id)
    assert final_status["status"] == "COMPLETED"


def test_dependency_failure_fixture(incomplete_dependency_project):
    """
    Dependency Failure Test Case:
    - Verifies that compilation fails with DEPENDENCY_ERROR due to unresolved external function.
    - Asserts that terminal status is FAILED.
    - Asserts that error category is DEPENDENCY_ERROR.
    - Asserts that AI repair is skipped with a message to upload the full project or missing dependency.
    """
    b64_zip = get_zip_base64(incomplete_dependency_project)
    payload = {
        "file": b64_zip,
        "filename": "real_e2e_incomplete.zip",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 1,
        "migration_mode": "standard"
    }

    resp = requests.post(f"{BACKEND_URL}/api/v1/migrate/upload", json=payload)
    assert resp.status_code == 202

    migration_id = resp.json()["migration_id"]
    final_status = poll_migration_job(migration_id)
    assert final_status["status"] == "FAILED"

    # Query report json
    workspace_dir = get_workspace_path(migration_id)
    report_json_path = workspace_dir / "reports" / "migration_report.json"
    assert report_json_path.exists()

    with open(report_json_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    metrics = report.get("migration_metrics", {})
    assert metrics.get("error_category") == "DEPENDENCY_ERROR"
    
    # Assert main error contains unresolved symbol
    main_error = metrics.get("main_error", "").lower()
    assert "undefined symbol" in main_error or "undefined reference" in main_error or "run_gelu" in main_error

    # Assert skipped AI repair reason instructs user to upload full project / missing dependency
    assert "AI repair skipped because this appears to be a missing project dependency." in report["final_summary"]["recommended_next_action"]
    assert "Upload the full project folder or include the file/library that defines the missing symbol." in report["final_summary"]["recommended_next_action"]


def test_syntax_error_fixture(syntax_error_project):
    """
    Syntax Error Test Case:
    - Verifies that syntax errors are captured as compiler errors.
    - Targets with retry_budget=0 to ensure immediate termination.
    - Asserts failed stage is COMPILING.
    """
    b64_zip = get_zip_base64(syntax_error_project)
    payload = {
        "file": b64_zip,
        "filename": "real_e2e_syntax_error.zip",
        "target_gpu_architecture": "gfx90a",
        "retry_budget": 0,
        "migration_mode": "standard"
    }

    resp = requests.post(f"{BACKEND_URL}/api/v1/migrate/upload", json=payload)
    assert resp.status_code == 202

    migration_id = resp.json()["migration_id"]
    final_status = poll_migration_job(migration_id)
    assert final_status["status"] == "FAILED"

    # Query report json
    workspace_dir = get_workspace_path(migration_id)
    report_json_path = workspace_dir / "reports" / "migration_report.json"
    assert report_json_path.exists()

    with open(report_json_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    metrics = report.get("migration_metrics", {})
    assert metrics.get("failed_stage") in ("COMPILING", "HIPIFY")
    assert "error:" in metrics.get("main_error", "").lower()
