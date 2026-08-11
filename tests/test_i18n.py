# SPDX-License-Identifier: GPL-3.0-or-later
"""Every translatable string must exist in the French catalogue.

A missing key is not a crash, t() falls back to English, so nothing else
would ever catch a half translated interface. Pure ast, no Blender needed:

    python tests/test_i18n.py
"""

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "paraforge")

#: Strings that are the same in both languages, or are proper nouns.
IDENTICAL = {
    "Orientation", "Textures", "Calibration", "Normal map", "Zone 0", "Zone 1",
    "Zone 2", "Zone 3", "Tolerance", "Master", "Detail", "GrayMask",
    "{0:.2f} x {1:.2f} x {2:.2f} m  ({3:.1f} x {4:.1f} tiles)",
}


def catalogue():
    """Load the French dictionary without importing bpy."""
    source = open(os.path.join(PACKAGE, "i18n.py"), encoding="utf-8").read()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "FR":
            return {ast.literal_eval(k) for k in node.value.keys}
    raise AssertionError("FR catalogue not found in i18n.py")


def used():
    """Every literal handed to t(), across the whole package."""
    found = {}
    for name in sorted(os.listdir(PACKAGE)):
        if not name.endswith(".py") or name == "i18n.py":
            continue
        path = os.path.join(PACKAGE, name)
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_t = (
                (isinstance(function, ast.Name) and function.id == "_")
                or (isinstance(function, ast.Attribute) and function.attr == "t")
            )
            if not is_t or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.setdefault(first.value, set()).add(name)
    return found


def dynamic_keys():
    """Strings translated indirectly, through spec tables."""
    source = open(os.path.join(PACKAGE, "spec.py"), encoding="utf-8").read()
    keys = set()
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        name = getattr(node.targets[0], "id", "")
        if name == "ITEM_TYPES":
            for value in node.value.values:
                for key, item in zip(value.keys, value.values):
                    if ast.literal_eval(key) in ("label", "description"):
                        keys.add(ast.literal_eval(item))
        elif name == "SOURCE_ROLES":
            for element in node.value.elts:
                # The identifier is a constant reference, only the two labels
                # after it are literals.
                keys.update(ast.literal_eval(e) for e in element.elts[1:])
    return keys


def main():
    known = catalogue()
    references = used()
    missing = {}

    for text, files in references.items():
        if text in known or text in IDENTICAL or not re.search(r"[A-Za-z]", text):
            continue
        missing[text] = files
    for text in dynamic_keys():
        if text not in known and text not in IDENTICAL:
            missing.setdefault(text, {"spec.py"})

    print("{0} translatable string(s), {1} in the catalogue".format(
        len(references) + len(dynamic_keys()), len(known)))

    if missing:
        print("")
        print("{0} MISSING from the French catalogue:".format(len(missing)))
        for text in sorted(missing):
            print('    {0!r}: "",   # {1}'.format(text, ", ".join(sorted(missing[text]))))
        sys.exit(1)

    unused = known - set(references) - dynamic_keys()
    if unused:
        print("")
        print("{0} unused catalogue entrie(s):".format(len(unused)))
        for text in sorted(unused):
            print("    " + repr(text))

    print("every string is translated")
    sys.exit(0)


if __name__ == "__main__":
    main()
