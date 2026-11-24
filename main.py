#!/usr/bin/env python3
"""Deliver the prepared front page for the 23 November 2026 entry.

The artwork is finished ahead of time and stored next to this script
as entry.png, so delivering the entry is a single faithful copy: read
the PNG bytes from the script's own folder and write them, unchanged,
into the output folder. The output folder comes from the
MAKEFUN_OUTPUT_DIR environment variable when it is set and is
/output otherwise. Standard library only, no network access, and the
bytes written are identical on every run.
"""

import os
import sys


def target_path():
    folder = os.environ.get("MAKEFUN_OUTPUT_DIR", "").strip()
    if not folder:
        folder = "/output"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "entry.png")


def run():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "entry.png"), "rb") as source:
        payload = source.read()
    with open(target_path(), "wb") as sink:
        sink.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(run())
