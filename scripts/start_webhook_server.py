"""Start webhook server with proper environment configuration."""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ensure DATABASE_URL is set
database_url = os.getenv('DATABASE_URL')
if not database_url:
    print("[X] ERROR: DATABASE_URL not set!")
    print("    Set it in your .env file or environment")
    sys.exit(1)

print("\n" + "="*60)
print("WEBHOOK SERVER CONFIGURATION")
print("="*60)
print(f"Database: {database_url[:50]}...")
print(f"Payment Enabled: {os.getenv('ENABLE_PAYMENT', 'False')}")
print(f"Tribute API Key: {'SET' if os.getenv('TRIBUTE_API_KEY') else 'NOT SET'}")
print(f"Webhook Secret: {'SET' if os.getenv('WEBHOOK_SECRET') else 'NOT SET'}")
print("="*60 + "\n")

# Import and run the server
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "vechnost_bot.payments.web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

