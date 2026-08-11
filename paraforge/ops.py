# SPDX-License-Identifier: GPL-3.0-or-later
"""Export, language and mod folder operators."""

import os
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import cache, exporter, i18n, inspector, modfolder, prefs, props, validate

_ = i18n.t


def _snapshot_dir():
    path = bpy.utils.user_resource("CONFIG", path="paraforge", create=True)
    return path


def _snapshot_path(mod_path):
    key = os.path.basename(os.path.normpath(mod_path)) or "mod"
    return os.path.join(_snapshot_dir(), key + ".snapshot.json")


class PARAFORGE_OT_export(Operator):
    bl_idname = "paraforge.export"
    bl_label = _("Export to Paralives")
    bl_description = _(
        "Write the FBX and its textures into the selected .mod folder, with "
        "the axes, naming and settings Paralives expects"
    )
    bl_options = {"REGISTER"}

    ignore_failures: BoolProperty(
        name=_("Export anyway"),
        description=_("Export even though checks are failing"),
        default=False,
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return bool(validate.target_objects(context))

    def execute(self, context):
        settings = props.settings(context)
        objects = validate.target_objects(context)
        report = cache.get(context, settings, force=True)

        if not report.can_export and not self.ignore_failures:
            failing = [c.label for c in report.checks if c.blocking]
            self.report(
                {"ERROR"},
                _("Blocked by: ") + ", ".join(failing[:4])
                + ("..." if len(failing) > 4 else ""),
            )
            return {"CANCELLED"}

        started = time.monotonic()
        try:
            result = exporter.export(context, settings, objects, report)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        for warning in result.warnings:
            self.report({"WARNING"}, warning)

        elapsed = (time.monotonic() - started) * 1000.0
        names = ", ".join(os.path.basename(p) for p in result.files[:4])
        self.report(
            {"INFO"},
            _("{0} file(s) in {1:.0f} ms: {2}{3}",
              len(result.files), elapsed, names,
              "..." if len(result.files) > 4 else ""),
        )

        preferences = prefs.get(context)
        if preferences and preferences.open_folder_after_export:
            exporter.reveal(result.target_dir)

        return {"FINISHED"}


class PARAFORGE_OT_open_mod_folder(Operator):
    bl_idname = "paraforge.open_mod_folder"
    bl_label = _("Open folder")
    bl_description = _("Open the target folder in the file browser")
    bl_options = {"INTERNAL"}

    path: StringProperty(subtype="DIR_PATH")

    def execute(self, context):
        settings = props.settings(context)
        target = self.path or settings.mod_folder or prefs.mods_root(context)
        if not target or not os.path.isdir(target):
            self.report({"ERROR"}, _("Folder not found"))
            return {"CANCELLED"}
        exporter.reveal(target)
        return {"FINISHED"}


class PARAFORGE_OT_refresh(Operator):
    bl_idname = "paraforge.refresh"
    bl_label = _("Refresh")
    bl_description = _("Re-run every check now")
    bl_options = {"INTERNAL"}

    def execute(self, context):
        settings = props.settings(context)
        cache.get(context, settings, force=True)
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


# --------------------------------------------------------------------------
# Language
#
# Blender bakes bl_label, bl_description and property tooltips into the RNA
# when a class registers, so the only way to translate them is to register
# again. The switch is deferred to a timer: tearing the add-on down from
# inside one of its own buttons would pull the rug from under the caller.


class PARAFORGE_OT_set_language(Operator):
    bl_idname = "paraforge.set_language"
    bl_label = _("Language")
    bl_description = _("Switch the whole add-on between French and English")
    bl_options = {"INTERNAL"}

    code: EnumProperty(
        name=_("Language"),
        items=[(key, label, description)
               for key, label, description in i18n.LANGUAGES],
        default=i18n.DEFAULT,
    )

    def execute(self, context):
        if not i18n.set_language(self.code):
            return {"CANCELLED"}

        cache.clear()
        bpy.app.timers.register(_reload_later, first_interval=0.0)
        self.report(
            {"INFO"}, _("Language set to {0}, reloading",
                        i18n.language_label(self.code))
        )
        return {"FINISHED"}


def _reload_later():
    """Re-register outside of any draw or operator callback."""
    import sys

    package = sys.modules.get(__package__)
    if package is None:
        return None
    try:
        package.reload_for_language()
    except Exception as error:  # a broken reload must not leave a dead add-on
        print("[ParaForge] language reload failed:", error)
    return None


# --------------------------------------------------------------------------
# Mod folder inspector


class PARAFORGE_OT_snapshot_mod(Operator):
    bl_idname = "paraforge.snapshot_mod"
    bl_label = _("Snapshot mod folder")
    bl_description = _(
        "Record the exact contents of the mod folder. Quit the game first, "
        "then create one item inside it, then run the diff"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = props.settings(context)
        mod_path = (settings.mod_folder or "").strip()
        if not mod_path or not os.path.isdir(mod_path):
            self.report({"ERROR"}, _("Pick a valid mod folder first"))
            return {"CANCELLED"}

        try:
            data = inspector.snapshot(mod_path)
            destination = inspector.save(data, _snapshot_path(mod_path))
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            _("{0} file(s) recorded to {1}", len(data["files"]), destination),
        )
        return {"FINISHED"}


class PARAFORGE_OT_diff_mod(Operator):
    bl_idname = "paraforge.diff_mod"
    bl_label = _("Diff since snapshot")
    bl_description = _(
        "Compare the mod folder with the last snapshot and open a report "
        "showing exactly what the game wrote"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = props.settings(context)
        mod_path = (settings.mod_folder or "").strip()
        if not mod_path or not os.path.isdir(mod_path):
            self.report({"ERROR"}, _("Pick a valid mod folder first"))
            return {"CANCELLED"}

        snapshot_file = _snapshot_path(mod_path)
        if not os.path.isfile(snapshot_file):
            self.report({"ERROR"}, _("No snapshot for this mod yet"))
            return {"CANCELLED"}

        try:
            before = inspector.load(snapshot_file)
            after = inspector.snapshot(mod_path)
            text = inspector.report(before, after)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        report_path = os.path.join(_snapshot_dir(), "last_diff.md")
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(text)

        name = "ParaForge diff"
        block = bpy.data.texts.get(name) or bpy.data.texts.new(name)
        block.clear()
        block.write(text)

        _show_text(context, block)
        changes = inspector.diff(before, after)
        self.report(
            {"INFO"},
            _("{0} added, {1} modified, {2} removed. Report in the Text "
              "Editor and at {3}",
              len(changes["added"]), len(changes["modified"]),
              len(changes["removed"]), report_path),
        )
        return {"FINISHED"}


def _show_text(context, block):
    """Point an existing Text Editor at the report, if one is open."""
    for area in context.screen.areas:
        if area.type == "TEXT_EDITOR":
            area.spaces.active.text = block
            area.tag_redraw()
            return True
    return False


classes = (
    PARAFORGE_OT_export,
    PARAFORGE_OT_open_mod_folder,
    PARAFORGE_OT_refresh,
    PARAFORGE_OT_set_language,
    PARAFORGE_OT_snapshot_mod,
    PARAFORGE_OT_diff_mod,
)
