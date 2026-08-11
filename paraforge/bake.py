# SPDX-License-Identifier: GPL-3.0-or-later
"""Collapse a many material asset into the single surface Paralives wants.

A model bought or downloaded is usually split into five or ten materials, each
with its own set of 4K maps. Paralives assigns one surface per mesh, so that
asset cannot be imported as it stands: either it is cut into as many meshes,
or everything is baked down into one atlas.

This does the second. It repacks the UVs of the whole selection into one 0 to
1 space, bakes each channel into one image per channel, then replaces every
material with a single one wired to the result. What comes out is what the
viewport was already showing, which is the point: the look survives, only the
plumbing changes.

Baking is the one slow operation in the add-on, so it is never automatic.
"""

import bpy

from . import i18n, imaging, spec, textures

_ = i18n.t

# Bake passes, in the order they are run. Each one becomes a source image
# with its role already stamped on it, so the export plan picks them up
# without having to guess anything.
#
# The fill matters more than it looks. A bake only touches the pixels a UV
# island covers, and an atlas is never full, so whatever the rest holds bleeds
# into the surface through the bake margin and through mipmapping. Cleared to
# black, an occlusion map reads as fully shadowed and the item arrives in game
# looking switched off. Each pass is therefore pre-filled with its neutral
# value and baked without clearing.
#
#   kind, image suffix, role, data map, neutral fill
PASSES = (
    ("DIFFUSE", "Detail", spec.BASE_COLOR, False, (0.5, 0.5, 0.5, 1.0)),
    ("NORMAL", "Normal", spec.NORMAL, True, spec.FLAT_NORMAL + (1.0,)),
    ("ROUGHNESS", "Roughness", spec.ROUGHNESS, True, (0.5, 0.5, 0.5, 1.0)),
    ("AO", "Occlusion", spec.OCCLUSION, True, (1.0, 1.0, 1.0, 1.0)),
)


class BakeError(RuntimeError):
    pass


def targets(objects):
    return [o for o in objects if o.type == "MESH" and o.data.polygons]


# --------------------------------------------------------------------------
# UV atlas


def repack_uvs(context, objects, name="ParaForgeAtlas", margin=0.003):
    """One shared UV layout across the whole selection.

    Smart UV Project run on a multi object edit session cuts every mesh into
    islands inside the same 0 to 1 square, which is what a shared atlas needs,
    but it leaves them wherever they landed. Packing afterwards scales them up
    to fill the square: without it a plant with fifty small islands uses about
    a tenth of the texture and throws away most of the resolution.
    """
    for obj in objects:
        layers = obj.data.uv_layers
        layer = layers.get(name) or layers.new(name=name, do_init=True)
        layers.active = layer
        for candidate in layers:
            candidate.active_render = candidate == layer

    with _selection(context, objects):
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(
                angle_limit=1.15192, island_margin=margin, correct_aspect=True,
                scale_to_bounds=False,
            )
            bpy.ops.uv.select_all(action="SELECT")
            _pack_islands(margin)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
    return name


def _pack_islands(margin):
    """Pack, degrading gracefully across Blender versions."""
    for kwargs in (
        {"rotate": True, "scale": True, "margin": margin,
         "shape_method": "CONCAVE", "margin_method": "SCALED"},
        {"rotate": True, "margin": margin},
        {"margin": margin},
        {},
    ):
        try:
            bpy.ops.uv.pack_islands(**kwargs)
            return True
        except TypeError:
            continue
        except RuntimeError as error:
            print("[ParaForge] pack_islands refused:", error)
            return False
    return False


# --------------------------------------------------------------------------
# Baking


def bake_all(context, objects, base_name, resolution=2048, samples=16,
             wanted=("DIFFUSE", "NORMAL", "ROUGHNESS", "AO"), margin=8):
    """Run every requested pass and return {pass: image}."""
    objects = targets(objects)
    if not objects:
        raise BakeError(_("Nothing selected"))
    if any(not obj.material_slots or not any(s.material for s in obj.material_slots)
           for obj in objects):
        raise BakeError(_("Every object needs at least one material to bake"))

    results = {}
    with _render_settings(context, samples):
        for kind, suffix, role, is_data, fill in PASSES:
            if kind not in wanted:
                continue
            image = _new_image(base_name + suffix, resolution, is_data, fill)
            nodes = _attach_target(objects, image)
            try:
                _bake(context, objects, kind, margin)
            finally:
                _detach(nodes)
            textures.set_stored_role(image, role)
            results[kind] = image
    return results


def _new_image(name, resolution, is_data, fill):
    existing = bpy.data.images.get(name)
    if existing is not None:
        bpy.data.images.remove(existing)
    image = bpy.data.images.new(
        name, resolution, resolution, alpha=True, float_buffer=False,
        is_data=is_data,
    )
    pixels = imaging.solid(resolution, resolution, fill)
    image.pixels.foreach_set(pixels.reshape(-1))
    image.update()
    return image


def _attach_target(objects, image):
    """Every material needs an active image node pointing at the target."""
    created = []
    seen = set()
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.name in seen:
                continue
            seen.add(material.name)
            if not material.use_nodes:
                material.use_nodes = True
            node = material.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            node.select = True
            node.label = "ParaForge bake target"
            material.node_tree.nodes.active = node
            created.append((material, node))
    return created


def _detach(nodes):
    for material, node in nodes:
        try:
            material.node_tree.nodes.remove(node)
        except (ReferenceError, RuntimeError):
            pass


def _bake(context, objects, kind, margin):
    settings = {
        "type": kind,
        # Never clear: the neutral fill put there by _new_image is what the
        # unreached pixels must keep.
        "use_clear": False,
        "margin": margin,
        "use_selected_to_active": False,
    }
    if kind == "DIFFUSE":
        # Colour only. Lighting baked into the albedo would be baked twice
        # once the game lights the item.
        settings["pass_filter"] = {"COLOR"}

    with _selection(context, objects):
        try:
            bpy.ops.object.bake(**settings)
        except RuntimeError as error:
            raise BakeError("{0}: {1}".format(kind, error))


# --------------------------------------------------------------------------
# The single material that replaces everything


def build_material(name, images):
    """One Principled BSDF fed by the baked maps, so the viewport agrees."""
    material = bpy.data.materials.get(name)
    if material is not None:
        bpy.data.materials.remove(material)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    principled = nodes.get("Principled BSDF")

    def image_node(image, x, y):
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        node.location = (x, y)
        return node

    if "DIFFUSE" in images:
        node = image_node(images["DIFFUSE"], -600, 300)
        links.new(node.outputs["Color"], principled.inputs["Base Color"])
    if "ROUGHNESS" in images:
        node = image_node(images["ROUGHNESS"], -600, 0)
        links.new(node.outputs["Color"], principled.inputs["Roughness"])
    if "NORMAL" in images:
        node = image_node(images["NORMAL"], -600, -300)
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-300, -300)
        links.new(node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    if "AO" in images:
        # Nothing on the BSDF reads occlusion, but the image has to stay in
        # the graph for the export plan to find it.
        node = image_node(images["AO"], -600, -600)
        node.label = "Occlusion"
    return material


def replace_materials(objects, material):
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(material)


# --------------------------------------------------------------------------
# Borrowed state, always given back


class _selection:
    """Make exactly these objects the selection, then restore what was there."""

    def __init__(self, context, objects):
        self.context = context
        self.objects = objects
        self.previous = []
        self.active = None

    def __enter__(self):
        view_layer = self.context.view_layer
        self.previous = list(self.context.selected_objects)
        self.active = view_layer.objects.active
        if self.context.object is not None and self.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in self.previous:
            obj.select_set(False)
        for obj in self.objects:
            obj.select_set(True)
        view_layer.objects.active = self.objects[0]
        return self

    def __exit__(self, *exc):
        view_layer = self.context.view_layer
        for obj in self.context.selected_objects:
            obj.select_set(False)
        for obj in self.previous:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        try:
            view_layer.objects.active = self.active
        except (ReferenceError, AttributeError):
            pass
        return False


class _render_settings:
    """Baking needs Cycles. The scene gets it back exactly as it was."""

    KEYS = ("samples", "use_denoising", "bake_type")

    def __init__(self, context, samples):
        self.context = context
        self.samples = samples
        self.previous = {}

    def __enter__(self):
        scene = self.context.scene
        self.previous["engine"] = scene.render.engine
        scene.render.engine = "CYCLES"
        cycles = getattr(scene, "cycles", None)
        if cycles is not None:
            for key in self.KEYS:
                if hasattr(cycles, key):
                    self.previous[key] = getattr(cycles, key)
            cycles.samples = self.samples
            if hasattr(cycles, "use_denoising"):
                cycles.use_denoising = False
        return self

    def __exit__(self, *exc):
        scene = self.context.scene
        cycles = getattr(scene, "cycles", None)
        if cycles is not None:
            for key in self.KEYS:
                if key in self.previous:
                    try:
                        setattr(cycles, key, self.previous[key])
                    except (AttributeError, TypeError):
                        pass
        try:
            scene.render.engine = self.previous["engine"]
        except (TypeError, KeyError):
            pass
        return False
