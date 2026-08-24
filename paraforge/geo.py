# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry measurements shared by the validator, the overlay and the fixers.

Everything here works on the evaluated mesh, so modifiers are taken into
account exactly the way the FBX exporter will see them.
"""

import numpy as np

from . import spec


class Measurement:
    """World space measurements of a set of objects."""

    __slots__ = ("min", "max", "triangles", "ngons", "vertices", "empty")

    def __init__(self):
        self.min = np.zeros(3, dtype=np.float64)
        self.max = np.zeros(3, dtype=np.float64)
        self.triangles = 0
        self.ngons = 0
        self.vertices = 0
        self.empty = True

    @property
    def size(self):
        return self.max - self.min

    @property
    def center(self):
        return (self.max + self.min) * 0.5

    def anchor_value(self, axis_index, anchor):
        """The coordinate the rule for this axis constrains to zero."""
        if anchor == "center":
            return float(self.center[axis_index])
        if anchor == "min":
            return float(self.min[axis_index])
        if anchor == "max":
            return float(self.max[axis_index])
        return 0.0


def _world_coords(obj, depsgraph):
    """Vertex coordinates of the evaluated object, in world space."""
    if depsgraph is not None:
        evaluated = obj.evaluated_get(depsgraph)
    else:
        evaluated = obj
    try:
        mesh = evaluated.to_mesh()
    except (RuntimeError, AttributeError):
        return None, None
    if mesh is None:
        return None, None

    count = len(mesh.vertices)
    if count == 0:
        evaluated.to_mesh_clear()
        return np.zeros((0, 3)), mesh

    flat = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", flat)
    coords = flat.reshape(count, 3)

    matrix = np.array(evaluated.matrix_world, dtype=np.float64)
    rotated = coords @ matrix[:3, :3].T + matrix[:3, 3]
    return rotated, (evaluated, mesh)


def _face_stats(mesh):
    """Triangle count after triangulation, plus the number of n-gons."""
    polygon_count = len(mesh.polygons)
    if polygon_count == 0:
        return 0, 0
    sizes = np.empty(polygon_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    triangles = int(np.sum(np.maximum(sizes - 2, 0)))
    ngons = int(np.count_nonzero(sizes > 4))
    return triangles, ngons


def measure(objects, depsgraph=None):
    """Measure a list of mesh objects as if they were one asset."""
    result = Measurement()
    lows = []
    highs = []

    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        coords, handle = _world_coords(obj, depsgraph)
        if handle is None:
            continue
        evaluated, mesh = handle
        try:
            if coords is not None and len(coords):
                lows.append(coords.min(axis=0))
                highs.append(coords.max(axis=0))
                result.vertices += len(coords)
            triangles, ngons = _face_stats(mesh)
            result.triangles += triangles
            result.ngons += ngons
        finally:
            evaluated.to_mesh_clear()

    if lows:
        result.min = np.min(np.stack(lows), axis=0)
        result.max = np.max(np.stack(highs), axis=0)
        result.empty = False
    return result


def anchor_offsets(measurement, item_type):
    """Per axis correction needed to satisfy the origin rule.

    Returns a list of three floats to add to the geometry.
    """
    anchors = spec.ITEM_TYPES[item_type]["anchors"]
    offsets = [0.0, 0.0, 0.0]
    for index, axis in enumerate("xyz"):
        anchor = anchors.get(axis)
        if anchor is None:
            continue
        offsets[index] = -measurement.anchor_value(index, anchor)
    return offsets


def transform_is_clean(obj):
    """True when rotation and scale are already baked into the mesh data."""
    rotation_ok = all(
        abs(value) <= 1e-5 for value in obj.rotation_euler
    ) if obj.rotation_mode not in {"QUATERNION", "AXIS_ANGLE"} else _quat_is_identity(obj)
    scale_ok = all(abs(value - 1.0) <= 1e-5 for value in obj.scale)
    return rotation_ok and scale_ok


def _quat_is_identity(obj):
    if obj.rotation_mode == "QUATERNION":
        q = obj.rotation_quaternion
        return abs(q.w - 1.0) <= 1e-5 and all(abs(v) <= 1e-5 for v in (q.x, q.y, q.z))
    angle = obj.rotation_axis_angle[0]
    return abs(angle) <= 1e-5


def color_zones(objects):
    """Inspect the active colour attribute of every object.

    Returns (zones_found, illegal_samples, objects_without_attribute).
    """
    zones = set()
    illegal = []
    missing = []

    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        mesh = obj.data
        attributes = getattr(mesh, "color_attributes", None)
        if not attributes or len(attributes) == 0:
            missing.append(obj.name)
            continue
        attribute = attributes.active_color or attributes[0]
        count = len(attribute.data)
        if count == 0:
            missing.append(obj.name)
            continue

        flat = np.empty(count * 4, dtype=np.float64)
        attribute.data.foreach_get("color", flat)
        colors = flat.reshape(count, 4)[:, :3]

        # Only look at distinct colours, a mesh can carry millions of loops.
        unique = np.unique(np.round(colors, 3), axis=0)
        for rgb in unique:
            zone = spec.classify_color(tuple(float(v) for v in rgb))
            if zone is None:
                if len(illegal) < 8:
                    illegal.append((obj.name, tuple(round(float(v), 3) for v in rgb)))
            else:
                zones.add(zone)

    return zones, illegal, missing


def uv_layer_count(objects):
    counts = []
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        counts.append(len(obj.data.uv_layers))
    return counts


def seat_height(objects, depsgraph=None):
    """Where the mesh actually offers something to sit on, in metres.

    The seat is the largest single horizontal surface the item has, above the
    floor. Not an average: averaging a chair mixes its seat with its armrests
    and its backrest top, and the answer belongs to none of them.

    So every upward facing triangle is binned by height, the heaviest bin by
    area wins, and the answer is the area weighted height of that cluster. Run
    over the game's own furniture it returns 0.448 m across 28 chairs, 0.450 m
    across 12 benches and 0.649 m across 9 stools, which is the check that it
    measures the thing a Para sits on rather than whatever is nearest the top.

    Returns (height above the item's base, area of that surface), or
    (None, 0.0) when the item has no horizontal surface clear of the floor.
    """
    measurement = measure(objects, depsgraph)
    if measurement.empty:
        return None, 0.0
    base = float(measurement.min[2])

    heights = []
    areas = []
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph) if depsgraph else obj
        try:
            mesh = evaluated.to_mesh()
        except (RuntimeError, AttributeError):
            continue
        if mesh is None:
            continue
        try:
            # Blender computes these lazily, and older builds need the ask.
            if hasattr(mesh, "calc_loop_triangles"):
                mesh.calc_loop_triangles()
            matrix = np.array(evaluated.matrix_world, dtype=np.float64)
            rotation = matrix[:3, :3]
            # Area lives in the mesh's own space, so it has to be carried
            # into the world the same way the coordinates are.
            stretch = abs(np.linalg.det(rotation)) ** (2.0 / 3.0)
            for triangle in mesh.loop_triangles:
                normal = rotation @ np.array(triangle.normal, dtype=np.float64)
                length = np.linalg.norm(normal)
                if length < 1e-9 or normal[2] / length < spec.SEAT_NORMAL_MIN:
                    continue
                centre = rotation @ np.array(triangle.center, dtype=np.float64)
                height = float(centre[2] + matrix[2, 3]) - base
                if height < spec.SEAT_FLOOR_CLEARANCE:
                    continue
                heights.append(height)
                areas.append(float(triangle.area) * stretch)
        finally:
            evaluated.to_mesh_clear()

    if not heights:
        return None, 0.0

    heights = np.array(heights)
    areas = np.array(areas)
    bins = np.round(heights / (spec.SEAT_CLUSTER * 0.5)).astype(np.int64)
    best = None
    best_area = -1.0
    for value in np.unique(bins):
        total = float(areas[bins == value].sum())
        if total > best_area:
            best_area = total
            best = value

    near = np.abs(heights - best * spec.SEAT_CLUSTER * 0.5) <= spec.SEAT_CLUSTER
    area = float(areas[near].sum())
    if area < spec.SEAT_MIN_AREA:
        return None, area
    return float(np.average(heights[near], weights=areas[near])), area
