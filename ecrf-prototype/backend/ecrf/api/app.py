"""FastAPI application. Run with:  uvicorn ecrf.api.app:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ecrf import __version__
from ecrf.api import dashboard, data, protocols
from ecrf.config import config
from ecrf.storage import db

app = FastAPI(title="eCRF Pipeline", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(protocols.router)
app.include_router(data.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "backend": config.backend,
            "model": config.llm_model if config.backend != "mock" else "recorded",
            "context_mode": config.context_mode,
            "quote_match_threshold": config.quote_match_threshold}
