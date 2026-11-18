from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.router import router as agent_router
from app.analytics.router import router as analytics_router
from app.api.v1.identity import router as identity_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.system import router as system_router
from app.core.config import get_settings
from app.datasets.router import router as datasets_router

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(system_router, prefix="/api/v1")
app.include_router(identity_router, prefix="/api/v1")
app.include_router(datasets_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")
