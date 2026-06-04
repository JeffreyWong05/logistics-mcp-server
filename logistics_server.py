"""
Logistics MCP Server
====================
An MCP server exposing logistics-domain tools (shipment tracking, driver lookup,
fleet availability, compliance checks) to AI agents via the Model Context Protocol.

This is a portfolio demonstration: the data layer is mocked, but the tool surface
mirrors what a real dispatch / TMS / compliance system would expose to an
LLM-driven assistant.

Run locally:
    python logistics_server.py

Test with the MCP Inspector:
    npx @modelcontextprotocol/inspector python logistics_server.py

For remote deployment, swap the transport at the bottom of this file to
"streamable-http" and host on Cloudflare Workers, Cloud Run, or similar.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from mcp.server.fastmcp import FastMCP

from mcp.server.transport_security import TransportSecuritySettings

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("logistics_mcp")

mcp = FastMCP(
    "logistics",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["logistics-mcp-202947932379.us-central1.run.app", "localhost:*", "127.0.0.1:*"],
        allowed_origins=["https://logistics-mcp-202947932379.us-central1.run.app", "http://localhost:*"],
    ),
)
# ---------------------------------------------------------------------------
# Mock data layer
# In a real deployment, replace these dicts with queries against a dispatch
# database, a TMS API, or your fleet management system.
# ---------------------------------------------------------------------------

SHIPMENTS: dict[str, dict] = {
    "SHP-1001": {
        "origin": "Toronto, ON",
        "destination": "Chicago, IL",
        "status": "in_transit",
        "carrier": "Charger-002",
        "eta": "2026-05-31T18:30:00Z",
    },
    "SHP-1002": {
        "origin": "Brampton, ON",
        "destination": "Montreal, QC",
        "status": "delivered",
        "carrier": "Charger-014",
        "eta": "2026-05-29T11:00:00Z",
    },
    "SHP-1003": {
        "origin": "Mississauga, ON",
        "destination": "Detroit, MI",
        "status": "pending_pickup",
        "carrier": None,
        "eta": None,
    },
}

DRIVERS: dict[str, dict] = {
    "DRV-200": {
        "name": "A. Singh",
        "location": "Toronto, ON",
        "hos_remaining_hours": 7.5,
        "license_valid_until": "2027-04-12",
        "status": "available",
    },
    "DRV-201": {
        "name": "M. Chen",
        "location": "Brampton, ON",
        "hos_remaining_hours": 2.0,
        "license_valid_until": "2026-08-30",
        "status": "on_route",
    },
    "DRV-202": {
        "name": "R. Patel",
        "location": "Hamilton, ON",
        "hos_remaining_hours": 10.0,
        "license_valid_until": "2026-06-01",
        "status": "available",
    },
}


# ---------------------------------------------------------------------------
# Tools
# Each @mcp.tool() function becomes callable by any MCP-compatible client.
# Type hints define the input/output JSON schema automatically; docstrings
# become the tool descriptions shown to the LLM.
# ---------------------------------------------------------------------------

@mcp.tool()
def get_shipment_status(shipment_id: str) -> dict:
    """
    Look up the current status of a shipment.

    Args:
        shipment_id: The shipment identifier (e.g. 'SHP-1001').

    Returns:
        Shipment details including origin, destination, status, carrier, and ETA.
        Returns an error dict listing known IDs if the shipment is not found.
    """
    logger.info("Tool call: get_shipment_status(%s)", shipment_id)
    shipment = SHIPMENTS.get(shipment_id)
    if not shipment:
        return {
            "error": f"Shipment '{shipment_id}' not found.",
            "known_ids": list(SHIPMENTS.keys()),
        }
    return {"shipment_id": shipment_id, **shipment}

@mcp.tool()
def update_shipment_status(shipment_id: str, new_status: str) -> dict:
    """
    Update the status of a shipment.

    Args:
        shipment_id: The shipment identifier (e.g. 'SHP-1001').
        new_status: The new status to set (e.g. 'delivered', 'in_transit', 'pending_pickup').

    Returns:
        Updated shipment record. Returns an error dict listing known IDs if not found.
    """
    logger.info("Tool call: update_shipment_status(%s, %r)", shipment_id, new_status)
    shipment = SHIPMENTS.get(shipment_id)
    if not shipment:
        return {
            "error": f"Shipment '{shipment_id}' not found.",
            "known_ids": list(SHIPMENTS.keys()),
        }
    previous_status = shipment["status"]
    shipment["status"] = new_status
    return {
        "shipment_id": shipment_id,
        "previous_status": previous_status,
        **shipment,
    }

@mcp.tool()
def lookup_driver(driver_id: str) -> dict:
    """
    Retrieve a driver's record, including current Hours of Service (HOS) availability.

    Args:
        driver_id: The driver identifier (e.g. 'DRV-200').

    Returns:
        Driver record with name, location, remaining HOS hours, license validity, and status.
    """
    logger.info("Tool call: lookup_driver(%s)", driver_id)
    driver = DRIVERS.get(driver_id)
    if not driver:
        return {"error": f"Driver '{driver_id}' not found."}
    return {"driver_id": driver_id, **driver}


@mcp.tool()
def find_available_drivers(near_location: str | None = None) -> list[dict]:
    """
    Return drivers currently available for dispatch, optionally filtered by location.

    Args:
        near_location: Optional city name to filter on (case-insensitive substring match).

    Returns:
        A list of available driver records. Empty list if none match the filter.
    """
    logger.info("Tool call: find_available_drivers(near_location=%r)", near_location)
    results = []
    for driver_id, driver in DRIVERS.items():
        if driver["status"] != "available":
            continue
        if near_location and near_location.lower() not in driver["location"].lower():
            continue
        results.append({"driver_id": driver_id, **driver})
    return results


@mcp.tool()
def check_compliance(driver_id: str) -> dict:
    """
    Run a compliance check on a driver, covering HOS limits and license validity.

    Args:
        driver_id: The driver identifier to audit.

    Returns:
        A compliance report with pass/fail status and a list of any flagged issues.
    """
    logger.info("Tool call: check_compliance(%s)", driver_id)
    driver = DRIVERS.get(driver_id)
    if not driver:
        return {
            "error": f"Driver '{driver_id}' not found.",
            "compliant": False,
        }

    issues: list[str] = []

    if driver["hos_remaining_hours"] < 3.0:
        issues.append(
            f"Low HOS remaining: {driver['hos_remaining_hours']}h (below 3h threshold)."
        )

    license_expiry = date.fromisoformat(driver["license_valid_until"])
    days_to_expiry = (license_expiry - date.today()).days
    if days_to_expiry < 30:
        issues.append(f"License expires in {days_to_expiry} days.")

    return {
        "driver_id": driver_id,
        "compliant": len(issues) == 0,
        "issues": issues,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Entry point
# Local development uses stdio transport (the default).
# For Sunday's remote deployment, change this to:
#     mcp.run(transport="streamable-http")
# and host the resulting HTTP server on Cloudflare Workers, Google Cloud Run,
# or any platform that can run a long-lived Python process.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8080))
    mcp.run(transport="streamable-http")