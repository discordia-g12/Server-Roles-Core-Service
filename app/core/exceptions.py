import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import AppException

logger = logging.getLogger(__name__)

__all__ = [
    "AppException",
    "app_exception_handler",
    "http_exception_handler",
    "problem_response",
    "register_exception_handlers",
    "unhandled_exception_handler",
    "validation_exception_handler",
]


def problem_response(
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    invalid_params: list[dict[str, Any]] | None = None,
    problem_type: str = "about:blank",
) -> JSONResponse:
    content: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    if invalid_params:
        content["invalid_params"] = invalid_params

    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return problem_response(
        request=request,
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        invalid_params=exc.invalid_params,
        problem_type=exc.type,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    invalid_params = [
        {
            "name": ".".join(str(loc) for loc in err["loc"] if loc != "body") or "payload",
            "reason": err["msg"],
        }
        for err in exc.errors()
    ]
    return problem_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Validation Error",
        detail="One or more boundary validation rules failed.",
        invalid_params=invalid_params,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    title = (
        HTTPStatus(exc.status_code).phrase
        if exc.status_code in HTTPStatus._value2member_map_
        else "HTTP Error"
    )
    return problem_response(
        request=request,
        status_code=exc.status_code,
        title=title,
        detail=str(exc.detail),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception occurred: %s", exc)
    return problem_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire exceptions to their RFC 7807 handlers."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
