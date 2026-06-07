# Logistics MCP Server

A production-deployed [Model Context Protocol](https://modelcontextprotocol.io) server that exposes logistics-domain tools — shipment tracking, driver lookup, fleet availability, and compliance checks — to AI agents like Claude.

**Live endpoint:** `https://logistics-mcp-202947932379.us-central1.run.app/mcp`
**Status:** Deployed on Google Cloud Run

<iframe width="560" height="315" src="https://www.youtube.com/embed/Crw5bPiK9j4" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>---

## What is this?

Modern AI assistants like Claude are powerful, but they can't see into your business systems by default. The Model Context Protocol (MCP) is a recent open standard — originally developed by Anthropic, now industry-wide — that lets AI assistants talk to your databases, APIs, and internal tools through a consistent interface.

This project is a working MCP server for a logistics company's operations. With it connected, you can ask Claude things like:

- *"What's the status of shipment SHP-1001?"*
- *"Find me an available driver near Toronto."*
- *"Is driver DRV-201 cleared to dispatch right now?"*
- *"Mark SHP-1001 as delivered."*

…and Claude will reach into the system, look up the answer, take action where needed, and reply in natural language. No SQL, no API docs, no custom UI to learn. The same pattern generalizes to any business domain: customer accounts, inventory, ticketing systems, internal wikis.

This particular server is a portfolio demonstration — the data is mocked — but the architecture, deployment, and tool design mirror what a real production MCP server looks like.

---

## Try it yourself

You can connect this server to Claude Desktop in under two minutes and ask it questions directly.

1. Download Claude Desktop from [claude.ai/download](https://claude.ai/download) if you don't already have it.
2. Open Claude Desktop → **Settings** → **Connectors** → scroll down → **Add custom connector**.
3. Paste this URL:
   ```
   https://logistics-mcp-202947932379.us-central1.run.app/mcp
   ```
4. Name it `logistics-remote` (or whatever you like), save, and restart Claude Desktop.
5. Open a new chat and ask: *"Using the logistics tools, what's the status of shipment SHP-1001?"*

You'll see Claude discover the available tools, pick the right one, call it against the live deployed server, and use the response in its answer.

---

## Tool surface

The server exposes five tools to any connected MCP client:

| Tool | Purpose |
|------|---------|
| `get_shipment_status` | Look up the current status, origin, destination, and ETA of a shipment by ID |
| `update_shipment_status` | Change a shipment's status (e.g. mark as delivered) |
| `lookup_driver` | Retrieve a driver's record, including remaining Hours of Service (HOS) and license validity |
| `find_available_drivers` | Find drivers currently available for dispatch, optionally filtered by location |
| `check_compliance` | Run an automated compliance audit on a driver covering HOS limits and license expiration |

Each tool is a single decorated Python function. Type hints generate the input/output JSON schema automatically; docstrings become the descriptions the LLM reads when deciding which tool to call.

---

## Architecture

```
┌─────────────────────┐
│  MCP Client         │   Claude Desktop, MCP Inspector, custom agent, etc.
│  (any client)       │
└──────────┬──────────┘
           │   HTTPS POST /mcp
           │   JSON-RPC 2.0 envelope
           ▼
┌─────────────────────┐
│  Google Cloud Run   │   TLS termination at the edge, autoscaled container
│  (us-central1)      │   instances, scales to zero when idle
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  FastMCP server     │   Validates JSON-RPC, dispatches to tool by name,
│  (this codebase)    │   serializes return values back over the wire
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Mock data layer    │   In-memory Python dicts (SHIPMENTS, DRIVERS)
│  (in-memory)        │   Production swap target: dispatch DB / TMS API
└─────────────────────┘
```

The server uses the [official Anthropic Python SDK](https://github.com/modelcontextprotocol/python-sdk) with **Streamable HTTP transport** for remote deployment. Stateless mode (`stateless_http=True`) is enabled so any container instance can handle any request — no session affinity required, which is what makes horizontal autoscaling work cleanly.

---

## Tech stack

- **Python 3.11** with the official `mcp` SDK
- **FastMCP** for tool registration and protocol handling
- **Google Cloud Run** for serverless container hosting
- **Docker** (Python slim base image) for the build
- **Cloud Build** + **Artifact Registry** for CI/CD-style image management

Total cost of running this deployment: **$0/month** at portfolio traffic. Cloud Run's free tier covers 2M requests, 360K vCPU-seconds, and 180K GiB-seconds of memory per month — more than enough for a demo with a hard `--max-instances 2` cap.

---

## Running it locally

If you'd rather run the server on your own machine instead of (or in addition to) using the live deployment:

```bash
# Clone and enter the project
git clone https://github.com/JeffreyWong05/logistics-mcp-server.git
cd logistics-mcp-server

# Create a virtual environment
python -m venv venv
source venv/bin/activate          # macOS/Linux
# .\venv\Scripts\Activate.ps1     # Windows PowerShell

# Install the dependency
pip install "mcp[cli]"

# Run the server (stdio transport by default)
python logistics_server.py
```

For testing the local server, use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector python logistics_server.py
```

This opens a web UI where you can call each tool interactively.

---

## Testing the deployed server

Two ways, both included in the repo.

**Smoke test suite.** A Python script exercises every tool against the live URL and reports pass/fail:

```bash
python tests/smoke_test.py
```

Exit code 0 if all checks pass, 1 if any fail — suitable for CI gating.

**Manual curl test.** A single command to verify the server is reachable and responding:

```bash
curl -X POST https://logistics-mcp-202947932379.us-central1.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

A successful response returns a JSON-RPC envelope listing all five tools with their schemas.

---

## Deployment

The server is deployed to Google Cloud Run from this repo. To deploy your own copy:

```bash
gcloud run deploy logistics-mcp \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --max-instances 2 \
  --min-instances 0 \
  --memory 256Mi \
  --cpu 1
```

`--max-instances 2` caps how aggressively Cloud Run scales — both to control costs and to bound exposure if the public URL ever gets hammered. `--min-instances 0` ensures the service scales to zero (and thus to $0) when idle.

The Dockerfile (`Dockerfile` in the repo root) uses `python:3.11-slim`, installs from `requirements.txt`, exposes port 8080, and runs `logistics_server.py`. Cloud Build picks all of this up automatically from `--source .`.

---

## Project structure

```
logistics-mcp-server/
├── logistics_server.py       # Server: tool definitions, mock data layer, entry point
├── requirements.txt          # Minimal: just mcp[cli]
├── Dockerfile                # python:3.11-slim, port 8080
├── .gcloudignore             # Excludes venv/, __pycache__/, etc. from deploys
├── tests/
│   └── smoke_test.py         # End-to-end test suite against the live URL
└── README.md                 # This file
```

---

## Limitations

Worth being upfront about, since some of these would matter in a real production deployment:

- **The data layer is mocked.** `SHIPMENTS` and `DRIVERS` are Python dicts in memory. A real system would back these with a database (dispatch DB, TMS API, etc.) and replace the dict lookups with queries.
- **Mutations don't persist.** Calling `update_shipment_status` modifies the in-memory dict, but only on whichever container instance handled the request. When Cloud Run scales to zero (after a few minutes of idle) and spins up a fresh instance later, all updates are lost. Two requests in quick succession may also land on different instances, so a `get` immediately after an `update` may show the old value. Both behaviors are expected given the in-memory data layer.
- **No authentication.** The endpoint is `--allow-unauthenticated` for ease of demonstration. Production would add API key validation, OAuth, or mTLS — and the underlying Cloud Run service supports any of these.
- **No persistence of audit history.** A real compliance system would log every `check_compliance` call to an append-only audit log; this version just returns the verdict.
- **Limited error surface.** Tools return error dicts (`{"error": "..."}`) rather than raising MCP-protocol errors. Both are valid, but a production server would likely use proper protocol errors for things like authentication failures while reserving the error-dict pattern for domain-level "not found" cases.
- **No observability beyond stdout logging.** Cloud Run captures `logger.info` lines, which is enough for a demo. Production would add structured logging (JSON output with request IDs), metrics export (Cloud Monitoring or OpenTelemetry), and distributed tracing for multi-hop agent workflows.

These aren't bugs — they're scope choices that keep the project focused on demonstrating the MCP server pattern itself. Each one has a well-understood production-grade solution.

---

## License

MIT — feel free to fork, adapt, or use as a reference for your own MCP server projects.

---

*Built by [Jeffrey Wong](https://linkedin.com/in/jeffreywong05) as a demonstration of production MCP server engineering. Questions or want to discuss MCP architecture? Reach out on LinkedIn or GitHub.*
