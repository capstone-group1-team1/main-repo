"""
rate_limit.py — a single shared slowapi limiter.

One Limiter instance is created here and imported by main.py (to register the
handler + middleware) and by the route modules (to decorate endpoints). Limits
come from Settings, so they're tunable without code changes. Keying is by
client IP, which is the right default for this stage.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.rate_limit_default] if _settings.rate_limit_enabled else [],
    enabled=_settings.rate_limit_enabled,
)
