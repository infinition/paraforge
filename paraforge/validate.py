# SPDX-License-Identifier: GPL-3.0-or-later
"""The checklist.

Every rule Paralives imposes is turned into one line with a colour, a reason,
and where possible a button that fixes it. The point is that no failure should
ever be discovered by relaunching the game.
"""

from . import catalog, geo, i18n, item, spec, textures, uvxform

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
        self.seat_height = None
        self.backrest = None

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
    _check_asset_name(objects, settings, report)
    _check_usable(settings, report)
    _check_seat(objects, settings, measurement, depsgraph, report)
    _check_handles(settings, report)
    _check_backrest(objects, settings, depsgraph, report)
    _check_color_zones(objects, settings, report)
    _check_uvs(objects, report)
    _check_uv_transform(objects, report)
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

    if getattr(settings, "keep_origin", False):
        # Somebody put it where they wanted it. A door that swings on its
        # hinge and a sign that hangs off its bracket both need an origin the
        # rule would move, and a check that cannot be satisfied is a check
        # people learn to ignore.
        report.add(
            "origin", _("Origin placement"), OK,
            _("Placed by hand, so the rule for this item type is not "
              "applied. The item is anchored here when the game places it"),
            fix="paraforge.fix_origin", fix_label=_("Back to the rule"),
        )
        return

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
        # The button stays under the line even when the line is green: an
        # origin that follows the rule is still one somebody may want to move,
        # and a fix that only appears once something is broken cannot be used
        # to put it back.
        report.add(
            "origin", _("Origin placement"), OK,
            _(spec.ITEM_TYPES[item_type]["description"]),
            fix="paraforge.fix_origin", fix_label=_("Snap origin"),
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


def _check_usable(settings, report):
    """Whether a Para will ever do anything with the item.

    A chair carries no seat of its own. Of the game's 2434 prefabs only 58 name
    a NestedPrefabToSpawn, and no couch, stool or bench names one. What makes
    an item usable is its catalogue tag, through two separate fields on the tag
    entry in BuildModeCatalogTags.setting:

        NestedPrefabToSpawn   the slot template, on 13 tags. It holds the Seat,
                              the ButtLocator and the foot locators, so nothing
                              about the animation has to be authored.
        InteractionGroup      what a Para may do with it, on 47 tags.

    Tags inherit, so Armchairs seats a Para through Seating without declaring
    anything itself.

    An imported chair filed under the wrong tag is furniture nobody sits on,
    and the Para walks to another chair instead. The export cannot fix that,
    only the tag can, which is why this reads as information next to the choice
    rather than as a fault: most items are decoration and are meant to be.
    """
    tag = settings.catalog_tag
    if tag == spec.CUSTOM_TAG:
        report.add("usable", _("Used by a Para"), OK,
                   _("A tag typed by hand, so this cannot be checked"))
        return

    template = catalog.slot_template(tag)
    source = catalog.interaction_source(tag)
    parts = []

    if catalog.seats_a_para(tag):
        parts.append(_("a place to sit, from {0}", template))
    elif template:
        parts.append(_("{0}, which is a sound rather than a place", template))

    if source:
        parts.append(_("interactions, from the {0} tag", source))

    if parts:
        report.add("usable", _("Used by a Para"), OK,
                   _("This tag brings ") + ", ".join(parts))
        return

    report.add("usable", _("Used by a Para"), OK,
               _("Decoration: this tag brings neither a place to sit nor an "
                 "interaction, so a Para will walk past it. Seating lives "
                 "under Chairs, Armchairs, OfficeChairs, Couches or Benches"))


def _check_backrest(objects, settings, depsgraph, report):
    """Which way round the item is, for anything with a back to it.

    A Para sits facing Y+, along the floor arrow. Not reasoned out of the
    template's locators, which is how this got stated backwards once already,
    but measured: imported into Blender, 43 of the game's 48 chairs and
    armchairs put their backrest on the Y- side, 4 are too symmetrical to say
    and 1 disagrees.

    Build one the other way round and nothing fails. The item is in the
    catalogue, a Para walks over, sits down, and faces their own backrest.
    That is worth catching in Blender, where a half turn fixes it.

    A stool, a pouf and a bench have no back, so there is nothing to be wrong
    about and the check stays quiet.
    """
    template, seats = item.seat_choice(settings)
    if not seats:
        return

    offset = geo.backrest_side(objects, depsgraph)
    report.backrest = offset
    label = _("Which way round")
    if offset is None or abs(offset) < spec.BACKREST_MIN_OFFSET:
        report.add("backrest", label, OK,
                   _("Nothing stands above the seat, so there is no back to "
                     "put the wrong way. A Para sits facing Y+, along the "
                     "arrow"))
        return

    if offset < 0.0:
        report.add("backrest", label, OK, _(
            "The back is on the Y- side, where 43 of the game's 48 chairs "
            "put theirs. A Para sits facing the arrow"))
        return

    report.add(
        "backrest", label, WARN,
        _("The back is on the Y+ side, facing the arrow. A Para will sit "
          "down and face their own backrest. Turn the item half a turn"),
        fix="paraforge.rotate_to_face", fix_label=_("Turn it around"),
    )


def _check_handles(settings, report):
    """The resize widgets, against what the item is for.

    Joining the game's whole catalogue to its prefabs by GUID and grouping
    every item by the template it gets: the 54 items on a chair, armchair or
    toilet template hold one resize handle between them, while the 13 on a
    couch template and the 10 on a bench template are resizable to the last
    one, as are the 79 counters and the 22 tables.

    So it is not sitting that the handle breaks. A couch carries a row of
    seats and survives being stretched; a chair carries one, and moving it
    puts it where the Para cannot path to. The sit then fails in silence: the
    item is in the catalogue, renders, accepts the command, and the Para walks
    off to another chair with nothing logged.
    """
    if not item.sits_on_it(settings):
        return
    asked = getattr(settings, "scalable", False) or getattr(
        settings, "resizable", False)
    if not asked:
        return
    report.add(
        "handles", _("Resize handles"), OK,
        _("Left out. The game's 54 chairs, armchairs and toilets hold one "
          "resize handle between them, because a chair has a single seat and "
          "moving it puts it out of reach. Couches and benches keep theirs"),
    )


def _check_seat(objects, settings, measurement, depsgraph, report):
    """How high the seat is, and which way a Para will face on it.

    Nothing in the mesh tells the game where to sit, and nothing fixes the
    height either: every slot template carries VaryBasedOnHeight on its seat
    locator, with Min and Max children bounding the travel, so the game moves
    the Para to suit the item. That is why a stool and a dining chair both work
    through ChairSlotAndLocator.

    What it cannot do is invent a surface. A mesh whose only flat top is at
    1.2 m still seats a Para, who then floats, and nothing is logged because
    nothing failed. So the height is measured and shown, next to what the
    game's own furniture does:

        chairs, office chairs, benches, ottomans   around 0.45 m
        stools                                     around 0.65 m

    and a fault is only raised outside 0.20 to 0.75, where no shipped item
    sits. Inside it this is information, because 0.45 against 0.65 is a
    decision about what the item is, not a mistake.

    Which way they face is a separate question, answered by _check_backrest.
    """
    template, seats = item.seat_choice(settings)
    if not seats or measurement.empty:
        return

    label = _("Seat height")
    height, area = geo.seat_height(objects, depsgraph)
    report.seat_height = height

    if height is None:
        report.add(
            "seat", label, WARN,
            _("No flat surface clear of the floor, so there is nothing to sit "
              "on. {0} will still seat a Para, in mid air", template),
        )
        return

    span = float(measurement.size[2])
    ratio = (height / span * 100.0) if span > 1e-6 else 0.0
    detail = _("{0:.3f} m, {1:.0f}% of the height, over {2:.2f} m2",
               height, ratio, area)

    if height < spec.SEAT_MIN:
        report.add("seat", label, WARN, detail + _(
            ". Lower than anything the game seats a Para on, so they will sink "
            "into it. Its lowest is around {0:.2f}", spec.SEAT_MIN))
    elif height > spec.SEAT_MAX:
        report.add("seat", label, WARN, detail + _(
            ". Higher than anything the game seats a Para on, so they will "
            "float. Its tallest is a stool at {0:.2f}", spec.SEAT_STOOL))
    elif abs(height - spec.SEAT_STOOL) < abs(height - spec.SEAT_CHAIR):
        report.add("seat", label, OK, detail + _(
            ". Stool height: the game's sit at {0:.2f}", spec.SEAT_STOOL))
    else:
        report.add("seat", label, OK, detail + _(
            ". Chair height: the game's sit at {0:.2f}", spec.SEAT_CHAIR))


def _check_asset_name(objects, settings, report):
    """The name is the identity of the item, so a borrowed one is dangerous.

    Every file written into the mod, and every GUID derived for it, comes from
    this name. Two imports that both answer to Mesh_0 therefore write the same
    files, and the second silently replaces the first: the chair already in the
    catalogue starts showing the vase.
    """
    import os

    from . import textures

    explicit = (settings.asset_name or "").strip()
    fallback = objects[0].name if objects else ""
    resolved = textures.pascal_case(explicit or fallback)

    if not resolved:
        report.add("name", _("Asset name"), FAIL, _("Give the item a name"))
        return

    if not explicit and spec.looks_generic(fallback):
        report.add(
            "name", _("Asset name"), FAIL,
            _("No name set, so the object name {0} would be used. Another "
              "import called the same thing would overwrite this item in the "
              "game", fallback),
        )
        return

    if spec.looks_generic(resolved):
        report.add(
            "name", _("Asset name"), WARN,
            _("{0} is a name an importer chose, not one you did. Anything "
              "else exported under it replaces this item", resolved),
        )
        return

    # Already something of that name in the mod, carrying different geometry?
    mod_path = (settings.mod_folder or "").strip()
    existing = os.path.join(mod_path, resolved + ".fbx") if mod_path else ""
    if existing and os.path.isfile(existing):
        report.add(
            "name", _("Asset name"), WARN,
            _("{0} is already in this mod. Exporting replaces it, which is "
              "what you want for an update and not for a new item",
              resolved + ".fbx"),
        )
        return

    detail = resolved
    if not explicit:
        detail = _("{0}, taken from the object", resolved)
    report.add("name", _("Asset name"), OK, detail)


def _check_color_zones(objects, settings, report):
    zones, illegal, missing = geo.color_zones(objects)

    # An item that is not recolourable must reach the game with no colour
    # attribute at all. Any attribute makes the mesh ZoneDefinition:VertexZones
    # and there is no shader for that on a plain surface, so the item loads,
    # takes its footprint, and draws nothing. The export strips them, and
    # offering to create one here would be pointing at the trap.
    if not settings.recolourable:
        carried = len(objects) - len(missing)
        if carried > 0:
            report.add(
                "zones", _("Colour zones"), OK,
                _("Not used. They stay in Blender and are left out of the "
                  "FBX, because a non recolourable item that carries them "
                  "does not render"),
            )
        else:
            report.add(
                "zones", _("Colour zones"), OK,
                _("Not used, which is what a non recolourable item wants"),
            )
        return

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


def _check_uv_transform(objects, report):
    """Only worth a line when the material moves its coordinates.

    An FBX carries a mesh and its UV maps and nothing else, so a Mapping node
    is dropped at the door and the game samples the coordinates raw. ParaForge
    bakes the transform into the exported UVs instead, which is exact; the
    check exists to say so, and to name what it could not take along.
    """
    resolved = uvxform.resolve(objects)

    if resolved.blockers:
        image, reason = resolved.blockers[0]
        report.add(
            "uvtransform", _("Texture coordinates"), WARN,
            _("{0} cannot be carried over: {1}. Bake the selection into one "
              "atlas to fix it for good", image, reason),
            fix="paraforge.bake_to_atlas",
            fix_label=_("Bake into one atlas"),
        )
        return

    if resolved.variants:
        report.add(
            "uvtransform", _("Texture coordinates"), WARN,
            _("The textures are not all placed the same way ({0}). Only one "
              "placement can be exported, so bake the selection into one "
              "atlas", ", ".join(sorted(set(resolved.variants))[:3])),
            fix="paraforge.bake_to_atlas",
            fix_label=_("Bake into one atlas"),
        )
        return

    if resolved.moves:
        report.add(
            "uvtransform", _("Texture coordinates"), OK,
            _("The material moves them ({0}); the export bakes that into the "
              "UVs", uvxform.describe(resolved.matrix)),
        )


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
    from . import preview

    # While the preview is on it is the preview's own material on the object,
    # so rebuilding the plan here would read the converted textures back as if
    # they were the source: "copied PapanierDetail" where it said "rebuilt from
    # Image_2, Image_1". The plan that produced the preview is kept instead.
    plan = preview.frozen()
    if plan is None:
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
    elif missing and len(missing) == len(spec.ALBEDO_SUFFIXES):
        # Missing every albedo means the item has no colour at all.
        report.add(
            "textures", _("Texture naming"), WARN,
            _("No Detail or GrayMask map, the item will have no colour of "
              "its own"),
        )
    else:
        report.add(
            "textures", _("Texture naming"), OK,
            _("{0} texture(s), all roles recognised", len(plan.outputs)),
        )

    _check_texture_size(plan, report)


def _check_texture_size(plan, report):
    """Downloads arrive at 4K. Nothing in the game is bigger than 2K."""
    from . import imaging

    largest = 0
    worst = ""
    for source in plan.sources:
        width, height = imaging.dimensions(source.image)
        if max(width, height) > largest:
            largest = max(width, height)
            worst = source.stem

    if not largest:
        return
    if largest > spec.MAX_SENSIBLE_TEXTURE_SIZE:
        report.add(
            "texsize", _("Texture size"), WARN,
            _("{0} is {1} px. Paralives ships 256 to 1024, and nothing above "
              "{2}. Downscaling costs nothing visible on an item this size",
              worst, largest, spec.MAX_SENSIBLE_TEXTURE_SIZE),
            fix="paraforge.downscale_textures",
            fix_label=_("Downscale to {0} px", spec.MAX_SENSIBLE_TEXTURE_SIZE),
        )
    else:
        report.add("texsize", _("Texture size"), OK,
                   _("largest is {0} px", largest))


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
