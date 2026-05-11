# Start LangGraph AI Agent Server
Write-Host "🚀 Starting Sweden Relocators AI Agent..." -ForegroundColor Green
Write-Host ""

# Check if virtual environment exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "✓ Activating virtual environment..." -ForegroundColor Cyan
    & venv\Scripts\Activate.ps1
} else {
    Write-Host "⚠️  Virtual environment not found. Using global Python..." -ForegroundColor Yellow
}

# Check if dependencies are installed
Write-Host "✓ Checking dependencies..." -ForegroundColor Cyan
$packages = @("fastapi", "uvicorn", "langchain", "langgraph")
foreach ($package in $packages) {
    $installed = pip list | Select-String -Pattern "^$package "
    if (-not $installed) {
        Write-Host "⚠️  Missing package: $package" -ForegroundColor Yellow
        Write-Host "   Run: pip install -r requirements.txt" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host "  LANGGRAPH AI AGENT SERVER" -ForegroundColor Magenta
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host ""
Write-Host "  🌐 Server:    http://localhost:8000" -ForegroundColor Green
Write-Host "  🧪 Frontend:  http://localhost:8000/static/index.html" -ForegroundColor Green
Write-Host "  📚 API Docs:  http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host ""
Write-Host "✓ Starting server..." -ForegroundColor Cyan
Write-Host ""

# Start the server
uvicorn app:app --reload --port 8000 --host 0.0.0.0
