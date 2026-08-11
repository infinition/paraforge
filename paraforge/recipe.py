# SPDX-License-Identifier: GPL-3.0-or-later
"""The Control Panel checklist.

Everything up to the FBX is automated. What is left is the pass inside the
game: create the Item, create the Prefab, add ItemMeshReference, pick the
mesh, fit the bounding box, assign the surface, tag it, pick a swatch group.

This module writes that pass out with your values already filled in, so it
becomes a checklist to read rather than something to remember. If the mod
folder inspector shows the game stores items as text, this same data is what
a generator would consume.
"""

import datetime
import os

from . import i18n, spec

_ = i18n.t

FOLDER = "_paraforge"


def catalog_label(settings):
    if settings.catalog_tag == "CUSTOM":
        return settings.catalog_tag_custom.strip() or _("(not set)")
    for key, label, _description in spec.CATALOG_TAGS:
        if key == settings.catalog_tag:
            return label
    return settings.catalog_tag


def build(settings, name, report, files):
    zones = _zone_summary(report)
    textures = [os.path.basename(p) for p in files if not p.lower().endswith(".fbx")]
    meshes = [os.path.basename(p) for p in files if p.lower().endswith(".fbx")]

    def title(text):
        return [text, "-" * len(text)]

    lines = []
    lines.append(_("ParaForge recipe for: ") + name)
    lines.append(_("Written ")
                 + datetime.datetime.now().isoformat(timespec="seconds"))
    lines.append("")
    lines.extend(title(_("Files written into the mod folder")))
    for mesh in meshes:
        lines.append("  mesh     " + mesh)
    for texture in textures:
        _base, suffix = spec.split_suffix(os.path.splitext(texture)[0])
        role = suffix or _("UNKNOWN ROLE, the game will not auto configure it")
        lines.append("  texture  {0}   [{1}]".format(texture, role))
    lines.append("")

    lines.extend(title(_("Values to enter in the Control Panel")))
    lines.append("  " + _("Display name").ljust(18) + name)
    lines.append("  " + _("Item type").ljust(18)
                 + _(spec.ITEM_TYPES[settings.item_type]["label"]))
    lines.append("  " + _("Item tag").ljust(18) + catalog_label(settings))
    lines.append("  " + _("Swatch group").ljust(18)
                 + (settings.swatch_group or _("(not set)")))
    lines.append("  " + _("Colour zones").ljust(18) + zones)
    lines.append("  " + _("Thumbnail type").ljust(18)
                 + ("OneColor" if _zone_count(report) <= 1 else "MultiColor"))
    lines.append("")

    lines.extend(title(_("Steps, in order")))
    for index, step in enumerate(_steps(settings, name), start=1):
        lines.append("  {0}. {1}".format(index, step))
    lines.append("")

    lines.extend(title(_("Reminders")))
    lines.append("  " + _("The game imports assets at launch, there is no hot "
                          "reload. Restart Paralives after writing new files."))
    lines.append("  " + _("Detail and ColorZone maps are assigned in the "
                          "Prefab Editor, not in the Surfaces panel."))
    return "\n".join(lines) + "\n"


def _steps(settings, name):
    return (
        _("Control Panel > Build > Items, click + next to All Items"),
        _('Display name: "{0}", confirm the translation', name),
        _("Click the icon next to Prefab to create one, the Prefab Editor "
          "opens"),
        _("Select Root, click Add, search ItemMeshReference"),
        _("Asset Mesh: pick {0}.fbx", name),
        _("Click Set Edited Prefab Size to Mesh Size to fit the bounding box"),
        _("Assign the surface, then the Detail or ColorZone map if the item "
          "has one"),
        _("Save, which returns you to the Items page"),
        _("Item Tag: {0}, this also sets the base price",
          catalog_label(settings)),
        _("Swatch Group: {0}, then set the colour zone count",
          settings.swatch_group or _("(pick one)")),
        _("Check it in Build Mode, then upload with the cloud icon"),
    )


def _zone_count(report):
    if report is None:
        return 1
    check = next((c for c in report.checks if c.key == "zones"), None)
    if check is None:
        return 1
    digits = [int(c) for c in check.detail if c.isdigit()]
    return digits[0] if digits else 1


def _zone_summary(report):
    if report is None:
        return _("unknown")
    check = next((c for c in report.checks if c.key == "zones"), None)
    return check.detail if check else _("unknown")


def write(mod_path, name, text):
    folder = os.path.join(mod_path, FOLDER)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".recipe.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
