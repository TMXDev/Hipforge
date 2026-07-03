import os
import time
import logging
import docker
from typing import Dict, Any, List
from app.config.settings import settings

logger = logging.getLogger("sandbox")

def run_sandboxed_compiler(workspace_path: str, command: List[str], timeout_sec: int = 30, working_dir: str = None) -> Dict[str, Any]:
    """
    Executes a compiler tool safely inside an isolated Docker sandbox using gVisor.
    """
    # Canonicalize host directory paths
    host_workspace = os.path.abspath(workspace_path)
    host_input = os.path.abspath(os.path.join(host_workspace, "input"))
    host_generated = os.path.abspath(os.path.join(host_workspace, "generated"))
    host_logs = os.path.abspath(os.path.join(host_workspace, "logs"))
    host_patches = os.path.abspath(os.path.join(host_workspace, "patches"))

    # Ensure host directories exist
    os.makedirs(host_input, exist_ok=True)
    os.makedirs(host_generated, exist_ok=True)
    os.makedirs(host_logs, exist_ok=True)
    os.makedirs(host_patches, exist_ok=True)

    # Lowercase and forward-slash normalized versions for Windows compatibility
    host_input_norm = host_input.lower().replace("\\", "/")
    host_generated_norm = host_generated.lower().replace("\\", "/")
    host_logs_norm = host_logs.lower().replace("\\", "/")
    host_patches_norm = host_patches.lower().replace("\\", "/")

    # Translate host paths in command arguments to container paths
    container_command = []
    for arg in command:
        if not isinstance(arg, str):
            container_command.append(arg)
            continue
        
        canonical_arg = os.path.abspath(arg) if os.path.isabs(arg) or "workspace" in arg else arg
        if isinstance(canonical_arg, str) and (os.path.isabs(canonical_arg) or ":" in canonical_arg or canonical_arg.replace("\\", "/").startswith("/")):
            arg_norm = canonical_arg.lower().replace("\\", "/")
            if arg_norm.startswith(host_input_norm):
                rel = arg_norm[len(host_input_norm):].lstrip("/")
                canonical_arg = "/workspace/input/" + rel
            elif arg_norm.startswith(host_generated_norm):
                rel = arg_norm[len(host_generated_norm):].lstrip("/")
                canonical_arg = "/workspace/generated/" + rel
            elif arg_norm.startswith(host_logs_norm):
                rel = arg_norm[len(host_logs_norm):].lstrip("/")
                canonical_arg = "/workspace/logs/" + rel
            elif arg_norm.startswith(host_patches_norm):
                rel = arg_norm[len(host_patches_norm):].lstrip("/")
                canonical_arg = "/workspace/patches/" + rel
        
        container_command.append(canonical_arg)

    # Define volumes mounting mapping
    volumes = {
        host_input: {"bind": "/workspace/input", "mode": "ro"},
        host_generated: {"bind": "/workspace/generated", "mode": "rw"},
        host_logs: {"bind": "/workspace/logs", "mode": "rw"},
        host_patches: {"bind": "/workspace/patches", "mode": "rw"},
    }

    # Translate working_dir path to container path if it is a host path
    container_working_dir = None
    if working_dir:
        working_dir_norm = os.path.abspath(working_dir).lower().replace("\\", "/")
        host_input_norm = host_input.lower().replace("\\", "/")
        host_generated_norm = host_generated.lower().replace("\\", "/")
        host_logs_norm = host_logs.lower().replace("\\", "/")
        host_patches_norm = host_patches.lower().replace("\\", "/")
        
        if working_dir_norm.startswith(host_generated_norm):
            rel = working_dir_norm[len(host_generated_norm):].lstrip("/")
            container_working_dir = "/workspace/generated/" + rel
        elif working_dir_norm.startswith(host_input_norm):
            rel = working_dir_norm[len(host_input_norm):].lstrip("/")
            container_working_dir = "/workspace/input/" + rel
        elif working_dir_norm.startswith(host_logs_norm):
            rel = working_dir_norm[len(host_logs_norm):].lstrip("/")
            container_working_dir = "/workspace/logs/" + rel
        elif working_dir_norm.startswith(host_patches_norm):
            rel = working_dir_norm[len(host_patches_norm):].lstrip("/")
            container_working_dir = "/workspace/patches/" + rel
        else:
            container_working_dir = working_dir

    client = None
    container = None
    try:
        # Initialize official Docker client
        client = docker.from_env()
        
        logger.info(
            f"Spawning compiler sandbox (gVisor) for workspace: {host_workspace}. "
            f"Command: {container_command} (working_dir: {container_working_dir})"
        )

        # Check if gVisor (runsc) is available in the Docker runtimes list
        runtimes = client.info().get("Runtimes", {})
        runtime = "runsc" if "runsc" in runtimes else None
        if not runtime:
            logger.warning("gVisor (runsc) runtime not found in Docker. Falling back to default runtime.")

        # Run container under runsc (gVisor) if available, network none, nobody user, 2GB memory, 2 CPU cores
        container = client.containers.run(
            image=settings.SANDBOX_IMAGE,
            command=container_command,
            runtime=runtime,
            mem_limit="2g",
            nano_cpus=2000000000, # 2 CPU cores in nano units (2 * 10^9)
            network_mode="none",
            user="nobody",
            volumes=volumes,
            working_dir=container_working_dir,
            detach=True,
            stdout=True,
            stderr=True,
        )

        start_time = time.time()
        timed_out = False
        
        # Poll container execution state
        while True:
            container.reload()
            if container.status == "exited":
                break
            if time.time() - start_time > timeout_sec:
                timed_out = True
                break
            time.sleep(0.1)

        # Enforce timeout and terminate container if still running
        if timed_out:
            logger.warning(f"Compiler sandbox timed out after {timeout_sec}s. Terminating container...")
            try:
                container.kill()
            except Exception as ke:
                logger.error(f"Error terminating container: {ke}")

        # Capture output logs
        stdout_bytes = container.logs(stdout=True, stderr=False)
        stderr_bytes = container.logs(stdout=False, stderr=True)

        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        # Map container paths back to host paths for error parsers
        def map_to_host(text: str) -> str:
            if not text:
                return text
            # Replace Linux forward slashes mapping
            text = text.replace("/workspace/input", host_input.replace("\\", "/"))
            text = text.replace("/workspace/generated", host_generated.replace("\\", "/"))
            text = text.replace("/workspace/logs", host_logs.replace("\\", "/"))
            return text

        stdout_str = map_to_host(stdout_str)
        stderr_str = map_to_host(stderr_str)

        # Fetch return code
        try:
            exit_status = container.wait()
            returncode = exit_status.get("StatusCode", -1) if not timed_out else -1
        except Exception:
            returncode = -1

        return {
            "returncode": returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "timeout": timed_out,
        }

    except Exception as e:
        logger.exception(f"Failed to execute sandboxed compiler: {e}")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Docker sandbox error: {str(e)}",
            "timeout": False,
        }

    finally:
        # Guarantee instant cleanup/removal of the container
        if container is not None:
            try:
                container.remove(force=True)
            except Exception as re:
                logger.error(f"Failed to remove sandbox container: {re}")
