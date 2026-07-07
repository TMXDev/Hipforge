#!/usr/bin/env python3
import os
import sys
import argparse
import tempfile
import zipfile
import asyncio
import json
import base64
import shlex
from pathlib import Path
import requests
import websockets

try:
    import readline  # noqa: F401 – tab-complete in interactive shell; optional
except ImportError:
    readline = None  # ponytail: no pyreadline fallback; it can hang on Windows

# ANSI colors for premium terminal UI
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    GOLD = '\033[38;5;220m'
    DARK_GRAY = '\033[90m'
    PURPLE = '\033[38;5;141m'

# Load simple env from .env if present
def load_env_file():
    env_path = Path(".env")
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
        except Exception:
            pass

load_env_file()

# Session Config variables
default_host = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:8000")
default_arch = os.getenv("DEFAULT_ARCH", "gfx90a")
try:
    default_attempts = int(os.getenv("DEFAULT_RETRY_BUDGET", "5"))
except ValueError:
    default_attempts = 5
migration_history = []

# Function to validate architecture against supported targets
def validate_target_architecture(target_arch: str) -> bool:
    if not target_arch or not target_arch.strip():
        raise ValueError("Target architecture cannot be empty.")
    return True

def print_step(message: str):
    print(f"{Colors.BOLD}{Colors.BLUE}[+] {message}{Colors.ENDC}")

def print_success(message: str):
    print(f"{Colors.BOLD}{Colors.GREEN}[OK] {message}{Colors.ENDC}")

def print_warn(message: str):
    print(f"{Colors.WARNING}[!] {message}{Colors.ENDC}")

def print_fail(message: str):
    print(f"{Colors.BOLD}{Colors.FAIL}[X] {message}{Colors.ENDC}")

def _load_backend_diagnostics():
    """
    Import backend diagnostics when running from a source checkout. Installed CLI
    builds without backend sources fall back to the HTTP API.
    """
    repo_root = Path(__file__).resolve().parents[1]
    backend_path = repo_root / "backend"
    if backend_path.exists() and str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
    try:
        from app.diagnostics import run_preflight, run_self_test
        return run_preflight, run_self_test
    except Exception:
        return None, None

def _status_color(status: str) -> str:
    status = (status or "").lower()
    if status == "pass":
        return Colors.GREEN
    if status == "warn":
        return Colors.WARNING
    if status == "fail":
        return Colors.FAIL
    return Colors.DARK_GRAY

def print_diagnostic_report(report: dict, verbose: bool = False):
    print(f"\n{Colors.BOLD}{Colors.GOLD}=== HIPForge Health Check ==={Colors.ENDC}")
    print(f"  Overall Health Score: {Colors.BOLD}{report.get('health_score', 0)} / 100{Colors.ENDC}")
    print(f"  Status: {report.get('overall_status', 'unknown')}")
    print(f"  Estimated Migration Readiness: {report.get('readiness', 'UNKNOWN')}")
    print(f"  Workspace: {report.get('workspace_path', '-')}")

    missing = report.get("missing_components") or []
    warnings = report.get("warnings") or []
    installed = report.get("installed_components") or []

    print(f"\n{Colors.BOLD}Installed Components{Colors.ENDC}")
    if installed:
        for name in installed:
            print(f"  {Colors.GREEN}[OK]{Colors.ENDC} {name}")
    else:
        print(f"  {Colors.DARK_GRAY}None detected{Colors.ENDC}")

    print(f"\n{Colors.BOLD}Missing Components{Colors.ENDC}")
    if missing:
        for name in missing:
            print(f"  {Colors.FAIL}[X]{Colors.ENDC} {name}")
    else:
        print(f"  {Colors.GREEN}[OK] No missing critical components detected{Colors.ENDC}")

    if warnings:
        print(f"\n{Colors.BOLD}Warnings{Colors.ENDC}")
        for item in warnings:
            print(f"  {Colors.WARNING}[!]{Colors.ENDC} {item.get('name')}: {item.get('message')}")

    fixes = report.get("recommended_fixes") or []
    print(f"\n{Colors.BOLD}Recommended Fixes{Colors.ENDC}")
    if fixes:
        for fix in fixes:
            print(f"  - {fix}")
    else:
        print("  No fixes required.")

    if verbose:
        print(f"\n{Colors.BOLD}All Checks{Colors.ENDC}")
        for check in report.get("checks", []):
            color = _status_color(check.get("status", ""))
            label = (check.get("status") or "").upper()
            print(f"  {color}[{label}]{Colors.ENDC} {check.get('name')}: {check.get('message')}")

def run_doctor_command(host_url: str, local: bool = False, json_output: bool = False, verbose: bool = False) -> bool:
    # ponytail: default is remote (backend truth); --local runs preflight on this machine
    report = None
    if local:
        run_preflight, _ = _load_backend_diagnostics()
        if run_preflight:
            print_step("[local] Running preflight diagnostics on this machine...")
            report = run_preflight()
        else:
            print_warn("[local] Backend diagnostics module not available; falling back to HTTP endpoint.")

    if report is None:
        print_step(f"Checking backend health at {host_url} ...")
        response = requests.get(f"{host_url}/api/v1/health/check", timeout=120)
        response.raise_for_status()
        report = response.json()

    if json_output:
        print(json.dumps(report, indent=2))
    else:
        print_diagnostic_report(report, verbose=verbose)

    return not bool(report.get("critical_failures"))

def print_self_test_report(report: dict, verbose: bool = False):
    print(f"\n{Colors.BOLD}{Colors.GOLD}=== HIPForge Self Test ==={Colors.ENDC}")
    for step in report.get("steps", []):
        if step.get("success"):
            print(f"  {Colors.GREEN}[OK]{Colors.ENDC} {step.get('name')}: {step.get('message', '')}")
        else:
            print(f"  {Colors.FAIL}[X]{Colors.ENDC} {step.get('name')}: {step.get('message', '')}")
            if not verbose:
                break
    if report.get("success"):
        print_success("Installation verification passed.")
    else:
        print_fail(f"Installation verification failed. Category: {report.get('failure_category', 'UNKNOWN')}")

def run_self_test_command(host_url: str, target_arch: str | None = None, remote: bool = False, json_output: bool = False, verbose: bool = False) -> bool:
    report = None
    if not remote:
        _, run_self_test = _load_backend_diagnostics()
        if run_self_test:
            report = run_self_test(target_arch=target_arch)

    if report is None:
        response = requests.post(f"{host_url}/api/v1/self-test", timeout=180)
        response.raise_for_status()
        report = response.json()

    if json_output:
        print(json.dumps(report, indent=2))
    else:
        print_self_test_report(report, verbose=verbose)

    return bool(report.get("success"))

def run_history_command(host_url: str, limit: int = 20, job_id: str | None = None) -> bool:
    """Fetches and prints migration history from the backend API."""
    try:
        if job_id:
            url = f"{host_url}/api/v1/migrations/history/{job_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                print_fail(f"No history entry found for: {job_id}")
                return False
            resp.raise_for_status()
            data = resp.json()
            print(f"\n{Colors.BOLD}{Colors.GOLD}=== Migration History Detail ==={Colors.ENDC}")
            for k, v in data.items():
                print(f"  {Colors.BOLD}{k}{Colors.ENDC}: {v}")
            if data.get("report_missing"):
                print_warn("Report file is missing or was not generated.")
            if data.get("artifact_missing"):
                print_warn("Artifact ZIP is missing or was not generated.")
        else:
            url = f"{host_url}/api/v1/migrations/history?limit={limit}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            items = resp.json()
            if not items:
                print_warn("No migration history found.")
                return True
            print(f"\n{Colors.BOLD}{Colors.GOLD}=== Migration History (newest first) ==={Colors.ENDC}")
            for item in items:
                state_color = Colors.GREEN if (item.get("compile_status") or "").upper() == "PASSED" else Colors.FAIL
                main_err = item.get("main_error") or ""
                err_str = f" | err: {main_err[:60]}" if main_err else ""
                missing = " [report missing]" if item.get("report_missing") else ""
                print(
                    f"  {Colors.BOLD}{item.get('job_id')}{Colors.ENDC} "
                    f"| {(item.get('finished_at') or '')[:19]} "
                    f"| arch={item.get('target_architecture')} "
                    f"| state={item.get('final_state')} "
                    f"| compile={state_color}{item.get('compile_status')}{Colors.ENDC} "
                    f"| conf={item.get('validation_confidence')}"
                    f"{err_str}{Colors.DARK_GRAY}{missing}{Colors.ENDC}"
                )
            print()
        return True
    except requests.RequestException as exc:
        print_fail(f"History API unavailable: {exc}")
        return False


def zip_project(project_path: Path) -> Path:
    """Zips the target project path recursively into a temporary file.
    If the input is already a .zip, returns it as-is (no double-zip).
    """
    if project_path.is_file() and project_path.suffix.lower() == ".zip":
        print_step(f"Input is already a ZIP archive: {project_path.name}")
        return project_path

    temp_zip = Path(tempfile.mktemp(suffix=".zip"))
    print_step(f"Compressing project {project_path.name}...")
    
    with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if project_path.is_file():
            zipf.write(project_path, project_path.name)
        else:
            for file_path in project_path.rglob('*'):
                if file_path.is_file() and not any(part.startswith('.') for part in file_path.parts):
                    rel_path = file_path.relative_to(project_path)
                    zipf.write(file_path, rel_path)
                    
    print_success(f"Compressed into temporary package: {temp_zip.name} ({temp_zip.stat().st_size / 1024:.1f} KB)")
    return temp_zip

def draw_stage_pipeline(active_stage: str):
    """Draws a beautiful progress line of the migration workflow stages."""
    stages = ["QUEUED", "PREPARING", "PREFLIGHT", "HIPIFY", "SCA", "COMPILING", "ANALYZING", "PATCHING", "GENERATING_REPORT"]
    formatted = []
    
    for stage in stages:
        if stage == active_stage.upper():
            formatted.append(f"{Colors.BOLD}{Colors.GOLD}[{stage}]{Colors.ENDC}")
        else:
            formatted.append(f"{Colors.DARK_GRAY}[{stage}]{Colors.ENDC}")
    arrow = " -> "
    try:
        if sys.stdout.encoding:
            " ──► ".encode(sys.stdout.encoding)
            arrow = " ──► "
    except Exception:
        pass
        
    print(f"\rPipeline: {arrow.join(formatted)}", end="", flush=True)

async def stream_logs(host_url: str, migration_id: str):
    """Connects to WebSocket and streams migration logs live."""
    ws_host = host_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_host}/ws/v1/migrate/{migration_id}/stream"
    
    print_step("Connecting to migration event stream...")
    try:
        async with websockets.connect(ws_url) as websocket:
            print_success("Connected to event stream. Streaming live logs...\n")
            
            while True:
                try:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        status_url = f"{host_url}/api/v1/migrate/{migration_id}/status"
                        try:
                            poll_resp = requests.get(status_url, timeout=3)
                            if poll_resp.status_code == 200:
                                polled_status = (poll_resp.json().get("status") or "").upper()
                                if polled_status in ("COMPLETED", "FAILED"):
                                    return polled_status
                        except Exception:
                            pass
                        continue
                    data = json.loads(message)
                    
                    m_type = data.get("type")
                    if m_type in ("status", "event"):
                        status = (data.get("status") or "").lower()
                        stage = (data.get("stage") or status).upper()
                        msg = data.get("message", "")
                        
                        # ponytail: track elapsed time and seen stages
                        if not hasattr(asyncio.current_task(), "seen_stages"):
                            asyncio.current_task().seen_stages = set()
                            asyncio.current_task().stage_start_times = {}
                            
                        seen = asyncio.current_task().seen_stages
                        starts = asyncio.current_task().stage_start_times
                        
                        seen.add(stage)
                        
                        elapsed = ""
                        if status == "started":
                            import time
                            starts[stage] = time.time()
                            print(f"\n{Colors.BOLD}{Colors.CYAN}>>> Stage Transition: {stage} (Started){Colors.ENDC}")
                        elif status in ("completed", "failed"):
                            import time
                            if stage in starts:
                                elapsed_sec = round(time.time() - starts[stage], 2)
                                elapsed = f" ({elapsed_sec}s)"
                            print(f"\n{Colors.BOLD}{Colors.CYAN}>>> Stage Transition: {stage} ({status.capitalize()}{elapsed}){Colors.ENDC}")
                        else:
                            print(f"\n{Colors.BOLD}{Colors.CYAN}>>> Stage Transition: {stage}{Colors.ENDC}")
                            
                        draw_stage_pipeline(stage)
                        print() # New line after the pipeline draw
                        if msg:
                            if status == "failed":
                                print(f"  {Colors.FAIL}{msg}{Colors.ENDC}")
                            else:
                                print(f"  {Colors.GREEN}{msg}{Colors.ENDC}")
                                
                        if stage == "GENERATING_REPORT" and status == "started":
                            if "ANALYZING" not in seen:
                                # We skipped AI repair!
                                print(f"  {Colors.BOLD}{Colors.WARNING}[AI Repair] AI repair skipped.{Colors.ENDC}")

                        stage_upper = (stage or "").upper()
                        if stage_upper in ("COMPLETED", "FAILED"):
                            return stage_upper
                    elif m_type in ("log", "compiler_log"):
                        msg = (data.get("message") or data.get("content") or "").strip()
                        if msg:
                            if "error" in msg.lower() or "failed" in msg.lower():
                                print(f"  {Colors.FAIL}{msg}{Colors.ENDC}")
                            elif "warning" in msg.lower():
                                print(f"  {Colors.WARNING}{msg}{Colors.ENDC}")
                            else:
                                print(f"  {msg}")
                    elif m_type == "ping":
                        pass
                except websockets.ConnectionClosed:
                    break
    except Exception as e:
        print_warn(f"WebSocket logging stream closed or failed: {e}")
    return None

def download_and_extract(host_url: str, migration_id: str, output_path: Path):
    """Downloads the completed zip report package, saves it, and extracts it to a clean subdirectory."""
    download_url = f"{host_url}/api/v1/migrate/{migration_id}/download"
    print_step(f"Downloading migration package from {download_url}...")
    
    response = requests.get(download_url)
    if response.status_code != 200:
        print_fail(f"Download failed with status: {response.status_code}")
        return False
        
    output_path.mkdir(parents=True, exist_ok=True)
    zip_out = output_path / f"{migration_id}.zip"
    zip_out.write_bytes(response.content)
    print_success(f"Saved migration ZIP to: {zip_out.resolve()}")
    
    extract_dir = output_path / migration_id
    print_step(f"Extracting package to subdirectory: {extract_dir}...")
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    temp_zip = Path(tempfile.mktemp(suffix="_result.zip"))
    temp_zip.write_bytes(response.content)
    with zipfile.ZipFile(temp_zip, 'r') as zipf:
        zipf.extractall(extract_dir)
        
    if temp_zip.exists():
        os.remove(temp_zip)
        
    print_success(f"Successfully extracted project to: {extract_dir.resolve()}")
    return True

async def run_migration(project_path: Path, target_arch: str, output_path: Path, host_url: str, retry_budget: int = 5):
    zip_file = None
    try:
        zip_file = zip_project(project_path)
        
        # Validate architecture against supported targets before sending to server
        try:
            validate_target_architecture(target_arch)
        except ValueError as e:
            print_fail(str(e))
            return

        upload_url = f"{host_url}/api/v1/migrate/upload"
        print_step(f"Uploading project to {upload_url}...")
        
        # Base64 encode the zipped content
        zip_bytes = zip_file.read_bytes()
        base64_data = base64.b64encode(zip_bytes).decode('utf-8')
        
        filename = project_path.name if project_path.name.endswith('.zip') else (project_path.name + '.zip')
            
        payload = {
            "file": base64_data,
            "filename": filename,
            "target_gpu_architecture": target_arch,
            "retry_budget": retry_budget,
            "migration_mode": "file"
        }
        
        response = requests.post(upload_url, json=payload)
            
        if response.status_code not in (200, 202):
            print_fail(f"Upload failed: HTTP {response.status_code} - {response.text}")
            return
            
        res_data = response.json()
        migration_id = res_data.get("migration_id")
        if not migration_id:
            print_fail(f"Invalid response from server: {res_data}")
            return
            
        print_success(f"Migration job accepted. ID: {migration_id}")
        
        # Store in session history
        migration_history.append({
            "id": migration_id,
            "project": project_path.name,
            "arch": target_arch
        })
        
        # Check initial status first to avoid blocking on already completed jobs
        final_status = None
        try:
            status_url = f"{host_url}/api/v1/migrate/{migration_id}/status"
            poll_resp = requests.get(status_url)
            if poll_resp.status_code == 200:
                init_status = poll_resp.json().get("status", "")
                if init_status.upper() in ("COMPLETED", "FAILED"):
                    final_status = init_status
        except Exception:
            pass

        if not final_status:
            final_status = await stream_logs(host_url, migration_id)
        
        if not final_status:
            # ponytail: WS dropped — poll until terminal state or timeout; ceiling = HIPFORGE_POLL_TIMEOUT seconds
            try:
                poll_timeout = int(os.getenv("HIPFORGE_POLL_TIMEOUT", "300"))
            except ValueError:
                poll_timeout = 300
            _TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
            print_warn("Live event stream disconnected. Falling back to status polling...")
            status_url = f"{host_url}/api/v1/migrate/{migration_id}/status"
            elapsed = 0
            interval = 5
            while elapsed < poll_timeout:
                try:
                    poll_resp = requests.get(status_url, timeout=10)
                    if poll_resp.status_code == 200:
                        final_status = poll_resp.json().get("status", "")
                        if (final_status or "").upper() in _TERMINAL:
                            break
                        print(f"  Polling... status={final_status or 'pending'} ({elapsed}s elapsed)", flush=True)
                except Exception:
                    pass
                await asyncio.sleep(interval)
                elapsed += interval
                
        if final_status and final_status.upper() == "COMPLETED":
            download_and_extract(host_url, migration_id, output_path)

        detail = {}
        journal = []
        try:
            status_resp = requests.get(f"{host_url}/api/v1/migrate/{migration_id}/status", timeout=5)
            if status_resp.status_code == 200:
                detail = status_resp.json()
        except Exception:
            pass

        try:
            journal_resp = requests.get(f"{host_url}/api/v1/migrate/{migration_id}/journal", timeout=5)
            if journal_resp.status_code == 200:
                journal = journal_resp.json()
        except Exception:
            pass

        # Per-attempt summary from journal
        compile_attempts = sum(1 for e in journal if e.get("workflow_state") == "COMPILING")
        repair_cycles = sum(1 for e in journal if e.get("workflow_state") in ("ANALYZING",))

        # Find failed stage (last non-terminal workflow_state)
        failed_stage = ""
        main_error = ""
        for e in reversed(journal):
            ws = e.get("workflow_state", "")
            if ws not in ("COMPLETED", "FAILED", "GENERATING_REPORT"):
                failed_stage = ws
                break
        for e in reversed(journal):
            err = e.get("main_error") or ""
            if err:
                main_error = err
                break

        terminal_status = final_status or "unknown"

        # Detect preflight-level failures from detail response
        error_category = detail.get("error_category", "")
        if not error_category:
            for e in journal:
                cat = e.get("error_category", "")
                if cat and cat not in ("NONE", ""):
                    error_category = cat
                    break

        # Detect build strategy from detail response or journal
        build_strategy = ""
        project_scan = detail.get("project_scan", {}) if isinstance(detail.get("project_scan"), dict) else {}
        if project_scan:
            build_strategy = project_scan.get("compile_strategy", "")

        compiler_mode = detail.get("compiler_mode") or "real"
        compile_status = detail.get("compile_status") or "NOT_RUN"
        val_confidence = detail.get("validation_confidence") or "LOW"
        runtime_val = detail.get("runtime_validation_status") or "NOT_RUN"
        main_err = detail.get("main_error") or main_error or ""
        next_act = detail.get("recommended_next_action") or ""
        report_path = f"workspace/{migration_id}/reports/migration_report.md"

        print(f"\n{Colors.BOLD}{Colors.GOLD}Migration Summary{Colors.ENDC}")
        print(f"Job ID: {migration_id}")
        print(f"Target architecture: {target_arch}")
        print(f"Final state: {terminal_status}")
        print(f"Compiler mode: {compiler_mode}")
        print(f"Compiler validation: {compile_status}")
        print(f"Validation confidence: {val_confidence}")
        print(f"Runtime validation: {runtime_val}")
        if main_err:
            print(f"Main error: {main_err}")
        if error_category and error_category != "NONE":
            print(f"Error category: {error_category}")
        if next_act:
            print(f"Next action: {next_act}")
        print(f"Report: {report_path}")
        if terminal_status.upper() == "COMPLETED" and compile_status.upper() == "PASSED":
            artifact_dir = output_path / migration_id
            print(f"Artifact: {artifact_dir.resolve()}")

    finally:
        if zip_file and zip_file.exists() and zip_file != project_path:
            try:
                os.remove(zip_file)
            except Exception:
                pass

def show_interactive_help():
    print(f"\n{Colors.BOLD}{Colors.GOLD}=== HIPForge Interactive CLI Commands ==={Colors.ENDC}")
    print(f"  {Colors.BOLD}/migrate [path] [out_dir] [--arch <arch>] [--attempts <num>] [--host <url>]{Colors.ENDC}")
    print(f"      Migrates your project. Run without arguments to start the interactive wizard.")
    print(f"  {Colors.BOLD}/cancel <migration_id> [--host <url>]{Colors.ENDC}")
    print(f"      Aborts an actively running migration immediately.")
    print(f"  {Colors.BOLD}/status <migration_id> [--host <url>]{Colors.ENDC}")
    print(f"      Queries the current status of a migration.")
    print(f"  {Colors.BOLD}/set <key> <value>{Colors.ENDC}")
    print(f"      Changes session settings. Keys: `host`, `arch`, `attempts`.")
    print(f"      {Colors.DARK_GRAY}Example: /set arch gfx942{Colors.ENDC}")
    print(f"  {Colors.BOLD}/info{Colors.ENDC}")
    print(f"      Validates backend server connection, prints status and list of default values.")
    print(f"  {Colors.BOLD}/doctor [--remote] [--json] [--verbose]{Colors.ENDC}")
    print(f"      Runs the full HIPForge environment health check.")
    print(f"  {Colors.BOLD}/self-test [--arch <arch>] [--remote] [--json] [--verbose]{Colors.ENDC}")
    print(f"      Runs the official installation verification project.")
    print(f"  {Colors.BOLD}/history{Colors.ENDC}")
    print(f"      Shows recent migrations executed in this session.")
    print(f"  {Colors.BOLD}/clear{Colors.ENDC}")
    print(f"      Clears the terminal screen.")
    print(f"  {Colors.BOLD}/help{Colors.ENDC}")
    print(f"      Displays this commands manual.")
    print(f"  {Colors.BOLD}/exit{Colors.ENDC} or {Colors.BOLD}/quit{Colors.ENDC}")
    print(f"      Exit the interactive console.\n")

def run_interactive_cli():
    global default_host, default_arch, default_attempts

    if readline:
        commands = ["/migrate", "/cancel", "/status", "/set", "/info", "/doctor", "/self-test", "/history", "/clear", "/help", "/exit", "/quit"]
        configs = ["host", "arch", "attempts"]
        architectures = ["gfx906", "gfx908", "gfx90a", "gfx940", "gfx941", "gfx942", "gfx1030", "gfx1100"]

        def completer(text, state):
            try:
                buffer = readline.get_line_buffer()
                words = shlex.split(buffer) if buffer else []
            except Exception:
                words = []
                buffer = ""

            options = []
            
            if not buffer or buffer.startswith("/"):
                if not words or (len(words) == 1 and not buffer.endswith(" ")):
                    options = [cmd for cmd in commands if cmd.startswith(text)]
                else:
                    cmd = words[0].lower()
                    if cmd == "/set":
                        if len(words) == 2 and not buffer.endswith(" "):
                            options = [cfg for cfg in configs if cfg.startswith(text)]
                        elif len(words) == 3 or (len(words) == 2 and buffer.endswith(" ")):
                            key = words[1].lower()
                            if key == "arch":
                                options = [arch for arch in architectures if arch.startswith(text)]
                    elif cmd == "/migrate":
                        if text.startswith("-"):
                            flags = ["--arch", "--attempts", "--host"]
                            options = [f for f in flags if f.startswith(text)]
                        elif len(words) >= 2:
                            prev = words[-2].lower()
                            if prev == "--arch":
                                options = [arch for arch in architectures if arch.startswith(text)]
                                
            if state < len(options):
                return options[state]
            return None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
    
    # Try to clear screen on launch
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print(f"{Colors.BOLD}{Colors.PURPLE}    __  ______________________                     {Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.PURPLE}   / / / /  _/ __ \\____  ____/___  _________ _____{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.PURPLE}  / /_/ // // /_/ / __ `/ __ `/ __ \\/ ___/ __ `/ _ \\{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.PURPLE} / __  // // ____/ /_/ / /_/ / /_/ / /  / /_/ /  __/{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.PURPLE}/_/ /_/___/_/    \\__, /\\__, /\\____/_/   \\__, /\\___/ {Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.PURPLE}                /____//____/           /____/       {Colors.ENDC}")
    print(f"                  {Colors.GOLD}Premium Command Console v0.1.0{Colors.ENDC}\n")
    print(f"Type {Colors.BOLD}/help{Colors.ENDC} for commands list, or {Colors.BOLD}/exit{Colors.ENDC} to exit.\n")
    
    while True:
        try:
            line = input(f"{Colors.BOLD}{Colors.BLUE}hipforge>{Colors.ENDC} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
            
        if not line:
            continue
            
        if line.lower() in ("/exit", "/quit"):
            print("Exiting.")
            break
            
        if line.lower() == "/help":
            show_interactive_help()
            continue
            
        if line.lower() == "/clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            continue
            
        if line.lower() == "/history":
            # Try backend history API first; fall back to session list
            fetched = run_history_command(default_host)
            if not fetched and migration_history:
                print(f"\n{Colors.BOLD}{Colors.GOLD}=== Session Migration History ==={Colors.ENDC}")
                for idx, item in enumerate(migration_history, 1):
                    print(f"  [{idx}] ID: {item['id']} | Project: {item['project']} | Arch: {item['arch']}")
                print()
            continue

        if line.lower() == "/info":
            print(f"\n{Colors.BOLD}{Colors.GOLD}=== Console Environment Info ==={Colors.ENDC}")
            print(f"  Backend Host: {default_host}")
            print(f"  Default Arch: {default_arch}")
            print(f"  Retry Budget: {default_attempts} attempts")
            
            # Ping backend
            try:
                resp = requests.get(f"{default_host}/api/v1/health/check", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    print_success("Backend Server connection is ONLINE.")
                    
                    # Redis status
                    redis_check = next((c for c in data.get("checks", []) if c.get("id") == "redis_reachable"), None)
                    if redis_check and redis_check.get("status") == "pass":
                        print_success("Redis Connectivity: ONLINE")
                    else:
                        print_fail("Redis Connectivity: OFFLINE")
                        
                    # Worker status
                    worker_check = next((c for c in data.get("checks", []) if c.get("id") == "worker_reachable"), None)
                    if worker_check and worker_check.get("status") == "pass":
                        print_success("Migration Worker: ONLINE")
                    else:
                        print_warn("Migration Worker: OFFLINE (heartbeat not detected)")
                else:
                    print_warn(f"Backend Server returned status code: {resp.status_code}")
            except Exception as e:
                print_fail(f"Backend Server is OFFLINE: {e}")
            print()
            continue

        if line.startswith("/doctor"):
            parts = shlex.split(line)
            doctor_parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
            doctor_parser.add_argument("--host", type=str, default=default_host)
            doctor_parser.add_argument("--local", action="store_true")
            doctor_parser.add_argument("--json", action="store_true")
            doctor_parser.add_argument("--verbose", action="store_true")
            try:
                doctor_args = doctor_parser.parse_args(parts[1:])
                ok = run_doctor_command(
                    doctor_args.host,
                    local=doctor_args.local,
                    json_output=doctor_args.json,
                    verbose=doctor_args.verbose,
                )
                if not ok:
                    print_warn("Doctor found blocking issues.")
            except Exception as e:
                print_fail(f"Doctor failed: {e}")
            continue

        if line.startswith("/self-test"):
            parts = shlex.split(line)
            self_test_parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
            self_test_parser.add_argument("--host", type=str, default=default_host)
            self_test_parser.add_argument("--arch", type=str, default=None)
            self_test_parser.add_argument("--remote", action="store_true")
            self_test_parser.add_argument("--json", action="store_true")
            self_test_parser.add_argument("--verbose", action="store_true")
            try:
                self_args = self_test_parser.parse_args(parts[1:])
                ok = run_self_test_command(
                    self_args.host,
                    target_arch=self_args.arch,
                    remote=self_args.remote,
                    json_output=self_args.json,
                    verbose=self_args.verbose,
                )
                if not ok:
                    print_warn("Self-test failed.")
            except Exception as e:
                print_fail(f"Self-test failed: {e}")
            continue

        if line.startswith("/set"):
            parts = shlex.split(line)
            if len(parts) < 3:
                print_fail("Usage: /set <key> <value> (keys: host, arch, attempts)")
                continue
            key = parts[1].lower()
            val = parts[2]
            
            if key == "host":
                default_host = val
                print_success(f"Default Host updated to: {default_host}")
            elif key == "arch":
                default_arch = val
                print_success(f"Default Architecture updated to: {default_arch}")
            elif key == "attempts":
                if val.isdigit():
                    default_attempts = int(val)
                    print_success(f"Default Attempts Budget updated to: {default_attempts}")
                else:
                    print_fail("Error: Attempts must be an integer.")
            else:
                print_fail(f"Unknown config key: {key}. Supported: host, arch, attempts")
            continue

        if line.startswith("/cancel"):
            parts = shlex.split(line)
            if len(parts) < 2:
                print_fail("Usage: /cancel <migration_id> [--host <host_url>]")
                continue
            
            cancel_parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
            cancel_parser.add_argument("migration_id", type=str)
            cancel_parser.add_argument("--host", type=str, default=default_host)
            
            try:
                cancel_args = cancel_parser.parse_args(parts[1:])
                url = f"{cancel_args.host}/api/v1/migrate/{cancel_args.migration_id}/cancel"
                resp = requests.post(url)
                if resp.status_code == 200:
                    print_success(f"Cancelled migration: {cancel_args.migration_id}")
                else:
                    print_fail(f"Cancel failed: HTTP {resp.status_code} - {resp.text}")
            except Exception as e:
                print_fail(f"Invalid /cancel command syntax. Use /help.")
            continue

        if line.startswith("/migrate"):
            parts = shlex.split(line)
            parts.pop(0) # remove /migrate
            
            if not parts:
                # Launch the interactive wizard setup!
                print(f"\n{Colors.BOLD}{Colors.GOLD}─── HIPForge Migration Setup Assistant ───{Colors.ENDC}")
                path_input = input(f"{Colors.BOLD}[1/4] Path to project folder or file:{Colors.ENDC} ").strip()
                if not path_input:
                    print_fail("Aborted: Project path is required.")
                    continue
                proj_path = Path(path_input)
                if not proj_path.exists():
                    print_fail(f"Aborted: Target path '{proj_path}' does not exist.")
                    continue
                    
                output_input = input(f"{Colors.BOLD}[2/4] Output folder path for results:{Colors.ENDC} ").strip()
                if not output_input:
                    print_fail("Aborted: Output folder is required.")
                    continue
                out_path = Path(output_input)
                
                print(f"{Colors.BOLD}[3/4] Select Target AMD GPU Architecture:{Colors.ENDC}")
                print("  [1] gfx906 (Vega 20)")
                print("  [2] gfx908 (CDNA 1 / MI100)")
                print("  [3] gfx90a (CDNA 2 / MI200) [Default]")
                print("  [4] gfx940 (CDNA 3 / MI300A)")
                print("  [5] gfx941 (CDNA 3 / MI300X)")
                print("  [6] gfx942 (CDNA 3 / MI300)")
                print("  [7] gfx1030 (RDNA 2 / RX 6000)")
                print("  [8] gfx1100 (RDNA 3 / RX 7000)")
                arch_choice = input(f"{Colors.BOLD}Choice [1-8, or type custom arch name]:{Colors.ENDC} ").strip()
                arch_map = {
                    "1": "gfx906",
                    "2": "gfx908",
                    "3": "gfx90a",
                    "4": "gfx940",
                    "5": "gfx941",
                    "6": "gfx942",
                    "7": "gfx1030",
                    "8": "gfx1100"
                }
                arch = arch_map.get(arch_choice, arch_choice if arch_choice else default_arch)
                
                attempts_input = input(f"{Colors.BOLD}[4/4] Error repair attempts budget [default {default_attempts}]:{Colors.ENDC} ").strip()
                attempts = int(attempts_input) if attempts_input.isdigit() else default_attempts
                
                print_step(f"Executing Wizard Migration: {proj_path} -> {out_path} (Arch: {arch}, Attempts: {attempts})")
                asyncio.run(run_migration(proj_path, arch, out_path, default_host, attempts))
                continue
            
            # Non-interactive command parsed from args
            mig_parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
            mig_parser.add_argument("path", type=str)
            mig_parser.add_argument("output", type=str)
            mig_parser.add_argument("--arch", type=str, default=default_arch)
            mig_parser.add_argument("--attempts", type=int, default=default_attempts)
            mig_parser.add_argument("--host", type=str, default=default_host)
            
            try:
                mig_args = mig_parser.parse_args(parts)
                proj_path = Path(mig_args.path)
                out_path = Path(mig_args.output)
                if not proj_path.exists():
                    print_fail(f"Error: Target path '{proj_path}' does not exist.")
                    continue
                    
                print_step(f"Starting migration: {proj_path} -> {out_path} (target: {mig_args.arch}, budget: {mig_args.attempts})")
                asyncio.run(run_migration(proj_path, mig_args.arch, out_path, mig_args.host, mig_args.attempts))
            except Exception as e:
                print_fail(f"Invalid /migrate command syntax. Use /help to check options.")
            continue
            
        if line.startswith("/status"):
            parts = shlex.split(line)
            if len(parts) < 2:
                print_fail("Usage: /status <migration_id> [--host <host_url>]")
                continue
            
            stat_parser = argparse.ArgumentParser(exit_on_error=False, add_help=False)
            stat_parser.add_argument("migration_id", type=str)
            stat_parser.add_argument("--host", type=str, default=default_host)
            
            try:
                stat_args = stat_parser.parse_args(parts[1:])
                url = f"{stat_args.host}/api/v1/migrate/{stat_args.migration_id}/status"
                resp = requests.get(url)
                if resp.status_code == 200:
                    status_info = resp.json()
                    print_success(f"Status for {stat_args.migration_id}: {status_info.get('status')}")
                else:
                    print_fail(f"Failed to fetch status: HTTP {resp.status_code} - {resp.text}")
            except Exception as e:
                print_fail(f"Invalid /status command syntax. Use /help.")
            continue
            
        print_warn(f"Unknown command '{line}'. Type /help for available commands.")

def main():
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            h_out = kernel32.GetStdHandle(-11) # STD_OUTPUT_HANDLE
            if h_out != -1:
                mode = ctypes.c_uint()
                if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
                    # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                    kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description=f"{Colors.HEADER}HIPForge CLI Tool — Automate CUDA to ROCm/HIP Migrations{Colors.ENDC}"
    )
    subparsers = parser.add_subparsers(dest="command", help="CLI Subcommands")
    
    # Subcommand: start / shell / interactive  (all aliases → same behaviour)
    start_parser = subparsers.add_parser("start", help="Launch interactive shell")
    subparsers.add_parser("shell", help="Launch interactive shell (alias for start)")
    subparsers.add_parser("interactive", help="Launch interactive shell (alias for start)")
    
    # Subcommand: migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run direct migration (B2B/Non-interactive)")
    migrate_parser.add_argument("project_path", type=str, help="Path to CUDA file or folder to migrate")
    migrate_parser.add_argument("--arch", type=str, default="gfx90a", help="Target AMD GPU architecture (default: gfx90a)")
    migrate_parser.add_argument("--attempts", type=int, default=5, help="Number of retry budget attempts (default: 5)")
    migrate_parser.add_argument("--output", type=str, required=True, help="Output directory for translated project")
    migrate_parser.add_argument("--host", type=str, default="http://localhost:8000", help="HIPForge host URL (default: http://localhost:8000)")

    # Subcommand: doctor
    doctor_parser = subparsers.add_parser("doctor", help="Check backend server health (default). Use --local for this machine's toolchain.")
    doctor_parser.add_argument("--host", type=str, default="http://localhost:8000", help="HIPForge host URL")
    doctor_parser.add_argument("--local", action="store_true", help="Run preflight checks on this local machine instead of querying the backend")
    doctor_parser.add_argument("--json", action="store_true", help="Print raw JSON diagnostics")
    doctor_parser.add_argument("--verbose", action="store_true", help="Print every individual check")

    # Subcommand: self-test
    self_test_parser = subparsers.add_parser("self-test", help="Run official HIPForge installation verification")
    self_test_parser.add_argument("--host", type=str, default="http://localhost:8000", help="HIPForge host URL for remote fallback")
    self_test_parser.add_argument("--arch", type=str, default=None, help="Optional target AMD GPU architecture")
    self_test_parser.add_argument("--remote", action="store_true", help="Force using the backend self-test endpoint")
    self_test_parser.add_argument("--json", action="store_true", help="Print raw JSON self-test output")
    self_test_parser.add_argument("--verbose", action="store_true", help="Print every self-test step")

    # Subcommand: history
    history_parser = subparsers.add_parser("history", help="List or inspect previous migrations")
    history_parser.add_argument("--limit", type=int, default=20, help="Number of records to show (default: 20)")
    history_parser.add_argument("--id", type=str, default=None, help="Inspect a specific migration by ID")
    history_parser.add_argument("--host", type=str, default="http://localhost:8000", help="HIPForge host URL")
    
    args = parser.parse_args()

    if args.command in ("start", "shell", "interactive"):
        run_interactive_cli()
    elif args.command == "migrate":
        project_path = Path(args.project_path)
        output_path = Path(args.output)

        if not project_path.exists():
            print_fail(f"Error: Target path '{project_path}' does not exist.")
            sys.exit(1)

        asyncio.run(
            run_migration(project_path, args.arch, output_path, args.host, args.attempts)
        )
    elif args.command == "doctor":
        try:
            ok = run_doctor_command(
                args.host,
                local=args.local,
                json_output=args.json,
                verbose=args.verbose,
                
            )
        except Exception as e:
            print_fail(f"Doctor failed: {e}")
            sys.exit(2)
        sys.exit(0 if ok else 1)
    elif args.command == "self-test":
        try:
            ok = run_self_test_command(
                args.host,
                target_arch=args.arch,
                remote=args.remote,
                json_output=args.json,
                verbose=args.verbose,
            )
        except Exception as e:
            print_fail(f"Self-test failed: {e}")
            sys.exit(2)
        sys.exit(0 if ok else 1)
    elif args.command == "history":
        try:
            ok = run_history_command(
                args.host,
                limit=args.limit,
                job_id=args.id,
            )
        except Exception as e:
            print_fail(f"History failed: {e}")
            sys.exit(2)
        sys.exit(0 if ok else 1)
    else:
        # ponytail: no args / unknown subcommand → help and exit, not an interactive shell
        parser.print_help()
        sys.exit(0)

if __name__ == "__main__":
    main()
