# Tribute Webhook Handler

A production-ready FastAPI + SQLAlchemy 2.0 + Alembic webhook handler for Tribute payment events.

## Features

- ✅ **Async FastAPI** - High-performance async API
- ✅ **SQLAlchemy 2.0** - Modern ORM with async support
- ✅ **Alembic** - Database migrations with SQLite batch mode
- ✅ **HMAC Signature Verification** - Secure webhook validation
- ✅ **Idempotency** - Duplicate webhook detection via SHA256 hashing
- ✅ **SQLite First** - Easy local development, clean path to Postgres

## Quick Start

### 1. Install Dependencies

   ```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

   ```bash
cp .env.example .env
# Edit .env and add your TRIBUTE_API_KEY
   ```

### 3. Initialize Database

   ```bash
# Create initial migration
alembic revision --autogenerate -m "initial tables"

# Apply migration
alembic upgrade head
```

### 4. Run Development Server

   ```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at:
- Main API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Database Models

### Users
Stores Telegram user information:
- `telegram_user_id` (BIGINT, unique, indexed)
- `username`, `first_name`, `last_name`
- `created_at`

### Products
Available products/plans:
- `type` (digital, subscription)
- `name`, `amount`, `currency`
- `stars_amount` (Telegram Stars)
- `t_link`, `web_link`

### Payments
All payment transactions:
- `provider` (tribute)
- `event_name` (new_digital_product, new_subscription, cancelled_subscription)
- `user_id` (FK), `telegram_user_id`
- `product_id` (FK, optional)
- `amount`, `currency`, `expires_at`
- `raw_body` (JSON), `signature`
- `body_sha256` (unique, for idempotency)

### Subscriptions
User subscription status:
- `user_id` (FK), `subscription_id`
- `period`, `status`, `expires_at`
- `last_event_at`
- Unique constraint: `(user_id, subscription_id)`

### Webhook Events
Audit log of webhook deliveries:
- `name`, `sent_at`, `created_at`
- `body_sha256` (unique)
- `status_code`, `processed_at`, `error`

## Webhook Events

### Supported Events

1. **`new_digital_product`** - One-time digital product purchase
2. **`new_subscription`** - New recurring subscription created
3. **`cancelled_subscription`** - Subscription cancelled

### Webhook Endpoint

```
POST /webhook/tribute
```

**Headers:**
- `trbt-signature`: HMAC-SHA256 signature (verified against TRIBUTE_API_KEY)

**Response:**
- `200 OK` with `{"ok": true}` on success
- `200 OK` with `{"ok": true, "dup": true}` if duplicate (idempotency)
- `401 Unauthorized` if signature invalid
- `400 Bad Request` if malformed payload
- `500 Internal Server Error` if processing fails

### Security

1. **Signature Verification**:
   ```python
   HMAC-SHA256(raw_body, TRIBUTE_API_KEY) == trbt-signature header
   ```

2. **Idempotency**:
   ```python
   SHA256(raw_body) → stored in payments.body_sha256 (unique)
   ```
   Duplicate webhooks return immediately with `{"ok": true, "dup": true}`

## Example Webhook Request

```bash
# Generate signature (example - use your actual API key)
API_KEY="your_tribute_api_key"
BODY='{"event_name":"new_digital_product","telegram_user_id":123456789,"username":"testuser","amount":299,"currency":"RUB","product_id":1}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

# Send webhook
curl -X POST http://localhost:8000/webhook/tribute \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"
```

**Expected Response:**
```json
{"ok": true}
```

## Switching to PostgreSQL

### 1. Install PostgreSQL Driver

```bash
pip install psycopg2-binary asyncpg
```

### 2. Update Environment

Edit `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/tribute_db
```

### 3. Migrate

The same migrations work for both SQLite and Postgres thanks to `render_as_batch=True`:

```bash
# Apply existing migrations to Postgres
alembic upgrade head
```

### 4. Optional: Database-Specific Optimizations

For Postgres, you can create additional migrations with:
- Full-text search indexes
- JSONB operators for `raw_body`
- Partitioning for large tables
- Advanced constraints

## Development

### Create New Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "description"

# Review generated migration in alembic/versions/
# Edit if needed (especially for complex operations)

# Apply migration
alembic upgrade head
```

### Rollback Migration

```bash
# Rollback one version
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Rollback all
alembic downgrade base
```

### Check Migration Status

```bash
alembic current
alembic history
```

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app + webhook handlers
│   ├── config.py         # Settings from environment
│   ├── database.py       # Async engine + session
│   ├── models.py         # SQLAlchemy 2.0 models
│   ├── schemas.py        # Pydantic schemas
│   └── crud.py           # Database operations
├── alembic/
│   ├── env.py            # Alembic config (render_as_batch=True)
│   ├── script.py.mako    # Migration template
│   └── versions/         # Migration files
├── alembic.ini           # Alembic settings
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
└── README.md             # This file
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite+aiosqlite:///./tribute.db` |
| `TRIBUTE_API_KEY` | Tribute API key for signature verification | (required) |
| `DEBUG` | Enable debug mode | `false` |

## Alembic SQLite Configuration

The `env.py` is configured with `render_as_batch=True` for SQLite compatibility:

```python
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    render_as_batch=True,  # Required for SQLite ALTER operations
)
```

This enables batch mode for all migrations, allowing complex operations like:
- Adding/dropping columns with constraints
- Renaming columns
- Adding/modifying foreign keys
- Adding/modifying unique constraints

## Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test webhook (see example above)

# Check database
sqlite3 tribute.db "SELECT * FROM users;"
sqlite3 tribute.db "SELECT * FROM payments;"
```

## Production Deployment

1. **Set strong `TRIBUTE_API_KEY`**
2. **Use Postgres** for production
3. **Enable HTTPS** (signature verification over HTTP is vulnerable)
4. **Set `DEBUG=false`**
5. **Use process manager** (systemd, supervisor, or Docker)
6. **Configure logging**
7. **Set up monitoring** (check `/health` endpoint)
8. **Database backups**

### Example Production Start

```bash
# Using Gunicorn + Uvicorn workers
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

## License

MIT

## Support

For issues with Tribute integration, contact Tribute support.
For issues with this code, open an issue on your repository.
