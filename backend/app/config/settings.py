import os

class Settings:
    # Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")

    # Workspace settings
    WORKSPACE_PATH: str = os.getenv("WORKSPACE_PATH", "/app/workspace")
    WORKSPACE_SIZE_LIMIT: str = os.getenv("WORKSPACE_SIZE_LIMIT", "100MB")

    # Migration defaults
    DEFAULT_RETRY_BUDGET: int = int(os.getenv("DEFAULT_RETRY_BUDGET", "5"))

    # Logging and server configurations
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    NEXT_PUBLIC_BACKEND_URL: str = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:8000")

    # AI Infrastructure settings
    FIREWORKS_API_KEY: str = os.getenv("FIREWORKS_API_KEY", "your_fireworks_api_key")

    # Pre-hackathon / Mock settings
    USE_MOCK_AI: bool = os.getenv("USE_MOCK_AI", "true").lower() in ("true", "1", "yes")
    USE_MOCK_COMPILER: bool = os.getenv("USE_MOCK_COMPILER", "true").lower() in ("true", "1", "yes")

    # GPU Pinning Configuration
    HIP_VISIBLE_DEVICES: str = os.getenv("HIP_VISIBLE_DEVICES", "0")

    # CORS Configurations
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    ]

settings = Settings()
