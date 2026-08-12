# SPDX-License-Identifier: GPL-3.0-or-later
"""Small shared helpers."""


class object_mode:
    """Run in object mode, then put the user back where they were.

    Applying a modifier is refused outright from edit mode:

        Operator bpy.ops.object.modifier_apply.poll() This modifier operation
        is not allowed from Edit mode

    and an operator that reports that as a per object warning looks, from the
    outside, like a tool that quietly does nothing. Leaving the mode as it was
    found matters just as much: someone who was mid edit expects to still be
    there when the button is done.
    """

    def __init__(self, context):
        self.context = context
        self.previous = None

    def __enter__(self):
        import bpy

        obj = getattr(self.context, "object", None)
        mode = getattr(obj, "mode", "OBJECT")
        if obj is not None and mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
                self.previous = mode
            except RuntimeError:
                self.previous = None
        return self

    def __exit__(self, *exc):
        import bpy

        if self.previous is None:
            return False
        try:
            bpy.ops.object.mode_set(mode=self.previous)
        except (RuntimeError, TypeError):
            pass
        return False


def wrap(text, width):
    """Break a sentence into lines that fit a fixed width label column."""
    words = (text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def columns(context, reserve=4):
    """How many characters fit across the current region.

    A hard coded wrap width overflows a narrow sidebar and wastes half of a
    wide one, and the sidebar is resizable, so it is measured instead.
    """
    region = getattr(context, "region", None)
    scale = 1.0
    try:
        scale = context.preferences.system.ui_scale or 1.0
    except AttributeError:
        pass
    width = getattr(region, "width", 0) or 300
    fit = int(width / (7.2 * scale)) - reserve
    return max(16, min(fit, 110))


def wrap_to(context, text, reserve=4):
    return wrap(text, columns(context, reserve))
