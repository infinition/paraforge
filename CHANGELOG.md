# Changelog

All notable changes to ParaForge. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/) while it is below 1.0, meaning the
minor number moves on every behaviour change.

Every entry below was driven by something measured in the game's own data
rather than assumed. Paralives is in early access, so the game build a finding
was measured on is recorded with it.

## [0.32.0]

### Added

- **A person to build against.** A Para sized outline standing next to the
  item, off by default, under Viewport guides.

  A Para is not 1.80. The game's own body meshes carry their world position
  and assemble to exactly 1.702 m:

  ```
  HumanFoot0Left   0.000 to 0.119
  HumanBottom      0.390 to 0.962
  HumanTop         0.918 to 1.454
  HumanHead        1.427 to 1.702
  ```

  So 1.702 is the default, and the outline is proportioned on those four
  numbers rather than on a generic figure. The height is editable for anything
  built to a different reference. It is drawn as a cross, two outlines at
  right angles, so it stays readable from any camera angle instead of
  vanishing edge on.

## [0.31.0]

### Fixed

- **Every item left turned around.** An asymmetric item arrived in the game
  with its front where its back should be. On a chair it showed twice over,
  and both symptoms are the same half turn: the catalogue thumbnail is shot
  from behind, and a Para sits down facing their own backrest. Symmetrical
  items, which is most of what had been exported until now, never showed it.

  The export now applies a half turn around Z before the Y up rotation, so
  what you build facing the green viewport arrow is what the game calls the
  front. Nothing in Blender changes meaning, and nothing has to be remodelled:
  regenerating an item is enough.

  Settled in the game rather than in the files. Three attempts to read it out
  of the shipped meshes gave three different answers, because the FBX
  importer's axis conversion is not the inverse of the export's and every
  reading needed a sign that could not be checked. A chair built facing the
  arrow, exported, and looked at in game answers it in one go.

  The half turn is now pinned by a test on a marked vertex, and it agrees with
  the slot template independently: `ChairSlotAndLocator` puts the front feet
  at Z +0.42, and Blender +Y now leaves on the game's +Z, so the knees land
  where the arrow points.

- **The 0.29.0 and 0.30.0 arrows were both symptoms of this.** Neither
  direction was right, because the export underneath them was turned around.
  The seat arrow points along Y+ and the backrest check wants the back on the
  Y- side, which is what 0.27.0 said, and with the export fixed both are now
  true rather than accidentally half true.

## [0.30.0]

### Fixed

- **A Para sits facing Y+, along the floor arrow.** 0.29.0 said the opposite,
  reasoned out of `ChairSlotAndLocator`, whose seat children put the
  `ButtLocator` at Z -0.28 and the front feet at Z +0.42. The reasoning needed
  the sign of the Blender to file axis mapping, and that sign was wrong.

  Measured instead of reasoned, by importing the game's own chairs into
  Blender and asking where the geometry in the top third of each one sits:

  ```
  48 chairs and armchairs measured
     43 put the backrest on the Y- side, from -0.10 to -0.47
      4 too symmetrical to say
      1 disagrees
  ```

  So the backrest goes behind the arrow, the knees at the arrow, which is what
  0.27.0 said before 0.29.0 broke it. The seat height arrow points along Y+
  again.

  The floor arrow is unchanged and was never in question: it is the item's
  front, and it is what the catalogue thumbnail and the placement rotation
  use.

### Added

- **Which way round.** The arrow says which way a Para will face; this says
  which way the item actually is, which is the half of it you cannot check by
  eye once the model is symmetrical enough to fool you.

  Geometry in the top third of the item is the back. If its centre sits on the
  Y- side, the item agrees with the game's 43 chairs and the check passes. On
  the Y+ side it warns, with a half turn on a button, because nothing in the
  game will ever tell you: the item is in the catalogue, a Para walks over,
  sits down, and faces their own backrest.

  A stool, a pouf and a bench have nothing standing above the seat, so there
  is no back to be wrong and the check stays quiet.

## [0.29.0]

### Fixed

- **An item a Para sits on carries neither resize handle. Not one of the two:
  neither.** 0.27.0 said the two were alternatives, which was the wrong
  conclusion drawn from a population that mixed items you sit on with items
  you stand beside. The real split, counted over the shipped prefabs that name
  a slot template and grouped by whether that template has a `Seat` node:

  ```
  ChairSlotAndLocator       29 prefabs,  0 declaring a resize widget
  CounterSlotsAndLocators   29 prefabs, 29 declaring one
  ```

  No exception either way. A resize widget on something a Para sits on moves
  the seat locators somewhere they cannot path to, and the sit fails in
  silence.

  Two of the user's own items settle it, since their catalogue entries are
  identical down to the tag and the slot GUID and they differ only in the
  prefab: the one with no widget is sat on, the one declaring `IsResizable` is
  walked past. So both handles are now dropped from any item whose template
  carries a `Seat` node, whatever the panel has ticked, and the panel greys
  them out and says why. Both handles together remain fine on anything else,
  and 133 shipped prefabs declare both.

- **The sit direction arrow pointed the wrong way.** Read out of
  `ChairSlotAndLocator`, the seat's own children put the `ButtLocator` at
  Z -0.28 and the front feet at Z +0.42, so a Para faces the item's +Z. Export
  maps Blender +Y onto the file's -Z. The knees therefore land at Blender -Y,
  against the floor arrow rather than along it, and the backrest belongs on
  the +Y side where the arrow points.

  0.27.0 drew it the other way and said so in both READMEs. A chair built to
  that arrow works, seats a Para, and sits them facing their own backrest.

## [0.28.0]

### Fixed

- **A pouf has no seat, said 0.27.0.** The first measurement averaged the
  upward facing faces between 15% and 75% of the item's height, which is a
  description of a dining chair and of nothing else. A box shaped ottoman
  seats a Para on its lid, at 100% of its height, and was told it had nowhere
  to sit at all. A cube got the same answer.

  The seat is not a fraction of the item and it is not an average. It is the
  largest single horizontal surface the item has, so it is now found as one:
  upward facing triangles are binned by height, the heaviest bin by area wins,
  and the answer is that cluster alone. Averaging a chair mixes its seat with
  its armrests and its backrest top, and the answer belongs to none of them.

  Checked against the game's own furniture, which is what makes it a
  measurement rather than a guess:

  ```
  Chairs        28 meshes   0.448 m    49% of the item's height
  OfficeChairs   5 meshes   0.449 m    43%
  Benches       12 meshes   0.450 m    86%
  Ottomans       7 meshes   0.449 m   100%
  Stools         9 meshes   0.649 m    99%
  ```

- **And there was never one band.** 0.27.0 warned outside 0.316 to 0.520,
  which fails every stool the game ships. There are two heights, 0.45 for
  anything you sit on with your feet down and 0.65 for a stool, and the ratios
  above show why a single band could not exist: a dining chair's seat is
  halfway up it, an ottoman's seat is its lid.

  ParaForge now names which of the two your mesh matches instead of judging it,
  and only warns outside 0.20 to 0.75, where no shipped item sits.

### Changed

- **The height was never fixed by the template either.** Every slot template
  carries `VaryBasedOnHeight:True` on its seat locator, with `Min` and `Max`
  children bounding the travel, so the game moves the Para to suit the item
  rather than demanding a height of it. That is why a stool and a dining chair
  both work through the same `ChairSlotAndLocator`, and why this check is
  information and a wide safety net, not a rule.

  Read out of `Environments/Items/Prefabs/*.prefab` in `Main.mod`. The same
  files show `ShorterChairSlotAndLocator` holding its seat at exactly the
  position `ChairSlotAndLocator` does, so picking the shorter variant to fix a
  low chair will not do anything.

## [0.27.0]

### Fixed

- **A chair that declares both resize widgets seats nobody.** Measured on game
  build 0.1.6b: of the 353 shipped items that carry a place to sit, 146 declare
  `IsResizable`, 27 declare `IsScalable`, 180 declare neither, and not one
  declares both. Declaring both moves the seat locators somewhere no Para can
  path to, so the item appears in the catalogue, renders correctly, and is
  walked past forever with no error anywhere.

  Confirmed by experiment rather than inferred: stripping both flags from a
  custom chair made it usable immediately, and putting them back broke it
  again. The two toggles now switch each other off, the prefab writer refuses
  to write both even if a scene saved before this rule asks for it, and the
  panel says so under the pair.

### Added

- **Seat guide.** Nothing in a mesh tells the game where to sit: the slot
  template does, and it holds the Seat and the ButtLocator at heights it was
  authored for. A mesh with no surface there still seats a Para, floating above
  the cushion or sunk into it, and no error is ever raised.

  The seat is measured, drawn in the viewport, and reported as a checklist
  line and under the seat template dropdown, with an arrow at seat height
  showing which way a Para will face: along Y+, the same direction the big
  green floor arrow points, so the backrest belongs at the far end.

  The measurement itself was wrong in this release and is corrected in 0.28.0.

## [0.26.0]

### Added

- **Ask the game to explain itself.** A Para refusing to use an item says
  nothing, and every guess about why costs a restart. The game does keep a
  reason, behind `Setting.Loggers`, which ships with every logger off:

  ```
  =LogItemSlotManager:False
  =LogItemFinderRuleManager:False
  =LogItemLocatorManager:False
  ```

  A mod's own Settings merge over the game's, so the button writes a
  `Loggers.setting` that turns them on, and `Player.log` then carries the real
  reason in the game's own words:

  ```
  !! Item has no item slots !!
  Slot has no ItemObjectChairSlot component.
  Slot is of type X instead of required type Y.
  ```

  Press again to remove the file.

  Decompiled from `Paralives.dll`, the sit chain is
  `SetTargetedLocatorProcessor` reading `UsedItemSlotGUIDsOfPreviousInteraction`,
  which `ItemSlotManager` only fills for an item registered in `ItemsWithSlots`,
  which in turn requires `root.GetChildren<ItemObjectSlot>()` to be non empty.
  Every step of that is now observable rather than inferred.

## [0.25.0]

### Fixed

- **The right tag was not enough, and the Para still walked to another chair.**
  Filing an item under `Chairs` is what 0.24.0 checked for, and it is only half
  of it. The tag names a default template, but the item overrides it, and 22 of
  the game's 29 shipped chairs write their own:

  ```
  =OverrideNestedPrefabToSpawn:True
  =NestedPrefabToSpawn:3998377347708258495
  ```

  Counted across the 29 items tagged `Chairs`: 25 name a template in
  `Items.setting`, 18 in their prefab, 3 in neither. ParaForge wrote none of
  them, so the catalogue entry looked right and no Para could reach it.

### Added

- **A seat picker**, listing the 29 slot templates the game ships. Left on
  automatic it follows the catalogue tag, which is what most items want. Three
  chair variants exist, `ChairSlotAndLocator`, `ShorterChairSlotAndLocator` and
  `LongChairSlotAndLocator`, for three seat heights, and the shipped chairs are
  split evenly across them, so an explicit choice is worth having.

## [0.24.0]

### Added

- **Whether a Para will actually use the item.** An imported chair that nobody
  sits on is not missing a seat, it is filed under the wrong tag.

  A chair carries no seat of its own. Of the game's 2434 prefabs only 58 name a
  `NestedPrefabToSpawn`, and no couch, stool or bench names one at all. What
  makes an item usable is its **catalogue tag**: the tag entry in
  `BuildModeCatalogTags.setting` carries the template, and the game attaches it
  to everything filed under that tag.

  | Tag | Template it attaches |
  |---|---|
  | Chairs, OfficeChairs | `ChairSlotAndLocator` |
  | Armchairs | `ArmchairSlotAndLocator` |
  | Couches | `CouchesSlotAndLocators` |
  | Benches, _SittableBench | `BenchSlotsAndLocators` |
  | Tables | `TableSlots` |
  | CountersAndCabinets | `CounterSlotsAndLocators` |
  | Toilets | `ToiletSlotAndLocators` |
  | _BedCrib | `CribSlotsAndLocators` |

  Thirteen tags out of 298 attach something, three of them a sound rather than
  a place to sit. The template positions the Para itself: `ArmchairSlotAndLocator`
  holds a Seat, a ButtLocator, a FeetFront and a FeetEnter, so nothing about
  the animation has to be authored.

  Interactions are the tag's other field, `InteractionGroup`, on 47 tags: what
  a Para may do with a computer, a fridge, a range, a sink. Tags inherit, which
  is why `Armchairs` seats a Para through `Seating` without declaring anything
  itself.

  The picker now says what the chosen tag brings, right under the choice, and
  the checklist repeats it. It is information rather than a fault, since most
  items are decoration and are meant to be.

  What this does not cover: food is not a placeable item. `FoodBreadRound`
  carries `Tag: s0`, no tag at all, and the `Food` tag carries nothing, so a
  food mesh cannot be made edible by exporting it. Beds are the other gap: they
  hang their slots off a child object carrying an `ItemNestedPrefabSpawner`
  rather than off the tag.

## [0.22.0]

### Added

- **Stretching per axis**, the game's second resize widget and a different
  thing from scaling. Scaling multiplies the whole item, stretching pulls it
  along the axes you allow to real dimensions, so a shelf can be made wider
  without becoming taller. The game keeps them apart itself, in
  `CancelResizeOrScaleItem`, and 133 of its 2434 prefabs declare both.

  It takes two statements, because the mesh has to be told which of its own
  axes follow the item's cube. `ArchitectureFanCommercial` carries the mesh
  side alone, which is what proves they are separate:

  ```
  ItemObjectRoot:
   IsResizable:True
    ResizableAxes:bool3(True, False, True)
    MinSizes:(0.2000, 0.1000, 0.0500)
    HasMaxSize:True
    MaxSizes:(20.0000, 10.0000, 5.0000)
  ItemMeshReference:
   IsResizable:bool3(True, False, True)
  ```

  The sizes are metres in the same order as `Size`, so they follow the item's
  own measurements. `HasMaxSize` gates `MaxSizes` exactly as `HasMaxScale`
  gates `MaxScale`, and there is no `HasMinSize` anywhere in the assembly: 139
  shipped prefabs write a ceiling while only 47 declare the flag that applies
  it.

### Changed

- **Wider limits at both ends**, from 0.5 to 2 up to 0.1 to 10. Across the 185
  shipped prefabs that set them, `MinScale` runs 0.25 to 1.75 and `MaxScale`
  0.5 to 10, because each is authored for a purpose. A mod item is handed to
  someone who wants it tiny on a shelf and huge in the garden, so the ceiling
  is now the game's own maximum and the floor goes below anything it ships.
- The scaling toggle is called **Scalable in game** rather than Resizable,
  which was the name of the other widget.

## [0.21.0]

### Added

- **A Remesh panel**, because collapsing edges is the wrong tool for an
  organic asset. Blender's own modifier is exposed as it is, with its four
  modes and the settings each one actually uses: Octree Depth, Scale and
  Threshold for Blocks, Smooth and Sharp, plus Sharpness for Sharp, and Voxel
  Size with Adaptivity for Voxel. Remove Disconnected and Smooth Shading sit
  alongside. Settings that mean nothing in the current mode are not drawn.

  The point is that the choice is yours and it is visible before anything is
  baked: pick the look in the viewport, then let the original be baked onto
  it.

  Measured on a 302 108 triangle asset, in Blender 5.2:

  | mode | setting | triangles | time |
  |---|---|---|---|
  | Sharp | depth 5 | 1 456 | 0.6 s |
  | Sharp | depth 6 | 5 656 | 0.6 s |
  | Sharp | depth 7 | 22 604 | 0.9 s |
  | Blocks | depth 5 | 1 456 | 0.6 s |
  | Voxel | 0.02 m, adaptivity 0.3 | 7 496 | 0.7 s |

  Remeshing keeps no UV map, no vertex colour and no material but the first,
  so the bake is not an option but the other half of the operation, and it is
  on by default. Turned off, the panel says the object will come out bare
  rather than letting it look like a broken remesh. The whole run on that
  asset, remesh at depth 6 then unwrap and bake four maps at 2048, took 165
  seconds and came out at 5 656 triangles carrying the original's grain,
  bolts and relief.

### Fixed

- **Reduce to the budget did nothing from edit mode**, which is most of why
  it seemed not to work. Applying a modifier is refused outright there:

  ```
  Operator bpy.ops.object.modifier_apply.poll() This modifier operation is
  not allowed from Edit mode
  ```

  and the failure arrived as a per object warning, which reads as a button
  that ran and changed nothing. Both reducing and remeshing now step into
  object mode and put you back in the mode you were in.

- **A failed rebake is now said out loud.** It left an object with no UVs and
  no texture, which looks exactly like the mesh having disappeared.

## [0.20.0]

### Added

- **The yellow scaling handle**, which a mod item never had. The game creates
  the widget only for a root that declares it:

  ```csharp
  if (... && player.ItemSelected.Item.Root.IsScalable)
  ```

  and the drag reaches one axis only if that axis is named:

  ```csharp
  vector2.x = (item.ScalableAxes.x ? value : 1f);
  ```

  so the flag without the axes gives a handle that does nothing. Counted
  across the game's 2434 prefabs, now readable as plain text in
  `Main.mod/Environments/Items/Prefabs`: 1114 declare `IsScalable`, 983 of
  them on all three axes, against 650 that declare the per axis `IsResizable`
  instead. The three axis form is what is written.

  `HasMinScale` and `HasMaxScale` are written too, although the game's own
  prefabs omit them, because the clamp reads the booleans and not the bounds:

  ```csharp
  if (item.HasMinScale) min = ...
  value = Mathf.Clamp(value, min, item.HasMaxScale ? item.MaxScale : ...);
  ```

  Without them a declared MinScale is a limit that does not hold and the item
  can be dragged down to nothing. Bounds default to 0.5 and 2, the most
  common values among the scalable prefabs.

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
