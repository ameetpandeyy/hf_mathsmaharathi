"""Authentication and authorization middleware for Maths Maharathi API."""

import os
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_admin_auth(
    x_api_key: Optional[str] = Security(API_KEY_HEADER),
    authorization: Optional[str] = Header(None),
) -> str:
    """Verifies that the incoming request is authorized via API Key or JWT."""
    configured_key = os.getenv("ADMIN_API_KEY", "mm-dev-secret-key-2025")
    
    # 1. Check API Key header
    if x_api_key and x_api_key == configured_key:
        return "admin_api_key"

    # 2. Check Bearer Token (e.g. Supabase JWT)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        if token == configured_key:
            return "admin_jwt"
        # In production with supabase, jwt can be decoded with SUPABASE_JWT_SECRET
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if jwt_secret:
            try:
                import jwt
                payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
                if payload.get("role") in ("authenticated", "service_role"):
                    return payload.get("sub", "authenticated_user")
            except Exception:
                pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials (X-API-Key or Bearer token)",
    )
