import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import get_settings
from app.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="RepoWise API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger("repowise.http").exception("request_failed", extra={"request_id": request_id})
        return JSONResponse({"detail": "Internal server error", "request_id": request_id}, status_code=500)
    response.headers["X-Request-ID"] = request_id
    logging.getLogger("repowise.http").info("%s %s %s %.1fms", request.method, request.url.path,
                                           response.status_code, (time.monotonic() - started) * 1000)
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": "repowise"}

