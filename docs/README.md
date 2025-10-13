# Vechnost Telegram Bot

A production-ready Telegram bot for the Vechnost card game - an intimate conversation game designed to deepen relationships through meaningful questions and tasks.

## Features

- **Multiple Themes**: Acquaintance, For Couples, Sex, and Provocation
- **Progressive Levels**: 3 levels for most themes, with increasing intimacy
- **NSFW Protection**: 18+ confirmation required for Sex theme
- **Dual Content Types**: Questions and Tasks (Sex theme only)
- **Session Management**: Track progress and prevent duplicate cards
- **Modern UI**: Inline keyboard for intuitive navigation
- **Payment Integration**: Optional Tribute payment system with subscription support
- **Multi-language Support**: English, Russian, and Czech translations

## 📁 Структура проекта

```
vechnost/
├── vechnost_bot/          # Основной код бота
├── scripts/               # Вспомогательные Python скрипты
├── sql/                   # SQL скрипты для БД
├── docs/                  # Документация
├── assets/                # Изображения и ресурсы
├── data/                  # Переводы и вопросы
└── tests/                 # Тесты
```

## Quick Start

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd vechnost
   python -m pip install --upgrade pip
   pip install .[dev]
   ```

2. **Set environment variables**:
   ```bash
   export TELEGRAM_BOT_TOKEN=your_bot_token_here
   export LOG_LEVEL=INFO
   ```

3. **Run the bot**:
   ```bash
   python -m vechnost_bot
   ```

### Docker

1. **Build and run**:
   ```bash
   docker build -t vechnost-bot .
   docker run --rm -e TELEGRAM_BOT_TOKEN=your_token vechnost-bot
   ```

2. **Using docker-compose**:
   ```bash
   cp env.example .env
   # Edit .env with your bot token
   docker-compose up
   ```

## Development

### Running Tests

```bash
# Run all tests
pytest -q

# Run specific test file
pytest tests/test_models.py
pytest tests/test_payments.py

# Run with coverage
pytest --cov=vechnost_bot

# Run payment tests only
pytest tests/test_payments.py -v
```

### Code Quality

```bash
# Lint with ruff
ruff check .

# Type checking with mypy
mypy vechnost_bot

# Format code
ruff format .
```

### Project Structure

```
vechnost-bot/
├── vechnost_bot/           # Main bot package
│   ├── __init__.py
│   ├── main.py             # Entry point
│   ├── bot.py              # Bot application setup
│   ├── handlers.py         # Message handlers
│   ├── keyboards.py        # Inline keyboards
│   ├── logic.py            # Game logic
│   ├── models.py           # Data models
│   ├── storage.py          # Session storage
│   ├── config.py           # Configuration
│   ├── i18n.py             # Internationalization
│   └── payments/           # Payment integration
│       ├── __init__.py
│       ├── models.py       # Database models
│       ├── database.py     # Database connection
│       ├── repositories.py # Data access layer
│       ├── services.py     # Business logic
│       ├── tribute_client.py # Tribute API client
│       ├── signature.py    # Webhook verification
│       ├── middleware.py   # Payment middleware
│       ├── handlers.py     # Payment handlers
│       └── web.py          # FastAPI webhook server
├── data/
│   ├── questions*.yaml     # Game content
│   └── translations*.yaml  # UI translations
├── alembic/                # Database migrations
│   ├── versions/
│   └── env.py
├── tests/                  # Test suite
│   └── test_payments.py    # Payment tests
├── .github/workflows/      # CI/CD
├── pyproject.toml          # Dependencies & config
├── alembic.ini             # Alembic configuration
├── run_webhook_server.py   # Webhook server launcher
├── Dockerfile
├── docker-compose.yml
└── render.yaml            # Render deployment
```

## Deployment

### Render.com (Recommended)

1. **Connect your repository** to Render
2. **Create a new Worker service** using `render.yaml`
3. **Set environment variables** in Render dashboard:
   - `TELEGRAM_BOT_TOKEN`: Your bot token from @BotFather
   - `LOG_LEVEL`: Optional, defaults to INFO
4. **Deploy** - Render will automatically build and deploy

### Other Platforms

The bot can be deployed to any platform that supports Python 3.11+:

- **Heroku**: Use the included `Dockerfile`
- **Railway**: Deploy with `python -m vechnost_bot`
- **VPS**: Use docker-compose or direct Python installation

## Game Content

The bot uses content from `data/questions.yaml` with the following structure:

- **Acquaintance**: 3 levels of getting-to-know-you questions
- **For Couples**: 3 levels of relationship-deepening questions
- **Sex**: 1 level with both questions and tasks (18+)
- **Provocation**: 1 level of challenging scenarios

## Bot Commands

- `/start` - Start a new game
- `/help` - Show help information
- `/reset` - Reset current game

## Payment Integration

The bot includes an optional payment system powered by Tribute. When enabled, users must have an active subscription or payment to access bot features.

### Features

- **Flexible Configuration**: Enable/disable payments via environment variable
- **Tribute Integration**: Support for one-time payments and subscriptions
- **Webhook Processing**: Automatic handling of payment events with idempotency
- **SQLite Database**: Track users, products, payments, and subscriptions
- **Secure Webhooks**: HMAC-SHA256 signature verification
- **Admin API**: Manual product synchronization endpoint

### Setting Up Payments

1. **Install dependencies**:
   ```bash
   pip install -e .  # Includes SQLAlchemy, Alembic, FastAPI, and uvicorn
   ```

2. **Configure environment variables**:
   ```bash
   # In your .env file
   ENABLE_PAYMENT=TRUE
   TRIBUTE_API_KEY=your_tribute_api_key_here
   TRIBUTE_BASE_URL=https://api.tribute.to
   WEBHOOK_SECRET=your_webhook_secret_here
   DATABASE_URL=sqlite:///./vechnost.db
   ```

3. **Initialize database**:
   ```bash
   alembic upgrade head
   ```

4. **Start the webhook server**:
   ```bash
   python run_webhook_server.py
   # Or use uvicorn directly:
   uvicorn vechnost_bot.payments.web:app --host 0.0.0.0 --port 8000
   ```

5. **Expose webhook to internet** (for local development):
   ```bash
   # Using ngrok
   ngrok http 8000
   # Configure the public URL in Tribute dashboard
   ```

6. **Sync products from Tribute**:
   ```bash
   curl -X POST http://localhost:8000/admin/sync-products \
     -H "Authorization: Bearer YOUR_TRIBUTE_API_KEY"
   ```

### Webhook Endpoints

- **POST /webhooks/tribute** - Receive payment/subscription events from Tribute
- **GET /health** - Health check endpoint
- **POST /admin/sync-products** - Manually sync products (requires authentication)
- **GET /** - API information

### Database Schema

The payment system uses the following tables:

- **users**: Telegram user information
- **products**: Available products from Tribute
- **payments**: Payment transactions and events
- **subscriptions**: Active subscriptions
- **webhook_events**: Webhook delivery log

### Disabling Payments (Testing Mode)

To disable payment requirements:

```bash
ENABLE_PAYMENT=FALSE
```

When disabled, all users have full access to the bot, but webhooks continue to be processed and logged.

### Alembic Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes | - |
| `LOG_LEVEL` | Logging level | No | INFO |
| `ENABLE_PAYMENT` | Enable payment requirement | No | FALSE |
| `TRIBUTE_API_KEY` | Tribute API key | If payments enabled | - |
| `TRIBUTE_BASE_URL` | Tribute API base URL | No | https://api.tribute.to |
| `WEBHOOK_SECRET` | Webhook signature secret | If payments enabled | - |
| `DATABASE_URL` | Database connection URL | No | sqlite:///./vechnost.db |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions, please open a GitHub issue or contact the development team.
