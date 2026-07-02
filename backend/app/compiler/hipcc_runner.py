import os
import subprocess
import logging
from typing import Dict, Any, List
from app.models.compiler_error import CompilerError
from app.compiler.error_parser import parse_compiler_errors

logger = logging.getLogger("hipcc_runner")

class HipccRunner:
    """Real runner that executes the actual hipcc compiler tool."""
    
    def run_hipcc(self, source_path: str, output_path: str, target_arch: str = None) -> Dict[str, Any]:
        """
        Runs the real hipcc compiler as a subprocess.
        Parses output errors if compiling fails.
        """
        logger.info(f"Running hipcc compiler on {source_path} -> {output_path} target_arch={target_arch}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        cmd = ["hipcc", source_path, "-o", output_path]
        if target_arch:
            cmd.append(f"--offload-arch={target_arch}")
        
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


def run_hipcc(source_path: str, output_path: str, target_arch: str = None) -> Dict[str, Any]:
    """
    Top-level helper function to run hipcc.
    Instantiates and executes the real HipccRunner tool.
    """
    return HipccRunner().run_hipcc(source_path, output_path, target_arch)

