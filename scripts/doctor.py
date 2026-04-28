#!/usr/bin/env python3
"""Wrapper CLI pour `python -m PHOEBUS.doctor`."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PHOEBUS.doctor import main


if __name__ == "__main__":
    raise SystemExit(main())
