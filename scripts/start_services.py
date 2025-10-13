#!/usr/bin/env python3
"""Start both webhook server and bot."""
import os
import subprocess
import sys
import time

def main():
    """Start services."""
    port = os.getenv('PORT', '8000')

    print(f"[*] Starting webhook server on port {port}...")

    # Start webhook server in background
    webhook_process = subprocess.Popen([
        'python', '-m', 'uvicorn',
        'vechnost_bot.payments.web:app',
        '--host', '0.0.0.0',
        '--port', port
    ])

    print("[*] Webhook server started")
    print("[*] Waiting 3 seconds...")
    time.sleep(3)

    print("[*] Starting Telegram bot...")

    # Start bot in foreground
    bot_process = subprocess.Popen([
        'python', '-m', 'vechnost_bot'
    ])

    print("[*] Both services started!")

    # Wait for processes
    try:
        bot_process.wait()
    except KeyboardInterrupt:
        print("\n[*] Stopping services...")
        webhook_process.terminate()
        bot_process.terminate()
        webhook_process.wait()
        bot_process.wait()
        print("[*] Services stopped")
        sys.exit(0)


if __name__ == '__main__':
    main()

