# Redis Auto-Start Feature

## Overview

The Vechnost Bot now includes a sophisticated Redis auto-start system that automatically manages Redis instances during deployment. This feature ensures high availability and graceful fallback to in-memory storage when Redis is unavailable.

## Features

### 🚀 **Automatic Redis Management**
- **Auto-Start**: Automatically starts Redis when the bot deploys
- **Health Monitoring**: Continuous health checks with automatic restart
- **Graceful Fallback**: Falls back to in-memory storage if Redis fails
- **Cross-Platform**: Works on Windows, Linux, and macOS

### 🔧 **Deployment Modes**

#### 1. **Auto-Start Mode (Default)**
```bash
# Deploy with Redis auto-start
./deploy.sh auto
# or
.\deploy.ps1 -Mode auto
```

**Features:**
- Bot automatically starts Redis if not available
- Falls back to in-memory storage if Redis fails
- No external dependencies required
- Perfect for development and simple deployments

#### 2. **External Redis Mode**
```bash
# Deploy with external Redis container
./deploy.sh redis
# or
.\deploy.ps1 -Mode redis
```

**Features:**
- Uses dedicated Redis container
- Better for production environments
- Persistent data storage
- Full Redis features available

## Architecture

### Redis Manager (`redis_manager.py`)
```python
class RedisManager:
    """Manages Redis instance lifecycle with auto-start and health monitoring."""

    async def start_redis(self) -> bool:
        """Start Redis instance with retry logic."""

    async def health_check(self) -> bool:
        """Check if Redis is healthy."""

    async def cleanup(self):
        """Cleanup Redis resources."""
```

### Hybrid Storage (`hybrid_storage.py`)
```python
class HybridStorage:
    """Hybrid storage with Redis auto-start and fallback to in-memory."""

    async def _ensure_redis_connection(self) -> bool:
        """Ensure Redis connection is available with auto-start."""
```

### Auto-Start Manager (`redis_manager.py`)
```python
class RedisAutoStartManager:
    """High-level Redis auto-start manager with fallback strategy."""

    async def initialize(self) -> bool:
        """Initialize Redis with auto-start and fallback."""
```

## Configuration

### Environment Variables
```bash
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional
LOG_LEVEL=INFO
REDIS_URL=redis://localhost:6379
REDIS_AUTO_START=true
```

### Docker Compose Configuration
```yaml
services:
  # Redis service (optional - bot can auto-start Redis)
  redis:
    image: redis:7-alpine
    container_name: vechnost-redis
    ports:
      - "6379:6379"
    profiles:
      - redis-external  # Only start with --profile redis-external

  # Bot service with Redis auto-start capability
  vechnost-bot:
    build: .
    environment:
      - REDIS_AUTO_START=true
    # No depends_on - bot will auto-start Redis or fallback to memory
```

## Usage Examples

### Development Setup
```bash
# Simple development deployment
export TELEGRAM_BOT_TOKEN="your_token"
./deploy.sh auto
```

### Production Setup
```bash
# Production with external Redis
export TELEGRAM_BOT_TOKEN="your_token"
./deploy.sh redis
```

### Docker Compose Usage
```bash
# Auto-start mode (default)
docker-compose up -d vechnost-bot

# External Redis mode
docker-compose --profile redis-external up -d
```

## Monitoring and Logs

### Check Deployment Status
```bash
# Show status
./deploy.sh status
# or
.\deploy.ps1 -Command status
```

### View Logs
```bash
# View bot logs
./deploy.sh logs
# or
.\deploy.ps1 -Command logs

# View Redis logs (if external)
docker logs vechnost-redis
```

### Health Monitoring
The system automatically monitors Redis health and provides detailed logging:

```
2025-09-23 15:18:20 [info     ] initializing_redis_auto_start
2025-09-23 15:18:20 [info     ] starting_redis_instance
2025-09-23 15:18:20 [info     ] redis_startup_attempt attempt=1 max_attempts=3
2025-09-23 15:18:20 [warning  ] redis_auto_start_failed_fallback_to_memory
```

## Fallback Strategy

### When Redis Auto-Start Fails:
1. **Detection**: System detects Redis is not available
2. **Logging**: Logs warning about fallback
3. **Fallback**: Switches to in-memory storage
4. **Continuation**: Bot continues to work normally
5. **Retry**: Periodically attempts to reconnect to Redis

### Storage Modes:
- **Redis Mode**: Persistent storage with full Redis features
- **Memory Mode**: Fast in-memory storage for development
- **Hybrid Mode**: Automatic switching between modes

## Performance Characteristics

### Redis Mode
- ✅ **Persistent**: Data survives restarts
- ✅ **Scalable**: Handles multiple bot instances
- ✅ **Feature-Rich**: Full Redis capabilities
- ⚠️ **Resource**: Requires Redis installation

### Memory Mode
- ✅ **Fast**: In-memory operations
- ✅ **Simple**: No external dependencies
- ✅ **Reliable**: Always available
- ⚠️ **Temporary**: Data lost on restart

## Troubleshooting

### Common Issues

#### 1. Redis Not Found
```
[ERROR] Redis server binary not found. Please install Redis or use Docker.
```
**Solution**: Install Redis or use Docker mode

#### 2. Connection Failed
```
[WARNING] redis_connection_failed
```
**Solution**: Check Redis installation and port availability

#### 3. Fallback to Memory
```
[WARNING] redis_auto_start_failed_fallback_to_memory
```
**Solution**: This is normal behavior when Redis is unavailable

### Debug Commands
```bash
# Check Redis status
docker ps | grep redis

# Test Redis connection
redis-cli ping

# View detailed logs
docker logs vechnost-bot --tail 50
```

## Best Practices

### Development
- Use auto-start mode for simplicity
- Monitor logs for Redis status
- Test fallback behavior

### Production
- Use external Redis for persistence
- Monitor Redis health metrics
- Set up Redis backups
- Use Redis clustering for high availability

### Security
- Use Redis authentication in production
- Restrict Redis network access
- Monitor Redis logs for security events

## Migration Guide

### From Manual Redis Setup
1. Remove manual Redis dependencies
2. Update deployment scripts
3. Test auto-start functionality
4. Verify fallback behavior

### From In-Memory Only
1. Enable Redis auto-start
2. Test Redis functionality
3. Monitor performance improvements
4. Configure persistence settings

## Support

For issues or questions about the Redis auto-start feature:

1. Check the logs for detailed error messages
2. Verify Redis installation and configuration
3. Test fallback behavior
4. Review this documentation

The system is designed to be robust and self-healing, automatically handling Redis availability issues without manual intervention.
