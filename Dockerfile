FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run database migrations on startup, then start server
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
