import asyncio
import re

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException


class UploadLimitError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status, message)
        self.code = code


class UploadLimits:
    """Bound multipart reception before the endpoint processes the file."""

    def __init__(self, app, max_file_bytes: int, timeout: float):
        self.app = app
        self.max_body_bytes = max_file_bytes + 1024 * 1024  # Multipart framing and form fields.
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        upload = (
            scope["type"] == "http" and scope["method"] == "POST"
            and re.fullmatch(r"/api/scans/[^/]+/assets/?", scope["path"])
        )
        if not upload:
            await self.app(scope, receive, send)
            return

        received = 0
        deadline = asyncio.get_running_loop().time() + self.timeout
        length = Headers(scope=scope).get("content-length", "")

        async def limited_receive():
            nonlocal received
            if length.isdecimal() and int(length) > self.max_body_bytes:
                raise UploadLimitError(413, "FILE_TOO_LARGE", "Upload exceeds the request size limit")
            try:
                async with asyncio.timeout_at(deadline):
                    message = await receive()
            except TimeoutError as exc:
                raise UploadLimitError(408, "UPLOAD_TIMEOUT", "Upload request body timed out") from exc
            received += len(message.get("body", b""))
            if received > self.max_body_bytes:
                raise UploadLimitError(413, "FILE_TOO_LARGE", "Upload exceeds the request size limit")
            return message

        await self.app(scope, limited_receive, send)
