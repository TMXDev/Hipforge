import os
import shutil
import pytest
from unittest.mock import patch, MagicMock
from app.compiler.hipcc_runner import run_hipcc, HipccRunner
from app.compiler.error_parser import parse_compiler_errors
from app.models.compiler_error import CompilerError
from app.config.settings import settings

# Paths for testing
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_HIP = os.path.join(FIXTURES_DIR, "sample.hip")
SAMPLE_ERROR_HIP = os.path.join(FIXTURES_DIR, "sample_error.hip")
OUTPUT_BINARY = os.path.join(FIXTURES_DIR, "output", "sample.bin")

@pytest.fixture(autouse=True)
def cleanup(monkeypatch):
    monkeypatch.setenv("USE_MOCK_COMPILER", "false")
    monkeypatch.setenv("DISABLE_COMPILER_CACHE", "true")
    output_dir = os.path.dirname(OUTPUT_BINARY)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    yield
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

def test_error_parser_basic():
    """Verify that the error parser extracts details from standard compiler output."""
    stderr = (
        "kernel.hip:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]\n"
        "kernel.hip:67:12: error: use of undeclared identifier 'hipStreamNonBlocking' [E0020]\n"
        "some info warning line without match\n"
        "another/file.hip:100:15: fatal error: missing semicolon [E0001]\n"
    )
    errors = parse_compiler_errors(stderr)
    
    assert len(errors) == 3
    
    assert errors[0].file == "kernel.hip"
    assert errors[0].line == 42
    assert errors[0].column == 8
    assert errors[0].message == "no matching function for call to 'hipMemcpyAsync'"
    assert errors[0].code == "E0308"
    
    assert errors[1].file == "kernel.hip"
    assert errors[1].line == 67
    assert errors[1].column == 12
    assert errors[1].message == "use of undeclared identifier 'hipStreamNonBlocking'"
    assert errors[1].code == "E0020"
    
    assert errors[2].file == "another/file.hip"
    assert errors[2].line == 100
    assert errors[2].column == 15
    assert errors[2].message == "missing semicolon"
    assert errors[2].code == "E0001"



def test_real_hipcc_runner_success():
    """Verify HipccRunner runs subprocess compile with correct arguments (mocked sandbox)."""
    with patch("app.compiler.sandbox.run_sandboxed_compiler") as mock_sandbox:
        mock_sandbox.return_value = {
            "returncode": 0,
            "stdout": "hipcc compiled success",
            "stderr": ""
        }
        
        runner = HipccRunner()
        result = runner.run_hipcc(SAMPLE_HIP, OUTPUT_BINARY)
        
        assert result["success"] is True
        assert result["binary_path"] == OUTPUT_BINARY
        assert len(result["errors"]) == 0
        
        mock_sandbox.assert_called_once()

def test_real_hipcc_runner_failure():
    """Verify HipccRunner parsing error logs on failed compile (mocked sandbox)."""
    with patch("app.compiler.sandbox.run_sandboxed_compiler") as mock_sandbox:
        mock_sandbox.return_value = {
            "returncode": 1,
            "stdout": "",
            "stderr": f"{SAMPLE_HIP}:10:5: error: missing token [E444]\n"
        }
        
        runner = HipccRunner()
        result = runner.run_hipcc(SAMPLE_HIP, OUTPUT_BINARY)
        
        assert result["success"] is False
        assert len(result["errors"]) == 1
        assert result["errors"][0].file == SAMPLE_HIP
        assert result["errors"][0].line == 10
        assert result["errors"][0].column == 5
        assert result["errors"][0].message == "missing token"
        assert result["errors"][0].code == "E444"

def test_run_hipcc_dispatch():
    """Verify dispatch logic works correctly."""
    with patch("app.compiler.hipcc_runner.HipccRunner.run_hipcc") as mock_run:
        mock_run.return_value = {"success": True, "binary_path": OUTPUT_BINARY, "errors": []}
        result = run_hipcc(SAMPLE_HIP, OUTPUT_BINARY)
        assert result["success"] is True
        mock_run.assert_called_once_with(SAMPLE_HIP, OUTPUT_BINARY, None, None)
