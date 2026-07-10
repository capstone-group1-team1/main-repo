"""
main.py — FastAPI app assembly with an explicit lifespan.

    uvicorn app.main:app --port 8000        (from the backend/ folder)

The lifespan context opens the expensive resources ONCE at startup (Neo4j
driver, Weaviate client, embedding model) and closes them cleanly at
shutdown. They live on app.state and are handed to path operations via
Depends() injectors — the Module 10 pattern. Connection *settings* still come
only from core/config.py (single source), so the Stage 2 migration stays a
config-only change.

Also wires the three observability middlewares (request-id, structured
logging, metrics), the /metrics endpoint, and the /healthz (liveness) +
/readyz (readiness) probes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_admin, routes_chat, routes_devices, routes_incidents
from app.core.config import (get_embed_model, get_neo4j_driver, get_settings,
                             get_weaviate_client)
from app.core.logging import configure_logging, get_logger
from app.core.observability import (MetricsMiddleware, RequestIdMiddleware,
                                    StructuredLoggingMiddleware,
                                    metrics_asgi_app)

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup: open shared resources once, in explicit order ---
    log.info("startup: opening Neo4j driver, Weaviate client, embed model")
    app.state.neo4j_driver = get_neo4j_driver()
    app.state.weaviate_client = get_weaviate_client()
    app.state.embed_model = get_embed_model()      # warm now, not on 1st request
    # Warm the cross-encoder reranker too (None if disabled) so the first
    # query doesn't pay the model-load cost.
    from app.core.config import get_reranker_model
    app.state.reranker_model = get_reranker_model()
    log.info("startup complete")
    yield
    # --- shutdown: close cleanly ---
    log.info("shutdown: closing store connections")
    from app.core.config import close_all_clients
    close_all_clients()


app = FastAPI(
    title="Smart Office Hybrid RAG + Knowledge Graph Assistant",
    version="1.0.0-stage1",
    lifespan=lifespan,
)

# Rate limiting (slowapi): register the shared limiter, its 429 handler, and
# the SlowAPI middleware. Limits are per-endpoint via decorators + defaults.
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.core.rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Middleware order: last added runs first on the way in. We want request-id
# outermost (sets the id) and metrics innermost (times just the handler).
app.add_middleware(MetricsMiddleware)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_chat.router, tags=["chat"])
app.include_router(routes_devices.router, tags=["devices"])
app.include_router(routes_incidents.router, tags=["incidents"])
app.include_router(routes_admin.router, tags=["admin"])

# /metrics — OpenMetrics exposition for the eval harness / any scraper.
app.mount("/metrics", metrics_asgi_app())


# --- Dependency injectors (Module 10 Depends pattern) ----------------------
# Path operations may declare these instead of reaching into config directly.

def get_neo4j_session():
    with app.state.neo4j_driver.session() as session:
        yield session


def get_weaviate():
    return app.state.weaviate_client


# --- liveness vs readiness -------------------------------------------------

@app.get("/healthz")
def healthz() -> dict:
    """Liveness: is the process up? Must NOT touch the databases, so a store
    outage never causes a restart loop of a healthy process."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict:
    """Readiness: can we serve a useful request right now? Checks both stores;
    returns 503 with a structured body if either is unreachable."""
    try:
        app.state.neo4j_driver.verify_connectivity()
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail={"backend": "neo4j", "status": "unreachable",
                                    "error": str(exc)})
    try:
        if not app.state.weaviate_client.is_ready():
            raise HTTPException(status_code=503,
                                detail={"backend": "weaviate", "status": "not_ready"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail={"backend": "weaviate", "status": "unreachable",
                                    "error": str(exc)})
    return {"status": "ready"}
