import os
import subprocess
import logging
from typing import Dict, Any

logger = logging.getLogger("hipify_runner")

class HipifyRunner:
    """Real runner that executes the actual hipify-clang command line tool."""
    
    def run_hipify(self, source_path: str, output_path: str) -> Dict[str, Any]:
        """
        Runs the real hipify-clang tool as a subprocess on the given source file.
        Returns a dictionary with execution results.
        """
        logger.info(f"Running hipify-clang on {source_path} -> {output_path}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        cmd = ["hipify-clang", source_path, "-o", output_path, "--"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            success = (result.returncode == 0)
            return {
                "success": success,
                "output_path": output_path,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except FileNotFoundError:
            # If hipify-clang command is not found in system
            err_msg = "hipify-clang executable not found in system path."
            logger.error(err_msg)
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": err_msg
            }
        except Exception as e:
            err_msg = f"Unexpected subprocess error: {str(e)}"
            logger.exception(err_msg)
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": err_msg
            }


class MockHipifyRunner:
    """Mock runner used during pre-hackathon mode when compiler toolchain is missing."""
    
    def run_hipify(self, source_path: str, output_path: str) -> Dict[str, Any]:
        """
        Simulates running hipify-clang. 
        It writes a plausible HIP file by replacing 'cuda' with 'hip' in the source.
        Returns success=False if the source contains the mock failure trigger.
        """
        logger.info(f"[MOCK] run_hipify called for {source_path} -> {output_path}")
        
        # Read source file
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            err_msg = f"Could not read source file: {str(e)}"
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": err_msg
            }
            
        # Check for mock failure trigger
        if "HIPFORGE_MOCK_COMPILE_ERROR" in content:
            logger.info("[MOCK] Triggering mock compilation failure comment in source.")
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": "error: hipify-clang mock failure triggered by source comment"
            }
            
        # Write translated file (replace cuda/CUDA with hip/HIP)
        translated = (
            content
            .replace("cuda", "hip")
            .replace("Cuda", "Hip")
            .replace("CUDA", "HIP")
            .replace("cuda_runtime.h", "hip/hip_runtime.h")
        )
        
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated)
        except Exception as e:
            err_msg = f"Could not write output file: {str(e)}"
            return {
                "success": False,
                "output_path": output_path,
                "stdout": "",
                "stderr": err_msg
            }
            
        return {
            "success": True,
            "output_path": output_path,
            "stdout": "Mock translation completed successfully.",
            "stderr": ""
        }

def get_hipify_runner():
    """Factory function to retrieve the active runner based on environment settings."""
    from app.config.settings import settings
    if settings.USE_MOCK_COMPILER:
        return MockHipifyRunner()
    else:
        return HipifyRunner()

def run_hipify(source_path: str, output_path: str) -> Dict[str, Any]:
    """
    Top-level helper function to run hipify. 
    Dispatches to the active runner configured in the environment settings.
    """
    runner = get_hipify_runner()
    return runner.run_hipify(source_path, output_path)
