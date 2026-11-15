from fastapi import Header, HTTPException, status

from app.exceptions import StaffOnlyError


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



PLATFORM_STAFF_ROLE = "staff"


async def require_staff(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> str:
    """Staff endpoints (/api/v1/admin/servers): 401 without identity, 403 unless X-User-Role is exactly "staff".
    Second barrier: Kong already enforces validate("staff") on that route (Gateway ADR-002, rule 2)."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthenticated user identity. Gateway token verification is required.",
        )
    if not isinstance(x_user_role, str) or x_user_role.strip() != PLATFORM_STAFF_ROLE:
        raise StaffOnlyError()
    return x_user_id
