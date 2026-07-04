# tests/e2e/run_e2e.py
"""
HIPForge Real End-to-End Black-Box Validator.
Coordinates:
1. Generating ZIP files for each CUDA test case.
2. Submitting them to the live HIPForge REST API.
3. Tracking workflow status to COMPLETED.
4. Downloading and extracting the generated HIP project.
5. Verifying:
   - Dynamic source discovery.
   - Forbidden CUDA-only header checks.
6. Compiling the translated HIP code via hipcc inside Docker container.
7. Executing the binary in Docker container.
8. Validating numerical outputs against trusted CPU reference implementations.
9. Generating a detailed report.
"""

import os
import sys
import json
import time
import zipfile
import shutil
import tempfile
import subprocess
import requests
from pathlib import Path
import math

from projects import PROJECTS

BACKEND_URL = "http://localhost:8000"
DOCKER_IMAGE = "rocm/dev-ubuntu-22.04:latest"

def print_banner(msg):
    print(f"\n{'='*80}\n{msg.center(80)}\n{'='*80}")

def check_backend_health():
    url = f"{BACKEND_URL}/api/v1/health/check"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print(f"[Health] Live backend detected: {url}")
            return True
    except Exception as e:
        pass
    print(f"[Health] Could not connect to backend at {url}")
    return False

def create_project_zip(name, files_dict):
    """Creates a temporary zip file from the dict of file paths and contents."""
    temp_dir = Path(tempfile.mkdtemp(prefix=f"e2e_{name}_"))
    for rel_path, content in files_dict.items():
        file_path = temp_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    
    zip_path = Path(tempfile.mktemp(suffix=".zip"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in temp_dir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(temp_dir))
                
    shutil.rmtree(temp_dir)
    return zip_path

def run_migration_job(zip_path, name):
    """Uploads the zip, polls the status, and returns the downloaded zip path."""
    import base64
    zip_bytes = zip_path.read_bytes()
    base64_data = base64.b64encode(zip_bytes).decode("ascii")
    
    upload_url = f"{BACKEND_URL}/api/v1/migrate/upload"
    payload = {
        "file": base64_data,
        "filename": f"{name}.zip",
        "target_gpu_architecture": "gfx1100",
        "retry_budget": 3,
        "migration_mode": "file"
    }
    
    print(f"[{name}] Submitting migration request to {upload_url}...")
    resp = requests.post(upload_url, json=payload, timeout=10)
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"Failed to initiate migration: {resp.status_code} - {resp.text}")
        
    migration_id = resp.json()["migration_id"]
    print(f"[{name}] Migration job accepted. ID: {migration_id}")
    
    status_url = f"{BACKEND_URL}/api/v1/migrate/{migration_id}/status"
    start_time = time.time()
    timeout = 180 # 3 minutes timeout
    
    while True:
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Migration job {migration_id} timed out after {timeout}s.")
            
        time.sleep(2)
        status_resp = requests.get(status_url, timeout=5)
        if status_resp.status_code != 200:
            print(f"[{name}] Status check failed: {status_resp.status_code}")
            continue
            
        status = status_resp.json().get("status", "").upper()
        print(f"[{name}] Current status: {status} (elapsed: {int(time.time() - start_time)}s)")
        
        if status == "COMPLETED":
            break
        elif status in ("FAILED", "CANCELLED"):
            # Fetch journal for additional context
            journal_url = f"{BACKEND_URL}/api/v1/migrate/{migration_id}/journal"
            try:
                j_resp = requests.get(journal_url, timeout=5)
                if j_resp.status_code == 200:
                    print(f"[{name}] Journal entries on failure:")
                    for entry in j_resp.json():
                        print(f"  - State: {entry.get('workflow_state')}, Success: {entry.get('compiler_result', {}).get('success')}, Reason: {entry.get('compiler_result', {}).get('stderr')}")
            except Exception:
                pass
            raise RuntimeError(f"Migration job {migration_id} terminated with state: {status}")
            
    # Download the finished migration ZIP
    download_url = f"{BACKEND_URL}/api/v1/migrate/{migration_id}/download"
    print(f"[{name}] Downloading resulting package from {download_url}...")
    dl_resp = requests.get(download_url, timeout=15)
    if dl_resp.status_code != 200:
        raise RuntimeError(f"Failed to download result package: {dl_resp.status_code}")
        
    out_zip = Path(tempfile.mktemp(suffix="_result.zip"))
    out_zip.write_bytes(dl_resp.content)
    return out_zip

def verify_forbidden_headers(extracted_dir, forbidden_headers):
    """Verifies that no forbidden CUDA headers remain in translated files."""
    violations = []
    for p in Path(extracted_dir).rglob("*"):
        if p.is_file() and p.suffix in (".hip", ".h", ".hpp", ".cuh"):
            content = p.read_text(encoding="utf-8", errors="replace")
            for header in forbidden_headers:
                if f"#{header}" in content or f"<{header}>" in content or f'"{header}"' in content:
                    violations.append(f"{p.name} contains reference to {header}")
    return violations

def compile_and_run_in_docker(extracted_dir):
    """Compiles and executes the HIP project in Docker, capturing stdout/stderr."""
    # 1. Discover all sources and includes dynamically
    sources = []
    include_dirs = set()
    for p in Path(extracted_dir).rglob("*"):
        if p.is_file():
            rel = p.relative_to(extracted_dir)
            if p.suffix in (".hip", ".cpp", ".cc", ".cxx") and "output_attempt" not in p.name:
                sources.append(str(rel).replace("\\", "/"))
            if p.suffix in (".h", ".hpp", ".cuh"):
                include_dirs.add(str(rel.parent).replace("\\", "/"))
                
    if not sources:
        return False, "No source files discovered dynamically.", "", ""
        
    print(f"[Docker] Discovered sources: {sources}")
    print(f"[Docker] Discovered include dirs: {list(include_dirs)}")
    
    # 2. Build compile command
    cmd_compile = ["hipcc", *sources]
    for d in include_dirs:
        if d != ".":
            cmd_compile.extend(["-I", f"/workspace/{d}"])
    cmd_compile.extend(["-I", "/workspace"])
    cmd_compile.extend(["-o", "/workspace/app_binary"])
    
    local_workspace = os.path.abspath(extracted_dir).replace("\\", "/")
    
    # 3. Execute compilation in docker
    docker_compile_cmd = [
        "docker", "run", "--rm",
        "-v", f"{local_workspace}:/workspace",
        "-w", "/workspace",
        DOCKER_IMAGE,
        *cmd_compile
    ]
    
    print(f"[Docker] Compiling: {' '.join(docker_compile_cmd)}")
    c_res = subprocess.run(docker_compile_cmd, capture_output=True, text=True, check=False)
    if c_res.returncode != 0:
        return False, f"Compilation failed with exit code {c_res.returncode}", c_res.stdout, c_res.stderr
        
    print("[Docker] Compilation succeeded. Running binary...")
    
    # 4. Execute the binary in docker
    docker_run_cmd = [
        "docker", "run", "--rm",
        "-v", f"{local_workspace}:/workspace",
        "-w", "/workspace",
        DOCKER_IMAGE,
        "./app_binary"
    ]
    
    print(f"[Docker] Running: {' '.join(docker_run_cmd)}")
    r_res = subprocess.run(docker_run_cmd, capture_output=True, text=True, check=False)
    
    # Remove local binary if it exists
    bin_path = Path(extracted_dir) / "app_binary"
    if bin_path.exists():
        try:
            os.remove(bin_path)
        except Exception:
            pass
            
    if r_res.returncode != 0:
        return False, f"Execution failed with exit code {r_res.returncode}", r_res.stdout, r_res.stderr
        
    return True, "Success", r_res.stdout, r_res.stderr

def parse_values(line):
    """Parses a comma-separated list of float values from line."""
    parts = line.split(":", 1)[1].strip()
    if not parts:
        return []
    return [float(x) for x in parts.split(",")]

def compare_results(stdout, case_name, tolerance):
    """Parses output and checks correctness against a trusted Python/CPU reference."""
    lines = stdout.splitlines()
    input_a, input_b, output = None, None, None
    for line in lines:
        if line.startswith("INPUT_A:"):
            input_a = parse_values(line)
        elif line.startswith("INPUT_B:"):
            input_b = parse_values(line)
        elif line.startswith("OUTPUT:"):
            output = parse_values(line)
            
    if output is None:
        return False, "Could not parse OUTPUT from binary stdout."
    if input_a is None:
        return False, "Could not parse INPUT_A from binary stdout."
        
    # Run CPU references
    if case_name == "vector_add":
        if input_b is None:
            return False, "vector_add case missing INPUT_B."
        expected = [a + b for a, b in zip(input_a, input_b)]
    elif case_name == "gelu":
        # GELU approximation: 0.5 * x * (1 + tanh(sqrt(2/pi) * (x + 0.044715 * x^3)))
        expected = []
        for x in input_a:
            c1 = 0.7978845608
            c2 = 0.044715
            inner = c1 * (x + c2 * x * x * x)
            expected.append(0.5 * x * (1.0 + math.tanh(inner)))
    elif case_name == "tiled_matmul":
        if input_b is None:
            return False, "tiled_matmul case missing INPUT_B."
        width = 32
        expected = [0.0] * (width * width)
        for r in range(width):
            for c in range(width):
                val = 0.0
                for k in range(width):
                    val += input_a[r * width + k] * input_b[k * width + c]
                expected[r * width + c] = val
    elif case_name == "reduction":
        expected = []
        for b in range(8):
            expected.append(sum(input_a[b * 32 : (b + 1) * 32]))
    elif case_name == "softmax":
        max_val = max(input_a)
        exps = [math.exp(x - max_val) for x in input_a]
        sum_exps = sum(exps)
        expected = [e / sum_exps for e in exps]
    elif case_name == "nested_project":
        expected = [x * 2.5 for x in input_a]
    else:
        return False, f"Unknown case: {case_name}"
        
    # Compare with tolerance
    if len(output) != len(expected):
        return False, f"Length mismatch: output={len(output)}, expected={len(expected)}"
        
    max_abs_err = 0.0
    max_rel_err = 0.0
    abs_tol = tolerance["abs"]
    rel_tol = tolerance["rel"]
    
    for a, e in zip(output, expected):
        abs_err = abs(a - e)
        if abs_err > max_abs_err:
            max_abs_err = abs_err
            
        if e != 0.0:
            rel_err = abs_err / abs(e)
            if rel_err > max_rel_err:
                max_rel_err = rel_err
        else:
            rel_err = 0.0
            
        if abs_err > abs_tol and (e == 0.0 or rel_err > rel_tol):
            return False, f"Tolerance exceeded: actual={a}, expected={e} (abs_err={abs_err:.2e}, rel_err={rel_err:.2e})"
            
    return True, f"Numerical values match (Max abs err={max_abs_err:.2e}, Max rel err={max_rel_err:.2e})"

def main():
    print_banner("HIPForge E2E Black-Box Validation Suite Starting")
    
    if not check_backend_health():
        sys.exit(1)
        
    results = {}
    
    # Process each project
    for name, config in PROJECTS.items():
        print_banner(f"Running Case: {name}")
        results[name] = {
            "status": "FAIL",
            "reason": "Not started",
            "compile_log": "",
            "run_log": "",
            "metrics": ""
        }
        
        # 1. Zip files
        zip_path = create_project_zip(name, config["files"])
        print(f"[{name}] Created source zip: {zip_path}")
        
        extracted_dir = Path(tempfile.mkdtemp(prefix=f"e2e_extracted_{name}_"))
        
        try:
            # 2. Run migration
            res_zip = run_migration_job(zip_path, name)
            
            # 3. Extract output zip
            with zipfile.ZipFile(res_zip, "r") as zf:
                # Extract into the generated subfolder of temporary directory
                zf.extractall(extracted_dir)
            os.remove(res_zip)
            
            # Since HIPForge nests outputs under 'generated/', let's locate it
            gen_sub = extracted_dir / "generated"
            if not gen_sub.exists():
                gen_sub = extracted_dir
                
            print(f"[{name}] Extracted outputs to {gen_sub}")
            
            # 4. Verify forbidden headers
            violations = verify_forbidden_headers(gen_sub, config["forbidden_headers"])
            if violations:
                results[name]["reason"] = f"Forbidden CUDA headers found: {violations}"
                print(f"[{name}] FAILURE: {results[name]['reason']}")
                continue
                
            # 5. Compile and run in docker container
            success, msg, stdout, stderr = compile_and_run_in_docker(gen_sub)
            
            results[name]["compile_log"] = f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}" if not success else "Succeeded"
            results[name]["run_log"] = f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}" if success else "Not run"
            
            if not success:
                results[name]["reason"] = f"Compilation/Execution failed: {msg}\nStderr:\n{stderr}"
                print(f"[{name}] FAILURE: {results[name]['reason']}")
                continue
                
            # 6. Validate math results
            ok, metrics = compare_results(stdout, name, config["tolerance"])
            results[name]["metrics"] = metrics
            
            if not ok:
                results[name]["reason"] = f"Output correctness validation failed: {metrics}"
                print(f"[{name}] FAILURE: {results[name]['reason']}")
                continue
                
            # If everything passed
            results[name]["status"] = "PASS"
            results[name]["reason"] = "All checks passed successfully"
            print(f"[{name}] SUCCESS: {metrics}")
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            results[name]["reason"] = f"Unexpected exception: {str(e)}\n{tb}"
            print(f"[{name}] FAILURE: {results[name]['reason']}")
            
        finally:
            if zip_path.exists():
                os.remove(zip_path)
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
                
    # Generate final report
    print_banner("E2E Validation Harness Complete - Generating Report")
    
    report_path = Path("tests/e2e/e2e_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# HIPForge E2E Validation Harness Final Report\n\n")
        f.write(f"Executed on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Summary\n\n")
        f.write("| Case Name | Status | Metrics | Reason / Notes |\n")
        f.write("| --- | --- | --- | --- |\n")
        for name, res in results.items():
            f.write(f"| `{name}` | **{res['status']}** | {res['metrics']} | {res['reason'].splitlines()[0] if res['reason'] else 'N/A'} |\n")
            
        f.write("\n## Detailed Logs per Case\n\n")
        for name, res in results.items():
            f.write(f"### Case: `{name}`\n\n")
            f.write(f"- **Final Status**: {res['status']}\n")
            f.write(f"- **Validation Metrics**: {res['metrics']}\n")
            f.write(f"- **Reason for Outcome**: {res['reason']}\n\n")
            
            f.write("#### Compilation Output\n")
            f.write("```text\n")
            f.write(res["compile_log"] or "N/A\n")
            f.write("```\n\n")
            
            f.write("#### Runtime Execution Output\n")
            f.write("```text\n")
            f.write(res["run_log"] or "N/A\n")
            f.write("```\n\n")
            f.write("---\n\n")
            
    print(f"Report successfully written to {report_path.resolve()}")
    
    # Exit code based on success of all cases
    all_passed = all(res["status"] == "PASS" for res in results.values())
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
