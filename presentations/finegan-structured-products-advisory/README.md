# Finegan — Structured Products Advisory

Présentation commerciale HTML de cinq slides, disponible en français et en anglais. Elle présente une capacité de conseil couvrant la conception, le lancement et le pilotage d’une activité produits structurés.

## Ouvrir la présentation

Ouvrir `fr/index.html` ou `en/index.html` dans un navigateur récent. Le fichier `index.html` à la racine redirige vers la version française. Conserver ensemble les dossiers `fr`, `en` et `assets`.

Pour servir les fichiers en local, lancer depuis ce dossier :

```shell
python -m http.server 8768 --bind 127.0.0.1
```

Puis ouvrir <http://127.0.0.1:8768/fr/index.html>.

La présentation et le logo fonctionnent hors ligne. Le lien final vers le formulaire officiel Finegan nécessite une connexion Internet et n’envoie aucun message automatiquement.

## Structure

```text
finegan-structured-products-advisory/
├── index.html                 Entrée vers le français
├── fr/index.html              Version française
├── en/index.html              Version anglaise
├── assets/
│   ├── finegan-logo.png       Symbole officiel Finegan
│   ├── content.js             Tous les textes FR et EN
│   ├── presentation.css       Identité, layouts, animations et impression
│   └── presentation.js        Rendu des slides et navigation
└── README.md
```

## Navigation

| Commande | Action |
| --- | --- |
| Flèche droite, PageDown, Espace | Slide suivante |
| Flèche gauche, PageUp, Maj + Espace | Slide précédente |
| Home / End | Première / dernière slide |
| F | Activer ou quitter le plein écran |
| Échap | Quitter le plein écran |
| R ou bouton ↻ | Rejouer les animations |
| Repères et flèches en pied de page | Navigation à la souris |
| Balayage horizontal | Navigation tactile |
| FR / EN | Changer de langue en conservant la slide courante |
| Icône imprimante ou Ctrl + P | Imprimer les cinq slides |

Une URL terminant par `#slide-4`, par exemple, ouvre directement la quatrième slide.

## Modifier les textes

Éditer `assets/content.js`, puis recharger le navigateur. Les objets `fr` et `en` partagent la même structure. `ui` contient les libellés d’interface et `s1` à `s5` le contenu des slides. Les éléments `<em>` appliquent l’accent corail et `<br>` conserve un saut de ligne intentionnel.

Après toute modification, vérifier les deux langues en 1920 × 1080, 1440 × 900 et sur laptop. Des textes sensiblement plus longs peuvent modifier les retours à la ligne.

## Visuels et interprétation

Les courbes, niveaux de barrière et niveaux de coupon sont des illustrations abstraites. Ils ne comportent aucune donnée, cotation, rendement, échéance ou recommandation d’investissement. La courbe de payoff de la slide 1 sert uniquement à représenter le passage de l’idée produit à une solution d’investissement.

La slide 2 montre une chaîne de valeur continue. La slide 3 présente les quatre temps de construction de la capacité. La slide 4 illustre le renfort d’une équipe client par une expertise senior mobilisable à la demande. La slide 5 matérialise la progression du premier cas d’usage vers une activité capable de changer d’échelle.

## Identité Finegan

Le fichier `assets/finegan-logo.png` reprend le symbole officiel utilisé dans l’autre présentation Finegan. La palette, les espacements, la signature typographique et les contrôles sont volontairement communs aux deux supports afin de former une même gamme commerciale. Les layouts et animations sont spécifiques à l’offre Structured Products Advisory.

Références officielles :

- Identité visuelle : <https://finegan.fr/>
- Formulaire de contact : <https://finegan.fr/#contact>

Pour remplacer le logo, conserver le nom `finegan-logo.png` ou mettre à jour le chemin dans `assets/presentation.js` et dans les deux fichiers HTML. Ajuster `.brand-symbol` dans `assets/presentation.css` si les proportions changent.

## Format, accessibilité et impression

Le canevas desktop utilise un ratio 16:9 sur une base de 1600 × 900 et s’ajuste proportionnellement aux écrans 1920 × 1080, 1440 × 900 et aux laptops. Sur téléphone en portrait, le contenu se réorganise verticalement.

Les contrôles sont utilisables au clavier, les slides inactives sont exclues de l’interaction et les libellés sont exposés aux lecteurs d’écran. La préférence système de réduction des animations est respectée.

L’impression affiche les cinq slides dans leur état final, sans navigation. Pour créer un PDF, choisir le format paysage, activer les arrière-plans et désactiver les en-têtes et pieds de page du navigateur.
