# SPDX-License-Identifier: GPL-3.0-or-later
"""See what the game will show, before writing anything into a mod.

The viewport shows the source material: whatever glTF or a marketplace gave
you, with its roughness, its ORM packing and its metallic. The game shows
something else, because ParaForge rebuilds those channels into the four maps
Paralives reads and the game drops what it has no channel for.

Guessing at the difference costs a restart. This writes the textures exactly
as the export would, to a scratch folder, reads them back, and builds a
material from them. What the viewport shows is then the same data the game
will be handed, with the smoothness turned back into roughness the way the
shader does it.

The original materials are kept on the object and put back on the way out.
"""

import os
import tempfile

import bpy

from . import i18n, textures

_ = i18n.t

MATERIAL_SUFFIX = "_ParaForgePreview"
STASH = "paraforge_materials"

#: Where the previewed PNGs are written. Scratch, never the mod folder.
_folder = None

# The preview replaces the materials, so anything that reads the materials
# afterwards would read the preview instead of the source: the plan would say
# "copied PapanierDetail" where it used to say "rebuilt from Image_2, Image_1",
# and a later export would copy an already converted texture. The plan that
# produced the preview is therefore frozen for as long as it is on.
_frozen_plan = None


def frozen():
    return _frozen_plan


def scratch():
    global _folder
    if _folder is None or not os.path.isdir(_folder):
        _folder = tempfile.mkdtemp(prefix="paraforge_preview_")
    return _folder


def is_on(objects):
    return any(STASH in obj for obj in objects)


# --------------------------------------------------------------------------


def build_material(name, written, smoothness=None):
    """A Principled BSDF fed the way Paralives feeds its own shader.

    written maps a suffix to the PNG the export would put in the mod, so what
    is wired up here is the file itself and not the source it came from.

    smoothness is the single value the surface will carry. The game has no slot
    for a smoothness texture, so using the map here would show a per pixel
    gloss the game will never produce, and a mostly white map turns the object
    into a mirror of the viewport's own lighting.
    """
    full = name + MATERIAL_SUFFIX
    existing = bpy.data.materials.get(full)
    if existing is not None:
        bpy.data.materials.remove(existing)

    material = bpy.data.materials.new(full)
    material.use_nodes = True
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    principled = nodes.get("Principled BSDF")

    def load(path, is_data):
        image = bpy.data.images.load(path, check_existing=False)
        image.colorspace_settings.name = "Non-Color" if is_data else "sRGB"
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        return node

    base = written.get("Detail") or written.get("GrayMask")
    if base:
        node = load(base, is_data=False)
        node.location = (-700, 320)
        links.new(node.outputs["Color"], principled.inputs["Base Color"])

    if written.get("NormalOcclusion"):
        node = load(written["NormalOcclusion"], is_data=True)
        node.location = (-700, -260)
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-380, -260)
        links.new(node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

        # Occlusion travels in the alpha, and nothing on the BSDF reads it, so
        # it is multiplied into the base colour to show what it darkens.
        if base:
            mix = nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.location = (-380, 320)
            mix.inputs["Factor"].default_value = 1.0
            colour_node = next(
                n for n in nodes
                if n.bl_idname == "ShaderNodeTexImage"
                and n.image and n.image.filepath == base
            )
            links.new(colour_node.outputs["Color"], mix.inputs[6])
            links.new(node.outputs["Alpha"], mix.inputs[7])
            links.new(mix.outputs[2], principled.inputs["Base Color"])

    # One value, not a map, because that is all the surface can carry. White
    # is glossy for the game and rough for Blender, hence the inversion.
    value = 0.0 if smoothness is None else float(smoothness)
    principled.inputs["Roughness"].default_value = max(0.0, min(1.0 - value, 1.0))

    # Paralives has no metallic channel at all, so neither does the preview.
    if "Metallic" in principled.inputs:
        principled.inputs["Metallic"].default_value = 0.0

    return material


def apply(context, settings, objects, report):
    """Swap in a preview material. Returns (material, written_suffixes)."""
    global _frozen_plan

    plan = getattr(report, "texture_plan", None)
    if plan is None:
        plan = textures.build_plan(
            objects,
            settings.asset_name or (objects[0].name if objects else "Asset"),
            settings.recolourable,
        )
    if not plan.outputs:
        raise ValueError(_("No texture to preview"))

    folder = scratch()
    written = {}
    for output in plan.outputs:
        try:
            written[output.suffix] = textures.write(output, folder)
        except Exception as error:
            print("[ParaForge] preview could not write", output.target_name, error)

    if not written:
        raise ValueError(_("No texture to preview"))

    # The value the surface will actually carry, read from the file that was
    # just written rather than from whatever the slider happens to say.
    smoothness = getattr(settings, "smoothness", None)
    if written.get("Smoothness"):
        from . import exporter

        average = exporter.average_smoothness(written["Smoothness"])
        if average is not None:
            smoothness = average
            settings.smoothness = average

    name = textures.pascal_case(
        settings.asset_name or (objects[0].name if objects else "Asset"))
    material = build_material(name, written, smoothness)
    _frozen_plan = plan

    for obj in objects:
        if STASH not in obj:
            obj[STASH] = [
                slot.material.name if slot.material else ""
                for slot in obj.material_slots
            ]
        obj.data.materials.clear()
        obj.data.materials.append(material)

    return material, sorted(written)


def restore(objects):
    """Put the original materials back. Safe to call when nothing is on."""
    global _frozen_plan

    _frozen_plan = None
    restored = 0
    for obj in objects:
        stashed = obj.get(STASH)
        if stashed is None:
            continue
        obj.data.materials.clear()
        for name in stashed:
            obj.data.materials.append(bpy.data.materials.get(name))
        del obj[STASH]
        restored += 1

    for material in list(bpy.data.materials):
        if material.name.endswith(MATERIAL_SUFFIX) and material.users == 0:
            bpy.data.materials.remove(material)
    return restored
