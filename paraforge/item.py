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


def surface_fields(name, surface_guid, texture_guid, normal_guid="",
                   smoothness=None):
    """One surface, in the shape the game writes them.

    Kept to what a shipped surface with a normal map actually declares. Of the
    75 of them, all 75 carry a Texture and a NormalAndAmbientOcclusionMap, 13
    a SmoothnessValue, 12 an AmbientOcclusionStrength, and only 21 a
    DefaultSwatchGroup. WallStoneRubble is the whole minimal form:

        =GUID / =DisplayName / =Texture / =NormalAndAmbientOcclusionMap

    DefaultSwatchGroup and DefaultSwatch are deliberately absent: declaring
    them announces a swatch, and the plain shader has no colour zone to draw
    it in. ShaderType is left out too, as it is on 74 of those 75, and
    BuildModeTags with it, since a surface belonging to one item has no
    business in the in-game surface picker.

    GUID leads, and it is the field this whole file turns on. The game keys
    its surface lookup on it:

        _surfaceDictionary.Add(surface.GUID, surface)

    and WithSurfaces skips a surface that lookup cannot find, leaving the
    builder on the ShaderType.Simple that Init() put there. Against the
    OneZoneNew that one surface always produces, no shader matches, and the
    game says so before drawing the item white:

        Material builder got given parameters that don't match any shaders -
        ShaderType:Simple ZoneDefinition:OneZoneNew LightingMethod:Lit
    """
    fields = [
        ("GUID", surface_guid),
        ("DisplayName", name),
    ]
    if texture_guid:
        fields.append(("Texture", texture_guid))
    if normal_guid:
        fields.append(("NormalAndAmbientOcclusionMap", normal_guid))
        fields.append(("AmbientOcclusionStrength",
                       spec.SURFACE_AMBIENT_OCCLUSION_STRENGTH))
    if smoothness is not None:
        fields.append(("SmoothnessValue", "{0:.4g}".format(float(smoothness))))
    return fields


def _bool3(axes):
    """The game's own three axis flag, written the way it writes it."""
    values = tuple(bool(a) for a in tuple(axes) + (True, True, True))[:3]
    return "bool3({0}, {1}, {2})".format(
        *["True" if v else "False" for v in values]
    )


def _sizes(size, factor):
    """A size triple scaled by a factor, in the game's width/height/depth."""
    return "({0:.4f}, {1:.4f}, {2:.4f})".format(
        *[float(v) * float(factor) for v in size]
    )


def prefab_text(name, mesh_guid, size, detail_guid="", colorzone_guid="",
                pivot=(0.5, 0.5, 0.5), root_guid="", surface_guid="",
                scalable=False, min_scale=spec.MIN_SCALE,
                max_scale=spec.MAX_SCALE, resizable=False,
                resizable_axes=spec.DEFAULT_RESIZABLE_AXES,
                min_size_factor=spec.MIN_SIZE_FACTOR,
                max_size_factor=spec.MAX_SIZE_FACTOR):
    """One root object holding one mesh, which is what an item minimally is.

    Size is in metres, in the game's axis order: width, height, depth. Blender
    hands back width, depth, height, so the caller swaps them. Pivot is
    normalised inside the bounding cube, and the game centres everything at
    0.5 with barely any exception across its 2434 prefabs.

    The root object gets its own identity: ItemMeshReferences keys on the
    object that carries the reference, AssetMesh names the FBX, and the two
    are separate things even when there is only one object.

    IsScalable is what puts the yellow scaling handle on a placed item. The
    widget is created only for a root that declares it:

        if (... && player.ItemSelected.Item.Root.IsScalable)

    and the axes decide what the drag reaches, one axis at a time:

        vector2.x = (item.ScalableAxes.x ? value : 1f);

    so the flag without the axes gives a handle that does nothing. 1114 of the
    game's 2434 prefabs declare it, 983 of them on all three axes, which is
    the form written here.

    HasMinScale and HasMaxScale are written although the game's own prefabs
    omit them. The clamp reads them, not the bounds:

        if (item.HasMinScale) min = ...
        value = Mathf.Clamp(value, min, item.HasMaxScale ? item.MaxScale : ...)

    so a MinScale on its own is a limit that does not hold, and an item can be
    dragged down to nothing.

    IsResizable is the other widget, and a different thing: it stretches the
    item along chosen axes to real dimensions rather than multiplying it whole.
    The game keeps them apart itself, in CancelResizeOrScaleItem, and 133 of
    its prefabs carry both. It takes two statements, one on the root and one on
    the mesh reference, because the mesh has to be told which of its own axes
    follow:

        ItemObjectRoot:
         IsResizable:True
          ResizableAxes:bool3(False, True, False)
          MinSizes:(0.750, 0.670, 0.509)
          MaxSizes:(0.750, 1.500, 0.509)
        ItemMeshReference:
         IsResizable:bool3(False, True, False)

    The sizes are metres in the same order as Size, so they are derived from
    the item's own measurements. HasMaxSize gates MaxSizes exactly as
    HasMaxScale gates MaxScale, and there is no HasMinSize anywhere in the
    assembly, so the floor always applies and the ceiling only when declared.
    """
    root = root_guid or sidecar.guid_for("paraforge", "root", mesh_guid)
    lines = [
        "ItemObject:" + root,
        " Name:Root",
        "ItemObjectRoot:",
    ]
    if scalable:
        lines.extend([
            " IsScalable:True",
            "  ScalableAxes:bool3(True, True, True)",
            "  HasMinScale:True",
            "  MinScale:{0:g}".format(float(min_scale)),
            "  HasMaxScale:True",
            "  MaxScale:{0:g}".format(float(max_scale)),
        ])
    if resizable:
        lines.extend([
            " IsResizable:True",
            "  ResizableAxes:" + _bool3(resizable_axes),
            "  MinSizes:" + _sizes(size, min_size_factor),
            "  HasMaxSize:True",
            "  MaxSizes:" + _sizes(size, max_size_factor),
        ])
    lines.extend([
        " ItemMeshReferences:",
        "  GUID:" + root,
        "   AssetMesh:" + mesh_guid,
        "ItemCubeTransform:",
        " Pivot:({0:.4f}, {1:.4f}, {2:.4f})".format(*pivot),
        " Size:({0:.4f}, {1:.4f}, {2:.4f})".format(*size),
        "ItemMeshReference:",
    ])
    if resizable:
        # Without this the item's cube stretches and the mesh inside it does
        # not follow.
        lines.append(" IsResizable:" + _bool3(resizable_axes))
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
                zone_count, link_seed, recolourable=False, seat_guid=""):
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
        # The GUID of a list element is its identity, and it has to be the
        # item's own. Deriving it from the mod and the tag alone gave every
        # item in a mod filed under the same catalogue tag one shared element,
        # and the game folded them together: adding a vase turned the chair
        # already in the catalogue into a vase. Found by reading seven real
        # items whose Tag blocks all carried GUID:8509043764253587081.
        fields.append((
            "Tag",
            setting.linked_list(4, [
                (sidecar.guid_for(link_seed, "tag", item_guid, tag_guid),
                 tag_guid),
            ]),
        ))

    if seat_guid:
        # The tag names a default, and the item overrides it. 22 of the game's
        # 29 chairs write both lines, which is why filing an item under Chairs
        # is not on its own enough to seat a Para.
        fields.append(("OverrideNestedPrefabToSpawn", "True"))
        fields.append(("NestedPrefabToSpawn", seat_guid))

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


def resolve_seat(settings, tag_guid):
    """The slot template GUID to write on the item, or "".

    Automatic follows the catalogue tag, which is what the game's own items do
    when they leave it alone. Anything else is an explicit choice, and the
    three chair variants exist precisely because seat height differs.
    """
    choice = getattr(settings, "seat_template", "AUTO")
    if choice == "NONE":
        return ""
    if choice == "AUTO":
        return catalog.tag_slot_guid(tag_guid)
    return catalog.slot_prefab_guid(choice)


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

    normal_guid = _texture_guid(mod_path, report, "NormalOcclusion")
    marker = getattr(settings, "merge_marker", setting.MARKER_NEW)

    # A surface written positionally replaced the game's own 950 and threw at
    # startup. One written with the merge marker adds to them. Either way, a
    # file left behind by the old form has to go.
    _drop_legacy_surfaces(run, result, mod_path, seed)

    # The colour always travels through DetailMap. The surface's Texture is the
    # base the shader tints, not the item's colour, and swapping the two
    # renders the item white.
    overlay_guid = detail_guid
    surface_guid = spec.DEFAULT_SURFACE_GUID
    base_guid = gray_guid or spec.DEFAULT_BASE_TEXTURE_GUID
    has_texture = bool(gray_guid or detail_guid)

    if getattr(settings, "own_surface", False) and has_texture:
        # The relief and the material live on the surface, not on the prefab:
        # no prefab field anywhere mentions smoothness or occlusion.
        surface_guid = sidecar.guid_for(seed, "surface", name)
        smoothness = getattr(settings, "smoothness", None)
        _merge(run, result, settings_path(mod_path, SURFACES_FILE), "Surfaces",
               "AllSurfaces", "GUID", surface_guid,
               surface_fields(name, surface_guid, base_guid, normal_guid,
                              smoothness),
               marker, surface_guid)
        if not gray_guid:
            result.notes.append(_(
                "No GrayMask, so the surface sits on the game's neutral base "
                "and the colour comes through the DetailMap"
            ))
        if not normal_guid:
            result.notes.append(_(
                "No NormalOcclusion map, the item will have no relief"
            ))
    elif not has_texture:
        result.notes.append(_(
            "No texture in the mod, the item will render with {0}",
            spec.DEFAULT_SURFACE_NAME,
        ))
    else:
        result.notes.append(_(
            "Using the game's {0}. The NormalOcclusion and Smoothness maps "
            "have no slot on a shared surface, so the item has no relief. "
            "Turn on its own surface to give it one",
            spec.DEFAULT_SURFACE_NAME,
        ))

    size = game_size(getattr(report, "measurement", None))

    # Regenerating an unchanged item must be a no-op, otherwise every press
    # of the button adds a step to the undo history that undoes nothing.
    wanted = prefab_text(name, mesh_guid, size, overlay_guid, colorzone_guid,
                         surface_guid=surface_guid,
                         scalable=getattr(settings, "scalable", True),
                         min_scale=getattr(settings, "min_scale",
                                           spec.MIN_SCALE),
                         max_scale=getattr(settings, "max_scale",
                                           spec.MAX_SCALE),
                         resizable=getattr(settings, "resizable", False),
                         resizable_axes=tuple(
                             getattr(settings, "resizable_axes",
                                     spec.DEFAULT_RESIZABLE_AXES)),
                         min_size_factor=getattr(settings, "min_size_factor",
                                                 spec.MIN_SIZE_FACTOR),
                         max_size_factor=getattr(settings, "max_size_factor",
                                                 spec.MAX_SIZE_FACTOR))
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

    marker = getattr(settings, "merge_marker", setting.MARKER_NEW)

    seat_guid = resolve_seat(settings, tag_guid)
    if seat_guid:
        result.notes.append(_(
            "A Para can sit on it: {0}", catalog.SLOT_BY_GUID.get(
                seat_guid, seat_guid)))

    _merge(run, result, settings_path(mod_path, ITEMS_FILE), "Items",
           "AllItems", "GUID", item_guid,
           item_fields(name, item_guid, prefab_guid, tag_guid, swatch_guid,
                       zone_count, seed, recolourable, seat_guid),
           marker, item_guid)

    key = TRANSLATION_PREFIX + name
    translation_guid = sidecar.guid_for(seed, "translation", key)
    _merge(run, result, settings_path(mod_path, TRANSLATIONS_FILE),
           "Translations", "Items", "Key", key,
           translation_fields(key, _readable(name), seed),
           marker, translation_guid)

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


def _drop_legacy_surfaces(run, result, mod_path, seed):
    """Remove a Surfaces.setting written the dangerous way.

    Version 0.6.0 wrote its surface positionally, "s1" then "i0", which tells
    the game the surface collection has one member and makes its own 950 go
    away. The symptom was a crash at every launch:

        NullReferenceException at SurfaceThumbnailManager.Start()

    A file written with the merge marker adds to the collection instead and is
    left alone, so this only clears the old form. The journal keeps a copy
    either way, and Undo puts it back.
    """
    path = settings_path(mod_path, SURFACES_FILE)
    text = setting.read(path)
    if not text.strip():
        return

    lines = text.replace("\r\n", "\n").split("\n")
    if not setting.has_positional_entries(lines, "AllSurfaces"):
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
           fields, marker=setting.MARKER_NEW, key=None):
    """Add the entry, or repair the one already carrying the same key.

    Skipping an existing entry was wrong: an entry written by an earlier
    version stayed wrong forever, and the button still reported success.
    """
    text = setting.read(path)
    lines = text.replace("\r\n", "\n").split("\n")

    present = setting.contains_value(lines, unique_key, unique_value)
    if not present and marker != setting.MARKER_POSITIONAL:
        # The GUID lives in the marker line rather than in a field.
        present = setting.entry_span(
            lines, list_key, unique_key, unique_value
        ) is not None

    if present:
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
    merged = setting.append_entry(text, list_key, fields, section, marker, key)
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
