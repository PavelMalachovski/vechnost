# Quick Start Guide

## 1. Install & Setup (2 minutes)

```bash
# Install dependencies
pip install -r requirements.txt

# Configure (add your Tribute API key)
nano .env

# Initialize database
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

## 2. Run Server

```bash
uvicorn app.main:app --reload
```

## 3. Test Webhook

```bash
# Set your API key
export API_KEY="your_tribute_api_key"

# Test payload
BODY='{"event_name":"new_digital_product","telegram_user_id":123456789,"username":"testuser","amount":299,"currency":"RUB","product_id":1}'

# Generate signature
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

# Send request
curl -X POST http://localhost:8000/webhook/tribute \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"

# Expected: {"ok":true}
```

## 4. Switch to Postgres Later

```bash
# Install driver
pip install psycopg2-binary asyncpg

# Update .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/tribute_db

# Run migrations (same command!)
alembic upgrade head
```

Done! Your webhook handler is running.

