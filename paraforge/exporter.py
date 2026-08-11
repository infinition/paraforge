# SPDX-License-Identifier: GPL-3.0-or-later
"""FBX and texture export straight into a .mod folder."""

import os

import bpy

from . import i18n, modfolder, prefs, recipe, sidecar, spec, textures

_ = i18n.t


class ExportResult:
    def __init__(self):
        self.files = []
        self.warnings = []
        self.target_dir = ""

    @property
    def ok(self):
        return bool(self.files)


def fbx_settings(filepath, triangulate=True, vertex_colors=False):
    """Every FBX option Paralives cares about, in one place.

    vertex_colors is off by default on purpose. The game reads the presence of
    a colour attribute, not its contents: any attribute at all makes the mesh
    ZoneDefinition:VertexZones and demands a recolourable shader. Shipping one
    all-white zone therefore makes an item invisible rather than plain, and the
    game's own non recolourable meshes carry no colour attribute at all. See
    spec.py for the log lines and the meshes that were checked.
    """
    return {
        "filepath": filepath,
        "check_existing": False,
        "use_selection": True,
        "use_visible": False,
        "object_types": {"MESH"},
        "use_mesh_modifiers": True,
        "mesh_smooth_type": "FACE",
        "use_triangles": triangulate,
        "use_tspace": True,
        # Only a recolourable item wants its colour zones in the FBX.
        "colors_type": "SRGB" if vertex_colors else "NONE",
        "prioritize_active_color": True,
        "path_mode": "STRIP",
        "embed_textures": False,
        # The wiki is explicit: Z Forward, Y Up.
        "axis_forward": spec.FBX_AXIS_FORWARD,
        "axis_up": spec.FBX_AXIS_UP,
        "apply_unit_scale": True,
        "apply_scale_options": "FBX_SCALE_NONE",
        "global_scale": 1.0,
        "bake_space_transform": False,
        "use_custom_props": False,
        "add_leaf_bones": False,
        "bake_anim": False,
    }


def _supported(kwargs):
    """Drop options this Blender build does not know about."""
    try:
        known = {
            prop.identifier
            for prop in bpy.ops.export_scene.fbx.get_rna_type().properties
        }
    except Exception:
        return kwargs
    return {key: value for key, value in kwargs.items() if key in known}


def base_name(settings, objects):
    raw = settings.asset_name or (objects[0].name if objects else "Asset")
    return textures.pascal_case(raw)


def export(context, settings, objects, report=None):
    """Write the FBX and its textures into the selected mod folder."""
    result = ExportResult()

    mod_path = (settings.mod_folder or "").strip()
    if not mod_path or not os.path.isdir(mod_path):
        raise ValueError("The target mod folder does not exist: " + str(mod_path))
    if not objects:
        raise ValueError("Nothing to export")

    # Assets go in a mod, never in the installation.
    install = modfolder.game_install_above(mod_path)
    if install:
        raise ValueError(_(
            "That folder is inside the Paralives installation ({0}). Assets "
            "belong in a mod under AppData, or a game update will wipe them "
            "and they cannot be shared", install,
        ))

    preferences = prefs.get(context)
    subfolder = preferences.asset_subfolder if preferences else ""
    target_dir = modfolder.ensure_subfolder(mod_path, subfolder)
    result.target_dir = target_dir

    if preferences and preferences.warn_outside_root:
        root = prefs.mods_root(context)
        if root and not modfolder.is_inside_mods_root(mod_path, root):
            result.warnings.append(
                _("The target is outside the detected Paralives folder")
            )

    name = base_name(settings, objects)
    fbx_path = os.path.join(target_dir, name + ".fbx")

    if not settings.overwrite and os.path.exists(fbx_path):
        raise ValueError("File already exists and overwrite is off: " + fbx_path)

    _export_fbx(context, objects, fbx_path, settings.triangulate,
                settings.recolourable)
    result.files.append(fbx_path)

    # Worth saying only when there was something to leave out.
    if not settings.recolourable and _has_color_attribute(objects):
        result.warnings.append(_(
            "The colour zones were left out of the FBX on purpose. A non "
            "recolourable item that carries them does not render in game"
        ))
    if settings.write_sidecars:
        result.files.append(sidecar.write_for_mesh(mod_path, fbx_path))

    if settings.export_textures:
        plan = (report.texture_plan if report else None) or textures.build_plan(
            objects,
            settings.asset_name or (objects[0].name if objects else "Asset"),
            settings.recolourable,
        )
        for output in plan.outputs:
            try:
                written = textures.write(output, target_dir)
            except Exception as error:
                result.warnings.append(
                    _("Could not write {0}: {1}", output.target_name, error)
                )
                continue
            result.files.append(written)
            if settings.write_sidecars:
                result.files.append(
                    sidecar.write_for_texture(mod_path, written, output.suffix)
                )

        for source in plan.unknown:
            result.warnings.append(_(
                "{0} has no known suffix, Paralives will not auto configure it",
                source.stem,
            ))

    if settings.write_recipe:
        try:
            text = recipe.build(settings, name, report, result.files)
            result.files.append(recipe.write(mod_path, name, text))
        except Exception as error:
            result.warnings.append(_("Could not write the recipe: {0}", error))

    return result


def _has_color_attribute(objects):
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        if len(getattr(obj.data, "color_attributes", ())):
            return True
    return False


def _export_fbx(context, objects, filepath, triangulate, vertex_colors=False):
    """Select exactly the target objects, export, then restore the selection."""
    view_layer = context.view_layer
    previous_selection = [o for o in context.selected_objects]
    previous_active = view_layer.objects.active

    try:
        for obj in previous_selection:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        view_layer.objects.active = objects[0]

        kwargs = _supported(fbx_settings(filepath, triangulate, vertex_colors))
        bpy.ops.export_scene.fbx(**kwargs)
    finally:
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in previous_selection:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        try:
            view_layer.objects.active = previous_active
        except (ReferenceError, AttributeError):
            pass


def reveal(path):
    """Open the folder in the system file browser."""
    try:
        bpy.ops.wm.path_open(filepath=path)
    except Exception as error:
        print("[ParaForge] could not open", path, error)
