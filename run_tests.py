#!/usr/bin/env python3
"""Comprehensive test runner for the Vechnost bot."""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"✅ {description} - PASSED")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"Exit code: {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"❌ {description} - FAILED")
        print(f"Command not found: {cmd[0]}")
        return False


def main():
    """Run all tests and checks."""
    project_root = Path(__file__).parent
    os.chdir(project_root)

    print("🚀 Starting comprehensive test suite for Vechnost bot...")

    # Test commands
    test_commands = [
        # Linting
        (["ruff", "check", "."], "Ruff linting check"),
        (["ruff", "format", "--check", "."], "Ruff format check"),

        # Type checking
        (["mypy", "vechnost_bot"], "MyPy type checking"),

        # Unit tests
        (["pytest", "tests/", "-v", "--tb=short"], "Unit tests"),
        (["pytest", "tests/", "--cov=vechnost_bot", "--cov-report=html", "--cov-report=term"], "Unit tests with coverage"),

        # Integration tests (if they exist)
        (["pytest", "tests/integration/", "-v"], "Integration tests"),

        # Performance tests (if they exist)
        (["pytest", "tests/performance/", "-v"], "Performance tests"),
    ]

    # Run all tests
    passed = 0
    total = 0

    for cmd, description in test_commands:
        total += 1
        if run_command(cmd, description):
            passed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1


if __name__ == "__main__":
    import os
    sys.exit(main())
