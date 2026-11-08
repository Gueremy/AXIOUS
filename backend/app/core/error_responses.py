"""Consistent, actionable errors without echoing submitted passwords or values."""
import uuid
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def register_error_responses(app):
    @app.middleware("http")
    async def correlate(request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, headers=exc.headers, content={
            "detail": exc.detail,
            "message": exc.detail if isinstance(exc.detail, str) else "Revisa los datos de la solicitud",
            "code": f"HTTP_{exc.status_code}", "request_id": getattr(request.state, "request_id", str(uuid.uuid4())),
        })

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": fields, "fields": fields,
            "message": "Revisa los campos indicados antes de volver a guardar", "code": "VALIDATION_ERROR",
            "request_id": request.state.request_id})
