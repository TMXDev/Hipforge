import os
import time
import pytest
from unittest.mock import patch, MagicMock
from app.compiler.sandbox import run_sandboxed_compiler

@pytest.fixture(autouse=True)
def mock_makedirs():
    with patch("os.makedirs") as mock:
        yield mock

def test_run_sandboxed_compiler_success():
    """Test successful sandboxed compilation execution with mocked docker SDK."""
    workspace_path = "/mock/workspace"
    command = ["hipcc", "/mock/workspace/input/kernel.cu", "-o", "/mock/workspace/generated/output"]

    with patch("docker.from_env") as mock_from_env:
        mock_client = MagicMock()
        mock_container = MagicMock()
        
        # Simulate status transitioning to exited
        mock_container.status = "exited"
        mock_container.logs.side_effect = lambda stdout=False, stderr=False: (
            b"Translated successfully /workspace/generated/output" if stdout else b"no errors"
        )
        mock_container.wait.return_value = {"StatusCode": 0}
        
        mock_client.containers.run.return_value = mock_container
        mock_from_env.return_value = mock_client
        
        result = run_sandboxed_compiler(workspace_path, command, timeout_sec=5)
        
        assert result["returncode"] == 0
        assert "Translated successfully" in result["stdout"]
        # Mapped back to host path
        assert "/mock/workspace/generated/output" in result["stdout"]
        assert result["timeout"] is False
        
        # Verify run configuration
        called_args, called_kwargs = mock_client.containers.run.call_args
        from app.config.settings import settings
        assert called_kwargs["image"] == settings.SANDBOX_IMAGE
        assert called_kwargs["runtime"] == "runsc"
        assert called_kwargs["mem_limit"] == "2g"
        assert called_kwargs["nano_cpus"] == 2000000000
        assert called_kwargs["network_mode"] == "none"
        assert called_kwargs["user"] == "nobody"
        assert called_kwargs["detach"] is True
        
        # Verify volume mounts
        volumes = called_kwargs["volumes"]
        norm_volumes = {k.replace("\\", "/"): v for k, v in volumes.items()}
        assert norm_volumes[os.path.abspath("/mock/workspace/input").replace("\\", "/")]["mode"] == "ro"
        assert norm_volumes[os.path.abspath("/mock/workspace/generated").replace("\\", "/")]["mode"] == "rw"
        assert norm_volumes[os.path.abspath("/mock/workspace/logs").replace("\\", "/")]["mode"] == "rw"
        
        # Verify cleanup was triggered
        mock_container.remove.assert_called_once_with(force=True)


def test_run_sandboxed_compiler_timeout():
    """Test timeout logic when the compiler container hangs."""
    workspace_path = "/mock/workspace"
    command = ["hipcc", "kernel.cu"]

    with patch("docker.from_env") as mock_from_env:
        mock_client = MagicMock()
        mock_container = MagicMock()
        
        # Keep status as running to force timeout
        mock_container.status = "running"
        mock_container.logs.return_value = b""
        mock_container.wait.return_value = {"StatusCode": -1}
        
        mock_client.containers.run.return_value = mock_container
        mock_from_env.return_value = mock_client
        
        # Run with short timeout
        result = run_sandboxed_compiler(workspace_path, command, timeout_sec=0.2)
        
        assert result["timeout"] is True
        assert result["returncode"] == -1
        
        # Verify kill and remove were called
        mock_container.kill.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)


def test_run_sandboxed_compiler_path_translation():
    """Test path mapping translation: host -> container inside command, and container -> host in logs."""
    # Ensure Windows vs Linux separator compatibility
    workspace_path = os.path.abspath("C:/Users/test/workspace")
    input_file = os.path.join(workspace_path, "input", "subdir", "kernel.cu")
    output_file = os.path.join(workspace_path, "generated", "kernel.hip")
    
    command = ["hipify-clang", input_file, "-o", output_file]

    with patch("docker.from_env") as mock_from_env:
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = "exited"
        
        # Return logs containing container paths
        mock_container.logs.side_effect = lambda stdout=False, stderr=False: (
            b"Compiling file: /workspace/input/subdir/kernel.cu to /workspace/generated/kernel.hip"
            if stdout else b""
        )
        mock_container.wait.return_value = {"StatusCode": 0}
        
        mock_client.containers.run.return_value = mock_container
        mock_from_env.return_value = mock_client
        
        result = run_sandboxed_compiler(workspace_path, command, timeout_sec=5)
        
        # Verify command argument translation
        called_args, called_kwargs = mock_client.containers.run.call_args
        called_cmd = called_kwargs["command"]
        
        # Executable remains untouched
        assert called_cmd[0] == "hipify-clang"
        # Input mapped to container path
        assert called_cmd[1] == "/workspace/input/subdir/kernel.cu"
        assert called_cmd[2] == "-o"
        # Output mapped to container path
        assert called_cmd[3] == "/workspace/generated/kernel.hip"
        
        # Logs mapped back to host paths
        expected_input_host = input_file.replace("\\", "/")
        expected_output_host = output_file.replace("\\", "/")
        assert expected_input_host in result["stdout"]
        assert expected_output_host in result["stdout"]
