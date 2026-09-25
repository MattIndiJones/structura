# Plaquette Finegan — Patrimonia 2026

Plaquette commerciale A4 paysage recto-verso, pliée en deux pour former quatre pages A5 portrait.

## Prévisualiser

Ouvrir `index.html` directement dans un navigateur. La barre d’outils permet de passer entre :

- **Lecture 1–4** : quatre pages dans l’ordre de lecture ;
- **Imposition print** : recto `page 4 | page 1`, verso `page 2 | page 3` ;
- **Print / Export PDF** : dialogue d’impression du navigateur.

Le document ne dépend d’aucun service distant. Le logo, les styles et les scripts sont locaux.

## Coordonnées

Les variables sont regroupées en tête de `js/main.js` :

```js
const CONTACT_NAME = "";
const CONTACT_TITLE = "";
const CONTACT_EMAIL = "";
const CONTACT_PHONE = "";
const CONTACT_URL = "https://finegan.fr/#contact";
```

Les champs personnels restent vides tant qu’ils ne sont pas validés. `CONTACT_URL` utilise la page de contact officielle Finegan et peut être remplacé par une URL validée.

## Export PDF

Paramètres recommandés dans Chrome ou Edge :

- destination : **Enregistrer au format PDF** ;
- format : défini par CSS, **303 × 216 mm** ;
- marges : **aucune** ;
- échelle : **100 %** ;
- graphiques d’arrière-plan : **activés** ;
- en-têtes et pieds de page du navigateur : **désactivés** ;
- impression recto-verso chez l’imprimeur : **retournement sur bord court**, après validation de son flux.

Le format 303 × 216 mm comprend 3 mm de fond perdu autour du format fini A4 paysage 297 × 210 mm. Le pli central se situe à 151,5 mm dans le fichier, soit au milieu du format fini.

## Structure

```text
index.html
css/styles.css
js/main.js
assets/finegan-logo.png
assets/finegan-mark.png
PREPRESS-CHECKLIST.md
```

La palette privilégie des aplats sobres et des contrastes compatibles avec une conversion CMJN. La conversion finale en profil CMJN et l’incorporation d’un profil ICC relèvent du flux prépresse de l’imprimeur.
