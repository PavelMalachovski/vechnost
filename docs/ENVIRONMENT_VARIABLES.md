# Environment Variables Reference

This document describes all environment variables used by the Vechnost Telegram bot.

## Required Variables

### Telegram Configuration

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | ✅ Yes | `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `API_TOKEN_TELEGRAM` | Alternative name for bot token | ✅ Yes (if TELEGRAM_BOT_TOKEN not set) | Same as above |

**Note**: Either `TELEGRAM_BOT_TOKEN` or `API_TOKEN_TELEGRAM` must be set. The code checks for both.

## Optional Variables

### Basic Bot Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | `INFO` |
| `CHAT_ID` | Optional chat ID for notifications | None | `123456789` |
| `ENVIRONMENT` | Application environment | `development` | `production` |

### Redis Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` | `redis://user:pass@host:6379` |
| `REDIS_DB` | Redis database number | `0` | `0` |

### Performance Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MAX_CONNECTIONS` | Maximum Redis connections | `20` | `50` |
| `SESSION_TTL` | Session TTL in seconds | `3600` | `7200` |

### Monitoring & Error Tracking

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `SENTRY_DSN` | Sentry DSN for error tracking | None | `https://key@sentry.io/project` |

## Payment System Variables

### Payment Configuration

| Variable | Description | Required for Payments | Default | Example |
|----------|-------------|----------------------|---------|---------|
| `ENABLE_PAYMENT` | Enable payment requirement | No | `FALSE` | `TRUE` or `FALSE` |
| `TRIBUTE_API_KEY` | Tribute API key for authentication | ✅ Yes (if payments enabled) | None | `trib_live_xxxxxxxxxxxxx` |
| `TRIBUTE_BASE_URL` | Tribute API base URL | No | `https://api.tribute.to` | `https://api.tribute.to` |
| `TRIBUTE_PAYMENT_URL` | Tribute payment page URL for users | No | `https://tribute.to/vechnost` | `https://tribute.to/your_page` |
| `WEBHOOK_SECRET` | Secret for webhook signature verification | ✅ Yes (if payments enabled) | None | `whsec_xxxxxxxxxxxxx` |

### Database Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `DATABASE_URL` | Database connection URL | `sqlite:///./vechnost.db` | `sqlite:///./vechnost.db` |

**Note**: For production with PostgreSQL:
```
postgresql+asyncpg://user:password@host:5432/database
```

## Complete .env Template

```env
# ============================================
# REQUIRED - Telegram Bot Token
# ============================================
TELEGRAM_BOT_TOKEN=your_bot_token_here
# OR
# API_TOKEN_TELEGRAM=your_bot_token_here

# ============================================
# BASIC CONFIGURATION (Optional)
# ============================================
LOG_LEVEL=INFO
ENVIRONMENT=development
CHAT_ID=your_chat_id_here

# ============================================
# REDIS CONFIGURATION (Optional)
# ============================================
REDIS_URL=redis://localhost:6379
REDIS_DB=0
MAX_CONNECTIONS=20
SESSION_TTL=3600

# ============================================
# MONITORING (Optional)
# ============================================
SENTRY_DSN=https://your_sentry_dsn_here

# ============================================
# PAYMENT SYSTEM (Required if ENABLE_PAYMENT=TRUE)
# ============================================
ENABLE_PAYMENT=FALSE
TRIBUTE_API_KEY=your_tribute_api_key_here
TRIBUTE_BASE_URL=https://api.tribute.to
TRIBUTE_PAYMENT_URL=https://tribute.to/your_page_here
WEBHOOK_SECRET=your_webhook_secret_here

# Local development (SQLite)
DATABASE_URL=sqlite+aiosqlite:///./vechnost.db

# Production (PostgreSQL)
# DATABASE_URL=postgresql+asyncpg://postgres:password@postgres.railway.internal:5432/railway
```

## Environment-Specific Configuration

### Development Environment

```env
# Minimal setup for local development
TELEGRAM_BOT_TOKEN=your_bot_token_here
LOG_LEVEL=DEBUG
ENVIRONMENT=development
ENABLE_PAYMENT=FALSE
```

### Testing Environment

```env
# Testing with payments disabled
TELEGRAM_BOT_TOKEN=your_test_bot_token_here
LOG_LEVEL=INFO
ENVIRONMENT=testing
ENABLE_PAYMENT=FALSE
DATABASE_URL=sqlite:///./test_vechnost.db
```

### Production Environment

```env
# Full production setup with payments
TELEGRAM_BOT_TOKEN=your_production_bot_token_here
LOG_LEVEL=INFO
ENVIRONMENT=production

# Redis for production
REDIS_URL=redis://your-redis-host:6379
REDIS_DB=0
MAX_CONNECTIONS=50

# Sentry for error tracking
SENTRY_DSN=https://your_sentry_dsn_here

# Payment system enabled
ENABLE_PAYMENT=TRUE
TRIBUTE_API_KEY=trib_live_xxxxxxxxxxxxx
TRIBUTE_BASE_URL=https://api.tribute.to
TRIBUTE_PAYMENT_URL=https://tribute.to/your_page
WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres.railway.internal:5432/railway
```

## Variable Validation

The bot uses Pydantic Settings for configuration validation. The following rules apply:

### Required Field Validation
- `TELEGRAM_BOT_TOKEN` (or `API_TOKEN_TELEGRAM`) - **Must be set**, bot won't start without it

### Type Validation
- `ENABLE_PAYMENT` - Must be boolean-like (`TRUE`, `FALSE`, `true`, `false`, `1`, `0`)
- `LOG_LEVEL` - Should be valid logging level
- `REDIS_DB` - Must be integer
- `MAX_CONNECTIONS` - Must be integer
- `SESSION_TTL` - Must be integer

### URL Validation
- `REDIS_URL` - Must be valid Redis DSN
- `TRIBUTE_BASE_URL` - Must be valid URL
- `DATABASE_URL` - Must be valid database connection string

## Security Best Practices

### ⚠️ NEVER Commit Secrets to Git

```bash
# Always use .env file (already in .gitignore)
cp env.example .env
# Edit .env with your actual values
nano .env
```

### 🔒 Production Security Checklist

- [ ] Use strong, unique `WEBHOOK_SECRET`
- [ ] Store `TRIBUTE_API_KEY` securely (never in code)
- [ ] Use environment variables, not hardcoded values
- [ ] Rotate secrets regularly
- [ ] Use HTTPS for webhook endpoints
- [ ] Enable Sentry for production monitoring
- [ ] Use PostgreSQL instead of SQLite for high traffic
- [ ] Set appropriate `LOG_LEVEL` (INFO or WARNING, not DEBUG)

## Troubleshooting

### Bot Won't Start

**Error**: "TELEGRAM_BOT_TOKEN is required"
- **Solution**: Set either `TELEGRAM_BOT_TOKEN` or `API_TOKEN_TELEGRAM` in your `.env` file

### Payment Features Not Working

**Error**: "Tribute API key not configured"
- **Solution**: Set `TRIBUTE_API_KEY` when `ENABLE_PAYMENT=TRUE`

**Error**: "Webhook secret not configured"
- **Solution**: Set `WEBHOOK_SECRET` when `ENABLE_PAYMENT=TRUE`

### Database Errors

**Error**: "Could not connect to database"
- **Solution**: Check `DATABASE_URL` format
- For SQLite: `sqlite:///./vechnost.db` (relative path)
- For PostgreSQL: Include `+asyncpg` driver

### Redis Connection Issues

**Error**: "Could not connect to Redis"
- **Solution**: Verify `REDIS_URL` is correct and Redis server is running
- Bot will fallback to in-memory storage if Redis unavailable

## Getting Your Credentials

### Telegram Bot Token
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the prompts to create your bot
4. Copy the token provided

### Tribute API Key
1. Sign up at [Tribute](https://tribute.to)
2. Navigate to Developer Settings
3. Generate API key
4. Copy the key (starts with `trib_live_` or `trib_test_`)

### Webhook Secret
1. In Tribute dashboard, go to Webhooks
2. Create new webhook endpoint
3. Copy the webhook signing secret
4. Use this as `WEBHOOK_SECRET`

### Sentry DSN (Optional)
1. Sign up at [Sentry.io](https://sentry.io)
2. Create a new Python project
3. Copy the DSN from project settings

## Deployment Platform Specific

### Railway
Set environment variables in Railway dashboard:
```
Settings → Variables → Add all required variables
```

### Render
Set environment variables in Render dashboard:
```
Environment → Add Environment Variables
```

### Docker
Use `.env` file or pass via docker-compose:
```yaml
environment:
  - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
  - ENABLE_PAYMENT=${ENABLE_PAYMENT}
```

### Heroku
Use Heroku CLI or dashboard:
```bash
heroku config:set TELEGRAM_BOT_TOKEN=your_token
heroku config:set ENABLE_PAYMENT=TRUE
```

## Reference

For more details, see:
- [Main README](../README.md)
- [Payment Setup Guide](PAYMENT_SETUP_GUIDE.md)
- [Configuration Code](../vechnost_bot/config.py)

