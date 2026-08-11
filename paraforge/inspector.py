# SPDX-License-Identifier: GPL-3.0-or-later
"""Mod folder snapshot and diff.

This is the tool for the experiment that decides how far the pipeline can be
automated: snapshot an empty mod, create one item inside the game, snapshot
again, and read what the game wrote. If the item definition turns out to be
plain text, an exporter can generate it and the in game step disappears.

Pure standard library on purpose, so it also runs outside Blender through
tools/mod_diff.py.
"""

import datetime
import difflib
import hashlib
import json
import os

#: Files small enough and textual enough to keep in full, so the diff can show
#: what the game actually wrote.
TEXT_EXTENSIONS = {
    ".json", ".txt", ".xml", ".csv", ".meta", ".ini", ".cfg",
    ".yaml", ".yml", ".md", ".asset", ".mod", ".manifest", ".log",
}
TEXT_MAX_BYTES = 512 * 1024

SNAPSHOT_VERSION = 1


def _hash_file(path):
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path, size):
    if size > TEXT_MAX_BYTES:
        return None
    extension = os.path.splitext(path)[1].lower()
    if extension not in TEXT_EXTENSIONS:
        # Extensionless files are common in Unity style data folders.
        if extension:
            return None
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        if b"\x00" in raw[:4096]:
            return None
        return raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def snapshot(root):
    """Record every file under root, with content for the textual ones."""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise ValueError("Not a folder: " + root)

    files = {}
    for directory, _subdirs, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(directory, name)
            relative = os.path.relpath(full, root).replace("\\", "/")
            try:
                size = os.path.getsize(full)
                entry = {"size": size, "sha1": _hash_file(full)}
                text = _read_text(full, size)
                if text is not None:
                    entry["text"] = text
            except OSError as error:
                entry = {"size": -1, "sha1": "", "error": str(error)}
            files[relative] = entry

    return {
        "version": SNAPSHOT_VERSION,
        "root": root,
        "taken": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": files,
    }


def save(data, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    return path


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def diff(before, after):
    old = before.get("files", {})
    new = after.get("files", {})

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(
        name for name in set(old) & set(new)
        if old[name].get("sha1") != new[name].get("sha1")
    )
    return {"added": added, "removed": removed, "modified": modified}


def _unified(old_text, new_text, name):
    lines = difflib.unified_diff(
        (old_text or "").splitlines(),
        (new_text or "").splitlines(),
        fromfile="before/" + name,
        tofile="after/" + name,
        lineterm="",
        n=2,
    )
    return list(lines)


def report(before, after, max_text_lines=400):
    """A readable markdown report of what changed between two snapshots."""
    changes = diff(before, after)
    old = before.get("files", {})
    new = after.get("files", {})

    out = []
    out.append("# Paralives mod folder diff")
    out.append("")
    out.append("Folder: `{0}`".format(after.get("root", "?")))
    out.append("")
    out.append("Before: {0}  |  After: {1}".format(
        before.get("taken", "?"), after.get("taken", "?")
    ))
    out.append("")
    out.append("{0} added, {1} modified, {2} removed".format(
        len(changes["added"]), len(changes["modified"]), len(changes["removed"])
    ))
    out.append("")

    if not any(changes.values()):
        out.append("Nothing changed. Did the game write to a different folder, "
                   "or did you forget to quit the game before snapshotting?")
        return "\n".join(out)

    text_added = [n for n in changes["added"] if "text" in new.get(n, {})]
    binary_added = [n for n in changes["added"] if n not in text_added]

    if changes["added"]:
        out.append("## Added")
        out.append("")
        for name in changes["added"]:
            marker = "text" if name in text_added else "binary"
            out.append("- `{0}`  ({1} bytes, {2})".format(
                name, new[name].get("size", "?"), marker
            ))
        out.append("")

    if changes["modified"]:
        out.append("## Modified")
        out.append("")
        for name in changes["modified"]:
            out.append("- `{0}`  ({1} -> {2} bytes)".format(
                name, old[name].get("size", "?"), new[name].get("size", "?")
            ))
        out.append("")

    if changes["removed"]:
        out.append("## Removed")
        out.append("")
        for name in changes["removed"]:
            out.append("- `{0}`".format(name))
        out.append("")

    verdict = _verdict(text_added, binary_added, changes, old, new)
    out.append("## Verdict")
    out.append("")
    out.extend(verdict)
    out.append("")

    budget = max_text_lines
    if text_added:
        out.append("## Content of the added text files")
        out.append("")
        for name in text_added:
            if budget <= 0:
                out.append("_(truncated)_")
                break
            out.append("### " + name)
            out.append("")
            out.append("```")
            lines = new[name]["text"].splitlines()
            out.extend(lines[:budget])
            if len(lines) > budget:
                out.append("... {0} more lines".format(len(lines) - budget))
            budget -= min(len(lines), budget)
            out.append("```")
            out.append("")

    text_modified = [
        n for n in changes["modified"]
        if "text" in old.get(n, {}) and "text" in new.get(n, {})
    ]
    if text_modified:
        out.append("## Changes inside modified text files")
        out.append("")
        for name in text_modified:
            patch = _unified(old[name]["text"], new[name]["text"], name)
            if not patch:
                continue
            out.append("### " + name)
            out.append("")
            out.append("```diff")
            out.extend(patch[:200])
            if len(patch) > 200:
                out.append("... {0} more lines".format(len(patch) - 200))
            out.append("```")
            out.append("")

    return "\n".join(out)


def _verdict(text_added, binary_added, changes, old, new):
    """Say plainly whether generating item definitions looks feasible."""
    lines = []
    json_like = [n for n in text_added if n.lower().endswith(".json")]
    text_modified = [
        n for n in changes["modified"]
        if "text" in old.get(n, {}) and "text" in new.get(n, {})
    ]

    if json_like:
        lines.append(
            "**JSON files were written.** The item definition is very likely "
            "generatable from outside the game, which means a full one click "
            "pipeline is possible. Read the files listed above and template "
            "from them, never from a hand written schema."
        )
    elif text_added or text_modified:
        lines.append(
            "**Text files changed but none are JSON.** Look at the content "
            "below. If it is structured and readable, generating it is still "
            "realistic."
        )
    else:
        lines.append(
            "**Only binary files changed.** The item definition is not "
            "editable from outside, so the Control Panel pass stays manual. "
            "ParaForge still removes the export and validation work."
        )

    if binary_added:
        lines.append("")
        lines.append(
            "Binary files added: " + ", ".join("`{0}`".format(n) for n in binary_added[:10])
            + ("..." if len(binary_added) > 10 else "")
        )
    lines.append("")
    lines.append(
        "Whatever the format, it is not a published contract. Paralives is in "
        "early access, so record the game version this snapshot came from."
    )
    return lines
