"""
The minted token must satisfy backend/app/core/security.py.

These assertions are written out longhand rather than imported, because this
package must never import from `app.*`. That means they can drift from the
platform. If a bot starts getting 401s, re-read `decode_supabase_token` and
`get_current_user` and update this file.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from llm_panel.jwt_util import ALGORITHM, decode_bot_jwt, generate_bot_jwt

# 32+ bytes, matching the shape of a real Supabase JWT secret.
SECRET = "test-secret-not-a-real-one-0123456789abcdef"


def test_token_carries_the_claims_the_platform_requires() -> None:
    token = generate_bot_jwt("llm-panel-a-claude-panel", "a@llm-panel.example", SECRET)
    claims = decode_bot_jwt(token, SECRET)

    # sub is looked up against User.supabase_uid — NOT User.id.
    assert claims["sub"] == "llm-panel-a-claude-panel"
    # security.py rejects any token whose role is not exactly this.
    assert claims["role"] == "authenticated"
    assert claims["email"] == "a@llm-panel.example"
    assert claims["exp"] > datetime.now(UTC).timestamp()


def test_token_is_hs256() -> None:
    """The platform picks its verification path off the `alg` header."""
    token = generate_bot_jwt("uid", "bot@llm-panel.example", SECRET)
    assert jwt.get_unverified_header(token)["alg"] == ALGORITHM


def test_expiry_defaults_to_a_year_and_is_configurable() -> None:
    now = datetime.now(UTC).timestamp()

    default_token = generate_bot_jwt("uid", "b@x.example", SECRET)
    default_claims = decode_bot_jwt(default_token, SECRET)
    assert 364 * 86400 < default_claims["exp"] - now < 366 * 86400

    short_claims = decode_bot_jwt(
        generate_bot_jwt("uid", "b@x.example", SECRET, expires_in_days=1), SECRET
    )
    assert 0 < short_claims["exp"] - now <= 86400


def test_wrong_secret_does_not_verify() -> None:
    token = generate_bot_jwt("uid", "b@x.example", SECRET)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_bot_jwt(token, "some-other-secret-0123456789abcdefghij")


def test_expired_token_does_not_verify() -> None:
    """
    Minted directly rather than through generate_bot_jwt, which refuses a
    non-positive expiry. The platform rejects an expired token too — this pins
    that decode_bot_jwt agrees, so a debugging operator gets the real reason.
    """
    past = datetime.now(UTC) - timedelta(days=2)
    expired = jwt.encode(
        {
            "sub": "uid",
            "email": "b@x.example",
            "role": "authenticated",
            "aud": "authenticated",
            "iat": int(past.timestamp()),
            "exp": int((past + timedelta(days=1)).timestamp()),
        },
        SECRET,
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_bot_jwt(expired, SECRET)


@pytest.mark.parametrize(
    ("uid", "secret", "days"),
    [
        ("", SECRET, 365),
        ("uid", "", 365),
        ("uid", SECRET, 0),
        ("uid", SECRET, -1),
    ],
)
def test_rejects_unusable_inputs(uid: str, secret: str, days: int) -> None:
    with pytest.raises(ValueError):
        generate_bot_jwt(uid, "b@x.example", secret, expires_in_days=days)
