"""FastAPI application entry point."""
from fastapi import FastAPI

from real_invest_fl.api.routes.auth import router as auth_router
from real_invest_fl.api.routes.counties import router as counties_router
from real_invest_fl.api.routes.config import router as config_router
from real_invest_fl.api.routes.properties import router as properties_router
from real_invest_fl.api.routes.listings import router as listings_router
from real_invest_fl.api.routes.profiles import router as profiles_router
from real_invest_fl.api.routes.dashboard import router as dashboard_router
from real_invest_fl.api.routes.ingest import router as ingest_router
# from real_invest_fl.api.routes.outreach import router as outreach_router  # pending outreach design session (item 36)

app = FastAPI(
    title="real_invest_fl",
    description="Florida real estate investment property discovery platform.",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(counties_router)
app.include_router(config_router)
app.include_router(properties_router)
app.include_router(listings_router)
app.include_router(profiles_router)
app.include_router(dashboard_router)
app.include_router(ingest_router)
# app.include_router(outreach_router)  # pending outreach design session (item 36)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
