# SPDX-License-Identifier: GPL-3.0-or-later
"""Per scene settings.

Property names and tooltips are baked into the RNA when the class registers,
so they are translated here, once, in whatever language was saved. Everything
drawn later goes through i18n.t and follows a live switch.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import catalog, i18n, modfolder, prefs, spec

_ = i18n.t

# Blender frees strings returned by a dynamic enum callback, so the list has to
# outlive the call. This is the documented workaround.
_MOD_ITEMS = []


def _mod_items(self, context):
    _MOD_ITEMS.clear()
    root = prefs.mods_root(context)
    for name, path in modfolder.list_mods(root):
        _MOD_ITEMS.append(
            (path, modfolder.mod_display_name(name), path, "FILE_FOLDER", len(_MOD_ITEMS))
        )
    if not _MOD_ITEMS:
        _MOD_ITEMS.append(
            ("NONE", _("No .mod folder found"),
             _("Create one in the game first"), "ERROR", 0)
        )
    return _MOD_ITEMS


def _on_mod_picked(self, context):
    if self.mod_picker and self.mod_picker != "NONE":
        self.mod_folder = self.mod_picker


def _item_type_items(self, context):
    items = []
    for index, (key, data) in enumerate(spec.ITEM_TYPES.items()):
        items.append((key, _(data["label"]), _(data["description"]), index))
    return items


_CATALOG_ITEMS = []


def _catalog_items(self, context):
    """The real Build Mode tags, read out of the game by extract_catalog.py.

    Indented by depth so a flat dropdown still reads as the tree it is, and
    Blender's own search box makes 298 entries perfectly usable.
    """
    if _CATALOG_ITEMS:
        return _CATALOG_ITEMS
    for guid, name, _parent, depth in catalog.TAGS:
        _CATALOG_ITEMS.append((
            guid,
            ("    " * depth) + name,
            catalog.path(guid),
        ))
    _CATALOG_ITEMS.append((spec.CUSTOM_TAG, _("Custom"),
                           _("Type the tag by hand")))
    return _CATALOG_ITEMS


def _invalidate(self, context):
    from . import cache

    cache.invalidate()


def _redraw(self, context):
    if context is None or context.screen is None:
        return
    for area in context.screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


class ParaForgeSettings(PropertyGroup):

    item_type: EnumProperty(
        name=_("Item type"),
        description=_("Decides which origin rule is enforced"),
        items=_item_type_items,
        update=_invalidate,
    )

    asset_name: StringProperty(
        name=_("Asset name"),
        description=_(
            "Base name for the exported files. Leave empty to use the object "
            "name. Textures become <Name><Suffix>.png"
        ),
        default="",
        update=_invalidate,
    )

    mod_picker: EnumProperty(
        name=_("Mod"),
        description=_("Mod folders found in the Paralives data folder"),
        items=_mod_items,
        update=_on_mod_picked,
    )

    mod_folder: StringProperty(
        name=_("Mod folder"),
        description=_("The .mod folder assets are written into"),
        subtype="DIR_PATH",
        default="",
        update=_invalidate,
    )

    facing_confirmed: BoolProperty(
        name=_("Facing confirmed"),
        description=_("You have checked the item faces the green Y+ arrow"),
        default=False,
        update=_invalidate,
    )

    triangle_budget: IntProperty(
        name=_("Triangle budget"),
        description=_(
            "Paralives publishes no official limit. This is your own ceiling, "
            "used for a warning only"
        ),
        default=spec.DEFAULT_TRIANGLE_BUDGET,
        min=100,
        soft_max=200000,
        update=_invalidate,
    )

    tile_size: FloatProperty(
        name=_("Tile size"),
        description=_(
            "Size of one Paralives grid tile in metres. Calibrate it once by "
            "importing an official game mesh and measuring it"
        ),
        default=spec.DEFAULT_TILE_SIZE,
        min=0.01,
        soft_max=10.0,
        unit="LENGTH",
        update=_invalidate,
    )

    # Catalog placement. These never reach the FBX, they are written to the
    # recipe file so the Control Panel pass becomes a checklist instead of a
    # memory exercise.

    catalog_tag: EnumProperty(
        name=_("Catalog"),
        description=_(
            "Where the item belongs in Build Mode. Paralives sets the base "
            "price from the Item Tag, so this has to match what you pick in "
            "the Control Panel"
        ),
        items=_catalog_items,
    )

    catalog_tag_custom: StringProperty(
        name=_("Custom tag"),
        description=_("Used when the catalog is set to Custom"),
        default="",
    )

    swatch_group: StringProperty(
        name=_("Swatch group"),
        description=_(
            "Swatch group to assign in the Control Panel, for example "
            "BasicWood. One mesh plus a swatch group gives many colourways "
            "without duplicating geometry"
        ),
        default="BasicWood",
    )

    decimate_rebake: BoolProperty(
        name=_("Bake the look back onto it"),
        description=_(
            "Collapsing edges throws the UVs out of shape, which is why the "
            "texture seems to disappear. Unwrap the reduced mesh and bake the "
            "original's colour, relief and roughness onto it"
        ),
        default=True,
    )

    own_surface: BoolProperty(
        name=_("Give the item its own surface"),
        description=_(
            "Write a Surface for this item so it carries its own normal map "
            "and smoothness. Off by default: a mod defined surface still "
            "makes the game refuse the shader and draw the item white, while "
            "borrowing the game's own surface renders correctly without the "
            "relief"
        ),
        default=False,
        update=_invalidate,
    )

    smoothness: FloatProperty(
        name=_("Smoothness"),
        description=_(
            "How glossy the surface is, 0 matte and 1 mirror. The game stores "
            "one value per surface and has no slot for a smoothness texture, "
            "so a Smoothness map is averaged into this on export"
        ),
        default=spec.DEFAULT_SMOOTHNESS,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    fbx_unit_scale: FloatProperty(
        name=_("FBX units per metre"),
        description=_(
            "The game multiplies the raw coordinates of an FBX by 0.01, so a "
            "mesh has to leave Blender in centimetres or it arrives a hundred "
            "times too small and cannot be seen. Measured in the game's own "
            "imported assets. Only change this if a game update changes it"
        ),
        default=spec.FBX_UNITS_PER_METRE,
        min=0.001,
        soft_max=1000.0,
    )

    merge_marker: EnumProperty(
        name=_("Merge style"),
        description=_(
            "How an entry is added to a list the base game already fills. "
            "Leave this alone unless the game misbehaves"
        ),
        items=(
            ("@", _("Add to the game's list"),
             _("Adds a member, identified by its GUID. What a content mod "
               "wants")),
            ("g", _("Extend an existing entry"),
             _("Merges fields onto an entry that already exists. How the "
               "game's own French.mod writes translations")),
            ("i", _("Positional (dangerous)"),
             _("Numbered entry with a size line. On a list the base game "
               "fills, this makes the game keep only what the mod wrote and "
               "drop everything else")),
        ),
        default="@",
    )

    write_recipe: BoolProperty(
        name=_("Write the recipe file"),
        description=_(
            "Save a short text file listing every value to enter in the "
            "Control Panel for this item"
        ),
        default=True,
    )

    # Colour zone authoring

    zone_target: EnumProperty(
        name=_("Zone"),
        description=_("Zone the next assignment writes"),
        items=(
            ("0", "0", _("White, usually the Detail map")),
            ("1", "1", _("Red")),
            ("2", "2", _("Green")),
            ("3", "3", _("Blue")),
            ("decal", _("Decal"), _("Yellow, never recolourable")),
        ),
        default="1",
    )

    zone_color: FloatVectorProperty(
        name=_("Picked colour"),
        description=_("Texture colour sampled from the model"),
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
    )

    zone_tolerance: FloatProperty(
        name=_("Tolerance"),
        description=_(
            "How far from the picked colour still counts. 0 is that exact "
            "colour, 1 takes the whole texture"
        ),
        default=0.12,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    zone_image: StringProperty(
        name=_("Texture"),
        description=_("Image the colour match reads. Filled in by the picker"),
        default="",
    )

    zone_reset_rest: BoolProperty(
        name=_("Reset the rest to zone 0"),
        description=_("Paint everything white before assigning the match"),
        default=False,
    )

    zone_whole_mesh: BoolProperty(
        name=_("Whole mesh"),
        description=_(
            "Paint the entire mesh instead of the faces selected in Edit Mode"
        ),
        default=False,
    )

    # Export options

    recolourable: BoolProperty(
        name=_("Recolourable in game"),
        description=_(
            "Turn the base colour into a GrayMask so the player can recolour "
            "the item from a swatch. Leave it off to keep the texture exactly "
            "as it is, as a Detail map, which is what a downloaded or "
            "generated asset usually wants"
        ),
        default=False,
        update=_invalidate,
    )

    triangulate: BoolProperty(
        name=_("Triangulate on export"),
        description=_("Triangulate in the FBX rather than leaving it to the engine"),
        default=True,
    )

    export_textures: BoolProperty(
        name=_("Export textures"),
        description=_("Write the material textures next to the FBX, correctly named"),
        default=True,
    )

    overwrite: BoolProperty(
        name=_("Overwrite existing files"),
        default=True,
    )

    write_sidecars: BoolProperty(
        name=_("Write the .meta files"),
        description=_(
            "Write the sidecar the game keeps beside every asset, with the "
            "import settings already filled in. Read back from the game's own "
            "mod folder, so the import stops depending on the file name being "
            "parsed correctly"
        ),
        default=True,
    )

    # Viewport overlay

    show_overlay: BoolProperty(
        name=_("Viewport guides"),
        description=_("Draw the grid, origin, facing arrow and bounding box"),
        default=True,
        update=_redraw,
    )

    show_hud: BoolProperty(
        name=_("Viewport checklist"),
        description=_("Draw the checklist in the corner of the viewport"),
        default=True,
        update=_redraw,
    )

    show_grid: BoolProperty(name=_("Grid"), default=True, update=_redraw)
    show_bounds: BoolProperty(name=_("Bounding box"), default=True, update=_redraw)
    show_arrow: BoolProperty(name=_("Facing arrow"), default=True, update=_redraw)

    grid_extent: IntProperty(
        name=_("Grid tiles"),
        description=_("How many tiles to draw around the origin"),
        default=4, min=1, max=32,
        update=_redraw,
    )

    # Where the checklist sits. The 3D viewport draws its own toolbar, sidebar
    # and text overlay on top of the same region, so the checklist measures
    # them and steps aside. These are the manual escape hatch.

    hud_corner: EnumProperty(
        name=_("Checklist corner"),
        description=_("Which corner of the viewport the checklist docks to"),
        items=(
            ("TOP_LEFT", _("Top left"), ""),
            ("TOP_RIGHT", _("Top right"), ""),
            ("BOTTOM_LEFT", _("Bottom left"), ""),
            ("BOTTOM_RIGHT", _("Bottom right"), ""),
        ),
        default="TOP_LEFT",
        update=_redraw,
    )

    hud_offset_x: IntProperty(
        name=_("Nudge X"),
        description=_("Extra horizontal margin, in pixels"),
        default=0, min=-2000, max=2000,
        update=_redraw,
    )

    hud_offset_y: IntProperty(
        name=_("Nudge Y"),
        description=_("Extra vertical margin, in pixels"),
        default=0, min=-2000, max=2000,
        update=_redraw,
    )

    show_all_checks: BoolProperty(
        name=_("Show every check"),
        description=_(
            "Twelve green boxes push the buttons off the bottom of the panel. "
            "Folded, only what still needs attention is listed"
        ),
        default=False,
    )

    hud_only_problems: BoolProperty(
        name=_("Only problems"),
        description=_(
            "Hide the checks that already pass, so the checklist shrinks to "
            "nothing once the asset is clean"
        ),
        default=False,
        update=_redraw,
    )


classes = (ParaForgeSettings,)


def register_pointer():
    bpy.types.Scene.paraforge = bpy.props.PointerProperty(type=ParaForgeSettings)


def unregister_pointer():
    if hasattr(bpy.types.Scene, "paraforge"):
        del bpy.types.Scene.paraforge


def settings(context=None):
    context = context or bpy.context
    return getattr(context.scene, "paraforge", None)


# --------------------------------------------------------------------------
# Surviving a re-registration
#
# Switching language tears the add-on down and builds it again so the baked
# RNA strings change. That deletes Scene.paraforge along with its values, so
# they are copied out first and poured back in afterwards.


SKIPPED = {"rna_type", "name"}


def capture():
    values = {}
    for scene in bpy.data.scenes:
        group = getattr(scene, "paraforge", None)
        if group is None:
            continue
        stored = {}
        for prop in group.bl_rna.properties:
            if prop.identifier in SKIPPED or prop.is_readonly:
                continue
            try:
                value = getattr(group, prop.identifier)
            except (AttributeError, TypeError):
                continue
            if hasattr(value, "__len__") and not isinstance(value, str):
                value = tuple(value)
            stored[prop.identifier] = value
        values[scene.name] = stored
    return values


def restore(values):
    for scene_name, stored in (values or {}).items():
        scene = bpy.data.scenes.get(scene_name)
        group = getattr(scene, "paraforge", None) if scene else None
        if group is None:
            continue
        for identifier, value in stored.items():
            try:
                setattr(group, identifier, value)
            except (AttributeError, TypeError, ValueError):
                continue
