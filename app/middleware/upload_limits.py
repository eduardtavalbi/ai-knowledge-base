from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.document import MAX_DOCUMENT_CONTENT_BYTES

# Allow multipart boundaries, headers, and the filename in addition to the file.
MAX_UPLOAD_REQUEST_BYTES = MAX_DOCUMENT_CONTENT_BYTES + 64 * 1024


class _RequestBodyTooLarge(Exception):
    pass


class UploadRequestSizeLimitMiddleware:
    """Bound upload request bodies before Starlette parses multipart data."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_UPLOAD_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path", "").rstrip("/") != "/documents/upload"
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_content_length = headers.get(b"content-length")
        if raw_content_length is not None:
            try:
                if int(raw_content_length) > self.max_bytes:
                    await self._send_too_large(send)
                    return
            except ValueError:
                # Do not trust malformed metadata; enforce the streaming limit.
                pass

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if not response_started:
                await self._send_too_large(send)

    async def _send_too_large(self, send: Send) -> None:
        body = b'{"detail":"Upload request body is too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })
