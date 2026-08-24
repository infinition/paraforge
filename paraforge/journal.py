# SPDX-License-Identifier: GPL-3.0-or-later
"""An undo history for everything ParaForge writes into a mod folder.

Generating an item does not only add files, it also edits Items.setting and
Translations.setting, which the game writes too. Editing someone else's file
is only acceptable if it can be taken back exactly, so every run is recorded:
which files were created, and what the ones that were modified looked like
first.

Undoing removes what was created and restores what was changed, oldest state
last, so pressing it twice walks backwards through two runs rather than
getting stuck. The backups live inside the mod, next to the recipe files, so
copying the mod carries its own history with it.
"""

import datetime
import json
import os
import shutil

FOLDER = "_paraforge"
BACKUPS = os.path.join(FOLDER, "backups")
JOURNAL = os.path.join(FOLDER, "journal.json")

#: Runs kept before the oldest are dropped, with their backups.
KEEP = 20


def _journal_path(mod_path):
    return os.path.join(mod_path, JOURNAL)


def load(mod_path):
    try:
        with open(_journal_path(mod_path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def save(mod_path, runs):
    path = _journal_path(mod_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(runs, handle, indent=1)
    return path


class Run:
    """Collects what a single generation touched, then records it."""

    def __init__(self, mod_path, label):
        self.mod_path = mod_path
        self.label = label
        self.created = []
        self.modified = []
        self.stamp = datetime.datetime.now().isoformat(timespec="seconds")

    def _relative(self, path):
        try:
            return os.path.relpath(path, self.mod_path).replace("\\", "/")
        except ValueError:
            return path

    def will_create(self, path):
        """Call before writing a file that did not exist."""
        if not os.path.exists(path):
            self.created.append(self._relative(path))
            return True
        return False

    def will_modify(self, path):
        """Copy a file aside before it is changed. Returns the backup path.

        Only the first time. A run that touches one file twice, which is what
        removing several items does to Items.setting, would otherwise take its
        second backup from the already half edited file, and the undo would
        restore the middle of the run instead of the state before it.

        The backup name is built from the run's own timestamp, so the second
        copy lands on the first one and there is no trace of the mistake
        beyond an undo that brings back some of what it should.
        """
        if not os.path.isfile(path):
            return self.will_create(path)

        relative = self._relative(path)
        if relative in self.created:
            return None
        for change in self.modified:
            if change["path"] == relative:
                return os.path.join(self.mod_path, change["backup"])

        folder = os.path.join(self.mod_path, BACKUPS)
        os.makedirs(folder, exist_ok=True)
        stamp = self.stamp.replace(":", "").replace("-", "")

        # The stamp is only good to the second, and two runs inside one second
        # is not a hypothetical: pressing the button twice does it, and so did
        # every removal of several items before this was found. The second run
        # wrote its backup over the first one's, and the older undo then
        # restored the newer state, quietly losing whatever the first run had
        # replaced.
        base = os.path.join(
            folder, "{0}.{1}".format(os.path.basename(path), stamp))
        backup = base + ".bak"
        attempt = 1
        while os.path.exists(backup):
            backup = "{0}.{1}.bak".format(base, attempt)
            attempt += 1

        shutil.copy2(path, backup)
        self.modified.append({
            "path": self._relative(path),
            "backup": self._relative(backup),
        })
        return backup

    def record(self):
        if not self.created and not self.modified:
            return None
        runs = load(self.mod_path)
        runs.append({
            "stamp": self.stamp,
            "label": self.label,
            "created": self.created,
            "modified": self.modified,
        })
        dropped = runs[:-KEEP]
        for old in dropped:
            for change in old.get("modified", []):
                _remove(os.path.join(self.mod_path, change["backup"]))
        save(self.mod_path, runs[-KEEP:])
        return self


def _remove(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def last(mod_path):
    runs = load(mod_path)
    return runs[-1] if runs else None


def undo_last(mod_path):
    """Put the mod back the way it was before the most recent run.

    Returns (label, removed, restored) or None when there is nothing to undo.
    """
    runs = load(mod_path)
    if not runs:
        return None
    run = runs.pop()

    removed = 0
    emptied = set()
    for relative in run.get("created", []):
        target = os.path.join(mod_path, relative)
        if _remove(target):
            removed += 1
            emptied.add(os.path.dirname(target))

    restored = 0
    for change in run.get("modified", []):
        backup = os.path.join(mod_path, change["backup"])
        target = os.path.join(mod_path, change["path"])
        if not os.path.isfile(backup):
            continue
        try:
            shutil.copy2(backup, target)
            restored += 1
        except OSError:
            continue
        _remove(backup)

    # A Settings folder this run created should not survive it empty.
    for folder in sorted(emptied, key=len, reverse=True):
        if os.path.abspath(folder) == os.path.abspath(mod_path):
            continue
        try:
            os.rmdir(folder)
        except OSError:
            pass

    save(mod_path, runs)
    return run.get("label", ""), removed, restored
