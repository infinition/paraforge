# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading and extending a Paralives .setting file.

The format is plain text driven by indentation:

    #Setting.Items
     =AllItems
      s2222
      i2189
       =GUID:5413764035250012132
       =DisplayName:ClutterHobbyUnpackingTiger
       =Tag
        s3
        i0
         =GUID:6839941761839372929
         =Value:1137003889713374791

A leading "=" marks a key, with or without a value. A bare "s<n>" is the
length of the list that follows, and "i<n>" opens one of its entries.

These files belong to a mod, not to the game. Every mod carries its own
Settings folder and the game merges them, which is how the French translation
mod ships nothing but a Translations.setting. So adding an item means writing
inside your own .mod, and the installation is never touched.

Merging is done on the text rather than by rebuilding the file from a parsed
model. A mod's Items.setting is written by the game and may hold fields this
add-on has never heard of; re-serialising it would quietly drop them. Adding
an entry therefore changes exactly two things: the count line, and the block
inserted after it.
"""

import os
import re

INDENT = " "

_LIST_LENGTH = re.compile(r"^(\s*)s(\d+)\s*$")
_ENTRY = re.compile(r"^(\s*)i(\d+)\s*$")


def line_ending(text):
    """Match whatever the file already uses. The game writes CRLF."""
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    return "\r\n"


def read(path):
    # newline="" keeps CRLF as it is on disk. Without it Python translates
    # line endings on the way in, and comparing what is there against what is
    # about to be written never matches.
    try:
        with open(path, "r", encoding="utf-8", errors="replace",
                  newline="") as handle:
            return handle.read()
    except OSError:
        return ""


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def header(name):
    return "#Setting." + name


def block(depth, *lines):
    """Indent a run of lines to the given depth."""
    return [(INDENT * depth) + line for line in lines]


def entry_lines(depth, index, fields):
    """One i<n> entry and its key/value pairs.

    fields is a list of (key, value) where a value of None opens a nested
    block whose own lines are supplied already indented.
    """
    out = [(INDENT * depth) + "i" + str(index)]
    for key, value in fields:
        if isinstance(value, list):
            out.append((INDENT * (depth + 1)) + "=" + key)
            out.extend(value)
        elif value is None:
            out.append((INDENT * (depth + 1)) + "=" + key)
        else:
            out.append((INDENT * (depth + 1)) + "=" + key + ":" + str(value))
    return out


def linked_list(depth, pairs):
    """The GUID/Value shape the game uses for every cross reference."""
    out = [(INDENT * depth) + "s" + str(len(pairs))]
    for index, (guid, value) in enumerate(pairs):
        out.append((INDENT * depth) + "i" + str(index))
        out.append((INDENT * (depth + 1)) + "=GUID:" + str(guid))
        out.append((INDENT * (depth + 1)) + "=Value:" + str(value))
    return out


# --------------------------------------------------------------------------


def find_list(lines, key):
    """Locate the "=<key>" block and its "s<n>" line.

    Returns (key_index, count_index, count, indent) or None.
    """
    wanted = "=" + key
    for index, line in enumerate(lines):
        if line.strip() != wanted:
            continue
        for offset in range(index + 1, min(index + 4, len(lines))):
            match = _LIST_LENGTH.match(lines[offset])
            if match:
                return index, offset, int(match.group(2)), match.group(1)
        return index, None, 0, INDENT * 2
    return None


def used_indices(lines, start, indent):
    """Every i<n> at the list's own depth, from start to the end of it."""
    found = set()
    for line in lines[start:]:
        match = _ENTRY.match(line)
        if match and match.group(1) == indent:
            found.add(int(match.group(2)))
            continue
        # A line indented less than the list means the list is over.
        stripped = line.strip()
        if stripped and not line.startswith(indent):
            break
    return found


def contains_value(lines, key, value):
    """True when "=<key>:<value>" is already somewhere in the file."""
    wanted = "={0}:{1}".format(key, value)
    return any(line.strip() == wanted for line in lines)


def entry_span(lines, list_key, unique_key, unique_value):
    """Locate the entry that holds "=<unique_key>:<unique_value>".

    Returns (start, end, index, depth), where start and end bound the whole
    i<n> block including its own line. None when there is no such entry.
    """
    found = find_list(lines, list_key)
    if found is None:
        return None
    key_index, _count_index, _count, indent = found
    depth = len(indent) // len(INDENT) if INDENT else 2
    wanted = "={0}:{1}".format(unique_key, unique_value)

    spans = []
    start = None
    index = 0
    for position in range(key_index + 1, len(lines) + 1):
        line = lines[position] if position < len(lines) else ""
        match = _ENTRY.match(line) if position < len(lines) else None
        at_depth = match is not None and match.group(1) == indent
        stripped = line.strip()
        # A non-empty line shallower than the list means the list has ended.
        ended = (
            position >= len(lines)
            or (stripped and not line.startswith(indent) and not at_depth)
        )
        if at_depth or ended:
            if start is not None:
                spans.append((start, position, index))
            if ended:
                break
            start = position
            index = int(match.group(2))

    for start, end, index in spans:
        if any(line.strip() == wanted for line in lines[start:end]):
            return start, end, index, depth
    return None


def replace_entry(text, list_key, unique_key, unique_value, fields):
    """Rewrite one entry in place, keeping its index and the list length.

    Returns the new text, or None when the entry is not there. Used so that
    regenerating an item repairs an entry an earlier version wrote badly,
    rather than leaving it and reporting success.
    """
    ending = line_ending(text)
    lines = text.replace("\r\n", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()

    span = entry_span(lines, list_key, unique_key, unique_value)
    if span is None:
        return None

    start, end, index, depth = span
    lines[start:end] = entry_lines(depth, index, fields)
    return ending.join(lines) + ending


def append_entry(text, list_key, fields, setting_name):
    """Add one entry to a list, creating the whole file when it is missing.

    Returns the new text, or None when nothing needed doing.
    """
    ending = line_ending(text)
    if not text.strip():
        lines = [header(setting_name), INDENT + "=" + list_key,
                 (INDENT * 2) + "s1"]
        lines.extend(entry_lines(2, 0, fields))
        return ending.join(lines) + ending

    lines = text.replace("\r\n", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()

    found = find_list(lines, list_key)
    if found is None:
        # The file exists but holds a different section. Append the list.
        lines.append(INDENT + "=" + list_key)
        lines.append((INDENT * 2) + "s1")
        lines.extend(entry_lines(2, 0, fields))
        return ending.join(lines) + ending

    key_index, count_index, count, indent = found
    depth = len(indent) // len(INDENT) if INDENT else 2
    taken = used_indices(lines, key_index + 1, indent)
    index = (max(taken) + 1) if taken else 0

    new_lines = entry_lines(depth, index, fields)
    if count_index is None:
        lines[key_index + 1:key_index + 1] = [indent + "s1"] + new_lines
    else:
        lines[count_index] = indent + "s" + str(len(taken) + 1)
        lines[count_index + 1:count_index + 1] = new_lines

    return ending.join(lines) + ending
