# Vechnost Bot Deployment Script with Redis Auto-Start
# PowerShell version for Windows deployment

param(
    [string]$Mode = "auto",
    [string]$Command = "deploy"
)

# Configuration
$BOT_NAME = "vechnost-bot"
$REDIS_NAME = "vechnost-redis"
$COMPOSE_FILE = "docker-compose.yml"

# Functions
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check if Docker is running
function Test-Docker {
    try {
        docker info | Out-Null
        Write-Success "Docker is running"
        return $true
    }
    catch {
        Write-Error "Docker is not running. Please start Docker Desktop and try again."
        return $false
    }
}

# Check if required environment variables are set
function Test-Environment {
    if (-not $env:TELEGRAM_BOT_TOKEN) {
        Write-Error "TELEGRAM_BOT_TOKEN environment variable is not set"
        Write-Info "Please set it with: `$env:TELEGRAM_BOT_TOKEN='your_token_here'"
        return $false
    }
    Write-Success "Environment variables are set"
    return $true
}

# Stop existing containers
function Stop-Containers {
    Write-Info "Stopping existing containers..."

    # Stop bot container
    $botContainer = docker ps -q -f "name=$BOT_NAME"
    if ($botContainer) {
        docker stop $BOT_NAME
        Write-Success "Stopped $BOT_NAME"
    }

    # Stop Redis container if running externally
    $redisContainer = docker ps -q -f "name=$REDIS_NAME"
    if ($redisContainer) {
        docker stop $REDIS_NAME
        Write-Success "Stopped $REDIS_NAME"
    }

    # Remove stopped containers
    docker container prune -f
}

# Build the bot image
function Build-Image {
    Write-Info "Building bot image..."
    docker-compose build --no-cache
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Bot image built successfully"
    } else {
        Write-Error "Failed to build bot image"
        exit 1
    }
}

# Deploy with Redis auto-start (default)
function Deploy-WithAutoStart {
    Write-Info "Deploying with Redis auto-start..."
    Write-Info "The bot will automatically start Redis or fallback to in-memory storage"

    docker-compose up -d vechnost-bot

    if ($LASTEXITCODE -eq 0) {
        # Wait for bot to start
        Write-Info "Waiting for bot to initialize..."
        Start-Sleep -Seconds 10

        # Check if bot is running
        $botContainer = docker ps -q -f "name=$BOT_NAME"
        if ($botContainer) {
            Write-Success "Bot deployed successfully with Redis auto-start"
            Write-Info "Check logs with: docker logs $BOT_NAME"
        } else {
            Write-Error "Bot failed to start"
            docker logs $BOT_NAME
            exit 1
        }
    } else {
        Write-Error "Failed to start bot container"
        exit 1
    }
}

# Deploy with external Redis
function Deploy-WithExternalRedis {
    Write-Info "Deploying with external Redis..."

    # Start Redis first
    docker-compose --profile redis-external up -d redis

    if ($LASTEXITCODE -eq 0) {
        # Wait for Redis to be healthy
        Write-Info "Waiting for Redis to be healthy..."
        $timeout = 60
        while ($timeout -gt 0) {
            try {
                docker exec $REDIS_NAME redis-cli ping | Out-Null
                Write-Success "Redis is healthy"
                break
            }
            catch {
                Start-Sleep -Seconds 2
                $timeout -= 2
            }
        }

        if ($timeout -le 0) {
            Write-Error "Redis failed to start within timeout"
            exit 1
        }

        # Start bot
        docker-compose up -d vechnost-bot

        if ($LASTEXITCODE -eq 0) {
            # Wait for bot to start
            Write-Info "Waiting for bot to initialize..."
            Start-Sleep -Seconds 10

            # Check if bot is running
            $botContainer = docker ps -q -f "name=$BOT_NAME"
            if ($botContainer) {
                Write-Success "Bot deployed successfully with external Redis"
                Write-Info "Check logs with: docker logs $BOT_NAME"
            } else {
                Write-Error "Bot failed to start"
                docker logs $BOT_NAME
                exit 1
            }
        } else {
            Write-Error "Failed to start bot container"
            exit 1
        }
    } else {
        Write-Error "Failed to start Redis container"
        exit 1
    }
}

# Show deployment status
function Show-Status {
    Write-Info "Deployment Status:"
    Write-Host ""

    # Bot status
    $botContainer = docker ps -q -f "name=$BOT_NAME"
    if ($botContainer) {
        Write-Success "Bot: Running"
        Write-Host "Recent logs:"
        docker logs --tail 10 $BOT_NAME
    } else {
        Write-Error "Bot: Not running"
    }

    Write-Host ""

    # Redis status
    $redisContainer = docker ps -q -f "name=$REDIS_NAME"
    if ($redisContainer) {
        Write-Success "External Redis: Running"
    } else {
        Write-Info "External Redis: Not running (using auto-start or in-memory)"
    }
}

# Cleanup function
function Invoke-Cleanup {
    Write-Info "Cleaning up..."
    docker-compose down
    docker system prune -f
    Write-Success "Cleanup completed"
}

# Main deployment function
function Deploy {
    param([string]$Mode)

    Write-Info "Starting Vechnost Bot deployment..."
    Write-Info "Mode: $Mode"
    Write-Host ""

    if (-not (Test-Docker)) { exit 1 }
    if (-not (Test-Environment)) { exit 1 }

    Stop-Containers
    Build-Image

    switch ($Mode.ToLower()) {
        "auto" { Deploy-WithAutoStart }
        "autostart" { Deploy-WithAutoStart }
        "redis" { Deploy-WithExternalRedis }
        "external" { Deploy-WithExternalRedis }
        default {
            Write-Error "Unknown deployment mode: $Mode"
            Write-Info "Available modes: auto, redis"
            exit 1
        }
    }

    Write-Host ""
    Show-Status
    Write-Host ""
    Write-Success "Deployment completed successfully!"
    Write-Info "Use 'docker logs $BOT_NAME' to view bot logs"
    Write-Info "Use 'docker logs $REDIS_NAME' to view Redis logs (if external)"
}

# Help function
function Show-Help {
    Write-Host "Vechnost Bot Deployment Script (PowerShell)"
    Write-Host ""
    Write-Host "Usage: .\deploy.ps1 [MODE] [COMMAND]"
    Write-Host ""
    Write-Host "Modes:"
    Write-Host "  auto, autostart    Deploy with Redis auto-start (default)"
    Write-Host "  redis, external    Deploy with external Redis container"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  deploy            Deploy the bot (default)"
    Write-Host "  status            Show deployment status"
    Write-Host "  logs              Show bot logs"
    Write-Host "  cleanup           Clean up containers and images"
    Write-Host "  help              Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\deploy.ps1                           # Deploy with auto-start"
    Write-Host "  .\deploy.ps1 -Mode auto                # Deploy with auto-start"
    Write-Host "  .\deploy.ps1 -Mode redis               # Deploy with external Redis"
    Write-Host "  .\deploy.ps1 -Command status           # Show status"
    Write-Host "  .\deploy.ps1 -Command logs              # Show logs"
    Write-Host "  .\deploy.ps1 -Command cleanup           # Clean up"
    Write-Host ""
    Write-Host "Environment Variables:"
    Write-Host "  TELEGRAM_BOT_TOKEN          Required: Your Telegram bot token"
    Write-Host "  LOG_LEVEL                   Optional: Log level (default: INFO)"
    Write-Host ""
    Write-Host "Redis Auto-Start Features:"
    Write-Host "  - Automatically starts Redis if not available"
    Write-Host "  - Falls back to in-memory storage if Redis fails"
    Write-Host "  - Health monitoring and automatic restart"
    Write-Host "  - Graceful shutdown handling"
}

# Handle commands
switch ($Command.ToLower()) {
    "deploy" { Deploy $Mode }
    "status" { Show-Status }
    "logs" {
        $botContainer = docker ps -q -f "name=$BOT_NAME"
        if ($botContainer) {
            docker logs -f $BOT_NAME
        } else {
            Write-Error "Bot is not running"
        }
    }
    "cleanup" { Invoke-Cleanup }
    "help" { Show-Help }
    default {
        Write-Error "Unknown command: $Command"
        Show-Help
        exit 1
    }
}
