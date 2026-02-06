# Production startup script for Windows
# Uses Gunicorn with UvicornWorker for maximum performance

param(
    [int]$Workers = 4,
    [int]$Port = 8000,
    [string]$Host = "0.0.0.0"
)

Write-Host "🚀 Starting Sweden Relocators AI Agent in PRODUCTION mode..." -ForegroundColor Green
Write-Host "   Workers: $Workers"
Write-Host "   Host: ${Host}:${Port}"
Write-Host ""

# Check if gunicorn is installed
$gunicornCheck = pip show gunicorn 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing gunicorn..." -ForegroundColor Yellow
    pip install gunicorn uvicorn[standard]
}

# Check if Redis is running (optional)
Write-Host "Checking Redis connection..." -ForegroundColor Cyan
try {
    $redisCheck = redis-cli ping 2>&1
    if ($redisCheck -eq "PONG") {
        Write-Host "✅ Redis is running" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Redis not available - using in-memory cache" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Redis CLI not found - using in-memory cache" -ForegroundColor Yellow
}

# Set production environment
$env:DEBUG = "false"

Write-Host ""
Write-Host "Starting Gunicorn with $Workers workers..." -ForegroundColor Cyan
Write-Host "Health checks available at:"
Write-Host "  - /health  - Full component health"
Write-Host "  - /ready   - Readiness probe"  
Write-Host "  - /live    - Liveness probe"
Write-Host ""

# Start with gunicorn config file
gunicorn app:app `
    --config gunicorn.conf.py `
    --bind "${Host}:${Port}" `
    --workers $Workers

