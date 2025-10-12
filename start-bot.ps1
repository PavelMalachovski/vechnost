#!/usr/bin/env pwsh
# Quick script to start the Vechnost bot with Docker Compose

Write-Host "🔧 Stopping existing containers..." -ForegroundColor Cyan
docker-compose down 2>&1 | Out-Null

Write-Host "🏗️  Building and starting containers..." -ForegroundColor Cyan
docker-compose up --build -d

Write-Host ""
Write-Host "✅ Bot started!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 View logs with:" -ForegroundColor Yellow
Write-Host "   docker-compose logs -f bot" -ForegroundColor White
Write-Host ""
Write-Host "🛑 Stop with:" -ForegroundColor Yellow
Write-Host "   docker-compose down" -ForegroundColor White

