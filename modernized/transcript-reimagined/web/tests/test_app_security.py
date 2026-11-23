"""来源校验、错误契约、请求关联 id 与结构化日志（NFR-6）。"""

from __future__ import annotations

import logging

import pytest

from transcript_reimagined.web.routes.pages import inline_json


@pytest.mark.rule("RULE-067")
def test_inline_json_escapes_script_breakers_and_line_separators():
    payload = {"text": "</script><b>&\u2028\u2029"}
    rendered = inline_json(payload)
    assert "</script>" not in rendered
    assert "\\u003c/script\\u003e" in rendered
    assert "\\u0026" in rendered
    assert "\u2028" not in rendered and "\u2029" not in rendered


def test_pages_inline_boot_and_escape(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "window.__BOOT__=" in html
    assert "<script>window.__BOOT__=" in html


def test_host_whitelist_rejects_unknown_host(client):
    response = client.get("/api/status", headers={"Host": "evil.test"})
    assert response.status_code == 400
    assert "Host" in response.json()["error"]


def test_cross_site_origin_is_rejected(client):
    response = client.post(
        "/api/estimate",
        data={"source_path": "/tmp/x.wav"},
        headers={"Origin": "http://evil.test"},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "跨站请求被拒绝"


def test_cross_site_fetch_metadata_is_rejected(client):
    response = client.post(
        "/api/estimate",
        data={"source_path": "/tmp/x.wav"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


def test_same_origin_post_is_allowed(client):
    response = client.post(
        "/api/estimate",
        data={"source_path": "/tmp/definitely-missing.wav"},
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_request_id_is_returned_on_success_and_error(client):
    ok = client.get("/api/status")
    assert ok.headers["X-Request-ID"]
    missing = client.get("/api/tasks/9999")
    assert missing.status_code == 404
    assert missing.headers["X-Request-ID"]


def test_error_contract_is_a_single_error_key(client):
    response = client.get("/api/tasks/9999")
    assert response.status_code == 404
    assert set(response.json()) == {"error"}


def test_failures_are_logged_with_request_id_and_code(client):
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("transcript")
    handler = Capture()
    logger.addHandler(handler)
    try:
        client.get("/api/tasks/9999")
    finally:
        logger.removeHandler(handler)

    failure = next(r for r in records if getattr(r, "code", None) == "http_404")
    assert failure.request_id and failure.request_id != "-"
    assert failure.task_id == "-"
    assert "任务不存在" in failure.getMessage()


@pytest.mark.rule("RULE-063")
def test_removed_upload_endpoint_is_gone(client):
    response = client.post("/api/upload", files={"file": ("a.wav", b"x")})
    assert response.status_code == 404
