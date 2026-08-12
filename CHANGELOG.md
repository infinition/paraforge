# Changelog

All notable changes to ParaForge. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/) while it is below 1.0, meaning the
minor number moves on every behaviour change.

Every entry below was driven by something measured in the game's own data
rather than assumed. Paralives is in early access, so the game build a finding
was measured on is recorded with it.

## [0.16.0]

### Fixed

- **The item still rendered white, and the game said why.** The log carried,
  once per item:

  ```
  Material builder got given parameters that don't match any shaders -
  ShaderType:Simple ZoneDefinition:OneZoneNew LightingMethod:Lit
  ```

  The surface declared `DefaultSwatchGroup:0` and `DefaultSwatch:0`, which
  announces a swatch, so the game asked for a colour zone the plain shader
  cannot draw. Only 21 of the 75 shipped surfaces with a normal map declare
  them, and the minimal form, `WallStoneRubble`, is four fields: GUID,
  DisplayName, Texture, NormalAndAmbientOcclusionMap. The surface is now kept
  to that, plus smoothness and occlusion strength, which 13 and 12 of them
  carry.

### Changed

- The preview reads each map back through the colour space its source carried
  rather than assuming sRGB. The pipeline works in raw bytes, so an albedo
  tagged Non-Color shown as sRGB comes out pale and washed, which reads as the
  texture having been applied wrongly.

## [0.15.0]

### Fixed

- **The preview became its own source.** It replaces the materials, so
  everything that read them afterwards read the preview instead: the plan went
  from "rebuilt from Image_2, Image_1" to "copied PapanierDetail", and a later
  export would have copied an already converted texture. The plan that produced
  the preview is now held for as long as it is on.
- **The preview showed a gloss the game cannot produce.** It used the
  Smoothness map as a per pixel roughness, while the game keeps one value per
  surface and has no slot for the map at all. On a mostly white map that made
  the object a mirror of the viewport's own lighting, which is where the
  scattered white patches came from. It now uses the single value the surface
  will carry, read back from the written file.

## [0.14.0]

### Added

- **Preview as in game.** The viewport shows the material the file arrived
  with, and the game shows something else, because the channels are rebuilt on
  the way out and the game has no slot for some of them. The preview writes the
  textures exactly as the export would, reads them back, and shows the object
  through them, with smoothness turned back into roughness the way the shader
  does it. Press again to get your own materials back.
- **Bake the look back after decimating.** Collapsing edges throws the UVs out
  of shape, which is why the texture seemed to disappear. The reduced mesh is
  now unwrapped and the original's colour, relief and roughness are baked onto
  it, from a copy kept aside for the purpose.

## [0.13.0]

### Fixed

- **A new item replaced the one already in the catalogue.** The GUID of a list
  element is its identity, and the item's `Tag` entry derived its own from the
  mod and the catalogue tag alone. Every item in a mod filed under the same tag
  therefore shared one element, and the game folded them together: adding a
  vase turned the chair already in the catalogue into a vase. Found by reading
  seven real items whose `Tag` blocks all carried
  `GUID:8509043764253587081`. The element is now derived from the item as well.

  Items written by an earlier version keep the shared GUID until they are
  generated again.

## [0.12.0]

### Added

- **A guard on the asset name**, which is the identity of the item. Every file
  written into the mod and every GUID derived for it comes from that name, so
  two imports both answering to `Mesh_0` write the same files and the second
  silently replaces the first: the chair already in the catalogue starts
  showing the vase. An unnamed item on a generic object now blocks the export,
  a name an importer chose warns, and a name already present in the mod says so
  before it replaces anything.

### Fixed

- **The item rendered white.** 0.11.0 put the item's colour in the surface's
  `Texture` field and dropped the `DetailMap`. That field is the base the
  shader tints, not the colour: across the game's 925 references it is a
  GrayMask 634 times, a Master 100 times, and a Detail 133 times, the last
  almost always under a vegetation or special shader. The colour of an ordinary
  item arrives through `DetailMap` on the prefab. An item with no GrayMask of
  its own now sits on the game's neutral base and keeps its colour in
  `DetailMap`, which is the path that rendered correctly in 0.10.0, with the
  surface added on top to carry the relief.

## [0.11.0]

### Added

- **The item gets a surface of its own**, which is the only place a normal map
  and a smoothness value can live. No prefab field anywhere mentions
  smoothness, metallic or occlusion, checked across 300 prefabs, so an item
  borrowing the shared surface has no relief at all. The entry is modelled on
  `TextileQuiltedSquares`, one of the 75 shipped surfaces with a real normal
  map, and written with the `@<GUID>` marker so it extends the game's list
  rather than replacing it. This is what 0.6.0 got wrong: it was not that a mod
  may not define a surface, it was the positional marker.
- A `Smoothness` map is averaged into `SmoothnessValue` on export. The game has
  no slot for a smoothness texture, only one value per surface.
- Toggle and smoothness slider in the export options, so a mod can fall back to
  the shared surface without a new release.

### Fixed

- The cleanup of a `Surfaces.setting` left by 0.6.0 now only removes one
  written in the old positional form, instead of removing any at all.

## [0.10.0]

### Fixed

- **The mesh arrived lying on its back.** The game reads raw vertex data and
  ignores the node, and Blender writes its axis conversion as a rotation on the
  node. The `Z Forward, Y Up` export setting is therefore not enough on its
  own. The rotation is now baked into the geometry on the throwaway copy, and
  the exporter is told to convert nothing. Measured by importing the game's own
  files with conversion switched off: their base sits on Y=0, ours sat on Z=0.
- A byte order mark in `blender_manifest.toml` stopped Blender from parsing it.

## [0.9.0]

### Fixed

- **The item was invisible, at one hundredth of its size.** The game multiplies
  raw FBX coordinates by 0.01 and ignores both the file's unit declaration and
  the node's scale, so a mesh authored in metres arrives a hundred times too
  small: present, correctly placed, with the right footprint, too small to see.
  Read out of the `.import` files the game itself produced. The geometry is now
  scaled on a throwaway copy, since no Blender export option does it.
- Exported meshes are named after the item rather than after whatever was left
  in the outliner, matching the game's own files.

### Added

- `FBX units per metre` in the Calibration panel.

## [0.8.0]

### Fixed

- **A one entry `Translations.setting` wiped the game's entire translation
  table**, turning every menu label into a raw key such as
  `UIBuildModeCatalog_XCancel`. Writing `s1` then `i0` tells the game the
  collection has one member, and it drops its own. Entries are now added with
  `@<GUID>` markers and no size line, which is how the game's own `French.mod`
  extends a collection.

### Added

- Merge style selector in the export options, covering `@<GUID>`, `g<GUID>` and
  the positional form, because the format is not documented anywhere official.

## [0.7.0]

### Fixed

- **The item sat in the catalogue with the right footprint and drew nothing.**
  Two causes, both measured. A `Surfaces.setting` written by a mod crashes the
  game during startup in `SurfaceThumbnailManager.Start()`, and any colour
  attribute at all makes the mesh `ZoneDefinition:VertexZones`, which demands a
  recolourable shader a plain surface cannot provide. The item now points at
  the game's shared `GenericGrayMask` and lays its own texture over it through
  `DetailMap`, copying `CityGravelPile.prefab`. Colour zones are kept out of
  the FBX unless the item really is recolourable.
- A non recolourable item now writes `HasSwatches:False` and no swatch fields,
  as the game's own entries do.
- Merging repairs an entry an earlier version wrote badly instead of skipping
  it and reporting success.
- A `Surfaces.setting` left by 0.6.0 is removed, with a backup, and prefabs
  that referenced it are repointed.

## [0.6.0]

### Added

- Writes a surface per item. This turned out to be wrong and was reverted in
  0.7.0, and the crash it caused is explained by the collection wipe fixed in
  0.8.0.

## [0.5.0]

### Added

- **Create the item in the catalogue.** ParaForge writes the prefab, the
  catalogue entry and the translation itself, so the Control Panel pass
  disappears. Everything it writes is journalled and reversible in one click.
- Create a mod from Blender, and refuse to write into the game installation.

### Changed

- Actions moved above the checklist, which had pushed them off screen.

## [0.4.0]

### Changed

- The specification is calibrated against the game's own data rather than
  assumptions: triangle budget from 159 shipped meshes, texture resolutions
  from 1 446 textures, map usage, and the `.meta` flag mapping from 800
  textures.

### Added

- `tools/extract_catalog.py`, which regenerates the 298 Build Mode tags with
  their GUID and hierarchy from an installed game.

## [0.2.0]

### Added

- French and English interface, switchable from the panel header.
- glTF and ORM texture conversion, identifying images from the shader graph
  first, then the file name, then the pixels.
- Merge several materials into a single surface by baking to an atlas.

## [0.1.0]

### Added

- First working version: the checklist, the fixes, the viewport guides, colour
  zone authoring including the texture picker with tolerance, texture role
  detection and naming, FBX and PNG export into a `.mod` folder, and the mod
  folder snapshot and diff tool.
