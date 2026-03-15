#!/usr/bin/env python3
"""Life Hack OS - Personal Operating System for Discipline and Execution."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.ui.app import run

if __name__ == "__main__":
    run()
