# Tribute Webhook Handler (Separate Service)

This is a standalone FastAPI webhook handler for Tribute payment events. It's separate from the main Telegram bot.

## Quick Start

```bash
cd tribute-webhook

# Install dependencies
pip install -r requirements.txt

# Configure
cp ../.env.example .env
# Edit .env and add TRIBUTE_API_KEY

# Initialize database
alembic revision --autogenerate -m "initial tables"
alembic upgrade head

# Run
uvicorn app.main:app --reload --port 8001
```

## Usage

This webhook handler receives payment events from Tribute and stores them in a SQLite database (or PostgreSQL).

- Endpoint: `POST /webhook/tribute`
- Signature: `trbt-signature` header with HMAC-SHA256
- Idempotency: SHA256 body hash prevents duplicates

See documentation in this directory for full details.

