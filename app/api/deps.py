from fastapi import Header, HTTPException, status


async def get_current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id", description="Authenticated User ID from Gateway")
) -> str:
    """Extracts and validates the authenticated user ID injected by the API Gateway (Kong/Auth0)."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthenticated user identity. Gateway token verification is required.",
        )
    return x_user_id

