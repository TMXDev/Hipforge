import os
import subprocess
import logging
from typing import Dict, Any, List
from app.models.compiler_error import CompilerError
from app.compiler.error_parser import parse_compiler_errors

logger = logging.getLogger("hipcc_runner")

class HipccRunner:
    """Real runner that executes the actual hipcc compiler tool."""
    
    def run_hipcc(self, source_path: str, output_path: str) -> Dict[str, Any]:
        """
        Runs the real hipcc compiler as a subprocess.
        Parses output errors if compiling fails.
        """
        logger.info(f"Running hipcc compiler on {source_path} -> {output_path}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        cmd = ["hipcc", source_path, "-o", output_path]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            success = (result.returncode == 0)
            errors = []
            if not success:
                errors = parse_compiler_errors(result.stderr)
                
            return {
                "success": success,
                "binary_path": output_path if success else "",
                "errors": errors,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except FileNotFoundError:
            err_msg = "hipcc executable not found in system path."
            logger.error(err_msg)
            # Create a fallback CompilerError
            fallback_err = CompilerError(
                file=source_path,
                line=1,
                column=1,
                message=err_msg,
                code="E999"
            )
            return {
                "success": False,
                "binary_path": "",
                "errors": [fallback_err],
                "stdout": "",
                "stderr": err_msg
            }
        except Exception as e:
            err_msg = f"Unexpected subprocess error: {str(e)}"
            logger.exception(err_msg)
            fallback_err = CompilerError(
                file=source_path,
                line=1,
                column=1,
                message=err_msg,
                code="E999"
            )
            return {
                "success": False,
                "binary_path": "",
                "errors": [fallback_err],
                "stdout": "",
                "stderr": err_msg
            }


class MockHipccRunner:
    """Mock compiler used during pre-hackathon mode when ROCm sdk is missing."""
    
    def run_hipcc(self, source_path: str, output_path: str) -> Dict[str, Any]:
        """
        Simulates running hipcc.
        If the file contains the compile error trigger keyword, it generates realistic mock diagnostics,
        runs them through the error parser, and returns success=False.
        Otherwise, writes a dummy file to output_path and returns success=True.
        """
        logger.info(f"[MOCK] run_hipcc called for {source_path} -> {output_path}")
        
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            err_msg = f"Could not read source file: {str(e)}"
            fallback_err = CompilerError(
                file=source_path,
                line=1,
                column=1,
                message=err_msg,
                code="E999"
            )
            return {
                "success": False,
                "binary_path": "",
                "errors": [fallback_err],
                "stdout": "",
                "stderr": err_msg
            }
            
        if "HIPFORGE_MOCK_COMPILE_ERROR" in content:
            logger.info("[MOCK] Triggering mock compilation failure errors.")
            # Format realistic mock compiler output matching clang format
            file_basename = os.path.basename(source_path)
            stderr = (
                f"{file_basename}:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]\n"
                f"{file_basename}:67:12: error: use of undeclared identifier 'hipStreamNonBlocking' [E0020]\n"
            )
            errors = parse_compiler_errors(stderr)
            # Correct the error filenames to point to the actual source file path
            for err in errors:
                err.file = source_path
                
            return {
                "success": False,
                "binary_path": "",
                "errors": errors,
                "stdout": "",
                "stderr": stderr
            }
            
        # Success path: write dummy compiled binary
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("/* HIPForge mock binary */\n")
        except Exception as e:
            err_msg = f"Could not write dummy binary file: {str(e)}"
            fallback_err = CompilerError(
                file=source_path,
                line=1,
                column=1,
                message=err_msg,
                code="E999"
            )
            return {
                "success": False,
                "binary_path": "",
                "errors": [fallback_err],
                "stdout": "",
                "stderr": err_msg
            }
            
        return {
            "success": True,
            "binary_path": output_path,
            "errors": [],
            "stdout": "Mock compilation completed successfully.",
            "stderr": ""
        }

def get_hipcc_runner():
    """Factory function to retrieve the active runner based on environment settings."""
    from app.config.settings import settings
    if settings.USE_MOCK_COMPILER:
        return MockHipccRunner()
    else:
        return HipccRunner()

def run_hipcc(source_path: str, output_path: str) -> Dict[str, Any]:
    """
    Top-level helper function to run hipcc.
    Dispatches to the active runner configured in the environment settings.
    """
    runner = get_hipcc_runner()
    return runner.run_hipcc(source_path, output_path)
