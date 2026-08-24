# SPDX-License-Identifier: GPL-3.0-or-later
"""The game's own catalogue pictures, shown in Blender.

The game renders a thumbnail for every item it loads and caches it as a PNG
named after the item's GUID. Reading those back is the difference between a
list of names, where Chaise1 through Chaise9 are indistinguishable, and a list
you can actually pick from.

Blender loads them through a preview collection, which keeps its own GPU
handles, so there is exactly one collection here and it is emptied when the
add-on unregisters.
"""

import os

import bpy.utils.previews

_collection = None
_loaded = {}


def icon_id(path):
    """A Blender icon for an image on disk, or 0 when there is not one.

    Zero is what layout.template_icon takes for nothing, so a missing
    thumbnail draws as a blank rather than raising in the middle of a panel
    redraw, which Blender handles by printing the traceback on every frame.
    """
    global _collection

    if not path or not os.path.isfile(path):
        return 0
    if _collection is None:
        _collection = bpy.utils.previews.new()

    key = _loaded.get(path)
    if key is not None:
        preview = _collection.get(key)
        if preview is not None:
            return preview.icon_id

    key = "t{0}".format(len(_loaded))
    _loaded[path] = key
    try:
        preview = _collection.load(key, path, "IMAGE")
    except (KeyError, RuntimeError):
        return 0
    return preview.icon_id


def clear():
    """Drop every loaded picture, so a deleted file stops being shown."""
    global _collection

    _loaded.clear()
    if _collection is not None:
        _collection.clear()


def register():
    pass


def unregister():
    global _collection

    _loaded.clear()
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
        _collection = None
