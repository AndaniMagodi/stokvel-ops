from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.contributions import router as contributions_router
from app.api.members import router as members_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(contributions_router)
app.include_router(members_router)
