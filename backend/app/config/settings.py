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
    FIREWORKS_API_BASE: str = os.getenv("FIREWORKS_API_BASE", "https://api.fireworks.ai/inference/v1")
    FIREWORKS_MODEL: str = os.getenv(
        "FIREWORKS_MODEL",
        "accounts/fireworks/models/qwen2p5-coder-32b-instruct",
    )

    # Toolchain / sandbox settings
    USE_MOCK_AI: bool = os.getenv("USE_MOCK_AI", "false").lower() == "true"
    USE_MOCK_COMPILER: bool = os.getenv("USE_MOCK_COMPILER", "false").lower() == "true"
    SANDBOX_IMAGE: str = os.getenv("HIPFORGE_SANDBOX_IMAGE", "rocm/dev-ubuntu-22.04")
    ALLOW_RUNSC_FALLBACK: bool = os.getenv("ALLOW_RUNSC_FALLBACK", "true").lower() == "true"
    REQUIRE_HOST_HIPIFY: bool = os.getenv("REQUIRE_HOST_HIPIFY", "false").lower() == "true"
    REQUIRE_NINJA: bool = os.getenv("REQUIRE_NINJA", "false").lower() == "true"
    MIN_FREE_DISK_BYTES: int = int(os.getenv("HIPFORGE_MIN_FREE_DISK_BYTES", str(512 * 1024 * 1024)))



    # GPU Pinning Configuration
    HIP_VISIBLE_DEVICES: str = os.getenv("HIP_VISIBLE_DEVICES", "0")

    # CORS Configurations
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    ]

    @property
    def max_file_size_bytes(self) -> int:
        limit = self.WORKSPACE_SIZE_LIMIT
        if not limit:
            return 100 * 1024 * 1024
        limit = limit.upper().strip()
        multiplier = 1
        if limit.endswith("GB"):
            multiplier = 1024 * 1024 * 1024
            limit = limit[:-2]
        elif limit.endswith("MB"):
            multiplier = 1024 * 1024
            limit = limit[:-2]
        elif limit.endswith("KB"):
            multiplier = 1024
            limit = limit[:-2]
        elif limit.endswith("B"):
            limit = limit[:-1]
        try:
            return int(limit) * multiplier
        except ValueError:
            return 100 * 1024 * 1024

    def validate(self) -> None:
        if not self.USE_MOCK_AI and (
            not self.FIREWORKS_API_KEY
            or self.FIREWORKS_API_KEY.strip() in ("", "your_fireworks_api_key")
        ):
            raise ValueError("FIREWORKS_API_KEY must be set to a valid Fireworks API key.")

settings = Settings()
