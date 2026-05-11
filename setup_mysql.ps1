# MySQL Setup Script for LangGraph AI Agent
# Run this script to automatically set up the database

Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "MySQL Database Setup for LangGraph AI Agent" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# Check if MySQL is installed
Write-Host "Step 1: Checking MySQL installation..." -ForegroundColor Yellow
$mysqlService = Get-Service -Name "MySQL80" -ErrorAction SilentlyContinue

if (-not $mysqlService) {
    Write-Host "ERROR: MySQL service not found!" -ForegroundColor Red
    Write-Host "Please install MySQL from: https://dev.mysql.com/downloads/installer/" -ForegroundColor Red
    exit 1
}

Write-Host "  MySQL service found: $($mysqlService.Status)" -ForegroundColor Green

# Check if MySQL is running
if ($mysqlService.Status -ne "Running") {
    Write-Host "  Starting MySQL service..." -ForegroundColor Yellow
    Start-Service MySQL80
    Start-Sleep -Seconds 3
    Write-Host "  MySQL service started!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 2: Database Credentials" -ForegroundColor Yellow
Write-Host "  Please enter your MySQL root password:" -ForegroundColor White
$rootPassword = Read-Host -AsSecureString "  Password"
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($rootPassword)
$password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

Write-Host ""
Write-Host "Step 3: Creating database..." -ForegroundColor Yellow

# Create database
$createDbCommand = @"
CREATE DATABASE IF NOT EXISTS sweden_relocators_ai 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;
"@

try {
    $output = mysql -u root -p"$password" -e $createDbCommand 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Database created successfully!" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Failed to create database" -ForegroundColor Red
        Write-Host "  $output" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ERROR: MySQL command failed" -ForegroundColor Red
    Write-Host "  $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 4: Importing schema..." -ForegroundColor Yellow

# Check if schema file exists
$schemaPath = Join-Path $PSScriptRoot "..\database_schema.sql"
if (-not (Test-Path $schemaPath)) {
    Write-Host "  ERROR: Schema file not found at: $schemaPath" -ForegroundColor Red
    exit 1
}

# Import schema
try {
    Get-Content $schemaPath | mysql -u root -p"$password" sweden_relocators_ai 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Schema imported successfully!" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Failed to import schema" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ERROR: Schema import failed" -ForegroundColor Red
    Write-Host "  $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 5: Verifying tables..." -ForegroundColor Yellow

$showTablesCommand = "USE sweden_relocators_ai; SHOW TABLES;"
$tables = mysql -u root -p"$password" -e $showTablesCommand 2>&1

if ($tables -match "conversation_logs" -and $tables -match "admin_queue") {
    Write-Host "  All tables created:" -ForegroundColor Green
    Write-Host "    - conversation_logs" -ForegroundColor Green
    Write-Host "    - admin_availability" -ForegroundColor Green
    Write-Host "    - admin_queue" -ForegroundColor Green
    Write-Host "    - analytics_events" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Some tables might be missing" -ForegroundColor Yellow
    Write-Host $tables
}

Write-Host ""
Write-Host "Step 6: Creating .env file..." -ForegroundColor Yellow

# Create .env from .env.example
$envPath = Join-Path $PSScriptRoot ".env"
$envExamplePath = Join-Path $PSScriptRoot ".env.example"

if (Test-Path $envPath) {
    Write-Host "  .env file already exists. Creating backup..." -ForegroundColor Yellow
    $backupPath = Join-Path $PSScriptRoot ".env.backup.$(Get-Date -Format 'yyyy-MM-dd-HHmmss')"
    Copy-Item $envPath $backupPath
    Write-Host "  Backup created: $backupPath" -ForegroundColor Green
}

# Copy .env.example to .env
Copy-Item $envExamplePath $envPath -Force

# Update DATABASE_URL in .env
$envContent = Get-Content $envPath -Raw
$envContent = $envContent -replace 'mysql\+asyncmy://root:password@', "mysql+asyncmy://root:$password@"
Set-Content -Path $envPath -Value $envContent

Write-Host "  .env file created and configured!" -ForegroundColor Green
Write-Host "  DATABASE_URL updated with your password" -ForegroundColor Green

Write-Host ""
Write-Host "Step 7: Adding sample admin..." -ForegroundColor Yellow

$addAdminCommand = @"
USE sweden_relocators_ai;
INSERT INTO admin_availability (admin_name, admin_email, is_available, max_concurrent_chats)
VALUES ('Admin User', 'admin@swedenrelocators.se', 1, 5)
ON DUPLICATE KEY UPDATE admin_name=admin_name;
"@

mysql -u root -p"$password" -e $addAdminCommand 2>&1 | Out-Null
Write-Host "  Sample admin added!" -ForegroundColor Green

Write-Host ""
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "=" -ForegroundColor Cyan -NoNewline
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

Write-Host "Database Information:" -ForegroundColor Cyan
Write-Host "  Database Name: sweden_relocators_ai" -ForegroundColor White
Write-Host "  Host: localhost:3306" -ForegroundColor White
Write-Host "  User: root" -ForegroundColor White
Write-Host "  Tables: 4 tables created" -ForegroundColor White
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Edit .env file and add your GROQ_API_KEY:" -ForegroundColor White
Write-Host "     code .env" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Test the database connection:" -ForegroundColor White
Write-Host "     python test_db_connection.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Run the workflow tests:" -ForegroundColor White
Write-Host "     python test_workflow.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Start the API server:" -ForegroundColor White
Write-Host "     uvicorn app:app --reload --port 8000" -ForegroundColor Gray
Write-Host ""

Write-Host "Documentation:" -ForegroundColor Cyan
Write-Host "  - Full setup guide: MYSQL_SETUP_GUIDE.md" -ForegroundColor White
Write-Host "  - Quick start: QUICKSTART.md" -ForegroundColor White
Write-Host "  - Architecture: ARCHITECTURE.md" -ForegroundColor White
Write-Host ""

Write-Host "Done! Your database is ready for the LangGraph AI Agent!" -ForegroundColor Green
