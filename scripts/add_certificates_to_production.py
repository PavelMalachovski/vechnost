#!/usr/bin/env python3
"""Script to add existing certificates to production database."""

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Certificate codes from generated QR codes
CERTIFICATES = [
    "VECH-7AP3-XSE2455D",
    "VECH-ZHYK-VRE75YAG",
    "VECH-LHNV-UTDYKQ9T",
    "VECH-A9PC-9ABWGGKS",
    "VECH-834T-RXRCPJCX",
]


def add_certificates_sync(database_url: str) -> None:
    """
    Add certificates to database synchronously.

    Args:
        database_url: Database connection URL
    """
    print(f"🔗 Connecting to database...")
    print(f"   URL: {database_url[:20]}...")

    # Create engine
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)

    print(f"\n{'='*60}")
    print(f"Adding {len(CERTIFICATES)} certificates to database...")
    print(f"{'='*60}\n")

    with Session() as session:
        for i, code in enumerate(CERTIFICATES, 1):
            # Check if certificate already exists
            result = session.execute(
                text("SELECT id, is_used FROM certificates WHERE code = :code"),
                {"code": code}
            )
            existing = result.fetchone()

            if existing:
                status = "❌ Used" if existing[1] else "✅ Available"
                print(f"   {i}. {code}: Already exists ({status})")
            else:
                # Insert certificate
                session.execute(
                    text("""
                        INSERT INTO certificates (code, is_used, created_at)
                        VALUES (:code, FALSE, CURRENT_TIMESTAMP)
                    """),
                    {"code": code}
                )
                print(f"   {i}. {code}: ✅ Added")

        # Commit all changes
        session.commit()

    print(f"\n{'='*60}")
    print(f"✅ Successfully processed {len(CERTIFICATES)} certificates!")
    print(f"{'='*60}\n")

    # Verify
    with Session() as session:
        result = session.execute(
            text("SELECT COUNT(*) FROM certificates WHERE code IN :codes"),
            {"codes": tuple(CERTIFICATES)}
        )
        count = result.scalar()
        print(f"✅ Verified: {count}/{len(CERTIFICATES)} certificates in database\n")


def main():
    """Main function."""
    # Get database URL from environment or command line
    database_url = os.getenv("DATABASE_URL")

    if len(sys.argv) > 1:
        database_url = sys.argv[1]

    if not database_url:
        print("❌ Error: DATABASE_URL not found!")
        print("\nUsage:")
        print("  1. Set environment variable:")
        print("     export DATABASE_URL='postgresql://...'")
        print("     python scripts/add_certificates_to_production.py")
        print("\n  2. Or pass as argument:")
        print("     python scripts/add_certificates_to_production.py 'postgresql://...'")
        sys.exit(1)

    # Convert postgres:// to postgresql:// if needed (Railway compatibility)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    print("🎫 Certificate Addition Script")
    print("=" * 60)
    print("\n📋 Certificates to add:")
    for i, code in enumerate(CERTIFICATES, 1):
        print(f"   {i}. {code}")
    print()

    try:
        add_certificates_sync(database_url)
        print("✅ All done! Certificates are ready to use.")
        print("\n💡 Users can now activate these certificates via:")
        print("   1. Scanning QR codes from certificates/ folder")
        print("   2. Using command: /activate <CODE>")
        print(f"\n   Example: /activate {CERTIFICATES[0]}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

