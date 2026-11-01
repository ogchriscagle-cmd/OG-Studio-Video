"""Separate bundled resources from writable per-user application data."""
import os
import sys
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parent
DATA_ROOT = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OG Studio"
             if getattr(sys, "frozen", False) else ASSET_ROOT)
DATA_ROOT.mkdir(parents=True, exist_ok=True)
