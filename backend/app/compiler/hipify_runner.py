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


def run_hipify(source_path: str, output_path: str) -> Dict[str, Any]:
    """
    Top-level helper function to run hipify. 
    Instantiates and executes the real HipifyRunner tool.
    """
    return HipifyRunner().run_hipify(source_path, output_path)

