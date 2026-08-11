# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: where Paralives keeps its mods."""

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import AddonPreferences, Operator

from . import i18n, modfolder

_ = i18n.t

ADDON_ID = __package__


def get(context=None):
    context = context or bpy.context
    entry = context.preferences.addons.get(ADDON_ID)
    return entry.preferences if entry else None


def mods_root(context=None):
    preferences = get(context)
    configured = preferences.mods_root if preferences else ""
    return modfolder.resolve_root(configured)


class PARAFORGE_OT_detect_root(Operator):
    bl_idname = "paraforge.detect_root"
    bl_label = _("Detect Paralives folder")
    bl_description = _("Look for the Paralives mods folder in the usual location")
    bl_options = {"INTERNAL"}

    def execute(self, context):
        found = modfolder.detect_root()
        preferences = get(context)
        if not found:
            self.report(
                {"WARNING"},
                _("Not found. Tried: ") + " | ".join(modfolder.candidate_roots()),
            )
            return {"CANCELLED"}
        if preferences:
            preferences.mods_root = found
        self.report({"INFO"}, _("Found ") + found)
        return {"FINISHED"}


class ParaForgePreferences(AddonPreferences):
    bl_idname = ADDON_ID

    mods_root: StringProperty(
        name=_("Paralives mods folder"),
        description=_(
            "Folder holding the .mod directories. Leave empty to auto detect"
        ),
        subtype="DIR_PATH",
        default="",
    )

    asset_subfolder: StringProperty(
        name=_("Asset subfolder"),
        description=_(
            "Optional subfolder inside the mod to write assets into. "
            "Leave empty to write at the root of the mod folder, which is "
            "what the official guide describes"
        ),
        default="",
    )

    open_folder_after_export: BoolProperty(
        name=_("Open the folder after export"),
        default=False,
    )

    warn_outside_root: BoolProperty(
        name=_("Warn when writing outside the mods folder"),
        default=True,
    )

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.label(text=_("Language"), icon="WORLD")
        current = i18n.language()
        for code, label, _description in i18n.LANGUAGES:
            operator = row.operator(
                "paraforge.set_language", text=label,
                depress=(code == current),
            )
            operator.code = code

        box = layout.box()
        row = box.row(align=True)
        row.prop(self, "mods_root")
        row.operator(PARAFORGE_OT_detect_root.bl_idname, text="", icon="VIEWZOOM")

        resolved = modfolder.resolve_root(self.mods_root)
        if resolved:
            mods = modfolder.list_mods(resolved)
            box.label(
                text=_("{0} mod folder(s) found", len(mods)),
                icon="CHECKMARK",
            )
        else:
            box.label(text=_("Paralives folder not found"), icon="ERROR")
            column = box.column(align=True)
            column.scale_y = 0.8
            for candidate in modfolder.candidate_roots():
                column.label(text=candidate)
            box.label(text=_(
                "Create a mod once from the game's Modding Tools, then detect "
                "again"
            ))

        layout.prop(self, "asset_subfolder")
        layout.prop(self, "open_folder_after_export")
        layout.prop(self, "warn_outside_root")


classes = (PARAFORGE_OT_detect_root, ParaForgePreferences)
