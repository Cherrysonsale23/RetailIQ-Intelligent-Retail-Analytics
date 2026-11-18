from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid Supabase access token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None
        if settings.supabase_jwt_jwks_url:
            global _jwks_client
            if _jwks_client is None:
                _jwks_client = PyJWKClient(settings.supabase_jwt_jwks_url, cache_keys=True)
            signing_key = _jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, signing_key, algorithms=["ES256", "RS256"], audience="authenticated", issuer=issuer)
        elif settings.supabase_jwt_secret:
            claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated", issuer=issuer)
        else:
            raise _unauthorized()
    except HTTPException:
        raise
    except Exception as exc:
        raise _unauthorized() from exc
    if claims.get("role") != "authenticated" or not claims.get("sub"):
        raise _unauthorized()
    return claims


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return _decode_token(credentials.credentials)

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
