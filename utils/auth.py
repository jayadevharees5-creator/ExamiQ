import os
import time
from datetime import datetime, timedelta
from typing import Optional
import jwt

# Load secret key from environment (fallback to a random value if not set)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "quizforge_default_super_secret_jwt_key_2026_production")
ALGORITHM = "HS256"
TOKEN_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", "60"))


def create_access_token(username: str) -> str:
    """Create a signed JWT access token for a given username.
    The token expires after ``TOKEN_EXP_MINUTES`` minutes.
    """
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXP_MINUTES)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[str]:
    """Decode a JWT and return the ``sub`` (username) if valid.
    Returns ``None`` on any validation error.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

