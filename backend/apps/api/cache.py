"""Response caching and cross-process epoch invalidation for API v1."""

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Callable

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from rest_framework.response import Response

_EPOCH_FILE = Path(os.environ.get("FIREPULSE_EPOCH_FILE") or (Path(tempfile.gettempdir()) / "firepulse_api_epoch"))
_LOCAL_EPOCH = 0


def _read_epoch_file() -> str:
    try:
        return _EPOCH_FILE.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def get_data_epoch() -> str:
    """Return a combined in-process + cross-process epoch token for cache keys."""
    return f"{_LOCAL_EPOCH}:{_read_epoch_file()}"


def invalidate_api_cache(*_args, **_kwargs) -> None:
    """Advance both local and shared epoch tokens after database ingestion or model writes."""
    global _LOCAL_EPOCH
    _LOCAL_EPOCH += 1
    token = f"{time.time_ns()}-{_LOCAL_EPOCH}"
    try:
        _EPOCH_FILE.write_text(token, encoding="utf-8")
    except OSError:
        pass


def build_cache_key(prefix: str, request) -> str:
    """Build a bounded deterministic cache key from endpoint prefix, data epoch, and query params."""
    canonical_items = sorted(
        (key, tuple(values)) for key, values in request.query_params.lists()
    )
    digest = hashlib.sha256(repr(canonical_items).encode("utf-8")).hexdigest()[:24]
    return f"fp:api:v1:{prefix}:{get_data_epoch()}:{digest}"


def _apply_http_cache_headers(response: Response, hit_state: str, max_age: int) -> Response:
    response["X-FirePulse-Cache"] = hit_state
    if max_age > 0:
        swr = max(max_age * 5, 60)
        response["Cache-Control"] = f"public, max-age={max_age}, stale-while-revalidate={swr}"
    else:
        response["Cache-Control"] = "no-store"
    return response


def offline_unavailable_response(detail: str) -> Response:
    """Return a clean non-cacheable 503 JSON payload when DB is offline and no snapshot matches."""
    return _apply_http_cache_headers(
        Response(
            {
                "error": "Database unavailable and no matching offline snapshot is available.",
                "detail": detail,
            },
            status=503,
        ),
        "BYPASS",
        0,
    )


def _serve_fallback(
    fallback: Callable[[], dict | None] | None,
    detail: str,
) -> Response:
    if fallback is not None and getattr(settings, "API_SNAPSHOT_FALLBACK", True):
        payload = fallback()
        if payload is not None:
            return _apply_http_cache_headers(Response(payload), "FALLBACK", 0)
    return offline_unavailable_response(detail)


def cached_api_response(
    prefix: str,
    request,
    producer: Callable[[], tuple[dict, int] | dict],
    *,
    fallback: Callable[[], dict | None] | None = None,
    timeout: int | None = None,
    http_max_age: int | None = None,
) -> Response:
    """Serve cached JSON payloads on HTTP 200 and fall back to demo snapshots on DatabaseError."""
    if fallback is not None and getattr(settings, "FORCE_SNAPSHOT_FALLBACK", False):
        payload = fallback()
        if payload is not None:
            return _apply_http_cache_headers(Response(payload), "FALLBACK", 0)
        return offline_unavailable_response(
            "Requested resource is unavailable in offline snapshot fallback mode."
        )

    cache_ttl = getattr(settings, "API_CACHE_SECONDS", 300) if timeout is None else timeout
    max_age = getattr(settings, "HTTP_CACHE_MAX_AGE", 60) if http_max_age is None else http_max_age
    key = build_cache_key(prefix, request)

    if cache_ttl > 0:
        cached_payload = cache.get(key)
        if cached_payload is not None:
            return _apply_http_cache_headers(Response(cached_payload), "HIT", max_age)

    try:
        result = producer()
    except DatabaseError as exc:
        return _serve_fallback(fallback, str(exc))

    if isinstance(result, Response):
        return _apply_http_cache_headers(result, "BYPASS", 0)

    if isinstance(result, tuple):
        payload, status_code = result
    else:
        payload, status_code = result, 200

    if status_code != 200:
        return _apply_http_cache_headers(Response(payload, status=status_code), "BYPASS", 0)

    if cache_ttl > 0:
        cache.set(key, payload, timeout=cache_ttl)
        return _apply_http_cache_headers(Response(payload), "MISS", max_age)

    return _apply_http_cache_headers(Response(payload), "DISABLED", max_age)
