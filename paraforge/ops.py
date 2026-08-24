# SPDX-License-Identifier: GPL-3.0-or-later
"""Export, language and mod folder operators."""

import os
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import (
    cache, exporter, i18n, inspector, journal, manage, modfolder, prefs,
    props, setting, sidecar, spec, thumbs, validate,
)

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


class PARAFORGE_OT_preview(Operator):
    bl_idname = "paraforge.preview"
    bl_label = _("Preview as in game")
    bl_description = _(
        "Write the textures exactly as the export would, read them back, and "
        "show the object through them. What you see is then the data the game "
        "is handed, not the material the file arrived with. Press again to put "
        "your own materials back"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(validate.target_objects(context))

    def execute(self, context):
        from . import preview

        settings = props.settings(context)
        objects = validate.target_objects(context)

        if preview.is_on(objects):
            preview.restore(objects)
            self.report({"INFO"}, _("Your own materials are back"))
            return {"FINISHED"}

        report = cache.get(context, settings, force=True)
        try:
            _material, written = preview.apply(context, settings, objects, report)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        missing = [s for s in ("NormalOcclusion", "Smoothness")
                   if s not in written]
        if missing:
            self.report({"WARNING"}, _(
                "No {0}, so the game will not have one either",
                ", ".join(missing),
            ))
        self.report({"INFO"}, _("Showing {0}", ", ".join(written)))
        return {"FINISHED"}


LOGGERS_FILE = "Loggers.setting"

#: The game writes its settings with CRLF.
LINE_END = chr(13) + chr(10)

#: What the game logs once these are on. Every one of them is a field of
#: Setting.Loggers, which ships with all of them False, and a mod's own
#: Settings folder merges over the game's.
LOGGERS = (
    "LogItemSlotManager",
    "LogItemFinderRuleManager",
    "LogItemLocatorManager",
    "LogCharacterInteractions",
    "LogCharacterActions",
)


def _loggers_path(mod_path):
    return os.path.join(mod_path, "Settings", LOGGERS_FILE)


class PARAFORGE_OT_toggle_diagnostics(Operator):
    bl_idname = "paraforge.toggle_diagnostics"
    bl_label = _("Ask the game to explain itself")
    bl_description = _(
        "Turn on the game's own item slot logging, from inside your mod. It "
        "then writes into Player.log exactly why a Para refuses an item: the "
        "slot it wanted, the type it found, and whether the item had any slot "
        "at all. Press again to turn it off"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = props.settings(context)
        return bool(settings and settings.mod_folder)

    def execute(self, context):
        settings = props.settings(context)
        mod_path = (settings.mod_folder or "").strip()
        if not os.path.isdir(mod_path):
            self.report({"ERROR"}, _("Pick a valid mod folder first"))
            return {"CANCELLED"}

        path = _loggers_path(mod_path)
        if os.path.isfile(path):
            os.remove(path)
            meta = path + ".meta"
            if os.path.isfile(meta):
                os.remove(meta)
            self.report({"INFO"}, _("Diagnostics off"))
            return {"FINISHED"}

        lines = ["#Setting.Loggers"]
        # Without this every line is wrapped in colour markup.
        lines.append(" RemoveColorStyleTags:True")
        for name in LOGGERS:
            lines.append(" {0}:True".format(name))
        setting.write(path, LINE_END.join(lines) + LINE_END)
        sidecar.write(path, spec.META_TYPE_SETTING,
                      sidecar.asset_guid(mod_path, LOGGERS_FILE),
                      {"IsSettingType": "True",
                       "SettingType": "Setting.Loggers"})

        self.report({"INFO"}, _(
            "Diagnostics on. Restart Paralives, ask a Para to use the item, "
            "then read Player.log"))
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


class PARAFORGE_OT_create_mod(Operator):
    bl_idname = "paraforge.create_mod"
    bl_label = _("New mod")
    bl_description = _(
        "Create an empty mod folder and select it. A mod is a folder and a "
        "manifest, so the game does not have to be launched to make one. Use "
        "this rather than Local.mod, which is the game's own scratch folder "
        "and cannot be uploaded to the Workshop"
    )
    bl_options = {"REGISTER"}

    name: StringProperty(
        name=_("Mod name"),
        description=_("Becomes the folder name, and the name in the game"),
        default="MyPack",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def execute(self, context):
        settings = props.settings(context)
        root = prefs.mods_root(context)
        if not root:
            self.report({"ERROR"}, _(
                "Paralives folder not found. Run the game once, or set the "
                "folder in the add-on preferences"
            ))
            return {"CANCELLED"}

        try:
            folder, created = modfolder.create_mod(root, self.name)
        except OSError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        settings.mod_folder = folder
        cache.invalidate()
        if not created:
            self.report({"INFO"}, _("{0} already existed, selected it",
                                    os.path.basename(folder)))
        else:
            self.report({"INFO"}, _("{0} created", os.path.basename(folder)))
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
# The item itself
#
# This is the step that used to happen in the Control Panel. An item is three
# pieces of text inside your own mod, so it can be written from here, and
# undone from here too.


class PARAFORGE_OT_generate_item(Operator):
    bl_idname = "paraforge.generate_item"
    bl_label = _("Create the item in the catalogue")
    bl_description = _(
        "Write the prefab and register the item in the mod, so it appears in "
        "Build Mode without opening the Control Panel. Only files inside the "
        "target .mod are touched, and every change can be undone"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = props.settings(context)
        return bool(settings and settings.mod_folder)

    def execute(self, context):
        from . import exporter, item

        settings = props.settings(context)
        objects = validate.target_objects(context)
        report = cache.get(context, settings, force=True)
        mod_path = (settings.mod_folder or "").strip()

        if not os.path.isdir(mod_path):
            self.report({"ERROR"}, _("Pick a valid mod folder first"))
            return {"CANCELLED"}
        if modfolder.game_install_above(mod_path):
            self.report({"ERROR"}, _("Never inside the game installation"))
            return {"CANCELLED"}

        name = exporter.base_name(settings, objects)
        try:
            result = item.generate(
                mod_path, name, settings, report, _zone_count(report)
            )
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        for note in result.notes:
            self.report({"WARNING"}, note)
        if result.skipped:
            self.report({"INFO"}, _("{0} already had this item, left alone",
                                    ", ".join(result.skipped)))

        self.report(
            {"INFO"},
            _("{0} is in the catalogue. Restart Paralives to see it",
              name),
        )
        return {"FINISHED"}


def _zone_count(report):
    check = next((c for c in report.checks if c.key == "zones"), None)
    if check is None:
        return 1
    digits = [int(c) for c in check.detail if c.isdigit()]
    return digits[0] if digits else 1


class PARAFORGE_OT_undo_last(Operator):
    bl_idname = "paraforge.undo_last"
    bl_label = _("Undo the last write")
    bl_description = _(
        "Put the mod back exactly as it was before the last item was "
        "generated: created files are removed, edited ones are restored from "
        "the copy taken beforehand. Press again to step back further"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        settings = props.settings(context)
        if not settings or not settings.mod_folder:
            return False
        return bool(journal.last(settings.mod_folder))

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = props.settings(context)
        mod_path = (settings.mod_folder or "").strip()

        result = journal.undo_last(mod_path)
        if result is None:
            self.report({"INFO"}, _("Nothing to undo in this mod"))
            return {"CANCELLED"}

        label, removed, restored = result
        cache.invalidate()
        self.report(
            {"INFO"},
            _("{0} undone: {1} file(s) removed, {2} restored",
              label, removed, restored),
        )
        return {"FINISHED"}


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



class PARAFORGE_OT_delete_item(Operator):
    bl_idname = "paraforge.delete_item"
    bl_label = _("Remove from the mod")
    bl_description = _(
        "Remove this item from the mod: its prefab, its mesh, its textures, "
        "every sidecar, its catalogue entry, its translation and its "
        "thumbnail. Undo the last write puts it back"
    )
    bl_options = {"REGISTER", "INTERNAL"}

    guid: StringProperty(name="GUID", default="")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def _record(self, context):
        settings = props.settings(context)
        root = prefs.mods_root(context)
        for record in manage.items(settings.mod_folder, root):
            if record.guid == self.guid:
                return settings, record
        return settings, None

    def draw(self, context):
        layout = self.layout
        _settings, record = self._record(context)
        if record is None:
            layout.label(text=_("That item is no longer in the mod"))
            return

        layout.label(text=record.name or record.guid, icon="TRASH")
        files = manage.files_of(record)
        column = layout.column(align=True)
        column.scale_y = 0.7
        for path in files[:10]:
            column.label(text=os.path.basename(path))
        if len(files) > 10:
            column.label(text=_("and {0} more", len(files) - 10))
        column.label(text=_("plus its catalogue and translation entries"))

        # A mesh two items share is not this item's to take away.
        if record.shared:
            note = layout.column(align=True)
            note.scale_y = 0.7
            note.label(text=_("Kept, another item uses them:"), icon="INFO")
            for path in record.shared[:4]:
                note.label(text=os.path.basename(path))

    def execute(self, context):
        settings, record = self._record(context)
        if record is None:
            self.report({"ERROR"}, _("That item is no longer in the mod"))
            return {"CANCELLED"}

        root = prefs.mods_root(context)
        removed, notes = manage.delete(settings.mod_folder, record, root)
        thumbs.clear()
        for note in notes[:3]:
            self.report({"WARNING"}, note)
        self.report(
            {"INFO"},
            _("Removed {0}, {1} file(s)", record.name or record.guid,
              len(removed)),
        )
        return {"FINISHED"}


class PARAFORGE_OT_refresh_items(Operator):
    bl_idname = "paraforge.refresh_items"
    bl_label = _("Refresh")
    bl_description = _("Read the mod folder again, thumbnails included")
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        thumbs.clear()
        return {"FINISHED"}

classes = (
    PARAFORGE_OT_delete_item,
    PARAFORGE_OT_refresh_items,
    PARAFORGE_OT_export,
    PARAFORGE_OT_toggle_diagnostics,
    PARAFORGE_OT_preview,
    PARAFORGE_OT_open_mod_folder,
    PARAFORGE_OT_create_mod,
    PARAFORGE_OT_refresh,
    PARAFORGE_OT_set_language,
    PARAFORGE_OT_generate_item,
    PARAFORGE_OT_undo_last,
    PARAFORGE_OT_snapshot_mod,
    PARAFORGE_OT_diff_mod,
)
