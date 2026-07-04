import pytest
from pathlib import Path
from app.workflow_engine.states import get_cached_patch, write_cached_patch, PATCH_CACHE_DIR

def test_patch_cache_roundtrip():
    unpatched = "int main() { return 0; } // unpatched code"
    patched = "int main() { return 0; } // patched code successfully compiled"
    
    # 1. Clean cache before test
    import hashlib
    h = hashlib.sha256(unpatched.encode("utf-8")).hexdigest()
    test_file = PATCH_CACHE_DIR / f"{h}.txt"
    if test_file.exists():
        test_file.unlink()
        
    # 2. Get before write should return None
    assert get_cached_patch(unpatched) is None
    
    # 3. Write cached patch
    write_cached_patch(unpatched, patched)
    
    # 4. Get after write should return patched content
    assert get_cached_patch(unpatched) == patched
    
    # 5. Clean up
    if test_file.exists():
        test_file.unlink()
