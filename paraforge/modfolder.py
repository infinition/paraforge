# SPDX-License-Identifier: GPL-3.0-or-later
"""Locating and writing into Paralives mod folders.

A Paralives mod is a plain directory named "<Name>_<id>.mod" that lives in the
game's data folder. Importing an asset means dropping the file into that
directory, which is why this add-on never needs the game to be running.
"""

import os
import platform
import shutil

from . import spec

#: Candidate roots, most specific first. The game nests a second "Paralives"
#: directory on Windows; older guides quote only the outer one.
WINDOWS_ROOTS = (
    os.path.join("AppData", "LocalLow", "Paralives", "Paralives"),
    os.path.join("AppData", "LocalLow", "Paralives"),
)

MAC_ROOTS = (
    os.path.join("Library", "Application Support", "com.Paralives.Paralives"),
)

LINUX_ROOTS = (
    os.path.join(
        ".steam", "steam", "steamapps", "compatdata", "1118520", "pfx",
        "drive_c", "users", "steamuser", "AppData", "LocalLow",
        "Paralives", "Paralives",
    ),
)


def candidate_roots():
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        parts = WINDOWS_ROOTS
    elif system == "Darwin":
        parts = MAC_ROOTS
    else:
        parts = LINUX_ROOTS
    return [os.path.join(home, part) for part in parts]


def detect_root():
    """Return the first existing mods root, or an empty string."""
    for path in candidate_roots():
        if os.path.isdir(path):
            return path
    return ""


def resolve_root(configured=""):
    """Prefer an explicit preference, fall back to auto detection."""
    configured = (configured or "").strip()
    if configured and os.path.isdir(configured):
        return configured
    return detect_root()


def list_mods(root):
    """Return [(folder_name, absolute_path)] for every .mod folder under root."""
    if not root or not os.path.isdir(root):
        return []
    found = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    for name in entries:
        path = os.path.join(root, name)
        if name.endswith(spec.MOD_FOLDER_SUFFIX) and os.path.isdir(path):
            found.append((name, path))
    return found


def mod_display_name(folder_name):
    """Turn "MyPack_483920.mod" into "MyPack"."""
    stem = folder_name
    if stem.endswith(spec.MOD_FOLDER_SUFFIX):
        stem = stem[: -len(spec.MOD_FOLDER_SUFFIX)]
    head, sep, tail = stem.rpartition("_")
    if sep and tail.isdigit():
        return head
    return stem


def ensure_subfolder(mod_path, subfolder=""):
    """Return the directory assets should be written to, creating it if needed."""
    target = mod_path
    subfolder = (subfolder or "").strip().strip("/\\")
    if subfolder:
        target = os.path.join(mod_path, subfolder)
    os.makedirs(target, exist_ok=True)
    return target


def copy_asset(source, target_dir, target_name):
    """Copy a file into the mod folder and return the written path."""
    destination = os.path.join(target_dir, target_name)
    if os.path.abspath(source) == os.path.abspath(destination):
        return destination
    shutil.copyfile(source, destination)
    return destination


#: Files that only ever sit in a Paralives installation, never in a user mod.
GAME_MARKERS = ("Paralives.exe", "UnityPlayer.dll", "Paralives_Data")


def game_install_above(path):
    """The game folder this path sits inside, or an empty string.

    Assets belong in a mod under AppData, never in the installation. Writing
    into the game's own Main.mod would put work in a folder that a game update
    overwrites, and would produce something that cannot be shared. It is an
    easy mistake to make now that the install is a plain readable folder, so
    it is refused rather than warned about.
    """
    current = os.path.abspath(path or "")
    seen = set()
    while current and current not in seen:
        seen.add(current)
        try:
            names = set(os.listdir(current))
        except OSError:
            names = set()
        if sum(marker in names for marker in GAME_MARKERS) >= 2:
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return ""


def is_inside_mods_root(path, root):
    if not path or not root:
        return False
    try:
        return os.path.commonpath(
            [os.path.abspath(path), os.path.abspath(root)]
        ) == os.path.abspath(root)
    except ValueError:
        return False
