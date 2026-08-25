"""Per-client rate limiting (slowapi).

Storage is in-process memory: limits are per API replica, which is acceptable for the
prototype's single-replica deployment. Behind a reverse proxy the client address arrives in
X-Forwarded-For; without honouring it every user would share one bucket.
"""

from fastapi import Request
from slowapi import Limiter


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First hop is the originating client; later hops are proxies.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_key, default_limits=["300/minute"])
