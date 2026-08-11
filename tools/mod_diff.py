#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapshot and diff a Paralives mod folder, without Blender.

This answers the question that decides how far the pipeline can go: does the
game store item definitions as text you could generate, or as opaque binary?

    python tools/mod_diff.py snap  "C:/Users/you/AppData/LocalLow/Paralives/Paralives/MyPack_1234.mod"
    (create one item inside the game, then quit the game)
    python tools/mod_diff.py diff  "C:/Users/you/AppData/LocalLow/Paralives/Paralives/MyPack_1234.mod"

The diff prints a report and writes it next to the snapshot.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paraforge import inspector  # noqa: E402


def snapshot_path(mod_path, directory):
    key = os.path.basename(os.path.normpath(mod_path)) or "mod"
    return os.path.join(directory, key + ".snapshot.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snap", "diff"))
    parser.add_argument("mod", help="Path to the .mod folder")
    parser.add_argument(
        "--store", default=".paraforge",
        help="Where snapshots are kept (default: .paraforge)",
    )
    args = parser.parse_args(argv)

    mod = os.path.abspath(args.mod)
    if not os.path.isdir(mod):
        parser.error("Not a folder: " + mod)

    os.makedirs(args.store, exist_ok=True)
    path = snapshot_path(mod, args.store)

    if args.action == "snap":
        data = inspector.snapshot(mod)
        inspector.save(data, path)
        print("{0} file(s) recorded".format(len(data["files"])))
        print("Snapshot: " + path)
        print()
        print("Now create one item inside the game, quit the game, then run:")
        print('  python tools/mod_diff.py diff "{0}"'.format(mod))
        return 0

    if not os.path.isfile(path):
        parser.error("No snapshot yet, run 'snap' first")

    before = inspector.load(path)
    after = inspector.snapshot(mod)
    text = inspector.report(before, after)

    report_path = os.path.splitext(path)[0] + ".diff.md"
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    print(text)
    print()
    print("Report written to " + report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
