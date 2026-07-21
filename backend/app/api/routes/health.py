from fastapi import APIRouter

router = APIRouter(tags=["health"])


# Health check endpoint
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
