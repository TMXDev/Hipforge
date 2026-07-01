import re
from typing import List
from app.models.compiler_error import CompilerError

# Regular expression to extract compiler diagnostics matching Clang/GCC formats:
# Example: kernel.hip:42:8: error: no matching function for call to 'hipMemcpyAsync' [E0308]
DIAGNOSTIC_PATTERN = re.compile(
    r"^(?P<file>(?:[a-zA-Z]:)?[^:\n]+):(?P<line>\d+):(?P<column>\d+):\s+(?:fatal\s+)?error:\s+(?P<message>.*?)(?:\s+\[(?P<code>[^\]\n]+)\])?$"
)

def parse_compiler_errors(stderr: str) -> List[CompilerError]:
    """
    Parses stderr output from a compiler and extracts structured CompilerError models.
    Matches lines formatted like 'file:line:col: error: msg [code]'.
    """
    errors = []
    if not stderr:
        return errors
        
    for line in stderr.splitlines():
        line = line.strip()
        match = DIAGNOSTIC_PATTERN.match(line)
        if match:
            gd = match.groupdict()
            # If no code is explicitly matched in brackets, default to empty string
            code = gd.get("code") or ""
            errors.append(CompilerError(
                file=gd["file"],
                line=int(gd["line"]),
                column=int(gd["column"]),
                message=gd["message"],
                code=code
            ))
            
    return errors
