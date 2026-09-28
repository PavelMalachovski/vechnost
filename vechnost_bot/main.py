"""Main entry point for the Vechnost bot."""

import sys

from vechnost_bot.bot import run_bot


def main() -> None:
    """Main entry point."""
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
