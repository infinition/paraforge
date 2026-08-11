# SPDX-License-Identifier: GPL-3.0-or-later
"""The .meta file the game keeps beside every asset.

Paralives stores its own content as a mod, which is how the format is known:
Main.mod inside the installation is a plain folder of FBX, PNG and text. Each
asset sits next to a .meta holding a GUID and its import settings:

    GUID:5420372222036713657
    Type:2
    ImportFileCheckSum:5D6F4CC12A2F34F3E83C40EED2B54DA40661F61A
    IsLinear:True
    GenerateTextureQualities:YesWithObjectSettings
    GenerateMipMaps:True

The wiki says the file name suffix makes the game assign the right settings.
Writing the .meta ourselves says it outright instead, and the mapping used
here was read back from the 800 odd textures the game ships, where it is
exactly consistent.

Two properties matter more than they look:

  * the GUID has to stay the same across re-exports. A prefab points at its
    mesh by GUID, so a fresh random number on every export would break the
    item every time it is rebuilt. It is derived from the mod and the file
    name instead, which is stable and still collision free in practice.
  * the checksum is deliberately left out. The game uses it to decide whether
    an asset needs re-importing, and a file it has never seen must be
    imported, so claiming otherwise would be a lie that costs a restart to
    discover.
"""

import hashlib
import os

from . import spec


def guid_for(*parts):
    """A stable 63 bit identifier derived from the given strings.

    Same inputs, same GUID, on any machine and at any time. Signed 64 bit is
    what the game uses, so the top bit is cleared to keep it positive, and
    zero is avoided because the game treats it as unset.
    """
    digest = hashlib.sha1("\x00".join(str(p) for p in parts).encode("utf-8"))
    value = int.from_bytes(digest.digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF
    return str(value or 1)


def mod_name(mod_path):
    name = os.path.basename(os.path.normpath(mod_path or ""))
    if name.endswith(spec.MOD_FOLDER_SUFFIX):
        name = name[: -len(spec.MOD_FOLDER_SUFFIX)]
    return name or "ParaForge"


def asset_guid(mod_path, filename):
    return guid_for("paraforge", mod_name(mod_path), filename)


def checksum(path):
    """SHA1 of a file, uppercase hex, the way the game writes it."""
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def texture_flags(suffix):
    flags = dict(spec.TEXTURE_META_COMMON)
    flags.update(spec.TEXTURE_META_FLAGS.get(suffix, {}))
    return flags


def write(path, type_code, guid, flags=None):
    """Write <path>.meta. Returns the path written."""
    lines = ["GUID:" + guid, "Type:" + str(type_code)]
    for key, value in (flags or {}).items():
        lines.append("{0}:{1}".format(key, value))

    destination = path + ".meta"
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return destination


def write_for_mesh(mod_path, path):
    name = os.path.basename(path)
    return write(path, spec.META_TYPE_MESH, asset_guid(mod_path, name))


def write_for_texture(mod_path, path, suffix):
    name = os.path.basename(path)
    return write(path, spec.META_TYPE_TEXTURE, asset_guid(mod_path, name),
                 texture_flags(suffix))


def read(path):
    """Parse an existing .meta into a dict, or {} when there is none."""
    try:
        with open(path + ".meta", "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out
