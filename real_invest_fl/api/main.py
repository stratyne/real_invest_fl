"""FastAPI application entry point."""
from fastapi import FastAPI

from real_invest_fl.api.routes.auth import router as auth_router

app = FastAPI(
    title="real_invest_fl",
    description="Florida real estate investment property discovery platform.",
    version="0.1.0",
)

app.include_router(auth_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
