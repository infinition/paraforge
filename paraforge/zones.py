# SPDX-License-Identifier: GPL-3.0-or-later
"""Colour zone authoring.

Paralives reads four recolourable zones from vertex colours, plus yellow for
decals. Painting those by hand in Blender is slow and easy to get wrong, and
an asset that arrives without them (a generated mesh, a marketplace model, a
photogrammetry scan) has none at all.

Three ways in, from fastest to most precise:

  1. Select faces, click a zone. The obvious one.
  2. One material per zone. Most imported assets already split that way.
  3. Pick a colour off the texture and grow it by tolerance. This is the one
     that rescues an asset which only has a single baked texture.

The picker samples the texture through a raycast rather than reading screen
pixels, so viewport lighting never shifts the result.
"""

import numpy as np

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, StringProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils.interpolate import poly_3d_calc

from . import cache, i18n, spec, validate

_ = i18n.t

ATTRIBUTE_NAME = "Color"

ZONE_ITEMS = (
    ("0", "Zone 0", _("White. Usually carries the Detail map"), "", 0),
    ("1", "Zone 1", _("Red"), "", 1),
    ("2", "Zone 2", _("Green"), "", 2),
    ("3", "Zone 3", _("Blue"), "", 3),
    ("decal", _("Decal"), _("Yellow. Never recolourable"), "", 4),
)


def zone_rgb(key):
    if key == "decal":
        return spec.DECAL_COLOR
    return spec.ZONE_COLORS[int(key)][0]


# --------------------------------------------------------------------------
# Attribute plumbing


def ensure_attribute(mesh):
    """Return a colour attribute, creating a white CORNER one when missing."""
    attributes = mesh.color_attributes
    if len(attributes):
        return attributes.active_color or attributes[0]

    attribute = attributes.new(name=ATTRIBUTE_NAME, type="BYTE_COLOR", domain="CORNER")
    count = len(attribute.data)
    if count:
        attribute.data.foreach_set("color", np.ones(count * 4, dtype=np.float32))
    attributes.active_color = attribute
    try:
        attributes.render_color_index = 0
    except (AttributeError, TypeError):
        pass
    return attribute


def read_colors(attribute):
    count = len(attribute.data)
    flat = np.empty(count * 4, dtype=np.float32)
    attribute.data.foreach_get("color", flat)
    return flat.reshape(count, 4)


def write_colors(mesh, attribute, colors):
    attribute.data.foreach_set("color", colors.reshape(-1))
    mesh.update()


def loop_to_element(mesh, attribute):
    """Map every loop index onto the attribute element it writes to."""
    if attribute.domain == "CORNER":
        return np.arange(len(mesh.loops), dtype=np.int64)
    vertex_index = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", vertex_index)
    return vertex_index


def polygon_loops(mesh):
    """(loop_start, loop_total) arrays for every polygon."""
    count = len(mesh.polygons)
    starts = np.empty(count, dtype=np.int64)
    totals = np.empty(count, dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    return starts, totals


def loops_of_polygons(mesh, mask):
    """Loop indices belonging to the polygons flagged in mask."""
    starts, totals = polygon_loops(mesh)
    selected = np.nonzero(mask)[0]
    if not len(selected):
        return np.empty(0, dtype=np.int64)
    return np.concatenate(
        [np.arange(starts[i], starts[i] + totals[i], dtype=np.int64) for i in selected]
    )


# --------------------------------------------------------------------------
# UV sampling


def loop_uvs(mesh):
    """Per loop UV coordinates, or None when the mesh has no UV map."""
    layer = mesh.uv_layers.active
    if layer is None:
        return None
    count = len(mesh.loops)
    flat = np.empty(count * 2, dtype=np.float32)
    try:
        layer.uv.foreach_get("vector", flat)
    except (AttributeError, TypeError):
        layer.data.foreach_get("uv", flat)
    return flat.reshape(count, 2)


def image_array(image):
    """Image pixels as (height, width, 4), or None."""
    if image is None:
        return None
    width, height = image.size
    if width <= 0 or height <= 0:
        return None
    flat = np.empty(width * height * 4, dtype=np.float32)
    try:
        image.pixels.foreach_get(flat)
    except (AttributeError, TypeError):
        flat = np.array(image.pixels[:], dtype=np.float32)
    if flat.size != width * height * 4:
        return None
    return flat.reshape(height, width, 4)


def sample(pixels, uvs):
    """Nearest neighbour texture lookup for an array of UVs."""
    height, width = pixels.shape[0], pixels.shape[1]
    u = np.mod(uvs[:, 0], 1.0)
    v = np.mod(uvs[:, 1], 1.0)
    x = np.clip((u * width).astype(np.int64), 0, width - 1)
    y = np.clip((v * height).astype(np.int64), 0, height - 1)
    return pixels[y, x, :3]


def sample_one(pixels, uv):
    return sample(pixels, np.array([uv], dtype=np.float32))[0]


def default_image(obj):
    """The most likely texture to sample: base colour, else the first found."""
    best = None
    for slot in getattr(obj, "material_slots", []):
        material = slot.material
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.bl_idname != "ShaderNodeTexImage" or node.image is None:
                continue
            if best is None:
                best = node.image
            for output in node.outputs:
                for link in output.links:
                    if link.to_socket.name in {"Base Color", "Color"}:
                        return node.image
    return best


def resolve_image(context, settings, obj):
    name = (settings.zone_image or "").strip()
    if name:
        image = bpy.data.images.get(name)
        if image is not None:
            return image
    return default_image(obj)


# --------------------------------------------------------------------------
# Operators


class PARAFORGE_OT_assign_zone(Operator):
    bl_idname = "paraforge.assign_zone"
    bl_label = _("Assign zone")
    bl_description = _("Paint the selected faces with a Paralives colour zone")
    bl_options = {"REGISTER", "UNDO"}

    zone: EnumProperty(name=_("Zone"), items=ZONE_ITEMS, default="1")

    whole_mesh: BoolProperty(
        name=_("Whole mesh"),
        description=_("Ignore the selection and paint everything"),
        default=False,
    )

    def execute(self, context):
        objects = validate.target_objects(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        rgb = zone_rgb(self.zone)
        painted = 0

        with _object_mode(context):
            for obj in objects:
                mesh = obj.data
                attribute = ensure_attribute(mesh)
                colors = read_colors(attribute)
                mapping = loop_to_element(mesh, attribute)

                if self.whole_mesh:
                    targets = mapping
                else:
                    selected = np.empty(len(mesh.polygons), dtype=bool)
                    mesh.polygons.foreach_get("select", selected)
                    if not selected.any():
                        continue
                    targets = mapping[loops_of_polygons(mesh, selected)]

                if not len(targets):
                    continue
                colors[targets, :3] = rgb
                write_colors(mesh, attribute, colors)
                painted += len(targets)

        cache.invalidate()
        if not painted:
            self.report(
                {"WARNING"},
                _("No face selected. Select faces in Edit Mode first"),
            )
            return {"CANCELLED"}
        self.report({"INFO"}, _("{0} corner(s) set to {1}", painted, self.zone))
        return {"FINISHED"}


class PARAFORGE_OT_zones_from_materials(Operator):
    bl_idname = "paraforge.zones_from_materials"
    bl_label = _("Zones from materials")
    bl_description = _(
        "Turn each material slot into a colour zone. The fastest route for an "
        "imported or generated asset that already has separate materials"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = validate.target_objects(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        slot_count = max((len(o.material_slots) for o in objects), default=0)
        if slot_count == 0:
            self.report({"ERROR"}, _("No material slot to map"))
            return {"CANCELLED"}
        if slot_count > spec.MAX_COLOR_ZONES:
            self.report(
                {"WARNING"},
                _("{0} materials for {1} zones. The extra ones fall back to "
                  "zone {1}", slot_count, spec.MAX_COLOR_ZONES),
            )

        with _object_mode(context):
            for obj in objects:
                mesh = obj.data
                if not len(mesh.polygons):
                    continue
                attribute = ensure_attribute(mesh)
                colors = read_colors(attribute)
                mapping = loop_to_element(mesh, attribute)

                indices = np.empty(len(mesh.polygons), dtype=np.int64)
                mesh.polygons.foreach_get("material_index", indices)
                starts, totals = polygon_loops(mesh)

                for slot in range(max(indices) + 1):
                    zone = min(slot, spec.MAX_COLOR_ZONES - 1)
                    faces = np.nonzero(indices == slot)[0]
                    if not len(faces):
                        continue
                    loops = np.concatenate(
                        [np.arange(starts[i], starts[i] + totals[i]) for i in faces]
                    )
                    colors[mapping[loops], :3] = spec.ZONE_COLORS[zone][0]

                write_colors(mesh, attribute, colors)

        cache.invalidate()
        self.report({"INFO"}, _("{0} material slot(s) mapped to zones", slot_count))
        return {"FINISHED"}


class PARAFORGE_OT_pick_zone_color(Operator):
    bl_idname = "paraforge.pick_zone_color"
    bl_label = _("Pick a colour on the model")
    bl_description = _(
        "Click the model to read the texture colour under the cursor. The "
        "texture is sampled directly, so viewport lighting does not shift it"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        context.window.cursor_modal_set("EYEDROPPER")
        context.workspace.status_text_set(_(
            "Click the model to sample its texture   |   Esc or right click "
            "to cancel"
        ))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            result = self._sample(context, event)
            self._finish(context)
            if result is None:
                return {"CANCELLED"}
            return {"FINISHED"}

        return {"RUNNING_MODAL"}

    def _finish(self, context):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)

    def _sample(self, context, event):
        from . import props

        settings = props.settings(context)
        region = context.region
        rv3d = context.region_data
        if region is None or rv3d is None:
            self.report({"ERROR"}, _("No 3D view under the cursor"))
            return None

        coord = (event.mouse_region_x, event.mouse_region_y)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

        depsgraph = context.evaluated_depsgraph_get()
        hit, location, _normal, index, obj, matrix = context.scene.ray_cast(
            depsgraph, origin, direction
        )
        if not hit or obj is None or obj.type != "MESH":
            self.report({"WARNING"}, _("Nothing under the cursor"))
            return None

        image = resolve_image(context, settings, obj)
        if image is None:
            self.report({"ERROR"}, _("That object has no image texture to sample"))
            return None

        pixels = image_array(image)
        if pixels is None:
            self.report({"ERROR"}, _("Could not read the pixels of ") + image.name)
            return None

        uv = self._uv_at(obj, depsgraph, index, location, matrix)
        if uv is None:
            self.report({"ERROR"}, _("That object has no UV map"))
            return None

        rgb = sample_one(pixels, uv)
        settings.zone_color = tuple(float(v) for v in rgb)
        settings.zone_image = image.name
        self.report(
            {"INFO"},
            _("Sampled {0} at ({1:.3f}, {2:.3f})", image.name, uv[0], uv[1]),
        )
        return rgb

    @staticmethod
    def _uv_at(obj, depsgraph, polygon_index, world_location, matrix):
        """Interpolate the UV coordinate at a point on a polygon."""
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if mesh is None or polygon_index >= len(mesh.polygons):
                return None
            layer = mesh.uv_layers.active
            if layer is None:
                return None

            polygon = mesh.polygons[polygon_index]
            local = matrix.inverted() @ world_location
            corners = [mesh.vertices[v].co for v in polygon.vertices]
            weights = poly_3d_calc(corners, local)

            u = v = 0.0
            for weight, loop_index in zip(weights, polygon.loop_indices):
                try:
                    uv = layer.uv[loop_index].vector
                except (AttributeError, TypeError):
                    uv = layer.data[loop_index].uv
                u += weight * uv[0]
                v += weight * uv[1]
            return np.array([u, v], dtype=np.float32)
        finally:
            evaluated.to_mesh_clear()


class PARAFORGE_OT_zone_from_color(Operator):
    bl_idname = "paraforge.zone_from_color"
    bl_label = _("Grow zone from colour")
    bl_description = _(
        "Assign every part of the mesh whose texture colour is close to the "
        "picked one. Adjust the tolerance in the redo panel to see it change"
    )
    bl_options = {"REGISTER", "UNDO"}

    zone: EnumProperty(name=_("Zone"), items=ZONE_ITEMS, default="1")

    color: FloatVectorProperty(
        name=_("Colour"), subtype="COLOR", size=3, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0),
    )

    tolerance: FloatProperty(
        name=_("Tolerance"),
        description=_(
            "0 matches that exact colour, 1 matches the whole texture"
        ),
        default=0.12, min=0.0, max=1.0, subtype="FACTOR",
    )

    image_name: StringProperty(name=_("Texture"), options={"HIDDEN"})

    rest_to_zone_zero: BoolProperty(
        name=_("Everything else to zone 0"),
        description=_("Reset the rest of the mesh to white before assigning"),
        default=False,
    )

    def execute(self, context):
        objects = validate.target_objects(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        target = np.array(self.color[:3], dtype=np.float32)
        rgb = zone_rgb(self.zone)
        # Normalise so that the slider reads the same whatever the colour.
        threshold = float(self.tolerance) * np.sqrt(3.0)

        matched = 0
        total = 0
        missing_uv = []

        with _object_mode(context):
            for obj in objects:
                mesh = obj.data
                image = bpy.data.images.get(self.image_name) or default_image(obj)
                pixels = image_array(image)
                if pixels is None:
                    continue

                uvs = loop_uvs(mesh)
                if uvs is None:
                    missing_uv.append(obj.name)
                    continue

                colors_at_loop = sample(pixels, uvs)
                distance = np.linalg.norm(colors_at_loop - target, axis=1)
                mask = distance <= threshold

                attribute = ensure_attribute(mesh)
                colors = read_colors(attribute)
                mapping = loop_to_element(mesh, attribute)

                if self.rest_to_zone_zero:
                    colors[:, :3] = spec.ZONE_COLORS[0][0]

                hits = mapping[np.nonzero(mask)[0]]
                if len(hits):
                    colors[hits, :3] = rgb
                write_colors(mesh, attribute, colors)

                matched += int(mask.sum())
                total += len(mask)

        cache.invalidate()

        if missing_uv:
            self.report(
                {"ERROR"},
                _("No UV map on: ") + ", ".join(missing_uv[:3])
                + _(". Unwrap before sampling a texture"),
            )
            return {"CANCELLED"}
        if not total:
            self.report({"ERROR"}, _("No texture to sample. Pick a colour first"))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            _("{0:.1f}% of the surface assigned to zone {1}",
              100.0 * matched / total, self.zone),
        )
        return {"FINISHED"}


class PARAFORGE_OT_clear_zones(Operator):
    bl_idname = "paraforge.clear_zones"
    bl_label = _("Reset to zone 0")
    bl_description = _("Paint the whole mesh white, the single zone default")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = validate.target_objects(context)
        with _object_mode(context):
            for obj in objects:
                mesh = obj.data
                attribute = ensure_attribute(mesh)
                colors = read_colors(attribute)
                colors[:, :3] = spec.ZONE_COLORS[0][0]
                write_colors(mesh, attribute, colors)
        cache.invalidate()
        self.report({"INFO"}, _("Reset to zone 0"))
        return {"FINISHED"}


class _object_mode:
    """Temporarily leave Edit Mode so mesh data is readable and writable."""

    def __init__(self, context):
        self.context = context
        self.previous = None

    def __enter__(self):
        obj = self.context.object
        if obj is not None and obj.mode != "OBJECT":
            self.previous = obj.mode
            bpy.ops.object.mode_set(mode="OBJECT")
        return self

    def __exit__(self, *exc):
        if self.previous:
            try:
                bpy.ops.object.mode_set(mode=self.previous)
            except RuntimeError:
                pass
        return False


classes = (
    PARAFORGE_OT_assign_zone,
    PARAFORGE_OT_zones_from_materials,
    PARAFORGE_OT_pick_zone_color,
    PARAFORGE_OT_zone_from_color,
    PARAFORGE_OT_clear_zones,
)
