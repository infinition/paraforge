# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel.

Text is wrapped against the measured width of the region rather than a fixed
column count, because the sidebar is resizable and a hard coded wrap either
overflows a narrow one or wastes half of a wide one.
"""

import os

import bpy
from bpy.types import Panel

from . import (
    cache, catalog, i18n, item, modfolder, prefs, props, spec, textures,
    util, validate,
)

_ = i18n.t

CATEGORY = "ParaForge"

STATUS_ICONS = {
    validate.OK: "CHECKMARK",
    validate.WARN: "ERROR",
    validate.FAIL: "CANCEL",
    validate.TODO: "QUESTION",
}


class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


def paragraph(layout, context, text, scale=0.72, reserve=6):
    column = layout.column(align=True)
    column.scale_y = scale
    for line in util.wrap_to(context, text, reserve):
        column.label(text=line)
    return column


class PARAFORGE_PT_main(_Base, Panel):
    bl_label = _("Paralives export")
    bl_idname = "PARAFORGE_PT_main"

    def draw_header_preset(self, context):
        row = self.layout.row(align=True)
        current = i18n.language()
        for code, label, _description in i18n.LANGUAGES:
            operator = row.operator(
                "paraforge.set_language", text=label[:2].upper(),
                depress=(code == current),
            )
            operator.code = code

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)
        if settings is None:
            layout.label(text=_("Scene not ready"))
            return

        report = cache.get(context, settings)

        # Actions first. They are what the panel is for, and burying them
        # under a dozen check boxes means never scrolling far enough to find
        # the one that finishes the job.
        self._draw_target(context, layout, settings, report)
        layout.separator()
        self._draw_actions(context, layout, settings, report)
        layout.separator()
        self._draw_checklist(context, layout, settings, report)

    def _draw_target(self, context, layout, settings, report):
        root = prefs.mods_root(context)
        box = layout.box()

        if not root:
            column = box.column(align=True)
            column.label(text=_("Paralives folder not found"), icon="ERROR")
            column.operator("paraforge.detect_root",
                            text=_("Detect Paralives folder"), icon="VIEWZOOM")
            column.prop(settings, "mod_folder", text="")
        else:
            row = box.row(align=True)
            row.prop(settings, "mod_picker", text="", icon="FILE_FOLDER")
            row.operator("paraforge.create_mod", text="", icon="ADD")
            row.operator("paraforge.open_mod_folder", text="", icon="FILEBROWSER")
            if settings.mod_folder:
                sub = box.row()
                sub.scale_y = 0.7
                sub.label(text=os.path.basename(os.path.normpath(settings.mod_folder)))
                if modfolder.is_system_mod(settings.mod_folder):
                    warning = box.column(align=True)
                    warning.alert = True
                    paragraph(warning, context, _(
                        "This is one of the game's own folders. It works for "
                        "trying things out, but it cannot be uploaded to the "
                        "Workshop. Press + for a mod of your own."
                    ), scale=0.75)

        column = box.column(align=True)
        column.prop(settings, "item_type", text="")
        column.prop(settings, "catalog_tag", text="")
        if settings.catalog_tag == spec.CUSTOM_TAG:
            column.prop(settings, "catalog_tag_custom", text="")
        else:
            # The tag is what makes an item usable: it carries the slot
            # template the game attaches, so a chair filed under the wrong one
            # is furniture nobody sits on.
            template = catalog.slot_template(settings.catalog_tag)
            source = catalog.interaction_source(settings.catalog_tag)
            hint = column.row()
            hint.scale_y = 0.7
            if catalog.seats_a_para(settings.catalog_tag):
                hint.label(text=_("A Para can use it: ") + template,
                           icon="OUTLINER_OB_ARMATURE")
            elif source:
                hint.label(text=_("Interactions from ") + source, icon="PLAY")
            elif template:
                hint.label(text=_("Attaches ") + template, icon="SOUND")
            else:
                hint.label(text=_("Decoration, no Para uses it"),
                           icon="OUTLINER_OB_POINTCLOUD")

        # The tag names a default seat, the item overrides it. Left on
        # automatic this follows the tag, which is what most items want.
        column.prop(settings, "seat_template", text="", icon="OUTLINER_OB_ARMATURE")

        # Where the Para will land, next to the choice that decides it. The
        # figure comes from the checklist so the panel and the viewport guide
        # can never say different things.
        seat = next((c for c in report.checks if c.key == "seat"), None)             if report is not None else None
        if seat is not None:
            note = column.row()
            note.scale_y = 0.7
            note.alert = seat.status != validate.OK
            if report.seat_height is None:
                text = _("Nothing to sit on")
            else:
                text = _("Sits at {0:.3f} m, facing the arrow",
                         report.seat_height)
            note.label(text=text,
                       icon="CHECKMARK" if seat.status == validate.OK
                       else "ERROR")

        column.prop(settings, "asset_name", text="", icon="OUTLINER_OB_MESH")

    def _draw_checklist(self, context, layout, settings, report):
        counts = report.counts
        header = layout.row(align=True)
        header.alert = counts[validate.FAIL] > 0
        header.prop(
            settings, "show_all_checks",
            text=_("{0} ok   {1} warn   {2} blocking",
                   counts[validate.OK], counts[validate.WARN],
                   counts[validate.FAIL]),
            icon="CHECKMARK" if counts[validate.FAIL] == 0 else "CANCEL",
            emboss=False,
        )
        header.operator("paraforge.refresh", text="", icon="FILE_REFRESH")

        # Once everything passes there are twelve green boxes worth of
        # nothing to read, so they fold away behind the summary line.
        shown = report.checks if settings.show_all_checks else [
            c for c in report.checks if c.status != validate.OK
        ]
        for check in shown:
            box = layout.box()
            row = box.row(align=True)
            row.alert = check.status == validate.FAIL
            row.label(text=check.label, icon=STATUS_ICONS[check.status])

            if check.status != validate.OK or check.detail:
                column = paragraph(box, context, check.detail)
                column.enabled = check.status == validate.OK

            if check.fix and check.status != validate.OK:
                row = box.row()
                row.scale_y = 1.1
                row.operator(check.fix, text=check.fix_label or _("Fix"),
                             icon="TOOL_SETTINGS")

    def _draw_actions(self, context, layout, settings, report):
        if report.fixable():
            column = layout.column(align=True)
            column.scale_y = 1.2
            column.operator("paraforge.fix_all",
                            text=_("Fix everything safe"), icon="SHADERFX")

        # Seeing the game's own interpretation before writing anything is the
        # cheapest way to catch a texture problem, since the alternative is a
        # game restart.
        from . import preview as preview_module

        objects = validate.target_objects(context)
        row = layout.row(align=True)
        row.scale_y = 1.1
        row.operator(
            "paraforge.preview",
            text=(_("Back to my materials") if preview_module.is_on(objects)
                  else _("Preview as in game")),
            icon="SHADING_RENDERED",
            depress=preview_module.is_on(objects),
        )

        # Two steps, always both. Exporting writes the mesh and the textures,
        # generating declares the item. Assets alone sit in the mod without
        # ever showing up in Build Mode, which is exactly the trap.
        column = layout.column(align=True)
        column.scale_y = 1.6
        column.enabled = report.can_export
        column.operator("paraforge.export",
                        text="1.  " + _("Export to Paralives"), icon="EXPORT")

        if not report.can_export:
            row = layout.row()
            row.scale_y = 0.9
            operator = row.operator(
                "paraforge.export", text=_("Export anyway"), icon="ERROR"
            )
            operator.ignore_failures = True

        exported = self._exported(context, settings, report)
        column = layout.column(align=True)
        column.scale_y = 1.6
        column.operator("paraforge.generate_item",
                        text="2.  " + _("Create the item in the catalogue"),
                        icon="OUTLINER_OB_GROUP_INSTANCE")
        if exported is False:
            paragraph(layout, context,
                      _("Step 1 first: the mesh is not in the mod yet"),
                      scale=0.7)

        row = layout.row(align=True)
        row.operator("paraforge.undo_last", text=_("Undo the last write"),
                     icon="LOOP_BACK")

    @staticmethod
    def _exported(context, settings, report):
        """True when the FBX is already in the mod, None when unknowable."""
        from . import exporter

        objects = validate.target_objects(context)
        mod = (settings.mod_folder or "").strip()
        if not objects or not mod or not os.path.isdir(mod):
            return None
        name = exporter.base_name(settings, objects)
        return os.path.isfile(os.path.join(mod, name + ".fbx"))


class PARAFORGE_PT_facing(_Base, Panel):
    bl_label = _("Orientation")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)

        paragraph(layout, context, _(
            "The green arrow in the viewport points at Y+. The front of the "
            "item must look the same way."
        ))

        row = layout.row(align=True)
        for steps in ("90", "180", "270"):
            operator = row.operator("paraforge.rotate_to_face", text=steps)
            operator.steps = steps

        row = layout.row()
        row.scale_y = 1.2
        if settings.facing_confirmed:
            row.prop(settings, "facing_confirmed", text=_("Confirmed"),
                     icon="CHECKMARK", toggle=True)
        else:
            row.operator("paraforge.confirm_facing",
                         text=_("Confirm the item faces Y+"), icon="CHECKMARK")


def icon(*candidates, **kwargs):
    """First icon of the list that this Blender actually has.

    The sequencer colour tags were renamed from SEQUENCE_COLOR_ to
    STRIP_COLOR_ in Blender 5, and an icon name the build does not know raises
    at draw time rather than falling back, which takes the whole panel down.
    """
    known = {
        item.identifier for item in
        bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items
    }
    for name in candidates:
        if name in known:
            return name
    return kwargs.get("fallback", "DOT")


#: Blender ships coloured swatch icons, so the zone buttons can actually look
#: like their zone instead of reading as five identical numbers.
ZONE_BUTTONS = (
    ("0", "0", icon("STRIP_COLOR_09", "SEQUENCE_COLOR_09")),
    ("1", "1", icon("STRIP_COLOR_01", "SEQUENCE_COLOR_01")),
    ("2", "2", icon("STRIP_COLOR_04", "SEQUENCE_COLOR_04")),
    ("3", "3", icon("STRIP_COLOR_05", "SEQUENCE_COLOR_05")),
    ("decal", "Decal", icon("STRIP_COLOR_03", "SEQUENCE_COLOR_03")),
)


class PARAFORGE_PT_zones(_Base, Panel):
    bl_label = _("Colour zones")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)

        # 1. Paint a selection.
        box = layout.box()
        box.label(text=_("Paint"), icon="BRUSH_DATA")
        row = box.row(align=True)
        for key, label, icon in ZONE_BUTTONS:
            operator = row.operator(
                "paraforge.assign_zone",
                text=_(label) if key == "decal" else label, icon=icon,
            )
            operator.zone = key
            operator.whole_mesh = settings.zone_whole_mesh
        box.prop(settings, "zone_whole_mesh", text=_("Whole mesh"))
        paragraph(box, context, _(
            "Select faces in Edit Mode, then click a zone"
        ) if not settings.zone_whole_mesh else _("The whole mesh will be painted"))

        # 2. One material per zone.
        box = layout.box()
        box.label(text=_("From materials"), icon="MATERIAL")
        paragraph(box, context, _(
            "Each material slot becomes a zone, in order. The quickest route "
            "for an imported or generated asset."
        ))
        box.operator("paraforge.zones_from_materials",
                     text=_("Zones from materials"), icon="MATERIAL_DATA")

        # 3. Colour picker with tolerance.
        box = layout.box()
        box.label(text=_("From the texture"), icon="EYEDROPPER")
        paragraph(box, context, _(
            "For an asset with a single baked texture and no zones at all. "
            "The texture is read directly, lighting cannot shift it."
        ))

        box.operator(
            "paraforge.pick_zone_color",
            text=_("Pick a colour on the model"),
            icon="EYEDROPPER",
        )

        row = box.row(align=True)
        row.prop(settings, "zone_color", text="")
        row.prop_search(
            settings, "zone_image", bpy.data, "images", text="", icon="IMAGE_DATA"
        )

        box.prop(settings, "zone_tolerance", text=_("Tolerance"), slider=True)
        box.prop(settings, "zone_reset_rest", text=_("Reset the rest to zone 0"))

        row = box.row(align=True)
        row.prop(settings, "zone_target", expand=True)

        row = box.row()
        row.scale_y = 1.3
        row.enabled = bool(settings.zone_image)
        operator = row.operator(
            "paraforge.zone_from_color",
            text=_("Assign to zone ") + settings.zone_target,
            icon="CHECKMARK",
        )
        operator.zone = settings.zone_target
        operator.color = settings.zone_color
        operator.tolerance = settings.zone_tolerance
        operator.image_name = settings.zone_image
        operator.rest_to_zone_zero = settings.zone_reset_rest

        paragraph(box, context, _(
            "Press F9 afterwards to tune the tolerance live"
        ))

        layout.operator("paraforge.clear_zones", text=_("Reset to zone 0"),
                        icon="LOOP_BACK")


class PARAFORGE_PT_textures(_Base, Panel):
    bl_label = _("Textures")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)
        report = cache.peek()
        plan = report.texture_plan if report else None

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("paraforge.detect_roles", text=_("Auto-detect"),
                     icon="VIEWZOOM")
        layout.prop(settings, "recolourable", text=_("Recolourable in game"))

        if plan is None or not plan.sources:
            layout.label(text=_("No image in the materials"), icon="INFO")
            return

        if plan.multi_group:
            row = layout.row()
            row.scale_y = 1.3
            row.operator("paraforge.bake_to_atlas",
                         text=_("Bake into one surface"), icon="RENDER_STILL")

        self._draw_outputs(context, layout, plan)
        self._draw_sources(context, layout, plan)

        for note in plan.notes:
            box = layout.box()
            box.alert = True
            paragraph(box, context, note, scale=0.8)

    def _draw_outputs(self, context, layout, plan):
        layout.separator()
        layout.label(text=_("Will be written"), icon="FILE_TICK")
        if not plan.outputs:
            layout.label(text=_("Nothing to detect"), icon="ERROR")
            return

        for output in plan.outputs:
            box = layout.box()
            row = box.row(align=True)
            row.label(text=output.target_name, icon="IMAGE_DATA")

            sub = box.row()
            sub.scale_y = 0.72
            sub.label(text=textures.preview(output))

            if output.note:
                paragraph(box, context, output.note, scale=0.68)

    def _draw_sources(self, context, layout, plan):
        layout.separator()
        layout.label(text=_("Sources"), icon="TEXTURE")

        for source in plan.sources:
            box = layout.box()
            row = box.row(align=True)
            row.alert = not source.known
            row.label(
                text=source.stem,
                icon="IMAGE_DATA" if source.known else "ERROR",
            )

            sub = box.row()
            sub.scale_y = 0.72
            if source.known:
                sub.label(text="{0}   {1}".format(
                    source.role_label(), source.evidence_label()))
            else:
                sub.label(text=_("no suffix, will not auto configure"))

            operator = box.operator(
                "paraforge.set_texture_role",
                text=source.role_label() if source.known else _("Assign a role"),
                icon="PRESET",
            )
            operator.image = source.image.name


class PARAFORGE_PT_options(_Base, Panel):
    bl_label = _("Export options")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)
        column = layout.column(align=True)
        column.prop(settings, "triangulate", text=_("Triangulate on export"))
        column.prop(settings, "export_textures", text=_("Export textures"))
        column.prop(settings, "overwrite", text=_("Overwrite existing files"))
        column.prop(settings, "write_sidecars", text=_("Write the .meta files"))

        layout.separator()
        box = layout.box()
        box.prop(settings, "own_surface", text=_("Give the item its own surface"))
        column = box.column(align=True)
        column.scale_y = 0.72
        column.enabled = settings.own_surface
        for line in util.wrap_to(context, _(
            "Carries the normal map and the smoothness. Without it the item "
            "borrows the game's shared surface and has no relief."), 6
        ):
            column.label(text=line)
        row = box.row()
        row.enabled = settings.own_surface
        row.prop(settings, "smoothness", text=_("Smoothness"), slider=True)

        layout.separator()
        box = layout.box()

        # An item a Para sits on gets neither handle, whatever is ticked here,
        # so the panel says so where the ticks are rather than letting the
        # export quietly disagree with the interface.
        sits = item.sits_on_it(settings)
        if sits:
            warning = box.column(align=True)
            warning.alert = True
            for line in util.wrap_to(context, _(
                "A Para sits on this one, so both handles are left out. "
                "Resizing moves the seat out of reach and nobody sits down."
            ), 6):
                warning.label(text=line)

        handles = box.column()
        handles.enabled = not sits
        handles.prop(settings, "scalable", text=_("Scalable in game"))
        row = handles.row(align=True)
        row.enabled = settings.scalable and not sits
        row.prop(settings, "min_scale", text=_("Smallest"))
        row.prop(settings, "max_scale", text=_("Largest"))

        # The game's second handle, and a separate declaration. Scaling
        # multiplies the whole item, stretching moves one axis at a time.
        handles.separator()
        handles.prop(settings, "resizable", text=_("Stretchable per axis"))
        column = handles.column(align=True)
        column.enabled = settings.resizable
        row = column.row(align=True)
        row.prop(settings, "resizable_axes", text="")
        row = column.row(align=True)
        row.prop(settings, "min_size_factor", text=_("Smallest"))
        row.prop(settings, "max_size_factor", text=_("Largest"))
        if settings.resizable and not any(settings.resizable_axes):
            hint = column.row()
            hint.alert = True
            hint.label(text=_("No axis allowed, the handle would do nothing"))

        layout.separator()
        layout.prop(settings, "swatch_group", text=_("Swatch group"))
        layout.prop(settings, "write_recipe", text=_("Write the recipe file"))

        layout.separator()
        column = layout.column(align=True)
        column.scale_y = 0.72
        for line in util.wrap(_(
            "A mod adds to lists the game already fills. Getting this wrong "
            "makes the game keep only what the mod wrote, which is how every "
            "menu label turns into a raw key."), 40
        ):
            column.label(text=line)
        layout.prop(settings, "merge_marker", text="")

        box = layout.box()
        box.scale_y = 0.72
        box.label(text=_("Fixed by the Paralives spec:"))
        box.label(text=_("Forward {0}, Up {1}",
                         spec.FBX_AXIS_FORWARD, spec.FBX_AXIS_UP))
        box.label(text=_("Vertex colours exported (sRGB)"))
        box.label(text=_("Tangents exported for normal maps"))
        box.label(text=_("PNG only, the game rejects other formats"))
        box.label(text=_("Catalogue read from game build {0}",
                         catalog.SOURCE_BUILD))


class PARAFORGE_PT_viewport(_Base, Panel):
    bl_label = _("Viewport guides")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)

        column = layout.column(align=True)
        column.prop(settings, "show_overlay", text=_("Viewport guides"))
        column.prop(settings, "show_hud", text=_("Viewport checklist"))

        sub = layout.column(align=True)
        sub.enabled = settings.show_overlay
        sub.prop(settings, "show_grid", text=_("Grid"))
        sub.prop(settings, "show_bounds", text=_("Bounding box"))
        sub.prop(settings, "show_arrow", text=_("Facing arrow"))
        sub.prop(settings, "show_seat", text=_("Seat guide"))
        sub.prop(settings, "show_human", text=_("Person for scale"))
        row = sub.row()
        row.enabled = settings.show_human
        row.prop(settings, "human_height", text=_("Their height"))
        sub.prop(settings, "grid_extent", text=_("Grid tiles"))

        layout.separator()
        box = layout.box()
        box.enabled = settings.show_hud
        box.label(text=_("Checklist corner"), icon="WORDWRAP_ON")
        box.prop(settings, "hud_corner", text="")
        row = box.row(align=True)
        row.prop(settings, "hud_offset_x", text=_("Nudge X"))
        row.prop(settings, "hud_offset_y", text=_("Nudge Y"))
        box.prop(settings, "hud_only_problems", text=_("Only problems"))
        paragraph(box, context, _(
            "The checklist dodges the toolbar and the sidebar on its own"
        ), scale=0.68)


class PARAFORGE_PT_calibration(_Base, Panel):
    bl_label = _("Calibration")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)

        paragraph(layout, context, _(
            "Measured on {0} meshes taken from the game itself: {1} triangles "
            "in the median, {2} at the very most. The budget below is that "
            "maximum, and it is only a warning.",
            spec.MEASURED_SAMPLE, spec.MEASURED_TRIANGLES_MEDIAN,
            spec.MEASURED_TRIANGLES_MAX,
        ), scale=0.75)

        layout.prop(settings, "tile_size", text=_("Tile size"))
        layout.prop(settings, "triangle_budget", text=_("Triangle budget"))
        layout.prop(settings, "fbx_unit_scale", text=_("FBX units per metre"))
        layout.prop(settings, "decimate_rebake",
                    text=_("Bake the look back onto it"))
        layout.operator("paraforge.decimate_to_budget",
                        text=_("Reduce to the budget"), icon="MOD_DECIM")


class PARAFORGE_PT_remesh(_Base, Panel):
    bl_label = _("Remesh")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        from . import remesh

        layout = self.layout
        settings = props.settings(context)
        mode = settings.remesh_mode

        paragraph(layout, context, _(
            "Rebuilds the topology instead of collapsing it, which holds an "
            "organic shape together where reducing tears it apart. Try the "
            "modes on screen, then bake the original onto what you chose."
        ), scale=0.75)

        layout.prop(settings, "remesh_mode", expand=True)

        column = layout.column(align=True)
        for name, label in (
            ("remesh_octree_depth", _("Octree Depth")),
            ("remesh_scale", _("Scale")),
            ("remesh_sharpness", _("Sharpness")),
            ("remesh_threshold", _("Threshold")),
            ("remesh_voxel_size", _("Voxel Size")),
            ("remesh_adaptivity", _("Adaptivity")),
        ):
            if not remesh.used_by(mode, name[len("remesh_"):]):
                continue
            column.prop(settings, name, text=label)

        column = layout.column(align=True)
        column.prop(settings, "remesh_remove_disconnected",
                    text=_("Remove Disconnected"))
        column.prop(settings, "remesh_smooth_shading",
                    text=_("Smooth Shading"))

        layout.separator()
        layout.prop(settings, "remesh_rebake",
                    text=_("Bake the look back onto it"))
        row = layout.row()
        row.scale_y = 1.2
        row.operator("paraforge.remesh", text=_("Remesh"), icon="MOD_REMESH")


class PARAFORGE_PT_inspector(_Base, Panel):
    bl_label = _("Mod folder inspector")
    bl_parent_id = "PARAFORGE_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = props.settings(context)

        paragraph(layout, context, _(
            "Find out whether item definitions can be generated. Snapshot the "
            "mod, create one item in the game, quit, then diff."
        ), scale=0.75)

        column = layout.column(align=True)
        column.enabled = bool(settings.mod_folder and os.path.isdir(settings.mod_folder))
        # When the game refuses an item and will not say why, it can be
        # asked: every one of these loggers ships turned off.
        from . import ops as ops_module

        on = os.path.isfile(ops_module._loggers_path(settings.mod_folder))             if settings.mod_folder else False
        row = column.row()
        row.operator(
            "paraforge.toggle_diagnostics",
            text=(_("Stop explaining") if on
                  else _("Ask the game to explain itself")),
            icon="CONSOLE", depress=on,
        )

        column.operator("paraforge.snapshot_mod",
                        text=_("Snapshot mod folder"), icon="FILE_TICK")
        column.operator("paraforge.diff_mod",
                        text=_("Diff since snapshot"), icon="ZOOM_ALL")


classes = (
    PARAFORGE_PT_main,
    PARAFORGE_PT_facing,
    PARAFORGE_PT_zones,
    PARAFORGE_PT_textures,
    PARAFORGE_PT_options,
    PARAFORGE_PT_viewport,
    PARAFORGE_PT_calibration,
    PARAFORGE_PT_remesh,
    PARAFORGE_PT_inspector,
)
