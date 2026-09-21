# Présentation du rendez-vous de mercredi

## Deux versions prêtes à utiliser

- **Presentation-a-partager.html** : fichier à envoyer au cabinet. Les notes orales, réponses aux objections et indications internes sont retirées du contenu et du code. Aucun bouton ou raccourci ne permet de les afficher.
- **Presentation-presentateur.html** : fichier personnel pour Philippe, avec les notes orales (bouton **Notes** ou touche **N**).

Chaque version est **un seul fichier autonome** : images, graphiques, styles et scripts sont intégrés. On peut envoyer ou copier uniquement le fichier choisi, puis l’ouvrir dans un navigateur sans connexion et sans serveur. Ne pas envoyer le dossier complet : il contient les documents de préparation et la version présentateur.

Le PDF **Presentation-partenariat.pdf**, déjà sans notes, peut également être partagé.

Les fichiers se trouvent dans :

`C:\Users\Admin\GitHub\structura\presentations\studies-partnership`

Les fichiers `index.html`, `styles.css`, `presentation.js` et `assets` restent les sources éditables. Après modification de ces sources, exécuter `build_versions.py` pour actualiser les deux versions autonomes.

## Présenter

- Flèches **← / →** : écran précédent / suivant.
- Touches **1 à 6** : accès direct à un écran.
- **F** ou bouton en haut à droite : plein écran. **F11** peut aussi être utilisé dans le navigateur.
- **N** ou bouton **Notes** : fil oral et réponses aux objections, uniquement dans la version présentateur.
- **Échap** : fermer les notes ou un aperçu de rapport.
- Écran 2 : cliquer sur les quatre phrases colorées sous les étapes pour révéler les explications. Elles restent ouvertes pendant la navigation ; recharger la page les masque à nouveau. Le PDF les affiche toutes.
- Écran 3 : cliquer sur chaque question colorée pour révéler un visuel pédagogique. Les visuels restent ouverts pendant la navigation ; recharger les masque à nouveau. Aucun chiffre ou résultat du fonds n’est représenté dans ces illustrations. Tous sont visibles dans le PDF.
- Écran 4 : boutons **Performance / Drawdown / Contributions** pour changer de graphique.
- Écran 5 : cliquer sur une page du rapport pour l’agrandir.

Les notes s’affichent dans la même fenêtre : les consulter avant le partage d’écran ou pendant la répétition. Il ne s’agit pas d’une vue présentateur sur un second écran.

## PDF

**Presentation-partenariat.pdf** est le support de secours : six pages, fond clair, sans notes orales. Les interactions sont réservées au HTML ; le PDF conserve le graphique de NAV sur l’écran du cas concret.

Le bouton **PDF** ouvre aussi la boîte d’impression du navigateur pour produire une nouvelle version. Choisir « Enregistrer au format PDF », conserver le format paysage proposé, désactiver les en-têtes/pieds de page automatiques du navigateur et activer les graphiques d’arrière-plan si nécessaire.

## Avant le rendez-vous

Ouvrir le dossier sur l’ordinateur utilisé mercredi, passer les six écrans et essayer le plein écran. Le nom commercial confirmé est **TP Advisory Services**. L’identité visuelle est une proposition créée pour ce support, sans logo officiel fourni.

Le fonds montré est fictif. La mention de simulation doit rester visible. Les conventions et limites figurent dans les notes et dans `SOURCES.md`.

`CONTENU_ET_NOTES.md` contient le scénario détaillé pour préparer le discours. La présentation est un livrable séparé ; aucune modification de l’application n’est nécessaire pour l’utiliser. Elle n’a pas été publiée en ligne.

## Périmètre et mises à jour

Ce support est en français et destiné au cabinet partenaire. La présentation du site pour le client final sera un livrable distinct.

L’écran 3 regroupe les analyses en quatre questions métier. Mettre à jour les textes et les notes dans les sources communes, puis toujours régénérer **les deux éditions** avec `build_versions.py` et actualiser le PDF. Ne pas modifier directement les HTML autonomes : ils seraient écrasés à la prochaine génération.
