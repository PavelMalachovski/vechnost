# Tribute Payment Integration Setup Guide

This guide walks you through setting up the Tribute payment integration for the Vechnost Telegram bot.

## Overview

The payment system consists of:
- **SQLite Database**: Stores users, products, payments, subscriptions, and webhook events
- **Alembic Migrations**: Database schema management
- **FastAPI Webhook Server**: Receives payment events from Tribute
- **Payment Middleware**: Controls bot access based on payment status
- **Tribute API Client**: Syncs products and fetches subscription data

## Step-by-Step Setup

### 1. Prerequisites

- Python 3.11+
- Tribute account with API access
- Telegram bot token
- ngrok (for local development) or public server for webhooks

### 2. Install Dependencies

```bash
# Clone repository
git clone https://github.com/PavelMalachovski/vechnost
cd vechnost

# Install with payment dependencies
pip install -e .
```

This installs:
- `sqlalchemy>=2.0.0` - ORM for database
- `alembic>=1.13.0` - Database migrations
- `fastapi>=0.115.0` - Webhook web server
- `uvicorn>=0.30.0` - ASGI server
- `httpx>=0.27.0` - HTTP client for Tribute API

### 3. Configure Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp env.example .env
```

Edit `.env`:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Payment Configuration
ENABLE_PAYMENT=TRUE
TRIBUTE_API_KEY=your_tribute_api_key_here
TRIBUTE_BASE_URL=https://api.tribute.to
WEBHOOK_SECRET=your_webhook_secret_here

# Database
DATABASE_URL=sqlite:///./vechnost.db

# Optional
LOG_LEVEL=INFO
```

**Important**: Never commit `.env` to version control!

### 4. Initialize Database

Create database tables using Alembic:

```bash
# Apply all migrations
alembic upgrade head

# Verify migration was applied
alembic current
```

This creates the following tables:
- `users` - Telegram user information
- `products` - Tribute products
- `payments` - Payment transactions
- `subscriptions` - Active subscriptions
- `webhook_events` - Webhook delivery log

### 5. Sync Products from Tribute

Before users can purchase, sync available products from Tribute:

```bash
# Using the sync script
python sync_products.py

# Or via admin API (requires webhook server running)
curl -X POST http://localhost:8000/admin/sync-products \
  -H "Authorization: Bearer YOUR_TRIBUTE_API_KEY"
```

### 6. Start the Webhook Server

The webhook server must be running to receive payment events from Tribute:

```bash
# Using the run script
python run_webhook_server.py

# Or directly with uvicorn
uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port 8000 --reload
```

The server provides these endpoints:
- `GET /health` - Health check
- `POST /webhooks/tribute` - Tribute webhook receiver
- `POST /admin/sync-products` - Manual product sync (authenticated)
- `GET /` - API information

### 7. Expose Webhook (Local Development)

For local development, use ngrok to expose your webhook:

```bash
# Install ngrok: https://ngrok.com/
ngrok http 8000

# You'll get a public URL like: https://abc123.ngrok.io
```

Configure this URL in Tribute dashboard:
```
Webhook URL: https://abc123.ngrok.io/webhooks/tribute
```

### 8. Configure Tribute Dashboard

In your Tribute dashboard:

1. **Add Webhook URL**:
   - URL: `https://your-domain.com/webhooks/tribute`
   - Secret: Same as `WEBHOOK_SECRET` in `.env`

2. **Configure Products**:
   - Add products with Telegram links (`t_link`) or web links (`web_link`)
   - Set product metadata to include `telegram_user_id` for user identification

3. **Test Webhook**:
   - Use Tribute's webhook testing feature
   - Check webhook server logs for delivery

### 9. Start the Telegram Bot

Start the bot with payment middleware enabled:

```bash
python -m vechnost_bot
```

The bot will now:
- Check user payment status before allowing access
- Show payment required message to non-paying users
- Register users in database on first interaction
- Allow "check payment status" callback

### 10. Testing

#### Disable Payments (Testing Mode)

```env
ENABLE_PAYMENT=FALSE
```

With payments disabled:
- All users have access
- Webhooks still processed
- Database still updated
- Perfect for development/testing

#### Test Payment Flow

1. User starts bot without payment → sees payment required message
2. User clicks product link → redirected to Tribute
3. User completes payment → Tribute sends webhook
4. Webhook server processes event → updates database
5. User checks status → granted access

### 11. Running Tests

```bash
# Run all payment tests
pytest tests/test_payments.py -v

# Run with coverage
pytest tests/test_payments.py --cov=vechnost_bot.payments

# Run specific test
pytest tests/test_payments.py::test_user_has_access_with_subscription
```

## Webhook Event Processing

### Flow

```
Tribute → Webhook POST → FastAPI Server → Signature Verification →
Database Update → User Access Check
```

### Event Types

The system handles these Tribute events:

- `payment.succeeded` - One-time payment completed
- `payment.failed` - Payment failed
- `subscription.created` - New subscription
- `subscription.renewed` - Subscription renewed
- `subscription.canceled` - Subscription canceled
- `subscription.expired` - Subscription expired

### Idempotency

Webhooks are idempotent using SHA-256 hash of request body:
- Same webhook delivered multiple times → processed once
- Prevents duplicate charges/credits
- Logged in `webhook_events` table

## Database Migrations

### Creating Migrations

When you modify database models:

```bash
# Generate migration automatically
alembic revision --autogenerate -m "Add new field to payments"

# Review generated migration in alembic/versions/

# Apply migration
alembic upgrade head
```

### Rolling Back

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

# Rollback all
alembic downgrade base
```

### Migration History

```bash
# View current version
alembic current

# View all versions
alembic history

# View specific migration
alembic show <revision_id>
```

## Production Deployment

### Railway/Render

1. **Set environment variables** in platform dashboard
2. **Add web service** for webhook server:
   ```
   Start Command: uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port $PORT
   ```
3. **Add worker service** for Telegram bot:
   ```
   Start Command: python -m vechnost_bot
   ```
4. **Run migrations** as part of deployment or manually

### Docker

Update `docker-compose.yml`:

```yaml
services:
  bot:
    build: .
    environment:
      - ENABLE_PAYMENT=TRUE
      - TRIBUTE_API_KEY=${TRIBUTE_API_KEY}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
    command: python -m vechnost_bot

  webhook:
    build: .
    environment:
      - ENABLE_PAYMENT=TRUE
      - TRIBUTE_API_KEY=${TRIBUTE_API_KEY}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
    command: uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
```

### Security Considerations

1. **Never commit secrets**: Use environment variables
2. **Validate signatures**: Always verify webhook signatures
3. **Use HTTPS**: In production, serve webhooks over HTTPS
4. **Rate limiting**: Consider adding rate limiting to webhook endpoint
5. **Monitor logs**: Check webhook and payment logs regularly
6. **Backup database**: Regular backups of SQLite database

## Troubleshooting

### Webhook not received

1. Check ngrok/public URL is accessible
2. Verify webhook URL in Tribute dashboard
3. Check webhook server logs
4. Test with Tribute's webhook testing tool

### Invalid signature error

1. Verify `WEBHOOK_SECRET` matches Tribute configuration
2. Check signature header name (`X-Tribute-Signature`)
3. Review signature verification algorithm

### User denied access despite payment

1. Check database: `SELECT * FROM subscriptions WHERE user_id = X`
2. Verify subscription status and `expires_at`
3. Check webhook was processed: `SELECT * FROM webhook_events`
4. Review logs for errors

### Database errors

1. Ensure migrations are applied: `alembic current`
2. Check file permissions on SQLite database file
3. Review migration files for errors
4. Try recreating database: `alembic downgrade base && alembic upgrade head`

## Advanced Configuration

### Custom Product Display

Modify `vechnost_bot/payments/middleware.py`:

```python
async def get_payment_keyboard(language: str = "en") -> InlineKeyboardMarkup:
    # Customize keyboard layout and button text
    pass
```

### Custom Access Logic

Modify `vechnost_bot/payments/services.py`:

```python
async def user_has_access(telegram_user_id: int) -> bool:
    # Add custom access logic (e.g., trial periods, promo codes)
    pass
```

### Webhook Event Handlers

Extend `vechnost_bot/payments/services.py`:

```python
async def apply_webhook_event(...):
    # Add custom event handling logic
    if event_name == "custom.event":
        # Handle custom event
        pass
```

## Support

For issues with:
- **Bot functionality**: Open issue on GitHub
- **Payment integration**: Review this guide and logs
- **Tribute API**: Contact Tribute support

## Example Webhook Payload

```json
{
  "event_name": "subscription.renewed",
  "subscription_id": 1001,
  "telegram_user_id": 123456789,
  "amount": 999,
  "currency": "USD",
  "period": "month",
  "expires_at": "2025-11-12T00:00:00Z",
  "username": "testuser",
  "first_name": "Test",
  "last_name": "User"
}
```

## Additional Resources

- [Tribute API Documentation](https://docs.tribute.to)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/)

