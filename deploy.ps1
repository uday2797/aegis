# deploy.ps1 — Deployment guard for AEGIS
#
# POLICY: All Databricks bundle deployments must go through GitHub Actions.
# Do NOT run `databricks bundle deploy` manually from local CLI.
#
# To deploy:
#   Push to master  → CD pipeline triggers automatically
#   Manual deploy   → GitHub UI → Actions → "CD — Deploy to Databricks" → Run workflow

Write-Host ""
Write-Host "========================================================" -ForegroundColor Yellow
Write-Host "  DEPLOYMENT POLICY: Use GitHub Actions only." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Push your changes to master and the CD pipeline" -ForegroundColor Cyan
Write-Host "  will deploy automatically." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Or trigger manually:" -ForegroundColor Cyan
Write-Host "  GitHub -> Actions -> CD Deploy to Databricks -> Run workflow" -ForegroundColor Cyan
Write-Host ""
exit 1
