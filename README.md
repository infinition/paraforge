# ParaForge

Extension Blender qui prépare un asset pour le Build Mode de **Paralives** :
elle contrôle le mesh contre chaque règle du jeu, corrige ce qui peut l'être,
reconstruit les textures dans les cartes que le jeu lit vraiment, puis écrit le
FBX et ses PNG directement dans un dossier `.mod`. Le jeu n'a jamais besoin
d'être lancé.

Interface en **français par défaut**, anglais au choix.

Blender 4.2 ou plus. Testée sur Blender 5.2 LTS.

---

## Ce que Paralives attend

Le point le moins documenté, et celui qui coûte le plus d'allers-retours.
Paralives fait du **PBR sans canal metallic** : albédo, normal, occlusion,
smoothness. Le nom du fichier suffit à configurer l'import côté jeu, à
condition d'être exact.

| Suffixe | Contenu | Note |
|---|---|---|
| `GrayMask` | base recolorable, le gris 50 % est la teinte neutre | sRGB |
| `Detail` | couleur libre, non recolorable | une seule par objet |
| `NormalOcclusion` | normal map en **RGB**, occlusion dans l'**alpha** | données |
| `Smoothness` | **blanc = brillant**, noir = mat | données |
| `ColorZone` | carte de zones, pour les meshes sans vertex paint | données |
| `Master` | murs et sols : R GrayMask, G variante, B HueShift | sRGB |

Meshes en FBX ou OBJ, textures en **PNG uniquement**, `Z Forward` / `Y Up`,
objet tourné vers `Y+`, transformations appliquées. Origine : centrée en X/Y et
base à Z=0 au sol, centrée en X/Z et dos à Y=0 au mur, centrée sur les trois
axes pour une fenêtre. Quatre zones de couleur recolorables au maximum, plus le
jaune du décalque.

Sources : [Adding a Mesh for the Build Mode](https://paralives.wiki.gg/wiki/Adding_a_Mesh_for_the_Build_Mode),
[Adding Texture Assets to Create Surfaces](https://paralives.wiki.gg/wiki/Adding_Texture_Assets_to_Create_Surfaces),
[Creating an Item with Multiple Colors and Materials](https://paralives.wiki.gg/wiki/Creating_an_Item_with_Multiple_Colors_and_Materials).

Tout est rassemblé dans [`paraforge/spec.py`](paraforge/spec.py) : une mise à
jour du jeu ne devrait jamais demander de toucher un autre fichier.

## Un GLB téléchargé, converti tout seul

Un modèle pris sur le web n'arrive jamais au bon format. glTF donne de la
*roughness* là où le jeu veut de la *smoothness*, empaquette l'occlusion dans
le rouge d'une texture ORM, et gltfpack efface les noms d'images, si bien que
Blender les appelle `Image_0`, `Image_1`, `Image_2`.

ParaForge identifie chaque image par trois sources d'indices, la plus fiable
d'abord :

1. **le graphe de shader**, c'est-à-dire ce à quoi l'image est branchée. C'est
   un fait, pas une supposition, et c'est le seul indice quand les noms ont
   disparu ;
2. **le nom de fichier** : `_Diffuse`, `-ORM`, `_Normal`, `_BaseColor` ;
3. **les pixels** : une normal map est reconnaissable, et une texture sans
   couleur n'est jamais un albédo.

Puis elle reconstruit :

```
baseColor            -> Detail (copie exacte) ou GrayMask (désaturé, recentré sur 50 %)
normal + occlusion   -> NormalOcclusion (RGB + alpha)
roughness            -> Smoothness (1 - roughness)
metallic             -> pas de canal, reversé en brillance
emissive             -> pas de canal, réintégré dans la couleur
```

Rien n'est deviné : une image que rien n'identifie reste marquée inconnue et
n'est pas écrite, plutôt que de poser la mauvaise carte dans le mod.

### Assets à plusieurs matériaux

Paralives donne **une surface par mesh**. Un asset découpé en cinq matériaux ne
s'importe donc pas tel quel. Le bouton **Fusionner en une seule surface**
repaquette les UV de toute la sélection dans un atlas, bake chaque canal, et
remplace les matériaux par un seul. Le rendu est préservé, les UV non.

## Installation

```bash
python build.py --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

Puis dans Blender : `Edit > Preferences > Add-ons > Install from Disk`, et
choisir `dist/paraforge-0.5.0.zip`.

Le panneau apparaît dans la barre latérale de la vue 3D, onglet **ParaForge**
(`N` pour l'ouvrir).

## Utilisation

0. Choisir le mod cible, ou en créer un avec le **+** à côté du sélecteur.
   Les mods vivent dans `AppData\LocalLow\Paralives\Paralives\`. Évite
   `Local.mod` : c'est le bac à sable du jeu, il marche pour essayer mais ne
   peut pas être publié sur le Workshop.
1. Sélectionner le mesh. La checklist s'affiche dans le panneau et en
   surimpression dans la vue.
2. **Tout corriger sans risque** règle l'échelle, les transformations,
   l'origine, l'attribut de couleur et les rôles de texture.
3. Vérifier l'orientation contre la flèche verte, puis confirmer. C'est la
   seule chose qu'aucun outil ne peut deviner.
4. Choisir le dossier `.mod`, puis **Exporter vers Paralives**.
5. **Créer l'objet dans le catalogue**. C'est fini : l'objet est en Build Mode,
   sans passer par le Control Panel.

Le jeu importe ses assets au lancement, il n'y a pas de rechargement à chaud :
il faut relancer Paralives après chaque export.

## Ce que le wiki ne dit pas, et que le jeu dit

Paralives livre son propre contenu sous forme de mod : `Main.mod`, dans le
dossier d'installation, est un dossier ordinaire de FBX, de PNG et de texte.
C'est de là que viennent les chiffres ci-dessous, mesurés et non supposés.

**Budget de triangles.** 159 meshes tirés au hasard de `Environments/Items` et
importés dans Blender : médiane **294** triangles, 90e centile 1 380, maximum
**4 060**. Le budget par défaut de ParaForge est ce maximum. Un asset
téléchargé à 560 000 triangles fait cent fois le plus gros objet du jeu.

**Résolution des textures.** Sur les 1 446 textures d'objets : 512 px en tête,
puis 256, puis 1 024. Rien au-dessus de 2 048. Une carte 4K est donc quatre
fois la plus grande du jeu.

**Proportion des cartes.** Detail 524, GrayMask 474, ColorZone 52,
NormalOcclusion 41, Smoothness 22, Master 8. Une normal map est sur un objet
sur vingt : ParaForge ne la réclame plus.

**Fichiers `.meta`.** Chaque asset a un compagnon texte qui porte son GUID et
ses réglages d'import. Le mapping suffixe vers réglages, relevé sur 800
textures, est parfaitement régulier : `IsLinear` sur tout sauf `Detail`,
`IsPointFilter` sur `ColorZone`, et `HasVariantMap` plus `HasHueshiftMap` sur
`Master`. ParaForge écrit ce fichier, ce qui rend l'import déterministe au lieu
de dépendre de la lecture du nom.

**Tags du catalogue.** Les 298 tags du Build Mode sont extraits du jeu par
`tools/extract_catalog.py` vers `paraforge/catalog.py`, avec leur GUID et leur
hiérarchie. À relancer après une mise à jour du jeu.

**Une porte** fait 2,112 m de haut, un vantail simple 1,04 m de large. Pratique
pour juger l'échelle d'un modèle importé à l'oeil.

## L'objet, écrit sans passer par le Control Panel

Un objet Paralives, c'est trois morceaux de texte, tous **dans ton propre
mod** :

```
<Mod>/<Nom>.prefab               l'arbre d'objets, sa taille, son mesh
<Mod>/Settings/Items.setting     l'entrée de catalogue, le tag, les swatches
<Mod>/Settings/Translations...   le libellé que le joueur lit
```

Un mod ne porte que ce qu'il ajoute et le jeu fusionne le tout : le mod de
traduction française du jeu ne contient rien d'autre qu'un
`Translations.setting`. C'est pourquoi **aucun fichier du jeu n'est modifié**,
jamais.

La fusion se fait sur le texte, pas en régénérant le fichier depuis un modèle
analysé : un `Items.setting` écrit par le jeu peut contenir des champs que
l'extension ne connaît pas, et les réécrire les perdrait en silence. Ajouter
une entrée change donc exactement deux choses, la ligne de compte et le bloc
inséré.

**Annulation en un clic.** Chaque génération est journalisée dans
`_paraforge/journal.json`, avec une copie de tout fichier modifié. Le bouton
**Annuler la dernière écriture** supprime ce qui a été créé, restaure ce qui a
été changé, et efface les dossiers laissés vides. Appuyer deux fois remonte
deux générations en arrière. Générer deux fois le même objet ne fait rien et
n'ajoute pas d'étape.

## Rien n'est jamais écrit dans le jeu

L'export refuse un dossier situé dans l'installation de Paralives. Les assets
vont dans un `.mod` sous `AppData\LocalLow`, sinon une mise à jour du jeu les
efface et ils ne peuvent pas être partagés.

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

Le premier vérifie qu'aucune chaîne n'a été oubliée dans le catalogue
français. Le deuxième couvre la géométrie, les zones, la détection de textures,
le bake et l'export. Le troisième dessine chaque panneau et valide chaque
icône, propriété et opérateur contre l'API réelle, ce qui attrape les erreurs
qui n'apparaissent qu'à l'affichage.

## Licence

GPL-3.0-or-later.
