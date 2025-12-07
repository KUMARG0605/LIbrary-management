# Local Production Deployment Script
Write-Host "Starting Library Management System Deployment..." -ForegroundColor Green

# Set environment variables
$env:FLASK_APP = "app_new.py"
$env:FLASK_ENV = "production"

# Check if database exists
if (!(Test-Path "instance/library_dev.db")) {
    Write-Host "Database not found. Please run init_database.py first" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting application on http://0.0.0.0:5000" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""
Write-Host "Deployment Options:" -ForegroundColor Yellow
Write-Host "1. For local access: http://localhost:5000" -ForegroundColor White
Write-Host "2. For network access: http://YOUR_LOCAL_IP:5000" -ForegroundColor White
Write-Host ""

# Run with Flask (production mode with threading)
python app_new.py
