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


def surface_fields(name, surface_guid, texture_guid):
    """One surface: a texture, and the default shader.

    A mesh with no surface does not render. The game logs it plainly:

        Material builder got given parameters that don't match any shaders -
        ShaderType:GrayMask ZoneDefinition:None ...

    ShaderType is deliberately absent. Roughly 1400 of the 944 surface
    entries the game ships omit it, across GrayMask, Detail and Master
    textures alike, so leaving it out is the ordinary opaque item shader
    rather than an oversight.
    """
    fields = [
        ("GUID", surface_guid),
        ("DisplayName", name),
    ]
    if texture_guid:
        fields.append(("Texture", texture_guid))
    fields.append(("DefaultSwatchGroup", 0))
    fields.append(("DefaultSwatch", 0))
    return fields


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
                zone_count, link_seed):
    """The Items.setting entry, in the order the game writes it."""
    fields = [
        ("GUID", item_guid),
        ("DisplayName", name),
        ("Prefab", prefab_guid),
    ]
    if tag_guid:
        fields.append((
            "Tag",
            setting.linked_list(4, [
                (sidecar.guid_for(link_seed, "tag", tag_guid), tag_guid),
            ]),
        ))
    if swatch_guid:
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

    # The surface carries the base texture. A recolourable item bases itself
    # on the GrayMask and keeps the Detail as a separate overlay; an item that
    # is not recolourable has only the Detail, and that becomes the base.
    surface_texture = gray_guid or detail_guid
    overlay_guid = detail_guid if gray_guid else ""

    surface_guid = ""
    if surface_texture:
        surface_guid = sidecar.guid_for(seed, "surface", name)
        _merge(run, result, settings_path(mod_path, SURFACES_FILE), "Surfaces",
               "AllSurfaces", "GUID", surface_guid,
               surface_fields(name, surface_guid, surface_texture))
    else:
        result.notes.append(_(
            "No texture in the mod, the item will render with the game's "
            "default surface"
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
    if (settings.swatch_group or "").strip() and not swatch_guid:
        result.notes.append(_(
            "No swatch group called {0} in the game, the item is written "
            "without one", swatch_name,
        ))

    _merge(run, result, settings_path(mod_path, ITEMS_FILE), "Items",
           "AllItems", "GUID", item_guid,
           item_fields(name, item_guid, prefab_guid, tag_guid, swatch_guid,
                       zone_count, seed))

    key = TRANSLATION_PREFIX + name
    _merge(run, result, settings_path(mod_path, TRANSLATIONS_FILE),
           "Translations", "Items", "Key", key,
           translation_fields(key, _readable(name), seed))

    run.record()
    return result


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
    """Add an entry unless one with the same key is already there."""
    text = setting.read(path)
    lines = text.replace("\r\n", "\n").split("\n")
    if setting.contains_value(lines, unique_key, unique_value):
        result.skipped.append(os.path.basename(path))
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
