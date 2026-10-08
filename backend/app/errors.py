from fastapi import HTTPException


class ApiError(HTTPException):
    """An error with a stable machine-readable `code`, so the client can show it in the user's language.

    The body is {"detail": {"code": ..., "message": <English, for logs and API users>, "params": {...}}}.
    The web client keeps one Russian text per code (frontend/src/messages.ts); a test fails if a code has no translation.
    """

    def __init__(self, status_code: int, code: str, message: str, /, **params):
        detail = {"code": code, "message": message}
        if params:
            detail["params"] = params
        super().__init__(status_code, detail)
