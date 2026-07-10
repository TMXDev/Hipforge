# HIPIFY Recovery Fix Documentation

This document explains the fixes implemented for the defects identified in the HIPIFY recovery review in HIPForge.

## Defects Identified & Exact Fixes

### 1. Recoverable HIPIFY retries rerun identical inputs and configuration
- **Defect**: When a recoverable HIPIFY failure occurs (e.g. missing include), it retried using the exact same arguments and inputs, wasting the retry budget.
- **Fix**: Implemented a fingerprinting mechanism (`current_hipify_fingerprint`) that hashes the source files, include paths, CUDA architecture, and CUDA toolkit path. If a HIPIFY invocation fails, its fingerprint is stored. If a subsequent HIPIFY invocation has the identical fingerprint, the retry is rejected to prevent wasting the retry budget.

### 2. Semantic patches produced after a HIPIFY failure are not used by the next HIPIFY invocation
- **Defect**: When HIPIFY fails and AI produces a semantic patch, the workflow transitions back to HIPIFY, but `handle_hipify` ignored the patch and re-translated the original unpatched CUDA source, discarding the patch.
- **Fix**: Updated `handle_hipify` to copy patches back to the generated migration workspace (`generated/` directory) and verify if a patch exists for each file. If a patch exists, the HIPIFY stage reads the patched source directly and skips the `run_hipify` invocation for that file.

### 3. Semantic HIPIFY recovery increments the retry counter twice for one repair
- **Defect**: HIPIFY failure routed to `ANALYZING` incremented `current_attempt` once, and `handle_patching` incremented it again before running compilation or HIPIFY again.
- **Fix**: Adjusted transitions in `determine_next_state` so that `current_attempt` is only incremented when performing a direct recoverable configuration retry (`HIPIFY` -> `HIPIFY`). For semantic AI recovery (`HIPIFY` -> `ANALYZING`), the increment is deferred to `handle_patching`, ensuring exactly one increment per repair cycle.

### 4. discover_include_dirs() accepts escaping symlinks or Windows junctions
- **Defect**: `discover_include_dirs()` accepted include candidates containing symlinks or Windows junctions whose resolved paths escaped the project root.
- **Fix**: Refactored include candidate path validation to canonicalize all candidate directories using `.resolve()` and verify they are relative to the canonical project root using `.is_relative_to(input_dir_abs)`. Any directory that escapes the project root is rejected and not traversed or added.

### 5. Overstated recovery behavior and incorrect untouched archive state in documentation
- **Defect**: Previous documentation incorrectly stated that uploaded archives remain untouched, whereas the source ZIP is unlinked (deleted) after extraction, while only the extracted source files are preserved unmodified.
- **Fix**: Corrected this documentation to state that the uploaded ZIP archive is removed after safe extraction, while the extracted source files remain unmodified.

---

## Changed Files

1. [hipify_runner.py](file:///c:/Users/Yassi/Downloads/HIPForge/backend/app/compiler/hipify_runner.py)
   - Secure include directory discovery logic against path traversal by canonicalizing and checking containment of all paths under the project root.
2. [states.py](file:///c:/Users/Yassi/Downloads/HIPForge/backend/app/workflow_engine/states.py)
   - Updated `handle_hipify()` to apply patches to the generated directory and skip `run_hipify` (consuming the patched source) if a patch file exists.
   - Fixed `copy_patches_to_generated()` to create parent directories.
3. [transitions.py](file:///c:/Users/Yassi/Downloads/HIPForge/backend/app/workflow_engine/transitions.py)
   - Updated `determine_next_state()` to prevent retries on identical fingerprints and to only increment retry counters once per repair cycle.
4. [HIPIFY_RECOVERY_FIX.md](file:///c:/Users/Yassi/Downloads/HIPForge/docs/HIPIFY_RECOVERY_FIX.md)
   - Updated this documentation to align with correct system behavior.

---

## Regression Tests

Focused regression tests were added in `tests/backend/test_ponytail_fixes.py`:
- `test_identical_recoverable_hipify_not_repeated`: Verifies that identical recoverable HIPIFY failures are not retried repeatedly.
- `test_changed_config_permits_retry`: Verifies that if configuration changes (e.g. include path added), a retry is permitted.
- `test_semantic_patch_consumed_by_next_hipify`: Verifies that a semantic patch is consumed and read by the next HIPIFY invocation.
- `test_one_semantic_recovery_one_retry`: Verifies that a semantic recovery cycle increments the retry counter exactly once.
- `test_escaping_include_paths_rejected`: Verifies that symlinks/junctions escaping the project root are rejected.
- `test_local_include_paths_accepted`: Verifies that local (internal) include paths are still successfully accepted.

---

## Verification Results

### Automated Tests Result
Run command:
```powershell
$env:PYTHONPATH="backend"; .venv\Scripts\python -m pytest tests/backend/test_ponytail_fixes.py
```
**Status**: 100% Passed.

### E2E Migration Result
Run command:
```powershell
docker compose up --build -d
.venv\Scripts\python cli/hipforge.py migrate C:\Users\Yassi\Downloads\cuda-mini-test.zip --output migration_output
```
**Status**: Succeeded. Output ZIP generated in `migration_output/`.

---

## Hackathon Live Demo Instructions

To run the live demo with actual AI components and compilers:

1. **Verify Compiler Settings**:
   Ensure `USE_MOCK_COMPILER=false` is set in the `.env` file to validate code with the real ROCm compiler toolchain.

2. **Enable Live AI (without exposing API keys)**:
   Avoid committing private API keys to any shared `.env` files. Instead, set the API key in the process-level environment variable of the terminal shell where the FastAPI backend and workers are launched:
   - **PowerShell (Windows)**:
     ```powershell
     $env:FIREWORKS_API_KEY="your_actual_api_key"
     $env:USE_MOCK_AI="false"
     ```
   - **Bash (Linux/macOS)**:
     ```bash
     export FIREWORKS_API_KEY="your_actual_api_key"
     export USE_MOCK_AI="false"
     ```
   This ensures `USE_MOCK_AI=false` executes with a valid Fireworks API client, without saving sensitive keys to version-controlled files.

---

## Remaining Risks & Limitations

- **External Tools & Environment Dependencies**: Projects that depend on system-level libraries or toolchains not present in the Docker sandbox or the host path will fail during the compile stage.
- **Unreachable Symlinks**: Valid symbolic links to external files/directories outside the workspace root will be rejected for security, which may prevent projects with complex out-of-tree builds from resolving their headers.
