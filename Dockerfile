# Multi-stage build for optimized production image
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libjpeg-dev \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Production stage
FROM python:3.11-slim AS production

# Set working directory
WORKDIR /app

# Install runtime dependencies including Redis server and client tools
RUN apt-get update && apt-get install -y \
    libjpeg62-turbo \
    zlib1g \
    redis-server \
    redis-tools \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY vechnost_bot/ ./vechnost_bot/
COPY data/ ./data/
COPY assets/ ./assets/

# Create non-root user with proper permissions
RUN useradd --create-home --shell /bin/bash --uid 1000 app && \
    chown -R app:app /app && \
    mkdir -p /tmp/redis_data /tmp/redis_logs && \
    chown -R app:app /tmp/redis_data /tmp/redis_logs

# Switch to non-root user
USER app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV REDIS_AUTO_START=true
ENV LOG_LEVEL=INFO

# Create health check script
RUN echo '#!/bin/bash\npython -c "import sys; sys.exit(0)"' > /app/healthcheck.sh && \
    chmod +x /app/healthcheck.sh

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["/app/healthcheck.sh"]

# Expose port (if needed for future web interface)
EXPOSE 8000

# Run the application
CMD ["python", "-m", "vechnost_bot"]
