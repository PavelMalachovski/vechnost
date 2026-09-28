#!/usr/bin/env python3
"""Mint printed gift certificates: codes into the database, QR cards to disk.

A certificate code is a bearer token for lifetime access - whoever holds it
can redeem it once, no questions asked. So the script is careful about
where a code can end up:

- The codes are minted by `payments.gifts.create_gift_certificate`, the
  same function that issues a code when somebody buys a gift through
  Tribute. One alphabet, one length, one uniqueness check; the printed
  voucher and the bought one are indistinguishable to the bot and to
  `tests/test_no_secrets.py`, which knows this format and fails the build
  if a code is ever pasted into docs or scripts.
- The QR cards are written to `certificates/` by default, which is
  git-ignored. Any other output directory inside the repository is refused
  unless git ignores it too. (Five live codes were once committed inside a
  review document, and the repository is public.)
- Nothing but the certificate's database id is logged. The codes are
  printed once, to the terminal, and that is the only place they exist
  besides the database and the PNG files.

Usage:

    python scripts/generate_certificates.py 10
    python scripts/generate_certificates.py 10 --sql
    python scripts/generate_certificates.py 10 --out /somewhere/outside --bot my_bot

`--sql` also writes `certificates.sql` next to the cards: INSERT statements
for loading the same codes into another database, for the case where the
machine that prints the vouchers cannot reach production. Run it against
production before handing a voucher out, or the QR leads to «not found».
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from vechnost_bot.config import settings
from vechnost_bot.payments.database import get_db
from vechnost_bot.payments.gifts import create_gift_certificate

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "certificates"
FONT = ROOT / "assets" / "fonts" / "Inter-SemiBold.ttf"
MAX_PER_RUN = 100


def activation_link(code: str, bot_username: str) -> str:
    """The deep link the QR encodes; `/start activate_<code>` redeems it."""
    return f"https://t.me/{bot_username}?start=activate_{code}"


def render_card(code: str, link: str) -> Image.Image:
    """A white card: the QR code, the brand line and the code in clear text.

    The code is printed under the QR on purpose - a voucher whose code can
    only be read by a phone camera is useless to somebody typing it in a
    chat, and `/activate <code>` is the documented fallback.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    padding, text_band = 40, 90
    width = qr_img.width + 2 * padding
    card = Image.new("RGB", (width, qr_img.height + padding + text_band), "white")
    card.paste(qr_img, (padding, padding // 2))

    draw = ImageDraw.Draw(card)
    try:
        title_font = ImageFont.truetype(str(FONT), 22)
        code_font = ImageFont.truetype(str(FONT), 30)
    except OSError:
        title_font = code_font = ImageFont.load_default()

    y = qr_img.height + padding // 2
    for text, font in (("VECHNOST", title_font), (code, code_font)):
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (right - left)) // 2 - left, y - top), text, fill="black", font=font)
        y += bottom - top + 8
    return card


def git_ignores(path: Path) -> bool:
    """True if git would ignore `path` (or git is not available to ask).

    Asked with a trailing slash: a `dir/` pattern in .gitignore matches a
    directory, and a path with no slash that does not exist yet is a file
    to git and is not matched.
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", f"{path}/"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    except OSError:
        return True
    return result.returncode == 0


def output_dir_is_safe(out_dir: Path) -> bool:
    """A directory outside the repository, or one git ignores, is safe.

    Anything else would put PNGs named after live codes one `git add .`
    away from a public history.
    """
    out_dir = out_dir.resolve()
    try:
        out_dir.relative_to(ROOT)
    except ValueError:
        return True
    return git_ignores(out_dir)


def sql_for(codes: list[str]) -> str:
    """INSERTs that load the codes into a database the script could not reach.

    Portable between SQLite and PostgreSQL; a code already present is left
    alone rather than failing the whole file.
    """
    lines = ["BEGIN;"]
    for code in codes:
        lines.append(
            "INSERT INTO certificates (code, is_used, created_at) "
            f"VALUES ('{code}', FALSE, CURRENT_TIMESTAMP) ON CONFLICT (code) DO NOTHING;"
        )
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


async def mint(count: int, out_dir: Path, bot_username: str, with_sql: bool) -> list[str]:
    """Create `count` certificates in the database and write their cards."""
    out_dir.mkdir(parents=True, exist_ok=True)
    codes: list[str] = []
    async with get_db() as session:
        for _ in range(count):
            code = await create_gift_certificate(session)
            await session.commit()
            codes.append(code)
            render_card(code, activation_link(code, bot_username)).save(
                out_dir / f"certificate_{len(codes):02d}_{code}.png"
            )
    if with_sql:
        (out_dir / "certificates.sql").write_text(sql_for(codes), encoding="utf-8")
    return codes


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("count", nargs="?", type=int, default=5, help="how many to mint (1-100)")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="where to write the QR cards (default: certificates/, git-ignored)",
    )
    parser.add_argument(
        "--bot",
        default=None,
        help="bot username without @ (default: BOT_USERNAME from the environment)",
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="also write certificates.sql with INSERTs for another database",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.count <= MAX_PER_RUN:
        parser.error(f"count must be between 1 and {MAX_PER_RUN}")
    args.bot = (args.bot or settings.bot_username or "").lstrip("@")
    if not args.bot:
        parser.error("no bot username: pass --bot or set BOT_USERNAME")
    if not output_dir_is_safe(args.out):
        parser.error(
            f"{args.out} is inside the repository and not git-ignored; "
            "certificate codes must never be committed. Use certificates/ "
            "or a directory outside the checkout."
        )
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    codes = asyncio.run(mint(args.count, args.out, args.bot, args.sql))

    print(f"Minted {len(codes)} certificates for @{args.bot}; cards in {args.out.resolve()}")
    for i, code in enumerate(codes, 1):
        print(f"  {i:2d}. {code}")
    if args.sql:
        print(f"SQL for another database: {args.out.resolve() / 'certificates.sql'}")
    print("Redeem: scan the QR, or /activate <code> in the bot.")
    print("The codes are printed here once. Do not paste them into the repository.")


if __name__ == "__main__":
    main()
