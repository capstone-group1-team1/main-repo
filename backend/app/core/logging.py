"""
logging.py — uniform logging setup + the internal Query Router decision log.

Router Confidence is a DEBUG/observability signal for the team.  It is logged
here and must never appear in any API response (see synthesis/confidence.py
for the three user-facing signals).
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


_router_log = logging.getLogger("router.decisions")


def log_router_decision(
    question: str, route: str, router_confidence: float,
    entities: list[str], mechanism: str,
) -> None:
    """One line per routing decision — the team's debugging trail for
    edge case 5 (router misclassification review)."""
    try:
        _router_log.info(
            "ROUTE=%s conf=%.2f mechanism=%s entities=%s question=%r",
            route, router_confidence, mechanism, entities, question[:120],
        )
    except Exception:  # logging must never break the request path
        pass
