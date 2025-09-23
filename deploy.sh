#!/bin/bash

# Vechnost Bot Deployment Script with Redis Auto-Start
# This script handles deployment with automatic Redis management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BOT_NAME="vechnost-bot"
REDIS_NAME="vechnost-redis"
COMPOSE_FILE="docker-compose.yml"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    log_success "Docker is running"
}

# Check if required environment variables are set
check_environment() {
    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        log_error "TELEGRAM_BOT_TOKEN environment variable is not set"
        log_info "Please set it with: export TELEGRAM_BOT_TOKEN='your_token_here'"
        exit 1
    fi
    log_success "Environment variables are set"
}

# Stop existing containers
stop_containers() {
    log_info "Stopping existing containers..."

    # Stop bot container
    if docker ps -q -f name=$BOT_NAME | grep -q .; then
        docker stop $BOT_NAME
        log_success "Stopped $BOT_NAME"
    fi

    # Stop Redis container if running externally
    if docker ps -q -f name=$REDIS_NAME | grep -q .; then
        docker stop $REDIS_NAME
        log_success "Stopped $REDIS_NAME"
    fi

    # Remove stopped containers
    docker container prune -f
}

# Build the bot image
build_image() {
    log_info "Building bot image..."
    docker-compose build --no-cache
    log_success "Bot image built successfully"
}

# Deploy with Redis auto-start (default)
deploy_with_auto_start() {
    log_info "Deploying with Redis auto-start..."
    log_info "The bot will automatically start Redis or fallback to in-memory storage"

    docker-compose up -d vechnost-bot

    # Wait for bot to start
    log_info "Waiting for bot to initialize..."
    sleep 10

    # Check if bot is running
    if docker ps -q -f name=$BOT_NAME | grep -q .; then
        log_success "Bot deployed successfully with Redis auto-start"
        log_info "Check logs with: docker logs $BOT_NAME"
    else
        log_error "Bot failed to start"
        docker logs $BOT_NAME
        exit 1
    fi
}

# Deploy with external Redis
deploy_with_external_redis() {
    log_info "Deploying with external Redis..."

    # Start Redis first
    docker-compose --profile redis-external up -d redis

    # Wait for Redis to be healthy
    log_info "Waiting for Redis to be healthy..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if docker exec $REDIS_NAME redis-cli ping > /dev/null 2>&1; then
            log_success "Redis is healthy"
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done

    if [ $timeout -le 0 ]; then
        log_error "Redis failed to start within timeout"
        exit 1
    fi

    # Start bot
    docker-compose up -d vechnost-bot

    # Wait for bot to start
    log_info "Waiting for bot to initialize..."
    sleep 10

    # Check if bot is running
    if docker ps -q -f name=$BOT_NAME | grep -q .; then
        log_success "Bot deployed successfully with external Redis"
        log_info "Check logs with: docker logs $BOT_NAME"
    else
        log_error "Bot failed to start"
        docker logs $BOT_NAME
        exit 1
    fi
}

# Show deployment status
show_status() {
    log_info "Deployment Status:"
    echo

    # Bot status
    if docker ps -q -f name=$BOT_NAME | grep -q .; then
        log_success "Bot: Running"
        docker logs --tail 10 $BOT_NAME
    else
        log_error "Bot: Not running"
    fi

    echo

    # Redis status
    if docker ps -q -f name=$REDIS_NAME | grep -q .; then
        log_success "External Redis: Running"
    else
        log_info "External Redis: Not running (using auto-start or in-memory)"
    fi
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    docker-compose down
    docker system prune -f
    log_success "Cleanup completed"
}

# Main deployment function
deploy() {
    local mode=${1:-"auto"}

    log_info "Starting Vechnost Bot deployment..."
    log_info "Mode: $mode"
    echo

    check_docker
    check_environment
    stop_containers
    build_image

    case $mode in
        "auto"|"autostart")
            deploy_with_auto_start
            ;;
        "redis"|"external")
            deploy_with_external_redis
            ;;
        *)
            log_error "Unknown deployment mode: $mode"
            log_info "Available modes: auto, redis"
            exit 1
            ;;
    esac

    echo
    show_status
    echo
    log_success "Deployment completed successfully!"
    log_info "Use 'docker logs $BOT_NAME' to view bot logs"
    log_info "Use 'docker logs $REDIS_NAME' to view Redis logs (if external)"
}

# Help function
show_help() {
    echo "Vechnost Bot Deployment Script"
    echo
    echo "Usage: $0 [MODE] [COMMAND]"
    echo
    echo "Modes:"
    echo "  auto, autostart    Deploy with Redis auto-start (default)"
    echo "  redis, external    Deploy with external Redis container"
    echo
    echo "Commands:"
    echo "  deploy            Deploy the bot (default)"
    echo "  status            Show deployment status"
    echo "  logs              Show bot logs"
    echo "  cleanup           Clean up containers and images"
    echo "  help              Show this help message"
    echo
    echo "Examples:"
    echo "  $0                           # Deploy with auto-start"
    echo "  $0 auto                      # Deploy with auto-start"
    echo "  $0 redis                     # Deploy with external Redis"
    echo "  $0 status                    # Show status"
    echo "  $0 logs                      # Show logs"
    echo "  $0 cleanup                   # Clean up"
    echo
    echo "Environment Variables:"
    echo "  TELEGRAM_BOT_TOKEN          Required: Your Telegram bot token"
    echo "  LOG_LEVEL                   Optional: Log level (default: INFO)"
    echo
    echo "Redis Auto-Start Features:"
    echo "  - Automatically starts Redis if not available"
    echo "  - Falls back to in-memory storage if Redis fails"
    echo "  - Health monitoring and automatic restart"
    echo "  - Graceful shutdown handling"
}

# Handle commands
case "${2:-deploy}" in
    "deploy")
        deploy "$1"
        ;;
    "status")
        show_status
        ;;
    "logs")
        if docker ps -q -f name=$BOT_NAME | grep -q .; then
            docker logs -f $BOT_NAME
        else
            log_error "Bot is not running"
        fi
        ;;
    "cleanup")
        cleanup
        ;;
    "help")
        show_help
        ;;
    *)
        log_error "Unknown command: ${2:-deploy}"
        show_help
        exit 1
        ;;
esac
