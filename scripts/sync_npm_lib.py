#!/usr/bin/env python3
"""Backward-compatible alias for the deterministic distribution builder."""
import sys

from build_dist import main

if __name__ == "__main__":
    sys.exit(main())
