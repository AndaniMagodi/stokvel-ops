from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.contributions import router as contributions_router
from app.api.members import router as members_router
from app.api.reports import router as reports_router
from app.api.groups import router as groups_router
from app.api.whatsapp import router as whatsapp_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(contributions_router)
app.include_router(members_router)
app.include_router(reports_router)
app.include_router(groups_router)
app.include_router(whatsapp_router)
