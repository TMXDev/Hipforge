import os
import re
import base64
import io
import zipfile
from fastapi import HTTPException
from app.config.settings import settings

MIGRATION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
ARCH_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
MODE_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

def validate_migration_id(migration_id: str) -> None:
    """
    Validates that the migration_id contains only alphanumeric characters,
    hyphens, and underscores. Prevents path traversal at the route level.
    """
    if not migration_id or not MIGRATION_ID_PATTERN.match(migration_id):
        raise HTTPException(status_code=400, detail="Invalid migration ID format")

def validate_filename(filename: str) -> None:
    """
    Validates the filename extension and checks for null bytes.
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")
    if "\x00" in filename:
        raise HTTPException(status_code=400, detail="Null bytes are not allowed in filename")
    
    # Path traversal check on filename
    normalized = os.path.normpath(filename)
    if normalized.startswith("..") or "/.." in normalized or "\\.." in normalized or os.path.isabs(filename):
        raise HTTPException(status_code=400, detail="Path traversal attempt detected in filename")

    ext = os.path.splitext(filename)[1]
    if ext.lower() not in (".cu", ".hip", ".cpp", ".cuh", ".h", ".hpp", ".zip"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Supported extensions: .cu, .hip, .cpp, .cuh, .h, .hpp, .zip"
        )

def validate_api_parameters(target_gpu_architecture: str, migration_mode: str, retry_budget: int) -> None:
    """
    Validates request parameters to prevent shell command injection.
    """
    if not ARCH_PATTERN.match(target_gpu_architecture):
        raise HTTPException(status_code=400, detail="Invalid target GPU architecture format")
    if not MODE_PATTERN.match(migration_mode):
        raise HTTPException(status_code=400, detail="Invalid migration mode format")
    if retry_budget < 0 or retry_budget > 20:
        raise HTTPException(status_code=400, detail="Retry budget must be between 0 and 20")

def get_decoded_file_size_and_content(file_str: str) -> tuple[int, bytes]:
    """
    Returns size in bytes and decoded content bytes from base64 or raw string.
    """
    # Strip data URL prefix if any
    if "," in file_str and (file_str.startswith("data:") or "base64" in file_str.split(",")[0]):
        file_str = file_str.split(",", 1)[1]
    
    try:
        # Strict base64 decoding
        decoded = base64.b64decode(file_str.strip(), validate=True)
        return len(decoded), decoded
    except Exception:
        # Fallback to direct raw bytes of the string
        encoded = file_str.encode('utf-8')
        return len(encoded), encoded

def validate_zip_archive(zip_bytes: bytes) -> None:
    """
    Validates zip archive integrity and scans for path traversal attempts inside.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            corrupt_file = zf.testzip()
            if corrupt_file is not None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Corrupt zip archive: file '{corrupt_file}' failed CRC check."
                )
            
            for name in zf.namelist():
                # Check for null bytes in entry name
                if "\x00" in name:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Null bytes are not allowed in zip entry names: '{name}'"
                    )
                
                normalized = os.path.normpath(name)
                # Path traversal checks
                if normalized.startswith("..") or "/.." in normalized or "\\.." in normalized:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path traversal attempt detected in zip archive: '{name}'"
                    )
                if os.path.isabs(name) or name.startswith("/") or name.startswith("\\"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Absolute path or invalid path prefix detected in zip archive: '{name}'"
                    )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Invalid zip archive: not a zip file or file is corrupted."
        )
