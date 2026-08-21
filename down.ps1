# down.ps1  --  Delete the service so nothing can bill while you're not demoing.
# Usage:  .\down.ps1

$ErrorActionPreference = "Stop"

$PROJECT = "logistics-mcp-demo"
$SERVICE = "logistics-mcp"
$REGION  = "us-central1"

Write-Host "Deleting $SERVICE from $PROJECT ($REGION)..." -ForegroundColor Cyan

gcloud run services delete $SERVICE `
  --project $PROJECT --region $REGION --quiet

Write-Host "Gone. Nothing is billing now." -ForegroundColor Green
