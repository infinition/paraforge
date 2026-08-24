# SPDX-License-Identifier: GPL-3.0-or-later
"""FBX and texture export straight into a .mod folder."""

import os

import bpy

from . import i18n, modfolder, prefs, recipe, sidecar, spec, textures, uvxform

_ = i18n.t


class ExportResult:
    def __init__(self):
        self.files = []
        self.warnings = []
        self.target_dir = ""

    @property
    def ok(self):
        return bool(self.files)


def fbx_settings(filepath, triangulate=True, vertex_colors=False,
                 baked_axes=False):
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
        # The wiki says Z Forward, Y Up, and that is what the exporter is asked
        # for when it has to do the conversion itself. When the geometry has
        # already been rotated and scaled on a copy, the exporter must convert
        # nothing or it would undo the work on the node.
        "axis_forward": (spec.FBX_IDENTITY_FORWARD if baked_axes
                         else spec.FBX_AXIS_FORWARD),
        "axis_up": spec.FBX_IDENTITY_UP if baked_axes else spec.FBX_AXIS_UP,
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
                settings.recolourable,
                getattr(settings, "fbx_unit_scale", spec.FBX_UNITS_PER_METRE),
                name)
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

        # There is no slot for a smoothness texture anywhere in the game's
        # data, only one value per surface, so the map is averaged into it.
        for output in plan.by_suffix("Smoothness"):
            average = average_smoothness(
                os.path.join(target_dir, output.target_name)
            )
            if average is None:
                continue
            settings.smoothness = average
            result.warnings.append(_(
                "Smoothness averaged to {0:.2f}. The game stores one value "
                "per surface and has no slot for a smoothness map",
                average,
            ))
            break

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


def scaled_copies(context, objects, factor, name=""):
    """Throwaway objects holding the geometry, baked and scaled.

    The world transform is baked in and the result multiplied by factor, so
    the FBX carries centimetre sized vertices with an identity node. That is
    what the game reads: it scales raw coordinates by 0.01 and ignores node
    scaling, so putting the factor on the node instead would change nothing.

    Modifiers are evaluated here rather than by the exporter, because scaling
    the base mesh underneath a modifier would change what the modifier does.

    The material's coordinate transform is baked into the copy's UVs at the
    same time. An FBX cannot carry a Mapping node, and the game samples the
    exported coordinates as they are, so a transform left on the node would be
    lost and the texture would land on the wrong part of the mesh.
    """
    import math

    from mathutils import Matrix

    depsgraph = context.evaluated_depsgraph_get()
    scale = Matrix.Scale(factor, 4)
    # Blender is Z up, the game's meshes are Y up: (x, y, z) becomes (x, z, -y).
    to_y_up = Matrix.Rotation(math.radians(-90.0), 4, "X")
    # And the game's front is the other end from Blender's. Without this an
    # asymmetric item arrives backwards: the catalogue thumbnail is shot from
    # behind and a Para sits down facing their own backrest.
    half_turn = Matrix.Rotation(math.radians(spec.FBX_YAW), 4, "Z")
    created = []

    for index, obj in enumerate(objects):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
        )
        mesh.transform(obj.matrix_world)
        mesh.transform(half_turn)
        mesh.transform(to_y_up)
        mesh.transform(scale)

        resolved = uvxform.resolve_object(obj)
        if resolved.moves:
            uvxform.apply_to_mesh(mesh, resolved.matrix, resolved.uv_map)

        # The game's own files name the mesh after the item, not after
        # whatever the artist left in the outliner.
        label = name or obj.name
        if len(objects) > 1:
            label = "{0}_{1}".format(label, index)
        mesh.name = label

        copy = bpy.data.objects.new(label, mesh)
        context.scene.collection.objects.link(copy)
        created.append(copy)

    return created


def discard(objects):
    for obj in objects:
        mesh = obj.data
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except (ReferenceError, RuntimeError):
            continue
        if mesh is not None and mesh.users == 0:
            try:
                bpy.data.meshes.remove(mesh)
            except (ReferenceError, RuntimeError):
                pass


def average_smoothness(path):
    """The mean of a written Smoothness map, or None.

    The game keeps a single SmoothnessValue per surface, used by 329 of its own
    surfaces, and no field anywhere takes a smoothness texture. Averaging is
    therefore the whole of what can be carried over.

    The file on disk is read rather than the source image, because the map is
    often rebuilt on the way out, from roughness for instance, and it is the
    written result that the game would have used.
    """
    import numpy as np

    if not path or not os.path.isfile(path):
        return None

    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        width, height = image.size
        if width <= 0 or height <= 0:
            return None
        flat = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(flat)
        return float(np.clip(flat.reshape(-1, 4)[:, :3].mean(), 0.0, 1.0))
    except (RuntimeError, ValueError, AttributeError, TypeError):
        return None
    finally:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except (ReferenceError, RuntimeError):
                pass


def _has_color_attribute(objects):
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        if len(getattr(obj.data, "color_attributes", ())):
            return True
    return False


def _export_fbx(context, objects, filepath, triangulate, vertex_colors=False,
                unit_scale=spec.FBX_UNITS_PER_METRE, name=""):
    """Select exactly the target objects, export, then restore the selection."""
    view_layer = context.view_layer
    previous_selection = [o for o in context.selected_objects]
    previous_active = view_layer.objects.active
    temporary = []

    try:
        for obj in previous_selection:
            obj.select_set(False)

        # Copies are also what carries the material's coordinate transform
        # into the UVs, so they are made for that alone when the scale would
        # not have called for them.
        rescale = bool(unit_scale) and abs(unit_scale - 1.0) > 1e-9
        if rescale or uvxform.resolve(objects).moves:
            temporary = scaled_copies(
                context, objects, unit_scale if rescale else 1.0, name
            )
            exported = temporary
        else:
            exported = objects

        for obj in exported:
            obj.select_set(True)
        view_layer.objects.active = exported[0]

        kwargs = _supported(fbx_settings(
            filepath, triangulate, vertex_colors, baked_axes=bool(temporary)
        ))
        if temporary:
            # The copies already carry their modifiers and their transform.
            kwargs["use_mesh_modifiers"] = False
        bpy.ops.export_scene.fbx(**kwargs)
    finally:
        discard(temporary)
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
