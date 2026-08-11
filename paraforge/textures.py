# SPDX-License-Identifier: GPL-3.0-or-later
"""Working out what every texture of an asset is, then rebuilding it.

Paralives assigns import settings from the file name suffix, so naming a file
SofaGrayMask.png rather than sofa_basecolor.png is what removes the manual
per texture pass in the Control Panel. That only works if the add-on knows
what each image actually is, and a model downloaded from the web rarely says.

Three sources of evidence, strongest first:

  1. The node graph. gltfpack strips image names entirely, so a GLB from the
     web lands in Blender as Image_0, Image_1, Image_2 with nothing to read.
     What the image is wired to is then the only fact available, and it is a
     fact rather than a guess.
  2. The file name. Sketchfab exports keep _Diffuse and -ORM, Substance keeps
     _BaseColor and _Normal.
  3. The pixels. A tangent space normal map is unmistakable, and a texture
     with no colour in it is never an albedo.

What comes out is not a copy of the inputs. Paralives shades with albedo,
normal, occlusion and smoothness and has no metallic channel, while glTF
supplies roughness and packs occlusion into the red of an ORM map, so almost
every map has to be rebuilt. See imaging.py for that half.
"""

import os
import re

from . import i18n, imaging, spec

_ = i18n.t

_SPLIT = re.compile(r"[^0-9A-Za-z]+")

#: Set on the image datablock when the user overrides the detected role.
ROLE_KEY = "paraforge_role"

#: How a role was decided, shown in the panel so a wrong guess is obvious.
FROM_USER = "user"
FROM_NAME = "name"
FROM_GRAPH = "graph"
FROM_PIXELS = "pixels"


def pascal_case(text):
    """Turn "old wooden chair_02" into "OldWoodenChair02"."""
    parts = [p for p in _SPLIT.split(text or "") if p]
    out = []
    for part in parts:
        if part.isupper() and len(part) > 1:
            out.append(part.capitalize())
        else:
            out.append(part[:1].upper() + part[1:])
    return "".join(out) or "Asset"


def image_stem(image):
    """Best available base name for an image datablock."""
    path = getattr(image, "filepath_raw", "") or getattr(image, "filepath", "")
    if path:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem:
            return stem
    return os.path.splitext(image.name)[0]


# --------------------------------------------------------------------------
# Node graph evidence


def _principled(material):
    tree = material.node_tree
    output = next(
        (n for n in tree.nodes
         if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output),
        None,
    )
    if output is not None:
        link = next((l for l in output.inputs["Surface"].links), None)
        if link is not None and link.from_node.bl_idname == "ShaderNodeBsdfPrincipled":
            return link.from_node
    return next(
        (n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"),
        None,
    )


_SEPARATORS = {"ShaderNodeSeparateColor", "ShaderNodeSeparateRGB"}
_PASSTHROUGH_INPUTS = {
    "ShaderNodeNormalMap": ("Color",),
    "ShaderNodeBump": ("Height", "Normal"),
    "ShaderNodeInvert": ("Color",),
    "ShaderNodeGamma": ("Color",),
    "ShaderNodeBrightContrast": ("Color",),
    "ShaderNodeHueSaturation": ("Color",),
    "ShaderNodeMapRange": ("Value",),
    "ShaderNodeMath": ("Value",),
    "ShaderNodeMixRGB": ("Color1", "Color2"),
    "ShaderNodeMix": ("A", "B"),
}


def _trace(socket, depth=0, channel=None, inverted=False, seen=None):
    """Walk backwards from an input socket, yielding (image, channel, inverted)."""
    if depth > 8 or socket is None:
        return
    seen = seen if seen is not None else set()

    for link in socket.links:
        node = link.from_node
        key = (id(node), link.from_socket.name, channel)
        if key in seen:
            continue
        seen.add(key)

        idname = node.bl_idname
        if idname == "ShaderNodeTexImage":
            if node.image is not None:
                yield (node.image, channel, inverted)
            continue

        if idname in _SEPARATORS:
            index = next(
                (i for i, out in enumerate(node.outputs)
                 if out.name == link.from_socket.name),
                None,
            )
            for result in _trace(node.inputs[0], depth + 1, index, inverted, seen):
                yield result
            continue

        flip = inverted or idname == "ShaderNodeInvert"
        names = _PASSTHROUGH_INPUTS.get(idname)
        inputs = (
            [node.inputs[n] for n in names if n in node.inputs]
            if names else list(node.inputs)
        )
        for candidate in inputs:
            for result in _trace(candidate, depth + 1, channel, flip, seen):
                yield result


def _gltf_occlusion(tree):
    """The glTF importer hangs occlusion off a side group, not off the BSDF."""
    for node in tree.nodes:
        if node.bl_idname != "ShaderNodeGroup":
            continue
        label = "{0} {1}".format(
            node.name, getattr(node.node_tree, "name", "")
        ).lower()
        if "gltf" not in label:
            continue
        socket = node.inputs.get("Occlusion")
        if socket is not None:
            for result in _trace(socket):
                yield result


def graph_bindings(material):
    """{image: {role: channel}} for everything wired into the shader."""
    bindings = {}
    if material is None or not material.use_nodes or material.node_tree is None:
        return bindings

    def record(image, role, channel, inverted):
        if role == spec.ROUGHNESS and inverted:
            role = spec.GLOSSINESS
        bindings.setdefault(image, {})[role] = channel

    node = _principled(material)
    if node is not None:
        for socket_name, role in spec.SOCKET_ROLES.items():
            socket = node.inputs.get(socket_name)
            if socket is None:
                continue
            for image, channel, inverted in _trace(socket):
                record(image, role, channel, inverted)

    for image, channel, inverted in _gltf_occlusion(material.node_tree):
        record(image, spec.OCCLUSION, channel, inverted)

    return bindings


def _role_from_bindings(roles):
    """Fold what an image is wired to into a single role."""
    if not roles:
        return None

    channels = {role: channel for role, channel in roles.items()}
    packed = {
        role for role, channel in channels.items()
        if channel is not None and spec.ORM_CHANNELS.get(role) == channel
    }
    if len(packed) >= 2 or (
        packed and len(channels) >= 2 and spec.ROUGHNESS in channels
    ):
        return spec.ORM
    if spec.ROUGHNESS in channels and spec.METALLIC in channels:
        return spec.ORM

    order = (
        spec.BASE_COLOR, spec.NORMAL, spec.ORM, spec.OCCLUSION, spec.ROUGHNESS,
        spec.GLOSSINESS, spec.METALLIC, spec.EMISSION, spec.OPACITY,
    )
    for role in order:
        if role in channels:
            return role
    return None


# --------------------------------------------------------------------------
# Name and pixel evidence


def _normalised_name(image):
    return re.sub(r"\s+", "", image_stem(image)).lower()


def role_from_name(image):
    name = _normalised_name(image)
    for fragment, role in spec.NAME_HINTS:
        if fragment in name:
            return role
    return None


def role_from_pixels(image, only_image=False):
    data = imaging.stats(image)
    if data is None:
        return None, data
    if data.looks_like_normal:
        return spec.NORMAL, data
    if data.is_gray:
        # Grey could be occlusion, roughness or metalness. Nothing in the
        # pixels tells them apart, so it stays unknown unless it is all the
        # asset has, in which case it is the albedo of a grey object.
        return (spec.BASE_COLOR if only_image else None), data
    return spec.BASE_COLOR, data


ROLE_KEYS = frozenset(key for key, _label, _description in spec.SOURCE_ROLES)


def stored_role(image):
    role = image.get(ROLE_KEY) if image is not None else None
    return role if role in ROLE_KEYS else None


def set_stored_role(image, role):
    if role:
        image[ROLE_KEY] = role
    elif ROLE_KEY in image:
        del image[ROLE_KEY]


# --------------------------------------------------------------------------
# Sources


class Source:
    """One incoming image, and what the add-on believes it to be."""

    __slots__ = ("image", "role", "evidence", "channels", "stats", "material")

    def __init__(self, image, role, evidence, channels=None, stats=None,
                 material=""):
        self.image = image
        self.role = role
        self.evidence = evidence
        self.channels = channels or {}
        self.stats = stats
        self.material = material

    @property
    def known(self):
        return self.role not in (None, spec.UNKNOWN)

    @property
    def stem(self):
        return image_stem(self.image)

    def channel(self, role, default=0):
        value = self.channels.get(role)
        if value is None:
            value = spec.ORM_CHANNELS.get(role) if self.role == spec.ORM else None
        return default if value is None else value

    def role_label(self):
        return _(spec.role_label(self.role or spec.UNKNOWN))

    def evidence_label(self):
        if self.evidence == FROM_USER:
            return _("Set the role by hand")
        source = {
            FROM_GRAPH: _("the node graph"),
            FROM_NAME: _("the file name"),
            FROM_PIXELS: _("the pixels"),
        }.get(self.evidence, "")
        return (_("from ") + source) if source else ""


def identify(image, bindings=None, only_image=False, material=""):
    """Decide what one image is, using the strongest evidence available."""
    override = stored_role(image)
    if override:
        return Source(image, override, FROM_USER, material=material)

    stem = image_stem(image)
    _base, suffix = spec.split_suffix(stem)
    if suffix:
        return Source(image, spec.PARALIVES, FROM_NAME, material=material)

    role = _role_from_bindings(bindings or {})
    if role:
        return Source(image, role, FROM_GRAPH, dict(bindings or {}),
                      material=material)

    role = role_from_name(image)
    if role:
        return Source(image, role, FROM_NAME, material=material)

    role, data = role_from_pixels(image, only_image=only_image)
    return Source(image, role or spec.UNKNOWN, FROM_PIXELS, stats=data,
                  material=material)


def gather(objects):
    """Every image of the selection, identified, grouped by material."""
    groups = []
    seen_materials = set()

    for obj in objects:
        for slot in getattr(obj, "material_slots", []):
            material = slot.material
            if material is None or material.name in seen_materials:
                continue
            seen_materials.add(material.name)

            bindings = graph_bindings(material)
            images = list(bindings.keys())
            if material.use_nodes and material.node_tree is not None:
                for node in material.node_tree.nodes:
                    image = getattr(node, "image", None)
                    if image is not None and image not in images:
                        images.append(image)

            only = len(images) == 1
            sources = [
                identify(image, bindings.get(image), only, material.name)
                for image in images
            ]
            if sources:
                groups.append((material.name, sources))

    return groups


# --------------------------------------------------------------------------
# Outputs


COPY = "copy"
DETAIL = "detail"
GRAY_MASK = "graymask"
NORMAL_OCCLUSION = "normalocclusion"
SMOOTHNESS = "smoothness"


class Output:
    """One PNG that will land in the mod folder."""

    __slots__ = ("suffix", "target_name", "kind", "sources", "note")

    def __init__(self, suffix, target_name, kind, sources, note=""):
        self.suffix = suffix
        self.target_name = target_name
        self.kind = kind
        self.sources = sources
        self.note = note

    @property
    def rebuilt(self):
        return self.kind != COPY

    def source_names(self):
        return ", ".join(image_stem(s.image) for s in self.sources)


class Plan:
    """Everything that will be written, and everything that will not."""

    def __init__(self):
        self.groups = []
        self.sources = []
        self.outputs = []
        self.notes = []
        self.dropped = []

    @property
    def unknown(self):
        return [s for s in self.sources if not s.known]

    @property
    def multi_group(self):
        return len(self.groups) > 1

    def by_suffix(self, suffix):
        return [o for o in self.outputs if o.suffix == suffix]

    def missing_recommended(self):
        present = {o.suffix for o in self.outputs}
        return [s for s in spec.RECOMMENDED_SUFFIXES if s not in present]

    def duplicate_suffixes(self):
        counts = {}
        for item in self.outputs:
            counts[item.suffix] = counts.get(item.suffix, 0) + 1
        return [s for s in spec.UNIQUE_SUFFIXES if counts.get(s, 0) > 1]


def _first(sources, *roles):
    for role in roles:
        for source in sources:
            if source.role == role:
                return source
    return None


def build_plan(objects, asset_name, recolourable=False):
    """Work out the complete set of files, without touching a single pixel."""
    plan = Plan()
    base = pascal_case(asset_name)
    groups = gather(objects)
    plan.groups = [name for name, _sources in groups]

    for material_name, sources in groups:
        plan.sources.extend(sources)

    qualify = len(groups) > 1
    for material_name, sources in groups:
        prefix = base + (pascal_case(material_name) if qualify else "")
        _plan_group(plan, prefix, sources, recolourable)

    if qualify:
        plan.notes.append(_(
            "Several materials carry their own maps. Paralives assigns one "
            "surface per mesh, so bake them into one atlas or split the item "
            "into several meshes"
        ))
    if plan.dropped:
        plan.notes.append(_(
            "Metallic and emission maps are dropped, Paralives has no channel "
            "for them"
        ))
    return plan


def _plan_group(plan, prefix, sources, recolourable):
    def name(suffix):
        return "{0}{1}.png".format(prefix, suffix)

    # Already Paralives shaped: keep the bytes, only fix the base name.
    for source in sources:
        if source.role == spec.PARALIVES:
            _stem, suffix = spec.split_suffix(source.stem)
            plan.outputs.append(Output(suffix, name(suffix), COPY, [source]))

    base_color = _first(sources, spec.BASE_COLOR)
    emission = _first(sources, spec.EMISSION)
    normal = _first(sources, spec.NORMAL)
    occlusion = _first(sources, spec.OCCLUSION, spec.ORM)
    roughness = _first(sources, spec.ROUGHNESS, spec.GLOSSINESS, spec.ORM)
    metallic = _first(sources, spec.METALLIC, spec.ORM)

    if base_color is not None:
        if recolourable:
            plan.outputs.append(Output(
                "GrayMask", name("GrayMask"), GRAY_MASK, [base_color],
                _("A saturated base colour becomes a Detail map, a gray one "
                  "becomes a GrayMask"),
            ))
        elif emission is not None:
            plan.outputs.append(Output(
                "Detail", name("Detail"), DETAIL, [base_color, emission],
            ))
        else:
            plan.outputs.append(Output(
                "Detail", name("Detail"), COPY, [base_color],
            ))

    if normal is not None or occlusion is not None:
        used = [s for s in (normal, occlusion) if s is not None]
        # The same ORM image can be both, do not list it twice.
        unique = []
        for source in used:
            if source not in unique:
                unique.append(source)
        plan.outputs.append(Output(
            "NormalOcclusion", name("NormalOcclusion"), NORMAL_OCCLUSION,
            unique,
            _("Occlusion is packed into the alpha of the normal map"),
        ))

    if roughness is not None or metallic is not None:
        unique = []
        for source in (roughness, metallic):
            if source is not None and source not in unique:
                unique.append(source)
        plan.outputs.append(Output(
            "Smoothness", name("Smoothness"), SMOOTHNESS, unique,
            _("Smoothness is rebuilt as 1 - roughness"),
        ))

    for source in sources:
        if source.role in spec.DROPPED_ROLES and source.role != spec.METALLIC:
            plan.dropped.append(source)
        elif source.role == spec.METALLIC and metallic is None:
            plan.dropped.append(source)


# --------------------------------------------------------------------------
# Writing


def write(output, target_dir):
    """Produce one PNG in the mod folder. Returns the written path."""
    destination = os.path.join(target_dir, output.target_name)

    if output.kind == COPY:
        return imaging.copy_as_png(output.sources[0].image, destination)

    array = render(output)
    if array is None:
        raise ValueError(_("{0} is too large to rebuild ({1} x {2})",
                           output.target_name,
                           *imaging.dimensions(output.sources[0].image)))
    return imaging.write_png(array, destination, "ParaForge_" + output.suffix)


def render(output):
    """The pixels of a rebuilt map, or None when a source cannot be read."""
    read = {}
    for source in output.sources:
        pixels = imaging.read(source.image)
        if pixels is None:
            return None
        read[source.image.name] = pixels

    def pixels_of(source):
        return read.get(source.image.name) if source is not None else None

    if output.kind == DETAIL:
        base = output.sources[0]
        emission = output.sources[1] if len(output.sources) > 1 else None
        return imaging.build_detail(pixels_of(base), pixels_of(emission))

    if output.kind == GRAY_MASK:
        return imaging.build_gray_mask(pixels_of(output.sources[0]))

    if output.kind == NORMAL_OCCLUSION:
        normal = _first(output.sources, spec.NORMAL)
        occlusion = _first(output.sources, spec.OCCLUSION, spec.ORM)
        return imaging.build_normal_occlusion(
            pixels_of(normal), pixels_of(occlusion),
            occlusion.channel(spec.OCCLUSION) if occlusion else 0,
        )

    if output.kind == SMOOTHNESS:
        roughness = _first(output.sources, spec.ROUGHNESS, spec.ORM)
        glossy = _first(output.sources, spec.GLOSSINESS)
        metallic = _first(output.sources, spec.METALLIC, spec.ORM)
        source = roughness if roughness is not None else glossy
        return imaging.build_smoothness(
            pixels_of(source),
            source.channel(spec.ROUGHNESS, 0) if source else 1,
            # Glossiness already runs the right way, roughness is the opposite.
            invert=roughness is not None,
            metallic=pixels_of(metallic),
            metallic_channel=metallic.channel(spec.METALLIC, 0) if metallic else 2,
        )

    return None


def preview(output):
    """A one line description of how a map will be produced."""
    if output.kind == COPY:
        return "{0} {1}".format(_("copied"), output.source_names())
    return "{0} {1}{2}".format(_("rebuilt"), _("from "), output.source_names())
