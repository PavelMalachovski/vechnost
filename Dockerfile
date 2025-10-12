FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Pillow and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY README.md .

# Install the bot package and dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

# Run the bot
CMD ["python", "-m", "vechnost_bot"]
