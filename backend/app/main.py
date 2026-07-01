from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.api.health import router as health_router
from app.api.router import router as api_router

app = FastAPI(
    title="HIPForge Backend",
    description=(
        "The backend is responsible for exposing REST APIs, managing workspace environments, "
        "running WebSockets for event communication, pushing migration jobs to the Redis task queue, "
        "and serving final report packages."
    ),
    version="1.0"
)

# Custom ASGI middleware for secure HTTP headers
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                security_headers = [
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"no-referrer-when-downgrade"),
                    (b"content-security-policy", b"default-src 'self'; frame-ancestors 'none';"),
                ]
                # Filter out any duplicate headers
                existing_names = {h[0].lower() for h in security_headers}
                headers = [h for h in headers if h[0].lower() not in existing_names]
                headers.extend(security_headers)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

app.add_middleware(SecurityHeadersMiddleware)

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
app.include_router(api_router)

