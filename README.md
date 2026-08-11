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
choisir `dist/paraforge-0.2.0.zip`.

Le panneau apparaît dans la barre latérale de la vue 3D, onglet **ParaForge**
(`N` pour l'ouvrir).

## Utilisation

1. Sélectionner le mesh. La checklist s'affiche dans le panneau et en
   surimpression dans la vue.
2. **Tout corriger sans risque** règle l'échelle, les transformations,
   l'origine, l'attribut de couleur et les rôles de texture.
3. Vérifier l'orientation contre la flèche verte, puis confirmer. C'est la
   seule chose qu'aucun outil ne peut deviner.
4. Choisir le dossier `.mod`, puis **Exporter vers Paralives**.
5. Une fiche recette est écrite à côté, avec les valeurs exactes à saisir dans
   le Control Panel du jeu.

Le jeu importe ses assets au lancement, il n'y a pas de rechargement à chaud :
il faut relancer Paralives après chaque export.

## Ce qui n'est pas documenté par les développeurs

Le budget de triangles et la taille d'une tuile ne sont publiés nulle part. Ils
sont exposés dans le panneau **Calibrage** plutôt que codés en dur. Pour les
régler une bonne fois : importer un mesh officiel du jeu dans Blender et le
mesurer.

L'onglet **Inspecteur du dossier mod** sert à trancher une autre question
ouverte, celle de savoir si les définitions d'objets sont générables. Prendre
un instantané du dossier, créer un objet dans le jeu, quitter, comparer. Si le
jeu écrit du JSON lisible, la dernière étape manuelle devient automatisable.

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
