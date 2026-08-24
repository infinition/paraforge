# SPDX-License-Identifier: GPL-3.0-or-later
"""Two language interface, French by default.

Blender bakes bl_label, bl_description and property names into the RNA when a
class is registered, so a live switch can never reach them. ParaForge stores
the choice in its own config file, reads it at import time for those static
strings, and re-registers itself when the language changes. Everything drawn
at runtime goes through t() and updates on the next redraw.

Keys are the English source strings, so a missing translation degrades to
English instead of raising.
"""

import json
import os

DEFAULT = "fr"

LANGUAGES = (
    ("fr", "Français", "Interface en français"),
    ("en", "English", "English interface"),
)

CODES = tuple(code for code, _label, _description in LANGUAGES)

_current = None


# --------------------------------------------------------------------------
# Persistence


def config_path():
    import bpy

    folder = bpy.utils.user_resource("CONFIG", path="paraforge", create=True)
    return os.path.join(folder, "config.json")


def _read():
    try:
        with open(config_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    try:
        with open(config_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        return True
    except OSError as error:
        print("[ParaForge] could not save the language:", error)
        return False


def language():
    """Current language code, read from disk once per Blender session."""
    global _current
    if _current is None:
        code = _read().get("language", DEFAULT)
        _current = code if code in CODES else DEFAULT
    return _current


def set_language(code):
    """Persist the language. The caller re-registers to refresh static text."""
    global _current
    if code not in CODES or code == language():
        return False
    data = _read()
    data["language"] = code
    _write(data)
    _current = code
    return True


def language_label(code=None):
    code = code or language()
    for key, label, _description in LANGUAGES:
        if key == code:
            return label
    return code


def is_french():
    return language() == "fr"


# --------------------------------------------------------------------------
# Lookup


def t(text, *args):
    """Translate a source string, then apply str.format when args are given."""
    code = language()
    out = text if code == "en" else CATALOG.get(code, {}).get(text, text)
    if args:
        try:
            return out.format(*args)
        except (IndexError, KeyError, ValueError):
            return out
    return out


def pick(french, english):
    """For the rare string with no useful English source to key on."""
    return french if is_french() else english


# --------------------------------------------------------------------------
# French catalogue


FR = {
    # -- The item's own surface ---------------------------------------------
    "Give the item its own surface": "Donner sa propre surface à l'objet",

    "Write a Surface for this item so it carries its own normal map and "
    "smoothness. Borrowing the game's own surface renders too, but flat: no "
    "prefab field anywhere carries a normal map, so without a surface of its "
    "own the item has no relief":
        "Écrit une Surface pour cet objet, afin qu'il porte sa propre normal "
        "map et sa brillance. Emprunter la surface du jeu s'affiche aussi, "
        "mais à plat : aucun champ de prefab ne porte de normal map, donc "
        "sans surface propre l'objet n'a pas de relief",

    "Carries the normal map and the smoothness. Without it the item borrows "
    "the game's shared surface and has no relief.":
        "Porte la normal map et la brillance. Sans elle, l'objet emprunte la "
        "surface partagée du jeu et n'a aucun relief.",

    "Smoothness": "Brillance",

    "How glossy the surface is, 0 matte and 1 mirror. The game stores one "
    "value per surface and has no slot for a smoothness texture, so a "
    "Smoothness map is averaged into this on export":
        "À quel point la surface est brillante, 0 mat et 1 miroir. Le jeu "
        "stocke une seule valeur par surface et n'a aucun emplacement pour "
        "une texture de brillance : une carte Smoothness y est donc moyennée "
        "à l'export",

    "Smoothness averaged to {0:.2f}. The game stores one value per surface "
    "and has no slot for a smoothness map":
        "Brillance moyennée à {0:.2f}. Le jeu stocke une seule valeur par "
        "surface et n'a aucun emplacement pour une carte de brillance",

    # -- Preview and rebaking -----------------------------------------------
    "Preview as in game": "Aperçu comme dans le jeu",
    "Back to my materials": "Revenir à mes matériaux",
    "Your own materials are back": "Tes propres matériaux sont revenus",
    "No texture to preview": "Aucune texture à prévisualiser",
    "Showing {0}": "Affiche {0}",

    "Write the textures exactly as the export would, read them back, and show "
    "the object through them. What you see is then the data the game is "
    "handed, not the material the file arrived with. Press again to put your "
    "own materials back":
        "Écrit les textures exactement comme le ferait l'export, les relit, et "
        "affiche l'objet à travers elles. Ce que tu vois est alors la donnée "
        "remise au jeu, pas le matériau livré avec le fichier. Appuie encore "
        "pour retrouver tes propres matériaux",

    "No {0}, so the game will not have one either":
        "Aucune {0}, le jeu n'en aura donc pas non plus",

    "Bake the look back onto it": "Rebaker le rendu dessus",

    "Collapsing edges throws the UVs out of shape, which is why the texture "
    "seems to disappear. This unwraps the reduced mesh and bakes the "
    "original's colour, relief and roughness onto it":
        "Effondrer les arêtes déforme les UV, et c'est pour ça que la texture "
        "semble disparaître. Ceci déplie le mesh réduit et y bake la couleur, "
        "le relief et la rugosité de l'original",

    "Collapsing edges throws the UVs out of shape, which is why the texture "
    "seems to disappear. Unwrap the reduced mesh and bake the original's "
    "colour, relief and roughness onto it":
        "Effondrer les arêtes déforme les UV, et c'est pour ça que la texture "
        "semble disparaître. Déplie le mesh réduit et y bake la couleur, le "
        "relief et la rugosité de l'original",

    ", texture baked back onto it": ", texture rebakée dessus",
    "Could not bake it back: {0}": "Impossible de rebaker : {0}",

    # -- The asset name is the item's identity ------------------------------
    "Asset name": "Nom de l'objet",
    "Give the item a name": "Donne un nom à l'objet",

    "No name set, so the object name {0} would be used. Another import called "
    "the same thing would overwrite this item in the game":
        "Aucun nom saisi : le nom d'objet {0} serait utilisé. Un autre import "
        "portant le même nom écraserait cet objet dans le jeu",

    "{0} is a name an importer chose, not one you did. Anything else exported "
    "under it replaces this item":
        "{0} est un nom choisi par un importeur, pas par toi. Tout ce qui sera "
        "exporté sous ce nom remplacera cet objet",

    "{0} is already in this mod. Exporting replaces it, which is what you want "
    "for an update and not for a new item":
        "{0} est déjà dans ce mod. Exporter le remplace, ce qui est voulu pour "
        "une mise à jour et pas pour un nouvel objet",

    "{0}, taken from the object": "{0}, repris de l'objet",

    "No NormalOcclusion map, the item will have no relief":
        "Aucune carte NormalOcclusion, l'objet n'aura pas de relief",

    "No GrayMask, so the surface sits on the game's neutral base and the "
    "colour comes through the DetailMap":
        "Aucun GrayMask : la surface repose donc sur la base neutre du jeu et "
        "la couleur passe par le DetailMap",

    "Using the game's {0}. The NormalOcclusion and Smoothness maps have no "
    "slot on a shared surface, so the item has no relief. Turn on its own "
    "surface to give it one":
        "Utilise le {0} du jeu. Les cartes NormalOcclusion et Smoothness "
        "n'ont pas d'emplacement sur une surface partagée, l'objet n'a donc "
        "aucun relief. Active sa propre surface pour lui en donner un",

    # -- Units --------------------------------------------------------------
    "FBX units per metre": "Unités FBX par mètre",

    "The game multiplies the raw coordinates of an FBX by 0.01, so a mesh has "
    "to leave Blender in centimetres or it arrives a hundred times too small "
    "and cannot be seen. Measured in the game's own imported assets. Only "
    "change this if a game update changes it":
        "Le jeu multiplie les coordonnées brutes d'un FBX par 0,01 : un mesh "
        "doit donc sortir de Blender en centimètres, sinon il arrive cent "
        "fois trop petit et reste invisible. Mesuré dans les assets importés "
        "par le jeu lui-même. À ne changer que si une mise à jour du jeu le "
        "change",

    # -- Merging into the game's lists ------------------------------------
    "Merge style": "Style de fusion",

    "How an entry is added to a list the base game already fills. Leave this "
    "alone unless the game misbehaves":
        "Comment une entrée est ajoutée à une liste que le jeu remplit déjà. "
        "À ne pas toucher, sauf si le jeu se comporte mal",

    "Add to the game's list": "Ajouter à la liste du jeu",
    "Adds a member, identified by its GUID. What a content mod wants":
        "Ajoute un membre, identifié par son GUID. Ce que veut un mod de "
        "contenu",

    "Extend an existing entry": "Étendre une entrée existante",
    "Merges fields onto an entry that already exists. How the game's own "
    "French.mod writes translations":
        "Fusionne des champs sur une entrée qui existe déjà. C'est ainsi que "
        "le French.mod du jeu écrit ses traductions",

    "Positional (dangerous)": "Positionnel (dangereux)",
    "Numbered entry with a size line. On a list the base game fills, this "
    "makes the game keep only what the mod wrote and drop everything else":
        "Entrée numérotée avec une ligne de taille. Sur une liste que le jeu "
        "remplit, le jeu ne garde alors que ce que le mod a écrit et jette "
        "tout le reste",

    "A mod adds to lists the game already fills. Getting this wrong makes "
    "the game keep only what the mod wrote, which is how every menu label "
    "turns into a raw key.":
        "Un mod ajoute à des listes que le jeu remplit déjà. Se tromper ici "
        "fait que le jeu ne garde que ce que le mod a écrit, et c'est ainsi "
        "que chaque libellé de menu devient une clé brute.",

    # -- Surfaces and colour zones ----------------------------------------
    # Why an item can be in the catalogue and still draw nothing. See spec.py.
    "The colour zones were left out of the FBX on purpose. A non "
    "recolourable item that carries them does not render in game":
        "Les zones de couleur ont été volontairement exclues du FBX. Un objet "
        "non recolorable qui les porte ne s'affiche pas dans le jeu",

    "Not used. They stay in Blender and are left out of the FBX, because a "
    "non recolourable item that carries them does not render":
        "Inutilisées. Elles restent dans Blender et sont exclues du FBX : un "
        "objet non recolorable qui les porte ne s'affiche pas",

    "Not used, which is what a non recolourable item wants":
        "Inutilisées, ce qui est exactement ce que veut un objet non "
        "recolorable",

    "No texture in the mod, the item will render with {0}":
        "Aucune texture dans le mod, l'objet s'affichera avec {0}",

    "{0} holds surfaces this add-on did not write, so it was left alone. A "
    "mod defined surface crashes the game at startup, remove it by hand if "
    "the game does not start":
        "{0} contient des surfaces que cet add-on n'a pas écrites, il a donc "
        "été laissé tel quel. Une surface définie par un mod fait planter le "
        "jeu au démarrage, supprimez-la à la main si le jeu ne se lance pas",

    "Removed the {0} written by an earlier version: it made the game throw at "
    "startup and the item render as nothing. The item now points at the "
    "game's own {1}":
        "Retiré le {0} écrit par une version précédente : il faisait planter "
        "le jeu au démarrage et l'objet ne s'affichait pas. L'objet pointe "
        "maintenant le {1} du jeu",

    "Repointed {0} other prefab(s) at {1}, they referenced a surface that no "
    "longer exists":
        "{0} autre(s) prefab(s) repointé(s) vers {1}, ils référençaient une "
        "surface qui n'existe plus",

    # -- Panels -----------------------------------------------------------
    "Paralives export": "Export Paralives",
    "Orientation": "Orientation",
    "Colour zones": "Zones de couleur",
    "Textures": "Textures",
    "Export options": "Options d'export",
    "Viewport guides": "Repères dans la vue",
    "Calibration": "Calibrage",
    "Mod folder inspector": "Inspecteur du dossier mod",
    "Language": "Langue",
    "Scene not ready": "Scène pas encore prête",

    # -- Target -----------------------------------------------------------
    "Paralives folder not found": "Dossier Paralives introuvable",
    "Detect Paralives folder": "Détecter le dossier Paralives",
    "Open folder": "Ouvrir le dossier",
    "Mod folder": "Dossier du mod",
    "Item type": "Type d'objet",
    "Catalog": "Catalogue",
    "Custom tag": "Tag personnalisé",
    "Asset name": "Nom de l'asset",

    # -- Checklist --------------------------------------------------------
    "{0} ok   {1} warn   {2} blocking": "{0} ok   {1} alerte   {2} bloquant",
    "Items in this mod": "Objets de ce mod",
    "No mod folder chosen": "Aucun dossier de mod choisi",
    "That folder is not there any more": "Ce dossier n'existe plus",
    "Nothing in the catalogue yet. Export a mesh, then press Create the item "
    "in the catalogue.":
        "Rien au catalogue pour l'instant. Exporte un mesh, puis appuie sur "
        "Créer l'objet dans le catalogue.",
    "{0} item(s)": "{0} objet(s)",
    "{0} file(s)": "{0} fichier(s)",
    "shares {0} with another item": "partage {0} avec un autre objet",
    "{0} without a picture yet, load the mod in the game once":
        "{0} sans image pour l'instant, charge le mod une fois dans le jeu",
    "Refresh": "Actualiser",
    "Read the mod folder again, thumbnails included":
        "Relire le dossier du mod, miniatures comprises",
    "Remove from the mod": "Retirer du mod",
    "Remove this item from the mod: its prefab, its mesh, its textures, "
    "every sidecar, its catalogue entry, its translation and its thumbnail. "
    "Undo the last write puts it back":
        "Retirer cet objet du mod : son prefab, son mesh, ses textures, tous "
        "les fichiers annexes, son entrée de catalogue, sa traduction et sa "
        "miniature. Annuler la dernière écriture le remet",
    "That item is no longer in the mod": "Cet objet n'est plus dans le mod",
    "and {0} more": "et {0} de plus",
    "plus its catalogue and translation entries":
        "plus ses entrées de catalogue et de traduction",
    "Kept, another item uses them:": "Gardés, un autre objet s'en sert :",
    "Removed {0}": "{0} retiré",
    "Removed {0}, {1} file(s)": "{0} retiré, {1} fichier(s)",
    "Refresh": "Rafraîchir",
    "Fix": "Corriger",
    "Fix everything safe": "Tout corriger sans risque",
    "Export to Paralives": "Exporter vers Paralives",
    "Export anyway": "Exporter quand même",

    # -- Check labels -----------------------------------------------------
    "Mesh selected": "Mesh sélectionné",
    "Scene unit scale": "Échelle des unités",
    "Transforms applied": "Transformations appliquées",
    "Origin placement": "Placement de l'origine",
    "Bounding size": "Encombrement",
    "Faces Y+": "Orienté vers Y+",
    # -- Remesh --------------------------------------------------------------
    "Remesh": "Remesh",
    "Remesh mode": "Mode de remesh",
    "Which of Blender's four remesh solvers to run":
        "Lequel des quatre solveurs de remesh de Blender lancer",
    "Blocks": "Blocs",
    "Voxels left square. The blocky look, kept":
        "Voxels laissés carrés. Le rendu cubique, assumé",
    "Smooth": "Lisse",
    "The same voxels, rounded off": "Les mêmes voxels, arrondis",
    "Sharp": "Net",
    "Rounded, but corners and edges held. The usual choice for an object":
        "Arrondi, mais coins et arêtes tenus. Le choix habituel pour un objet",
    "Voxel": "Voxel",
    "A newer solver sized in metres rather than by subdivision, with an "
    "adaptivity that spends triangles only where the shape needs them":
        "Un solveur plus récent, dimensionné en mètres plutôt que par "
        "subdivision, avec une adaptivité qui dépense les triangles là où la "
        "forme en a besoin",
    "Octree Depth": "Profondeur d'octree",
    "How finely the volume is divided. Each step doubles the resolution, so "
    "it also roughly quadruples the triangles":
        "À quel point le volume est découpé. Chaque cran double la "
        "résolution, donc quadruple à peu près les triangles",
    "Scale": "Échelle",
    "How much of the octree the object fills. Nearer 1 gives a finer result "
    "at the same depth, and risks clipping the shape":
        "Quelle part de l'octree l'objet remplit. Près de 1 donne un résultat "
        "plus fin à profondeur égale, et risque de rogner la forme",
    "Sharpness": "Netteté",
    "How hard an edge has to be before it is kept":
        "À quel point une arête doit être marquée pour être gardée",
    "Threshold": "Seuil",
    "How much of a cell has to be inside the shape for it to be filled":
        "Quelle part d'une cellule doit être dans la forme pour être remplie",
    "Voxel Size": "Taille de voxel",
    "The size of one voxel, in metres. Small means fine and slow: on an "
    "object under two metres, a millimetre is already millions of triangles":
        "La taille d'un voxel, en mètres. Petit veut dire fin et lent : sur "
        "un objet de moins de deux mètres, un millimètre fait déjà des "
        "millions de triangles",
    "Adaptivity": "Adaptivité",
    "Lets flat areas use bigger triangles. Above zero it spends the budget "
    "where the shape actually turns":
        "Laisse les zones plates prendre de plus gros triangles. Au-dessus de "
        "zéro, le budget part là où la forme tourne vraiment",
    "Remove Disconnected": "Retirer les morceaux détachés",
    "Drop the loose shells the solver leaves behind":
        "Jette les coques isolées que le solveur laisse derrière lui",
    "Smooth Shading": "Ombrage lisse",
    "Shade the result smooth rather than faceted":
        "Ombre le résultat en lisse plutôt qu'en facettes",
    "Remeshing keeps no UV map, no vertex colour and no material but the "
    "first, so the object comes out bare. This unwraps the new surface and "
    "bakes the original's colour, relief and roughness onto it. Without it "
    "there is nothing left to look at":
        "Le remesh ne garde aucune carte UV, aucune couleur de sommet et "
        "aucun matériau sauf le premier, donc l'objet ressort nu. Ceci "
        "déplie la nouvelle surface et y cuit la couleur, le relief et la "
        "rugosité de l'original. Sans ça, il ne reste rien à regarder",
    "Throw the topology away and lay an even surface over the volume, then "
    "bake the original's look onto it. Where collapsing edges tears an "
    "organic asset apart long before it reaches a furniture budget, this "
    "rebuilds it instead":
        "Jette la topologie et pose une surface régulière sur le volume, puis "
        "y cuit le rendu de l'original. Là où l'effondrement d'arêtes déchire "
        "un asset organique bien avant d'atteindre un budget de mobilier, "
        "ceci le reconstruit",
    "Rebuilds the topology instead of collapsing it, which holds an organic "
    "shape together where reducing tears it apart. Try the modes on screen, "
    "then bake the original onto what you chose.":
        "Reconstruit la topologie au lieu de l'effondrer, ce qui tient une "
        "forme organique là où la réduction la déchire. Essaie les modes à "
        "l'écran, puis cuis l'original sur ce que tu as choisi.",
    "Remeshing keeps no UV map, so the object is bare until something is "
    "baked onto it":
        "Le remesh ne garde aucune carte UV, donc l'objet est nu tant que "
        "rien n'y est cuit",
    "Remeshed, but the look could not be baked back, so the object has no "
    "texture: {0}":
        "Remeshé, mais le rendu n'a pas pu être recuit, donc l'objet n'a pas "
        "de texture : {0}",
    "{0} triangles, was {1}": "{0} triangles, contre {1} avant",

    # -- The scaling handle on a placed item ---------------------------------
    "Seat": "Place assise",
    "The template that places a Para on the item. The tag names a default, "
    "but 22 of the game's 29 chairs name their own instead, which is why the "
    "tag alone does not seat anyone":
        "Le gabarit qui place un Para sur l'objet. Le tag en nomme un par "
        "défaut, mais 22 des 29 chaises du jeu nomment le leur à la place, et "
        "c'est pour ça que le tag seul n'assoit personne",
    "From the tag": "Depuis le tag",
    "Use whatever the chosen catalogue tag names":
        "Utiliser ce que nomme le tag de catalogue choisi",
    "None": "Aucune",
    "Write nothing, so the item is decoration":
        "N'écrire rien, l'objet reste une décoration",
    "A Para can sit on it: {0}": "Un Para peut s'y asseoir : {0}",
    "Ask the game to explain itself": "Demander au jeu de s'expliquer",
    "Stop explaining": "Arrêter les explications",
    "Turn on the game's own item slot logging, from inside your mod. It then "
    "writes into Player.log exactly why a Para refuses an item: the slot it "
    "wanted, the type it found, and whether the item had any slot at all. "
    "Press again to turn it off":
        "Active le journal interne du jeu sur les emplacements, depuis ton "
        "mod. Il écrit alors dans Player.log exactement pourquoi un Para "
        "refuse un objet : l'emplacement voulu, le type trouvé, et si l'objet "
        "en avait un. Appuie encore pour l'éteindre",
    "Diagnostics off": "Diagnostic désactivé",
    "Diagnostics on. Restart Paralives, ask a Para to use the item, then read "
    "Player.log":
        "Diagnostic activé. Relance Paralives, demande à un Para de se servir "
        "de l'objet, puis lis Player.log",
    "Used by a Para": "Utilisé par un Para",
    "A tag typed by hand, so this cannot be checked":
        "Un tag saisi à la main, donc invérifiable ici",
    "This tag brings ": "Ce tag apporte ",
    "a place to sit, from {0}": "une place assise, depuis {0}",
    "{0}, which is a sound rather than a place":
        "{0}, qui est un son et non une place",
    "interactions, from the {0} tag": "des interactions, depuis le tag {0}",
    "Decoration: this tag brings neither a place to sit nor an interaction, "
    "so a Para will walk past it. Seating lives under Chairs, Armchairs, "
    "OfficeChairs, Couches or Benches":
        "Décoration : ce tag n'apporte ni place assise ni interaction, un Para "
        "passera donc à côté. Les assises sont sous Chairs, Armchairs, "
        "OfficeChairs, Couches ou Benches",
    "Interactions from ": "Interactions depuis ",
    "A Para can use it: ": "Un Para peut s'en servir : ",
    "Attaches ": "Attache ",
    "Decoration, no Para uses it": "Décoration, aucun Para ne s'en sert",

    "Scalable in game": "Mise à l'échelle en jeu",

    "Put the scaling handle on the item once placed, which multiplies the "
    "whole item at once. Without it the game creates no handle and the item "
    "is stuck at the size it was exported. 1114 of the game's 2434 items "
    "declare it. Excludes the per axis stretch: no shipped item carries both":
        "Pose la poignée de mise à l'échelle sur l'objet une fois posé, qui "
        "multiplie l'objet entier d'un coup. Sans elle, le jeu ne crée aucune "
        "poignée et l'objet reste à la taille exportée. 1114 des 2434 objets "
        "du jeu la déclarent. Exclut l'étirement par axe : aucun objet livré "
        "ne porte les deux",

    "Stretchable per axis": "Étirable par axe",


    "The game's other handle, and a different thing: it stretches the item "
    "along the axes you allow instead of multiplying it whole, so a shelf can "
    "be made wider without becoming taller. 650 of the game's items declare "
    "it. Excludes scaling: of the 353 shipped items with a place to sit, 146 "
    "stretch, 27 scale, and none do both":
        "L'autre poignée du jeu, et une chose différente : elle étire l'objet "
        "sur les axes que tu autorises au lieu de le multiplier entièrement, "
        "de sorte qu'une étagère s'élargit sans grandir. 650 des objets du jeu "
        "la déclarent. Exclut la mise à l'échelle : sur les 353 objets livrés "
        "qui ont une place assise, 146 s'étirent, 27 se mettent à l'échelle, "
        "et aucun ne fait les deux",

    "Axes": "Axes",
    "Which axes the player may stretch, width, height, depth":
        "Quels axes le joueur peut étirer : largeur, hauteur, profondeur",

    "How far down the stretch can go, as a share of the exported size":
        "Jusqu'où l'étirement peut descendre, en part de la taille exportée",
    "How far up the stretch can go, as a multiple of the exported size":
        "Jusqu'où l'étirement peut monter, en multiple de la taille exportée",

    "No axis allowed, the handle would do nothing":
        "Aucun axe autorisé, la poignée ne ferait rien",
    "Smallest": "Plus petit",
    "Largest": "Plus grand",
    "How far down the handle can take the item":
        "Jusqu'où la poignée peut réduire l'objet",
    "How far up the handle can take the item":
        "Jusqu'où la poignée peut agrandir l'objet",

    "UV map": "Carte UV",
    "Texture coordinates": "Coordonnées de texture",
    "Triangle count": "Nombre de triangles",
    "N-gons": "N-gones",
    "Texture naming": "Nommage des textures",
    "Target mod folder": "Dossier mod cible",

    # -- Check details ----------------------------------------------------
    "Select the mesh you want to export":
        "Sélectionne le mesh à exporter",
    "Unit scale is {0:.4f}, Paralives expects 1.0 (metres)":
        "Échelle à {0:.4f}, Paralives attend 1.0 (mètres)",
    "1.0, metres": "1.0, mètres",
    "Set to 1.0": "Mettre à 1.0",
    "Rotation or scale still on the object: ":
        "Rotation ou échelle encore sur l'objet : ",
    "Apply rotation and scale": "Appliquer rotation et échelle",
    "rotation and scale are baked": "rotation et échelle figées",
    "The mesh has no geometry": "Le mesh n'a aucune géométrie",
    "{0} {1} is off by {2:+.4f} m": "{0} {1} décalé de {2:+.4f} m",
    "centre": "centre",
    "lower bound": "borne basse",
    "upper bound": "borne haute",
    "No documented rule for this item type, check it by eye":
        "Aucune règle documentée pour ce type, vérifie à l'oeil",
    "Snap origin": "Recaler l'origine",
    "Stands on the ground. Centred in X and Y, base at Z=0":
        "Posé au sol. Centré en X et Y, base à Z=0",
    "Hangs on a wall. Centred in X and Z, back at Y=0":
        "Accroché au mur. Centré en X et Z, dos à Y=0",
    "Cut into a wall. Centred on all three axes":
        "Percé dans un mur. Centré sur les trois axes",
    "No origin rule enforced, geometry checks still run":
        "Aucune règle d'origine appliquée, les autres contrôles tournent",
    "Floor item": "Objet au sol",
    "Wall item": "Objet mural",
    "Window / door": "Fenêtre / porte",
    "Other / undocumented": "Autre / non documenté",
    "The mesh is flat or empty": "Le mesh est plat ou vide",
    "  looks too large, check your unit scale":
        "  semble trop grand, vérifie l'échelle",
    "  looks too small, check your unit scale":
        "  semble trop petit, vérifie l'échelle",
    "confirmed by eye against the viewport arrow":
        "confirmé à l'oeil avec la flèche de la vue",
    "No reliable way to detect this automatically. Check the green arrow in "
    "the viewport, then confirm":
        "Impossible à détecter de façon fiable. Regarde la flèche verte dans "
        "la vue, puis confirme",
    "It faces the arrow": "Il suit la flèche",
    "No colour attribute. The item will have a single zone unless you supply "
    "a ColorZone texture":
        "Aucun attribut de couleur. L'objet n'aura qu'une zone, sauf si tu "
        "fournis une texture ColorZone",
    "Create zone 0 (white)": "Créer la zone 0 (blanc)",
    "Colours outside the legal set: ": "Couleurs hors de la liste légale : ",
    ". Only white, red, green, blue and yellow are read":
        ". Seuls le blanc, le rouge, le vert, le bleu et le jaune sont lus",
    "Snap to nearest zone": "Aligner sur la zone la plus proche",
    "{0} zones found, Build Mode allows {1}":
        "{0} zones trouvées, le Build Mode en accepte {1}",
    "{0}/{1} used, but no attribute on: {2}":
        "{0}/{1} utilisées, mais aucun attribut sur : {2}",
    "{0}/{1} used ({2})": "{0}/{1} utilisées ({2})",
    "zone {0}": "zone {0}",
    "decal": "décalque",
    "none": "aucune",
    "At least one object has no UV map, textures cannot be applied":
        "Au moins un objet n'a pas de carte UV, les textures ne peuvent pas "
        "s'appliquer",
    "UV1 present, UV2 present (deformations)":
        "UV1 présente, UV2 présente (déformations)",
    "UV1 present": "UV1 présente",

    # -- The transform the material puts in front of its textures -----------
    "The material moves them ({0}); the export bakes that into the UVs":
        "Le matériau les déplace ({0}) ; l'export cuit ce déplacement dans "
        "les UV",
    "scale {0:.3g} x {1:.3g}, offset {2:.3g} / {3:.3g}":
        "échelle {0:.3g} x {1:.3g}, décalage {2:.3g} / {3:.3g}",
    "{0} cannot be carried over: {1}. Bake the selection into one atlas to "
    "fix it for good":
        "{0} ne peut pas être transmise : {1}. Cuis la sélection dans un "
        "atlas unique pour régler ça définitivement",
    "The textures are not all placed the same way ({0}). Only one placement "
    "can be exported, so bake the selection into one atlas":
        "Les textures ne sont pas toutes placées pareil ({0}). Un seul "
        "placement peut être exporté, donc cuis la sélection dans un atlas "
        "unique",
    "Bake into one atlas": "Cuire dans un atlas unique",
    "its Mapping node is driven by another node":
        "son nœud Mapping est piloté par un autre nœud",
    "its Mapping node rotates outside the UV plane":
        "son nœud Mapping tourne hors du plan UV",
    "its Mapping node scales the texture to nothing":
        "son nœud Mapping réduit la texture à néant",
    "its Mapping node is set to {0}": "son nœud Mapping est réglé sur {0}",
    "its coordinates loop back on themselves":
        "ses coordonnées bouclent sur elles-mêmes",
    "it is projected with {0} coordinates, which live only in Blender":
        "elle est projetée avec des coordonnées {0}, qui n'existent que dans "
        "Blender",
    "its coordinates come from an attribute the mesh does not carry":
        "ses coordonnées viennent d'un attribut que le mesh ne porte pas",
    "its coordinates pass through a {0} node, which only Blender can run":
        "ses coordonnées passent par un nœud {0}, que seul Blender sait "
        "exécuter",

    "{0} triangles after triangulation": "{0} triangles après triangulation",
    " over your {0} budget. Paralives publishes no official limit, this is "
    "your own setting":
        " au-dessus de ton budget de {0}. Paralives ne publie aucune limite "
        "officielle, c'est ton propre réglage",
    "{0} faces with more than 4 sides. They will be triangulated on export, "
    "which can shade badly":
        "{0} faces de plus de 4 côtés. Elles seront triangulées à l'export, "
        "ce qui peut mal ombrer",
    "quads and triangles only": "uniquement des quads et des triangles",
    "No image found in the materials. The item will need a surface built "
    "from existing game textures":
        "Aucune image dans les matériaux. L'objet devra utiliser une surface "
        "faite de textures du jeu",
    "Pick a .mod folder, or create one from the game's Modding Tools first":
        "Choisis un dossier .mod, ou crées-en un depuis les outils de modding "
        "du jeu",
    "Folder does not exist: ": "Le dossier n'existe pas : ",
    "Folder name does not end with .mod, the game may ignore it":
        "Le nom du dossier ne finit pas par .mod, le jeu risque de l'ignorer",

    # -- Texture roles ----------------------------------------------------
    "Base colour": "Couleur de base",
    "Normal map": "Normal map",
    "Ambient occlusion": "Occlusion ambiante",
    "Roughness": "Rugosité",
    "Glossiness": "Brillance",
    "Metallic": "Métallique",
    "Packed ORM": "ORM empaqueté",
    "Emission": "Émission",
    "Opacity": "Opacité",
    "Unknown": "Inconnu",
    "Already named for Paralives": "Déjà nommé pour Paralives",

    # -- Texture panel ----------------------------------------------------
    "Auto-detect": "Détection auto",
    "Set the role by hand": "Définir le rôle à la main",
    "Assign a role": "Attribuer un rôle",
    "No image in the materials": "Aucune image dans les matériaux",
    "Will be written": "Sera écrit",
    "copied": "copié",
    "rebuilt": "reconstruit",
    "from ": "depuis ",
    "no suffix, will not auto configure":
        "aucun suffixe, pas de configuration automatique",
    "Sources": "Sources",
    "Nothing to detect": "Rien à détecter",
    "{0} texture(s), all roles recognised":
        "{0} texture(s), tous les rôles reconnus",
    "No recognised role on: ": "Aucun rôle reconnu sur : ",
    ". Run Auto-detect, or set the role by hand":
        ". Lance la détection auto, ou définis le rôle à la main",
    "More than one ": "Plus d'une carte ",
    " map. The game allows one": ". Le jeu n'en accepte qu'une",
    "Several materials carry their own maps. Paralives assigns one surface "
    "per mesh, so bake them into one atlas or split the item into several "
    "meshes":
        "Plusieurs matériaux ont leurs propres cartes. Paralives attribue une "
        "surface par mesh, donc bake-les en un seul atlas ou sépare l'objet "
        "en plusieurs meshes",
    "Metallic and emission maps are dropped, Paralives has no channel for "
    "them":
        "Les cartes métallique et émission sont ignorées, Paralives n'a pas "
        "de canal pour elles",
    "Smoothness is rebuilt as 1 - roughness":
        "La Smoothness est reconstruite en 1 - rugosité",
    "Occlusion is packed into the alpha of the normal map":
        "L'occlusion est empaquetée dans l'alpha de la normal map",
    "A saturated base colour becomes a Detail map, a gray one becomes a "
    "GrayMask":
        "Une couleur de base saturée devient une carte Detail, une couleur "
        "grise devient un GrayMask",

    # -- Zones panel ------------------------------------------------------
    "Paint": "Peindre",
    "Decal": "Décalque",
    "Select faces in Edit Mode, then click a zone":
        "Sélectionne des faces en mode Édition, puis clique une zone",
    "The whole mesh will be painted": "Tout le mesh sera peint",
    "From materials": "Depuis les matériaux",
    "Each material slot becomes a zone, in order. The quickest route for an "
    "imported or generated asset.":
        "Chaque slot de matériau devient une zone, dans l'ordre. La voie la "
        "plus rapide pour un asset importé ou généré.",
    "Zones from materials": "Zones depuis les matériaux",
    "From the texture": "Depuis la texture",
    "For an asset with a single baked texture and no zones at all. The "
    "texture is read directly, lighting cannot shift it.":
        "Pour un asset avec une seule texture bakée et aucune zone. La "
        "texture est lue directement, l'éclairage ne la fausse pas.",
    "Pick a colour on the model": "Pipette sur le modèle",
    "Assign to zone ": "Attribuer à la zone ",
    "Press F9 afterwards to tune the tolerance live":
        "Appuie sur F9 ensuite pour ajuster la tolérance en direct",
    "Reset to zone 0": "Tout remettre en zone 0",

    # -- Orientation panel ------------------------------------------------
    "The green arrow in the viewport points at Y+. The front of the item "
    "must look the same way.":
        "La flèche verte dans la vue pointe vers Y+. L'avant de l'objet doit "
        "regarder dans le même sens.",
    "Confirmed": "Confirmé",
    "Confirm the item faces Y+": "Confirmer que l'objet regarde Y+",

    # -- Options panel ----------------------------------------------------
    "Fixed by the Paralives spec:": "Imposé par la spec Paralives :",
    "Forward {0}, Up {1}": "Avant {0}, Haut {1}",
    "Vertex colours exported (sRGB)": "Couleurs de sommets exportées (sRGB)",
    "Tangents exported for normal maps":
        "Tangentes exportées pour les normal maps",
    "PNG only, the game rejects other formats":
        "PNG uniquement, le jeu refuse les autres formats",
    "Triangulate on export": "Trianguler à l'export",
    "Export textures": "Exporter les textures",
    "Overwrite existing files": "Écraser les fichiers existants",
    "Swatch group": "Groupe de swatches",
    "Write the recipe file": "Écrire la fiche recette",

    # -- Viewport panel ---------------------------------------------------
    "Viewport checklist": "Checklist dans la vue",
    "Grid": "Grille",
    "Bounding box": "Boîte englobante",
    "Facing arrow": "Flèche d'orientation",
    "Seat guide": "Repère d'assise",
    "Person for scale": "Silhouette d'échelle",
    "Their height": "Sa taille",
    "A Para sized outline standing next to the item. The game's own body "
    "meshes assemble to 1.702 m, so that is the default rather than a round "
    "1.80":
        "Une silhouette à la taille d'un Para, debout à côté de l'objet. Les "
        "meshes de corps du jeu s'assemblent à 1,702 m, c'est donc la valeur "
        "par défaut plutôt qu'un 1,80 rond",
    "In metres. The game's own Para is 1.702":
        "En mètres. Le Para du jeu mesure 1,702",
    "Seat height": "Hauteur d'assise",
    "Resize handles": "Poignées de redimensionnement",
    "A Para sits on this one, so both handles are left out. Resizing moves "
    "the seat out of reach and nobody sits down.":
        "Un Para s'assoit dessus, les deux poignées sont donc omises. "
        "Redimensionner éloigne l'assise hors de portée et plus personne ne "
        "s'assoit.",
    "Left out, because a Para sits on this one. Of the game's 29 items with a "
    "chair slot not one is resizable, and of its 29 counters, where the Para "
    "stands beside instead, all 29 are":
        "Omises, parce qu'un Para s'assoit dessus. Sur les 29 objets du jeu "
        "avec un slot de chaise, aucun n'est redimensionnable, et sur ses 29 "
        "comptoirs, où le Para se tient à côté, les 29 le sont",
    "{0:.3f} m, {1:.0f}% of the height, over {2:.2f} m2":
        "{0:.3f} m, {1:.0f}% de la hauteur, sur {2:.2f} m2",
    ". Chair height: the game's sit at {0:.2f}":
        ". Hauteur de chaise : celles du jeu sont à {0:.2f}",
    ". Stool height: the game's sit at {0:.2f}":
        ". Hauteur de tabouret : ceux du jeu sont à {0:.2f}",
    ". Lower than anything the game seats a Para on, so they will sink into "
    "it. Its lowest is around {0:.2f}":
        ". Plus bas que tout ce sur quoi le jeu assoit un Para, il s'y "
        "enfoncera donc. Le plus bas du jeu est vers {0:.2f}",
    ". Higher than anything the game seats a Para on, so they will float. "
    "Its tallest is a stool at {0:.2f}":
        ". Plus haut que tout ce sur quoi le jeu assoit un Para, il flottera "
        "donc. Le plus haut du jeu est un tabouret à {0:.2f}",
    "No flat surface clear of the floor, so there is nothing to sit on. {0} "
    "will still seat a Para, in mid air":
        "Aucune surface plane dégagée du sol, donc rien où s'asseoir. {0} y "
        "placera quand même un Para, en plein air",
    "Nothing to sit on": "Rien où s'asseoir",
    "Sits at {0:.3f} m, facing the arrow":
        "Assise à {0:.3f} m, face à la flèche",
    "Which way round": "Sens de l'objet",
    "Turn it around": "Faire demi-tour",
    "Nothing stands above the seat, so there is no back to put the wrong way. "
    "A Para sits facing Y+, along the arrow":
        "Rien ne dépasse au-dessus de l'assise, il n'y a donc pas de dossier à "
        "mettre à l'envers. Un Para s'assoit vers Y+, dans le sens de la flèche",
    "The back is on the Y- side, where 43 of the game's 48 chairs put theirs. "
    "A Para sits facing the arrow":
        "Le dossier est du côté Y-, là où 43 des 48 chaises du jeu mettent le "
        "leur. Un Para s'assoit face à la flèche",
    "The back is on the Y+ side, facing the arrow. A Para will sit down and "
    "face their own backrest. Turn the item half a turn":
        "Le dossier est du côté Y+, face à la flèche. Un Para s'assoira et "
        "regardera son propre dossier. Fais faire un demi-tour à l'objet",
    "Grid tiles": "Tuiles de grille",
    "Checklist corner": "Coin de la checklist",
    "Top left": "En haut à gauche",
    "Top right": "En haut à droite",
    "Bottom left": "En bas à gauche",
    "Bottom right": "En bas à droite",
    "Nudge X": "Décalage X",
    "Nudge Y": "Décalage Y",
    "Only problems": "Seulement les problèmes",
    "Everything is green": "Tout est au vert",
    "The checklist dodges the toolbar and the sidebar on its own":
        "La checklist évite d'elle-même la barre d'outils et le panneau latéral",

    # -- Calibration ------------------------------------------------------
    "Tile size": "Taille d'une tuile",
    "Triangle budget": "Budget de triangles",

    # -- Inspector --------------------------------------------------------
    "Find out whether item definitions can be generated. Snapshot the mod, "
    "create one item in the game, quit, then diff.":
        "Vérifie si les définitions d'objets sont générables. Prends un "
        "instantané du mod, crée un objet dans le jeu, quitte, puis compare.",
    "Snapshot mod folder": "Instantané du dossier mod",
    "Diff since snapshot": "Comparer avec l'instantané",

    # -- Operator reports -------------------------------------------------
    "Nothing selected": "Rien de sélectionné",
    "Blocked by: ": "Bloqué par : ",
    "Folder not found": "Dossier introuvable",
    "Unit scale set to 1.0": "Échelle des unités mise à 1.0",
    "Rotation and scale applied": "Rotation et échelle appliquées",
    "Blender refused to apply the transforms":
        "Blender a refusé d'appliquer les transformations",
    "Mesh data is shared with another object: ":
        "Les données du mesh sont partagées avec un autre objet : ",
    ". Make it single user first": ". Rends-les mono-utilisateur d'abord",
    "Could not apply transforms first":
        "Impossible d'appliquer les transformations d'abord",
    "No geometry to measure": "Aucune géométrie à mesurer",
    "Origin already correct": "Origine déjà correcte",
    "Geometry moved by ({0:+.4f}, {1:+.4f}, {2:+.4f}) m":
        "Géométrie déplacée de ({0:+.4f}, {1:+.4f}, {2:+.4f}) m",
    "Rotated by {0} degrees": "Tourné de {0} degrés",
    "Every object already has a colour attribute":
        "Chaque objet a déjà un attribut de couleur",
    "Zone 0 created on {0} object(s)": "Zone 0 créée sur {0} objet(s)",
    "{0} colour value(s) snapped": "{0} valeur(s) de couleur alignée(s)",
    "Nothing left that can be fixed automatically":
        "Plus rien à corriger automatiquement",
    "Applied: ": "Appliqué : ",
    "{0} corner(s) set to {1}": "{0} coin(s) mis en {1}",
    "No face selected. Select faces in Edit Mode first":
        "Aucune face sélectionnée. Sélectionne des faces en mode Édition",
    "No material slot to map": "Aucun slot de matériau à mapper",
    "{0} materials for {1} zones. The extra ones fall back to zone {1}":
        "{0} matériaux pour {1} zones. Les surplus retombent sur la zone {1}",
    "{0} material slot(s) mapped to zones":
        "{0} slot(s) de matériau mappés en zones",
    "Nothing under the cursor": "Rien sous le curseur",
    "That object has no image texture to sample":
        "Cet objet n'a aucune image à échantillonner",
    "Could not read the pixels of ": "Impossible de lire les pixels de ",
    "That object has no UV map": "Cet objet n'a pas de carte UV",
    "Sampled {0} at ({1:.3f}, {2:.3f})":
        "Échantillonné {0} en ({1:.3f}, {2:.3f})",
    "No UV map on: ": "Aucune carte UV sur : ",
    ". Unwrap before sampling a texture":
        ". Déplie les UV avant d'échantillonner une texture",
    "No texture to sample. Pick a colour first":
        "Aucune texture à échantillonner. Prends d'abord une couleur",
    "{0:.1f}% of the surface assigned to zone {1}":
        "{0:.1f}% de la surface attribuée à la zone {1}",
    "Click the model to sample its texture   |   Esc or right click to cancel":
        "Clique le modèle pour lire sa texture   |   Échap ou clic droit pour "
        "annuler",
    "Pick a valid mod folder first": "Choisis d'abord un dossier mod valide",
    "{0} file(s) recorded to {1}": "{0} fichier(s) enregistrés dans {1}",
    "No snapshot for this mod yet": "Aucun instantané pour ce mod",
    "{0} added, {1} modified, {2} removed. Report in the Text Editor and at "
    "{3}":
        "{0} ajouté(s), {1} modifié(s), {2} supprimé(s). Rapport dans "
        "l'éditeur de texte et dans {3}",
    "{0} file(s) in {1:.0f} ms: {2}{3}":
        "{0} fichier(s) en {1:.0f} ms : {2}{3}",
    "Image not found: ": "Image introuvable : ",
    "Role set to ": "Rôle défini sur ",
    "{0} image(s) identified, {1} left unknown":
        "{0} image(s) identifiées, {1} sans rôle",
    "Language set to {0}, reloading": "Langue réglée sur {0}, rechargement",
    "The target is outside the detected Paralives folder":
        "La cible est en dehors du dossier Paralives détecté",
    "{0} has no known suffix, Paralives will not auto configure it":
        "{0} n'a pas de suffixe connu, Paralives ne le configurera pas "
        "automatiquement",
    "Could not write {0}: {1}": "Impossible d'écrire {0} : {1}",
    "Could not write the recipe: {0}":
        "Impossible d'écrire la fiche recette : {0}",
    "{0} is too large to rebuild ({1} x {2})":
        "{0} est trop grande pour être reconstruite ({1} x {2})",

    # -- Preferences ------------------------------------------------------
    "Paralives mods folder": "Dossier des mods Paralives",
    "Asset subfolder": "Sous-dossier des assets",
    "Open the folder after export": "Ouvrir le dossier après l'export",
    "Warn when writing outside the mods folder":
        "Alerter en cas d'écriture hors du dossier des mods",
    "{0} mod folder(s) found": "{0} dossier(s) .mod trouvé(s)",
    "Create a mod once from the game's Modding Tools, then detect again":
        "Crée un mod une fois depuis les outils de modding du jeu, puis "
        "relance la détection",
    "Not found. Tried: ": "Introuvable. Essayé : ",
    "Found ": "Trouvé ",

    # -- Operator labels and tooltips -------------------------------------
    "Set unit scale to 1.0": "Mettre l'échelle des unités à 1.0",
    "Paralives works in metres at scale 1.0":
        "Paralives travaille en mètres à l'échelle 1.0",
    "Bake rotation and scale into the mesh data. Without this the item "
    "arrives in game at the wrong angle or size":
        "Fige la rotation et l'échelle dans les données du mesh. Sans ça "
        "l'objet arrive en jeu au mauvais angle ou à la mauvaise taille",
    "Move the geometry so the origin follows the Paralives rule for this "
    "item type":
        "Déplace la géométrie pour que l'origine suive la règle Paralives de "
        "ce type d'objet",
    "There is no reliable way to detect the front of a mesh. Compare the "
    "item with the green arrow in the viewport, then confirm":
        "Il n'y a pas de moyen fiable de détecter l'avant d'un mesh. Compare "
        "l'objet avec la flèche verte dans la vue, puis confirme",
    "Rotate 90 degrees": "Tourner de 90 degrés",
    "Turn the geometry a quarter turn around Z, then re-check":
        "Fait pivoter la géométrie d'un quart de tour autour de Z, puis "
        "recontrôle",
    "Rotation": "Rotation",
    "Quarter turn counter clockwise": "Quart de tour dans le sens antihoraire",
    "Half turn": "Demi-tour",
    "Quarter turn clockwise": "Quart de tour dans le sens horaire",
    "Create colour attribute": "Créer l'attribut de couleur",
    "Add a colour attribute filled with zone 0 (white) so the item has a "
    "valid single zone to start from":
        "Ajoute un attribut de couleur rempli en zone 0 (blanc) pour que "
        "l'objet parte d'une zone unique valide",
    "Snap colours to the nearest zone":
        "Aligner les couleurs sur la zone la plus proche",
    "Round every vertex colour to the nearest legal Paralives zone. Anything "
    "the game cannot read becomes the closest zone it can":
        "Arrondit chaque couleur de sommet vers la zone Paralives légale la "
        "plus proche. Tout ce que le jeu ne sait pas lire devient la zone la "
        "plus proche possible",
    "Work out what every texture is from the shader graph, the file name and "
    "the pixels, then remember it. A GLB downloaded from the web arrives "
    "with its images called Image_0 and Image_1, so what they are wired to "
    "is the only reliable clue":
        "Déduit ce qu'est chaque texture à partir du graphe de shader, du nom "
        "de fichier et des pixels, puis le retient. Un GLB téléchargé sur le "
        "web arrive avec ses images nommées Image_0 et Image_1, donc leur "
        "branchement est le seul indice fiable",
    "Tell ParaForge what this image is, so it can be folded into the right "
    "Paralives map":
        "Indique à ParaForge ce qu'est cette image, pour qu'elle soit versée "
        "dans la bonne carte Paralives",
    "Role": "Rôle",
    "Reduce to the budget": "Réduire au budget",
    "Collapse edges until the mesh fits the triangle budget. Downloaded and "
    "generated assets routinely arrive at half a million triangles, which no "
    "furniture item needs":
        "Fusionne des arêtes jusqu'à rentrer dans le budget de triangles. Les "
        "assets téléchargés ou générés arrivent couramment à un demi-million "
        "de triangles, ce dont aucun meuble n'a besoin",
    "Already under the budget": "Déjà sous le budget",

    # -- Creating a mod ---------------------------------------------------
    "New mod": "Nouveau mod",
    "Show every check": "Afficher tous les contrôles",
    "Twelve green boxes push the buttons off the bottom of the panel. "
    "Folded, only what still needs attention is listed":
        "Douze cadres verts poussent les boutons hors du panneau. Replié, "
        "seul ce qui demande encore de l'attention est listé",
    "Step 1 first: the mesh is not in the mod yet":
        "L'étape 1 d'abord : le mesh n'est pas encore dans le mod",
    "Mod name": "Nom du mod",
    "Becomes the folder name, and the name in the game":
        "Devient le nom du dossier, et le nom dans le jeu",
    "Create an empty mod folder and select it. A mod is a folder and a "
    "manifest, so the game does not have to be launched to make one. Use this "
    "rather than Local.mod, which is the game's own scratch folder and cannot "
    "be uploaded to the Workshop":
        "Crée un dossier de mod vide et le sélectionne. Un mod, c'est un "
        "dossier et un manifeste, donc pas besoin de lancer le jeu pour en "
        "faire un. À utiliser plutôt que Local.mod, qui est le bac à sable du "
        "jeu et ne peut pas être publié sur le Workshop",
    "{0} created": "{0} créé",
    "{0} already existed, selected it": "{0} existait déjà, sélectionné",
    "Paralives folder not found. Run the game once, or set the folder in the "
    "add-on preferences":
        "Dossier Paralives introuvable. Lance le jeu une fois, ou renseigne le "
        "dossier dans les préférences de l'extension",
    "This is one of the game's own folders. It works for trying things out, "
    "but it cannot be uploaded to the Workshop. Press + for a mod of your "
    "own.":
        "C'est un dossier du jeu lui-même. Ça marche pour essayer, mais ça ne "
        "peut pas être publié sur le Workshop. Appuie sur + pour ton propre "
        "mod.",

    # -- Item generation --------------------------------------------------
    "Create the item in the catalogue": "Créer l'objet dans le catalogue",
    "Write the prefab and register the item in the mod, so it appears in "
    "Build Mode without opening the Control Panel. Only files inside the "
    "target .mod are touched, and every change can be undone":
        "Écrit le prefab et enregistre l'objet dans le mod, pour qu'il "
        "apparaisse en Build Mode sans ouvrir le Control Panel. Seuls les "
        "fichiers du .mod ciblé sont touchés, et tout est annulable",
    "Undo the last write": "Annuler la dernière écriture",
    "Put the mod back exactly as it was before the last item was generated: "
    "created files are removed, edited ones are restored from the copy taken "
    "beforehand. Press again to step back further":
        "Remet le mod exactement dans l'état d'avant la dernière génération : "
        "les fichiers créés sont supprimés, ceux modifiés sont restaurés "
        "depuis la copie prise avant. Appuie encore pour remonter plus loin",
    "Nothing to undo in this mod": "Rien à annuler dans ce mod",
    "{0} undone: {1} file(s) removed, {2} restored":
        "{0} annulé : {1} fichier(s) supprimé(s), {2} restauré(s)",
    "{0} is in the catalogue. Restart Paralives to see it":
        "{0} est dans le catalogue. Relance Paralives pour le voir",
    "{0} already had this item, left alone":
        "{0} contenait déjà cet objet, laissé tel quel",
    "Export the mesh first, {0} is not in the mod folder":
        "Exporte d'abord le mesh, {0} n'est pas dans le dossier du mod",
    "No swatch group called {0} in the game, the item is written without one":
        "Aucun groupe de swatches nommé {0} dans le jeu, l'objet est écrit "
        "sans",
    "Never inside the game installation":
        "Jamais dans l'installation du jeu",
    "Custom": "Personnalisé",
    "Type the tag by hand": "Saisir le tag à la main",
    "Catalogue read from game build {0}":
        "Catalogue lu dans la build {0} du jeu",
    "Measured on {0} meshes taken from the game itself: {1} triangles in the "
    "median, {2} at the very most. The budget below is that maximum, and it "
    "is only a warning.":
        "Mesuré sur {0} meshes pris dans le jeu lui-même : {1} triangles en "
        "médiane, {2} au grand maximum. Le budget ci-dessous est ce maximum, "
        "et ce n'est qu'une alerte.",
    "Texture size": "Taille des textures",
    "largest is {0} px": "la plus grande fait {0} px",
    "{0} is {1} px. Paralives ships 256 to 1024, and nothing above {2}. "
    "Downscaling costs nothing visible on an item this size":
        "{0} fait {1} px. Paralives livre du 256 au 1024, et rien au-dessus "
        "de {2}. Réduire ne coûte rien de visible sur un objet de cette "
        "taille",
    "Downscale to {0} px": "Réduire à {0} px",
    "Downscale the textures": "Réduire les textures",
    "Halve oversized textures until they fit. Paralives ships 256 to 1024 px "
    "maps and nothing above 2048, so a 4K download is four times the largest "
    "texture in the game for no visible gain":
        "Divise par deux les textures trop grandes jusqu'à ce qu'elles "
        "rentrent. Paralives livre des cartes de 256 à 1024 px et rien "
        "au-dessus de 2048, donc un téléchargement en 4K fait quatre fois la "
        "plus grande texture du jeu sans rien apporter de visible",
    "Longest side": "Plus grand côté",
    "Every texture already fits": "Chaque texture rentre déjà",
    "{0} texture(s) downscaled to {1} px":
        "{0} texture(s) réduite(s) à {1} px",
    "No Detail or GrayMask map, the item will have no colour of its own":
        "Aucune carte Detail ni GrayMask, l'objet n'aura pas de couleur "
        "propre",
    "Write the .meta files": "Écrire les fichiers .meta",
    "Write the sidecar the game keeps beside every asset, with the import "
    "settings already filled in. Read back from the game's own mod folder, so "
    "the import stops depending on the file name being parsed correctly":
        "Écrit le fichier compagnon que le jeu garde à côté de chaque asset, "
        "avec les réglages d'import déjà remplis. Relevé dans le dossier de "
        "mod du jeu lui-même, donc l'import ne dépend plus de la lecture "
        "correcte du nom de fichier",
    "That folder is inside the Paralives installation ({0}). Assets belong in "
    "a mod under AppData, or a game update will wipe them and they cannot be "
    "shared":
        "Ce dossier est dans l'installation de Paralives ({0}). Les assets "
        "vont dans un mod sous AppData, sinon une mise à jour du jeu les "
        "effacera et ils ne pourront pas être partagés",
    "Bake into one surface": "Fusionner en une seule surface",
    "Repack the UVs of the whole selection into one atlas, bake every "
    "material into a single set of maps, and replace them with it. This is "
    "the way out for a downloaded asset split into five or ten materials, "
    "because Paralives assigns one surface per mesh. It uses Cycles and "
    "takes a while":
        "Repaquette les UV de toute la sélection dans un atlas, bake chaque "
        "matériau dans un jeu de cartes unique, et les remplace par lui. "
        "C'est la sortie de secours pour un asset téléchargé découpé en cinq "
        "ou dix matériaux, puisque Paralives attribue une surface par mesh. "
        "Ça passe par Cycles et ça prend un moment",
    "Resolution": "Résolution",
    "Samples": "Échantillons",
    "Only the occlusion pass is noisy, the others are exact whatever this is "
    "set to":
        "Seule la passe d'occlusion est bruitée, les autres sont exactes quel "
        "que soit ce réglage",
    "The materials of the selection are replaced by a single one. The look is "
    "preserved, the UVs are not: they are repacked into one atlas":
        "Les matériaux de la sélection sont remplacés par un seul. Le rendu "
        "est préservé, les UV non : ils sont repaquetés dans un atlas",
    "{0} map(s) baked into one surface at {1} px":
        "{0} carte(s) bakée(s) en une seule surface en {1} px",
    "Every object needs at least one material to bake":
        "Chaque objet a besoin d'au moins un matériau pour être baké",
    "{0} materials, so {1} sets of maps. Paralives gives one surface to one "
    "mesh: bake them together, or split the item into one mesh per material":
        "{0} matériaux, donc {1} jeux de cartes. Paralives donne une surface "
        "par mesh : fusionne-les, ou découpe l'objet en un mesh par matériau",
    "{0} triangles, down from {1}": "{0} triangles, contre {1} avant",
    "Run every fix that cannot lose work: unit scale, transforms, origin, "
    "missing colour attribute, illegal colours and texture roles. Facing and "
    "triangle reduction still need you":
        "Applique toutes les corrections sans perte : échelle, "
        "transformations, origine, attribut de couleur manquant, couleurs "
        "illégales et rôles de texture. L'orientation et la réduction de "
        "triangles restent à ta main",
    "Write the FBX and its textures into the selected .mod folder, with the "
    "axes, naming and settings Paralives expects":
        "Écrit le FBX et ses textures dans le dossier .mod choisi, avec les "
        "axes, le nommage et les réglages attendus par Paralives",
    "Export even though checks are failing":
        "Exporter malgré les contrôles en échec",
    "Open the target folder in the file browser":
        "Ouvre le dossier cible dans l'explorateur de fichiers",
    "Re-run every check now": "Relance tous les contrôles maintenant",
    "Switch the whole add-on between French and English":
        "Bascule toute l'extension entre le français et l'anglais",
    "Record the exact contents of the mod folder. Quit the game first, then "
    "create one item inside it, then run the diff":
        "Enregistre le contenu exact du dossier mod. Quitte le jeu d'abord, "
        "crée un objet dedans, puis lance la comparaison",
    "Compare the mod folder with the last snapshot and open a report showing "
    "exactly what the game wrote":
        "Compare le dossier mod avec le dernier instantané et ouvre un "
        "rapport montrant exactement ce que le jeu a écrit",
    "Look for the Paralives mods folder in the usual location":
        "Cherche le dossier des mods Paralives à l'emplacement habituel",
    "Assign zone": "Attribuer une zone",
    "Paint the selected faces with a Paralives colour zone":
        "Peint les faces sélectionnées avec une zone de couleur Paralives",
    "Ignore the selection and paint everything":
        "Ignore la sélection et peint tout",
    "Turn each material slot into a colour zone. The fastest route for an "
    "imported or generated asset that already has separate materials":
        "Transforme chaque slot de matériau en zone de couleur. La voie la "
        "plus rapide pour un asset importé ou généré qui a déjà des matériaux "
        "séparés",
    "Click the model to read the texture colour under the cursor. The "
    "texture is sampled directly, so viewport lighting does not shift it":
        "Clique le modèle pour lire la couleur de texture sous le curseur. La "
        "texture est lue directement, l'éclairage de la vue ne la fausse pas",
    "Grow zone from colour": "Étendre la zone depuis une couleur",
    "Assign every part of the mesh whose texture colour is close to the "
    "picked one. Adjust the tolerance in the redo panel to see it change":
        "Attribue toute la partie du mesh dont la couleur de texture est "
        "proche de celle prélevée. Ajuste la tolérance dans le panneau de "
        "reprise pour voir le résultat évoluer",
    "Paint the whole mesh white, the single zone default":
        "Peint tout le mesh en blanc, la zone unique par défaut",
    "0 matches that exact colour, 1 matches the whole texture":
        "0 ne prend que cette couleur exacte, 1 prend toute la texture",
    "Everything else to zone 0": "Tout le reste en zone 0",
    "Reset the rest to zone 0": "Remettre le reste en zone 0",
    "Reset the rest of the mesh to white before assigning":
        "Remet le reste du mesh en blanc avant l'attribution",
    "No 3D view under the cursor": "Aucune vue 3D sous le curseur",
    "Colour": "Couleur",
    "Texture": "Texture",
    "Zone": "Zone",
    "Red": "Rouge",
    "Green": "Vert",
    "Blue": "Bleu",
    "White. Usually carries the Detail map":
        "Blanc. Porte en général la carte Detail",
    "White, usually the Detail map": "Blanc, en général la carte Detail",
    "Yellow. Never recolourable": "Jaune. Jamais recolorable",
    "Yellow, never recolourable": "Jaune, jamais recolorable",
    "Whole mesh": "Tout le mesh",

    # -- Property tooltips ------------------------------------------------
    "Decides which origin rule is enforced":
        "Détermine quelle règle d'origine est appliquée",
    "Base name for the exported files. Leave empty to use the object name. "
    "Textures become <Name><Suffix>.png":
        "Nom de base des fichiers exportés. Laisse vide pour reprendre le nom "
        "de l'objet. Les textures deviennent <Nom><Suffixe>.png",
    "Mod": "Mod",
    "Mod folders found in the Paralives data folder":
        "Dossiers de mod trouvés dans le dossier de données Paralives",
    "No .mod folder found": "Aucun dossier .mod trouvé",
    "Create one in the game first": "Crées-en un dans le jeu d'abord",
    "The .mod folder assets are written into":
        "Le dossier .mod dans lequel les assets sont écrits",
    "Facing confirmed": "Orientation confirmée",
    "You have checked the item faces the green Y+ arrow":
        "Tu as vérifié que l'objet regarde la flèche verte Y+",
    "Paralives publishes no official limit. This is your own ceiling, used "
    "for a warning only":
        "Paralives ne publie aucune limite officielle. C'est ton propre "
        "plafond, utilisé pour une simple alerte",
    "Size of one Paralives grid tile in metres. Calibrate it once by "
    "importing an official game mesh and measuring it":
        "Taille d'une tuile de la grille Paralives en mètres. Calibre-la une "
        "fois en important un mesh officiel du jeu et en le mesurant",
    "Where the item belongs in Build Mode. Paralives sets the base price "
    "from the Item Tag, so this has to match what you pick in the Control "
    "Panel":
        "Où l'objet se range dans le Build Mode. Paralives fixe le prix de "
        "base à partir de l'Item Tag, donc ça doit correspondre à ce que tu "
        "choisis dans le Control Panel",
    "Used when the catalog is set to Custom":
        "Utilisé quand le catalogue est réglé sur Custom",
    "Swatch group to assign in the Control Panel, for example BasicWood. One "
    "mesh plus a swatch group gives many colourways without duplicating "
    "geometry":
        "Groupe de swatches à assigner dans le Control Panel, par exemple "
        "BasicWood. Un mesh plus un groupe de swatches donne des dizaines de "
        "coloris sans dupliquer la géométrie",
    "Save a short text file listing every value to enter in the Control "
    "Panel for this item":
        "Enregistre un court fichier texte listant chaque valeur à saisir "
        "dans le Control Panel pour cet objet",
    "Zone the next assignment writes":
        "Zone que la prochaine attribution écrira",
    "Picked colour": "Couleur prélevée",
    "Texture colour sampled from the model":
        "Couleur de texture prélevée sur le modèle",
    "How far from the picked colour still counts. 0 is that exact colour, 1 "
    "takes the whole texture":
        "Jusqu'où on s'éloigne de la couleur prélevée. 0 ne prend que cette "
        "couleur exacte, 1 prend toute la texture",
    "Image the colour match reads. Filled in by the picker":
        "Image que la correspondance de couleur lit. Remplie par la pipette",
    "Paint everything white before assigning the match":
        "Peint tout en blanc avant d'attribuer la correspondance",
    "Paint the entire mesh instead of the faces selected in Edit Mode":
        "Peint tout le mesh au lieu des faces sélectionnées en mode Édition",
    "Recolourable in game": "Recolorable en jeu",
    "Turn the base colour into a GrayMask so the player can recolour the "
    "item from a swatch. Leave it off to keep the texture exactly as it is, "
    "as a Detail map, which is what a downloaded or generated asset usually "
    "wants":
        "Transforme la couleur de base en GrayMask pour que le joueur puisse "
        "recolorer l'objet depuis un swatch. Laisse décoché pour garder la "
        "texture telle quelle, en carte Detail, ce que veut en général un "
        "asset téléchargé ou généré",
    "Triangulate in the FBX rather than leaving it to the engine":
        "Triangule dans le FBX plutôt que de laisser le moteur le faire",
    "Write the material textures next to the FBX, correctly named":
        "Écrit les textures du matériau à côté du FBX, correctement nommées",
    "Draw the grid, origin, facing arrow and bounding box":
        "Dessine la grille, l'origine, la flèche d'orientation et la boîte "
        "englobante",
    "Draw the checklist in the corner of the viewport":
        "Dessine la checklist dans un coin de la vue",
    "How many tiles to draw around the origin":
        "Combien de tuiles dessiner autour de l'origine",
    "Which corner of the viewport the checklist docks to":
        "Le coin de la vue auquel la checklist s'accroche",
    "Extra horizontal margin, in pixels":
        "Marge horizontale supplémentaire, en pixels",
    "Extra vertical margin, in pixels":
        "Marge verticale supplémentaire, en pixels",
    "Hide the checks that already pass, so the checklist shrinks to nothing "
    "once the asset is clean":
        "Masque les contrôles déjà au vert, pour que la checklist disparaisse "
        "une fois l'asset propre",
    "Folder holding the .mod directories. Leave empty to auto detect":
        "Dossier contenant les répertoires .mod. Laisse vide pour la "
        "détection automatique",
    "Optional subfolder inside the mod to write assets into. Leave empty to "
    "write at the root of the mod folder, which is what the official guide "
    "describes":
        "Sous-dossier optionnel dans le mod où écrire les assets. Laisse vide "
        "pour écrire à la racine du dossier mod, ce que décrit le guide "
        "officiel",

    # -- Source role descriptions -----------------------------------------
    "Albedo, diffuse or a fully baked texture":
        "Albédo, diffuse ou texture entièrement bakée",
    "Tangent space normals": "Normales en espace tangent",
    "Contact shadows, goes in the alpha":
        "Ombres de contact, va dans l'alpha",
    "Inverted to become Smoothness": "Inversée pour devenir la Smoothness",
    "Already the right way round for Smoothness":
        "Déjà dans le bon sens pour la Smoothness",
    "No Paralives channel, folded into Smoothness":
        "Aucun canal Paralives, reversée dans la Smoothness",
    "R occlusion, G roughness, B metallic":
        "R occlusion, G rugosité, B métallique",
    "No Paralives channel": "Aucun canal Paralives",
    "Copied through untouched": "Recopiée telle quelle",
    "Could not be identified": "N'a pas pu être identifiée",
    "the node graph": "le graphe de shader",
    "the file name": "le nom de fichier",
    "the pixels": "les pixels",

    # -- Recipe file ------------------------------------------------------
    "ParaForge recipe for: ": "Fiche recette ParaForge pour : ",
    "Written ": "Écrite le ",
    "Files written into the mod folder":
        "Fichiers écrits dans le dossier du mod",
    "UNKNOWN ROLE, the game will not auto configure it":
        "RÔLE INCONNU, le jeu ne le configurera pas automatiquement",
    "Values to enter in the Control Panel":
        "Valeurs à saisir dans le Control Panel",
    "Display name": "Nom affiché",
    "Item tag": "Item Tag",
    "Thumbnail type": "Type de vignette",
    "Steps, in order": "Étapes, dans l'ordre",
    "Reminders": "Rappels",
    "(not set)": "(non défini)",
    "(pick one)": "(à choisir)",
    "unknown": "inconnu",
    "Control Panel > Build > Items, click + next to All Items":
        "Control Panel > Build > Items, clique le + à côté de All Items",
    'Display name: "{0}", confirm the translation':
        'Display Name : "{0}", confirme la traduction',
    "Click the icon next to Prefab to create one, the Prefab Editor opens":
        "Clique l'icône à côté de Prefab pour en créer un, le Prefab Editor "
        "s'ouvre",
    "Select Root, click Add, search ItemMeshReference":
        "Sélectionne Root, clique Add, cherche ItemMeshReference",
    "Asset Mesh: pick {0}.fbx": "Asset Mesh : choisis {0}.fbx",
    "Click Set Edited Prefab Size to Mesh Size to fit the bounding box":
        "Clique Set Edited Prefab Size to Mesh Size pour caler la boîte "
        "englobante",
    "Assign the surface, then the Detail or ColorZone map if the item has "
    "one":
        "Assigne la surface, puis la carte Detail ou ColorZone si l'objet en "
        "a une",
    "Save, which returns you to the Items page":
        "Save, ce qui te ramène à la page Items",
    "Item Tag: {0}, this also sets the base price":
        "Item Tag : {0}, il fixe aussi le prix de base",
    "Swatch Group: {0}, then set the colour zone count":
        "Swatch Group : {0}, puis règle le nombre de zones de couleur",
    "Check it in Build Mode, then upload with the cloud icon":
        "Vérifie en Build Mode, puis publie avec l'icône nuage",
    "The game imports assets at launch, there is no hot reload. Restart "
    "Paralives after writing new files.":
        "Le jeu importe les assets au lancement, il n'y a pas de rechargement "
        "à chaud. Relance Paralives après avoir écrit de nouveaux fichiers.",
    "Detail and ColorZone maps are assigned in the Prefab Editor, not in the "
    "Surfaces panel.":
        "Les cartes Detail et ColorZone s'assignent dans le Prefab Editor, "
        "pas dans le panneau Surfaces.",
}

CATALOG = {"fr": FR}
