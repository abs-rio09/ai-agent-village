"""HTTP API routers, all mounted under /api.

The router-level `enforce_auth` dependency makes /api default-deny: any route added
here needs a valid session unless its path is on `security.PUBLIC_PATHS`.
"""

from fastapi import APIRouter, Depends

from app.api import auth, health, setup, village
from app.security import enforce_auth

api_router = APIRouter(prefix="/api", dependencies=[Depends(enforce_auth)])
api_router.include_router(health.router)
api_router.include_router(setup.router)
api_router.include_router(auth.router)
api_router.include_router(village.router)
