#!/usr/bin/env python3
"""Startet den Spielplatz-Modus: python playground.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.playground import run_playground

if __name__ == "__main__":
    run_playground()
