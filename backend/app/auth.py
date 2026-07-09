"""Current-user resolution via Clerk — real when configured, faked for demo.

Real mode (settings.clerk_configured, i.e. CLERK_JWKS_URL set): verify the
`Authorization: Bearer <clerk session JWT>` against Clerk's JWKS (the
`fastapi-clerk-auth` guard caches the keys), map the `sub` claim to a users
row (load-or-create).

Fake mode (no Clerk config — local dev / demo): the exact same dependency
surface, but the token is trusted without verification so you don't need to
run Clerk:
  - a real Clerk JWT from the app  -> decoded UNVERIFIED for sub/email/name
  - any plain string, e.g. "alice" -> used directly as the identity
  - no Authorization header        -> anonymous (OptionalUserDep -> None);
                                      required deps fall back to a fixed
                                      "dev" user
This lets the mobile app's real sign-in flow drive per-user behavior in the
demo, and lets curl hit user-scoped routes with just `-H "Authorization:
Bearer alice"`. Flip to real verification by setting CLERK_JWKS_URL.

Exposed dependencies:
  CurrentUserDep       -> uuid.UUID   the user's DB id (most routes want this)
  CurrentUserModelDep  -> User        the full row (email, prefs, ...)
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer

from app.config import settings
from app.models import User
from app.services.users import UserServiceDep

logger = logging.getLogger(__name__)

# Identity used when no token is presented in fake mode (local dev / demo).
_DEV_CLERK_ID = "dev_user"
_DEV_EMAIL = "dev@tasted.local"
_DEV_NAME = "Dev User"

# JWKS-backed bearer guard; only constructed when Clerk is configured.
_clerk_guard: ClerkHTTPBearer | None = (
    ClerkHTTPBearer(config=ClerkConfig(jwks_url=settings.clerk_jwks_url, leeway=60))
    if settings.clerk_configured
    else None
)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _identity_from_token(token: str) -> tuple[str, str | None, str | None]:
    """Best-effort identity from an UNVERIFIED token (fake mode only).

    A real Clerk JWT is decoded without signature checks; anything else
    (e.g. "alice") is used directly as the identity. NOT for production —
    guarded by `clerk_configured` being False.
    """
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return token, None, None
    sub = claims.get("sub") or claims.get("user_id") or token
    return sub, claims.get("email") or claims.get("primary_email"), claims.get("name")


async def get_optional_user(request: Request, users: UserServiceDep) -> User | None:
    """The authenticated user, or None when the request is anonymous.

    For endpoints that work logged out (menu scanning): a missing token means
    anonymous, an invalid one still fails loudly in real mode.
    """
    token = _bearer_token(request)
    if token is None:
        return None
    if _clerk_guard is None:
        sub, email, name = _identity_from_token(token)
        return await users.get_or_create_by_clerk_id(sub, email=email, display_name=name)

    creds = await _clerk_guard(request)  # raises 403 on an invalid token
    claims = getattr(creds, "decoded", None) if creds else None
    sub = claims.get("sub") if claims else None
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token")
    email = claims.get("email") or claims.get("primary_email")
    name = claims.get("name") or claims.get("full_name")
    return await users.get_or_create_by_clerk_id(sub, email=email, display_name=name)


async def get_current_user(request: Request, users: UserServiceDep) -> User:
    """The authenticated user — required.

    Anonymous requests get the fixed dev user in fake mode (keeps local
    curl/demo flows working) and a 401 in real mode.
    """
    user = await get_optional_user(request, users)
    if user is not None:
        return user
    if _clerk_guard is None:
        return await users.get_or_create_by_clerk_id(
            _DEV_CLERK_ID, email=_DEV_EMAIL, display_name=_DEV_NAME
        )
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


async def get_current_user_id(
    user: Annotated[User, Depends(get_current_user)],
) -> uuid.UUID:
    return user.id


CurrentUserDep = Annotated[uuid.UUID, Depends(get_current_user_id)]
CurrentUserModelDep = Annotated[User, Depends(get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]
