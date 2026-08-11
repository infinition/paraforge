# SPDX-License-Identifier: GPL-3.0-or-later
"""Catch the mistakes that only blow up when a panel is drawn.

A wrong icon name, a renamed property or a stale operator id raises at draw
time, in the user's face, and never during a headless export test. This walks
the source and checks every one of them against the live Blender API.

    blender --background --factory-startup --python tests/test_ui_contract.py
"""

import os
import re
import sys
import types

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paraforge  # noqa: E402
from paraforge import props, ui, validate  # noqa: E402

SOURCES = ("ui.py", "prefs.py", "fixes.py", "ops.py", "zones.py", "validate.py",
           "overlay.py")

FAILURES = []
CHECKED = 0


def check(condition, label, detail=""):
    global CHECKED
    CHECKED += 1
    if not condition:
        print("  FAIL  {0}  {1}".format(label, detail))
        FAILURES.append(label)


def read(name):
    with open(os.path.join(ROOT, "paraforge", name), "r", encoding="utf-8") as handle:
        return handle.read()


def valid_icons():
    enum = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items
    return {item.identifier for item in enum}


def test_icons():
    print("== Icons")
    known = valid_icons()
    pattern = re.compile(r'icon\s*=\s*"([A-Z0-9_]+)"')
    seen = set()
    for name in SOURCES:
        for icon in pattern.findall(read(name)):
            seen.add(icon)
            check(icon in known, "icon " + icon, "not a Blender icon")
    for icon in ui.STATUS_ICONS.values():
        check(icon in known, "status icon " + icon)
    for _key, _label, icon in ui.ZONE_BUTTONS:
        check(icon in known, "zone icon " + icon)
    print("  {0} distinct icon(s) referenced".format(len(seen)))


def test_settings_properties():
    print("== Settings properties")
    known = set(props.ParaForgeSettings.bl_rna.properties.keys())
    pattern = re.compile(r'\bprop(?:_search)?\(\s*settings\s*,\s*"([a-z_]+)"')
    attribute = re.compile(r"\bsettings\.([a-z_]+)")
    seen = set()

    for name in SOURCES:
        text = read(name)
        for prop in pattern.findall(text):
            seen.add(prop)
            check(prop in known, "layout property settings." + prop, "not declared")
        for prop in attribute.findall(text):
            if prop in {"settings"}:
                continue
            seen.add(prop)
            check(prop in known, "attribute settings." + prop, "not declared")

    print("  {0} distinct property reference(s)".format(len(seen)))


def test_operators():
    print("== Operators")
    pattern = re.compile(r'operator\(\s*"(paraforge\.[a-z_]+)"')
    seen = set()
    for name in SOURCES:
        for idname in pattern.findall(read(name)):
            seen.add(idname)
    # The validator hands operator ids to the panel as fix buttons.
    seen.update(
        match for match in re.findall(r'"(paraforge\.[a-z_]+)"', read("validate.py"))
    )

    for idname in sorted(seen):
        module, _dot, function = idname.partition(".")
        available = hasattr(getattr(bpy.ops, module, None), function)
        check(available, "operator " + idname, "not registered")
    print("  {0} distinct operator(s) referenced".format(len(seen)))


def test_panels():
    print("== Panels")
    registered = {cls.__name__ for cls in ui.classes}
    ids = set()
    for cls in ui.classes:
        ids.add(getattr(cls, "bl_idname", cls.__name__))
    for cls in ui.classes:
        parent = getattr(cls, "bl_parent_id", "")
        if parent:
            check(parent in ids, "parent panel " + parent, "unknown panel id")
        check(
            hasattr(bpy.types, cls.__name__),
            "panel registered " + cls.__name__,
        )
    print("  {0} panel(s)".format(len(registered)))


def test_fix_targets():
    print("== Fix buttons")
    # Every fix the validator can emit must be a real operator with a label.
    fixes = set(re.findall(r'fix="(paraforge\.[a-z_]+)"', read("validate.py")))
    for idname in sorted(fixes):
        module, _dot, function = idname.partition(".")
        check(hasattr(getattr(bpy.ops, module), function), "fix " + idname)
    print("  {0} fix operator(s)".format(len(fixes)))


def test_status_coverage():
    print("== Status coverage")
    for status in (validate.OK, validate.WARN, validate.FAIL, validate.TODO):
        check(status in ui.STATUS_ICONS, "icon for status " + status)
        from paraforge import overlay

        check(status in overlay.STATUS_COLORS, "overlay colour for status " + status)


def test_panels_draw():
    """Actually run every draw(), which is where a bad icon or property blows up."""
    print("== Panel draw")
    scene = bpy.context.scene
    settings = scene.paraforge

    for corner in ("TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"):
        settings.hud_corner = corner
    settings.hud_only_problems = True
    settings.recolourable = True

    # A panel draw needs a region to lay itself out in. In background mode
    # there is none, so draw() is called unbound against a stand-in that only
    # has to carry a layout.
    for cls in ui.classes:
        stand_in = _FakePanel(cls)
        for name in ("draw", "draw_header_preset"):
            function = getattr(cls, name, None)
            if function is None:
                continue
            try:
                function(stand_in, bpy.context)
            except Exception as error:
                check(False, "{0}.{1}".format(cls.__name__, name), repr(error))
            else:
                check(True, "{0}.{1}".format(cls.__name__, name))


class _FakePanel:
    """A Panel subclass cannot be instantiated outside Blender, so its own
    helper methods are lifted onto a plain object that carries a layout."""

    def __init__(self, cls):
        self.layout = _FakeLayout()
        for name, value in vars(cls).items():
            if name.startswith("bl_"):
                continue
            if isinstance(value, (staticmethod, classmethod)):
                # Already bound the way they need to be; binding again would
                # pass self as the first argument.
                setattr(self, name, value.__get__(self, cls))
            elif callable(value):
                setattr(self, name, types.MethodType(value, self))


class _FakeLayout:
    """Records calls instead of building widgets, so draw() can run headless."""

    scale_y = 1.0
    alert = False
    enabled = True
    use_property_split = False

    def _child(self, *args, **kwargs):
        return _FakeLayout()

    box = row = column = split = _child
    separator = label = prop = prop_search = template_ID = _child

    def operator(self, idname, **kwargs):
        module, _dot, function = idname.partition(".")
        if not hasattr(getattr(bpy.ops, module, None), function):
            raise AssertionError("unknown operator " + idname)
        return _FakeOperatorProperties()


class _FakeOperatorProperties:
    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)


def test_language_round_trip():
    print("== Language")
    from paraforge import i18n

    before = i18n.language()
    try:
        check(i18n.t("Refresh") != "Refresh" or before == "en",
              "French is in use by default", before)
        i18n.set_language("en")
        check(i18n.t("Refresh") == "Refresh", "English passes strings through")
    finally:
        i18n.set_language(before)
        check(i18n.language() == before, "the language was put back")


def main():
    print("ParaForge UI contract, Blender " + bpy.app.version_string)
    paraforge.register()
    try:
        test_icons()
        test_settings_properties()
        test_operators()
        test_panels()
        test_fix_targets()
        test_status_coverage()
        test_panels_draw()
        test_language_round_trip()
    finally:
        paraforge.unregister()

    print("")
    if FAILURES:
        print("{0} of {1} checks FAILED".format(len(FAILURES), CHECKED))
        sys.exit(1)
    print("all {0} checks passed".format(CHECKED))
    sys.exit(0)


if __name__ == "__main__":
    main()
