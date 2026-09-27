from typing import Any


class AppException(Exception):
    status_code: int = 500
    title: str = "Internal Server Error"

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


__all__ = [
    "AppException",
    "BadRequestError",
    "ChannelNotFoundError",
    "ConflictError",
    "DuplicateChannelNameError",
    "ForbiddenError",
    "InsufficientPermissionsError",
    "NotFoundError",
    "RoleNotFoundError",
    "ServerNotFoundError",
    "UnauthorizedError",
    "UnprocessableEntityError",
]

