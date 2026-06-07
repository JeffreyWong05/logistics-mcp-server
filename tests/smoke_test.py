"""
Smoke tests for the deployed Logistics MCP server.

Sends JSON-RPC requests directly to the live Cloud Run endpoint and verifies
each tool returns the expected shape. Run after every deploy to confirm the
service is healthy end-to-end.

Usage:
    python tests/smoke_test.py

Exit code 0 if all checks pass, 1 if any fail. Suitable for CI gating.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

SERVER_URL = "https://logistics-mcp-202947932379.us-central1.run.app/mcp"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

def jsonrpc_call(method: str, params: dict | None = None) -> dict[str, Any]:
    """Send one JSON-RPC request to the MCP server and return the parsed envelope."""
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params

    with httpx.Client(timeout=30.0) as client:
        response = client.post(SERVER_URL, json=payload, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def tool_call(name: str, arguments: dict[str, Any]) -> Any:
    """Invoke a specific MCP tool by name and return its parsed return value."""
    envelope = jsonrpc_call("tools/call", {"name": name, "arguments": arguments})
    result_field = envelope["result"]

    # Prefer structuredContent — it carries the full return value in one place,
    # regardless of how many content blocks FastMCP creates.
    structured = result_field.get("structuredContent")
    if structured is not None:
        # FastMCP wraps non-object returns (lists, primitives) as {"result": ...}
        # to satisfy the MCP spec, which requires structured output to be an object.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured

    # Fall back to text content if no structured output is present.
    content_blocks = result_field.get("content", [])
    if not content_blocks:
        return None
    if len(content_blocks) == 1:
        return json.loads(content_blocks[0]["text"])
    # Multiple blocks — FastMCP split a list across them. Reassemble.
    return [json.loads(b["text"]) for b in content_blocks if b.get("type") == "text"]


# ---------------------------------------------------------------------------
# Test driver
# ---------------------------------------------------------------------------

results: list[tuple[str, bool]] = []


def check(label: str, condition: bool, details: str = "") -> None:
    status = "OK  " if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition and details:
        print(f"         {details}")
    results.append((label, condition))


def print_summary() -> None:
    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{'-' * 50}")
    print(f"  {passed} passed, {failed} failed")
    print(f"{'-' * 50}")


def main() -> int:
    print(f"Smoke testing: {SERVER_URL}\n")

    # 1. tools/list -- verify server is reachable and reports its tools
    print("Listing tools")
    try:
        envelope = jsonrpc_call("tools/list")
        tools = envelope.get("result", {}).get("tools", [])
        tool_names = {t["name"] for t in tools}
    except Exception as exc:
        check("Server reachable", False, str(exc))
        print_summary()
        return 1

    check("Server reachable and returns tool list", len(tools) > 0)
    expected = {
        "get_shipment_status",
        "lookup_driver",
        "find_available_drivers",
        "check_compliance",
        "update_shipment_status",
    }
    missing = expected - tool_names
    check("Expected tools present", not missing, f"missing: {sorted(missing)}")

    # 2. get_shipment_status -- happy path
    print("\nTesting get_shipment_status")
    result = tool_call("get_shipment_status", {"shipment_id": "SHP-1001"})
    check("Returns shipment record", result.get("shipment_id") == "SHP-1001")
    check("Includes status field", "status" in result)

    # 3. get_shipment_status -- error path
    result = tool_call("get_shipment_status", {"shipment_id": "BOGUS"})
    check("Returns error for unknown shipment", "error" in result)

    # 4. lookup_driver
    print("\nTesting lookup_driver")
    result = tool_call("lookup_driver", {"driver_id": "DRV-200"})
    check("Returns driver record", result.get("driver_id") == "DRV-200")
    check("Includes HOS remaining", "hos_remaining_hours" in result)

    # 5. find_available_drivers
    print("\nTesting find_available_drivers")
    result = tool_call("find_available_drivers", {"near_location": "Toronto"})
    check("Returns a list", isinstance(result, list))
    print(f"  DEBUG raw envelope: {jsonrpc_call('tools/call', {'name': 'find_available_drivers', 'arguments': {'near_location': 'Toronto'}})!r}")
    check("At least one driver matches", isinstance(result, list) and len(result) > 0)

    # 6. check_compliance
    print("\nTesting check_compliance")
    result = tool_call("check_compliance", {"driver_id": "DRV-200"})
    check("Returns compliance verdict", "compliant" in result)

    # 7. update_shipment_status -- the new tool
    print("\nTesting update_shipment_status")
    result = tool_call(
        "update_shipment_status",
        {"shipment_id": "SHP-1001", "new_status": "delivered"},
    )
    check("Status updated to new value", result.get("status") == "delivered")
    check("Returns previous_status field", "previous_status" in result)

    print_summary()
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())