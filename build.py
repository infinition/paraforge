#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package the add-on into an installable zip.

Blender expects blender_manifest.toml at the root of the archive, so the
contents of paraforge/ are zipped, not the folder itself.

    python build.py
    python build.py --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"

With --blender, Blender's own extension builder is used instead, which also
validates the manifest.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(ROOT, "paraforge")
DIST = os.path.join(ROOT, "dist")

EXCLUDE_DIRS = {"__pycache__", ".git", ".mypy_cache"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo")


def read_version():
    manifest = os.path.join(SOURCE, "blender_manifest.toml")
    with open(manifest, "r", encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("No version in blender_manifest.toml")
    return match.group(1)


def build_zip():
    version = read_version()
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, "paraforge-{0}.zip".format(version))

    if os.path.exists(target):
        os.remove(target)

    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for directory, subdirs, names in os.walk(SOURCE):
            subdirs[:] = [d for d in subdirs if d not in EXCLUDE_DIRS]
            for name in sorted(names):
                if name.endswith(EXCLUDE_SUFFIXES):
                    continue
                full = os.path.join(directory, name)
                relative = os.path.relpath(full, SOURCE)
                archive.write(full, relative)
                count += 1

    print("{0} file(s) -> {1}".format(count, target))
    return target


def build_with_blender(executable):
    os.makedirs(DIST, exist_ok=True)
    command = [
        executable, "--command", "extension", "build",
        "--source-dir", SOURCE,
        "--output-dir", DIST,
    ]
    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default="", help="Path to blender.exe")
    parser.add_argument("--clean", action="store_true", help="Remove dist first")
    args = parser.parse_args(argv)

    if args.clean and os.path.isdir(DIST):
        shutil.rmtree(DIST)

    if args.blender:
        return build_with_blender(args.blender)

    build_zip()
    return 0


if __name__ == "__main__":
    sys.exit(main())
