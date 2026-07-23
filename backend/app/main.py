from fastapi import FastAPI

from app.api import api_router
from app.api.routes import health


# Create FastAPI app instance
def create_app() -> FastAPI:
    app = FastAPI(title="ChatOps API")

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
