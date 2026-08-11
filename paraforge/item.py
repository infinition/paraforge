# SPDX-License-Identifier: GPL-3.0-or-later
"""Generating the item itself, so nothing is left to do in the Control Panel.

Until now the add-on stopped at the FBX and its textures, and the last ten
clicks happened inside the game. They do not have to: an item is three pieces
of plain text inside your own mod.

    <Mod>/<Name>.prefab              the object tree, its size, its mesh
    <Mod>/Settings/Items.setting     the catalogue entry, tag and swatches
    <Mod>/Settings/Translations...   the label the player actually reads

The shapes here were read back from Main.mod, the developers' own mod, which
ships inside the installation as ordinary text. Nothing is written into the
game: every path below is inside the target .mod.

Everything cross references by GUID, and sidecar.asset_guid derives those from
the mod and the file name so that regenerating an item points at the same mesh
instead of orphaning it.
"""

import os
import re

from . import catalog, i18n, journal, setting, sidecar, spec, textures

_ = i18n.t

SETTINGS_FOLDER = "Settings"
ITEMS_FILE = "Items.setting"
TRANSLATIONS_FILE = "Translations.setting"
SURFACES_FILE = "Surfaces.setting"

#: Item.DisplayName is an identifier; the label comes from this translation.
TRANSLATION_PREFIX = "Item_"


def settings_path(mod_path, name):
    return os.path.join(mod_path, SETTINGS_FOLDER, name)


# --------------------------------------------------------------------------
# The prefab


def prefab_text(name, mesh_guid, size, detail_guid="", colorzone_guid="",
                pivot=(0.5, 0.5, 0.5), root_guid="", surface_guid=""):
    """One root object holding one mesh, which is what an item minimally is.

    Size is in metres, in the game's axis order: width, height, depth. Blender
    hands back width, depth, height, so the caller swaps them. Pivot is
    normalised inside the bounding cube, and the game centres everything at
    0.5 with barely any exception across its 2434 prefabs.

    The root object gets its own identity: ItemMeshReferences keys on the
    object that carries the reference, AssetMesh names the FBX, and the two
    are separate things even when there is only one object.
    """
    root = root_guid or sidecar.guid_for("paraforge", "root", mesh_guid)
    lines = [
        "ItemObject:" + root,
        " Name:Root",
        "ItemObjectRoot:",
        " ItemMeshReferences:",
        "  GUID:" + root,
        "   AssetMesh:" + mesh_guid,
        "ItemCubeTransform:",
        " Pivot:({0:.4f}, {1:.4f}, {2:.4f})".format(*pivot),
        " Size:({0:.4f}, {1:.4f}, {2:.4f})".format(*size),
        "ItemMeshReference:",
    ]
    if surface_guid:
        lines.extend([
            " Surfaces:",
            "  Surface:",
            "   GUID:" + sidecar.guid_for("paraforge", "surfacelink", root),
            "   Value:" + surface_guid,
        ])
    if detail_guid:
        lines.append(" DetailMap:" + detail_guid)
    if colorzone_guid:
        lines.append(" ColorZoneMap:" + colorzone_guid)
    lines.append("---")
    return "\r\n".join(lines) + "\r\n"


def game_size(measurement):
    """Blender's (x, y, z) turned into the game's (width, height, depth)."""
    if measurement is None or measurement.empty:
        return (1.0, 1.0, 1.0)
    size = measurement.size
    return (float(size[0]), float(size[2]), float(size[1]))


# --------------------------------------------------------------------------
# The catalogue entry


def item_fields(name, item_guid, prefab_guid, tag_guid, swatch_guid,
                zone_count, link_seed, recolourable=False):
    """The Items.setting entry, in the order the game writes it.

    An item that is not recolourable says so and stops there. CityGravelPile,
    which is the shape ParaForge copies, is exactly:

        =GUID / =DisplayName / =Prefab / =HasSwatches:False / =Tag

    Declaring a swatch group on an item with no recolourable zones asks the
    game for colourways that its material cannot produce, so it is written
    only when the item really is recolourable.
    """
    fields = [
        ("GUID", item_guid),
        ("DisplayName", name),
        ("Prefab", prefab_guid),
    ]

    if not (recolourable and swatch_guid):
        fields.append(("HasSwatches", "False"))

    if tag_guid:
        fields.append((
            "Tag",
            setting.linked_list(4, [
                (sidecar.guid_for(link_seed, "tag", tag_guid), tag_guid),
            ]),
        ))

    if recolourable and swatch_guid:
        fields.append(("SwatchGroup", swatch_guid))
        fields.append(("SwatchColorZoneCount", max(0, int(zone_count))))
        # 1 is what the game uses for a single colour thumbnail, which is
        # what an item with one zone wants.
        fields.append(("SwatchThumbnailType", 1 if zone_count <= 1 else 2))
    return fields


def translation_fields(key, label, link_seed):
    return [
        ("GUID", sidecar.guid_for(link_seed, "translation", key)),
        ("Key", key),
        ("Value", label),
    ]


# --------------------------------------------------------------------------
# Writing it all


class Result:
    def __init__(self):
        self.files = []
        self.notes = []
        self.item_guid = ""
        self.prefab_guid = ""
        self.skipped = []


def resolve_tag(settings):
    if settings.catalog_tag == spec.CUSTOM_TAG:
        return (settings.catalog_tag_custom or "").strip()
    return settings.catalog_tag


def resolve_swatch(settings):
    """Swatch groups are referenced by GUID, the field holds a name."""
    wanted = (settings.swatch_group or "").strip()
    if not wanted:
        return "", ""
    if wanted.isdigit():
        return wanted, catalog.SWATCH_BY_GUID.get(wanted, wanted)
    guid = catalog.SWATCH_BY_NAME.get(wanted)
    return (guid or ""), wanted


def generate(mod_path, name, settings, report, zone_count=1):
    """Write the prefab and register the item. Returns a Result."""
    result = Result()
    mesh_file = name + ".fbx"
    mesh_path = os.path.join(mod_path, mesh_file)
    if not os.path.isfile(mesh_path):
        raise ValueError(_(
            "Export the mesh first, {0} is not in the mod folder", mesh_file
        ))

    run = journal.Run(mod_path, name)
    seed = sidecar.mod_name(mod_path)

    # Once the game has imported an asset it owns its GUID. Ours matches, but
    # an asset that arrived some other way would not, and the prefab has to
    # point at whatever is actually on disk.
    mesh_guid = existing_guid(mod_path, mesh_file)
    prefab_file = name + ".prefab"
    prefab_path = os.path.join(mod_path, prefab_file)
    prefab_guid = sidecar.asset_guid(mod_path, prefab_file)
    result.prefab_guid = prefab_guid

    # The Detail and ColorZone maps are assigned on the mesh reference, which
    # is the step the wiki tells you to do by hand in the Prefab Editor.
    gray_guid = _texture_guid(mod_path, report, "GrayMask")
    detail_guid = _texture_guid(mod_path, report, "Detail")
    colorzone_guid = _texture_guid(mod_path, report, "ColorZone")

    # A mod must not define its own surface: the game throws
    # NullReferenceException in SurfaceThumbnailManager.Start() on startup when
    # it finds one. Its own items point at a shared surface and lay their
    # texture over it through DetailMap, which is what happens here.
    _drop_our_surfaces(run, result, mod_path, seed)
    surface_guid = spec.DEFAULT_SURFACE_GUID

    overlay_guid = detail_guid
    if gray_guid and not detail_guid:
        # A GrayMask is the recolourable base, and the base lives on the
        # surface, which is the one thing a mod cannot supply. Say so rather
        # than write an item that renders as plain gray.
        result.notes.append(_(
            "{0} is a GrayMask. A mod cannot define the surface that would "
            "carry it, so the item points at {1} instead. Recolourable "
            "textures still need a Surface built in the Control Panel",
            name, spec.DEFAULT_SURFACE_NAME,
        ))
    elif not detail_guid:
        result.notes.append(_(
            "No texture in the mod, the item will render with {0}",
            spec.DEFAULT_SURFACE_NAME,
        ))

    size = game_size(getattr(report, "measurement", None))

    # Regenerating an unchanged item must be a no-op, otherwise every press
    # of the button adds a step to the undo history that undoes nothing.
    wanted = prefab_text(name, mesh_guid, size, overlay_guid, colorzone_guid,
                         surface_guid=surface_guid)
    if setting.read(prefab_path) != wanted:
        run.will_modify(prefab_path)
        setting.write(prefab_path, wanted)
        result.files.append(prefab_path)
    else:
        result.skipped.append(prefab_file)

    if sidecar.read(prefab_path).get("GUID") != prefab_guid:
        run.will_modify(prefab_path + ".meta")
        result.files.append(sidecar.write(
            prefab_path, spec.META_TYPE_PREFAB, prefab_guid
        ))

    item_guid = sidecar.guid_for(seed, "item", name)
    result.item_guid = item_guid
    tag_guid = resolve_tag(settings)
    swatch_guid, swatch_name = resolve_swatch(settings)
    recolourable = bool(getattr(settings, "recolourable", False))
    if recolourable and (settings.swatch_group or "").strip() and not swatch_guid:
        result.notes.append(_(
            "No swatch group called {0} in the game, the item is written "
            "without one", swatch_name,
        ))

    _merge(run, result, settings_path(mod_path, ITEMS_FILE), "Items",
           "AllItems", "GUID", item_guid,
           item_fields(name, item_guid, prefab_guid, tag_guid, swatch_guid,
                       zone_count, seed, recolourable))

    key = TRANSLATION_PREFIX + name
    _merge(run, result, settings_path(mod_path, TRANSLATIONS_FILE),
           "Translations", "Items", "Key", key,
           translation_fields(key, _readable(name), seed))

    run.record()
    return result


def our_surface_entries(text, seed):
    """Split a Surfaces.setting into (ours, foreign) by GUID.

    An entry is ours when its GUID is the one guid_for would derive from its
    own DisplayName. Anything else was put there by a human or another tool and
    is left alone.
    """
    ours, foreign = [], []
    current = None
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if re.fullmatch(r"i\d+", line):
            if current is not None:
                (ours if _is_ours(current, seed) else foreign).append(current)
            current = {}
            continue
        if line.startswith("=") and current is not None:
            key, _sep, value = line[1:].partition(":")
            current[key.strip()] = value.strip()
    if current is not None:
        (ours if _is_ours(current, seed) else foreign).append(current)
    return ours, foreign


def _is_ours(entry, seed):
    name = entry.get("DisplayName", "")
    guid = entry.get("GUID", "")
    if not name or not guid:
        return False
    return guid == sidecar.guid_for(seed, "surface", name)


def _drop_our_surfaces(run, result, mod_path, seed):
    """Remove a Surfaces.setting this add-on wrote in an earlier version.

    Version 0.6.0 defined a surface per item, which turned out to crash the
    game during startup:

        NullReferenceException at SurfaceThumbnailManager.Start()

    Leaving the file in place would keep that crash alive on every launch, so
    it goes. The journal keeps a copy, and Undo puts it back.
    """
    path = settings_path(mod_path, SURFACES_FILE)
    text = setting.read(path)
    if not text.strip():
        return

    ours, foreign = our_surface_entries(text, seed)
    if foreign or not ours:
        result.notes.append(_(
            "{0} holds surfaces this add-on did not write, so it was left "
            "alone. A mod defined surface crashes the game at startup, remove "
            "it by hand if the game does not start", SURFACES_FILE,
        ))
        return

    run.will_modify(path)
    os.remove(path)
    result.files.append(path)

    meta = path + ".meta"
    if os.path.isfile(meta):
        run.will_modify(meta)
        os.remove(meta)
        result.files.append(meta)

    result.notes.append(_(
        "Removed the {0} written by an earlier version: it made the game "
        "throw at startup and the item render as nothing. The item now points "
        "at the game's own {1}", SURFACES_FILE, spec.DEFAULT_SURFACE_NAME,
    ))

    # Every prefab that pointed at one of those surfaces now points at
    # nothing, which is how the item became invisible in the first place.
    # Only this item is being regenerated, so the others are repaired here or
    # they stay broken until someone remembers them.
    removed = {entry.get("GUID", "") for entry in ours if entry.get("GUID")}
    repointed = _repoint_prefabs(run, result, mod_path, removed)
    if repointed:
        result.notes.append(_(
            "Repointed {0} other prefab(s) at {1}, they referenced a surface "
            "that no longer exists", repointed, spec.DEFAULT_SURFACE_NAME,
        ))


def _repoint_prefabs(run, result, mod_path, removed_guids):
    """Send prefabs referencing a deleted surface to the shared one."""
    if not removed_guids:
        return 0

    count = 0
    for name in sorted(os.listdir(mod_path)):
        if not name.endswith(".prefab"):
            continue
        path = os.path.join(mod_path, name)
        text = setting.read(path)
        if not text:
            continue

        patched = text
        for guid in removed_guids:
            patched = patched.replace(
                "Value:" + guid, "Value:" + spec.DEFAULT_SURFACE_GUID
            )
        if patched == text:
            continue

        run.will_modify(path)
        setting.write(path, patched)
        result.files.append(path)
        count += 1
    return count


def existing_guid(mod_path, filename):
    """The GUID already on disk, or the one this add-on would derive."""
    written = sidecar.read(os.path.join(mod_path, filename)).get("GUID", "")
    if written.isdigit() and written != "0":
        return written
    return sidecar.asset_guid(mod_path, filename)


def _texture_guid(mod_path, report, suffix):
    plan = getattr(report, "texture_plan", None)
    if plan is None:
        return ""
    for output in plan.by_suffix(suffix):
        if os.path.isfile(os.path.join(mod_path, output.target_name)):
            return existing_guid(mod_path, output.target_name)
    return ""


def _merge(run, result, path, section, list_key, unique_key, unique_value,
           fields):
    """Add the entry, or repair the one already carrying the same key.

    Skipping an existing entry was wrong: an entry written by an earlier
    version stayed wrong forever, and the button still reported success.
    """
    text = setting.read(path)
    lines = text.replace("\r\n", "\n").split("\n")
    if setting.contains_value(lines, unique_key, unique_value):
        repaired = setting.replace_entry(
            text, list_key, unique_key, unique_value, fields
        )
        if repaired is None or repaired == text:
            result.skipped.append(os.path.basename(path))
            return
        run.will_modify(path)
        setting.write(path, repaired)
        result.files.append(path)
        return

    run.will_modify(path)
    merged = setting.append_entry(text, list_key, fields, section)
    setting.write(path, merged)
    result.files.append(path)

    # Settings files carry a .meta like every other asset, with two extra
    # keys naming the section, exactly as the game writes it.
    meta = path + ".meta"
    if not os.path.isfile(meta):
        run.will_create(meta)
        mod_path = os.path.dirname(os.path.dirname(path))
        sidecar.write(
            path, spec.META_TYPE_SETTING,
            sidecar.asset_guid(mod_path, os.path.basename(path)),
            {"IsSettingType": "True", "SettingType": "Setting." + section},
        )


def _readable(name):
    """Turn OldWoodenTable into "Old Wooden Table" for the player facing label."""
    out = []
    for index, character in enumerate(name):
        if index and character.isupper() and not name[index - 1].isupper():
            out.append(" ")
        out.append(character)
    return "".join(out).strip() or name
