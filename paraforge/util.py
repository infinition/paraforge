# SPDX-License-Identifier: GPL-3.0-or-later
"""Small shared helpers."""


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
