# Docker Configuration Fixed ✅

## What Was Wrong

The Dockerfile I created was for the **FastAPI webhook handler**, but you were trying to run your **Telegram bot** (`vechnost_bot`).

### The Problem
- ❌ Missing `python-telegram-bot` package
- ❌ Wrong CMD (tried to run FastAPI instead of bot)
- ❌ Used wrong `requirements.txt` (FastAPI deps instead of bot deps)

## What I Fixed

### 1. **Restored Correct Dockerfile** for Telegram Bot

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Pillow
RUN apt-get update && apt-get install -y \
    gcc libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install from pyproject.toml (includes python-telegram-bot)
COPY pyproject.toml .
COPY README.md .
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

# Run the Telegram bot
CMD ["python", "-m", "vechnost_bot"]
```

### 2. **Fixed docker-compose.yml**

Now correctly configured for your Telegram bot with Redis:

```yaml
services:
  bot:
    build: .
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - REDIS_URL=redis://redis:6379
      - PAYMENT_ENABLED=${PAYMENT_ENABLED:-false}
      - TRIBUTE_API_KEY=${TRIBUTE_API_KEY}
    depends_on:
      - redis
    volumes:
      - ./assets:/app/assets:ro
      - ./data:/app/data:ro

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

### 3. **Moved FastAPI Webhook Handler**

The FastAPI webhook handler is now in a **separate directory**: `tribute-webhook/`

```
├── vechnost_bot/           # Your Telegram bot (main project)
├── Dockerfile              # For Telegram bot ✅
├── docker-compose.yml      # For Telegram bot + Redis ✅
└── tribute-webhook/        # Separate FastAPI service
    ├── app/
    ├── alembic/
    ├── requirements.txt
    ├── Dockerfile          # For webhook handler
    └── docker-compose.yml  # Can run separately
```

## Now You Can Run Your Bot

```bash
# Build and run the Telegram bot
docker-compose up --build
```

The bot will now:
- ✅ Install all dependencies from `pyproject.toml` (including `python-telegram-bot`)
- ✅ Connect to Redis for session storage
- ✅ Load assets and data from mounted volumes
- ✅ Run `python -m vechnost_bot`

## If You Want to Run the Webhook Handler

That's now separate:

```bash
cd tribute-webhook
docker-compose up --build
```

This runs on port 8001 (not conflicting with the bot).

## Summary

| Component | Location | Port | Purpose |
|-----------|----------|------|---------|
| **Telegram Bot** | Root directory | - | Main bot (fixed ✅) |
| **Redis** | Docker service | 6379 | Session storage |
| **Webhook Handler** | `tribute-webhook/` | 8001 | FastAPI for Tribute webhooks |

---

Your bot should now start correctly! 🎉

