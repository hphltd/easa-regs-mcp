"""Private instance: access key in the path, index from a private GitHub release (token must not leak)."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from easa_regs import asgi

SQLITE = b"SQLite format 3\x00" + b"\x00" * 100


class _FakeGitHub(BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None]] = []

    def log_message(self, *args):  # noqa: ANN002 - keep test output quiet
        pass

    def do_GET(self):  # noqa: N802
        auth = self.headers.get("Authorization")
        _FakeGitHub.seen.append((self.path, auth))
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/repos/hphltd/private/releases/latest":
            if auth != "Bearer s3cret":
                return self._send(401, b"{}")
            body = json.dumps({"assets": [{"name": "manifest.json", "url": base + "/assets/1"},
                                          {"name": "easa_regs.sqlite", "url": base + "/assets/2"}]}).encode()
            return self._send(200, body)
        if self.path == "/assets/2":
            if auth != "Bearer s3cret" or self.headers.get("Accept") != "application/octet-stream":
                return self._send(401, b"")
            self.send_response(302)
            self.send_header("Location", base + "/storage/blob?sig=x")
            self.end_headers()
            return None
        if self.path.startswith("/storage/blob"):
            if auth:                                   # storage rejects a second auth method
                return self._send(400, b"two auth methods")
            return self._send(200, SQLITE)
        return self._send(404, b"")

    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def fake_github():
    srv = HTTPServer(("127.0.0.1", 0), _FakeGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _FakeGitHub.seen = []
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_download_private_index_follows_redirect_without_token(fake_github, tmp_path: Path):
    target = asgi.download_private_index(tmp_path / "idx.sqlite", repo="hphltd/private", token="s3cret",
                                         api=fake_github)
    assert target.read_bytes() == SQLITE
    storage = [auth for path, auth in _FakeGitHub.seen if path.startswith("/storage/")]
    assert storage == [None]                           # the token never reached the storage host


def test_download_private_index_rejects_wrong_token(fake_github, tmp_path: Path):
    with pytest.raises(Exception):
        asgi.download_private_index(tmp_path / "idx.sqlite", repo="hphltd/private", token="wrong", api=fake_github)
    assert not (tmp_path / "idx.sqlite").exists()


def _get(path: str) -> tuple[int, bytes]:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""}
    asyncio.run(asgi.app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


def test_access_key_hides_everything_else(monkeypatch):
    monkeypatch.setattr(asgi, "ACCESS_KEY", "k3y-abc")
    assert _get("/")[0] == 404
    assert _get("/mcp")[0] == 404
    assert _get("/health")[0] == 404
    assert _get("/wrong/")[0] == 404
    status, body = _get("/k3y-abc/")
    assert status == 200 and b"MCP" in body


def test_no_access_key_keeps_public_paths(monkeypatch):
    monkeypatch.setattr(asgi, "ACCESS_KEY", "")
    assert _get("/")[0] == 200
