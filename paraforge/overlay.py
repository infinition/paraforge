# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport guides and heads up checklist.

The whole point of the add-on: you should be able to tell at a glance whether
the asset is oriented, centred and sized the way Paralives wants, without
launching the game.
"""

import blf
import gpu
from gpu_extras.batch import batch_for_shader

import bpy

from . import cache, i18n, props, spec, validate

_ = i18n.t

_handle_3d = None
_handle_2d = None
_shader = None

STATUS_COLORS = {
    validate.OK: (0.35, 0.85, 0.45, 1.0),
    validate.WARN: (1.00, 0.72, 0.20, 1.0),
    validate.FAIL: (1.00, 0.35, 0.35, 1.0),
    validate.TODO: (0.55, 0.70, 1.00, 1.0),
}

GRID_COLOR = (0.45, 0.50, 0.60, 0.35)
GRID_MAJOR = (0.60, 0.68, 0.80, 0.65)
ARROW_COLOR = (0.30, 0.90, 0.45, 0.95)
BOUNDS_OK = (0.35, 0.85, 0.45, 0.85)
BOUNDS_BAD = (1.00, 0.35, 0.35, 0.95)
ORIGIN_COLOR = (1.00, 0.85, 0.25, 1.0)

# The seat guide. The two heights the game's own furniture sits at, 0.45 for a
# chair and 0.65 for a stool, are drawn faintly. The height this mesh actually
# offers is drawn solidly, in green while a Para could plausibly use it and in
# amber once it is higher or lower than anything the game seats one on.
SEAT_BAND_COLOR = (0.55, 0.70, 1.00, 0.30)
SEAT_OK_COLOR = (0.35, 0.85, 0.45, 0.95)
SEAT_BAD_COLOR = (1.00, 0.72, 0.20, 0.95)
SEAT_FILL_OK = (0.35, 0.85, 0.45, 0.16)
SEAT_FILL_BAD = (1.00, 0.72, 0.20, 0.16)


def _get_shader():
    global _shader
    if _shader is None:
        _shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    return _shader


def _draw_lines(coords, color, width=1.0):
    if not coords:
        return
    shader = _get_shader()
    gpu.state.line_width_set(width)
    batch = batch_for_shader(shader, "LINES", {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.line_width_set(1.0)


def _draw_tris(coords, color):
    if not coords:
        return
    shader = _get_shader()
    batch = batch_for_shader(shader, "TRIS", {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


# --------------------------------------------------------------------------
# 3D guides


def _grid_lines(tile, extent):
    span = tile * extent
    lines = []
    for step in range(-extent, extent + 1):
        offset = step * tile
        lines.extend([(offset, -span, 0.0), (offset, span, 0.0)])
        lines.extend([(-span, offset, 0.0), (span, offset, 0.0)])
    return lines


def _axis_lines(tile, extent):
    span = tile * extent
    return [
        (-span, 0.0, 0.0), (span, 0.0, 0.0),
        (0.0, -span, 0.0), (0.0, span, 0.0),
    ]


def _arrow_lines(tile):
    """A big arrow along Y+, the direction the item must face."""
    length = tile * 1.35
    head = tile * 0.30
    width = tile * 0.17
    z = tile * 0.012
    return [
        (0.0, 0.0, z), (0.0, length, z),
        (0.0, length, z), (-width, length - head, z),
        (0.0, length, z), (width, length - head, z),
        (-width, length - head, z), (width, length - head, z),
    ]


def _seat_rect(low, high, z):
    """Outline of a horizontal rectangle over the item's footprint."""
    x0, y0 = float(low[0]), float(low[1])
    x1, y1 = float(high[0]), float(high[1])
    corners = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    lines = []
    for index in range(4):
        lines.append(corners[index])
        lines.append(corners[(index + 1) % 4])
    return lines


def _seat_fill(low, high, z):
    x0, y0 = float(low[0]), float(low[1])
    x1, y1 = float(high[0]), float(high[1])
    return [
        (x0, y0, z), (x1, y0, z), (x1, y1, z),
        (x0, y0, z), (x1, y1, z), (x0, y1, z),
    ]


def _sit_direction(low, high, z):
    """Where the knees go: a short arrow along Y+, at seat height.

    Along the floor arrow, not against it. Measured rather than reasoned:
    imported into Blender, 43 of the game's 48 chairs and armchairs put their
    backrest on the Y- side, 4 are symmetrical enough not to say, and 1
    disagrees. So a Para sits facing Y+, and the backrest goes behind.

    Drawing it again up at seat height is the difference between knowing which
    way the item faces and knowing which way somebody sitting on it will look.
    """
    x0, y0 = float(low[0]), float(low[1])
    x1, y1 = float(high[0]), float(high[1])
    mid_x = (x0 + x1) * 0.5
    depth = max(y1 - y0, 1e-4)
    tip = y1 + depth * 0.45
    head = depth * 0.18
    width = max(x1 - x0, 1e-4) * 0.12
    return [
        (mid_x, y0 + depth * 0.5, z), (mid_x, tip, z),
        (mid_x, tip, z), (mid_x - width, tip - head, z),
        (mid_x, tip, z), (mid_x + width, tip - head, z),
    ]


def _draw_seat_guide(measurement, seat_height):
    """The band the game's chairs live in, and where this mesh actually sits."""
    low, high = measurement.min, measurement.max
    base = float(low[2])
    for edge in (spec.SEAT_CHAIR, spec.SEAT_STOOL):
        _draw_lines(_seat_rect(low, high, base + edge), SEAT_BAND_COLOR, 1.0)

    if seat_height is None:
        return

    inside = spec.SEAT_MIN <= seat_height <= spec.SEAT_MAX
    line_color = SEAT_OK_COLOR if inside else SEAT_BAD_COLOR
    fill_color = SEAT_FILL_OK if inside else SEAT_FILL_BAD
    z = base + seat_height
    _draw_tris(_seat_fill(low, high, z), fill_color)
    _draw_lines(_seat_rect(low, high, z), line_color, 2.5)
    _draw_lines(_sit_direction(low, high, z), line_color, 2.5)


def _origin_marker(tile):
    size = tile * 0.09
    return [
        (-size, 0.0, 0.0), (size, 0.0, 0.0),
        (0.0, -size, 0.0), (0.0, size, 0.0),
        (0.0, 0.0, -size), (0.0, 0.0, size),
    ]


def _box_lines(low, high):
    x0, y0, z0 = float(low[0]), float(low[1]), float(low[2])
    x1, y1, z1 = float(high[0]), float(high[1]), float(high[2])
    corners = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    edges = (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )
    lines = []
    for a, b in edges:
        lines.append(corners[a])
        lines.append(corners[b])
    return lines


def _anchor_hint(measurement, item_type, tile):
    """Short line segments showing where the geometry should be but is not."""
    anchors = spec.ITEM_TYPES[item_type]["anchors"]
    from . import geo

    offsets = geo.anchor_offsets(measurement, item_type)
    lines = []
    reach = tile * 0.6
    for index, axis in enumerate("xyz"):
        if anchors.get(axis) is None:
            continue
        if abs(offsets[index]) <= spec.POSITION_TOLERANCE:
            continue
        current = measurement.anchor_value(index, anchors[axis])
        start = [0.0, 0.0, 0.0]
        end = [0.0, 0.0, 0.0]
        start[index] = current
        end[index] = 0.0
        # Offset the segment sideways so it does not hide inside the mesh.
        side = (index + 1) % 3
        start[side] = end[side] = reach
        lines.append(tuple(start))
        lines.append(tuple(end))
    return lines


def draw_3d():
    context = bpy.context
    settings = props.settings(context)
    if settings is None or not settings.show_overlay:
        return

    tile = max(settings.tile_size, 1e-4)
    extent = settings.grid_extent

    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")

    if settings.show_grid:
        _draw_lines(_grid_lines(tile, extent), GRID_COLOR, 1.0)
        _draw_lines(_axis_lines(tile, extent), GRID_MAJOR, 2.0)

    gpu.state.depth_test_set("NONE")

    if settings.show_arrow:
        _draw_lines(_arrow_lines(tile), ARROW_COLOR, 3.0)
    _draw_lines(_origin_marker(tile), ORIGIN_COLOR, 2.0)

    report = cache.peek()
    if (settings.show_seat and report is not None
            and report.measurement is not None
            and not report.measurement.empty
            and any(c.key == "seat" for c in report.checks)):
        _draw_seat_guide(report.measurement, report.seat_height)

    if settings.show_bounds and report is not None and report.measurement is not None:
        measurement = report.measurement
        if not measurement.empty:
            origin_check = next(
                (c for c in report.checks if c.key == "origin"), None
            )
            bad = origin_check is not None and origin_check.status == validate.FAIL
            color = BOUNDS_BAD if bad else BOUNDS_OK
            _draw_lines(_box_lines(measurement.min, measurement.max), color, 2.0)
            if bad:
                _draw_lines(
                    _anchor_hint(measurement, settings.item_type, tile),
                    BOUNDS_BAD, 4.0,
                )

    gpu.state.blend_set("NONE")
    gpu.state.depth_test_set("LESS_EQUAL")


# --------------------------------------------------------------------------
# 2D checklist


def _set_font_size(font_id, size):
    try:
        blf.size(font_id, size)
    except TypeError:
        blf.size(font_id, size, 72)


def _text_width(font_id, text):
    try:
        return blf.dimensions(font_id, text)[0]
    except (TypeError, RuntimeError):
        return len(text) * 7.0


def _dot(x, y, size, color):
    half = size * 0.5
    coords = [
        (x - half, y - half), (x + half, y - half), (x + half, y + half),
        (x - half, y - half), (x + half, y + half), (x - half, y + half),
    ]
    shader = _get_shader()
    batch = batch_for_shader(shader, "TRIS", {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _panel_background(x, y, width, height):
    coords = [
        (x, y), (x + width, y), (x + width, y + height),
        (x, y), (x + width, y + height), (x, y + height),
    ]
    _draw_tris(coords, (0.08, 0.09, 0.11, 0.82))
    outline = [
        (x, y), (x + width, y),
        (x + width, y), (x + width, y + height),
        (x + width, y + height), (x, y + height),
        (x, y + height), (x, y),
    ]
    _draw_lines(outline, (1.0, 1.0, 1.0, 0.10), 1.0)


# --------------------------------------------------------------------------
# Where the checklist is allowed to sit
#
# The 3D viewport draws its toolbar, its sidebar and its own text overlay on
# top of the very region this handler paints into, so anything drawn at a
# fixed corner ends up underneath them. These measure the furniture and hand
# back the rectangle that is actually free.


def _region_insets(context):
    """Pixels taken by the viewport's own panels, per edge."""
    area = context.area
    left = right = top = bottom = 0
    if area is None:
        return left, right, top, bottom

    overlap = context.preferences.system.use_region_overlap
    for region in area.regions:
        if region.width <= 1 or region.height <= 1:
            continue
        kind = region.type
        if kind == "TOOLS":
            # Without region overlap the window region is already shrunk.
            left = max(left, region.width if overlap else 0)
        elif kind == "UI":
            right = max(right, region.width if overlap else 0)
        elif kind == "HUD":
            # The redo panel, bottom left, appears after any operator.
            bottom = max(bottom, region.height)
        elif kind == "ASSET_SHELF":
            bottom = max(bottom, region.height)
        elif kind == "TOOL_HEADER" and overlap:
            top = max(top, region.height)
    return left, right, top, bottom


#: Blender's own text overlay, measured in the viewport: the first baseline
#: sits about two lines below the region top, and each line is one of these.
_TEXT_LINE = 19.0
_TEXT_TOP_GAP = 2.2


def _text_overlay_height(context, scale):
    """Room for Blender's own view name, collection and statistics."""
    space = context.space_data
    overlay = getattr(space, "overlay", None)
    if overlay is None or not getattr(overlay, "show_overlays", True):
        return 0
    if not getattr(overlay, "show_text", False):
        return 0
    lines = 2  # the view name, then the collection and active object
    if getattr(overlay, "show_stats", False):
        lines += 7
    return int((lines + _TEXT_TOP_GAP) * _TEXT_LINE * scale)


def _navigation_gizmo_width(context, scale):
    """The axis ball and the zoom column, top right of the viewport."""
    space = context.space_data
    if not getattr(space, "show_gizmo", True):
        return 0
    if not getattr(space, "show_gizmo_navigate", True):
        return 0
    return int(80 * scale)


def _anchor(context, settings, width, height, scale):
    """Bottom left corner of the panel, dodging everything already drawn."""
    region = context.region
    left_in, right_in, top_in, bottom_in = _region_insets(context)
    margin = int(12 * scale)

    free_left = left_in + margin
    free_right = region.width - right_in - margin
    free_top = region.height - top_in - margin
    free_bottom = bottom_in + margin

    corner = settings.hud_corner
    if corner.endswith("LEFT"):
        x = free_left
        # Blender prints the view name and the active collection top left.
        if corner.startswith("TOP"):
            free_top -= _text_overlay_height(context, scale)
    else:
        if corner.startswith("TOP"):
            free_right -= _navigation_gizmo_width(context, scale)
        x = free_right - width

    y = free_top - height if corner.startswith("TOP") else free_bottom

    x += int(settings.hud_offset_x * scale)
    y += int(settings.hud_offset_y * scale)

    # Never let a nudge or a narrow viewport push it off screen.
    x = max(min(x, region.width - width - margin), margin)
    y = max(min(y, region.height - height - margin), margin)
    return x, y


def visible_checks(report, settings):
    if settings.hud_only_problems:
        return [c for c in report.checks if c.status != validate.OK]
    return list(report.checks)


def draw_2d():
    context = bpy.context
    settings = props.settings(context)
    if settings is None or not settings.show_hud:
        return

    report = cache.peek()
    if report is None or not report.checks:
        return

    region = context.region
    if region is None or region.width < 260 or region.height < 160:
        return

    checks = visible_checks(report, settings)
    scale = context.preferences.system.ui_scale
    font = 0
    head_size = int(12 * scale)
    text_size = int(11 * scale)
    line_height = int(19 * scale)
    pad = int(10 * scale)
    indent = int(18 * scale)

    counts = report.counts
    headline = "PARAFORGE   " + _(
        "{0} ok   {1} warn   {2} blocking",
        counts[validate.OK], counts[validate.WARN], counts[validate.FAIL],
    )

    _set_font_size(font, head_size)
    width = _text_width(font, headline)
    _set_font_size(font, text_size)
    labels = [check.label for check in checks]
    for label in labels:
        width = max(width, _text_width(font, label) + indent)
    if not checks:
        width = max(width, _text_width(font, _("Everything is green")) + indent)

    width = int(width) + pad * 2
    rows = len(checks) + (1 if checks else 2)
    height = rows * line_height + pad

    # A viewport can always be narrower than the checklist wants to be.
    width = min(width, region.width - int(24 * scale))

    x, y = _anchor(context, settings, width, height, scale)

    gpu.state.blend_set("ALPHA")
    _panel_background(x, y, width, height)

    text_x = x + pad
    baseline = y + height - line_height + int(4 * scale)

    _set_font_size(font, head_size)
    blf.color(font, 0.92, 0.93, 0.96, 1.0)
    blf.position(font, text_x, baseline, 0)
    blf.draw(font, headline)
    baseline -= line_height

    _set_font_size(font, text_size)
    if not checks:
        color = STATUS_COLORS[validate.OK]
        blf.color(font, *color)
        blf.position(font, text_x + indent, baseline, 0)
        blf.draw(font, _("Everything is green"))
    for check, label in zip(checks, labels):
        color = STATUS_COLORS.get(check.status, (1, 1, 1, 1))
        _dot(text_x + int(4 * scale), baseline + int(4 * scale),
             int(8 * scale), color)
        blf.color(font, *color)
        blf.position(font, text_x + indent, baseline, 0)
        blf.draw(font, label)
        baseline -= line_height

    gpu.state.blend_set("NONE")


# --------------------------------------------------------------------------


def register():
    global _handle_3d, _handle_2d
    if _handle_3d is None:
        _handle_3d = bpy.types.SpaceView3D.draw_handler_add(
            draw_3d, (), "WINDOW", "POST_VIEW"
        )
    if _handle_2d is None:
        _handle_2d = bpy.types.SpaceView3D.draw_handler_add(
            draw_2d, (), "WINDOW", "POST_PIXEL"
        )


def unregister():
    global _handle_3d, _handle_2d, _shader
    if _handle_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_3d, "WINDOW")
        _handle_3d = None
    if _handle_2d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_2d, "WINDOW")
        _handle_2d = None
    _shader = None
