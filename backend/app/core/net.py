from fastapi import Request

from app.core.config import get_settings


def client_ip(request: Request) -> str:
    """The caller's IP for rate limiting.

    X-Forwarded-For is only trusted for the number of proxy hops we actually run behind
    (TRUSTED_PROXY_HOPS, e.g. 1 on Render). Entries further left are client-supplied and ignored,
    so a caller cannot dodge a limit by inventing the header.
    """
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        parts = [
            p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
        ]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"
