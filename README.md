# Vechnost Telegram Bot

A production-ready Telegram bot for the Vechnost card game - an intimate conversation game designed to deepen relationships through meaningful questions and tasks.

## Features

- **Multiple Themes**: Acquaintance, For Couples, Sex, and Provocation
- **Progressive Levels**: 3 levels for most themes, with increasing intimacy
- **NSFW Protection**: 18+ confirmation required for Sex theme
- **Dual Content Types**: Questions and Tasks (Sex theme only)
- **Session Management**: Track progress and prevent duplicate cards
- **Modern UI**: Inline keyboards for intuitive navigation

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

# Run with coverage
pytest --cov=vechnost_bot
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
│   └── config.py           # Configuration
├── data/
│   └── questions.yaml      # Game content
├── tests/                  # Test suite
├── .github/workflows/      # CI/CD
├── pyproject.toml          # Dependencies & config
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

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes | - |
| `LOG_LEVEL` | Logging level | No | INFO |

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
