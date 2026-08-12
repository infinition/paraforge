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

# That setting is not enough on its own. Blender expresses the conversion as a
# rotation on the exported node rather than in the vertex data, and the game
# ignores what the node says exactly as it ignores the node's scale. The mesh
# then arrives Z-up in a Y-up world, lying on its back.
#
# Measured by importing with the conversion switched off, so the coordinates
# are the file's own:
#
#   CityGravelPile.fbx   base sits on Y=0    node rotation 180 deg about Z
#   Barbecue.fbx         base sits on Y=0    node rotation 180 deg about Z
#   our export           base sits on Z=0    node rotation  90 deg about X
#
# So the rotation is baked into the geometry too, and the exporter is then
# told to convert nothing.
FBX_IDENTITY_FORWARD = "-Y"
FBX_IDENTITY_UP = "Z"

# The game multiplies the raw vertex coordinates of an FBX by 0.01. It ignores
# both the file's unit declaration and any scaling on the node, so a mesh
# authored in metres arrives a hundred times too small: present, correctly
# placed, with the right footprint, and far too small to see.
#
# Measured in the game's own processed assets rather than guessed. A .import
# file is what the game made of an FBX, and its coordinates read:
#
#   CityGravelPile   prefab Size 4.4642 m    coordinates around 2.24
#   Cereal box       roughly 0.3 m           coordinates around 0.15
#   our first rock   prefab Size 1.9086 m    coordinates around 0.0088
#
# The shipped meshes agree with their prefabs; ours was out by a factor of a
# hundred. Re-importing the game's FBX files into Blender says the same thing
# from the other side: they carry a 0.01 node scale over centimetre sized
# vertices, so 446 raw units is the 4.4642 m the prefab declares.
#
# So the mesh has to leave Blender in centimetres. No FBX export option does
# it (Blender puts the factor on the node, which the game ignores), and the
# geometry is scaled on a throwaway copy instead.
FBX_UNITS_PER_METRE = 100.0

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

# Names an object arrives with rather than names anybody chose. Every file in
# the mod, and every GUID in it, is derived from the asset name, so two
# imports that both answer to Mesh_0 write the same files and the second
# quietly becomes the first: the chair in the catalogue turns into a vase.
GENERIC_NAMES = (
    "mesh", "object", "cube", "plane", "sphere", "icosphere", "circle",
    "cylinder", "cone", "torus", "grid", "suzanne", "model", "untitled",
    "default", "empty", "scene", "node", "group", "geometry", "mesh0",
    "defaultmaterial", "asset",
)


def looks_generic(name):
    """True when a name is what an importer produced, not what a human chose."""
    stem = "".join(c for c in (name or "").lower() if c.isalpha())
    return stem in GENERIC_NAMES


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

#: The two ways to carry colour. Every Build Mode item has one of them.
ALBEDO_SUFFIXES = ("Detail", "GrayMask")

#: An item is only really missing something if it has no colour at all.
#: Counted across the 1446 textures the game ships under Environments/Items:
#: Detail 524, GrayMask 474, ColorZone 52, NormalOcclusion 41, Smoothness 22,
#: Master 8. A normal map is on roughly one item in twenty, so warning about a
#: missing one, as this add-on used to, was wrong.
RECOMMENDED_SUFFIXES = ALBEDO_SUFFIXES

#: Suffixes that must never appear more than once on a single item.
UNIQUE_SUFFIXES = ("Detail", "ColorZone", "Master")

#: Import flags the game writes into the .meta beside a texture, keyed by
#: suffix. Read back from 800+ shipped textures, where the mapping is exactly
#: consistent. Writing these ourselves makes the import deterministic instead
#: of depending on the game parsing our file name.
#:
#: IsPointFilter on ColorZone matters: a zone map must not be interpolated, or
#: the boundary between two zones blends into a colour that is not a zone.
TEXTURE_META_FLAGS = {
    "Detail": {},
    "GrayMask": {"IsLinear": "True"},
    "NormalOcclusion": {"IsLinear": "True"},
    "Smoothness": {"IsLinear": "True"},
    "ColorZone": {"IsPointFilter": "True"},
    "Master": {"IsLinear": "True", "HasVariantMap": "True",
               "HasHueshiftMap": "True"},
}

#: Written on every texture whatever its role.
TEXTURE_META_COMMON = {
    "GenerateMipMaps": "True",
    "GenerateTextureQualities": "YesWithObjectSettings",
}

# Why an item can sit in the catalogue, take its footprint, and still draw
# nothing. The game builds a material from a combination of parameters and
# says so when the combination has no shader:
#
#   Material builder got given parameters that don't match any shaders -
#   ShaderType:Simple ZoneDefinition:VertexZones ...
#
# ShaderType comes from the surface, ZoneDefinition from the mesh. A mesh that
# carries a vertex colour attribute is VertexZones whatever the attribute
# contains, so exporting one all-white zone is not neutral: it asks for a
# recolourable shader that the plain surface cannot provide, and the item goes
# invisible. Meshes are checked, not assumed. Importing the game's own
# CityGravelPile.fbx and ClutterKitchenIngredientCereal.fbx back into Blender:
# zero colour attributes on either.
#
# Defining a surface inside a mod is not the way round it. The game crashes
# during startup on a mod supplied surface:
#
#   NullReferenceException at SurfaceThumbnailManager.Start()
#
# Its own items do not do that either. Surfaces are a shared material library:
# 397 of the 2434 shipped prefabs point at GenericGrayMask, 370 of those add
# their own texture through DetailMap. CityGravelPile.prefab is the whole
# pattern, and it is exactly what ParaForge writes:
#
#   ItemMeshReference:
#    Surfaces:
#     Surface:
#      GUID:4303346223996877069        <- identity of this list entry
#      Value:6533686579680309849       <- GenericGrayMask
#    DetailMap:4868737352193020236     <- the item's own texture
#
# So: point at a surface the game already defines, put the asset's texture in
# DetailMap, and keep vertex colours out of the FBX unless the item really is
# recolourable. Nothing global is written, and nothing crashes.

#: GenericGrayMask, verified in Main.mod/Settings/Surfaces.setting, game build
#: 0.1.6b. Its own texture is Environments/Items/ItemsTileableTextures/
#: GenericGrayMask.png, a plain tileable gray the DetailMap covers.
DEFAULT_SURFACE_GUID = "6533686579680309849"
DEFAULT_SURFACE_NAME = "GenericGrayMask"

#: ShaderType is a number, not a name, and 1445 of the 1649 surface entries
#: leave it out entirely. The log prints the default as "Simple". Nothing here
#: needs to write it, the field is listed only so a reader stops looking.
SURFACE_SHADER_TYPE_IS_NUMERIC = True

# UNRESOLVED. A surface written by a mod still makes the game refuse to build
# a material, and the item draws white:
#
#   Material builder got given parameters that don't match any shaders -
#   ShaderType:Simple ZoneDefinition:OneZoneNew LightingMethod:Lit
#
# ZoneDefinition is chosen by GetColorZoneDefinition inside the game, and its
# members, read out of Paralives.dll, are None, OneZoneOld, OneZoneNew,
# ColorZoneMapOld and ColorZoneMapNew. Something in a mod supplied surface
# makes it answer OneZoneNew, which the plain shader has no variant for.
# Removing the swatch defaults did not change it, and GenericGrayMask declares
# them and works, so it is not those on their own.
#
# Until that is understood, an item borrows the game's own surface, which is
# proven to render, and does without the relief. The switch is still there for
# anyone who wants to carry the investigation further.
#
# A surface of one's own, for the relief and the material.
#
# Pointing at GenericGrayMask and putting the item's texture in DetailMap makes
# the item render, but the normal and the smoothness have nowhere to go: they
# are fields on the surface, not on the prefab. Checked across 300 prefabs, no
# prefab field mentions smoothness, metallic or occlusion at all.
#
# 0.6.0 wrote a surface and the game threw NullReferenceException in
# SurfaceThumbnailManager.Start() at every launch. That was not because a mod
# may not define a surface. It was the positional marker bug: the entry was
# written as "s1" then "i0", which told the game the surface collection had one
# member, and its own 950 went away. A thumbnail manager walking an empty
# surface library is exactly what would throw. With the @<GUID> marker the
# collection is extended rather than replaced.
#
# The shape below is TextileQuiltedSquares, one of the 75 shipped surfaces that
# carry a real normal map, with the fields no simple item needs removed:
#
#   =GUID:2837101404810957891
#   =DisplayName:TextileQuiltedSquares
#   =Texture:1228250718176622809
#   =NormalAndAmbientOcclusionMap:1794374427089866391
#   =AmbientOcclusionStrength:1
#
# BuildModeTags is deliberately absent. It is what puts a surface in the
# in-game picker, and a surface belonging to one item has no business there.

# What goes in a surface's Texture field is the base the shader tints, not the
# item's colour. Across the 925 shipped references it is a GrayMask 634 times,
# a Master 100 times, and a Detail 133 times, the last almost always alongside
# a vegetation or a special shader.
#
# The colour of an ordinary item arrives through DetailMap on the prefab, laid
# over that base. Putting the colour in Texture and dropping DetailMap renders
# the item white, which is exactly what 0.11.0 did.
#
# So an item with no GrayMask of its own borrows the game's neutral one and
# keeps its colour in DetailMap. That is the 0.10.0 path, which rendered
# correctly, plus a surface to carry the relief.

#: GenericGrayMask.png, the plain tileable gray GenericGrayMask itself uses.
DEFAULT_BASE_TEXTURE_GUID = "4272001606441780869"

#: Occlusion comes from the alpha of the NormalOcclusion map, at full strength.
SURFACE_AMBIENT_OCCLUSION_STRENGTH = 1

#: How far a placed item can be scaled by its yellow handle. The game's own
#: prefabs spread widely, and these are the two most common values across the
#: 1114 that are scalable: MinScale 0.5 on 47 of them, MaxScale 2 on 39.
MIN_SCALE = 0.5
MAX_SCALE = 2.0

#: There is no slot for a smoothness texture anywhere: the game stores a single
#: scalar per surface, SmoothnessValue, used by 329 of the shipped surfaces. A
#: smoothness map is therefore averaged down to one number.
DEFAULT_SMOOTHNESS = 0.5

#: Asset type codes used in a .meta file.
META_TYPE_MESH = 1
META_TYPE_TEXTURE = 2
META_TYPE_PREFAB = 201
META_TYPE_SETTING = 203
META_TYPE_MOD = 401

#: Resolutions the game actually ships, most common first: 512, 256, 1024,
#: then 2048 for a handful of large pieces. A 4K map off a download is four
#: times the largest thing in the game.
TYPICAL_TEXTURE_SIZES = (256, 512, 1024)
MAX_SENSIBLE_TEXTURE_SIZE = 2048

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

# The Item Tag decides where the item lands in Build Mode and sets its base
# price. The list is not published anywhere, so it is read straight out of the
# game: see catalog.py, regenerated by tools/extract_catalog.py.

#: Fallback used when no game install has been read yet.
CUSTOM_TAG = "CUSTOM"


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

# The team has never published a triangle budget, so it was measured instead:
# 159 meshes taken at random from Environments/Items and imported into
# Blender.
#
#   minimum         2
#   median        294
#   75th        624
#   90th       1 380
#   99th       3 980
#   maximum    4 060   (a Christmas tree)
#
# So the default ceiling is the 99th percentile of the game's own art. It is
# still only a warning, and still editable, but it is now a real number rather
# than a guess. A downloaded asset at half a million triangles is a hundred
# times the largest object Paralives ships.

DEFAULT_TRIANGLE_BUDGET = 4000

#: For reference in the interface.
MEASURED_TRIANGLES_MEDIAN = 294
MEASURED_TRIANGLES_MAX = 4060
MEASURED_SAMPLE = 159

#: Paralives places freely rather than on a grid, so this is only the spacing
#: of the reference grid drawn in the viewport. One metre reads well against
#: the game's own furniture, whose median footprint is 0.82 x 0.48 m.
DEFAULT_TILE_SIZE = 1.0

#: A door in the game is 2.112 m tall and a single leaf is 1.04 m wide.
#: Handy for eyeballing whether an imported asset is at the right scale.
REFERENCE_DOOR_HEIGHT = 2.112
REFERENCE_DOOR_WIDTH = 1.039
