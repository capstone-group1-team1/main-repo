"""
observability.py — the "fast" and "reliable" axes (Module 11).

Three ASGI middlewares wired in the right order, plus the three Prometheus
metric declarations and the /metrics exposition app:

  * RequestIdMiddleware      — one uuid per request, echoed as X-Request-ID,
                               threaded through logs via a ContextVar.
  * StructuredLoggingMiddleware — one JSON log line per request, correlated by
                               request_id (path, method, status, latency_ms).
  * MetricsMiddleware        — increments the counter, observes latency into
                               the histogram, tracks in-flight gauge.

Metric types follow the standard mapping: Counter for request counts (only
goes up), Histogram for latency (percentiles after the fact), Gauge for
in-flight (goes up and down). Labels are bounded sets only (path, status) so
the timeseries count stays small.
"""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# request_id available to any log call during a request without passing it
# through every function signature.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# --- the three metrics (declared once, at import) --------------------------
REQUESTS_TOTAL = Counter("requests_total", "Total HTTP requests", ["path", "status"])
REQUEST_LATENCY_SECONDS = Histogram(
    "request_latency_seconds",
    "Request latency in seconds",
    ["path"],
    # buckets span 5 ms .. 50 s: fine-grained at the fast end (graph/device
    # reads), and now more resolution above 1s too — /chat runs the
    # cross-encoder reranker (scoring up to `rerank_candidate_pool`
    # candidates) on top of Weaviate hybrid search and LLM synthesis, which
    # regularly pushes it into the 3-15 s range, and /chat/stream holds its
    # connection open for the full streamed answer on top of that. The old
    # ceiling of 10s bucketed anything slower straight into +Inf, which
    # flattened p95 on both endpoints.
    buckets=[
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2,
        5,
        7.5,
        10,
        15,
        20,
        30,
        40,
        50,
    ],
)
INFLIGHT_REQUESTS = Gauge("inflight_requests", "In-flight requests")

_access_log = logging.getLogger("app.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _access_log.info(
            json.dumps(
                {
                    "ts": time.time(),
                    "level": "INFO",
                    "request_id": request_id_var.get(),
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                }
            )
        )
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        INFLIGHT_REQUESTS.inc()
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            INFLIGHT_REQUESTS.dec()
        latency = time.perf_counter() - started
        path = request.url.path
        REQUESTS_TOTAL.labels(path=path, status=str(response.status_code)).inc()
        REQUEST_LATENCY_SECONDS.labels(path=path).observe(latency)
        return response


def metrics_asgi_app():
    """ASGI app that serves the current metric state in OpenMetrics text."""
    return make_asgi_app()
