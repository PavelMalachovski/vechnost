#!/usr/bin/env python3
"""Start webhook server using Railway's PORT variable."""
import os
import sys

# Get port from environment or use 8000 as default
port = os.getenv('PORT', '8000')

print(f"[*] Starting webhook server on port {port}...")

# Import and run uvicorn
import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        'vechnost_bot.payments.web:app',
        host='0.0.0.0',
        port=int(port),
        log_level='info'
    )

