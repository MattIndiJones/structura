# Origine de la fixture long only

`studies_long_only_reference.zip` contient le carnet, le relevé final et les NAV du jeu indépendant `LO_BASE_2020_2025_V1`, ses flux cash, son résumé et ses appariements FIFO de référence. Seul le manifeste d'import est adapté à Studies 2.1 : assiette ACT/365 précédente, cristallisation annuelle, marks du relevé, carnet déjà ajusté des splits.

Les valeurs attendues proviennent du générateur indépendant en bibliothèque standard Python et de son second calcul en Decimal, pas de Studies. Le ZIP a été créé le 21 septembre 2026 à partir du dossier `artifacts/studies/LO_BASE_2020_2025_V1` et ne requiert pas ce dossier pour les tests. Les devises sont converties avec l'historique BCE figé ; tous les titres et transactions sont fictifs.

Voir `docs/projects/studies/STUDIES_RECONCILIATION_AND_FEES_2026-09-21.md` et `INDEPENDENT_LONG_ONLY_DATASET_2026-09-21.md`. Ne pas régénérer les attentes à partir du moteur testé en cas d'échec.
