# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebuild the topology, then carry the old look onto the new surface.

Decimating collapses edges: it keeps the silhouette honest but leaves a mesh
made of whatever triangles survived, and on an organic asset that comes apart
into spikes and holes long before it reaches a furniture budget. Remeshing
throws the topology away instead and lays a fresh, even surface over the
volume, which is what you want when the geometry is a means to an end and only
the look has to survive.

The catch is that remeshing keeps nothing else. UV maps are gone, vertex
colours are gone, and every material slot but the first is gone. So a remesh
on its own leaves an untextured object, and the operation is only useful as
half of a pair: remesh, then bake the original's colour, relief and roughness
onto the result. Blender's own modifier is used as it is, with its four modes
and their settings exposed, so what the viewport shows during the tweak is
exactly what gets baked onto.
"""

import bpy

from . import i18n, util

_ = i18n.t

#: The modifier's four modes, in the order Blender lists them.
MODES = (
    ("BLOCKS", _("Blocks"), _("Voxels left square. The blocky look, kept")),
    ("SMOOTH", _("Smooth"), _("The same voxels, rounded off")),
    ("SHARP", _("Sharp"),
     _("Rounded, but corners and edges held. The usual choice for an object")),
    ("VOXEL", _("Voxel"),
     _("A newer solver sized in metres rather than by subdivision, with an "
       "adaptivity that spends triangles only where the shape needs them")),
)

#: Settings that mean nothing outside their own mode, so the panel can grey
#: them out rather than show a slider that does nothing.
PER_MODE = {
    "BLOCKS": ("octree_depth", "scale", "threshold"),
    "SMOOTH": ("octree_depth", "scale", "threshold"),
    "SHARP": ("octree_depth", "scale", "threshold", "sharpness"),
    "VOXEL": ("voxel_size", "adaptivity"),
}


def used_by(mode, name):
    """Whether a setting does anything in this mode."""
    return name in PER_MODE.get(mode, ())


def configure(modifier, mode="SHARP", octree_depth=4, scale=0.9,
              sharpness=1.0, threshold=1.0, voxel_size=0.05, adaptivity=0.0,
              remove_disconnected=True, smooth_shading=False):
    """Put the settings on a Remesh modifier, skipping what a build lacks.

    Written attribute by attribute rather than in one sweep because the two
    solvers do not share their settings, and an older Blender is missing some
    of them outright.
    """
    values = {
        "mode": mode,
        "octree_depth": int(octree_depth),
        "scale": float(scale),
        "sharpness": float(sharpness),
        "threshold": float(threshold),
        "voxel_size": float(voxel_size),
        "adaptivity": float(adaptivity),
        "use_remove_disconnected": bool(remove_disconnected),
        "use_smooth_shade": bool(smooth_shading),
    }
    for key, value in values.items():
        if not hasattr(modifier, key):
            continue
        try:
            setattr(modifier, key, value)
        except (AttributeError, TypeError, ValueError):
            continue
    return modifier


def apply_to(context, objects, **kwargs):
    """Remesh each object in place. Returns the names it could not do.

    The modifier is applied rather than left on the stack: everything after
    this reads the mesh, from the triangle count in the report to the UV
    repack the bake needs, and a mesh that is only remeshed at evaluation time
    would have none of it.
    """
    failed = []
    with util.object_mode(context):
        for obj in objects:
            if getattr(obj, "type", None) != "MESH":
                continue
            modifier = obj.modifiers.new("ParaForge Remesh", "REMESH")
            configure(modifier, **kwargs)
            try:
                with context.temp_override(object=obj, active_object=obj):
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
            except RuntimeError as error:
                try:
                    obj.modifiers.remove(modifier)
                except (ReferenceError, RuntimeError):
                    pass
                failed.append("{0}: {1}".format(obj.name, error))
    return failed
