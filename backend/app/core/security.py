"""
Supabase JWT verification for FastAPI.

Supabase issues JWTs signed with either:
  - HS256 (legacy projects): verified with the project JWT secret
  - ES256 (newer projects): verified with Supabase's public JWKS

We peek at the token header to choose the right path.
JWKS is fetched once from Supabase on first use and cached in-process.

Token claims we use:
  - sub: the supabase_uid (maps to User.supabase_uid)
  - email: verified email address
  - exp: expiry
  - role: "authenticated" for logged-in users

We do NOT trust the token's role claim for our tier system.
Tier is always read from our database (User.tier).
"""

from datetime import datetime
from functools import lru_cache

import httpx
from jose import JWTError, jwt

from app.config import settings

_ALGORITHM_HS256 = "HS256"
_ALGORITHM_ES256 = "ES256"


class TokenError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_jwks() -> list[dict]:
    """
    Fetch and cache Supabase's public JWKS (for ES256 tokens).
    Called at most once per process lifetime.
    """
    url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get("keys", [])
    except Exception as e:
        raise TokenError(f"Could not fetch Supabase JWKS: {e}") from e


def decode_supabase_token(token: str) -> dict:
    """
    Decode and verify a Supabase JWT. Returns the claims dict.
    Raises TokenError on any verification failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise TokenError(f"Invalid token header: {e}") from e

    alg = header.get("alg", _ALGORITHM_HS256)

    try:
        if alg == _ALGORITHM_HS256:
            claims = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=[_ALGORITHM_HS256],
                options={"verify_aud": False},
            )
        elif alg == _ALGORITHM_ES256:
            keys = _get_jwks()
            kid = header.get("kid")
            # Prefer the key whose kid matches; fall back to first key
            key = next((k for k in keys if k.get("kid") == kid), None)
            if key is None:
                key = keys[0] if keys else None
            if key is None:
                raise TokenError("No public key available to verify ES256 token")
            claims = jwt.decode(
                token,
                key,
                algorithms=[_ALGORITHM_ES256],
                options={"verify_aud": False},
            )
        else:
            raise TokenError(f"Unsupported token algorithm: {alg}")
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}") from e

    if claims.get("role") != "authenticated":
        raise TokenError("Token role is not 'authenticated'")

    exp = claims.get("exp")
    if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
        raise TokenError("Token has expired")

    return claims


def extract_supabase_uid(claims: dict) -> str:
    uid = claims.get("sub")
    if not uid:
        raise TokenError("Token missing 'sub' claim")
    return uid
