# SPDX-License-Identifier: GPL-3.0-or-later
"""The checklist.

Every rule Paralives imposes is turned into one line with a colour, a reason,
and where possible a button that fixes it. The point is that no failure should
ever be discovered by relaunching the game.
"""

from . import geo, i18n, spec, textures

_ = i18n.t

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
TODO = "TODO"

#: Ordering used for the worst-first summary.
SEVERITY = {OK: 0, TODO: 1, WARN: 2, FAIL: 3}


class Check:
    __slots__ = ("key", "label", "status", "detail", "fix", "fix_label")

    def __init__(self, key, label, status, detail="", fix=None, fix_label=""):
        self.key = key
        self.label = label
        self.status = status
        self.detail = detail
        self.fix = fix
        self.fix_label = fix_label

    @property
    def blocking(self):
        return self.status == FAIL


class Report:
    def __init__(self):
        self.checks = []
        self.measurement = None
        self.texture_plan = None

    def add(self, *args, **kwargs):
        self.checks.append(Check(*args, **kwargs))

    @property
    def worst(self):
        if not self.checks:
            return OK
        return max((c.status for c in self.checks), key=lambda s: SEVERITY[s])

    @property
    def can_export(self):
        return not any(c.blocking for c in self.checks)

    @property
    def counts(self):
        tally = {OK: 0, WARN: 0, FAIL: 0, TODO: 0}
        for check in self.checks:
            tally[check.status] += 1
        return tally

    def fixable(self):
        return [c for c in self.checks if c.fix and c.status in (FAIL, WARN)]


def target_objects(context):
    """Mesh objects the report applies to: the selection, or the active object."""
    selected = [o for o in context.selected_objects if o.type == "MESH"]
    if selected:
        return selected
    active = context.active_object
    if active is not None and active.type == "MESH":
        return [active]
    return []


def run(context, settings):
    """Build the full report for the current selection."""
    report = Report()
    objects = target_objects(context)

    if not objects:
        report.add(
            "selection", _("Mesh selected"), FAIL,
            _("Select the mesh you want to export"),
        )
        return report

    depsgraph = context.evaluated_depsgraph_get()
    measurement = geo.measure(objects, depsgraph)
    report.measurement = measurement

    _check_scene_units(context, report)
    _check_transforms(objects, report)
    _check_origin(measurement, settings, report)
    _check_size(measurement, settings, report)
    _check_facing(settings, report)
    _check_color_zones(objects, report)
    _check_uvs(objects, report)
    _check_topology(measurement, settings, report)
    _check_textures(objects, settings, report)
    _check_destination(settings, report)

    return report


# --------------------------------------------------------------------------


def _check_scene_units(context, report):
    unit = context.scene.unit_settings
    scale = getattr(unit, "scale_length", 1.0)
    if abs(scale - 1.0) > 1e-6:
        report.add(
            "units", _("Scene unit scale"), FAIL,
            _("Unit scale is {0:.4f}, Paralives expects 1.0 (metres)", scale),
            fix="paraforge.fix_units", fix_label=_("Set to 1.0"),
        )
    else:
        report.add("units", _("Scene unit scale"), OK, _("1.0, metres"))


def _check_transforms(objects, report):
    dirty = [o.name for o in objects if not geo.transform_is_clean(o)]
    if dirty:
        report.add(
            "transforms", _("Transforms applied"), FAIL,
            _("Rotation or scale still on the object: ") + ", ".join(dirty[:3])
            + ("..." if len(dirty) > 3 else ""),
            fix="paraforge.fix_transforms",
            fix_label=_("Apply rotation and scale"),
        )
    else:
        report.add("transforms", _("Transforms applied"), OK,
                   _("rotation and scale are baked"))


def _check_origin(measurement, settings, report):
    item_type = settings.item_type
    anchors = spec.ITEM_TYPES[item_type]["anchors"]

    if measurement is None or measurement.empty:
        report.add("origin", _("Origin placement"), FAIL,
                   _("The mesh has no geometry"))
        return

    offsets = geo.anchor_offsets(measurement, item_type)
    problems = []
    for index, axis in enumerate("xyz"):
        anchor = anchors.get(axis)
        if anchor is None:
            continue
        if abs(offsets[index]) > spec.POSITION_TOLERANCE:
            problems.append(_(
                "{0} {1} is off by {2:+.4f} m",
                axis.upper(), _anchor_words(anchor), -offsets[index],
            ))

    if not any(anchors.values()):
        report.add(
            "origin", _("Origin placement"), WARN,
            _("No documented rule for this item type, check it by eye"),
        )
    elif problems:
        report.add(
            "origin", _("Origin placement"), FAIL, "; ".join(problems),
            fix="paraforge.fix_origin", fix_label=_("Snap origin"),
        )
    else:
        report.add(
            "origin", _("Origin placement"), OK,
            _(spec.ITEM_TYPES[item_type]["description"]),
        )


def _anchor_words(anchor):
    return {
        "center": _("centre"),
        "min": _("lower bound"),
        "max": _("upper bound"),
    }[anchor]


def _check_size(measurement, settings, report):
    if measurement is None or measurement.empty:
        return
    size = measurement.size
    tile = max(settings.tile_size, 1e-6)
    detail = _(
        "{0:.2f} x {1:.2f} x {2:.2f} m  ({3:.1f} x {4:.1f} tiles)",
        size[0], size[1], size[2], size[0] / tile, size[1] / tile,
    )
    largest = float(max(size))
    if largest <= 0.0:
        report.add("size", _("Bounding size"), FAIL,
                   _("The mesh is flat or empty"))
    elif largest > 50.0:
        report.add(
            "size", _("Bounding size"), WARN,
            detail + _("  looks too large, check your unit scale"),
        )
    elif largest < 0.02:
        report.add(
            "size", _("Bounding size"), WARN,
            detail + _("  looks too small, check your unit scale"),
        )
    else:
        report.add("size", _("Bounding size"), OK, detail)


def _check_facing(settings, report):
    if settings.facing_confirmed:
        report.add(
            "facing", _("Faces Y+"), OK,
            _("confirmed by eye against the viewport arrow"),
        )
    else:
        report.add(
            "facing", _("Faces Y+"), TODO,
            _("No reliable way to detect this automatically. Check the green "
              "arrow in the viewport, then confirm"),
            fix="paraforge.confirm_facing", fix_label=_("It faces the arrow"),
        )


def _check_color_zones(objects, report):
    zones, illegal, missing = geo.color_zones(objects)

    if missing and len(missing) == len(objects):
        report.add(
            "zones", _("Colour zones"), WARN,
            _("No colour attribute. The item will have a single zone unless "
              "you supply a ColorZone texture"),
            fix="paraforge.fix_add_color_attribute",
            fix_label=_("Create zone 0 (white)"),
        )
        return

    recolourable = sorted(z for z in zones if isinstance(z, int))
    has_decal = "decal" in zones

    if illegal:
        sample = ", ".join(
            "{0} rgb{1}".format(name, value) for name, value in illegal[:3]
        )
        report.add(
            "zones", _("Colour zones"), FAIL,
            _("Colours outside the legal set: ") + sample
            + _(". Only white, red, green, blue and yellow are read"),
            fix="paraforge.fix_snap_colors",
            fix_label=_("Snap to nearest zone"),
        )
        return

    if len(recolourable) > spec.MAX_COLOR_ZONES:
        report.add(
            "zones", _("Colour zones"), FAIL,
            _("{0} zones found, Build Mode allows {1}",
              len(recolourable), spec.MAX_COLOR_ZONES),
        )
        return

    parts = [_("zone {0}", z) for z in recolourable]
    if has_decal:
        parts.append(_("decal"))
    if missing:
        report.add(
            "zones", _("Colour zones"), WARN,
            _("{0}/{1} used, but no attribute on: {2}",
              len(recolourable), spec.MAX_COLOR_ZONES, ", ".join(missing[:3])),
            fix="paraforge.fix_add_color_attribute",
            fix_label=_("Create zone 0 (white)"),
        )
    else:
        report.add(
            "zones", _("Colour zones"), OK,
            _("{0}/{1} used ({2})",
              len(recolourable), spec.MAX_COLOR_ZONES,
              ", ".join(parts) if parts else _("none")),
        )


def _check_uvs(objects, report):
    counts = geo.uv_layer_count(objects)
    if not counts:
        return
    if min(counts) == 0:
        report.add(
            "uv", _("UV map"), FAIL,
            _("At least one object has no UV map, textures cannot be applied"),
        )
    elif max(counts) >= 2:
        report.add("uv", _("UV map"), OK,
                   _("UV1 present, UV2 present (deformations)"))
    else:
        report.add("uv", _("UV map"), OK, _("UV1 present"))


def _check_topology(measurement, settings, report):
    if measurement is None or measurement.empty:
        return

    budget = max(settings.triangle_budget, 1)
    triangles = measurement.triangles
    detail = _("{0} triangles after triangulation",
               "{0:,}".format(triangles).replace(",", " "))

    if triangles > budget:
        report.add(
            "tris", _("Triangle count"), WARN,
            detail + _(" over your {0} budget. Paralives publishes no "
                       "official limit, this is your own setting", budget),
            fix="paraforge.decimate_to_budget",
            fix_label=_("Reduce to the budget"),
        )
    else:
        report.add("tris", _("Triangle count"), OK, detail)

    if measurement.ngons:
        report.add(
            "ngons", _("N-gons"), WARN,
            _("{0} faces with more than 4 sides. They will be triangulated on "
              "export, which can shade badly", measurement.ngons),
        )
    else:
        report.add("ngons", _("N-gons"), OK, _("quads and triangles only"))


def _check_textures(objects, settings, report):
    plan = textures.build_plan(
        objects,
        settings.asset_name or _default_name(objects),
        settings.recolourable,
    )
    report.texture_plan = plan

    if not plan.sources:
        report.add(
            "textures", _("Textures"), WARN,
            _("No image found in the materials. The item will need a surface "
              "built from existing game textures"),
        )
        return

    unknown = plan.unknown
    duplicates = plan.duplicate_suffixes()
    missing = plan.missing_recommended()

    if not plan.outputs:
        names = ", ".join(source.stem for source in unknown[:3])
        report.add(
            "textures", _("Texture naming"), FAIL,
            _("No recognised role on: ") + names
            + _(". Run Auto-detect, or set the role by hand"),
            fix="paraforge.detect_roles", fix_label=_("Auto-detect"),
        )
    elif duplicates and plan.multi_group:
        # One set of maps per material. Not wrong in itself, the item can be
        # split into as many meshes, but Paralives gives one surface to one
        # mesh so it will not import as a single object.
        report.add(
            "textures", _("Texture naming"), WARN,
            _("{0} materials, so {1} sets of maps. Paralives gives one "
              "surface to one mesh: bake them together, or split the item "
              "into one mesh per material",
              len(plan.groups), len(plan.groups)),
            fix="paraforge.bake_to_atlas",
            fix_label=_("Bake into one surface"),
        )
    elif duplicates:
        report.add(
            "textures", _("Texture naming"), FAIL,
            _("More than one ") + ", ".join(duplicates)
            + _(" map. The game allows one"),
        )
    elif unknown:
        names = ", ".join(source.stem for source in unknown[:3])
        report.add(
            "textures", _("Texture naming"), WARN,
            _("No recognised role on: ") + names
            + _(". Run Auto-detect, or set the role by hand"),
            fix="paraforge.detect_roles", fix_label=_("Auto-detect"),
        )
    elif missing:
        report.add(
            "textures", _("Texture naming"), WARN,
            _("{0} texture(s) ready, missing {1}",
              len(plan.outputs), ", ".join(missing)),
        )
    else:
        report.add(
            "textures", _("Texture naming"), OK,
            _("{0} texture(s), all roles recognised", len(plan.outputs)),
        )


def _check_destination(settings, report):
    path = (settings.mod_folder or "").strip()
    if not path:
        report.add(
            "destination", _("Target mod folder"), FAIL,
            _("Pick a .mod folder, or create one from the game's Modding "
              "Tools first"),
        )
        return

    import os

    if not os.path.isdir(path):
        report.add(
            "destination", _("Target mod folder"), FAIL,
            _("Folder does not exist: ") + path,
        )
    elif not path.rstrip("/\\").endswith(spec.MOD_FOLDER_SUFFIX):
        report.add(
            "destination", _("Target mod folder"), WARN,
            _("Folder name does not end with .mod, the game may ignore it"),
        )
    else:
        report.add("destination", _("Target mod folder"), OK,
                   os.path.basename(path))


def _default_name(objects):
    return objects[0].name if objects else "Asset"
