#!/usr/bin/env python3
"""Script to generate QR code certificates for free one-time access."""

import asyncio
import os
import secrets
import string
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.repositories import CertificateRepository


def generate_certificate_code(length: int = 12) -> str:
    """
    Generate a unique certificate code.

    Args:
        length: Length of the code (default: 12)

    Returns:
        Unique certificate code in format: VECH-XXXX-XXXX
    """
    # Use uppercase alphanumeric characters (excluding confusing ones like 0, O, I, 1)
    chars = string.ascii_uppercase.replace("O", "").replace("I", "") + string.digits.replace("0", "").replace("1", "")
    code = "".join(secrets.choice(chars) for _ in range(length))
    # Format as VECH-XXXX-XXXX
    return f"VECH-{code[:4]}-{code[4:]}"


def generate_qr_code(code: str, output_path: Path) -> None:
    """
    Generate QR code image for certificate.

    Args:
        code: Certificate code
        output_path: Path to save QR code image
    """
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(code)
    qr.make(fit=True)

    # Create QR code image
    qr_img = qr.make_image(fill_color="black", back_color="white")

    # Create a larger image with text
    img_width, img_height = qr_img.size
    padding = 40
    text_height = 60
    final_img = Image.new("RGB", (img_width + 2 * padding, img_height + 2 * padding + text_height), "white")

    # Paste QR code
    final_img.paste(qr_img, (padding, padding))

    # Add text
    draw = ImageDraw.Draw(final_img)
    try:
        # Try to use a nice font
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        # Fallback to default font
        font = ImageFont.load_default()

    # Center text
    text = f"VECHNOST Certificate\n{code}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (final_img.width - text_width) // 2
    text_y = img_height + padding + 10

    draw.text((text_x, text_y), text, fill="black", font=font, align="center")

    # Save image
    final_img.save(output_path)
    print(f"✅ QR code saved: {output_path}")


async def create_certificates(count: int = 5, output_dir: str = "certificates") -> None:
    """
    Create certificates and generate QR codes.

    Args:
        count: Number of certificates to create (default: 5)
        output_dir: Directory to save QR code images
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Generating {count} certificates...")
    print(f"{'='*60}\n")

    codes = []
    async with get_db() as session:
        for i in range(count):
            # Generate unique code
            while True:
                code = generate_certificate_code()
                # Check if code already exists
                existing = await CertificateRepository.get_by_code(session, code)
                if not existing:
                    break

            # Create certificate in database
            certificate = await CertificateRepository.create(session, code)
            await session.commit()

            # Generate QR code
            qr_filename = f"certificate_{i+1:02d}_{code}.png"
            qr_path = output_path / qr_filename
            generate_qr_code(code, qr_path)

            codes.append(code)
            print(f"📋 Certificate {i+1}: {code}")

    print(f"\n{'='*60}")
    print(f"✅ Successfully created {count} certificates!")
    print(f"📁 QR codes saved in: {output_path.absolute()}")
    print(f"{'='*60}\n")

    # Print summary
    print("📋 Certificate Codes:")
    for i, code in enumerate(codes, 1):
        print(f"   {i}. {code}")

    print(f"\n💡 Users can activate certificates using:")
    print(f"   /activate <CODE>")
    print(f"\n   Example: /activate {codes[0]}")


async def main():
    """Main function."""
    count = 5
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
            if count < 1 or count > 100:
                print("Error: count must be between 1 and 100")
                sys.exit(1)
        except ValueError:
            print("Error: count must be a number")
            sys.exit(1)

    output_dir = "certificates"
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]

    await create_certificates(count, output_dir)


if __name__ == "__main__":
    asyncio.run(main())

