"""Rate limiting for the routes that spend real Mistral API money per call (/extract,
/query in app/main.py). Redis-backed via REDIS_URL so limits hold across multiple backend
replicas — falls back to slowapi's in-process default when REDIS_URL isn't set (local dev,
tests), which is correct for a single instance and needs no Redis server running.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=["60/minute"],
)
