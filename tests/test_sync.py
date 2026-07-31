"""Vérifie que les copies déployées du cœur de reco sont synchronisées."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deployed_copies_in_sync():
    result = subprocess.run(
        [sys.executable, "scripts/sync_recommender.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "Copies désynchronisées — lancer `python scripts/sync_recommender.py`.\n"
        + result.stdout + result.stderr
    )
