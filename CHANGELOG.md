# Changelog

All notable changes to ParaForge. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/) while it is below 1.0, meaning the
minor number moves on every behaviour change.

Every entry below was driven by something measured in the game's own data
rather than assumed. Paralives is in early access, so the game build a finding
was measured on is recorded with it.

## [0.19.0]

Read straight out of `Paralives_Data/Managed/Paralives.dll`, decompiled with
ILSpy. One missing line was causing both open bugs.

### Fixed

- **Every item a mod added collided with the others**, so a newly created
  item took over the ones already placed: two cacti became a flower, and the
  catalogue entry named Cactus2 became Fleufleur.

  A `@<GUID>` entry says where the new member goes. The game creates it with
  every field at its default, so its `GUID` field stays at zero unless the
  file writes it, and the game keys its lookups on that field:

  ```csharp
  _dictionary.Add(AllItems[i].GUID, AllItems[i]);        // Setting.Items
  _surfaceDictionary.Add(surface.GUID, surface);         // Setting.Surfaces
  ```

  Both skip a key they already hold. Left at zero, every entry collided on
  zero, one won, and the rest disappeared behind it. The game's own editor
  writes `AddArrayAtGUID` and then sets the field named by `[ClassGUID]` to
  the same value; ParaForge was stripping it, on the mistaken reading that
  `French.mod` omits it. `French.mod` uses `g<GUID>`, which merges onto a
  member that already has a GUID. `@<GUID>` creates one that does not.

- **The item rendered white with a surface of its own**, and this was the same
  missing line, not a rule against mod surfaces. `WithSurfaces` skips a
  surface `GetSurfaceByGUID` cannot find, leaving the builder on the
  `ShaderType.Simple` that `Init()` put there, while `ZoneDefinition` is
  `OneZoneNew` for any item with one surface:

  ```csharp
  if (item.ColorZoneMap != 0L)       zoneDefinition = ColorZoneMapNew;
  else if (item.Surfaces.Count == 1) zoneDefinition = OneZoneNew;
  ```

  So `ShaderType:Simple ZoneDefinition:OneZoneNew` never meant "a mod may not
  supply a surface". It meant the surface was not found. Nothing about the
  surface's contents was ever the problem, and the swatch defaults removed in
  0.16.0 were innocent.

### Changed

- **A surface of its own is back on by default**, which brings the relief
  back with it. No prefab field anywhere carries a normal map, so the surface
  is the only place it can live.

## [0.18.0]

### Fixed

- **The texture landed on the wrong part of the mesh**, showing the unwrapped
  islands through a smear of colour. The cause is not in the game and not in
  the textures: it is the coordinate transform the material puts in front of
  them.

  Measured on the cactus that showed the fault. Its UVs run `0 .. 0.0625` on U
  and `0.9375 .. 1` on V, one cell of a 16 by 16 grid, and every one of its
  four texture nodes is fed by a Mapping node at scale `15.98 x 16.00` with a
  `-15.002` offset on V. Run through it, those coordinates land on
  `0 .. 0.9986` by `0 .. 1`: the whole image. That is the shape an atlas cut
  arrives in, and `KHR_texture_transform` in a glTF arrives the same way.

  An FBX carries a mesh and its UV maps and nothing else. The Mapping node was
  dropped at the door and the game sampled a 256th of the texture, stretched
  over everything.

  The transform is affine, so it does not have to be baked into pixels.
  ParaForge now applies it to the coordinates themselves, on the export copy,
  which is exact and costs nothing in resolution. The scene keeps the UVs the
  artist gave it.

- **The in game preview showed the fault instead of warning about it.** It
  swaps the material while leaving the mesh alone, so its textures were
  sampled with the raw coordinates. It now rebuilds the same transform in
  front of them, and shows what the exported UVs will show. Side by side with
  the source material on the cactus, the two are indistinguishable.

### Added

- **A "Texture coordinates" line in the report**, which appears only when the
  material moves them. It names the transform being carried over, and warns
  instead when the chain holds something an FBX cannot express: generated or
  object coordinates, a Mapping node driven by another node, a rotation out of
  the UV plane, or textures placed several different ways at once. In those
  cases the coordinates are left alone rather than moved wrongly, and the
  atlas bake is offered as the way out.

## [0.17.0]

### Changed

- **A surface of its own is off by default**, because a mod supplied surface
  still makes the game refuse to build a material and draw the item white:

  ```
  Material builder got given parameters that don't match any shaders -
  ShaderType:Simple ZoneDefinition:OneZoneNew LightingMethod:Lit
  ```

  `ZoneDefinition` is chosen by `GetColorZoneDefinition` inside the game, and
  its members, read out of `Paralives.dll`, are `None`, `OneZoneOld`,
  `OneZoneNew`, `ColorZoneMapOld` and `ColorZoneMapNew`. Something in a mod
  supplied surface makes it answer `OneZoneNew`, which the plain shader has no
  variant for. Removing the swatch defaults did not change it, and
  `GenericGrayMask` declares them and renders, so it is not those on their own.

  Borrowing the game's own surface is proven to render, so that is the default
  again. The relief has to wait, and the switch stays for anyone carrying the
  investigation further.

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
