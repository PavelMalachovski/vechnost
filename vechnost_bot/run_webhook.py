#!/usr/bin/env python3
"""Start both webhook server and Telegram bot."""
import os
import subprocess
import sys
import time

if __name__ == '__main__':
    # Get port from environment or use 8000 as default
    port = int(os.getenv('PORT', '8000'))

    print(f"[*] Starting webhook server on port {port}...")

    # Start webhook server in background
    import multiprocessing

    def run_webhook():
        """Run webhook server."""
        import uvicorn
        uvicorn.run(
            'vechnost_bot.payments.web:app',
            host='0.0.0.0',
            port=port,
            log_level='info'
        )

    def run_bot():
        """Run Telegram bot."""
        print("[*] Starting Telegram bot...")
        time.sleep(3)  # Wait for webhook server to start
        from vechnost_bot import main
        main.main()

    # Start webhook server in separate process
    webhook_process = multiprocessing.Process(target=run_webhook)
    webhook_process.start()

    # Start bot in separate process
    bot_process = multiprocessing.Process(target=run_bot)
    bot_process.start()

    print("[*] Both webhook server and bot are running!")

    # Wait for processes
    try:
        webhook_process.join()
        bot_process.join()
    except KeyboardInterrupt:
        print("\n[*] Stopping services...")
        webhook_process.terminate()
        bot_process.terminate()
        webhook_process.join()
        bot_process.join()
        print("[*] Services stopped")
        sys.exit(0)

