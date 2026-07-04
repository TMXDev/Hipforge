# HIPForge Demo Readiness Notes

Last verified: 2026-07-03

This file is the honest demo-status snapshot for HIPForge. It is scoped to
hackathon / YC-style demo stability only. It does not claim production
readiness, real ROCm completion, or full browser automation unless those checks
were actually run.

## Current Summary

| Area | Status | Evidence |
| --- | --- | --- |
| Docker Compose config | PASS | `docker compose config` completed successfully. |
| Redis service | PASS | `docker compose up -d redis` and `docker compose ps` showed Redis running. |
| Backend import | PASS | `python -c "import sys; sys.path.insert(0, 'backend'); from app.main import app; print('backend import ok')"` printed `backend import ok`. |
| Backend startup | PASS | Temporary uvicorn on `127.0.0.1:18000` started and `/health` returned `{"status":"ok"}`. |
| Worker startup | PASS | Temporary worker entered its loop with `BRPOP timeout=1s`. |
| CLI help | PASS | `python cli/hipforge.py --help` printed subcommands. |
| CLI mock self-test | PASS | Mock self-test completed with `success: true`. |
| Frontend install/build | PASS | `npm install` completed and `npm run build` completed successfully. |
| Web UI HTTP route | PASS | `GET http://localhost:3000/` returned 200 and included `HIPForge`. |
| Upload page HTTP route | PASS | `GET http://localhost:3000/upload` returned 200 and upload indicators were present. |
| Dashboard HTTP route | PASS | `GET http://localhost:3000/migration/<id>` returned 200 and dashboard indicators were present. |
| Browser automation | NOT EXECUTED | Playwright / in-app browser target was unavailable in this Codex session. HTTP route checks are not a browser pass. |
| Mock API upload | PASS | Isolated mock backend + worker accepted a small CUDA file and reached `COMPLETED`. |
| Real ROCm mode | NOT READY | Current real-mode doctor reports missing CUDA Toolkit, `cuda_runtime.h`, and `libdevice` in the sandbox. |

## Verified Commands

Run from the repository root unless noted.

```powershell
git status -sb
git log --oneline -3
git diff --stat HEAD
docker compose config
docker compose up -d redis
docker compose ps
python -c "import sys; sys.path.insert(0, 'backend'); from app.main import app; print('backend import ok')"
python cli/hipforge.py --help
cd frontend
npm install
npm run build
```

Additional checks were run for startup and mock mode:

```powershell
$env:PYTHONPATH='backend'
$env:REDIS_URL='redis://localhost:4444/15?protocol=2'
python -m uvicorn app.main:app --host 127.0.0.1 --port 18000 --log-level info

$env:USE_MOCK_AI='true'
$env:USE_MOCK_COMPILER='true'
$env:MIGRATION_WORKER_TIMEOUT='1'
python -m app.workers.migration_worker
```

The mock upload verification used a temporary local backend on port `18001`, a
temporary worker, and Redis DB 15. The submitted file was `mock_demo.cu`. The
job reached:

```text
status=COMPLETED
stage=COMPLETED
journal entries=8
compiler log entries=2
```

## Demo Modes

### Mock Mode Prepared

Mock mode is the reliable demo path today. It was verified through:

- CLI self-test with `USE_MOCK_AI=true` and `USE_MOCK_COMPILER=true`.
- API upload of a small CUDA file through a temporary mock backend and worker.
- Worker execution through preflight, hipify, SCA, compile, and report
  generation, ending in `COMPLETED`.

For a Web UI mock demo, make sure `.env` sets:

```env
USE_MOCK_AI=true
USE_MOCK_COMPILER=true
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Then restart/rebuild the stack before demonstrating the browser flow.

### Real ROCm Mode Not Verified

The current `.env` is configured for real mode:

```env
USE_MOCK_AI=false
USE_MOCK_COMPILER=false
```

`python cli/hipforge.py doctor --json` now confirms Docker and Fireworks are
reachable, but real migrations are still `NOT_READY` because the sandbox is
missing:

- CUDA Toolkit
- `cuda_runtime.h`
- `libdevice`

Do not claim real ROCm migration works until those dependencies are installed
inside the configured sandbox image and `hipforge doctor` plus `hipforge
self-test` pass in real mode.

## Browser Status

Browser test: NOT EXECUTED.

Reason: the Playwright / in-app browser target was unavailable in this Codex
session. I did not use Chrome as a substitute browser pass.

Manual browser verification steps:

1. Start the app with the desired mode in `.env`.
2. Open `http://localhost:3000`.
3. Confirm the homepage renders without a crash.
4. Open `http://localhost:3000/upload`.
5. Confirm the upload form, paste mode, GPU selector, retry selector, and start
   button are visible.
6. In mock mode, submit a tiny `.cu` file.
7. Confirm redirect to `/migration/<migration_id>`.
8. Confirm the status/timeline and log panels are visible.
9. Confirm the migration reaches `COMPLETED`, or record the exact blocker.

## Known Limitations

- Real ROCm mode is blocked by missing CUDA compatibility files in the sandbox.
- gVisor `runsc` is not installed; Docker default runtime fallback is allowed.
- Host `hipify-clang` is not on PATH on this Windows host, but sandbox
  `hipify-clang` is available.
- Browser automation was not executed in this session.
- `npm install` reported audit warnings: 2 moderate and 6 high vulnerabilities.

## Exact Next Step

For the project owner: decide the demo mode.

Use mock mode for the pitch demo today. For real ROCm mode, rebuild or replace
the sandbox image so CUDA Toolkit compatibility files, `cuda_runtime.h`, and
`libdevice` are present, then rerun:

```powershell
python cli/hipforge.py doctor --json
python cli/hipforge.py self-test --json --arch gfx90a
```
