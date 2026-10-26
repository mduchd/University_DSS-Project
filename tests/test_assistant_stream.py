"""Streaming chat keeps authentication, provider errors and answer chunks intact."""

from __future__ import annotations

import datetime as dt
import json

import jwt
import pytest
import requests

from app import app
from services import assistant_service


class FakeUpstream:
    ok = True

    def __init__(self, lines):
        self.lines = lines
        self.closed = False

    def iter_lines(self, chunk_size=1):
        yield from self.lines

    def close(self):
        self.closed = True


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def test_stream_forwards_content_deltas_and_closes_upstream(monkeypatch):
    upstream = FakeUpstream([
        b": keep-alive",
        b'data: {"model":"deepseek-flash","choices":[{"delta":{"content":"**Xin "}}]}',
        'data: {"choices":[{"delta":{"content":"chào**"}}]}'.encode(),
        b"data: [DONE]",
    ])
    calls = []
    monkeypatch.setattr(assistant_service, "_prepare_request", lambda *_: ([{"role": "user", "content": "test"}], [], "test-key"))
    monkeypatch.setattr(assistant_service.requests, "post", lambda *args, **kwargs: (calls.append(kwargs), upstream)[1])

    output = "".join(assistant_service.stream_answer("hi", {}, []))

    assert _event("delta", {"text": "**Xin "}) in output
    assert _event("delta", {"text": "chào**"}) in output
    assert _event("done", {"model": "deepseek-flash", "sources": []}) in output
    assert calls[0]["stream"] is True
    assert calls[0]["json"]["stream"] is True
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert upstream.closed


def test_stream_reports_interrupted_provider_response(monkeypatch):
    class InterruptedUpstream(FakeUpstream):
        def iter_lines(self, chunk_size=1):
            yield b'data: {"choices":[{"delta":{"content":"Phan dau"}}]}'
            raise requests.ConnectionError("upstream disconnected")

    upstream = InterruptedUpstream([])
    monkeypatch.setattr(assistant_service, "_prepare_request", lambda *_: ([{"role": "user", "content": "test"}], [], "test-key"))
    monkeypatch.setattr(assistant_service.requests, "post", lambda *args, **kwargs: upstream)

    output = "".join(assistant_service.stream_answer("hi", {}, []))

    assert 'event: delta' in output
    assert 'event: error' in output
    assert 'event: done' not in output
    assert upstream.closed


def test_stream_rejects_provider_error_before_sending_sse(monkeypatch):
    upstream = FakeUpstream([])
    upstream.ok = False
    monkeypatch.setattr(assistant_service, "_prepare_request", lambda *_: ([{"role": "user", "content": "test"}], [], "test-key"))
    monkeypatch.setattr(assistant_service.requests, "post", lambda *args, **kwargs: upstream)

    with pytest.raises(assistant_service.AssistantError) as error:
        assistant_service.stream_answer("hi", {}, [])

    assert error.value.status_code == 503
    assert upstream.closed


def test_stream_route_requires_login_and_keeps_sse_content_type(monkeypatch):
    client = app.test_client()
    assert client.post("/api/assistant/chat/stream", json={"message": "hi"}).status_code == 401

    monkeypatch.setitem(app.config, "JWT_SECRET_KEY", "test-auth-secret")
    token = jwt.encode(
        {"sub": "7", "username": "student", "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)},
        "test-auth-secret",
        algorithm="HS256",
    )
    monkeypatch.setattr("app.stream_answer", lambda *_: iter([_event("delta", {"text": "Xin chào"}), _event("done", {"model": "test", "sources": []})]))

    response = client.post(
        "/api/assistant/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "hi", "profile": {}, "history": []},
    )

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache, no-transform"
    assert 'event: delta' in response.get_data(as_text=True)
