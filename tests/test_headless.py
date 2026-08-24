# SPDX-License-Identifier: GPL-3.0-or-later
"""End to end check, runnable without a GUI.

    blender --background --factory-startup --python tests/test_headless.py

Exits non zero on the first failure, so it works as a CI step.
"""

import os
import re
import shutil
import sys
import tempfile
import traceback

import numpy as np

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paraforge  # noqa: E402
from paraforge import (  # noqa: E402
    cache, catalog, exporter, geo, i18n, imaging, inspector, props, recipe,
    sidecar, spec, textures, uvxform, validate, zones,
)

FAILURES = []
CHECKED = 0


def check(condition, label, detail=""):
    global CHECKED
    CHECKED += 1
    if condition:
        print("  ok    {0}".format(label))
    else:
        print("  FAIL  {0}  {1}".format(label, detail))
        FAILURES.append(label)


def section(title):
    print("")
    print("== " + title)


# --------------------------------------------------------------------------


def fresh_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cache.clear()


def make_cube(name="TestSofa", size=1.0):
    bpy.ops.mesh.primitive_cube_add(size=size)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    return obj


def status_of(report, key):
    for item in report.checks:
        if item.key == key:
            return item.status
    return None


def detail_of(report, key):
    for item in report.checks:
        if item.key == key:
            return item.detail
    return ""


# --------------------------------------------------------------------------


def test_spec():
    section("Specification")
    check(spec.classify_color((1.0, 0.0, 0.0)) == 1, "red is zone 1")
    check(spec.classify_color((0.0, 1.0, 0.0)) == 2, "green is zone 2")
    check(spec.classify_color((1.0, 1.0, 0.0)) == "decal", "yellow is a decal")
    check(spec.classify_color((0.5, 0.2, 0.9)) is None, "an arbitrary colour is illegal")
    check(spec.split_suffix("SofaGrayMask") == ("Sofa", "GrayMask"), "suffix split")
    check(spec.split_suffix("SofaNormalOcclusion")[1] == "NormalOcclusion",
          "longest suffix wins")
    check(spec.split_suffix("sofa_basecolor")[1] is None, "unknown suffix returns None")
    check(textures.pascal_case("old wooden chair_02") == "OldWoodenChair02",
          "pascal case", textures.pascal_case("old wooden chair_02"))


def test_measurement():
    section("Measurement")
    fresh_scene()
    obj = make_cube(size=2.0)
    obj.location = (0.0, 0.0, 1.0)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    measurement = geo.measure([obj], depsgraph)

    check(abs(measurement.min[2] - 0.0) < 1e-6, "base sits at Z=0",
          str(measurement.min))
    check(measurement.triangles == 12, "cube is 12 triangles",
          str(measurement.triangles))
    check(measurement.ngons == 0, "a cube has no n-gons")
    check(abs(float(measurement.size[0]) - 2.0) < 1e-6, "size is 2 m")

    offsets = geo.anchor_offsets(measurement, "FLOOR")
    check(all(abs(v) < 1e-6 for v in offsets), "floor anchors already satisfied",
          str(offsets))

    offsets = geo.anchor_offsets(measurement, "WINDOW")
    check(abs(offsets[2] + 1.0) < 1e-6, "window rule wants it centred in Z",
          str(offsets))


def test_validation_and_fixes():
    section("Validation and fixes")
    fresh_scene()
    obj = make_cube()
    obj.rotation_euler = (0.4, 0.0, 0.0)
    obj.scale = (2.0, 1.0, 1.0)
    obj.location = (0.7, 0.0, 3.0)

    settings = props.settings(bpy.context)
    settings.item_type = "FLOOR"
    settings.asset_name = "TestSofa"

    report = cache.get(bpy.context, settings, force=True)
    check(status_of(report, "transforms") == validate.FAIL, "dirty transforms caught")
    check(status_of(report, "origin") == validate.FAIL, "bad origin caught")
    check(status_of(report, "facing") == validate.TODO, "facing needs a human")
    check(not report.can_export, "export is blocked")

    bpy.ops.paraforge.fix_all()
    report = cache.get(bpy.context, settings, force=True)

    check(status_of(report, "transforms") == validate.OK, "transforms fixed",
          detail_of(report, "transforms"))
    check(status_of(report, "origin") == validate.OK, "origin fixed",
          detail_of(report, "origin"))
    check(status_of(report, "units") == validate.OK, "units fixed")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    measurement = geo.measure([obj], depsgraph)
    check(abs(measurement.min[2]) < 1e-5, "base snapped to Z=0", str(measurement.min))
    check(abs(measurement.center[0]) < 1e-5, "centred in X", str(measurement.center))

    bpy.ops.paraforge.confirm_facing()
    report = cache.get(bpy.context, settings, force=True)
    check(status_of(report, "facing") == validate.OK, "facing confirmed")


def test_wall_rule():
    section("Wall item rule")
    fresh_scene()
    obj = make_cube(size=1.0)
    settings = props.settings(bpy.context)
    settings.item_type = "WALL"
    settings.asset_name = "TestShelf"

    bpy.ops.paraforge.fix_origin()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    measurement = geo.measure([obj], depsgraph)

    check(abs(measurement.min[1]) < 1e-5, "back snapped to Y=0", str(measurement.min))
    check(abs(measurement.center[0]) < 1e-5, "centred in X")
    check(abs(measurement.center[2]) < 1e-5, "centred in Z")


def build_texture(name, color):
    image = bpy.data.images.new(name, 64, 64, alpha=True)
    pixels = np.zeros((64, 64, 4), dtype=np.float32)
    pixels[:, :, :3] = color
    pixels[:, :, 3] = 1.0
    # Left half gets a second colour so the tolerance test has something to bite.
    pixels[:, :32, :3] = (1.0, 0.0, 0.0)
    image.pixels.foreach_set(pixels.reshape(-1))
    image.update()
    return image


def attach_material(obj, image, name="TestMat"):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    if principled is not None:
        material.node_tree.links.new(
            texture.outputs["Color"], principled.inputs["Base Color"]
        )
    obj.data.materials.append(material)
    return material


def test_zones():
    section("Colour zones")
    fresh_scene()
    obj = make_cube()
    image = build_texture("SofaGrayMask", (0.0, 0.0, 1.0))
    attach_material(obj, image)

    settings = props.settings(bpy.context)
    settings.asset_name = "TestSofa"

    bpy.ops.paraforge.assign_zone(zone="1", whole_mesh=True)
    zones_found, illegal, missing = geo.color_zones([obj])
    check(zones_found == {1}, "whole mesh painted to zone 1", str(zones_found))
    check(not illegal, "no illegal colour")
    check(not missing, "attribute created")

    # Grow zone 2 from the red half of the texture.
    result = bpy.ops.paraforge.zone_from_color(
        zone="2", color=(1.0, 0.0, 0.0), tolerance=0.05,
        image_name=image.name, rest_to_zone_zero=False,
    )
    check("FINISHED" in result, "colour match ran")
    zones_found, illegal, _missing = geo.color_zones([obj])
    check(2 in zones_found, "zone 2 assigned from the picked colour", str(zones_found))
    check(not illegal, "colour match writes only legal colours")

    # A wide tolerance should swallow everything.
    bpy.ops.paraforge.zone_from_color(
        zone="3", color=(1.0, 0.0, 0.0), tolerance=1.0,
        image_name=image.name, rest_to_zone_zero=False,
    )
    zones_found, _illegal, _missing = geo.color_zones([obj])
    check(zones_found == {3}, "tolerance 1.0 takes the whole mesh", str(zones_found))

    bpy.ops.paraforge.clear_zones()
    zones_found, _illegal, _missing = geo.color_zones([obj])
    check(zones_found == {0}, "reset returns to zone 0", str(zones_found))

    # Illegal colours get snapped.
    attribute = obj.data.color_attributes.active_color
    colors = zones.read_colors(attribute)
    colors[:, :3] = (0.9, 0.1, 0.1)
    zones.write_colors(obj.data, attribute, colors)
    _found, illegal, _missing = geo.color_zones([obj])
    check(bool(illegal), "illegal colour detected")
    bpy.ops.paraforge.fix_snap_colors()
    found, illegal, _missing = geo.color_zones([obj])
    check(not illegal and found == {1}, "snapped to the nearest zone", str(found))


def test_zones_from_materials():
    section("Zones from materials")
    fresh_scene()
    obj = make_cube()
    image = build_texture("MultiGrayMask", (0.2, 0.2, 0.2))
    attach_material(obj, image, "MatA")
    attach_material(obj, image, "MatB")

    # Send half the faces to the second slot.
    for index, polygon in enumerate(obj.data.polygons):
        polygon.material_index = index % 2

    bpy.ops.paraforge.zones_from_materials()
    found, illegal, _missing = geo.color_zones([obj])
    check(found == {0, 1}, "two materials became two zones", str(found))
    check(not illegal, "material mapping writes legal colours only")


def test_export():
    section("Export")
    fresh_scene()
    obj = make_cube()
    image = build_texture("TestSofaGrayMask", (0.3, 0.3, 0.3))
    attach_material(obj, image)

    settings = props.settings(bpy.context)
    settings.item_type = "FLOOR"
    settings.asset_name = "TestSofa"
    settings.catalog_tag = catalog.BY_NAME["Armchairs"]
    settings.swatch_group = "BasicWood"
    settings.facing_confirmed = True

    temp = tempfile.mkdtemp(prefix="paraforge_")
    mod = os.path.join(temp, "TestPack_1234567890.mod")
    os.makedirs(mod)
    settings.mod_folder = mod

    bpy.ops.paraforge.fix_all()
    report = cache.get(bpy.context, settings, force=True)

    check(status_of(report, "destination") == validate.OK, "mod folder accepted",
          detail_of(report, "destination"))
    check(status_of(report, "textures") in (validate.OK, validate.WARN),
          "texture naming accepted", detail_of(report, "textures"))
    check(report.can_export, "export unblocked",
          str([c.label for c in report.checks if c.blocking]))

    result = bpy.ops.paraforge.export()
    check("FINISHED" in result, "export ran")

    fbx = os.path.join(mod, "TestSofa.fbx")
    png = os.path.join(mod, "TestSofaGrayMask.png")
    recipe_file = os.path.join(mod, recipe.FOLDER, "TestSofa.recipe.txt")

    check(os.path.isfile(fbx), "FBX written", fbx)
    check(os.path.getsize(fbx) > 1000, "FBX is not empty",
          str(os.path.getsize(fbx)) if os.path.isfile(fbx) else "missing")
    check(os.path.isfile(png), "texture written with its suffix", png)
    check(os.path.isfile(recipe_file), "recipe written", recipe_file)

    if os.path.isfile(recipe_file):
        with open(recipe_file, "r", encoding="utf-8") as handle:
            text = handle.read()
        check("BasicWood" in text, "recipe carries the swatch group")
        check("Armchairs" in text, "recipe carries the catalog tag")
        check("ItemMeshReference" in text, "recipe lists the Control Panel steps")

    settings_used = exporter.fbx_settings("x.fbx")
    check(settings_used["axis_forward"] == "Z", "FBX forward is Z")
    check(settings_used["axis_up"] == "Y", "FBX up is Y")
    # Any colour attribute at all makes the mesh ZoneDefinition:VertexZones,
    # which a plain surface has no shader for, and the item goes invisible.
    check(settings_used["colors_type"] == "NONE",
          "vertex colours are left out by default")
    check(exporter.fbx_settings("x.fbx", vertex_colors=True)["colors_type"]
          == "SRGB", "and exported only for a recolourable item")

    return temp, mod


def test_inspector(mod):
    section("Mod folder inspector")
    before = inspector.snapshot(mod)
    check(len(before["files"]) >= 2, "snapshot recorded the exported files",
          str(len(before["files"])))

    # Pretend the game wrote an item definition.
    with open(os.path.join(mod, "items.json"), "w", encoding="utf-8") as handle:
        handle.write('{\n "items": [\n  {"name": "TestSofa"}\n ]\n}\n')

    after = inspector.snapshot(mod)
    changes = inspector.diff(before, after)
    check(changes["added"] == ["items.json"], "diff caught the new file",
          str(changes))

    text = inspector.report(before, after)
    check("JSON files were written" in text, "verdict recognises JSON")
    check('"items"' in text, "report includes the file content")


def test_texture_planning():
    section("Texture planning")
    fresh_scene()
    obj = make_cube()
    good = build_texture("AnythingGrayMask", (0.5, 0.5, 0.5))
    attach_material(obj, good, "A")

    plan = textures.build_plan([obj], "Sofa")
    check(len(plan.sources) == 1, "the image was found", str(len(plan.sources)))
    check(plan.sources[0].role == spec.PARALIVES,
          "a Paralives suffix is recognised", plan.sources[0].role)
    check(plan.outputs[0].target_name == "SofaGrayMask.png",
          "renamed onto the asset name", plan.outputs[0].target_name)
    check(plan.outputs[0].kind == textures.COPY,
          "an already correct map is copied, not rebuilt")
    # A GrayMask is a complete albedo, so nothing important is missing. The
    # game ships a normal map on about one item in twenty, so its absence is
    # not worth a word.
    check(plan.missing_recommended() == ["Detail"],
          "the other albedo is listed, nothing else",
          str(plan.missing_recommended()))
    check("NormalOcclusion" not in plan.missing_recommended(),
          "a missing normal map is not treated as a problem")

    # Two grey images, no name, no wiring: there is genuinely nothing to go
    # on, and a guess would put the wrong map in the mod folder.
    fresh_scene()
    obj = make_cube()
    material = bpy.data.materials.new("Mystery")
    material.use_nodes = True
    for index in (42, 43):
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = flat_image("xyz_00{0}".format(index), (0.5, 0.5, 0.5, 1.0))
    obj.data.materials.append(material)

    plan = textures.build_plan([obj], "Sofa")
    check(len(plan.unknown) == 2, "two unidentifiable images",
          str([s.stem for s in plan.unknown]))
    check(not plan.outputs, "nothing is written from guesses")


# --------------------------------------------------------------------------
# What a real download looks like


def gltf_material(obj, name="Downloaded", base=None, orm=None, normal=None,
                  occlusion_group=True):
    """Rebuild what the glTF importer produces for a GLB from the web.

    gltfpack strips image names, so the only usable evidence is the wiring:
    base colour straight in, roughness and metalness split out of one packed
    texture, occlusion hanging off a side group that never reaches the BSDF.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    principled = nodes.get("Principled BSDF")

    def image_node(image):
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        return node

    if base is not None:
        links.new(image_node(base).outputs["Color"], principled.inputs["Base Color"])

    if orm is not None:
        node = image_node(orm)
        separate = nodes.new("ShaderNodeSeparateColor")
        links.new(node.outputs["Color"], separate.inputs["Color"])
        links.new(separate.outputs["Green"], principled.inputs["Roughness"])
        links.new(separate.outputs["Blue"], principled.inputs["Metallic"])

        if occlusion_group:
            group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
            group.interface.new_socket(
                "Occlusion", in_out="INPUT", socket_type="NodeSocketFloat"
            )
            holder = nodes.new("ShaderNodeGroup")
            holder.node_tree = group
            links.new(separate.outputs["Red"], holder.inputs["Occlusion"])

    if normal is not None:
        node = image_node(normal)
        normal_map = nodes.new("ShaderNodeNormalMap")
        links.new(node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    obj.data.materials.append(material)
    return material


def flat_image(name, rgba, size=16):
    image = bpy.data.images.new(name, size, size, alpha=True)
    pixels = np.empty((size, size, 4), dtype=np.float32)
    pixels[:, :, :] = rgba
    image.pixels.foreach_set(pixels.reshape(-1))
    image.update()
    return image


def test_downloaded_asset():
    section("A GLB downloaded from the web")
    fresh_scene()
    obj = make_cube()

    # Exactly what gltfpack hands over: no names to read anywhere.
    base = flat_image("Image_0", (0.6, 0.2, 0.15, 1.0))
    orm = flat_image("Image_1", (0.35, 0.8, 1.0, 1.0))
    normal = flat_image("Image_2", (0.5, 0.5, 1.0, 1.0))
    gltf_material(obj, base=base, orm=orm, normal=normal)

    plan = textures.build_plan([obj], "Capsule")
    roles = {source.stem: source.role for source in plan.sources}

    check(roles.get("Image_0") == spec.BASE_COLOR, "base colour from the graph",
          str(roles))
    check(roles.get("Image_1") == spec.ORM, "packed ORM recognised", str(roles))
    check(roles.get("Image_2") == spec.NORMAL, "normal map from the graph",
          str(roles))
    check(all(s.evidence == textures.FROM_GRAPH for s in plan.sources),
          "the wiring is what identified them")

    names = sorted(o.target_name for o in plan.outputs)
    check(names == ["CapsuleDetail.png", "CapsuleNormalOcclusion.png",
                    "CapsuleSmoothness.png"],
          "three Paralives maps planned", str(names))

    # Smoothness is the opposite of glTF roughness.
    smoothness = next(o for o in plan.outputs if o.suffix == "Smoothness")
    pixels = textures.render(smoothness)
    value = float(pixels[0, 0, 0])
    expected = 1.0 - 0.8 + 1.0 * spec.METALLIC_SMOOTHNESS_BOOST
    check(abs(value - expected) < 0.02,
          "smoothness is 1 - roughness, plus the metal boost",
          "{0:.3f} wanted {1:.3f}".format(value, expected))

    # Occlusion rides in the alpha of the normal map, per the wiki.
    combined = next(o for o in plan.outputs if o.suffix == "NormalOcclusion")
    pixels = textures.render(combined)
    check(abs(float(pixels[0, 0, 2]) - 1.0) < 0.01, "normal blue kept")
    check(abs(float(pixels[0, 0, 3]) - 0.35) < 0.02,
          "occlusion packed into the alpha", str(float(pixels[0, 0, 3])))

    # And the albedo is copied untouched, so the look survives.
    detail = next(o for o in plan.outputs if o.suffix == "Detail")
    check(detail.kind == textures.COPY, "the albedo is not touched")


def test_recolourable_conversion():
    section("Recolourable conversion")
    fresh_scene()
    obj = make_cube()
    base = flat_image("Image_0", (0.8, 0.1, 0.1, 1.0))
    gltf_material(obj, base=base)

    plan = textures.build_plan([obj], "Chair", recolourable=True)
    output = plan.outputs[0]
    check(output.suffix == "GrayMask", "recolourable asks for a GrayMask",
          output.suffix)

    pixels = textures.render(output)
    check(abs(float(pixels[0, 0, 0]) - 0.5) < 0.02,
          "recentred on the 50% gray the game expects",
          str(float(pixels[0, 0, 0])))
    check(abs(float(pixels[0, 0, 0]) - float(pixels[0, 0, 1])) < 1e-4,
          "and fully desaturated")


def test_sketchfab_names():
    section("Names from a Sketchfab export")
    fresh_scene()
    obj = make_cube()
    diffuse = flat_image("29_144_monstera_plant_metal_Diffuse", (0.3, 0.5, 0.2, 1.0))
    orm = flat_image("144_monstera_plant_metal-ORM", (0.5, 0.5, 0.0, 1.0))

    material = bpy.data.materials.new("Loose")
    material.use_nodes = True
    for image in (diffuse, orm):
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
    obj.data.materials.append(material)

    plan = textures.build_plan([obj], "Monstera")
    roles = {source.stem: source.role for source in plan.sources}
    check(roles.get("29_144_monstera_plant_metal_Diffuse") == spec.BASE_COLOR,
          "_Diffuse read from the file name", str(roles))
    check(roles.get("144_monstera_plant_metal-ORM") == spec.ORM,
          "-ORM read from the file name", str(roles))


def test_role_override():
    section("Manual role override")
    fresh_scene()
    obj = make_cube()
    image = flat_image("Image_0", (0.5, 0.5, 0.5, 1.0))
    material = bpy.data.materials.new("Loose")
    material.use_nodes = True
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    obj.data.materials.append(material)

    textures.set_stored_role(image, spec.OCCLUSION)
    plan = textures.build_plan([obj], "Thing")
    check(plan.sources[0].role == spec.OCCLUSION, "the override wins",
          plan.sources[0].role)
    check(plan.sources[0].evidence == textures.FROM_USER, "and is marked as ours")
    check(plan.outputs[0].suffix == "NormalOcclusion",
          "occlusion alone still produces a NormalOcclusion map",
          plan.outputs[0].suffix)

    pixels = textures.render(plan.outputs[0])
    check(abs(float(pixels[0, 0, 2]) - spec.FLAT_NORMAL[2]) < 0.01,
          "with a flat normal in the RGB")


def test_language_reload():
    """Switching language tears the add-on down and builds it again."""
    section("Language reload")
    fresh_scene()
    make_cube()

    settings = props.settings(bpy.context)
    settings.asset_name = "KeepMe"
    settings.triangle_budget = 4242
    settings.hud_corner = "BOTTOM_RIGHT"

    before = i18n.language()
    label_before = bpy.types.PARAFORGE_OT_export.bl_label
    try:
        i18n.set_language("en" if before == "fr" else "fr")
        paraforge.reload_for_language()

        check(bpy.types.PARAFORGE_OT_export.bl_label != label_before,
              "the baked operator label followed the switch",
              bpy.types.PARAFORGE_OT_export.bl_label)

        settings = props.settings(bpy.context)
        check(settings is not None, "the scene settings came back")
        check(settings.asset_name == "KeepMe", "a string survived",
              settings.asset_name)
        check(settings.triangle_budget == 4242, "a number survived",
              str(settings.triangle_budget))
        check(settings.hud_corner == "BOTTOM_RIGHT", "an enum survived",
              settings.hud_corner)

        # And the add-on still works afterwards.
        report = cache.get(bpy.context, settings, force=True)
        check(bool(report.checks), "the checklist still runs")
    finally:
        i18n.set_language(before)
        paraforge.reload_for_language()

    check(i18n.language() == before, "and the language was put back")
    check(bpy.types.PARAFORGE_OT_export.bl_label == label_before,
          "along with the labels")


def test_bake_to_atlas():
    section("Bake into one surface")
    fresh_scene()

    # Two objects, two materials, two flat colours: the smallest version of
    # the problem a downloaded asset has.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    left = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.0, 0.0, 0.0))
    right = bpy.context.active_object

    gltf_material(left, "Red", base=flat_image("red", (0.9, 0.05, 0.05, 1.0)))
    gltf_material(right, "Blue", base=flat_image("blue", (0.05, 0.05, 0.9, 1.0)))

    objects = [left, right]
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = left

    settings = props.settings(bpy.context)
    settings.asset_name = "Pair"

    plan = textures.build_plan(objects, "Pair")
    check(len(plan.groups) == 2, "two materials to start with", str(plan.groups))

    result = bpy.ops.paraforge.bake_to_atlas(
        resolution="1024", samples=1, bake_normal=False, bake_roughness=False,
        bake_occlusion=True,
    )
    check("FINISHED" in result, "the bake ran", str(result))

    check(all(len(o.data.materials) == 1 for o in objects),
          "one material left on every object")
    check(left.data.materials[0] == right.data.materials[0],
          "and it is the same one")

    plan = textures.build_plan(objects, "Pair")
    check(len(plan.groups) == 1, "a single surface now", str(plan.groups))
    roles = {s.stem: s.role for s in plan.sources}
    check(roles.get("PairDetail") == spec.BASE_COLOR,
          "the baked albedo is stamped as such", str(roles))
    check(roles.get("PairOcclusion") == spec.OCCLUSION,
          "and the occlusion too", str(roles))

    # Both colours have to be somewhere in the atlas, otherwise the bake
    # quietly lost half the model.
    pixels = imaging.read(bpy.data.images["PairDetail"])
    reds = pixels[:, :, 0] - pixels[:, :, 2]
    check(float(reds.max()) > 0.4, "the red material is in the atlas",
          str(float(reds.max())))
    check(float(reds.min()) < -0.4, "the blue material too",
          str(float(reds.min())))

    # Unreached pixels must stay lit. Cleared to black an occlusion map turns
    # the whole item off in game.
    occlusion = imaging.read(bpy.data.images["PairOcclusion"])
    check(float(occlusion[:, :, 0].mean()) > 0.5,
          "the occlusion atlas is lit, not black",
          str(float(occlusion[:, :, 0].mean())))


def test_catalog():
    """The tag list is read out of the game, not invented."""
    section("Catalogue read from the game")
    guids = [t[0] for t in catalog.TAGS]
    names = [t[1] for t in catalog.TAGS]
    check(len(catalog.TAGS) > 200, "the whole tree is there", str(len(catalog.TAGS)))
    check(len(set(guids)) == len(guids), "every GUID is unique")
    check(len(set(names)) == len(names), "every name is unique, enums need that")
    check(all(guid.isdigit() for guid in guids), "GUIDs are the game's integers")
    check(catalog.path(catalog.BY_NAME["Armchairs"]).endswith("Seating > Armchairs"),
          "ancestry resolves", catalog.path(catalog.BY_NAME["Armchairs"]))
    parents = {t[2] for t in catalog.TAGS if t[2]}
    check(parents <= set(guids), "no tag points at a parent that is missing")


def test_sidecars():
    section("Sidecar .meta files")
    fresh_scene()
    obj = make_cube()
    image = build_texture("TestSofaGrayMask", (0.5, 0.5, 0.5))
    attach_material(obj, image)

    settings = props.settings(bpy.context)
    settings.asset_name = "TestSofa"
    settings.facing_confirmed = True

    temp = tempfile.mkdtemp(prefix="paraforge_meta_")
    mod = os.path.join(temp, "MetaPack_42.mod")
    os.makedirs(mod)
    settings.mod_folder = mod

    bpy.ops.paraforge.fix_all()
    bpy.ops.paraforge.export(ignore_failures=True)

    fbx_meta = sidecar.read(os.path.join(mod, "TestSofa.fbx"))
    png_meta = sidecar.read(os.path.join(mod, "TestSofaGrayMask.png"))

    check(fbx_meta.get("Type") == str(spec.META_TYPE_MESH),
          "the mesh is declared as a mesh", str(fbx_meta))
    check(png_meta.get("Type") == str(spec.META_TYPE_TEXTURE),
          "the texture is declared as a texture", str(png_meta))
    check(png_meta.get("IsLinear") == "True",
          "a GrayMask is linear, as the game writes it", str(png_meta))
    check(png_meta.get("GenerateMipMaps") == "True", "and gets mip maps")
    check(fbx_meta.get("GUID", "").isdigit() and fbx_meta["GUID"] != "0",
          "GUIDs are positive integers", fbx_meta.get("GUID"))
    check(fbx_meta["GUID"] != png_meta["GUID"], "and differ per asset")

    # A prefab points at its mesh by GUID, so a rebuild must not renumber it.
    again = sidecar.asset_guid(mod, "TestSofa.fbx")
    check(again == fbx_meta["GUID"], "the GUID is stable across exports")
    check(sidecar.asset_guid(mod + "x", "TestSofa.fbx") != again,
          "but differs between mods")

    # ColorZone is the one that must not be filtered.
    flags = sidecar.texture_flags("ColorZone")
    check(flags.get("IsPointFilter") == "True",
          "a zone map is point filtered", str(flags))
    check("IsLinear" not in sidecar.texture_flags("Detail"),
          "a Detail map stays sRGB")


def test_refuses_the_game_folder():
    """Assets go in a mod, never in the installation."""
    section("Refusing to write into the game")
    from paraforge import modfolder

    temp = tempfile.mkdtemp(prefix="paraforge_game_")
    install = os.path.join(temp, "Paralives")
    inside = os.path.join(install, "Main.mod", "Environments")
    os.makedirs(inside)
    os.makedirs(os.path.join(install, "Paralives_Data"))
    open(os.path.join(install, "Paralives.exe"), "wb").close()

    check(modfolder.game_install_above(inside) == install,
          "the install is recognised from anywhere inside it",
          modfolder.game_install_above(inside))
    check(not modfolder.game_install_above(temp),
          "and a plain folder is not")

    fresh_scene()
    make_cube()
    settings = props.settings(bpy.context)
    settings.mod_folder = inside
    settings.asset_name = "Nope"
    # A cancelling operator raises when it is called from Python.
    try:
        result = str(bpy.ops.paraforge.export(ignore_failures=True))
    except RuntimeError as error:
        result = str(error)
    check("CANCELLED" in result or "installation" in result,
          "the export refuses", result[:80])
    check(not os.path.isfile(os.path.join(inside, "Nope.fbx")),
          "and wrote nothing")


def test_setting_merge():
    """Adding an entry must touch the count line and nothing else."""
    section("Merging a .setting file")
    from paraforge import setting

    original = (
        "#Setting.Items\r\n"
        " =AllItems\r\n"
        "  s2\r\n"
        "  i0\r\n"
        "   =GUID:111\r\n"
        "   =DisplayName:Existing\r\n"
        "   =SomeFieldWeHaveNeverHeardOf:True\r\n"
        "  i7\r\n"
        "   =GUID:222\r\n"
        "   =DisplayName:Other\r\n"
    )
    merged = setting.append_entry(
        original, "AllItems",
        [("GUID", "333"), ("DisplayName", "Fresh")], "Items",
        setting.MARKER_NEW, "333",
    )

    check("\r\n" in merged and "\n\n" not in merged,
          "the file keeps its CRLF endings")
    check("=SomeFieldWeHaveNeverHeardOf:True" in merged,
          "a field the add-on does not understand survives")

    # The size line counts the positional entries. Touching it on a list the
    # base game fills is what made the game drop everything else.
    check("  s2\r\n" in merged, "the count line is left exactly as it was",
          [l for l in merged.split("\r\n") if l.strip().startswith("s")])
    # The field, not just the marker. The marker says where the member goes;
    # the game creates it with every field at its default, and keys both
    # AllItems and AllSurfaces on the GUID field. Left at zero, every entry a
    # mod adds collides on zero and only one of them survives.
    check("   =GUID:333\r\n" in merged,
          "and carries its GUID as a field, which the lookup is keyed on",
          merged)

    extended = setting.append_entry(
        original, "AllItems",
        [("GUID", "111"), ("DisplayName", "Patched")], "Items",
        setting.MARKER_EXTEND, "111",
    )
    check("  g111\r\n" in extended and "=GUID:111\r\n   =DisplayName:Patched"
          not in extended,
          "while a g entry leaves it out, merging onto a member that has one")

    check("  @333\r\n" in merged, "the new entry is added by GUID",
          [l for l in merged.split("\r\n") if l.strip().startswith("@")])
    check(merged.count("=GUID:333") == 1,
          "with the GUID field written exactly once", merged)
    check(merged.count("=GUID:111") == 1 and merged.count("=DisplayName:Fresh") == 1,
          "both the old and the new entry are there")

    # Positional stays available, and still behaves the old way.
    positional = setting.append_entry(
        original, "AllItems",
        [("GUID", "333"), ("DisplayName", "Fresh")], "Items",
        setting.MARKER_POSITIONAL,
    )
    check("  s3\r\n" in positional, "positional still bumps the count")
    check("  i8\r\n" in positional, "and avoids the used indices",
          [l for l in positional.split("\r\n") if l.strip().startswith("i")])

    # A fresh file gets no size line either, unless it is positional.
    fresh = setting.append_entry(
        "", "Items", [("GUID", "9"), ("Key", "K"), ("Value", "V")],
        "Translations", setting.MARKER_NEW, "9",
    )
    check("s1" not in fresh, "a new file declares no size", fresh)
    check(" @9" in fresh, "and identifies its entry by GUID", fresh)

    # Finding it again has to work through the marker, not a GUID field.
    lines = fresh.replace("\r\n", "\n").split("\n")
    check(setting.entry_span(lines, "Items", "GUID", "9") is not None,
          "the entry is found by its marker")

    # Every original line still present, in order.
    before = [l for l in original.split("\r\n") if l.strip()]
    after = [l for l in merged.split("\r\n") if l.strip()]
    kept = [l for l in before if l != "  s2"]
    check(all(line in after for line in kept), "nothing was dropped")

    # A nested list, the shape the game uses for cross references.
    nested = setting.append_entry(
        "", "AllItems",
        [("GUID", "9"), ("Tag", setting.linked_list(4, [("11", "22")]))],
        "Items",
    )
    check("#Setting.Items" in nested, "a missing file is created whole")
    check("    s1" in nested and "     =Value:22" in nested,
          "the nested list is indented under its key", repr(nested))


def test_generate_item():
    section("Generating the item")
    from paraforge import item, journal

    fresh_scene()
    obj = make_cube()
    image = build_texture("ChairDetail", (0.4, 0.3, 0.2))
    attach_material(obj, image)

    settings = props.settings(bpy.context)
    settings.asset_name = "OldWoodenChair"
    settings.item_type = "FLOOR"
    settings.catalog_tag = catalog.BY_NAME["Armchairs"]
    settings.swatch_group = "BasicWood"
    settings.facing_confirmed = True
    # Off by default, since a mod supplied surface still draws white. The
    # option is exercised here so the shape it writes stays covered.
    settings.own_surface = True

    temp = tempfile.mkdtemp(prefix="paraforge_item_")
    mod = os.path.join(temp, "MyPack_9.mod")
    os.makedirs(mod)
    settings.mod_folder = mod

    bpy.ops.paraforge.fix_all()
    bpy.ops.paraforge.export(ignore_failures=True)
    result = bpy.ops.paraforge.generate_item()
    check("FINISHED" in result, "the item was generated", str(result))

    prefab = os.path.join(mod, "OldWoodenChair.prefab")
    items = os.path.join(mod, "Settings", "Items.setting")
    translations = os.path.join(mod, "Settings", "Translations.setting")

    check(os.path.isfile(prefab), "the prefab exists")
    check(os.path.isfile(prefab + ".meta"), "with its meta")
    check(os.path.isfile(items), "the catalogue entry exists")
    check(os.path.isfile(translations), "and the label")

    text = open(prefab, encoding="utf-8").read()
    mesh_guid = sidecar.asset_guid(mod, "OldWoodenChair.fbx")
    check("AssetMesh:" + mesh_guid in text, "the prefab points at the mesh",
          text)

    check("Size:(1.0000, 1.0000, 1.0000)" in text,
          "with the measured bounding box",
          [l for l in text.splitlines() if "Size" in l])

    # By default the item gets a surface of its own, which is the only place
    # the normal map and the smoothness can live.
    surfaces = os.path.join(mod, "Settings", "Surfaces.setting")
    check(os.path.isfile(surfaces), "a surface of its own is written")
    surface = open(surfaces, encoding="utf-8").read()
    own_guid = sidecar.guid_for(sidecar.mod_name(mod), "surface",
                                "OldWoodenChair")

    check("@" + own_guid in surface,
          "added to the game's list by GUID, never positionally", surface)
    check("s1" not in surface,
          "with no size line, which would drop the game's own surfaces",
          surface)
    # The surface's Texture is the base the shader tints, not the colour. With
    # no GrayMask of its own the item borrows the game's neutral base, and the
    # colour stays in DetailMap. Swapping the two renders the item white.
    check("=Texture:" + spec.DEFAULT_BASE_TEXTURE_GUID in surface,
          "sitting on the game's neutral base", surface)
    check(sidecar.asset_guid(mod, "OldWoodenChairDetail.png") not in surface,
          "the colour is not put in the base slot", surface)
    check("ShaderType" not in surface,
          "and no ShaderType, as on 74 of the game's 75 such surfaces")
    # Declaring a swatch default announces a colour zone the plain shader
    # cannot draw, and the item comes out white.
    check("DefaultSwatchGroup" not in surface and "DefaultSwatch" not in surface,
          "no swatch default, which would ask for a zone it cannot draw",
          surface)
    check("Value:" + own_guid in text, "the prefab points at it", text)
    check("DetailMap:" + sidecar.asset_guid(mod, "OldWoodenChairDetail.png")
          in text, "and the colour still comes through DetailMap", text)


    entry = open(items, encoding="utf-8").read()
    check("=DisplayName:OldWoodenChair" in entry, "the item is named", entry)
    check("=Prefab:" + sidecar.asset_guid(mod, "OldWoodenChair.prefab")
          in entry, "and points at its prefab")
    check("=Value:" + catalog.BY_NAME["Armchairs"] in entry,
          "with the real Armchairs tag")
    check("=HasSwatches:False" in entry,
          "and says it has no swatches, like every non recolourable item",
          entry)
    check("=SwatchGroup:" not in entry,
          "so no swatch group is claimed for colourways it cannot produce",
          entry)

    label = open(translations, encoding="utf-8").read()
    check("=Key:Item_OldWoodenChair" in label, "the translation key is right")
    check("=Value:Old Wooden Chair" in label,
          "and the label is readable", label)

    # Running twice must not double the entry.
    before = open(items, encoding="utf-8").read()
    bpy.ops.paraforge.generate_item()
    check(open(items, encoding="utf-8").read().count("=DisplayName:OldWoodenChair") == 1,
          "generating twice does not duplicate the item")

    return temp, mod, before


def test_export_units():
    """The mesh must leave Blender in centimetres, or it is invisible in game.

    The game multiplies raw FBX coordinates by 0.01 and ignores node scaling.
    A 2 m cube therefore has to reach the file as 200 units across.
    """
    section("Export units")
    fresh_scene()
    obj = make_cube(size=2.0)
    obj.location = (0.0, 0.0, 1.0)

    check(abs(spec.FBX_UNITS_PER_METRE - 100.0) < 1e-9,
          "a metre is a hundred FBX units", str(spec.FBX_UNITS_PER_METRE))

    copies = exporter.scaled_copies(
        bpy.context, [obj], spec.FBX_UNITS_PER_METRE, "Rock"
    )
    try:
        check(len(copies) == 1, "one copy per object")
        copy = copies[0]
        coords = np.array([v.co for v in copy.data.vertices])
        size = coords.max(axis=0) - coords.min(axis=0)

        check(all(abs(float(v) - 200.0) < 1e-3 for v in size),
              "a 2 m cube becomes 200 units across",
              str(tuple(round(float(v), 3) for v in size)))

        # The game's meshes are Y up with their base on zero, and it reads the
        # geometry rather than the node, so the rotation is baked in here.
        check(abs(float(coords[:, 1].min())) < 1e-3,
              "the base sits at zero on Y, the game's up axis",
              str(float(coords[:, 1].min())))
        check(abs(float(coords[:, 1].max()) - 200.0) < 1e-3,
              "and the height runs up Y",
              str(float(coords[:, 1].max())))
        check(abs(float(coords[:, 2].min()) + 100.0) < 1e-3,
              "while Z became depth, centred on zero",
              str(float(coords[:, 2].min())))
        check(copy.name == "Rock" and copy.data.name == "Rock",
              "the mesh is named after the item, as the game's own files are",
              copy.name)
        check(all(abs(v - 1.0) < 1e-6 for v in copy.scale),
              "with an identity node, since the game ignores node scaling")

        # The world transform has to be baked in, not left on the object: the
        # cube was moved up by 1 m, so its base is on zero rather than at -100.
        check(float(coords[:, 1].min()) > -1e-3,
              "the object's own location is baked into the geometry",
              str(float(coords[:, 1].min())))
    finally:
        exporter.discard(copies)

    check(not any(o.name == "Rock" for o in bpy.data.objects),
          "and the copies are cleaned up afterwards")
    check(obj.name in bpy.data.objects, "the original is untouched")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    measurement = geo.measure([obj], depsgraph)
    check(abs(float(measurement.size[0]) - 2.0) < 1e-6,
          "and it is still 2 m, so the prefab Size stays in metres")


def test_uv_transform():
    """A Mapping node has to reach the game, and the only way in is the UVs.

    This is the shape an atlas cut arrives in: the mesh's UVs sit inside one
    cell of a 16 by 16 grid and a Mapping node blows that cell back up to the
    whole image. Exported as they stand, those coordinates send the game to a
    sixteenth of a sixteenth of the texture and the item comes back wearing a
    smear with its unwrapped islands showing through.
    """
    section("Texture coordinates")

    # The arithmetic, first, with no scene in the way.
    check(uvxform.is_identity(uvxform.IDENTITY), "identity is identity")
    doubled = (2.0, 0.0, 0.5, 0.0, 2.0, -1.0)
    back = uvxform.invert(doubled)
    check(uvxform.is_identity(uvxform.compose(doubled, back)),
          "a transform composed with its inverse cancels out",
          str(uvxform.compose(doubled, back)))
    check(uvxform.invert((0.0, 0.0, 0.0, 0.0, 0.0, 0.0)) is None,
          "a collapsed transform has no inverse")

    fresh_scene()
    obj = make_cube(name="Cactus", size=2.0)
    obj.location = (0.0, 0.0, 1.0)

    # One cell of a 16 by 16 grid, top left, exactly where an atlas cut lands.
    layer = obj.data.uv_layers[0]
    flat = np.empty(len(layer.data) * 2, dtype=np.float32)
    layer.data.foreach_get("uv", flat)
    uv = flat.reshape(-1, 2)
    uv[:, 0] = uv[:, 0] / 16.0
    uv[:, 1] = uv[:, 1] / 16.0 + 15.0 / 16.0
    layer.data.foreach_set("uv", uv.reshape(-1))

    material = bpy.data.materials.new("Cell")
    material.use_nodes = True
    tree = material.node_tree
    principled = tree.nodes.get("Principled BSDF")
    image = bpy.data.images.new("CactusDetail", 64, 64)
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (16.0, 16.0, 1.0)
    mapping.inputs["Location"].default_value = (0.0, -15.0, 0.0)
    uvnode = tree.nodes.new("ShaderNodeUVMap")
    uvnode.uv_map = layer.name
    tree.links.new(uvnode.outputs["UV"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    obj.data.materials.append(material)

    resolved = uvxform.resolve_object(obj)
    check(resolved.moves, "the Mapping node is seen")
    check(resolved.clean, "and nothing in the chain blocks the way over",
          str(resolved.blockers + resolved.variants))
    check(abs(resolved.matrix[0] - 16.0) < 1e-5
          and abs(resolved.matrix[4] - 16.0) < 1e-5
          and abs(resolved.matrix[5] + 15.0) < 1e-5,
          "read as scale 16 with a -15 offset on V", str(resolved.matrix))
    check(resolved.uv_map == layer.name, "on the layer the material names",
          str(resolved.uv_map))

    copies = exporter.scaled_copies(
        bpy.context, [obj], spec.FBX_UNITS_PER_METRE, "Cactus"
    )
    try:
        exported = copies[0].data.uv_layers[0]
        out = np.empty(len(exported.data) * 2, dtype=np.float32)
        exported.data.foreach_get("uv", out)
        out = out.reshape(-1, 2)
        check(out[:, 0].min() > -1e-4 and out[:, 0].max() < 1.0 + 1e-4
              and out[:, 1].min() > -1e-4 and out[:, 1].max() < 1.0 + 1e-4,
              "the exported UVs cover the whole image, not one cell of it",
              "u {0:.4f}..{1:.4f} v {2:.4f}..{3:.4f}".format(
                  out[:, 0].min(), out[:, 0].max(),
                  out[:, 1].min(), out[:, 1].max()))
    finally:
        exporter.discard(copies)

    layer.data.foreach_get(
        "uv", flat)  # the scene must be exactly as the artist left it
    kept = flat.reshape(-1, 2)
    check(kept[:, 1].min() > 0.9 - 1e-4,
          "while the scene keeps its own coordinates untouched",
          str(float(kept[:, 1].min())))

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    settings = props.settings(bpy.context)
    settings.asset_name = "Cactus"
    report = validate.run(bpy.context, settings)
    check(status_of(report, "uvtransform") == validate.OK,
          "the report says the transform is being carried over",
          str(status_of(report, "uvtransform")))

    # Generated coordinates have no equivalent in an FBX, so the report has to
    # stop claiming the export can carry them.
    coords = tree.nodes.new("ShaderNodeTexCoord")
    tree.links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    cache.clear()
    report = validate.run(bpy.context, settings)
    check(status_of(report, "uvtransform") == validate.WARN,
          "and warns when the coordinates only exist in Blender",
          str(status_of(report, "uvtransform")))
    check(not uvxform.resolve_object(obj).moves,
          "leaving the UVs alone rather than moving them wrongly")

    # A plain material says nothing at all: a line that is always green is a
    # line nobody reads.
    tree.links.new(uvnode.outputs["UV"], texture.inputs["Vector"])
    cache.clear()
    report = validate.run(bpy.context, settings)
    check(status_of(report, "uvtransform") is None,
          "and stays quiet when the material moves nothing",
          str(status_of(report, "uvtransform")))


def test_remesh():
    """Rebuild the topology, and say plainly that it takes the UVs with it."""
    section("Remesh")
    from paraforge import remesh, util

    check(remesh.used_by("SHARP", "sharpness"),
          "sharpness belongs to the sharp solver")
    check(not remesh.used_by("BLOCKS", "sharpness"),
          "and to no other, so the panel can hide it")
    check(remesh.used_by("VOXEL", "voxel_size")
          and not remesh.used_by("VOXEL", "octree_depth"),
          "the voxel solver is sized in metres, not by subdivision")

    fresh_scene()
    obj = make_cube(size=1.0)
    material = bpy.data.materials.new("RemeshSource")
    material.use_nodes = True
    obj.data.materials.append(material)
    before = len(obj.data.polygons)
    check(len(obj.data.uv_layers) >= 1, "the source starts with a UV map")

    failed = remesh.apply_to(bpy.context, [obj], mode="SHARP", octree_depth=4)
    check(not failed, "the modifier applies", str(failed))
    check(len(obj.data.polygons) != before,
          "and the topology is rebuilt, not collapsed",
          "{0} -> {1}".format(before, len(obj.data.polygons)))

    # The whole reason the bake is not optional.
    check(len(obj.data.uv_layers) == 0,
          "remeshing takes the UV map with it, so a bake has to follow")

    # Edit mode refuses modifier_apply, which is what made the reduce button
    # look like it did nothing.
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    count = len(obj.data.polygons)
    failed = remesh.apply_to(bpy.context, [obj], mode="BLOCKS", octree_depth=3)
    check(not failed, "it still applies from edit mode", str(failed))
    check(len(obj.data.polygons) != count, "and actually changes the mesh")
    check(bpy.context.object.mode == "EDIT",
          "leaving the user in the mode they were in",
          bpy.context.object.mode)
    bpy.ops.object.mode_set(mode="OBJECT")

    with util.object_mode(bpy.context):
        check(bpy.context.object.mode == "OBJECT",
              "the guard is a no-op when already in object mode")


def test_preview():
    """The preview must show the exported files, and give the scene back."""
    section("Preview as in game")
    from paraforge import preview

    fresh_scene()
    obj = make_cube()
    image = build_texture("ChairDetail", (0.5, 0.2, 0.1))
    attach_material(obj, image, "Original")

    settings = props.settings(bpy.context)
    settings.asset_name = "Chair"

    original = [s.material.name for s in obj.material_slots]
    check(original == ["Original"], "the object starts on its own material",
          str(original))
    check(not preview.is_on([obj]), "and the preview is off")

    report = cache.get(bpy.context, settings, force=True)
    plan_before = report.texture_plan
    material, written = preview.apply(bpy.context, settings, [obj], report)

    check(preview.is_on([obj]), "the preview reports itself on")
    check("Detail" in written, "the colour map is among what it shows",
          str(written))
    check(obj.material_slots[0].material is material,
          "and the object wears the preview material")
    check(material.name.endswith(preview.MATERIAL_SUFFIX),
          "which is named so it cannot be mistaken for yours", material.name)

    # It has to be the written file, not the source image, or the preview
    # would show the very thing the export is meant to change.
    images = [n.image for n in material.node_tree.nodes
              if n.bl_idname == "ShaderNodeTexImage" and n.image]
    check(images, "with at least one texture wired up")
    check(all(os.path.isfile(i.filepath) for i in images),
          "every one of them read back from a written file",
          str([i.filepath for i in images]))
    check(any(os.path.basename(i.filepath).startswith("Chair") for i in images),
          "named as the export would name it",
          str([os.path.basename(i.filepath) for i in images]))

    # The preview must not become its own source. Rebuilding the plan while
    # it is on would read the converted textures back as if they were the
    # material the file arrived with.
    check(preview.frozen() is plan_before,
          "the plan that produced the preview is frozen")
    after = cache.get(bpy.context, settings, force=True)
    sources = [s.stem for s in after.texture_plan.sources]
    check("ChairDetail" in sources,
          "and the checklist still reports the original source", str(sources))
    check(not any(s.startswith("Chair") and s.endswith("Detail")
                  and s != "ChairDetail" for s in sources),
          "not the texture the preview just wrote", str(sources))

    # The preview has to read a map back through the colour space its source
    # carried. Showing a Non-Color albedo as sRGB washes it out, which reads
    # as the texture having been applied wrongly.
    source_image = bpy.data.images["ChairDetail"]
    check(preview.source_colorspaces(plan_before).get("Detail")
          == source_image.colorspace_settings.name,
          "the source colour space is carried over",
          str(preview.source_colorspaces(plan_before)))
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage" and node.image:
            if "Detail" in os.path.basename(node.image.filepath):
                check(node.image.colorspace_settings.name
                      == source_image.colorspace_settings.name,
                      "and the previewed copy is read through it",
                      node.image.colorspace_settings.name)

    # The roughness comes from the single value the surface carries, never
    # from the map, which the game has no slot for.
    principled = material.node_tree.nodes.get("Principled BSDF")
    check(principled is not None, "the preview has a shader")
    if principled is not None:
        check(not principled.inputs["Roughness"].links,
              "roughness is a value, not a map")

    restored = preview.restore([obj])
    check(restored == 1, "restoring reports what it touched")
    check(preview.frozen() is None, "and the frozen plan is released")
    check(not preview.is_on([obj]), "the preview is off again")
    check([s.material.name for s in obj.material_slots] == original,
          "and the original material is back",
          str([s.material.name for s in obj.material_slots]))

    check(preview.restore([obj]) == 0,
          "restoring twice is harmless")


def test_decimate_rebake():
    """Reducing a mesh must not be what loses its texture."""
    section("Decimate")
    from paraforge import bake

    fresh_scene()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1.0)
    obj = bpy.context.active_object
    obj.name = "Boulder"
    image = build_texture("BoulderDetail", (0.3, 0.5, 0.2))
    attach_material(obj, image)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    before = geo.measure([obj], depsgraph).triangles
    check(before > 4000, "the test mesh is over the budget", str(before))

    # Without the rebake, which is the cheap path and must still work.
    bpy.ops.paraforge.decimate_to_budget(budget=1000, rebake=False)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    after = geo.measure([obj], depsgraph).triangles
    check(after <= 1200, "the mesh came down to the budget", str(after))
    check(len(obj.material_slots) == 1, "and kept its material")

    check(not any(o.name.endswith("_ParaForgeOriginal")
                  for o in bpy.data.objects),
          "no working copy is left behind in the scene",
          str([o.name for o in bpy.data.objects]))

    # The bake path itself: passing sources switches it to selected to active.
    import inspect

    signature = inspect.signature(bake.bake_all)
    check("sources" in signature.parameters,
          "bake_all can bake from another object")
    signature = inspect.signature(bake._bake)
    check("sources" in signature.parameters,
          "and the pass is set up for selected to active")


def test_two_items_share_nothing():
    """Two items in one mod must not share a single identifier of their own.

    A shared Tag element GUID made the game fold two items together: adding a
    vase turned the chair already in the catalogue into a vase.
    """
    section("Two items in one mod")
    from paraforge import item, setting

    temp = tempfile.mkdtemp(prefix="paraforge_pair_")
    mod = os.path.join(temp, "Pair_8.mod")
    os.makedirs(mod)
    seed = sidecar.mod_name(mod)
    tag = catalog.BY_NAME["Armchairs"]

    made = {}
    for name in ("Chair", "Vase"):
        guid = sidecar.guid_for(seed, "item", name)
        made[name] = item.item_fields(
            name, guid, sidecar.asset_guid(mod, name + ".prefab"), tag, "",
            1, seed, False,
        )

    def identifiers(fields):
        found = set()
        for key, value in fields:
            if isinstance(value, list):
                for line in value:
                    match = re.search(r"=(?:GUID|Value):(\d+)", line)
                    if match:
                        found.add(match.group(1))
            elif str(value).isdigit() and len(str(value)) > 6:
                found.add(str(value))
        return found

    chair = identifiers(made["Chair"])
    vase = identifiers(made["Vase"])
    shared = sorted(chair & vase)
    # The catalogue tag itself is meant to be the same on both.
    unexpected = [g for g in shared if g != tag]

    check(not unexpected, "the two entries share no identifier of their own",
          ", ".join(unexpected))
    check(tag in chair and tag in vase,
          "while both still point at the same catalogue tag")

    # And the same through the whole generation, on disk.
    for name, size in (("Chair", 1.0), ("Vase", 2.0)):
        fresh_scene()
        obj = make_cube(size=size)
        image = build_texture(name + "Detail", (0.3, 0.3, 0.3))
        attach_material(obj, image)
        settings = props.settings(bpy.context)
        settings.asset_name = name
        settings.item_type = "FLOOR"
        settings.catalog_tag = tag
        settings.mod_folder = mod
        settings.facing_confirmed = True
        bpy.ops.paraforge.fix_all()
        bpy.ops.paraforge.export(ignore_failures=True)
        bpy.ops.paraforge.generate_item()

    text = open(os.path.join(mod, "Settings", "Items.setting"),
                encoding="utf-8").read()
    tag_guids = re.findall(r"=GUID:(\d+)\s*\r?\n\s*=Value:" + tag, text)
    check(len(tag_guids) == 2, "both items are in the catalogue",
          str(len(tag_guids)))
    check(len(set(tag_guids)) == 2,
          "each with its own tag element, not one shared between them",
          str(tag_guids))

    shutil.rmtree(temp, ignore_errors=True)


def test_asset_name_guard():
    """A borrowed name is how one item silently replaces another."""
    section("Asset name")
    fresh_scene()
    obj = make_cube()
    obj.name = "Mesh_0"

    settings = props.settings(bpy.context)
    settings.asset_name = ""

    report = cache.get(bpy.context, settings, force=True)
    check(status_of(report, "name") == validate.FAIL,
          "an unnamed item on a generic object is blocking",
          detail_of(report, "name"))
    check(not report.can_export, "and export is blocked")

    settings.asset_name = "Cube"
    report = cache.get(bpy.context, settings, force=True)
    check(status_of(report, "name") == validate.WARN,
          "a name the importer chose is a warning",
          detail_of(report, "name"))

    settings.asset_name = "OldWoodenChair"
    report = cache.get(bpy.context, settings, force=True)
    check(status_of(report, "name") == validate.OK,
          "a real name passes", detail_of(report, "name"))

    # And a name already in the mod is flagged, since exporting replaces it.
    temp = tempfile.mkdtemp(prefix="paraforge_name_")
    mod = os.path.join(temp, "Names_2.mod")
    os.makedirs(mod)
    with open(os.path.join(mod, "OldWoodenChair.fbx"), "wb") as handle:
        handle.write(b"already here")
    settings.mod_folder = mod

    report = cache.get(bpy.context, settings, force=True)
    check(status_of(report, "name") == validate.WARN,
          "a name already in the mod warns before it replaces anything",
          detail_of(report, "name"))

    check(spec.looks_generic("Mesh_0") and spec.looks_generic("Cube.001"),
          "generic names are recognised through their numbering")
    check(not spec.looks_generic("OldWoodenChair"),
          "and a real name is not")

    settings.mod_folder = ""
    shutil.rmtree(temp, ignore_errors=True)


def test_shared_surface_fallback():
    """With its own surface off, the item borrows the game's shared one."""
    section("Falling back to the shared surface")

    fresh_scene()
    obj = make_cube()
    image = build_texture("StoolDetail", (0.4, 0.3, 0.2))
    attach_material(obj, image)

    settings = props.settings(bpy.context)
    settings.asset_name = "Stool"
    settings.item_type = "FLOOR"
    settings.catalog_tag = catalog.BY_NAME["Armchairs"]
    settings.facing_confirmed = True
    settings.own_surface = False

    temp = tempfile.mkdtemp(prefix="paraforge_shared_")
    mod = os.path.join(temp, "Shared_3.mod")
    os.makedirs(mod)
    settings.mod_folder = mod

    bpy.ops.paraforge.fix_all()
    bpy.ops.paraforge.export(ignore_failures=True)
    bpy.ops.paraforge.generate_item()

    text = open(os.path.join(mod, "Stool.prefab"), encoding="utf-8").read()
    check("Value:" + spec.DEFAULT_SURFACE_GUID in text,
          "the prefab points at the game's shared surface", text)
    check("DetailMap:" + sidecar.asset_guid(mod, "StoolDetail.png") in text,
          "and lays the texture over it instead", text)
    check(not os.path.isfile(os.path.join(mod, "Settings", "Surfaces.setting")),
          "nothing is written into Surfaces.setting")

    settings.own_surface = True
    shutil.rmtree(temp, ignore_errors=True)


def test_repair_stale_entry():
    """An entry an earlier version wrote badly has to be corrected, not kept."""
    section("Repairing a stale entry")
    from paraforge import setting

    stale = "\r\n".join([
        "#Setting.Items",
        " =AllItems",
        "  s1",
        "  i0",
        "   =GUID:12345",
        "   =DisplayName:OldWoodenChair",
        "   =Prefab:999",
        "   =SwatchGroup:777",
        "   =SwatchColorZoneCount:1",
    ]) + "\r\n"

    repaired = setting.replace_entry(
        stale, "AllItems", "GUID", "12345",
        [("GUID", "12345"), ("DisplayName", "OldWoodenChair"),
         ("Prefab", "111"), ("HasSwatches", "False")],
    )
    check(repaired is not None, "the entry was found")
    check("=SwatchGroup:" not in repaired, "the bad field is gone", repaired)
    check("=HasSwatches:False" in repaired, "the right one is there")
    check("=Prefab:111" in repaired and "=Prefab:999" not in repaired,
          "and the changed value took", repaired)
    check(repaired.count("i0") == 1 and "  s1" in repaired,
          "the list length and index are untouched", repaired)

    missing = setting.replace_entry(
        stale, "AllItems", "GUID", "nope", [("GUID", "nope")]
    )
    check(missing is None, "an absent entry reports itself rather than guessing")


def test_surface_cleanup():
    """The Surfaces.setting 0.6.0 wrote crashes the game, so it has to go."""
    section("Removing a surface written by an earlier version")
    from paraforge import item, journal, setting

    temp = tempfile.mkdtemp(prefix="paraforge_surface_")
    mod = os.path.join(temp, "Cleanup_7.mod")
    os.makedirs(os.path.join(mod, "Settings"))
    seed = sidecar.mod_name(mod)

    ours = sidecar.guid_for(seed, "surface", "Chair")
    text = "\r\n".join([
        "#Setting.Surfaces",
        " =AllSurfaces",
        "  s1",
        "  i0",
        "   =GUID:" + ours,
        "   =DisplayName:Chair",
        "   =Texture:4242",
    ]) + "\r\n"

    mine, foreign = item.our_surface_entries(text, seed)
    check(len(mine) == 1 and not foreign, "a surface we wrote is recognised")

    handwritten = text.replace("=GUID:" + ours, "=GUID:5150")
    mine, foreign = item.our_surface_entries(handwritten, seed)
    check(not mine and len(foreign) == 1,
          "one somebody else wrote is not claimed")

    path = os.path.join(mod, "Settings", "Surfaces.setting")
    setting.write(path, text)
    sidecar.write(path, spec.META_TYPE_SETTING, "1")

    # A second item whose prefab points at the surface about to disappear.
    other = os.path.join(mod, "Stool.prefab")
    setting.write(other, "\r\n".join([
        "ItemMeshReference:",
        " Surfaces:",
        "  Surface:",
        "   GUID:4242",
        "   Value:" + ours,
        "---",
    ]) + "\r\n")

    run = journal.Run(mod, "Chair")
    result = item.Result()
    item._drop_legacy_surfaces(run, result, mod, seed)
    run.record()

    check(not os.path.isfile(path), "ours is deleted")
    check(not os.path.isfile(path + ".meta"), "with its meta")

    other_text = setting.read(other)
    check("Value:" + spec.DEFAULT_SURFACE_GUID in other_text,
          "a prefab left dangling is repointed at the shared surface",
          other_text)
    check("Value:" + ours not in other_text,
          "and no longer names the surface that went away")
    check(any("Removed" in note or "Retir" in note for note in result.notes),
          "and it is reported, not done silently", str(result.notes))

    restored = journal.undo_last(mod)
    check(restored is not None and os.path.isfile(path),
          "undo puts it back", str(restored))

    # A file we did not write is left alone.
    setting.write(path, handwritten)
    run = journal.Run(mod, "Chair")
    result = item.Result()
    item._drop_legacy_surfaces(run, result, mod, seed)
    check(os.path.isfile(path), "a foreign surface file survives")
    check(bool(result.notes), "and the user is told why", str(result.notes))

    shutil.rmtree(temp, ignore_errors=True)


def test_undo(mod):
    """The whole point of touching someone else's file: being able to stop."""
    section("Undoing")
    from paraforge import journal

    items = os.path.join(mod, "Settings", "Items.setting")
    prefab = os.path.join(mod, "OldWoodenChair.prefab")

    # A second item, so undo has to unpick a merge rather than a fresh file.
    settings = props.settings(bpy.context)
    settings.asset_name = "SecondThing"
    fresh = os.path.join(mod, "SecondThing.fbx")
    with open(fresh, "wb") as handle:
        handle.write(b"not really an fbx")
    bpy.ops.paraforge.generate_item()

    two = open(items, encoding="utf-8").read()
    check(two.count("=DisplayName:") == 2, "two items now", two.count("=DisplayName:"))

    runs = journal.load(mod)
    check(len(runs) >= 2, "both runs are journalled", str(len(runs)))

    result = bpy.ops.paraforge.undo_last()
    check("FINISHED" in result, "undo ran", str(result))

    one = open(items, encoding="utf-8").read()
    check(one.count("=DisplayName:") == 1, "back to one item",
          one.count("=DisplayName:"))
    check("OldWoodenChair" in one, "and it is the right one")
    check(not os.path.isfile(os.path.join(mod, "SecondThing.prefab")),
          "the prefab it created is gone")
    check(os.path.isfile(prefab), "the first item's prefab is untouched")

    bpy.ops.paraforge.undo_last()
    after = open(items, encoding="utf-8").read() if os.path.isfile(items) else ""
    check("OldWoodenChair" not in after, "a second undo steps back further",
          after[:60])
    check(not journal.load(mod), "and the journal is empty")
    check(not os.path.isdir(os.path.join(mod, "Settings")),
          "the Settings folder it created is gone too")

    # And the prefab points at the mesh through its own root object, the way
    # the game's own prefabs do.
    from paraforge import item as item_module

    text = item_module.prefab_text("X", "123", (1.0, 1.0, 1.0))
    root = [l for l in text.splitlines() if l.startswith("ItemObject:")][0]
    check(root != "ItemObject:123", "the root has an identity of its own", root)
    check("   AssetMesh:123" in text, "and the mesh is still referenced")

    # The yellow scaling handle. The game creates the widget only for a root
    # that declares IsScalable, and the drag only reaches the axes named, so
    # the flag on its own would give a handle that does nothing.
    check(" IsScalable:True" not in text,
          "a prefab asked for nothing stays unscalable")

    scalable = item_module.prefab_text("X", "123", (1.0, 1.0, 1.0),
                                       scalable=True)
    check(" IsScalable:True" in scalable, "asked for it, the flag is written")
    check("  ScalableAxes:bool3(True, True, True)" in scalable,
          "on all three axes, as 983 of the game's 1114 scalable items are")
    check("  HasMinScale:True" in scalable and "  HasMaxScale:True" in scalable,
          "with the two booleans the clamp actually reads")
    check("  MinScale:0.1" in scalable and "  MaxScale:10" in scalable,
          "and the bounds themselves, wide enough to be worth a handle",
          [l for l in scalable.splitlines() if "Scale" in l])
    check(scalable.index(" IsScalable:True")
          < scalable.index(" ItemMeshReferences:"),
          "written before the mesh reference, in the game's own field order")

    # Stretching is the game's other handle and a separate declaration: the
    # root says the item may be stretched and between what dimensions, the
    # mesh reference says which of its own axes follow. Without the second
    # the cube stretches and the mesh inside it does not.
    check(" IsResizable" not in scalable,
          "a scalable item is not stretchable by accident")

    stretch = item_module.prefab_text(
        "X", "123", (2.0, 1.0, 0.5), resizable=True,
        resizable_axes=(True, False, True),
    )
    check(" IsResizable:True" in stretch, "asked for it, the root declares it")
    check("  ResizableAxes:bool3(True, False, True)" in stretch,
          "on the axes asked for, and only those",
          [l for l in stretch.splitlines() if "Resizable" in l])
    check(" IsResizable:bool3(True, False, True)" in stretch,
          "and the mesh reference names the same axes")
    check(stretch.index(" IsResizable:True")
          < stretch.index("ItemMeshReference:")
          < stretch.rindex(" IsResizable:bool3"),
          "the root first, the mesh reference after, as the game writes them")

    # The bounds are metres in the same order as Size, so they follow the
    # item's own measurements rather than a number out of the air.
    check("  MinSizes:(0.2000, 0.1000, 0.0500)" in stretch,
          "the floor is the item's size times the smallest factor",
          [l for l in stretch.splitlines() if "Sizes" in l])
    check("  MaxSizes:(20.0000, 10.0000, 5.0000)" in stretch,
          "and the ceiling times the largest")
    check("  HasMaxSize:True" in stretch,
          "with the boolean that gates the ceiling, since only MinSizes is "
          "read unconditionally")
    check("HasMinSize" not in stretch,
          "and no HasMinSize, which does not exist anywhere in the game")

    both = item_module.prefab_text("X", "123", (1.0, 1.0, 1.0),
                                   scalable=True, resizable=True)
    check(" IsScalable:True" in both and " IsResizable:True" in both,
          "an item can carry both, as 133 of the game's own do")


def test_create_mod():
    section("Creating a mod")
    from paraforge import modfolder

    root = tempfile.mkdtemp(prefix="paraforge_root_")
    folder, created = modfolder.create_mod(root, "My Pack!")
    check(created, "a fresh mod was created")
    check(folder.endswith("My Pack.mod"),
          "the name is cleaned but kept readable", folder)

    meta = sidecar.read(os.path.join(folder, os.path.basename(folder)))
    check(meta.get("Type") == str(spec.META_TYPE_MOD), "typed as a mod",
          str(meta))
    check(meta.get("IsSystemMod") == "False",
          "and not a system mod, so it can go on the Workshop")
    check(meta.get("Enabled") == "True", "and enabled")
    check(meta.get("CreationTime", "").isdigit(), "with a .NET timestamp",
          meta.get("CreationTime"))
    # 2020 in .NET ticks, a sanity floor that will not drift.
    check(int(meta["CreationTime"]) > 637_000_000_000_000_000,
          "that is actually in this century", meta.get("CreationTime"))

    again, created_again = modfolder.create_mod(root, "My Pack!")
    check(again == folder and not created_again,
          "asking twice selects the existing one")

    check(not modfolder.is_system_mod(folder), "ours is not a system mod")
    system = os.path.join(root, "Local.mod")
    os.makedirs(system)
    sidecar.write(os.path.join(system, "Local.mod"), spec.META_TYPE_MOD, "1",
                  {"IsSystemMod": "True"})
    check(modfolder.is_system_mod(system), "the game's scratch folder is")


def test_language():
    section("Language")
    check(i18n.DEFAULT == "fr", "French is the default")

    # The language is saved in the user's Blender config, so the assertions
    # below have to pin it. Without this the suite passes or fails depending
    # on which language the person running it last picked in the panel.
    previous = i18n._current
    try:
        i18n._current = "fr"
        check(i18n.t("Export to Paralives") == "Exporter vers Paralives",
              "the catalogue is wired up", i18n.t("Export to Paralives"))
        check(i18n.t("{0} ok   {1} warn   {2} blocking", 1, 2, 3)
              == "1 ok   2 alerte   3 bloquant",
              "arguments are formatted after translation",
              i18n.t("{0} ok   {1} warn   {2} blocking", 1, 2, 3))
        check(i18n.t("a string nobody translated")
              == "a string nobody translated",
              "a missing key falls back instead of raising")

        i18n._current = "en"
        check(i18n.t("Export to Paralives") == "Export to Paralives",
              "English is the source text, untouched")
    finally:
        i18n._current = previous


# --------------------------------------------------------------------------


def main():
    print("ParaForge headless test, Blender " + bpy.app.version_string)
    paraforge.register()
    temp = None
    try:
        test_spec()
        test_measurement()
        test_validation_and_fixes()
        test_wall_rule()
        test_zones()
        test_zones_from_materials()
        test_language()
        test_catalog()
        test_sidecars()
        test_refuses_the_game_folder()
        test_setting_merge()
        test_create_mod()
        test_texture_planning()
        test_downloaded_asset()
        test_recolourable_conversion()
        test_sketchfab_names()
        test_role_override()
        test_bake_to_atlas()
        test_language_reload()
        temp, mod = test_export()
        test_inspector(mod)
        test_export_units()
        test_uv_transform()
        test_remesh()
        test_preview()
        test_decimate_rebake()
        test_two_items_share_nothing()
        test_asset_name_guard()
        test_shared_surface_fallback()
        test_repair_stale_entry()
        test_surface_cleanup()
        _t, item_mod, _b = test_generate_item()
        test_undo(item_mod)
    except Exception:
        traceback.print_exc()
        FAILURES.append("exception")
    finally:
        try:
            paraforge.unregister()
        except Exception:
            traceback.print_exc()

    print("")
    print("=" * 60)
    if FAILURES:
        print("{0} of {1} checks FAILED: {2}".format(
            len(FAILURES), CHECKED, ", ".join(FAILURES)))
        sys.exit(1)
    print("all {0} checks passed".format(CHECKED))
    if temp:
        print("artifacts in " + temp)
    sys.exit(0)


if __name__ == "__main__":
    main()
