import time
import logging
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from utils.auth import decode_access_token

logger = logging.getLogger("quizforge.access")

def setup_logging(level: int = logging.INFO) -> None:
    """Configures structured application logging with timestamps and module names."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True
    )

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that logs every request with user, endpoint, method,
    status code, execution duration, and timestamp.
    """

    EXEMPT_PATHS = ("/static", "/favicon.ico")

    def _get_user(self, request: Request) -> str:
        # Check Authorization Bearer header
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth[7:].strip()
            username = decode_access_token(token)
            if username:
                return username.strip().lower()

        # Check request query params for legacy requests if any
        user_query = request.query_params.get("username")
        if user_query:
            return user_query.strip().lower()

        return "anonymous"

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            return await call_next(request)

        user = self._get_user(request)
        ip = self._get_client_ip(request)
        start_time = time.time()
        timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "[%s] user=%s | ip=%s | %s %s | status=%d | duration=%.2fms",
                timestamp_str,
                user,
                ip,
                request.method,
                path,
                response.status_code,
                duration_ms
            )
            return response
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "[%s] user=%s | ip=%s | %s %s | error=%s | duration=%.2fms",
                timestamp_str,
                user,
                ip,
                request.method,
                path,
                str(exc),
                duration_ms
            )
            raise exc

