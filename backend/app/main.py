from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.routes import health


# Create FastAPI app instance
def create_app() -> FastAPI:
    app = FastAPI(title="ChatOps API")

    # ── TEMP CORS: allows test_chat_frontend.html to call the API locally ──
    # Remove this block when done testing.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # ── END TEMP CORS ──

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
