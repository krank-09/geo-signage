import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import (
    alerts,
    assignments,
    auth,
    broadcasts,
    cities,
    clients,
    content,
    device_api,
    devices,
    discovery,
    monitoring,
    users,
    ws,
    zones,
)
from .database import SessionLocal, sync_schema
from .seed import seed
from .services.clients import ensure_default_client
from .services.monitor import monitor_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.SECRET_KEY.startswith(("dev-secret", "change-me")):
        log.warning("SECRET_KEY is the built-in default - set a real one before exposing this server")
    if config.DEFAULT_ADMIN_PASSWORD == "admin123":
        log.warning("Admin password is the default 'admin123' - change it in Users > Change my password")
    sync_schema()
    with SessionLocal() as db:
        ensure_default_client(db)
        seed(db)
    task = asyncio.create_task(monitor_loop())
    yield
    task.cancel()


app = FastAPI(title="Geo Signage API", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for router in (auth.router, users.router, devices.router, device_api.router, content.router, zones.router,
               assignments.router, monitoring.router, broadcasts.router, alerts.router, cities.router, discovery.router, clients.router, ws.router):
    app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
