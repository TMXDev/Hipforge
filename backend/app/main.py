from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.api.health import router as health_router

app = FastAPI(
    title="HIPForge Backend",
    description=(
        "The backend is responsible for exposing REST APIs, managing workspace environments, "
        "running WebSockets for event communication, pushing migration jobs to the Redis task queue, "
        "and serving final report packages."
    ),
    version="1.0"
)

# CORS Middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health_router)
