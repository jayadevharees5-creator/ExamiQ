import os
import time
import logging
from typing import Tuple, Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from config import Config
from utils.auth import decode_access_token

logger = logging.getLogger("quizforge.ratelimit")

class RedisRateLimiter:
    """
    Distributed Redis-backed rate limiter with seamless in-memory fallback.
    Tracks requests per user / IP using fixed time-window counters.
    """

    def __init__(
        self,
        redis_url: str = Config.REDIS_URL,
        limit_per_minute: int = Config.RATE_LIMIT_PER_MINUTE,
        enabled: bool = Config.RATE_LIMIT_ENABLED
    ):
        self.redis_url = redis_url
        self.limit = limit_per_minute
        self.enabled = enabled
        self._redis = None
        self._redis_available = None  # None = untried, True = connected, False = unavailable
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=1.5,
                socket_connect_timeout=1.5
            )
            # Test connection
            await self._redis.ping()
            self._redis_available = True
            logger.info("Connected to Redis for distributed rate limiting at %s", self.redis_url)
            return self._redis
        except Exception as e:
            self._redis_available = False
            self._redis = None
            logger.warning(
                "Redis connection failed (%s). Falling back to in-memory rate limiting.",
                str(e)
            )
            return None

    async def check_rate_limit(self, identifier: str, window: int = 60) -> Tuple[bool, int, int]:
        """
        Check if the identifier exceeded self.limit requests in the current window.
        Returns: (is_limited: bool, remaining: int, retry_after: int)
        """
        if not self.enabled:
            return False, self.limit, 0

        current_window = int(time.time() // window)
        reset_in = window - int(time.time() % window)

        # 1. Attempt Redis rate limit
        r = await self._get_redis()
        if r is not None:
            key = f"rate_limit:{identifier}:{current_window}"
            try:
                pipe = r.pipeline()
                pipe.incr(key)
                pipe.expire(key, window * 2)
                results = await pipe.execute()
                count = int(results[0])
                remaining = max(0, self.limit - count)
                is_limited = count > self.limit
                return is_limited, remaining, reset_in
            except Exception as e:
                logger.warning("Redis error during rate check: %s. Using memory fallback.", str(e))
                self._redis_available = False
                self._redis = None

        # 2. In-memory fallback
        mem_key = f"{identifier}:{current_window}"
        # Periodic cleanup of expired memory entries
        now = time.time()
        for k in list(self._memory_store.keys()):
            if self._memory_store[k].get("expires_at", 0) < now:
                self._memory_store.pop(k, None)

        if mem_key not in self._memory_store:
            self._memory_store[mem_key] = {
                "count": 1,
                "expires_at": now + (window * 2)
            }
            return False, self.limit - 1, reset_in

        self._memory_store[mem_key]["count"] += 1
        count = self._memory_store[mem_key]["count"]
        remaining = max(0, self.limit - count)
        is_limited = count > self.limit
        return is_limited, remaining, reset_in

    async def close(self):
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass


# Global singleton instance
rate_limiter = RedisRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware enforcing per-user (JWT) or per-IP rate limits.
    """

    # Paths exempt from strict rate limits (static files, docs, health)
    EXEMPT_PREFIXES = ("/static", "/docs", "/redoc", "/openapi.json", "/favicon.ico")

    def __init__(self, app, limiter: Optional[RedisRateLimiter] = None):
        super().__init__(app)
        self.limiter = limiter or rate_limiter

    def _extract_identifier(self, request: Request) -> str:
        # 1. Extract from JWT Bearer token if present
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth[7:].strip()
            username = decode_access_token(token)
            if username:
                return f"user:{username.strip().lower()}"

        # 2. Extract from client IP address
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            if ip:
                return f"ip:{ip}"
        
        client = request.client
        ip = client.host if client else "unknown"
        return f"ip:{ip}"

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip exempt endpoints
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return await call_next(request)

        identifier = self._extract_identifier(request)
        is_limited, remaining, retry_after = await self.limiter.check_rate_limit(identifier)

        if is_limited:
            logger.warning("Rate limit exceeded for %s on %s %s", identifier, request.method, path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and try again later.",
                    "retry_after_seconds": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limiter.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after)
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
