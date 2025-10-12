# Project Summary: Tribute Webhook Handler

## 📦 Complete FastAPI + SQLAlchemy 2 + Alembic Project

A production-ready webhook handler for Tribute payment events with:
- ✅ **Async FastAPI** with proper signature verification
- ✅ **SQLAlchemy 2.0** with async support
- ✅ **Alembic** migrations configured for SQLite (batch mode)
- ✅ **Idempotency** via SHA256 body hashing
- ✅ **Clean architecture** - easy to extend and test

---

## 📁 Project Structure

```
├── app/
│   ├── __init__.py           # Package marker
│   ├── main.py               # FastAPI app + webhook handlers
│   ├── config.py             # Settings from .env
│   ├── database.py           # Async engine + sessions
│   ├── models.py             # SQLAlchemy 2.0 models
│   ├── schemas.py            # Pydantic request/response
│   └── crud.py               # Database operations
│
├── alembic/
│   ├── env.py                # Migration environment (render_as_batch=True)
│   ├── script.py.mako        # Migration template
│   └── versions/             # Migration files go here
│
├── alembic.ini               # Alembic configuration
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (you edit this)
├── .gitignore                # Git exclusions
│
├── README.md                 # Full documentation
├── QUICKSTART.md             # 2-minute setup guide
├── MIGRATION_GUIDE.md        # Database migration details
├── docker-compose.yml        # Docker setup (optional)
├── Dockerfile                # Docker image (optional)
└── test_webhook.sh           # Webhook testing script
```

---

## 🚀 Quick Start (3 Commands)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Initialize database
alembic revision --autogenerate -m "initial tables"
alembic upgrade head

# 3. Run
uvicorn app.main:app --reload
```

**Done!** API running at http://localhost:8000

---

## 🔐 Security Features

### 1. **HMAC-SHA256 Signature Verification**
```python
def verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(TRIBUTE_API_KEY.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

- Verifies `trbt-signature` header
- Uses constant-time comparison
- Returns 401 on invalid signature

### 2. **Idempotency Protection**
```python
body_sha256 = hashlib.sha256(raw_body).hexdigest()
# Stored in payments.body_sha256 (unique constraint)
```

- Detects duplicate webhooks
- Returns `{"ok": true, "dup": true}` for duplicates
- Prevents double-processing

---

## 🗄️ Database Models

### **Users**
- Telegram user data (telegram_user_id unique)
- Auto-upserted on every webhook

### **Products**
- Available products/plans
- Links for Telegram & web payments

### **Payments**
- All payment transactions
- Stores raw webhook body (JSON)
- SHA256 hash for idempotency

### **Subscriptions**
- User subscription status
- Period, status, expires_at
- Unique per (user_id, subscription_id)

### **WebhookEvents**
- Audit log of all webhooks
- Tracks processing status & errors

---

## 📡 Webhook API

### **Endpoint**
```
POST /webhook/tribute
Content-Type: application/json
trbt-signature: <HMAC-SHA256>
```

### **Events Handled**

1. **`new_digital_product`** - One-time purchase
   ```json
   {
     "event_name": "new_digital_product",
     "telegram_user_id": 123456789,
     "username": "testuser",
     "amount": 299,
     "currency": "RUB",
     "product_id": 1
   }
   ```

2. **`new_subscription`** - Recurring subscription
   ```json
   {
     "event_name": "new_subscription",
     "telegram_user_id": 123456789,
     "subscription_id": 456,
     "period": "monthly",
     "amount": 299,
     "expires_at": "2025-02-12T00:00:00Z"
   }
   ```

3. **`cancelled_subscription`** - Cancellation
   ```json
   {
     "event_name": "cancelled_subscription",
     "telegram_user_id": 123456789,
     "subscription_id": 456
   }
   ```

### **Responses**

| Code | Body | Meaning |
|------|------|---------|
| 200 | `{"ok": true}` | Success |
| 200 | `{"ok": true, "dup": true}` | Duplicate (idempotent) |
| 401 | `{"detail": "Invalid signature"}` | Bad signature |
| 400 | `{"detail": "..."}` | Malformed request |
| 500 | `{"detail": "..."}` | Server error |

---

## 🧪 Testing

### **Test Script**
```bash
./test_webhook.sh
```

Tests:
- ✅ new_digital_product event
- ✅ new_subscription event
- ✅ cancelled_subscription event
- ✅ Duplicate detection (idempotency)
- ✅ Invalid signature rejection (401)

### **Manual Test**
```bash
API_KEY="your_key"
BODY='{"event_name":"new_digital_product","telegram_user_id":123,"amount":100}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

curl -X POST http://localhost:8000/webhook/tribute \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIG" \
  -d "$BODY"
```

---

## 🐘 Switching to PostgreSQL

The SAME migrations work for both databases!

```bash
# 1. Install driver
pip install psycopg2-binary asyncpg

# 2. Update .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/tribute_db

# 3. Run migrations (identical command!)
alembic upgrade head
```

That's it! The `render_as_batch=True` in `alembic/env.py` makes it work.

---

## 🔧 Key Configuration

### **Alembic SQLite Batch Mode**
```python
# alembic/env.py
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    render_as_batch=True,  # ← Makes migrations work on SQLite
)
```

This enables:
- Adding columns with constraints
- Renaming columns
- Adding foreign keys
- Modifying unique constraints

### **Environment Variables**
```bash
DATABASE_URL=sqlite+aiosqlite:///./tribute.db  # SQLite (default)
# DATABASE_URL=postgresql+asyncpg://...        # Postgres
TRIBUTE_API_KEY=your_key_here                  # Required!
DEBUG=false
```

---

## 📦 Dependencies

### **Core**
- `fastapi` - Async web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation
- `sqlalchemy[asyncio]` - Async ORM
- `aiosqlite` - SQLite async driver
- `alembic` - Database migrations

### **For Postgres** (install later)
- `psycopg2-binary` - Postgres sync driver
- `asyncpg` - Postgres async driver

---

## 🎯 What Makes This Production-Ready

1. **✅ Async Everything** - FastAPI + SQLAlchemy async
2. **✅ Proper Security** - HMAC signature verification
3. **✅ Idempotency** - SHA256 deduplication
4. **✅ Error Handling** - Graceful failures, error logging
5. **✅ Database Migrations** - Alembic with batch mode
6. **✅ Type Safety** - Pydantic schemas, SQLAlchemy 2.0 typed models
7. **✅ Clean Architecture** - Separated concerns (CRUD, models, schemas)
8. **✅ Docker Ready** - Dockerfile + docker-compose.yml
9. **✅ Testing Tools** - test_webhook.sh script
10. **✅ Documentation** - README, QUICKSTART, MIGRATION_GUIDE

---

## 📖 Documentation Files

- **README.md** - Complete guide (setup, API, deployment)
- **QUICKSTART.md** - 2-minute start (install → run → test)
- **MIGRATION_GUIDE.md** - Database migrations & Postgres switch
- **PROJECT_SUMMARY.md** - This file (overview)

---

## 🚢 Deployment Options

### **Option 1: Docker**
```bash
docker-compose up -d
```

### **Option 2: Systemd**
```bash
# Create systemd service
sudo nano /etc/systemd/system/tribute-webhook.service

[Unit]
Description=Tribute Webhook Handler
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/tribute-webhook
Environment="PATH=/var/www/tribute-webhook/venv/bin"
ExecStart=/var/www/tribute-webhook/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### **Option 3: Gunicorn**
```bash
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

---

## 🐛 Troubleshooting

### **"Table already exists"**
```bash
alembic stamp head  # Mark current DB state
```

### **"Invalid signature"**
- Check `TRIBUTE_API_KEY` is correct
- Verify raw body is used (not parsed JSON)
- Check signature is hex lowercase

### **"Cannot add NOT NULL column" (SQLite)**
Shouldn't happen with `render_as_batch=True`, but if it does:
```python
# Make column nullable first
batch_op.add_column(sa.Column('field', sa.String(), nullable=True))
# Then add data migration, then make NOT NULL in another migration
```

---

## ✨ Next Steps

1. **Add your Tribute API key** to `.env`
2. **Test webhooks** with `test_webhook.sh`
3. **Deploy** to your server
4. **Configure Tribute** to send webhooks to your endpoint
5. **Monitor** via `/health` endpoint
6. **Switch to Postgres** when ready for production

---

## 📞 Support

- Tribute API issues → Contact Tribute support
- Code issues → Check README.md and MIGRATION_GUIDE.md
- Questions → Review inline code comments

---

## 🎉 You're Ready!

This is a complete, production-ready webhook handler. Everything is configured and tested. Just add your API key and deploy!

**Last updated:** 2025-01-12

