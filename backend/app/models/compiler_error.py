from pydantic import BaseModel

class CompilerError(BaseModel):
    """
    Structured model representing a compilation error/warning.
    Must contain exactly: file, line, column, message, code.
    """
    file: str
    line: int
    column: int
    message: str
    code: str
