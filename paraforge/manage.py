# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a mod back, and taking one item out of it again.

Everything else in ParaForge writes into a mod. This reads it, so a mod folder
that has been tried on for a month can be cleaned up without opening a text
editor and without deleting the wrong file.

Removing an item is not removing a file. An item is a prefab, a mesh, its
textures, a sidecar for each of those, an entry in the catalogue, an entry in
the translations and a thumbnail the game generated somewhere else entirely.
Leave any of them and the mod carries a name with nothing behind it, or a
catalogue entry pointing at a prefab that is gone, which the game reads as an
item and fails to draw.

So the tree is walked from the item's own GUID outwards, by GUID rather than
by name, and nothing is deleted that another item in the same mod still
refers to.
"""

import os
import re

from . import i18n, journal, setting

_ = i18n.t

#: Where the game caches the pictures it generates for the catalogue.
THUMBNAIL_FOLDER = os.path.join("_GeneratedThumbnails", "Items")

#: Sidecars the game writes next to an asset, none of which it can be left
#: without. The import files carry the resolution variants.
SIDECAR_SUFFIXES = (".meta", ".import", ".5.import", ".25.import")

_GUID = re.compile(r"GUID:(\d+)")
_ASSET_MESH = re.compile(r"AssetMesh:(\d+)")
_DETAIL_MAP = re.compile(r"DetailMap:(\d+)")
_SURFACE_VALUE = re.compile(r"Value:(\d+)")


class Item:
    """One catalogue entry and everything that belongs to it."""

    __slots__ = ("guid", "name", "prefab_guid", "files", "thumbnail", "shared")

    def __init__(self, guid, name, prefab_guid):
        self.guid = guid
        self.name = name
        self.prefab_guid = prefab_guid
        self.files = []
        self.thumbnail = ""
        self.shared = []

    @property
    def sort_key(self):
        return (self.name or "").lower()


def _settings_path(mod_path, name):
    return os.path.join(mod_path, "Settings", name)


def guid_map(mod_path):
    """Every asset in the mod, keyed by the GUID its sidecar declares.

    Names collide and prefixes lie: Chaise1 is a prefix of Chaise10, and a
    delete that matched on names would take both. GUIDs do not have that
    problem, and they are what the prefabs and the catalogue actually hold.
    """
    found = {}
    try:
        names = os.listdir(mod_path)
    except OSError:
        return found

    for name in names:
        if not name.endswith(".meta"):
            continue
        asset = os.path.join(mod_path, name[:-5])
        if not os.path.isfile(asset):
            continue
        text = setting.read(os.path.join(mod_path, name))
        match = _GUID.search(text or "")
        if match:
            found[match.group(1)] = asset
    return found


def _entries(text, list_key):
    """[(guid, {field: value})] for one list, in the order the file has them."""
    out = []
    current = None
    fields = {}
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("@"):
            if current is not None:
                out.append((current, fields))
            current = stripped[1:]
            fields = {}
            continue
        if current is None or not stripped.startswith("="):
            continue
        key, _sep, value = stripped[1:].partition(":")
        fields.setdefault(key, value)
    if current is not None:
        out.append((current, fields))
    return out


def _sidecars(path):
    """The asset plus every sidecar of it that is actually there."""
    out = [path] if os.path.isfile(path) else []
    for suffix in SIDECAR_SUFFIXES:
        candidate = path + suffix
        if os.path.isfile(candidate):
            out.append(candidate)
    return out


def _referenced_guids(prefab_text):
    """Every GUID a prefab points at: its mesh, its detail map, its surfaces."""
    out = set()
    for pattern in (_ASSET_MESH, _DETAIL_MAP, _SURFACE_VALUE):
        for match in pattern.finditer(prefab_text or ""):
            out.add(match.group(1))
    return out


def thumbnail_for(root, mod_path, guid):
    """The picture the game generated for this item, wherever it put it.

    Not in the mod. The game caches thumbnails per profile, named by the
    item's GUID, and a mod folder copied to another machine arrives without
    them.
    """
    candidates = []
    if mod_path:
        candidates.append(os.path.join(mod_path, THUMBNAIL_FOLDER))
    if root:
        try:
            for name in sorted(os.listdir(root)):
                if name.endswith(".mod"):
                    candidates.append(
                        os.path.join(root, name, THUMBNAIL_FOLDER))
        except OSError:
            pass

    for folder in candidates:
        path = os.path.join(folder, guid + ".png")
        if os.path.isfile(path):
            return path
    return ""


def items(mod_path, root=""):
    """Every item this mod puts in the catalogue, in the order it holds them.

    Which is newest first, since that is how the game writes the file, and it
    is also the order somebody clearing out a month of experiments wants.

    Each one carries the files that belong to it alone. A mesh or a texture
    another item in the same mod also points at is listed as shared instead,
    and is never deleted with the item.
    """
    text = setting.read(_settings_path(mod_path, "Items.setting"))
    if not text:
        return []

    assets = guid_map(mod_path)
    records = []
    claims = {}

    for guid, fields in _entries(text, "AllItems"):
        record = Item(guid, fields.get("DisplayName", ""),
                      fields.get("Prefab", ""))
        record.thumbnail = thumbnail_for(root, mod_path, guid)

        prefab = assets.get(record.prefab_guid, "")
        wanted = [prefab] if prefab else []
        if prefab:
            for referenced in _referenced_guids(setting.read(prefab)):
                asset = assets.get(referenced)
                if asset:
                    wanted.append(asset)

        record.files = wanted
        for path in wanted:
            claims.setdefault(path, []).append(guid)
        records.append(record)

    # A file two items point at belongs to neither of them on its own.
    for record in records:
        keep = []
        for path in record.files:
            if len(claims.get(path, [])) > 1:
                record.shared.append(path)
            else:
                keep.append(path)
        record.files = keep

    return records


def files_of(record):
    """Every file removing this item would take, sidecars included."""
    out = []
    for path in record.files:
        out.extend(_sidecars(path))
    if record.thumbnail:
        out.append(record.thumbnail)
    return out


def remove_entry(text, list_key, guid):
    """Take one @guid entry out of a list, leaving the rest of the file alone.

    The size line is the danger everywhere else in this file, and the reason
    it is not one here: entries added by GUID carry no size, so removing one
    is removing its lines and nothing else. A list that still has a size line
    is one the mod did not write, and is left untouched.
    """
    if not text:
        return None
    ending = setting.line_ending(text)
    lines = text.replace("\r\n", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()

    span = setting.entry_span(lines, list_key, "GUID", guid)
    if span is None:
        return None
    start, end, _index, _depth, marker = span
    if marker == "i":
        return None

    del lines[start:end]
    return ending.join(lines) + ending


def delete(mod_path, record, root="", dry_run=False):
    """Remove one item from the mod, all of it, recoverably.

    Everything removed goes through the journal first, so Undo the last write
    puts it back exactly as it was. Returns (removed_files, notes).
    """
    notes = []
    targets = files_of(record)
    settings = (
        ("Items.setting", "AllItems"),
        ("Translations.setting", "Items"),
        ("Surfaces.setting", "AllSurfaces"),
    )

    edits = []
    for name, list_key in settings:
        path = _settings_path(mod_path, name)
        text = setting.read(path)
        if not text:
            continue
        if name == "Translations.setting":
            guid = _translation_guid(text, record.name)
            if not guid:
                continue
        else:
            guid = record.guid
        updated = remove_entry(text, list_key, guid)
        if updated is not None and updated != text:
            edits.append((path, updated))

    if dry_run:
        return targets, edits

    run = journal.Run(mod_path, _("Removed {0}", record.name or record.guid))
    removed = []
    for path in targets:
        run.will_modify(path)
        try:
            os.remove(path)
            removed.append(path)
        except OSError as error:
            notes.append("{0}: {1}".format(os.path.basename(path), error))

    for path, updated in edits:
        run.will_modify(path)
        setting.write(path, updated)

    run.record()
    return removed, notes


def _translation_guid(text, name):
    """The translation entry for an item, which keys on its name not its GUID."""
    if not name:
        return ""
    wanted = "=Key:Item_" + name
    current = ""
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("@"):
            current = stripped[1:]
        elif stripped == wanted:
            return current
    return ""
