from __future__ import annotations

from customer_facing.fastapi_server import _error_status_from_response as fastapi_status
from customer_facing.http_openapi_server import (
    _error_status_from_response as http_status,
    _http_status_for_run_response,
)


def test_fastapi_status_uses_error_status_field() -> None:
    response = {"error": {"code": "invalid_request", "status": 400}}
    assert fastapi_status(response) == 400


def test_fastapi_status_falls_back_to_not_found_code() -> None:
    response = {"error": {"code": "not_found"}}
    assert fastapi_status(response) == 404


def test_http_status_uses_error_status_field() -> None:
    response = {"error": {"code": "runtime_error", "status": 500}}
    assert http_status(response) == 500


def test_http_status_success_default_is_preserved() -> None:
    ok_response = {"ok": True, "data": {"run_id": "r-1"}}
    assert _http_status_for_run_response(ok_response, success_status=202) == 202


def test_http_status_for_error_overrides_success_default() -> None:
    error_response = {"error": {"code": "invalid_request", "status": 400}}
    assert _http_status_for_run_response(error_response, success_status=202) == 400
