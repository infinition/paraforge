# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared, throttled validation result.

The panel and the viewport overlay both need the report. Recomputing it on
every redraw would measure the evaluated mesh dozens of times per second, so
it is computed at most a few times a second and reused.
"""

import time

import bpy

from . import validate

_report = None
_stamp = 0.0
_dirty = True

#: Minimum delay between two recomputes, in seconds.
THROTTLE = 0.2


def invalidate(*args, **kwargs):
    global _dirty
    _dirty = True


def get(context, settings, force=False):
    """Return the current report, recomputing only when needed."""
    global _report, _stamp, _dirty

    now = time.monotonic()
    stale = _dirty and (now - _stamp) >= THROTTLE
    if force or _report is None or stale:
        try:
            _report = validate.run(context, settings)
        except Exception as error:  # never let a redraw crash on a bad mesh
            print("[ParaForge] validation failed:", error)
            if _report is None:
                _report = validate.Report()
        _stamp = now
        _dirty = False
    return _report


def peek():
    return _report


def clear():
    global _report, _dirty
    _report = None
    _dirty = True


# --------------------------------------------------------------------------
# Depsgraph hook


def _on_depsgraph(scene, depsgraph=None):
    invalidate()


def register():
    handlers = bpy.app.handlers.depsgraph_update_post
    if _on_depsgraph not in handlers:
        handlers.append(_on_depsgraph)
    load_handlers = bpy.app.handlers.load_post
    if _on_load not in load_handlers:
        load_handlers.append(_on_load)


def unregister():
    handlers = bpy.app.handlers.depsgraph_update_post
    if _on_depsgraph in handlers:
        handlers.remove(_on_depsgraph)
    load_handlers = bpy.app.handlers.load_post
    if _on_load in load_handlers:
        load_handlers.remove(_on_load)
    clear()


def _on_load(*args, **kwargs):
    clear()
