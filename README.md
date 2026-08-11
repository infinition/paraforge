<p align="center">
  <img src="docs/paraforge.png" alt="ParaForge" width="200">
</p>

<h1 align="center">ParaForge</h1>

<p align="center">
  <strong>Take a 3D model from Blender to the Paralives Build Mode catalogue, in two clicks.</strong>
</p>

<p align="center">
  <a href="README.md">English</a> &nbsp;·&nbsp; <a href="README.fr.md">Français</a>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License GPL-3.0-or-later" src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue"></a>
  <img alt="Blender 4.2+" src="https://img.shields.io/badge/Blender-4.2%2B-orange">
  <a href="../../actions/workflows/ci.yml"><img alt="CI" src="../../actions/workflows/ci.yml/badge.svg"></a>
  <a href="../../releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/infinition/paraforge?display_name=tag"></a>
</p>

---

ParaForge is a Blender add-on for [Paralives](https://store.steampowered.com/app/1118520/Paralives/).
It checks a mesh against every rule the game imposes, fixes what can be fixed,
rebuilds the textures into the maps the game actually reads, writes the FBX and
its PNGs straight into a `.mod` folder, and then declares the item in the Build
Mode catalogue.

The game never has to be running, and no file inside the installation is ever
touched.

Interface in **French by default**, English on request, switchable from the
panel header.

Blender 4.2 or newer. Developed and tested against Blender 5.2 LTS.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Install](#install)
- [Use it](#use-it)
- [What the checklist verifies](#what-the-checklist-verifies)
- [Colour zones, three ways in](#colour-zones-three-ways-in)
- [Textures, and the naming that configures them](#textures-and-the-naming-that-configures-them)
- [A downloaded GLB, converted on its own](#a-downloaded-glb-converted-on-its-own)
- [Writing the item without the Control Panel](#writing-the-item-without-the-control-panel)
- [What the wiki does not say, and the game does](#what-the-wiki-does-not-say-and-the-game-does)
- [Undo, and safety](#undo-and-safety)
- [Calibration](#calibration)
- [Limits](#limits)
- [Build from source](#build-from-source)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Credits and licence](#credits-and-licence)

---

## Why this exists

Paralives ships a real modding toolkit inside the game, and it works. What it
does not do is stop you from getting the mesh wrong. The official path is:
export from Blender, drop the files in a mod folder, restart the game, open the
Control Panel, create an Item, create a Prefab, add an `ItemMeshReference`, pick
the mesh, fit the bounding box, assign a surface, tag it, pick a swatch group,
then find out whether the orientation, the scale, the origin and the texture
roles were right.

Every mistake costs a full game restart, because the game imports its assets at
launch and has no hot reload.

ParaForge moves the whole verification into Blender, where a mistake costs
nothing, and then writes the catalogue entry itself so the Control Panel pass
disappears.

## Install

Download `paraforge-x.y.z.zip` from the [Releases page](../../releases/latest),
then in Blender:

**Edit > Preferences > Get Extensions > Install from Disk**, and pick the zip.

The panel appears in the 3D viewport sidebar, tab **ParaForge**. Press `N` to
open the sidebar.

## Use it

0. **Pick the target mod**, or create one with the `+` next to the selector.
   Mods live in `%USERPROFILE%\AppData\LocalLow\Paralives\Paralives\`. Avoid
   `Local.mod`: it is the game's own scratch folder, fine for a quick try, but
   it cannot be published to the Workshop.
1. **Select the mesh.** The checklist appears in the panel and as an overlay in
   the viewport.
2. **Fix everything safe** sorts out unit scale, transforms, origin, the colour
   attribute and the texture roles.
3. **Check the orientation** against the green arrow, then confirm. This is the
   one thing no tool can work out for you.
4. **1. Export to Paralives** writes the mesh and the textures.
5. **2. Create the item in the catalogue** declares the item.

Both steps are needed. Without the second, the files sit in the mod and nothing
appears in Build Mode.

Then restart Paralives. There is no hot reload.

## What the checklist verifies

Each line is green, orange or red, with the reason, and a button that fixes it
where a fix exists.

| Check | What it means |
|---|---|
| Scene unit scale | Paralives works in metres at scale 1.0 |
| Transforms applied | Rotation and scale baked, or the item arrives wrong |
| Origin placement | Per item type, see below |
| Bounding size | Sanity check against the tile size |
| Faces Y+ | Manual, compared with the arrow drawn in the viewport |
| Colour zones | Legal zone colours only, four maximum |
| UV map | Present, and UV2 reported when it is there |
| Triangle count | Against your own budget, with a decimate button |
| N-gons | They triangulate on export and can shade badly |
| Texture naming | Every image classified into a role the game knows |
| Texture size | Nothing in the game is above 2K |
| Target mod folder | Exists, ends in `.mod`, and is not inside the game |

Origin rules, from the wiki:

| Item type | Rule |
|---|---|
| Floor item | Centred in X and Y, base at Z=0 |
| Wall item | Centred in X and Z, back at Y=0 |
| Window or door | Centred on all three axes |

## Colour zones, three ways in

Paralives reads up to four recolourable zones from vertex colours, plus yellow
for decals. Painting them by hand is slow, and an asset that arrives from a
marketplace or a generator has none at all.

1. **Select faces, click a zone.** The obvious one, with coloured buttons.
2. **One material per zone.** Most imported assets already split that way, so
   the slots map straight onto zones.
3. **Pick a colour off the model, then grow it by tolerance.** This is the one
   that rescues an asset whose only texture is a single bake. The picker
   samples the texture through a raycast rather than reading screen pixels, so
   viewport lighting never shifts the result, and the tolerance slider is live
   in the redo panel.

The legal colours are exact, and nothing else is read by the game:

| Zone | Colour |
|---|---|
| 0 | white `1, 1, 1` |
| 1 | red `1, 0, 0` |
| 2 | green `0, 1, 0` |
| 3 | blue `0, 0, 1` |
| Decal | yellow `1, 1, 0`, never recolourable |

## Textures, and the naming that configures them

The suffix on the file name is what makes the game assign the right import
settings. Getting it right removes a manual configuration pass per texture,
which is the single largest saving in the whole pipeline.

| Suffix | Content | Note |
|---|---|---|
| `GrayMask` | Recolourable base, 50 percent gray is the neutral tone | sRGB |
| `Detail` | Free colour, not recolourable | one per item |
| `NormalOcclusion` | Normal map in **RGB**, occlusion in the **alpha** | data |
| `Smoothness` | **White is glossy**, black is matte | data |
| `ColorZone` | Zone map, for meshes that cannot carry vertex colours | data |
| `Master` | Walls and floors: R GrayMask, G variant, B hue shift | sRGB |

ParaForge also writes the `.meta` sidecar next to each asset, carrying its GUID
and its import flags, which makes the import deterministic instead of depending
on the game parsing the file name.

## A downloaded GLB, converted on its own

A model taken off the web never arrives in the right shape. glTF gives you
*roughness* where the game wants *smoothness*, packs occlusion into the red
channel of an ORM texture, and gltfpack strips image names so Blender calls
them `Image_0`, `Image_1`, `Image_2`.

ParaForge identifies each image from three sources of evidence, most reliable
first:

1. **the shader graph**, meaning what the image is actually wired to. That is a
   fact rather than a guess, and it is the only clue left when the names are
   gone;
2. **the file name**: `_Diffuse`, `-ORM`, `_Normal`, `_BaseColor`;
3. **the pixels**: a normal map is recognisable, and a texture with no colour is
   never an albedo.

Then it rebuilds:

```
baseColor            -> Detail (exact copy) or GrayMask (desaturated, recentred on 50%)
normal + occlusion   -> NormalOcclusion (RGB + alpha)
roughness            -> Smoothness (1 - roughness)
metallic             -> no channel, folded into smoothness
emissive             -> no channel, folded back into the colour
```

Nothing is invented. An image that nothing identifies stays marked unknown and
is not written, rather than putting the wrong map into someone's mod.

### Assets with several materials

Paralives gives **one surface per mesh**. An asset split across five materials
therefore does not import as it is. **Merge into one surface** repacks the UVs
of the whole selection into an atlas, bakes every channel, and replaces the
materials with one. The look is preserved, the UVs are not.

## Writing the item without the Control Panel

A Paralives item is three pieces of plain text, all **inside your own mod**:

```
<Mod>/<Name>.prefab                 the object tree, its size, its mesh
<Mod>/Settings/Items.setting        the catalogue entry and its tag
<Mod>/Settings/Translations.setting the label the player reads
```

A mod carries only what it adds and the game merges everything: the game's own
French translation mod contains nothing but a `Translations.setting`. That is
why **no game file is ever modified**.

Merging is done on the text rather than by rebuilding the file from a parsed
model. An `Items.setting` written by the game may hold fields this add-on has
never heard of, and re-serialising it would drop them in silence.

## What the wiki does not say, and the game does

Paralives ships its own content as a mod: `Main.mod`, in the installation
folder, is an ordinary folder of FBX, PNG and text. Every number below was
measured there, not assumed. This section is the part of the project most
likely to be useful to other tools.

### The mesh has to be in centimetres

The game multiplies the raw vertex coordinates of an FBX by 0.01. It ignores
both the file's unit declaration and any scaling on the node, so a mesh
authored in metres arrives a hundred times too small: present, correctly
placed, with the right footprint, and far too small to see.

Read out of the `.import` files, which are what the game made of each FBX:

| Mesh | Size in its prefab | Coordinates in the import |
|---|---|---|
| `CityGravelPile` | 4.4642 m | around 2.24 |
| Cereal box | around 0.3 m | around 0.15 |
| An early ParaForge export | 1.9086 m | around 0.0088 |

No Blender export option produces this, because Blender puts the factor on the
node. ParaForge scales the geometry on a throwaway copy instead.

### And it has to be Y up, in the geometry

Same cause. Blender writes its axis conversion as a rotation on the node, and
the game ignores the node, so the mesh arrives Z up in a Y up world, lying on
its back. Importing with the conversion switched off shows the files as they
are:

```
CityGravelPile.fbx   base sits on Y=0    node rotation 180 deg about Z
Barbecue.fbx         base sits on Y=0    node rotation 180 deg about Z
an early export      base sits on Z=0    node rotation  90 deg about X
```

ParaForge bakes the rotation into the geometry too, and then tells the exporter
to convert nothing.

### Adding to a list, without wiping it

This one is worth knowing for anyone writing `.setting` files by hand.

A collection can be written three ways, and the marker decides what the game
does with the base game's own entries:

| Marker | Meaning |
|---|---|
| `i<index>` | Positional. Authoring a collection from scratch. Used by a mod on a list the base game also fills, **it drops the base collection and keeps only what the mod wrote** |
| `@<GUID>` | Add a new member to a list the base game already fills. What a content mod wants |
| `g<GUID>` | Merge fields onto a member that already exists |

The symptom of getting this wrong is spectacular and misleading: a
`Translations.setting` with one entry wipes the entire translation table, and
every menu label in the game turns into a raw key such as
`UIBuildModeCatalog_XCancel`.

Verified in the game's own data: `French.mod` extends `Translations.Items`
using `g<GUID>` markers with **no `s<N>` size line**, and never uses
`i<index>`. Credit to [paralives-modgen](https://github.com/LoryGlory/paralives-modgen)
for documenting the `@<GUID>` form first.

### Surfaces are shared, and the item's texture goes in DetailMap

The game does not give each item its own surface. Surfaces are a shared
material library: 397 of the 2434 shipped prefabs point at `GenericGrayMask`,
and 370 of those lay their own texture over it through `DetailMap`. Of the 486
DetailMap textures, 344 are used by exactly one prefab and live next to their
mesh, so it really is the per item slot.

That is one of the two shapes ParaForge writes, copied from
`CityGravelPile.prefab`:

```
ItemMeshReference:
 Surfaces:
  Surface:
   GUID:4303346223996877069        identity of this list entry
   Value:6533686579680309849       GenericGrayMask
 DetailMap:4868737352193020236     the item's own texture
```

The other shape gives the item a surface of its own, which is the only place a
normal map and a smoothness value can live. No prefab field anywhere mentions
smoothness, metallic or occlusion, checked across 300 prefabs, so an item
borrowing a shared surface has no relief at all. The entry is modelled on
`TextileQuiltedSquares`, one of the 75 shipped surfaces carrying a real normal
map:

```
#Setting.Surfaces
 =AllSurfaces
  @2693213273477870343
   =DisplayName:Stool
   =Texture:4272001606441780869          the game's neutral gray base
   =NormalAndAmbientOcclusionMap:...     the item's relief
   =AmbientOcclusionStrength:1
   =SmoothnessValue:0.42
   =DefaultSwatchGroup:0
   =DefaultSwatch:0
```

Note that the item's colour is **not** in there. A surface's `Texture` is the
base the shader tints, and across the game's 925 references it is a GrayMask
634 times, a Master 100 times, and a Detail 133 times, the last almost always
under a vegetation or special shader. The colour of an ordinary item arrives
through `DetailMap` on the prefab, over that base. Putting the colour in
`Texture` and dropping `DetailMap` renders the item white.

Note the `@` marker and the absent size line. Writing this positionally is what
made the game throw `NullReferenceException` in `SurfaceThumbnailManager.Start()`
at every launch: the mod was not adding a surface, it was replacing all 950 of
them with one.

There is **no slot for a smoothness texture** anywhere, only a single
`SmoothnessValue` per surface, used by 329 of the shipped ones. A Smoothness map
is therefore averaged into that number on export.

### Vertex colours are not free

The game reads the **presence** of a colour attribute, not its contents. Any
attribute at all makes the mesh `ZoneDefinition:VertexZones` and demands a
recolourable shader that a plain surface cannot provide:

```
Material builder got given parameters that don't match any shaders -
ShaderType:Simple ZoneDefinition:VertexZones ...
```

The item then loads, takes its footprint, and draws nothing. Exporting a single
white zone is therefore not neutral, it is what makes the item invisible. The
game's own meshes confirm it: `CityGravelPile.fbx` and
`ClutterKitchenIngredientCereal.fbx` carry no colour attribute at all.
ParaForge only exports them when the item really is recolourable.

### Measured numbers

**Triangle budget.** 159 meshes taken at random from `Environments/Items` and
imported into Blender: median **294** triangles, 90th percentile 1 380, maximum
**4 060**. That maximum is ParaForge's default budget. A downloaded asset at
560 000 triangles is a hundred times the largest object in the game.

**Texture resolution.** Across 1 446 item textures: 512 px leads, then 256, then
1 024. Nothing above 2 048. A 4K map is four times the largest in the game.

**Map usage.** Detail 524, GrayMask 474, ColorZone 52, NormalOcclusion 41,
Smoothness 22, Master 8. A normal map appears on one item in twenty.

**Catalogue tags.** The 298 Build Mode tags are extracted from the game by
`tools/extract_catalog.py` into `paraforge/catalog.py`, with their GUID and
their hierarchy. Run it again after a game update.

**A door** is 2.112 m tall, a single leaf 1.04 m wide. Useful for judging the
scale of an imported model by eye.

Everything the game imposes is gathered in
[`paraforge/spec.py`](paraforge/spec.py), so a game update should never require
touching another file.

## Undo, and safety

Every generation is journalled in `_paraforge/journal.json` inside the mod,
with a copy of any file it changed. **Undo the last write** removes what was
created, restores what was changed, and cleans up folders left empty. Pressing
it twice walks back two generations. Regenerating an unchanged item does
nothing and does not add a step.

Export refuses any folder inside the Paralives installation. Assets belong in a
`.mod` under `AppData\LocalLow`, or a game update wipes them and they cannot be
shared.

## Calibration

Three values the developers have never published live in the **Calibration**
panel, so a game update can be absorbed without a new release:

- **Tile size**, the size of one Build Mode grid tile in metres
- **Triangle budget**, your own ceiling, used for a warning only
- **FBX units per metre**, measured at 100

## Limits

- **Script mods are out of scope.** The developers provide no tools for them
  and they are not allowed on the Steam Workshop. ParaForge only ever produces
  mods that can be uploaded.
- **A smoothness map becomes one number.** The game has no slot for a
  smoothness texture, only a value per surface.
- **Recolourable items are only partly tested.** The GrayMask base and the
  colour zones are written, but swatch groups have had far less use than the
  plain path.
- **The format is not a published contract.** Paralives is in early access.
  Every finding above is recorded with the game build it was measured on.

## Build from source

```bash
python build.py
```

Or let Blender validate the manifest while it packages:

```bash
python build.py --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

The zip lands in `dist/`. Releases are built the same way by
[the release workflow](.github/workflows/release.yml).

## Tests

```bash
python tests/test_i18n.py
```

```bash
blender --background --factory-startup --python tests/test_headless.py
```

```bash
blender --background --factory-startup --python tests/test_ui_contract.py
```

The first checks that no string was left out of the French catalogue. The
second covers geometry, zones, texture detection, baking, units, axes, the
`.setting` merge and the export. The third draws every panel and validates every
icon, property and operator against the live API, which catches the errors that
only show up on screen.

All three run on every push, against Blender 4.2 and 5.2, in
[the CI workflow](.github/workflows/ci.yml).

## Project layout

```
paraforge/
  spec.py        everything Paralives imposes, in one place
  validate.py    the checklist
  fixes.py       one button per failed check
  geo.py         measurements shared by the validator, overlay and fixers
  zones.py       colour zone authoring, including the texture picker
  textures.py    role detection, naming, export
  imaging.py     channel rebuilding for glTF and ORM sources
  bake.py        merging several materials into one surface
  exporter.py    FBX and texture export into a .mod
  item.py        the prefab and the catalogue entry
  setting.py     reading and extending a .setting file
  sidecar.py     .meta files and GUID derivation
  journal.py     undo history for everything written into a mod
  catalog.py     Build Mode tags, generated from the game
  overlay.py     viewport guides and heads up checklist
  ui.py          the sidebar panel
  i18n.py        French and English strings
tools/
  extract_catalog.py   regenerate catalog.py from an installed game
  mod_diff.py          snapshot and diff a mod folder, without Blender
tests/
```

## Credits and licence

Created by **infinition**.

Thanks to the Paralives team for shipping a moddable game with a transparent,
plain text data format, and to [paralives-modgen](https://github.com/LoryGlory/paralives-modgen)
for documenting the collection merge syntax.

Licensed under the **GNU General Public License v3.0 or later**. See
[LICENSE](LICENSE) for the full text. Blender add-ons link against `bpy` and are
distributed under the GPL for that reason.
