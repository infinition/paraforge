# Changelog

All notable changes to ParaForge. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/) while it is below 1.0, meaning the
minor number moves on every behaviour change.

Every entry below was driven by something measured in the game's own data
rather than assumed. Paralives is in early access, so the game build a finding
was measured on is recorded with it.

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
