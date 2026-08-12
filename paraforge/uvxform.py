# SPDX-License-Identifier: GPL-3.0-or-later
"""Carry the material's coordinate transform over into the exported UVs.

An FBX holds a mesh and its UV maps. It holds nothing of what a material does
to those coordinates before it samples a texture, and the game rebuilds the
material from scratch anyway: Paralives reads the mesh's first UV map, raw.

Importers put a transform there all the time. A glTF carrying
KHR_texture_transform arrives as a Mapping node, and an asset cut out of an
atlas arrives with its UVs confined to one cell and a Mapping node blowing
that cell back up to the whole image. Blender shows it correctly, because
Blender runs the node. Exported as they stand, those UVs send the game to the
wrong corner of the texture, and the object comes back wearing a smear of one
cell, its unwrapped islands showing through.

The transform is affine, so it does not have to be baked into pixels: applying
it to the coordinates themselves gives exactly what the node gave, at no cost
in quality. That is what this does, on the export copy, leaving the scene as
the artist left it.
"""

import math

from . import i18n

_ = i18n.t

#: An affine 2D transform as (a, b, tx, c, d, ty):
#:     u' = a*u + b*v + tx
#:     v' = c*u + d*v + ty
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

#: Below this, a transform is not worth carrying and not worth mentioning.
EPSILON = 1e-6


class Resolved:
    """What feeds an object's textures, once the node chain is walked."""

    __slots__ = ("matrix", "uv_map", "blockers", "variants")

    def __init__(self, matrix=IDENTITY, uv_map=None, blockers=None,
                 variants=None):
        self.matrix = matrix
        #: The UV layer the material names, when it names one.
        self.uv_map = uv_map
        #: (image name, reason) for every chain that cannot be carried over.
        self.blockers = blockers or []
        #: Images whose transform differs from the one being carried.
        self.variants = variants or []

    @property
    def moves(self):
        return not is_identity(self.matrix)

    @property
    def clean(self):
        return not self.blockers and not self.variants


# --------------------------------------------------------------------------
# Affine arithmetic


def is_identity(matrix):
    return all(abs(a - b) <= EPSILON for a, b in zip(matrix, IDENTITY))


def compose(outer, inner):
    """The transform that applies inner first, then outer."""
    oa, ob, otx, oc, od, oty = outer
    ia, ib, itx, ic, id_, ity = inner
    return (
        oa * ia + ob * ic,
        oa * ib + ob * id_,
        oa * itx + ob * ity + otx,
        oc * ia + od * ic,
        oc * ib + od * id_,
        oc * itx + od * ity + oty,
    )


def invert(matrix):
    """The reverse transform, or None when it collapses the plane."""
    a, b, tx, c, d, ty = matrix
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    ia, ib = d / det, -b / det
    ic, id_ = -c / det, a / det
    return (ia, ib, -(ia * tx + ib * ty), ic, id_, -(ic * tx + id_ * ty))


def key(matrix):
    """A roundable form, so two equal transforms group together."""
    return tuple(round(value, 6) for value in matrix)


def describe(matrix):
    """The transform in the terms the Mapping node shows it in."""
    a, b, tx, c, d, ty = matrix
    return _("scale {0:.3g} x {1:.3g}, offset {2:.3g} / {3:.3g}",
             math.hypot(a, c), math.hypot(b, d), tx, ty)


# --------------------------------------------------------------------------
# Reading the node chain


def _mapping_matrix(node):
    """The Mapping node as an affine transform, or (None, reason).

    Only the Z rotation stays inside the UV plane. A rotation around X or Y
    tilts the coordinates out of it, which no UV map can hold.
    """
    for name in ("Location", "Rotation", "Scale"):
        socket = node.inputs.get(name)
        if socket is not None and socket.links:
            return None, _("its Mapping node is driven by another node")

    location = list(node.inputs["Location"].default_value)
    rotation = list(node.inputs["Rotation"].default_value)
    scale = list(node.inputs["Scale"].default_value)

    if abs(rotation[0]) > EPSILON or abs(rotation[1]) > EPSILON:
        return None, _("its Mapping node rotates outside the UV plane")

    angle = rotation[2]
    cos, sin = math.cos(angle), math.sin(angle)
    sx, sy = scale[0], scale[1]

    # Blender applies scale, then rotation, then location.
    point = (cos * sx, -sin * sy, location[0],
             sin * sx, cos * sy, location[1])

    kind = getattr(node, "vector_type", "POINT")
    if kind == "POINT":
        return point, None
    if kind == "VECTOR":
        # Same, minus the translation.
        return (point[0], point[1], 0.0, point[3], point[4], 0.0), None
    if kind == "TEXTURE":
        # Texture mapping is the inverse: it moves the image, not the point.
        inverse = invert(point)
        if inverse is None:
            return None, _("its Mapping node scales the texture to nothing")
        return inverse, None
    return None, _("its Mapping node is set to {0}", kind)


def _walk(image_node):
    """Follow what feeds an image node's Vector, back to the coordinates.

    Returns (matrix, uv_map, reason). The matrix is what the chain does to the
    UVs; reason is set instead when the chain holds something an FBX cannot
    carry, in which case the caller must leave the coordinates alone.
    """
    socket = image_node.inputs.get("Vector")
    if socket is None or not socket.links:
        # Unlinked means the default: the active UV map, untouched.
        return IDENTITY, None, None

    total = IDENTITY
    link = socket.links[0]
    seen = set()

    while link is not None:
        node = link.from_node
        if id(node) in seen:
            return None, None, _("its coordinates loop back on themselves")
        seen.add(id(node))

        kind = node.bl_idname
        if kind == "ShaderNodeUVMap":
            return total, (node.uv_map or None), None

        if kind == "ShaderNodeTexCoord":
            if link.from_socket.name != "UV":
                return None, None, _(
                    "it is projected with {0} coordinates, which live only in "
                    "Blender", link.from_socket.name)
            return total, None, None

        if kind == "ShaderNodeAttribute":
            # glTF and FBX importers both reach for a named layer this way.
            if getattr(node, "attribute_type", "GEOMETRY") != "GEOMETRY":
                return None, None, _("its coordinates come from an attribute "
                                     "the mesh does not carry")
            return total, (node.attribute_name or None), None

        if kind == "ShaderNodeMapping":
            matrix, reason = _mapping_matrix(node)
            if matrix is None:
                return None, None, reason
            total = compose(total, matrix)
        elif kind == "NodeReroute":
            pass
        else:
            return None, None, _("its coordinates pass through a {0} node, "
                                 "which only Blender can run", node.name)

        following = None
        for name in ("Vector", "Input"):
            inp = node.inputs.get(name)
            if inp is not None and inp.links:
                following = inp.links[0]
                break
        link = following

    # The chain ended on a node with nothing plugged in: default coordinates.
    return total, None, None


def resolve_object(obj):
    """The one transform to bake into this object's UVs.

    An object can hold several textures wired several ways. Only one set of
    coordinates gets exported, so the transform shared by the most textures
    wins, with the base colour breaking a tie: it is the map whose misplacement
    is visible. Anything left over is reported rather than silently dropped.
    """
    if getattr(obj, "type", None) != "MESH":
        return Resolved()

    found = []
    blockers = []
    for slot in getattr(obj, "material_slots", ()):
        material = slot.material
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.bl_idname != "ShaderNodeTexImage" or node.image is None:
                continue
            matrix, uv_map, reason = _walk(node)
            if reason is not None:
                blockers.append((node.image.name, reason))
                continue
            found.append((key(matrix), matrix, uv_map, node.image.name,
                          _feeds_base_colour(node)))

    if not found:
        return Resolved(blockers=blockers)

    groups = {}
    for entry in found:
        groups.setdefault(entry[0], []).append(entry)

    def weight(items):
        return (len(items), any(item[4] for item in items))

    winner = max(groups.values(), key=weight)
    variants = [item[3] for group in groups.values() if group is not winner
                for item in group]

    return Resolved(matrix=winner[0][1], uv_map=winner[0][2],
                    blockers=blockers, variants=variants)


def _feeds_base_colour(node):
    """Whether this image reaches a Base Color socket, one hop or two."""
    for output in node.outputs:
        for link in output.links:
            target = link.to_socket.name
            if target in ("Base Color", "Color"):
                return True
    return False


def resolve(objects):
    """The transform for a whole selection, and what it could not carry."""
    combined = Resolved()
    for obj in objects:
        one = resolve_object(obj)
        combined.blockers.extend(one.blockers)
        combined.variants.extend(one.variants)
        if one.moves and not combined.moves:
            combined.matrix = one.matrix
            combined.uv_map = one.uv_map
        elif one.moves and key(one.matrix) != key(combined.matrix):
            combined.variants.append(getattr(obj, "name", "?"))
    return combined


# --------------------------------------------------------------------------
# Writing it into the coordinates


def layer_for(mesh, name=None):
    """The UV layer the export will send: the named one, else the rendered."""
    layers = getattr(mesh, "uv_layers", None)
    if not layers or not len(layers):
        return None
    if name:
        found = layers.get(name)
        if found is not None:
            return found
    for layer in layers:
        if getattr(layer, "active_render", False):
            return layer
    return layers[0]


def apply_to_mesh(mesh, matrix, name=None):
    """Move a mesh's UVs through the transform. Returns whether it did."""
    if is_identity(matrix):
        return False
    layer = layer_for(mesh, name)
    if layer is None or not len(layer.data):
        return False

    import numpy as np

    a, b, tx, c, d, ty = matrix
    flat = np.empty(len(layer.data) * 2, dtype=np.float32)
    layer.data.foreach_get("uv", flat)
    uv = flat.reshape(-1, 2)
    u = uv[:, 0].copy()
    v = uv[:, 1].copy()
    uv[:, 0] = a * u + b * v + tx
    uv[:, 1] = c * u + d * v + ty
    layer.data.foreach_set("uv", uv.reshape(-1))
    return True


def wire_into(tree, image_nodes, matrix, uv_map=None):
    """Rebuild the transform in a material, for the preview to agree.

    The preview leaves the mesh alone and swaps the material, so its textures
    would be sampled with the raw coordinates and show the very fault the
    export exists to remove. Putting the same transform back in front of them
    makes the preview show what the exported UVs will show.
    """
    if is_identity(matrix) and not uv_map:
        return None

    nodes, links = tree.nodes, tree.links
    source = None
    if uv_map:
        source = nodes.new("ShaderNodeUVMap")
        source.uv_map = uv_map
        source.location = (-1400, 0)

    head = source
    if not is_identity(matrix):
        a, b, tx, c, d, ty = matrix
        mapping = nodes.new("ShaderNodeMapping")
        mapping.vector_type = "POINT"
        mapping.location = (-1100, 0)
        # Recovering scale and rotation from the matrix, which is all a
        # Mapping node can express. The chain that produced it was built the
        # same way, so nothing is lost on the way back.
        mapping.inputs["Location"].default_value = (tx, ty, 0.0)
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.atan2(c, a))
        mapping.inputs["Scale"].default_value = (
            math.hypot(a, c), math.hypot(b, d), 1.0,
        )
        if source is not None:
            links.new(source.outputs["UV"], mapping.inputs["Vector"])
        head = mapping

    if head is None:
        return None
    for node in image_nodes:
        links.new(head.outputs[0], node.inputs["Vector"])
    return head
