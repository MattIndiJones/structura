# Studies — organisation de l’interface

## Parcours

L’étude complète dispose de deux espaces en pleine largeur : **Configuration & données** et **Résultats**. L’analyse FF classique conserve son organisation précédente.

La configuration regroupe les sources, l’identification et l’arrêté, les frais, les dividendes et les paramètres d’analyse. Les raccourcis internes font défiler la page sans modifier la route de l’application. Les options de réinvestissement apparaissent selon la convention sélectionnée. Les chemins des fichiers sont modifiables ; une ligne correspond à un carnet de transactions.

Un récapitulatif distingue les fichiers référencés des contrôles réalisés par le moteur lors du lancement. Les frais absents et certaines sources manquantes sont signalés. Le bouton de lancement se trouve en haut de la configuration. Après un calcul réussi ou le chargement d’une étude sauvegardée, l’espace Résultats s’ouvre automatiquement.

Une modification des paramètres, du dossier ou des fichiers après le calcul affiche une indication de résultats à recalculer. Changer d’espace préserve la configuration et les résultats en mémoire. Les rapports PDF restent accessibles en bas de la configuration.

## Lecture des résultats

- Tableaux défilants, en-têtes fixes dans leur zone de défilement, espacement homogène des titres et cellules.
- Colonnes numériques alignées à droite, y compris leurs titres ; noms et descriptions alignés à gauche.
- Indicateurs regroupés dans des cartes adaptatives, notamment dans les blocs de risque, attribution, trading et comportement.
- Attribution : indicateurs, détail par titre, rapprochement NAV puis registre des dividendes. La devise figure dans le titre du tableau ; le FX réalisé est explicitement indiqué comme déjà inclus.
- Conservation des valeurs et des arrondis existants, des contrôles de qualité et du masquage des montants sensibles.

## Validation

Modification de présentation dans `frontend/src/views/AmcView.vue`, sans modification des moteurs ni du schéma backend. Les 194 tests frontend existants passent et le build de production réussit.

Le navigateur intégré a refusé l’accès à l’instance locale (`ERR_BLOCKED_BY_CLIENT`) : la recette visuelle interactive reste à faire dans le navigateur de Philippe. Recharger la page, ouvrir une étude sauvegardée, alterner entre les deux espaces, vérifier Attribution et Risque puis modifier un paramètre pour vérifier le bandeau de recalcul. Sur une fenêtre étroite, vérifier le passage des formulaires à une colonne et le défilement indépendant des tableaux. Aucun redémarrage backend n’est nécessaire pour cette modification d’interface.


## Accès PDF et synthèse IA

Les exports PDF complet et simplifié sont visibles en haut de l’étude, dans les deux espaces Configuration et Résultats. Le navigateur télécharge le fichier ; son dossier dépend des réglages du navigateur.

Le bouton Synthèse / IA ouvre la rédaction et le choix du modèle. La génération est déclenchée explicitement par « Générer la synthèse », pas par le calcul des blocs. Le composant reste monté lors des changements d’onglet de résultats : une réponse en cours n’est plus perdue pour cette raison. Une synthèse vide est remplie automatiquement après une réponse valide ; un texte existant est conservé et peut être remplacé avec « Insérer dans la synthèse ». Une réponse vide ou associée à une autre version de l’étude affiche un message explicite.

Diagnostic : le déplacement de la configuration avait masqué les exports depuis les résultats. Les journaux locaux consultés dataient du 21/07/2026 et ne permettent pas d’attribuer un échec IA récent à un fournisseur ou une clé API.
