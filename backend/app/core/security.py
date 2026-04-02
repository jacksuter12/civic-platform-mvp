"""
Supabase JWT verification for FastAPI.

Supabase issues HS256 JWTs signed with the project-level JWT secret.
We verify locally — no round-trip to Supabase Auth on every request.

Token claims we use:
  - sub: the supabase_uid (maps to User.supabase_uid)
  - email: verified email address
  - exp: expiry
  - role: "authenticated" for logged-in users

We do NOT trust the token's role claim for our tier system.
Tier is always read from our database (User.tier).
"""

from datetime import datetime

from jose import JWTError, jwt

from app.config import settings

_ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def decode_supabase_token(token: str) -> dict:
    """
    Decode and verify a Supabase JWT. Returns the claims dict.
    Raises TokenError on any verification failure.
    """
    try:
        claims = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[_ALGORITHM],
            options={"verify_aud": False},  # Supabase doesn't set standard aud
        )
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
