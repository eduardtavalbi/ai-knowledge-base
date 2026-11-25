import pytest

from app.middleware.upload_limits import UploadRequestSizeLimitMiddleware


async def _run_middleware(
    *,
    path: str = "/documents/upload",
    method: str = "POST",
    headers: list[tuple[bytes, bytes]] | None = None,
    messages: list[dict] | None = None,
    max_bytes: int = 5,
):
    received = []
    sent = []
    queue = list(messages or [])

    async def app(scope, receive, send):
        while True:
            message = await receive()
            received.append(message)
            if message["type"] == "http.request" and not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = UploadRequestSizeLimitMiddleware(app, max_bytes=max_bytes)
    await middleware(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
        },
        receive,
        send,
    )
    return received, sent


@pytest.mark.asyncio
async def test_upload_middleware_rejects_oversized_content_length_without_reading_body():
    received, sent = await _run_middleware(
        headers=[(b"content-length", b"6")],
        messages=[{"type": "http.request", "body": b"abcdef", "more_body": False}],
    )

    assert received == []
    assert sent[0]["status"] == 413
    assert sent[1]["body"] == b'{"detail":"Upload request body is too large"}'


@pytest.mark.asyncio
async def test_upload_middleware_rejects_chunked_body_over_limit():
    received, sent = await _run_middleware(
        messages=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": False},
        ],
    )

    assert len(received) == 1
    assert sent[0]["status"] == 413
    assert sent[1]["body"] == b'{"detail":"Upload request body is too large"}'


@pytest.mark.asyncio
async def test_upload_middleware_accepts_body_at_exact_limit():
    _, sent = await _run_middleware(
        headers=[(b"content-length", b"5")],
        messages=[{"type": "http.request", "body": b"12345", "more_body": False}],
    )

    assert sent[0]["status"] == 200
    assert sent[1]["body"] == b"ok"


@pytest.mark.asyncio
async def test_upload_middleware_does_not_limit_other_routes_or_methods():
    _, sent = await _run_middleware(
        path="/documents/",
        method="POST",
        messages=[{"type": "http.request", "body": b"123456", "more_body": False}],
    )

    assert sent[0]["status"] == 200
    assert sent[1]["body"] == b"ok"
