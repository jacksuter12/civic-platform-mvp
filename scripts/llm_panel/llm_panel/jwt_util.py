"""
Long-lived bot JWTs.

The platform verifies HS256 tokens against SUPABASE_JWT_SECRET. Bot users never
go through Supabase Auth — there is no magic link to click — so the panel mints
their tokens directly with the same secret.

The platform's verifier requires, in this order:
  - a decodable HS256 signature over SUPABASE_JWT_SECRET
  - `role == "authenticated"` (rejected outright otherwise)
  - a non-expired `exp`
  - a `sub` claim, which is looked up against **User.supabase_uid** — not
    User.id. A `sub` with no matching user row is a 401, never an auto-create.

`aud` and `iss` are not verified by the platform. `aud` is included anyway so
the token shape matches a real Supabase token; `iss` is omitted because there is
no issuer URL that would be true.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"

#: The only role value the platform accepts. See backend/app/core/security.py.
AUTHENTICATED_ROLE = "authenticated"

DEFAULT_EXPIRY_DAYS = 365


def generate_bot_jwt(
    supabase_uid: str,
    email: str,
    secret: str,
    expires_in_days: int = DEFAULT_EXPIRY_DAYS,
) -> str:
    """
    Mint an HS256 bearer token for a seeded bot user.

    `supabase_uid` becomes the `sub` claim and must match the bot's
    User.supabase_uid row exactly, or every request 401s.
    """
    if not supabase_uid:
        raise ValueError("supabase_uid is required — it becomes the 'sub' claim")
    if not secret:
        raise ValueError("secret is required (SUPABASE_JWT_SECRET)")
    if expires_in_days <= 0:
        raise ValueError("expires_in_days must be positive")

    now = datetime.now(UTC)
    claims = {
        "sub": supabase_uid,
        "email": email,
        "role": AUTHENTICATED_ROLE,
        "aud": AUTHENTICATED_ROLE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expires_in_days)).timestamp()),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_bot_jwt(token: str, secret: str) -> dict:
    """
    Decode a token minted by `generate_bot_jwt`. Used by the panel's own tests
    and by operators debugging a 401 — the platform does its own verification.
    """
    return jwt.decode(
        token,
        secret,
        algorithms=[ALGORITHM],
        audience=AUTHENTICATED_ROLE,
    )
