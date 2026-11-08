from typing import Any

PROBLEM_TYPE_BASE = "https://discordia.app/problems"


class AppException(Exception):
    status_code: int = 500
    title: str = "Internal Server Error"
    # RFC 7807 "type": los clientes deciden por este campo. "about:blank" salvo los errores con tipo propio
    type: str = "about:blank"

    def __init__(
        self,
        detail: str,
        status_code: int | None = None,
        title: str | None = None,
        invalid_params: list[dict[str, Any]] | None = None,
    ):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if title is not None:
            self.title = title
        self.invalid_params = invalid_params


class BadRequestError(AppException):
    status_code = 400
    title = "Bad Request"


class UnauthorizedError(AppException):
    status_code = 401
    title = "Unauthorized"

    def __init__(self, detail: str = "Unauthenticated user identity. Gateway token verification is required."):
        super().__init__(detail)


class ForbiddenError(AppException):
    status_code = 403
    title = "Forbidden"

    def __init__(self, detail: str = "You do not have permissions to perform this action."):
        super().__init__(detail)


class NotFoundError(AppException):
    status_code = 404
    title = "Not Found"

    def __init__(self, detail: str = "Resource not found."):
        super().__init__(detail)


class ConflictError(AppException):
    status_code = 409
    title = "Conflict"

    def __init__(self, detail: str = "Resource conflict."):
        super().__init__(detail)


class UnprocessableEntityError(AppException):
    status_code = 422
    title = "Validation Error"


class ServiceUnavailableError(AppException):
    status_code = 503
    title = "Service Unavailable"

    def __init__(self, detail: str = "The request could not be processed right now. Try again later."):
        super().__init__(detail)


# Domain-Specific Exceptions
class ServerNotFoundError(NotFoundError):
    def __init__(self, detail: str = "Server not found."):
        super().__init__(detail)


class ChannelNotFoundError(NotFoundError):
    def __init__(self, detail: str = "Channel not found."):
        super().__init__(detail)


class RoleNotFoundError(NotFoundError):
    def __init__(self, detail: str = "Role not found."):
        super().__init__(detail)


class InsufficientPermissionsError(ForbiddenError):
    def __init__(self, detail: str = "You do not have permissions to perform this operation."):
        super().__init__(detail)


class DuplicateChannelNameError(BadRequestError):
    def __init__(self, detail: str = "A channel with that name already exists in this category."):
        super().__init__(detail)


class MissingServerPermissionError(ForbiddenError):
    def __init__(self, detail: str = "Missing required permission: MANAGE_SERVER"):
        super().__init__(detail)


class StorageUnavailableError(ServiceUnavailableError):
    def __init__(self, detail: str = "The image could not be stored. Try again later."):
        super().__init__(detail)


__all__ = [
    "AppException",
    "BadRequestError",
    "ChannelNotFoundError",
    "ConflictError",
    "DuplicateChannelNameError",
    "ForbiddenError",
    "InsufficientPermissionsError",
    "MissingServerPermissionError",
    "NotFoundError",
    "RoleNotFoundError",
    "ServerNotFoundError",
    "ServiceUnavailableError",
    "StorageUnavailableError",
    "UnauthorizedError",
    "UnprocessableEntityError",
    "PROBLEM_TYPE_BASE",
    "ServerSuspendedError",
    "StaffOnlyError",
]


class StaffOnlyError(ForbiddenError):
    """Second barrier for staff endpoints. The first one is validate("staff") in Kong (Gateway ADR-002)."""

    type = f"{PROBLEM_TYPE_BASE}/staff-only"

    def __init__(self, detail: str = "Only platform staff can perform this action."):
        super().__init__(detail)


class ServerSuspendedError(ForbiddenError):
    """The server was suspended by platform staff (ADR-002): nobody can use it until the suspension is lifted.
    Clients show the server with its "suspended" banner instead of its channels."""

    type = f"{PROBLEM_TYPE_BASE}/server-suspended"

    def __init__(self, detail: str = "This server has been suspended by the platform."):
        super().__init__(detail)
