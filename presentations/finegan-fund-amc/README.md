# Finegan — Fund & AMC Analysis

Présentation commerciale de cinq slides, en français et en anglais. HTML, CSS et JavaScript natif, sans installation ni dépendance réseau nécessaire à la lecture.

## Ouvrir la présentation

Ouvrir `fr/index.html` ou `en/index.html` dans un navigateur récent. Un double-clic suffit. Le fichier `index.html` à la racine ouvre la version française. Après extraction de l’archive, conserver ensemble les dossiers `fr`, `en` et `assets`.

Pour servir les fichiers en local, depuis ce dossier :

```shell
python -m http.server 8767 --bind 127.0.0.1
```

Puis ouvrir <http://127.0.0.1:8767/fr/index.html>.

La présentation et le logo fonctionnent hors ligne. Seul le lien de contact final nécessite Internet : il ouvre le formulaire officiel Finegan, sans envoyer de message automatiquement.

## Structure

```text
finegan-fund-amc/
├── index.html                 Entrée vers le français
├── fr/index.html              Version française
├── en/index.html              Version anglaise
├── assets/
│   ├── finegan-logo.png        Symbole officiel Finegan
│   ├── content.js             Tous les textes FR et EN
│   ├── presentation.css       Identité, compositions, animations, impression
│   └── presentation.js        Rendu des slides, diagrammes et navigation
└── README.md
```

## Navigation

| Commande | Action |
| --- | --- |
| Flèche droite, PageDown, Espace | Slide suivante |
| Flèche gauche, PageUp, Maj + Espace | Slide précédente |
| Home / End | Première / dernière slide |
| F | Activer ou quitter le plein écran, si le navigateur le permet |
| Échap | Quitter le plein écran |
| R ou bouton ↻ | Rejouer les animations de la slide |
| Flèches et repères en pied de page | Navigation à la souris |
| Balayage horizontal sur écran tactile | Slide précédente / suivante |
| FR / EN | Changer de langue en conservant la slide courante |
| Icône imprimante ou Ctrl + P | Imprimer les cinq slides |

Les animations se lancent à l’entrée de chaque slide. Aucune avance automatique. Les boutons précédent et suivant se désactivent aux extrémités. Une URL terminant par `#slide-3`, par exemple, ouvre directement la troisième slide.

## Modifier les textes

Éditer `assets/content.js`, puis recharger le navigateur. Les objets `fr` et `en` partagent la même structure : `ui` pour les contrôles, `s1` à `s5` pour les slides. Les éléments `<em>` définissent l’accent corail et `<br>` les sauts de ligne intentionnels. Préserver des longueurs proches pour conserver la lisibilité et revérifier les deux versions après modification.

Le lien de contact se trouve dans `assets/presentation.js`, dans la composition de la slide 5. Les tracés SVG sont également définis dans ce fichier. Ils sont purement conceptuels, sans rendement, date, échelle numérique ni résultat client. Ils ne constituent pas une attribution additive calculée.

## Identité visuelle et logo

Le fichier `assets/finegan-logo.png` est le symbole officiel, conservé dans ses proportions, accompagné de la signature typographique FINEGAN comme sur le site officiel. Le texte reste présent si l’image est absente. Pour intégrer un autre fichier officiel, remplacer cette image ou modifier le chemin de `brand-symbol` dans `assets/presentation.js`, ainsi que les liens d’icône des deux fichiers HTML. Ajuster au besoin `.brand-symbol` dans la feuille de style.

Sources officielles consultées le 23 septembre 2026 :

- Identité et référence visuelle : <https://finegan.fr/>
- Symbole téléchargé uniquement depuis le site officiel : <https://finegan.fr/assets/finegan-logo-DqRLknzl.png>
- Destination du contact : <https://finegan.fr/#contact>

La palette reprend l’esprit marine et corail du site, avec un blanc cassé pour les slides claires. Les couleurs sont centralisées dans `:root` au début de `assets/presentation.css`. La typographie utilise Aptos, Segoe UI ou Arial selon les polices installées, sans appel à un service externe.

## Format, accessibilité et impression

Le canevas desktop est en 16:9, sur une base de 1600 × 900. Il se met à l’échelle en conservant ses proportions, y compris en 1920 × 1080, 1440 × 900 et 1366 × 768. Des bandes de fond apparaissent lorsque le ratio de l’écran diffère. Sur petit écran portrait, le contenu se réorganise verticalement pour rester lisible, avec navigation fixe et défilement de la slide.

Les commandes sont accessibles au clavier et nommées pour les lecteurs d’écran. Les slides inactives sont exclues de l’interaction. La préférence système « réduire les animations » est respectée : tous les contenus restent visibles sans attente.

L’impression affiche les cinq slides dans leur état final, sans navigation ni animation. Le format CSS est de 400 × 225 mm, soit 16:9. Pour un PDF, choisir « Enregistrer au format PDF », sans en-têtes/pieds de page du navigateur et avec les arrière-plans activés. Si le navigateur impose un format papier, choisir paysage et ajuster à la page. La présentation HTML animée demeure le support principal.
