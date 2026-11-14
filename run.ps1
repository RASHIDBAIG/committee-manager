Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  Committee Manager Chalu..." -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  Browser: http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "  Password: admin123" -ForegroundColor Green
Write-Host "  Band karne: Ctrl + C" -ForegroundColor Yellow
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
if (-not (Test-Path "venv")) {
    Write-Host "ERROR: Pehle setup.ps1 chalayein." -ForegroundColor Red
    Read-Host "Enter dabayein"; exit 1
}
Start-Process "http://127.0.0.1:5000"
& ".\venv\Scripts\python.exe" app.py