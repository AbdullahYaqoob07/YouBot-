# Setup MySQL Database Tables
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MySQL Database Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$dbName = "sweden_relocators_ai"
$dbUser = "root"
$dbPassword = "pak88523"
$schemaFile = "..\database_schema.sql"

Write-Host "Step 1: Checking MySQL connection..." -ForegroundColor Yellow
try {
    # Test MySQL connection
    $testQuery = "SELECT VERSION();"
    $result = mysql -u $dbUser -p$dbPassword -e $testQuery 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ MySQL connection successful" -ForegroundColor Green
        Write-Host "  Version: $result" -ForegroundColor Gray
    } else {
        Write-Host "✗ MySQL connection failed" -ForegroundColor Red
        Write-Host "  Error: $result" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error connecting to MySQL: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Creating database '$dbName'..." -ForegroundColor Yellow
$createDbQuery = "CREATE DATABASE IF NOT EXISTS $dbName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u $dbUser -p$dbPassword -e $createDbQuery 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Database created/verified" -ForegroundColor Green
} else {
    Write-Host "✗ Database creation failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 3: Importing schema from $schemaFile..." -ForegroundColor Yellow

if (Test-Path $schemaFile) {
    # Import schema
    Get-Content $schemaFile | mysql -u $dbUser -p$dbPassword $dbName 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Schema imported successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Schema import failed" -ForegroundColor Red
        Write-Host "  Check the error messages above" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✗ Schema file not found: $schemaFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 4: Verifying tables..." -ForegroundColor Yellow
$tables = mysql -u $dbUser -p$dbPassword $dbName -e "SHOW TABLES;" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Tables created successfully:" -ForegroundColor Green
    Write-Host $tables -ForegroundColor Gray
} else {
    Write-Host "✗ Could not verify tables" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Database Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now start the server:" -ForegroundColor Yellow
Write-Host "  python -m uvicorn app:app --reload --port 8000" -ForegroundColor White
Write-Host ""
