import os
import shutil
import pytest
from unittest.mock import patch, MagicMock
from app.compiler.hipify_runner import run_hipify, HipifyRunner
from app.config.settings import settings

# Paths for testing
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CU = os.path.join(FIXTURES_DIR, "sample.cu")
SAMPLE_ERROR_CU = os.path.join(FIXTURES_DIR, "sample_error.cu")
OUTPUT_HIP = os.path.join(FIXTURES_DIR, "output", "sample.hip")

@pytest.fixture(autouse=True)
def cleanup():
    # Cleanup generated files before and after each test
    output_dir = os.path.dirname(OUTPUT_HIP)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    yield
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)



def test_real_hipify_runner_success():
    """Test HipifyRunner runs subprocess hipify-clang successfully (mocked subprocess)."""
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hipify-clang success output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        runner = HipifyRunner()
        result = runner.run_hipify(SAMPLE_CU, OUTPUT_HIP)
        
        assert result["success"] is True
        assert result["output_path"] == OUTPUT_HIP
        assert result["stdout"] == "hipify-clang success output"
        assert result["stderr"] == ""
        
        # Verify the exact subprocess call
        mock_run.assert_called_once_with(
            ["hipify-clang", SAMPLE_CU, "-o", OUTPUT_HIP, "--"],
            capture_output=True,
            text=True,
            check=False
        )

def test_real_hipify_runner_failure():
    """Test HipifyRunner failure returns exit code and error logs (mocked subprocess)."""
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: parsing error at line 4"
        mock_run.return_value = mock_result
        
        runner = HipifyRunner()
        result = runner.run_hipify(SAMPLE_CU, OUTPUT_HIP)
        
        assert result["success"] is False
        assert result["output_path"] == OUTPUT_HIP
        assert result["stderr"] == "error: parsing error at line 4"

def test_real_hipify_runner_not_found():
    """Test HipifyRunner returns failure if hipify-clang command is missing from system."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        runner = HipifyRunner()
        result = runner.run_hipify(SAMPLE_CU, OUTPUT_HIP)
        
        assert result["success"] is False
        assert "not found" in result["stderr"]

def test_run_hipify_dispatch_success():
    """Test run_hipify dispatcher function works correctly."""
    with patch("app.compiler.hipify_runner.HipifyRunner.run_hipify") as mock_run:
        mock_run.return_value = {"success": True, "output_path": OUTPUT_HIP}
        result = run_hipify(SAMPLE_CU, OUTPUT_HIP)
        assert result["success"] is True
        mock_run.assert_called_once_with(SAMPLE_CU, OUTPUT_HIP)
