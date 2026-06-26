# AEGIS Live Dashboard Launcher
# Sets up environment and launches Streamlit dashboard

Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🛡️  AEGIS Live Dashboard Launcher" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Set PYTHONPATH
$env:PYTHONPATH = "C:\Users\uday_nagisetti\aegis"
Write-Host "✅ PYTHONPATH set to: $env:PYTHONPATH" -ForegroundColor Green
Write-Host ""

# Check if streamlit is installed
try {
    $streamlitVersion = python -m streamlit --version 2>&1
    Write-Host "✅ Streamlit installed: $streamlitVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Streamlit not found. Installing..." -ForegroundColor Yellow
    pip install streamlit
}

Write-Host ""
Write-Host "🚀 Launching AEGIS Live Dashboard..." -ForegroundColor Cyan
Write-Host ""
Write-Host "────────────────────────────────────────────────────────────────" -ForegroundColor Gray
Write-Host "Once loaded, the dashboard will be available at:" -ForegroundColor White
Write-Host "🌐 http://localhost:8501" -ForegroundColor Yellow
Write-Host "────────────────────────────────────────────────────────────────" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop the dashboard" -ForegroundColor DarkGray
Write-Host ""

# Launch Streamlit
python -m streamlit run app_aegis_live.py
