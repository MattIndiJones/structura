# Correction des quatre défauts établis — 24 octobre 2026

## Périmètre

Cette intervention traite **CR01 à CR04 du rapport livré dans
`output/structura-counter-review-2026-10-24/COUNTER_REVIEW_FR.md`** : contexte
KID/MTF, faux succès du solveur, levier EMT et créances des horizons KID.
Ces identifiants sont propres à ce rapport ; ils ne désignent pas les constats
homonymes de l'autre contre-revue conservée dans ce dossier.

Les modifications préexistantes du checkout ont été conservées. Aucun service
n'a été démarré, aucune base applicative utilisée, aucun commit ni push effectué.

## CR01 — hypothèses de valorisation transmises ou refusées

Le calcul KID à échéance utilise désormais `ValuationContext` et
`run_valuation`, comme le prix canonique. Funding plat ou courbe, monitoring,
calendrier résolu/figé, paiement final et rebasage à la value date suivent le même
chemin. Les flux des scénarios portent leurs dates de paiement, puis sont
exprimés depuis la value date pour le TRI. Un flux antérieur à cette date fait
refuser le KID, plutôt que produire une annualisation ambiguë.

Pour `PAY 1`, T = 0,25 an et r = 3 %, le prix KID publié passe de **0,9925**
sans funding à **0,9876** avec 2 % de funding. L'oracle est
`exp(-(r + funding) * T)` ; le résultat publié est arrondi à quatre décimales.
Un test HTTP distinct vérifie la courbe de funding et les dates de paiement et
de règlement initial contre `exp(-(r + funding) * (payment_t - value_t))`.

Le rejeu imbriqué MTF garde son domaine actuel. Une validation commune est
appliquée **avant tout Monte Carlo** dans le KID avec horizons intermédiaires,
l'éventail MTF et son drill-down :

| Hypothèse | KID à échéance seul | Horizons intermédiaires KID | Éventail MTF et drill-down |
|---|---|---|---|
| Funding plat ou courbe | Transmis au prix canonique | Refus explicite | Refus explicite |
| Monitoring continu | Transmis au moteur, sous ses restrictions | Refus explicite | Refus explicite |
| Value date décalée | Prix rebasé et flux décalés | Refus explicite | Refus explicite |
| Paiements différés | Dates de paiement effectives | Créances et cash distingués | Refus explicite |
| Courbe de taux, taux stochastiques, LSV, dividendes par courbe | Restrictions du moteur canonique | Refus existants partagés | Refus existants partagés |

La configuration KID produisant des horizons intermédiaires est refusée en
entier si l'un d'eux est hors domaine : aucune réponse partielle n'est publiée.
Un funding matériel ne doit donc pas être supprimé pour contourner le refus.
Le prix reste calculable avec son contexte, indépendamment de cette analyse.

## CR02 — convergence du solveur

`tol` reste une tolérance de **prix**. `param_tol`, exposée dans la requête,
mesure séparément la largeur de l'intervalle en unités stockées du PARAM
(défaut : `5e-7`). Une largeur petite arrête la recherche sans déclarer le prix
atteint. Le résultat expose `price_converged`, `parameter_converged`,
`stop_reason` et les deux tolérances ; `converged` suit uniquement le critère
de prix.

Le paramètre publié à six décimales est **repricé** avant cette décision.
Le prix, le résidu et la cible publiés conservent la précision nécessaire au
critère de convergence ; la trace garde les paramètres effectivement évalués.
Le budget du solveur réserve cette valorisation supplémentaire.

Les oracles ciblés comprennent une racine affine, un contrat discontinu sans
racine à 0,5, une pente de 1 000 000 qui rend l'arrondi matériel, le cas d'une
racine à une borne et une cible non encadrée. Le saut et l'arrondi donnent
`converged=false`, avec un prix reproductible au paramètre publié. Un test HTTP
vérifie également la propagation de `param_tol` et du motif d'arrêt.

## CR03 — levier EMT

La détection de `GEARING` et `LEVERAGE` utilise leur valeur économique effective
sans exiger le marqueur syntaxique `is_pct`. Les notations `2` et `200 %`
donnent donc la même détection. Les tests couvrent `PARAM` et `PARAM()`, les
deux noms, les séries d'overrides contenant un coefficient supérieur à 1 et
les séries restant à 1 ou en dessous.

La classification EMT conserve son caractère heuristique ; ce correctif ferme
l'incohérence de notation établie par la contre-revue.

## CR04 — cash et créances KID après STOP

Les horizons intermédiaires utilisent le rejeu des paiements déjà présent pour
les expositions de crédit (`credit_exposure=True`). Ce choix ne rajoute aucun
ajustement de crédit : il fournit le traitement existant des dates de paiement
et des créances acquises. Les flux déjà payés sont pris à leurs dates ; les
créances futures restent dans le mark de sortie à l'horizon, même après STOP.
Elles ne sont pas ajoutées une seconde fois au cash.

Pour `PAY 1; STOP` à 0,25 an, paiement à 0,75 an et sortie à 0,5 an sous r = 3 % :

- cash reçu avant la sortie : **0** ;
- créance vendue à la sortie : `exp(-0.03 * (0.75 - 0.5))`, soit **0,992528** ;
- scénario médian pour 10 000 € investis au pair : **9 925,28 € à 0,5 an** ;
- à détention jusqu'au paiement : **10 000 € à 0,75 an**.

Les tests passent avant observation, à observation, avant paiement, au paiement
et après paiement, avec et sans STOP, à taux 0 et 3 %. Ils vérifient aussi un
coupon déjà reçu accompagné d'une créance encore impayée, le paiement final
explicite et le chemin HTTP KID avec calendrier figé.

Dans `run_mc`, la collecte des flux aux dates de paiement est une option
explicite. La collecte historique aux dates d'observation garde son défaut,
notamment pour les autres consommateurs qui effectuent eux-mêmes la conversion.

## Validation ciblée et preuves

Les exécutions utilisent le Python de `.venv`, un répertoire de données
temporaire, une garde interdisant SQLite dans `backend/data` et un blocage réseau
externe. Les appels HTTP de test passent par ASGI et une base en mémoire.
Le cas HTTP KID imbriqué borne les effectifs à 4 scénarios extérieurs et
8 chemins intérieurs ; il exécute le vrai moteur sur un payoff déterministe.

Le fichier `backend/tests/test_review_fixes_2026_10_24.py` contient **50 cas de
régression**. Les validations adjacentes portent sur le solveur et sa grille,
l'EMT, le KID/TRI, le contexte commun, la partition temporelle MTF, la cohérence
éventail/drill-down, deux cas de créances CCR et les propriétés KID existantes.
Les scénarios déterministes sont rapprochés d'oracles analytiques ; les tests
Monte Carlo existants gardent leurs effectifs et tolérances propres.

Les preuves sont conservées dans
`.runtime/diagnostic-acceptance/review-fixes-2026-10-24/` :

- `targeted.xml` : **111 réussites**, 0 échec, 0 erreur, en 63,88 secondes ;
- `final-kid.xml` : **52 réussites**, 0 échec, 0 erreur, avec les derniers cas de
  régression et les propriétés KID revérifiées ;
- `calendar-final.xml` : **1 réussite** ; le test MTF préexistant vérifie
  désormais le refus des hypothèses de règlement hors domaine, à l'émission et
  en cours de vie, puis conserve son contrôle de bascule résiduelle avec un
  calendrier sans délai de paiement et sans value date décalée ;
- `inlife-solver.xml` : **1 réussite** ; le solveur résiduel est rapproché d'un
  repricing indépendant au paramètre publié ;
- **118 cas distincts dans la sélection finale**, après remplacement de la
  première version du fichier de régression par sa version finale ;
- `baseline/`, `task-only.patch` et `verification.json` : delta de cette tâche,
  empreintes des fichiers et identité du HEAD ;
- `run_targeted.py` : harnais reproductible d'isolation.

Commande courte pour rejouer les 50 régressions depuis la racine :

```powershell
.\.venv\Scripts\python.exe .runtime/diagnostic-acceptance/review-fixes-2026-10-24/run_targeted.py backend/tests/test_review_fixes_2026_10_24.py -q
```

La suite backend complète n'a pas été relancée. Ces contrôles valident les
corrections dans leur périmètre ; ils ne constituent pas une qualification
réglementaire du KID/EMT ni une extension du domaine numérique du MTF.
