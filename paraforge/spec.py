# SPDX-License-Identifier: GPL-3.0-or-later
"""Paralives asset specification.

Every rule the game imposes on a Build Mode asset lives here, in one place, so
that a game update only ever requires editing this file.

Sources (Paralives Wiki, checked against game build 0.1.6b, July 2026):
  Adding_a_Mesh_for_the_Build_Mode
  Adding_Texture_Assets_to_Create_Surfaces
  Creating_an_Item_with_Multiple_Colors_and_Materials
  Creating_a_Mod_and_Uploading_to_the_Steam_Workshop
"""

# --------------------------------------------------------------------------
# FBX export
# --------------------------------------------------------------------------

#: The wiki states: "make sure the FBX export settings have Z Forward and Y Up".
FBX_AXIS_FORWARD = "Z"
FBX_AXIS_UP = "Y"

#: Items must face Y+ before export.
FACING_AXIS = "Y+"

#: Accepted asset extensions when dropping files into a .mod folder.
MESH_EXTENSIONS = (".fbx", ".obj")
TEXTURE_EXTENSIONS = (".png", ".jpg", ".jpeg")
AUDIO_EXTENSIONS = (".ogg", ".mp3", ".wav")
FONT_EXTENSIONS = (".ttf",)


# --------------------------------------------------------------------------
# Origin / bounding rules per item type
# --------------------------------------------------------------------------

# Anchor codes:
#   "center" -> the bounding box is centred on 0 for that axis
#   "min"    -> the lowest bounding box coordinate sits at 0
#   "max"    -> the highest bounding box coordinate sits at 0
#   None     -> no documented rule

ITEM_TYPES = {
    "FLOOR": {
        "label": "Floor item",
        "description": "Stands on the ground. Centred in X and Y, base at Z=0",
        "anchors": {"x": "center", "y": "center", "z": "min"},
    },
    "WALL": {
        "label": "Wall item",
        "description": "Hangs on a wall. Centred in X and Z, back at Y=0",
        "anchors": {"x": "center", "y": "min", "z": "center"},
    },
    "WINDOW": {
        "label": "Window / door",
        "description": "Cut into a wall. Centred on all three axes",
        "anchors": {"x": "center", "y": "center", "z": "center"},
    },
    "GENERIC": {
        "label": "Other / undocumented",
        "description": "No origin rule enforced, geometry checks still run",
        "anchors": {"x": None, "y": None, "z": None},
    },
}

DEFAULT_ITEM_TYPE = "FLOOR"

#: Distance below which two coordinates are considered equal, in metres.
POSITION_TOLERANCE = 1e-4


# --------------------------------------------------------------------------
# Colour zones (vertex colours)
# --------------------------------------------------------------------------

#: Build Mode items support at most four recolourable zones.
MAX_COLOR_ZONES = 4

#: Exact vertex colours the game reads, keyed by zone index.
ZONE_COLORS = {
    0: ((1.0, 1.0, 1.0), "Zone 0 (white), usually the Detail map"),
    1: ((1.0, 0.0, 0.0), "Zone 1 (red)"),
    2: ((0.0, 1.0, 0.0), "Zone 2 (green)"),
    3: ((0.0, 0.0, 1.0), "Zone 3 (blue)"),
}

#: Yellow marks a decal zone. It is never recolourable and does not count
#: against MAX_COLOR_ZONES.
DECAL_COLOR = (1.0, 1.0, 0.0)

#: Channel values are only ever 0.0 or 1.0, so sRGB and linear agree exactly
#: and no colour space conversion is needed when comparing.
COLOR_TOLERANCE = 0.02


def classify_color(rgb):
    """Return a zone index, "decal", or None when the colour is not legal."""
    for index, (reference, _label) in ZONE_COLORS.items():
        if _close(rgb, reference):
            return index
    if _close(rgb, DECAL_COLOR):
        return "decal"
    return None


def _close(a, b):
    return all(abs(a[i] - b[i]) <= COLOR_TOLERANCE for i in range(3))


def zone_label(zone):
    if zone == "decal":
        return "Decal (yellow)"
    entry = ZONE_COLORS.get(zone)
    return entry[1] if entry else "Unknown"


# --------------------------------------------------------------------------
# Texture suffixes
# --------------------------------------------------------------------------

# The suffix on the file name is what makes the game assign the correct import
# settings automatically. Getting this right removes a manual configuration
# pass per texture, which is the single largest saving in the whole pipeline.
#
# Wiki, Adding_Texture_Assets_to_Create_Surfaces:
#   "The texture name should be in camel case, ending with the type of map it
#    is." and "The texture should be exported as a png. Other file types are
#    not supported."

TEXTURE_SUFFIXES = {
    "GrayMask": "Recolourable base. 50% gray is the neutral tone",
    "NormalOcclusion": "Normal map in RGB, ambient occlusion in the alpha",
    "Smoothness": "Reflectivity. White is reflective, black is matte",
    "Detail": "Free colour, not recolourable. One per item only",
    "ColorZone": "Zone map, for meshes that cannot carry vertex colours",
    "Master": "Walls and floors only. Two gray variations plus a hue shift",
}

#: Longest suffixes first so that matching is unambiguous.
SUFFIX_ORDER = sorted(TEXTURE_SUFFIXES, key=len, reverse=True)

#: Suffixes a regular Build Mode item is normally expected to ship.
RECOMMENDED_SUFFIXES = ("GrayMask", "NormalOcclusion")

#: Suffixes that must never appear more than once on a single item.
UNIQUE_SUFFIXES = ("Detail", "ColorZone", "Master")

#: Colour handling of each output. sRGB maps carry colour a human picked,
#: data maps carry numbers the shader reads and must never be gamma shifted.
SUFFIX_IS_DATA = {
    "GrayMask": False,
    "Detail": False,
    "Master": False,
    "NormalOcclusion": True,
    "Smoothness": True,
    "ColorZone": True,
}

# What Paralives actually shades with. There is no metallic map and no
# emission map anywhere in the documented set, so a downloaded PBR asset has
# to be folded down into these four channels:
#
#   albedo      GrayMask (recolourable) or Detail (fixed colour)
#   normal      NormalOcclusion, RGB
#   occlusion   NormalOcclusion, alpha
#   smoothness  Smoothness, and glTF stores the opposite (roughness)
#
#: Neutral value written into the alpha when an asset has a normal map but no
#: ambient occlusion map: fully lit.
DEFAULT_OCCLUSION = 1.0

#: Flat tangent space normal, the value a normal map has where the surface is
#: undisturbed. Written when an asset has occlusion but no normal map.
FLAT_NORMAL = (0.5, 0.5, 1.0)

#: A metal reads as a shiny surface rather than a diffuse one. Paralives has
#: no metallic channel, so metalness is folded into smoothness by this much.
METALLIC_SMOOTHNESS_BOOST = 0.35


def split_suffix(stem):
    """Split "SofaGrayMask" into ("Sofa", "GrayMask").

    Returns (stem, None) when no known suffix is present.
    """
    for suffix in SUFFIX_ORDER:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return stem[: -len(suffix)], suffix
    return stem, None


# --------------------------------------------------------------------------
# Source texture roles
# --------------------------------------------------------------------------

# What an incoming image *is*, before it is folded into a Paralives map. A
# glTF or GLB downloaded from the web arrives with these, and very often with
# no usable file name at all: gltfpack strips image names, so Blender ends up
# calling them Image_0, Image_1, Image_2. The node graph is then the only
# reliable evidence.

BASE_COLOR = "BASE_COLOR"
NORMAL = "NORMAL"
OCCLUSION = "OCCLUSION"
ROUGHNESS = "ROUGHNESS"
GLOSSINESS = "GLOSSINESS"
METALLIC = "METALLIC"
ORM = "ORM"
EMISSION = "EMISSION"
OPACITY = "OPACITY"
PARALIVES = "PARALIVES"
UNKNOWN = "UNKNOWN"

SOURCE_ROLES = (
    (BASE_COLOR, "Base colour", "Albedo, diffuse or a fully baked texture"),
    (NORMAL, "Normal map", "Tangent space normals"),
    (OCCLUSION, "Ambient occlusion", "Contact shadows, goes in the alpha"),
    (ROUGHNESS, "Roughness", "Inverted to become Smoothness"),
    (GLOSSINESS, "Glossiness", "Already the right way round for Smoothness"),
    (METALLIC, "Metallic", "No Paralives channel, folded into Smoothness"),
    (ORM, "Packed ORM", "R occlusion, G roughness, B metallic"),
    (EMISSION, "Emission", "No Paralives channel"),
    (OPACITY, "Opacity", "No Paralives channel"),
    (PARALIVES, "Already named for Paralives", "Copied through untouched"),
    (UNKNOWN, "Unknown", "Could not be identified"),
)

#: Channel of an ORM style packed map that holds each piece of information.
ORM_CHANNELS = {OCCLUSION: 0, ROUGHNESS: 1, METALLIC: 2}

#: Roles Paralives has no home for. They are reported, never written.
DROPPED_ROLES = (METALLIC, EMISSION, OPACITY)

#: File name fragments, checked lowercased with separators removed. Longest
#: first, because "roughness" contains "rough" and "ao" hides inside "shadow".
NAME_HINTS = (
    ("normalocclusion", PARALIVES),
    ("graymask", PARALIVES),
    ("greymask", PARALIVES),
    ("colorzone", PARALIVES),
    ("smoothness", PARALIVES),
    ("basecolor", BASE_COLOR),
    ("basecolour", BASE_COLOR),
    ("albedo", BASE_COLOR),
    ("diffuse", BASE_COLOR),
    ("difuse", BASE_COLOR),
    ("baked", BASE_COLOR),
    ("bake", BASE_COLOR),
    ("_col", BASE_COLOR),
    ("normalgl", NORMAL),
    ("normaldx", NORMAL),
    ("normalmap", NORMAL),
    ("normal", NORMAL),
    ("_nrm", NORMAL),
    ("_nor", NORMAL),
    ("occlusionroughnessmetallic", ORM),
    ("metallicroughness", ORM),
    ("roughnessmetallic", ORM),
    ("-orm", ORM),
    ("_orm", ORM),
    ("_arm", ORM),
    ("_rma", ORM),
    ("occlusion", OCCLUSION),
    ("ambientocc", OCCLUSION),
    ("_ao", OCCLUSION),
    ("roughness", ROUGHNESS),
    ("_rough", ROUGHNESS),
    ("_rgh", ROUGHNESS),
    ("glossiness", GLOSSINESS),
    ("_gloss", GLOSSINESS),
    ("specular", GLOSSINESS),
    ("metallic", METALLIC),
    ("metalness", METALLIC),
    ("_metal", METALLIC),
    ("emissive", EMISSION),
    ("emission", EMISSION),
    ("opacity", OPACITY),
    ("alphamask", OPACITY),
)

#: Principled BSDF inputs, and the role an image feeding them must have.
SOCKET_ROLES = {
    "Base Color": BASE_COLOR,
    "Roughness": ROUGHNESS,
    "Metallic": METALLIC,
    "Normal": NORMAL,
    "Emission Color": EMISSION,
    "Emission": EMISSION,
    "Alpha": OPACITY,
    "Specular IOR Level": GLOSSINESS,
}


def role_label(role):
    for key, label, _description in SOURCE_ROLES:
        if key == role:
            return label
    return role


# --------------------------------------------------------------------------
# Catalog placement
# --------------------------------------------------------------------------

# The Item Tag chosen in the Control Panel sets the base price and other
# backend properties. Paralives has never published the tag list, so this is a
# working set of Build Mode categories rather than a verified enumeration.
# Anything missing goes through CUSTOM. Correct this list once you have read
# the real tags in the game, it is the only place they appear.

CATALOG_TAGS = (
    ("SEATING", "Seating", "Chairs, sofas, stools, benches"),
    ("TABLES", "Tables", "Dining, coffee, side and desk tables"),
    ("BEDS", "Beds", "Beds and cribs"),
    ("STORAGE", "Storage", "Dressers, shelves, cabinets, wardrobes"),
    ("COUNTERS", "Counters and surfaces", "Counters, islands, worktops"),
    ("APPLIANCES", "Appliances", "Fridges, ovens, washers"),
    ("ELECTRONICS", "Electronics", "Screens, audio, computers"),
    ("LIGHTING", "Lighting", "Ceiling, wall, floor and table lights"),
    ("DECOR", "Decor", "Ornaments and small clutter"),
    ("WALL_DECOR", "Wall decor", "Paintings, mirrors, shelves on walls"),
    ("RUGS", "Rugs", "Floor coverings"),
    ("PLANTS", "Plants", "Indoor and outdoor greenery"),
    ("BATHROOM", "Bathroom", "Sinks, tubs, toilets, showers"),
    ("KITCHEN", "Kitchen", "Kitchen specific items"),
    ("OUTDOOR", "Outdoor", "Garden and patio items"),
    ("PLUMBING", "Plumbing", "Taps, sinks and related fittings"),
    ("STRUCTURAL", "Structural", "Doors, windows, stairs, fences, roofs"),
    ("CUSTOM", "Custom", "Type the tag by hand"),
)


# --------------------------------------------------------------------------
# Workshop
# --------------------------------------------------------------------------

#: Workshop thumbnails must be square and below this size.
THUMBNAIL_MAX_BYTES = 15 * 1024 * 1024

#: Mod folders are directories whose name ends with this suffix.
MOD_FOLDER_SUFFIX = ".mod"


# --------------------------------------------------------------------------
# Values that are NOT documented by the developers
# --------------------------------------------------------------------------

# These are exposed as add-on preferences rather than hard rules, because the
# Paralives team has never published them. Calibrate them once by importing an
# official game mesh into Blender and measuring it. See README.

DEFAULT_TRIANGLE_BUDGET = 15000
DEFAULT_TILE_SIZE = 1.0
