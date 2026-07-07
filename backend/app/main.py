from fastapi import FastAPI

app = FastAPI(title="ChatOps API")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "ChatOps API"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
