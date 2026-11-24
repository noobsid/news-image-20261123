#!/usr/bin/env python3
"""Entry program for make.fun's news-image-20261123 competition.

Beside this file sits entry.png: a single broadsheet page summing up
Monday 23 November 2026 — Jensen Huang's return to Nvidia, the sinking
of the corvette Merkury at Benghazi, Iran's defiance over Hormuz, and
34 further stories. render.py painted it beforehand; this program
only has to deliver a byte-identical copy to
$MAKEFUN_OUTPUT_DIR/entry.png, falling back to /output/entry.png when
the variable is not set. It uses nothing outside the standard
library, touches no network, and writes the same bytes on every run.
"""

import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "entry.png", out_dir / "entry.png")


if __name__ == "__main__":
    main()
