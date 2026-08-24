# SPDX-License-Identifier: GPL-3.0-or-later
"""ParaForge, a one click Paralives asset pipeline for Blender.

Validate the mesh against every rule Paralives imposes, fix what can be fixed,
rebuild the textures into the maps the game actually reads, then write the FBX
and its correctly named PNGs straight into a .mod folder. The game never has
to be running.
"""

import importlib
import sys

import bpy

from . import cache, fixes, ops, overlay, prefs, props, thumbs, ui, zones

#: Registration order matters: preferences first, because the mod folder enum
#: reads them while it builds its item list.
MODULES = (prefs, props, fixes, zones, ops, ui)

#: Reload order for a language switch, dependencies before dependents. Every
#: bl_label and every property tooltip is baked at class definition time, so
#: the class bodies have to run again for a switch to reach them.
RELOAD_ORDER = (
    "i18n", "catalog", "spec", "util", "imaging", "modfolder", "geo",
    "uvxform", "sidecar", "setting", "journal", "textures", "bake", "remesh",
    "item",
    "recipe", "inspector", "validate",
    "cache", "prefs", "props", "zones", "fixes", "exporter", "manage",
    "thumbs", "ops", "overlay", "ui",
)


def register():
    for module in MODULES:
        for cls in module.classes:
            bpy.utils.register_class(cls)

    props.register_pointer()
    cache.register()
    thumbs.register()

    if not bpy.app.background:
        overlay.register()


def unregister():
    if not bpy.app.background:
        overlay.unregister()

    thumbs.unregister()
    cache.unregister()
    props.unregister_pointer()

    for module in reversed(MODULES):
        for cls in reversed(module.classes):
            try:
                bpy.utils.unregister_class(cls)
            except RuntimeError:
                pass


def reload_for_language():
    """Rebuild every class so the baked interface strings change language.

    importlib.reload re-executes a module inside the object that already
    exists, so the references held across the package stay valid and only the
    classes are new. Scene settings are copied out and back because dropping
    Scene.paraforge takes their values with it.
    """
    values = props.capture()
    unregister()
    try:
        for name in RELOAD_ORDER:
            module = sys.modules.get("{0}.{1}".format(__name__, name))
            if module is not None:
                importlib.reload(module)
    finally:
        register()
        props.restore(values)
        cache.clear()
        _redraw_everything()


def _redraw_everything():
    manager = getattr(bpy.context, "window_manager", None)
    for window in getattr(manager, "windows", ()):
        for area in window.screen.areas:
            area.tag_redraw()


if __name__ == "__main__":
    register()
