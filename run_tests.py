#!/usr/bin/env python3
"""Comprehensive test runner for Vechnost bot."""

import sys
import subprocess
import argparse
import os
from pathlib import Path


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"❌ Command not found: {cmd[0]}")
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run Vechnost bot tests")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "performance", "all"],
        default="all",
        help="Type of tests to run"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run with coverage reporting"
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        help="Include slow tests"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of parallel workers"
    )
    parser.add_argument(
        "--html-report",
        action="store_true",
        help="Generate HTML coverage report"
    )

    args = parser.parse_args()

    # Base pytest command
    cmd = ["python", "-m", "pytest"]

    # Add test type filters
    if args.type == "unit":
        cmd.extend(["-m", "unit"])
    elif args.type == "integration":
        cmd.extend(["-m", "integration"])
    elif args.type == "performance":
        cmd.extend(["-m", "performance"])

    # Add slow tests if requested
    if args.slow:
        cmd.extend(["-m", "slow"])
    else:
        cmd.extend(["-m", "not slow"])

    # Add coverage if requested
    if args.coverage:
        cmd.extend([
            "--cov=vechnost_bot",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml"
        ])

        if args.html_report:
            cmd.append("--cov-report=html:htmlcov")

    # Add verbose output
    if args.verbose:
        cmd.append("-v")

    # Add parallel execution
    if args.parallel > 1:
        cmd.extend(["-n", str(args.parallel)])

    # Add test directory
    cmd.append("tests/")

    # Run tests
    success = run_command(cmd, f"Running {args.type} tests")

    if not success:
        print("\n❌ Tests failed!")
        sys.exit(1)

    # Run additional checks if all tests passed
    if args.type == "all":
        print("\n" + "="*60)
        print("Running additional checks...")
        print("="*60)

        # Lint check
        lint_success = run_command(
            ["python", "-m", "ruff", "check", "."],
            "Linting with ruff"
        )

        # Type check
        type_success = run_command(
            ["python", "-m", "mypy", "vechnost_bot"],
            "Type checking with mypy"
        )

        # Format check
        format_success = run_command(
            ["python", "-m", "ruff", "format", "--check", "."],
            "Format checking with ruff"
        )

        if not all([lint_success, type_success, format_success]):
            print("\n❌ Some checks failed!")
            sys.exit(1)

    print("\n🎉 All tests and checks passed!")

    # Show coverage summary if available
    if args.coverage:
        coverage_file = Path("coverage.xml")
        if coverage_file.exists():
            print(f"\n📊 Coverage report generated: {coverage_file}")

        html_dir = Path("htmlcov")
        if html_dir.exists():
            print(f"📊 HTML coverage report: {html_dir}/index.html")


if __name__ == "__main__":
    main()
