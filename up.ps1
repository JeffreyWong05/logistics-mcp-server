# up.ps1  --  Spin up the logistics MCP server for a demo.
# Run this from your project folder (the one with your Dockerfile / source).
# Usage:  .\up.ps1

$ErrorActionPreference = "Stop"

$PROJECT = "logistics-mcp-demo"
$SERVICE = "logistics-mcp"
$REGION  = "us-central1"

Write-Host "Deploying $SERVICE to $PROJECT ($REGION)..." -ForegroundColor Cyan

gcloud run deploy $SERVICE `
  --source . `
  --project $PROJECT `
  --region  $REGION `
  --allow-unauthenticated `
  --max-instances=1

$URL = gcloud run services describe $SERVICE `
  --project $PROJECT --region $REGION --format="value(status.url)"

Write-Host ""
Write-Host "Live at: $URL/mcp" -ForegroundColor Green
Write-Host "When you're done, run:  .\down.ps1" -ForegroundColor Yellow

# ---------------------------------------------------------------------------
# HARDENED ALTERNATIVE (no public URL at all -- nothing external can reach it)
# 1. Change --allow-unauthenticated to --no-allow-unauthenticated above.
# 2. During the demo, open a SECOND terminal and run a local authed proxy:
#      gcloud run services proxy logistics-mcp `
#        --project logistics-mcp-demo --region us-central1 --port 8080
# 3. Point your MCP client at  http://127.0.0.1:8080/mcp  instead of the URL.
#    Only you can reach it, and it closes when you close the proxy.
# ---------------------------------------------------------------------------
