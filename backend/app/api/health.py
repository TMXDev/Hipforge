from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/api/v1/health/check")
async def health_check_deep():
    from app.diagnostics import run_preflight

    return run_preflight()


@router.get("/api/v1/doctor")
async def doctor():
    from app.diagnostics import run_preflight

    return run_preflight()


@router.post("/api/v1/self-test")
async def self_test():
    from app.diagnostics import run_self_test

    return run_self_test()
