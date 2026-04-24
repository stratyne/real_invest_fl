"""FastAPI application entry point."""
from fastapi import FastAPI

app = FastAPI(
    title="real_invest_fl",
    description="Florida real estate investment property discovery platform.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
