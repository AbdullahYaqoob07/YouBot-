# Apply Super Admin Schema to Database
# This script runs the super_admin_schema.sql file against MySQL

$ErrorActionPreference = "Stop"

# Database configuration
$dbUser = "root"
$dbPassword = "pak88523"
$dbName = "sweden_relocators_ai"
$sqlFile = "super_admin_schema.sql"

Write-Host "Applying Super Admin schema to database..." -ForegroundColor Cyan

# Try to find MySQL executable
$mysqlPaths = @(
    "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
    "C:\Program Files\MySQL\MySQL Server 9.0\bin\mysql.exe",
    "C:\xampp\mysql\bin\mysql.exe",
    "C:\wamp\bin\mysql\mysql8.0.27\bin\mysql.exe",
    "mysql.exe"  # Try PATH
)

$mysqlExe = $null
foreach ($path in $mysqlPaths) {
    if (Test-Path $path -ErrorAction SilentlyContinue) {
        $mysqlExe = $path
        Write-Host "Found MySQL at: $mysqlExe" -ForegroundColor Green
        break
    }
    # Try to find in PATH
    if ($path -eq "mysql.exe") {
        try {
            $result = Get-Command mysql -ErrorAction SilentlyContinue
            if ($result) {
                $mysqlExe = "mysql"
                Write-Host "Found MySQL in PATH" -ForegroundColor Green
                break
            }
        } catch {}
    }
}

if (-not $mysqlExe) {
    Write-Host "ERROR: MySQL executable not found!" -ForegroundColor Red
    Write-Host "Please install MySQL or add it to your PATH" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternative: Run SQL manually in MySQL Workbench:" -ForegroundColor Yellow
    Write-Host "1. Open MySQL Workbench" -ForegroundColor White
    Write-Host "2. Connect to your database" -ForegroundColor White
    Write-Host "3. Open file: super_admin_schema.sql" -ForegroundColor White
    Write-Host "4. Execute the SQL statements" -ForegroundColor White
    exit 1
}

# Check if SQL file exists
if (-not (Test-Path $sqlFile)) {
    Write-Host "ERROR: $sqlFile not found!" -ForegroundColor Red
    exit 1
}

try {
    # Read SQL file and execute
    Write-Host "Reading SQL file: $sqlFile" -ForegroundColor Cyan
    $sqlContent = Get-Content $sqlFile -Raw
    
    # Execute SQL using mysql command
    Write-Host "Executing SQL commands..." -ForegroundColor Cyan
    $sqlContent | & $mysqlExe -u $dbUser -p$dbPassword $dbName 2>&1 | Out-String
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Super Admin schema applied successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Changes applied:" -ForegroundColor Cyan
        Write-Host "  - Added 'role' column to admin_availability" -ForegroundColor White
        Write-Host "  - Added super admin tracking to active_conversations" -ForegroundColor White
        Write-Host "  - Added 'is_super_admin' to admin_messages" -ForegroundColor White
        Write-Host "  - Created super_admin_audit_log table" -ForegroundColor White
        Write-Host "  - Created dashboard views" -ForegroundColor White
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "1. Restart your FastAPI server" -ForegroundColor White
        Write-Host "2. Create a super admin user (see SUPER_ADMIN_GUIDE.md)" -ForegroundColor White
        Write-Host "3. Access dashboard at: http://localhost:8000/static/super_admin_dashboard.html" -ForegroundColor White
    } else {
        Write-Host ""
        Write-Host "❌ Error applying schema. Exit code: $LASTEXITCODE" -ForegroundColor Red
        Write-Host "Check the error messages above for details." -ForegroundColor Yellow
    }
} catch {
    Write-Host ""
    Write-Host "❌ Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Verify MySQL is running" -ForegroundColor White
    Write-Host "2. Check database credentials in .env file" -ForegroundColor White
    Write-Host "3. Ensure database 'sweden_relocators_ai' exists" -ForegroundColor White
    exit 1
}
