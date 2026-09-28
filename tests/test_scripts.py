"""Every script in scripts/ answers --help, and does nothing else.

The scripts are doors into production data, run by hand, rarely, and often
months after the code under them changed. Three had quietly stopped doing
what they said (one printed the wrong columns, one could not see a lifetime
purchase, one filtered for markers nothing carried) and nothing noticed. This
runs each one the cheapest way there is, in a fresh interpreter: a script
whose imports no longer resolve fails here, and so does one that acts before
it has read its arguments - on --help, generating the card art or
downloading fonts would rewrite files in the checkout.

The one shell script, typecheck.sh, is a CI gate and runs on every push.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((REPO / "scripts").glob("*.py"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_every_script_answers_help_and_does_nothing_else(script, tmp_path):
    # The checkout's code, not whatever copy of the package is installed;
    # the environment is the suite's (a fake token, a throwaway database).
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage:"), result.stdout
    assert not list(tmp_path.iterdir()), "--help wrote files"


def test_the_scripts_are_found():
    """A glob that matches nothing passes every parametrized test."""
    assert {path.name for path in SCRIPTS} >= {
        "broadcast.py",
        "check_user_simple.py",
        "generate_certificates.py",
        "smoke_production.py",
        "test_webhook.py",
    }
