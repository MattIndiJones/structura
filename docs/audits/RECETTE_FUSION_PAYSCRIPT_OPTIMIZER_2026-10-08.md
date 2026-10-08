# Contrôles de fusion — PayScript et Optimizer

État du 08/10/2026, sur `codex/payscript-basket-startdate`, à la demande de Philippe de commit, push et fusionner sur `main`. La [PR #1](https://github.com/MattIndiJones/structura/pull/1) rassemble les évolutions PayScript, Optimizer et outils de surface déjà préparées, avec leur documentation et le build frontend. La base réelle et les dossiers temporaires ne sont pas versionnés.

## Contrôle GitHub initial

Sur le commit `7d49740`, les 355 tests frontend et le build passent sur GitHub. Le workflow Windows backend se termine avec **2 613 tests réussis, trois ignorés et deux échecs**, en 18 min 10 s pour pytest. Ce lancement provient du workflow automatique du dépôt ; aucune suite backend complète n’a été lancée localement pour la fusion.

| Échec | Cause et correction |
| --- | --- |
| Contrat de prompt AMC dans `test_ai_workbench` | Le fournisseur fictif renvoyait un seul mot, rejeté par le validateur de synthèse existant. Le test utilise désormais un texte de longueur valide ; les contrôles de qualité et de contexte restent inchangés. |
| Égalité grille de stress / grille 2D pour un avenant en cours de vie | Le solveur et la grille de paramètres recevaient l’état réalisé, mais pas la date de paiement final du contexte résiduel. Le chemin partagé transmet désormais `maturity_payment_t` et `strike_set_t`, comme le pricing et les cellules de stress. La régression garde son égalité stricte et couvre les délais de paiement de 0, 9 et 45 jours, ainsi que la résolution du coupon à prix identique. |

Sur le cas de régression initial, le stress donnait 0,459539 contre 0,459700 pour la grille : environ **1,61 bp du nominal** de différence. Aucun assouplissement de tolérance ni modification du payoff, du simulateur ou des tirages n’a été utilisé pour faire passer le contrôle.

## Vérification ciblée des corrections

- `test_ai_workbench.py` et la régression de comparaison sur trois délais : **19 tests réussis**.
- `test_simulation.py`, `test_scenarios.py` et cette régression complétée par le solveur : **16 tests réussis**.
- Au total : **32 tests backend distincts** ; les trois cas de délai ont été rejoués après ajout du contrôle du solveur.
- Tests offline, historiques synthétiques et base SQLite en mémoire. La base réelle n’a pas été utilisée ; son horodatage est resté inchangé pendant ces vérifications.

Les contrôles GitHub du commit correctif sont relancés automatiquement au push. Leur état final et la fusion sont consultables dans la PR. Les limites de pricing et de recette visuelle restent celles des notes des lots ; ce contrôle de fusion ne les remplace pas.
