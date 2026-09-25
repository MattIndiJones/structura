# Corrections de recette Studies — 22 septembre 2026

## Périmètre

Corrections du parcours existant, méthode `studies-2.5`. Le Buy & Hold conserve ses conventions : panier brut avec dividendes réinvestis, comparé à la NAV nette du fonds. Aucun input fictif modifié, aucun commit/push.

## Modifications

| Domaine | Modification |
|---|---|
| IA | Contexte éditorial ciblé, séparé des tables complètes ; suppression du catalogue de hashes dans le texte envoyé ; distinction explicite entre performance cumulée et annuelle. Prompt `amc-synthesis-v2`, contexte Ollama de 16 384 tokens. |
| IA / intégration | Refus des réponses vides, techniques, trop courtes, blocs de code incomplets et fins de génération signalées comme tronquées. Une réponse recevable reste un **brouillon non validé**, jamais inséré automatiquement. Les erreurs sémantiques ne sont pas toutes détectables par ces contrôles. |
| PDF | Dividendes acquis ajoutés au pont comptable, détail par titre avec dividendes, conventions de gestion et de cristallisation tirées du résultat, tableau annuel des frais/HWM. Meilleurs contrastes, libellés P&L et alignement des cartes. |
| Turnover | Annualisation ACT/365 entre premier et dernier ordre ; la vue A de l’étude complète reprend le turnover exécuté de C. Les observations NAV ne servent plus de durée d’annualisation de cet indicateur. |
| Affichage | Semi-déviation annualisée de J reliée au bon champ ; panier E/G reconnu dans la configuration ; date effective du B&H et écart en points ; réserves F/G et aides D/H/I actualisées. |
| Frais/HWM | Détail annuel calculé à partir des cumuls de la même reconstruction, NAV et HWM à chaque fin d’année disponible ; frais présentés avec leur signe. Une provision intermédiaire n’est pas présentée comme un paiement. |

## Vérifications

- Nouvelle exécution complète sur `LO_ALL_BLOCKS_2020_2025`, puis exécution depuis l’interface ; sauvegarde « Recette corrigée 2.5 — 22/09/2026 » et réouverture.
- **85/85** comparaisons multi-blocs et **108/108** comparaisons financières conformes. Le comparateur utilise pour 2.5 la politique indépendante déjà applicable à 2.4 ; aucune valeur d’oracle ajustée à la sortie.
- Référence annuelle indépendante conservée dans `backend/tests/fixtures/studies_long_only_annual.csv`, issue du journal du générateur indépendant. NAV, HWM, gestion, performance et transactions contrôlés sur six années. La différence entre deux cumuls arrondis peut atteindre un centime : tolérance annuelle 0,011 USD, distincte de celle des cumuls.
- 126 tests backend ciblés (Studies, réconciliation, méthodologie, transport IA/scripting) ; 204 tests frontend et build de production. La suite backend complète n’a pas été lancée.
- Les PDF complet et simplifié sont générés à partir du nouveau résultat ; contrôle textuel des rubriques modifiées et inspection visuelle des pages de réconciliation et tableaux. Cela ne constitue pas une inspection exhaustive de toutes les annexes.

## Lecture du contrôle annuel

| Année | Gestion USD | Performance USD | HWM fin |
|---|---:|---:|---:|
| 2020 | −97 910,06 | −44 937,52 | 102,5465 |
| 2021 | −112 595,52 | −507 220,73 | 131,2890 |
| 2022 | −103 920,09 | 0,00 | 131,2890 |
| 2023 | −105 980,34 | 0,00 | 131,2890 |
| 2024 | −110 265,21 | 0,00 | 131,2890 |
| 2025 | −129 398,18 | −119 580,19 | 138,0652 |

2023 est positive, mais reste sous le HWM cristallisé de 2021 : aucune commission de performance. Les chiffres sont des charges estimées à partir de la NAV publiée, pas des mouvements bancaires attestés.

## Procédure utilisateur

1. Redémarrer l’application sur le nouveau code puis recharger le navigateur.
2. Scanner le même dossier et **relancer une étude** : une ancienne sauvegarde n’acquiert pas les nouveaux champs annuels automatiquement.
3. Dans B, lire « Frais et HWM par année ». Dans A/C, comparer le turnover ; dans J, vérifier la semi-déviation 8,25 %.
4. Dans Synthèse, générer un brouillon, vérifier ses faits et conclusions, puis seulement utiliser « Insérer dans la synthèse ».
5. Générer un nouveau PDF et sauvegarder cette version. Un PDF déjà exporté reste inchangé.

## Limite de validation IA

Les essais réels avec Gemma 4B produisent désormais du français, mais ont encore montré des erreurs de montant et d’interprétation. Le changement de prompt et le contrôle de format ne certifient pas la fidélité financière. Mistral 7B a ensuite atteint la limite de génération : le backend a rejeté la réponse et l’interface a affiché « Synthèse interrompue par la limite de génération ; aucun texte intégré ». Le retrait de l’insertion automatique est donc essentiel ; une relecture reste requise avant utilisation du rapport. Les résultats chiffrés du moteur, contrôlés séparément, ne sont pas remplacés par la prose IA.

Preuves locales : `artifacts/studies/RECETTE_CORRIGEE_2026_09_22/` (résultat, CSV de contrôles, PDF, extractions et rendus). Les artefacts et la base applicative restent locaux et ignorés par Git.

Fin de session : instances backend démarrées pour les tests arrêtées après vérification des PID et commandes ; port 8000 libre. Les autres processus Python et Ollama préexistants n’ont pas été arrêtés.
