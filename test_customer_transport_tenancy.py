from __future__ import annotations

from customer_facing.http_openapi_server import _resolve_tenant_id_for_request
from customer_facing.mcp_tool_bridge import MCPToolBridge


def test_http_tenant_resolution_prefers_authenticated_identity() -> None:
    tenant_id = _resolve_tenant_id_for_request(
        auth_enabled=True,
        authenticated_tenant_id="tenant-acme",
        body={"tenant_id": "tenant-beta"},
    )
    assert tenant_id == "tenant-acme"


def test_http_tenant_resolution_does_not_accept_body_override_with_auth() -> None:
    tenant_id = _resolve_tenant_id_for_request(
        auth_enabled=True,
        authenticated_tenant_id=None,
        body={"tenant_id": "tenant-beta"},
    )
    assert tenant_id is None


def test_http_tenant_resolution_uses_body_when_auth_disabled() -> None:
    tenant_id = _resolve_tenant_id_for_request(
        auth_enabled=False,
        authenticated_tenant_id=None,
        body={"tenant_id": "tenant-acme"},
    )
    assert tenant_id == "tenant-acme"


class _FakeAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute_skill(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "completed"}


class _FakeGateway:
    pass


def test_mcp_skill_execute_propagates_tenant_id() -> None:
    api = _FakeAPI()
    bridge = MCPToolBridge(api=api, gateway=_FakeGateway())

    response = bridge.call_tool(
        name="skill.execute",
        arguments={
            "skill_id": "x.y",
            "inputs": {"n": 1},
            "tenant_id": "tenant-acme",
            "include_trace": False,
        },
    )

    assert response["status"] == "completed"
    assert len(api.calls) == 1
    assert api.calls[0]["execution_channel"] == "mcp"
    assert api.calls[0]["tenant_id"] == "tenant-acme"
