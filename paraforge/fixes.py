# SPDX-License-Identifier: GPL-3.0-or-later
"""One button per failed check.

Fixes are deliberately explicit. Nothing is silently corrected at export time,
so what you see in the viewport is exactly what lands in the mod folder.
"""

import numpy as np

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import cache, geo, i18n, props, spec, textures, util, validate

_ = i18n.t


def _targets(context):
    return validate.target_objects(context)


def _multi_user(objects):
    return [o.name for o in objects if o.data and o.data.users > 1]


# --------------------------------------------------------------------------


class PARAFORGE_OT_fix_units(Operator):
    bl_idname = "paraforge.fix_units"
    bl_label = _("Set unit scale to 1.0")
    bl_description = _("Paralives works in metres at scale 1.0")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        unit = context.scene.unit_settings
        unit.system = "METRIC"
        unit.scale_length = 1.0
        cache.invalidate()
        self.report({"INFO"}, _("Unit scale set to 1.0"))
        return {"FINISHED"}


class PARAFORGE_OT_fix_transforms(Operator):
    bl_idname = "paraforge.fix_transforms"
    bl_label = _("Apply rotation and scale")
    bl_description = _(
        "Bake rotation and scale into the mesh data. Without this the item "
        "arrives in game at the wrong angle or size"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        shared = _multi_user(objects)
        if shared:
            self.report(
                {"ERROR"},
                _("Mesh data is shared with another object: ")
                + ", ".join(shared[:3]) + _(". Make it single user first"),
            )
            return {"CANCELLED"}

        if not apply_transforms(context, objects):
            self.report({"ERROR"}, _("Blender refused to apply the transforms"))
            return {"CANCELLED"}

        cache.invalidate()
        self.report({"INFO"}, _("Rotation and scale applied"))
        return {"FINISHED"}


def apply_transforms(context, objects, location=True):
    """Apply loc/rot/scale so that local space equals world space."""
    if not objects:
        return False
    try:
        with context.temp_override(
            active_object=objects[0],
            object=objects[0],
            selected_objects=objects,
            selected_editable_objects=objects,
        ):
            bpy.ops.object.transform_apply(
                location=location, rotation=True, scale=True, properties=False
            )
    except (RuntimeError, TypeError) as error:
        print("[ParaForge] transform_apply failed:", error)
        return False
    return True


class PARAFORGE_OT_fix_origin(Operator):
    bl_idname = "paraforge.fix_origin"
    bl_label = _("Snap origin")
    bl_description = _(
        "Move the geometry so the origin follows the Paralives rule for this "
        "item type"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = props.settings(context)
        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        shared = _multi_user(objects)
        if shared:
            self.report(
                {"ERROR"},
                _("Mesh data is shared with another object: ")
                + ", ".join(shared[:3]),
            )
            return {"CANCELLED"}

        # Local space has to equal world space before the offset means anything.
        if not apply_transforms(context, objects):
            self.report({"ERROR"}, _("Could not apply transforms first"))
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()
        measurement = geo.measure(objects, depsgraph)
        if measurement.empty:
            self.report({"ERROR"}, _("No geometry to measure"))
            return {"CANCELLED"}

        offsets = geo.anchor_offsets(measurement, settings.item_type)

        # This is the way back from an origin placed by hand, so it clears the
        # mark too. Leaving it set would move the geometry to the rule and go
        # on claiming the origin was chosen, which is the checklist describing
        # something that is no longer true.
        settings.keep_origin = False

        if all(abs(value) <= spec.POSITION_TOLERANCE for value in offsets):
            self.report({"INFO"}, _("Origin already correct"))
            return {"FINISHED"}

        delta = np.array(offsets, dtype=np.float64)
        for obj in objects:
            translate_mesh(obj.data, delta)
            obj.data.update()

        cache.invalidate()
        self.report(
            {"INFO"},
            _("Geometry moved by ({0:+.4f}, {1:+.4f}, {2:+.4f}) m", *offsets),
        )
        return {"FINISHED"}


def translate_mesh(mesh, delta):
    """Shift every vertex of a mesh datablock, in place."""
    count = len(mesh.vertices)
    if count == 0:
        return
    flat = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", flat)
    flat.reshape(count, 3)[:] += delta
    mesh.vertices.foreach_set("co", flat)


class PARAFORGE_OT_confirm_facing(Operator):
    bl_idname = "paraforge.confirm_facing"
    bl_label = _("Confirm the item faces Y+")
    bl_description = _(
        "There is no reliable way to detect the front of a mesh. Compare the "
        "item with the green arrow in the viewport, then confirm"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = props.settings(context)
        settings.facing_confirmed = True
        cache.invalidate()
        return {"FINISHED"}


class PARAFORGE_OT_rotate_to_face(Operator):
    bl_idname = "paraforge.rotate_to_face"
    bl_label = _("Rotate")
    bl_description = _(
        "Turn the geometry around Z and re-check. The rotation is baked "
        "into the mesh, not left on the object, because the game reads "
        "the vertices and ignores the node"
    )
    bl_options = {"REGISTER", "UNDO"}

    steps: EnumProperty(
        name=_("Rotation"),
        items=(
            ("45", "45", _("Eighth turn counter clockwise")),
            ("90", "90", _("Quarter turn counter clockwise")),
            ("180", "180", _("Half turn")),
            ("270", "270", _("Quarter turn clockwise")),
            ("315", "-45", _("Eighth turn clockwise")),
        ),
        default="90",
    )

    def execute(self, context):
        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        angle = np.radians(float(self.steps))
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        rotation = np.array(
            [[cos_a, -sin_a, 0.0], [sin_a, cos_a, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

        if not apply_transforms(context, objects):
            self.report({"ERROR"}, _("Could not apply transforms first"))
            return {"CANCELLED"}

        for obj in objects:
            mesh = obj.data
            count = len(mesh.vertices)
            if count == 0:
                continue
            flat = np.empty(count * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", flat)
            coords = flat.reshape(count, 3)
            coords[:] = coords @ rotation.T
            mesh.vertices.foreach_set("co", flat)
            mesh.update()

        settings = props.settings(context)
        settings.facing_confirmed = False
        cache.invalidate()
        self.report({"INFO"}, _("Rotated by {0} degrees", self.steps))
        return {"FINISHED"}


class PARAFORGE_OT_fix_add_color_attribute(Operator):
    bl_idname = "paraforge.fix_add_color_attribute"
    bl_label = _("Create colour attribute")
    bl_description = _(
        "Add a colour attribute filled with zone 0 (white) so the item has a "
        "valid single zone to start from"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = _targets(context)
        touched = 0
        for obj in objects:
            mesh = obj.data
            attributes = mesh.color_attributes
            if len(attributes):
                continue
            attribute = attributes.new(name="Color", type="BYTE_COLOR", domain="CORNER")
            count = len(attribute.data)
            if count:
                flat = np.ones(count * 4, dtype=np.float32)
                attribute.data.foreach_set("color", flat)
            attributes.active_color = attribute
            try:
                attributes.render_color_index = 0
            except (AttributeError, TypeError):
                pass
            mesh.update()
            touched += 1

        cache.invalidate()
        if not touched:
            self.report({"INFO"}, _("Every object already has a colour attribute"))
        else:
            self.report({"INFO"}, _("Zone 0 created on {0} object(s)", touched))
        return {"FINISHED"}


class PARAFORGE_OT_fix_snap_colors(Operator):
    bl_idname = "paraforge.fix_snap_colors"
    bl_label = _("Snap colours to the nearest zone")
    bl_description = _(
        "Round every vertex colour to the nearest legal Paralives zone. "
        "Anything the game cannot read becomes the closest zone it can"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        legal = np.array(
            [spec.ZONE_COLORS[i][0] for i in sorted(spec.ZONE_COLORS)]
            + [spec.DECAL_COLOR],
            dtype=np.float64,
        )

        changed = 0
        for obj in _targets(context):
            mesh = obj.data
            attributes = getattr(mesh, "color_attributes", None)
            if not attributes or not len(attributes):
                continue
            attribute = attributes.active_color or attributes[0]
            count = len(attribute.data)
            if not count:
                continue

            flat = np.empty(count * 4, dtype=np.float64)
            attribute.data.foreach_get("color", flat)
            colors = flat.reshape(count, 4)

            distances = np.linalg.norm(
                colors[:, None, :3] - legal[None, :, :], axis=2
            )
            nearest = legal[np.argmin(distances, axis=1)]
            moved = int(np.count_nonzero(np.any(colors[:, :3] != nearest, axis=1)))
            if moved:
                colors[:, :3] = nearest
                attribute.data.foreach_set("color", flat)
                mesh.update()
                changed += moved

        cache.invalidate()
        self.report({"INFO"}, _("{0} colour value(s) snapped", changed))
        return {"FINISHED"}


# --------------------------------------------------------------------------
# Texture roles


# Blender frees the strings a dynamic enum callback returns, so they have to
# outlive the call.
_ROLE_ITEMS = []


def _role_items(self, context):
    _ROLE_ITEMS.clear()
    for key, label, description in spec.SOURCE_ROLES:
        if key == spec.PARALIVES:
            continue
        _ROLE_ITEMS.append((key, _(label), _(description)))
    return _ROLE_ITEMS


class PARAFORGE_OT_detect_roles(Operator):
    bl_idname = "paraforge.detect_roles"
    bl_label = _("Auto-detect")
    bl_description = _(
        "Work out what every texture is from the shader graph, the file name "
        "and the pixels, then remember it. A GLB downloaded from the web "
        "arrives with its images called Image_0 and Image_1, so what they are "
        "wired to is the only reliable clue"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        known = 0
        unknown = 0
        for _material, sources in textures.gather(objects):
            for source in sources:
                if source.evidence == textures.FROM_USER:
                    continue
                if source.known and source.role != spec.PARALIVES:
                    textures.set_stored_role(source.image, source.role)
                    known += 1
                elif not source.known:
                    unknown += 1

        cache.invalidate()
        if not known and not unknown:
            self.report({"INFO"}, _("Nothing to detect"))
            return {"CANCELLED"}
        self.report(
            {"INFO"}, _("{0} image(s) identified, {1} left unknown", known, unknown)
        )
        return {"FINISHED"}


class PARAFORGE_OT_set_texture_role(Operator):
    bl_idname = "paraforge.set_texture_role"
    bl_label = _("Set the role by hand")
    bl_description = _(
        "Tell ParaForge what this image is, so it can be folded into the "
        "right Paralives map"
    )
    bl_options = {"REGISTER", "UNDO"}

    image: StringProperty(name="Image", options={"HIDDEN"})

    role: EnumProperty(name=_("Role"), items=_role_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.image, icon="IMAGE_DATA")
        layout.prop(self, "role")
        layout.separator()
        box = layout.box()
        box.scale_y = 0.8
        description = next(
            (d for key, _label, d in spec.SOURCE_ROLES if key == self.role), ""
        )
        for line in util.wrap(_(description), 56):
            box.label(text=line)

    def execute(self, context):
        image = bpy.data.images.get(self.image)
        if image is None:
            self.report({"ERROR"}, _("Image not found: ") + self.image)
            return {"CANCELLED"}

        textures.set_stored_role(image, self.role)
        cache.invalidate()
        self.report({"INFO"}, _("Role set to ") + _(spec.role_label(self.role)))
        return {"FINISHED"}


# --------------------------------------------------------------------------
# Topology


class PARAFORGE_OT_decimate_to_budget(Operator):
    bl_idname = "paraforge.decimate_to_budget"
    bl_label = _("Reduce to the budget")
    bl_description = _(
        "Collapse edges until the mesh fits the triangle budget. Downloaded "
        "and generated assets routinely arrive at half a million triangles, "
        "which no furniture item needs"
    )
    bl_options = {"REGISTER", "UNDO"}

    budget: IntProperty(
        name=_("Triangle budget"), default=spec.DEFAULT_TRIANGLE_BUDGET,
        min=100, soft_max=200000, options={"SKIP_SAVE"},
    )

    rebake: BoolProperty(
        name=_("Bake the look back onto it"),
        description=_(
            "Collapsing edges throws the UVs out of shape, which is why the "
            "texture seems to disappear. This unwraps the reduced mesh and "
            "bakes the original's colour, relief and roughness onto it"
        ),
        default=True,
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, event):
        settings = props.settings(context)
        if settings is not None:
            self.budget = settings.triangle_budget
            self.rebake = settings.decimate_rebake
        return self.execute(context)

    def execute(self, context):
        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()
        before = geo.measure(objects, depsgraph).triangles
        if before <= self.budget:
            self.report({"INFO"}, _("Already under the budget"))
            return {"CANCELLED"}

        # A copy of the original has to survive the decimation, or there is
        # nothing left to bake the look from.
        keepers = []
        if self.rebake:
            keepers = _duplicate_for_bake(context, objects)

        ratio = max(min(float(self.budget) / float(before), 1.0), 0.01)
        # Edit mode refuses modifier_apply outright, which turned this button
        # into one that reported a warning and changed nothing.
        with util.object_mode(context):
            for obj in objects:
                modifier = obj.modifiers.new("ParaForge Decimate", "DECIMATE")
                modifier.decimate_type = "COLLAPSE"
                modifier.ratio = ratio
                modifier.use_collapse_triangulate = True
                try:
                    with context.temp_override(object=obj, active_object=obj):
                        bpy.ops.object.modifier_apply(modifier=modifier.name)
                except RuntimeError as error:
                    obj.modifiers.remove(modifier)
                    self.report({"WARNING"},
                                "{0}: {1}".format(obj.name, error))

        cache.invalidate()
        depsgraph = context.evaluated_depsgraph_get()
        after = geo.measure(objects, depsgraph).triangles

        baked = ""
        if keepers:
            try:
                baked = _rebake_from(context, objects, keepers)
            except Exception as error:
                self.report({"WARNING"}, _("Could not bake it back: {0}", error))
            finally:
                _discard(keepers)
            cache.invalidate()

        self.report({"INFO"},
                    _("{0} triangles, down from {1}", after, before) + baked)
        return {"FINISHED"}


class PARAFORGE_OT_remesh(Operator):
    bl_idname = "paraforge.remesh"
    bl_label = _("Remesh")
    bl_description = _(
        "Throw the topology away and lay an even surface over the volume, "
        "then bake the original's look onto it. Where collapsing edges tears "
        "an organic asset apart long before it reaches a furniture budget, "
        "this rebuilds it instead"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import remesh

        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        settings = props.settings(context)
        rebake = getattr(settings, "remesh_rebake", True)

        depsgraph = context.evaluated_depsgraph_get()
        before = geo.measure(objects, depsgraph).triangles

        # The original has to outlive the remesh, or there is nothing left to
        # bake the look from and the object stays bare.
        keepers = _duplicate_for_bake(context, objects) if rebake else []

        try:
            failed = remesh.apply_to(
                context, objects,
                mode=settings.remesh_mode,
                octree_depth=settings.remesh_octree_depth,
                scale=settings.remesh_scale,
                sharpness=settings.remesh_sharpness,
                threshold=settings.remesh_threshold,
                voxel_size=settings.remesh_voxel_size,
                adaptivity=settings.remesh_adaptivity,
                remove_disconnected=settings.remesh_remove_disconnected,
                smooth_shading=settings.remesh_smooth_shading,
            )
        except Exception as error:
            _discard(keepers)
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        for message in failed:
            self.report({"WARNING"}, message)

        cache.invalidate()
        depsgraph = context.evaluated_depsgraph_get()
        after = geo.measure(objects, depsgraph).triangles

        baked = ""
        if keepers:
            try:
                baked = _rebake_from(context, objects, keepers)
            except Exception as error:
                # Say it plainly. A silent failure here leaves an object with
                # no UVs and no texture, which reads as a broken remesh.
                self.report({"WARNING"}, _(
                    "Remeshed, but the look could not be baked back, so the "
                    "object has no texture: {0}", error))
            finally:
                _discard(keepers)
            cache.invalidate()
        elif not failed:
            self.report({"WARNING"}, _(
                "Remeshing keeps no UV map, so the object is bare until "
                "something is baked onto it"))

        self.report({"INFO"},
                    _("{0} triangles, was {1}", after, before) + baked)
        return {"FINISHED"}


def _duplicate_for_bake(context, objects):
    """Copies of the originals, hidden away, to bake the look from."""
    copies = []
    for obj in objects:
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.name = obj.name + "_ParaForgeOriginal"
        context.scene.collection.objects.link(copy)
        copy.hide_set(True)
        copies.append(copy)
    return copies


def _discard(objects):
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


def _rebake_from(context, objects, sources):
    """Unwrap the reduced mesh and bake the originals onto it."""
    from . import bake

    for obj in sources:
        obj.hide_set(False)

    name = objects[0].name
    bake.repack_uvs(context, objects, name="ParaForgeUV")
    images = bake.bake_all(
        context, objects, textures.pascal_case(name),
        wanted=("DIFFUSE", "NORMAL", "ROUGHNESS", "AO"),
        sources=sources,
    )
    material = bake.build_material(textures.pascal_case(name) + "Baked", images)
    bake.replace_materials(objects, material)
    return _(", texture baked back onto it")


class PARAFORGE_OT_downscale_textures(Operator):
    bl_idname = "paraforge.downscale_textures"
    bl_label = _("Downscale the textures")
    bl_description = _(
        "Halve oversized textures until they fit. Paralives ships 256 to "
        "1024 px maps and nothing above 2048, so a 4K download is four times "
        "the largest texture in the game for no visible gain"
    )
    bl_options = {"REGISTER", "UNDO"}

    limit: IntProperty(
        name=_("Longest side"), default=spec.MAX_SENSIBLE_TEXTURE_SIZE,
        min=64, max=8192,
    )

    def execute(self, context):
        from . import imaging

        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        touched = []
        for _material, sources in textures.gather(objects):
            for source in sources:
                image = source.image
                width, height = imaging.dimensions(image)
                if max(width, height) <= self.limit:
                    continue
                ratio = self.limit / float(max(width, height))
                image.scale(max(1, int(width * ratio)), max(1, int(height * ratio)))
                touched.append(source.stem)

        cache.invalidate()
        if not touched:
            self.report({"INFO"}, _("Every texture already fits"))
            return {"CANCELLED"}
        self.report({"INFO"}, _("{0} texture(s) downscaled to {1} px",
                                len(touched), self.limit))
        return {"FINISHED"}


class PARAFORGE_OT_bake_to_atlas(Operator):
    bl_idname = "paraforge.bake_to_atlas"
    bl_label = _("Bake into one surface")
    bl_description = _(
        "Repack the UVs of the whole selection into one atlas, bake every "
        "material into a single set of maps, and replace them with it. This "
        "is the way out for a downloaded asset split into five or ten "
        "materials, because Paralives assigns one surface per mesh. It uses "
        "Cycles and takes a while"
    )
    bl_options = {"REGISTER", "UNDO"}

    resolution: EnumProperty(
        name=_("Resolution"),
        items=(("1024", "1024", ""), ("2048", "2048", ""), ("4096", "4096", "")),
        default="2048",
    )

    samples: IntProperty(
        name=_("Samples"),
        description=_(
            "Only the occlusion pass is noisy, the others are exact whatever "
            "this is set to"
        ),
        default=16, min=1, max=512,
    )

    bake_normal: BoolProperty(name=_("Normal map"), default=True)
    bake_roughness: BoolProperty(name=_("Roughness"), default=True)
    bake_occlusion: BoolProperty(name=_("Ambient occlusion"), default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "resolution")
        layout.prop(self, "samples")
        column = layout.column(align=True)
        column.prop(self, "bake_normal")
        column.prop(self, "bake_roughness")
        column.prop(self, "bake_occlusion")
        box = layout.box()
        box.scale_y = 0.8
        for line in util.wrap(_(
            "The materials of the selection are replaced by a single one. "
            "The look is preserved, the UVs are not: they are repacked into "
            "one atlas"
        ), 56):
            box.label(text=line)

    def execute(self, context):
        from . import bake

        objects = bake.targets(_targets(context))
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        settings = props.settings(context)
        base = textures.pascal_case(
            settings.asset_name or objects[0].name
        )

        wanted = ["DIFFUSE"]
        if self.bake_normal:
            wanted.append("NORMAL")
        if self.bake_roughness:
            wanted.append("ROUGHNESS")
        if self.bake_occlusion:
            wanted.append("AO")

        try:
            bake.repack_uvs(context, objects)
            images = bake.bake_all(
                context, objects, base, int(self.resolution), self.samples,
                wanted,
            )
        except bake.BakeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        material = bake.build_material(base + "Paralives", images)
        bake.replace_materials(objects, material)

        cache.invalidate()
        self.report(
            {"INFO"},
            _("{0} map(s) baked into one surface at {1} px",
              len(images), self.resolution),
        )
        return {"FINISHED"}


# --------------------------------------------------------------------------


class PARAFORGE_OT_fix_all(Operator):
    bl_idname = "paraforge.fix_all"
    bl_label = _("Fix everything safe")
    bl_description = _(
        "Run every fix that cannot lose work: unit scale, transforms, origin, "
        "missing colour attribute, illegal colours and texture roles. Facing "
        "and triangle reduction still need you"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = props.settings(context)
        report = cache.get(context, settings, force=True)
        applied = []

        wanted = {check.fix for check in report.fixable()}
        order = (
            ("paraforge.fix_units", bpy.ops.paraforge.fix_units),
            ("paraforge.fix_transforms", bpy.ops.paraforge.fix_transforms),
            ("paraforge.fix_add_color_attribute", bpy.ops.paraforge.fix_add_color_attribute),
            ("paraforge.fix_snap_colors", bpy.ops.paraforge.fix_snap_colors),
            ("paraforge.detect_roles", bpy.ops.paraforge.detect_roles),
            ("paraforge.fix_origin", bpy.ops.paraforge.fix_origin),
        )

        for idname, operator in order:
            if idname not in wanted:
                continue
            try:
                result = operator()
            except RuntimeError as error:
                self.report({"WARNING"}, "{0}: {1}".format(idname, error))
                continue
            if "FINISHED" in result:
                applied.append(idname.rpartition(".")[2])

        cache.invalidate()
        if not applied:
            self.report({"INFO"}, _("Nothing left that can be fixed automatically"))
        else:
            self.report({"INFO"}, _("Applied: ") + ", ".join(applied))
        return {"FINISHED"}



class PARAFORGE_OT_origin_to_cursor(Operator):
    bl_idname = "paraforge.origin_to_cursor"
    bl_label = _("Origin to the 3D cursor")
    bl_description = _(
        "Move the geometry so the 3D cursor becomes the item's origin. Place "
        "the cursor where the item should hang from, then press this. The "
        "origin is where the game anchors the item when it is placed"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = _targets(context)
        if not objects:
            self.report({"ERROR"}, _("Nothing selected"))
            return {"CANCELLED"}

        shared = _multi_user(objects)
        if shared:
            self.report(
                {"ERROR"},
                _("Mesh data is shared with another object: ")
                + ", ".join(shared[:3]),
            )
            return {"CANCELLED"}

        if not apply_transforms(context, objects):
            self.report({"ERROR"}, _("Could not apply transforms first"))
            return {"CANCELLED"}

        cursor = context.scene.cursor.location
        delta = -np.array([cursor[0], cursor[1], cursor[2]], dtype=np.float64)
        if np.all(np.abs(delta) <= spec.POSITION_TOLERANCE):
            self.report({"INFO"}, _("The cursor is already at the origin"))
            return {"FINISHED"}

        for obj in objects:
            translate_mesh(obj.data, delta)
            obj.data.update()

        # Placed by hand on purpose, so the checklist stops asking for the
        # rule it was just overridden with.
        settings = props.settings(context)
        if settings is not None:
            settings.keep_origin = True

        cache.invalidate()
        self.report(
            {"INFO"},
            _("Geometry moved by ({0:+.4f}, {1:+.4f}, {2:+.4f}) m", *delta),
        )
        return {"FINISHED"}

classes = (
    PARAFORGE_OT_fix_units,
    PARAFORGE_OT_fix_transforms,
    PARAFORGE_OT_fix_origin,
    PARAFORGE_OT_origin_to_cursor,
    PARAFORGE_OT_confirm_facing,
    PARAFORGE_OT_rotate_to_face,
    PARAFORGE_OT_fix_add_color_attribute,
    PARAFORGE_OT_fix_snap_colors,
    PARAFORGE_OT_detect_roles,
    PARAFORGE_OT_set_texture_role,
    PARAFORGE_OT_decimate_to_budget,
    PARAFORGE_OT_remesh,
    PARAFORGE_OT_downscale_textures,
    PARAFORGE_OT_bake_to_atlas,
    PARAFORGE_OT_fix_all,
)
