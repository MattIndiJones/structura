# Corrections de la seconde confrontation — 24 octobre 2026

Cette intervention traite le défaut P1 et les trois incohérences P2 retenus
après confrontation de la seconde contre-revue au code déjà corrigé. Elle est
distincte des quatre corrections documentées dans
[REVIEW_FIXES_2026-10-24.md](REVIEW_FIXES_2026-10-24.md).

## Corrections et portée

| Point | Comportement corrigé | Limite conservée |
|---|---|---|
| P1 — observations à l'origine ou passées | Un contrôle commun refuse les dates d'observation AT non finies ou non strictement positives, après résolution et ajustement ouvré. Il s'applique aussi aux calendriers figés et à l'ordonnanceur moteur avant diffusion. | Les dates futures positives restent projetées sur la grille existante ; aucun schéma de diffusion n'est changé. |
| P2 — message de règlement | À la date contractuelle de paiement et après, le refus de MtM explique la sortie du périmètre contractuel et précise que le règlement bancaire n'est pas confirmé ici. | Aucun suivi bancaire, paiement partiel ou recouvrement n'est ajouté. Les conventions contractuelles du lifecycle restent identiques. |
| P2 — seed MTF | L'écran affiche « Graine fixe », 42 en lecture seule, et explique la portée de reproductibilité. Le store envoie explicitement 42 et le drill-down réutilise le corps de l'éventail. Le masquage démo est conservé. | Ce chemin de desk ne fournit pas de réplications à graines indépendantes. |
| P2 — EE/EPE | Les nouvelles sorties retirent le scalaire ambigu `ee`. `current_exposure` porte EE(0), `profile[].ee` porte EE(t), et `epe` la moyenne temporelle. La version devient `ccr-1.4-explicit-exposure-metrics`. | Les archives ne sont pas réécrites. Un ancien client utilisant le scalaire `ee` comme alias doit désormais lire `epe`. |

Le contrôle des dates porte sur les événements effectivement exécutés : une
date inutilisée dans un calendrier ne fait pas refuser un bloc qui sélectionne
uniquement une observation future. Le fixing initial explicite et sa fenêtre
de départ restent séparés des événements de paiement et conservent leurs
règles. Un relevé sélectionné explicitement par un bloc AT est contrôlé comme
une observation. Une date passée exige un rejeu des fixings réalisés, sans
substitution par une date simulée.

La modification CCR ne change ni l'intégration de l'EPE, ni les profils, ni les
limites. Sa documentation décrit désormais l'intégration existante par
rectangles à gauche avec frontières ex-paiement. Un oracle discriminant donne
EE(0) = 100, EE(0,5) = 60, EE(2) = 0 et EPE = 70 ; ces objets restent distincts.

## Validation finale

Les tests backend ont été lancés depuis la racine, dans le harnais isolé
`.runtime/diagnostic-acceptance/review-followup-2026-10-24/run_targeted.py` :
répertoire de données temporaire, refus des connexions SQLite dans
`backend/data`, blocage réseau externe et clients ASGI sur base en mémoire.
Aucun service applicatif n'a été démarré.

**285 tests backend réussis, 0 échec, 0 erreur**, en 19,26 secondes selon le
JUnit final `targeted.xml` :

| Fichier | Cas réussis |
|---|---:|
| `test_review_followup_2026_10_24.py` | 19 |
| `test_parser.py` | 50 |
| `test_payscript_reference.py` | 14 |
| `test_payscript_binding.py` | 25 |
| `test_contractual_calendars.py` | 46 |
| `test_contractual_timeline.py` | 25 |
| `test_schedule_model.py` | 11 |
| `test_market_data_lot4.py` | 4 |
| `test_ccr.py` | 24 |
| `test_ccr_api.py` | 3 |
| `test_ccr_cache.py` | 6 |
| `test_mtf_fenetres.py` | 8 |
| `test_review_fixes_2026_10_24.py` | 50 |

Les 19 régressions nouvelles couvrent les observations ponctuelles et les
échéanciers à l'origine ou passés, l'ajustement ouvré, les relevés qualifiés,
les calendriers figés, le refus avant diffusion et par HTTP, le message de
règlement à échéance et J+5, les métriques CCR et les modes FULL/FAST. Les
50 régressions des corrections précédentes restent vertes.

Le script `npm run build` a exécuté les **782 tests frontend : tous réussis**
(87 fichiers), dont les trois nouveaux tests `MtfTab.test.js` : champ effectif
en lecture seule, masquage démo et requêtes éventail/drill-down à seed 42.
La compilation Vite a ensuite réussi en **10,52 secondes**. L'option de sortie
ayant été absorbée par la première invocation npm/PowerShell, seule la phase
de compilation a été reprise directement avec Node, sans répéter les tests
déjà réussis. Sa sortie se trouve dans le dossier de preuves `frontend-dist/`,
afin de préserver les fichiers `frontend/dist` préexistants.

Les premiers journaux d'itération sont conservés et ne constituent pas des
preuves de succès final : `before.xml`, `regressions.xml` et
`frontend-targeted.xml`. Ils comprennent notamment des ajustements du harnais
de test : une fenêtre `3D`, et non `2D`, était nécessaire pour viser le relevé
à l'origine ; l'aide repliée n'est pas rendue en SSR et l'état privé du store
se vérifie par la requête de drill-down. Le premier refus par assertion dans
un thread ASGI produisait aussi une erreur de fermeture du client ; les
preuves finales ne contiennent plus cette erreur.

## Preuves et limites

Le dossier `.runtime/diagnostic-acceptance/review-followup-2026-10-24/` conserve :

- `targeted.xml` : preuve backend finale ;
- `frontend-build.log` : succès des 782 tests frontend et erreur initiale
  d'argument de compilation ;
- `frontend-compile.log` et `frontend-dist/` : compilation finale réussie ;
- `baseline.json`, `baseline/`, `task-only.patch` et `verification.json` :
  état préalable, delta de cette intervention et empreintes finales.

La suite backend complète n'a pas été relancée. Les contrôles de rendu
frontend sont automatisés ; aucune nouvelle recette graphique en navigateur
n'est revendiquée. Ces corrections n'étendent pas le domaine numérique, la
qualification réglementaire ou le suivi bancaire. Les ZIP précédents restent
les photographies historiques de leur livraison et n'ont pas été régénérés.

Les modifications préexistantes du checkout sont préservées. Aucun commit ni
push n'a été effectué.
