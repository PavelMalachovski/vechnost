#!/usr/bin/env python
"""Script to run the payment webhook server."""

import sys
import uvicorn

if __name__ == "__main__":
    # Run the webhook server
    uvicorn.run(
        "vechnost_bot.payments.web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

