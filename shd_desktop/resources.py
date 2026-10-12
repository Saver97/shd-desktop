"""Paths shared by source runs and PyInstaller bundles."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT_ROOT / "assets"
