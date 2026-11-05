# Grille de diffusion du Pricer et du MtM — 05/11/2026

## Comportement livré

- 52 pas/an par défaut ; 104 et 208 disponibles dans Marché & Paramètres.
- La fréquence est numérique. Les observations et dates de fixing contractuelles complètent la grille ; aucun échéancier du produit n’est déplacé.
- Le reçu signé du prix initial contient `steps_per_year`. Le booking le conserve dans `pricing_input` et `stepsPerYear` du snapshot, sans modifier les termes Product.
- Un MtM reprend la grille du booking par défaut. Le choix 52/104/208 reste libre et affiche une mention non bloquante si la référence du booking diffère. Cette mention existe dans le Booking et dans le Pricer ouvert depuis un deal.
- Les anciens dossiers sans fréquence utilisent 52. Une surcharge de MtM ne réécrit jamais le snapshot du deal.
- Les résultats, archives, rejeux, Greeks et rapports portent la fréquence effective. La restauration du MtM filtre la fréquence avant de choisir le dernier calcul compatible, y compris lorsque le dernier calcul global utilise une autre grille.

## Propagation et invariants

| Domaine | Traitement |
|---|---|
| Moteur GBM, Heston, SABR, Dupire, LSV | Fréquence liée au calcul par `ContextVar`, réinitialisée en sortie même sur erreur ; aucune mutation de `SY` partagé. |
| Budget | Temps et mémoire estimés selon la fréquence ; le pricing tient compte des dates contractuelles ajoutées. |
| Analytiques et workers | Champ sérialisé dans `ValuationContext`, scénarios, solveur et workers ; axes MTF et levier LSV utilisent le même contexte. |
| MTF / drill-down | Fréquence dans l’empreinte ; un drill-down d’une autre grille est refusé. |
| Booking / lifecycle | Snapshot signé conservé, réglage effectif distinct pour chaque valorisation. Une créance connue reste actualisée à son paiement, indépendamment de la fréquence, sans Monte Carlo. |
| Attribution de valo archivée | Contribution « Grille de diffusion » séparée, en fin de décomposition, quand les fréquences diffèrent ; avertissement conservé. |
| RFQ / Product / sauvegarde | La fréquence reste un réglage externe aux termes contractuels et suit le contexte de calcul et les entrées enregistrées. |

Le choix d’une autre grille déclenche un nouveau calcul. Une graine identique rend chaque configuration reproductible ; elle ne constitue pas un couplage brownien entre deux grilles. La contribution numérique peut donc aussi contenir du bruit Monte Carlo.

## Recette reproductible

Données synthétiques, SQLite isolées, aucun booking dans la base utilisateur. Athena à coupon cumulé 10 %, rappel 100 %, protection européenne 60 %, observations annuelles et règlements J+3. Hypothèses STM : ATM 54,646136 %, q 0,7388 % ; SG : ATM 34,952353 %, q 2,8009 % ; corrélation 0,32012317 ; smile Actions SSVI, rho −0,75, intensité 0,85 ; r 3 %.

- `backend/tests/test_simulation_grid.py` : 38 cas passés. Grilles 52/104/208 sur les cinq modèles ; concurrence et sortie sur erreur ; STM et SG–STM en Dupire et Heston, pricing → reçu signé → booking → MtM aux trois grilles → archivage/rejeu, sans mutation du deal ; MTF et drill-down GBM/Dupire ; anciens contextes ; refus LSV résiduel connu.
- `test_booking_mtm_daily.py` : restauration par fréquence et test HTTP des paramètres numériques ; les chaînes de requête HTTP sont converties avant validation de 52/104/208. Créance à trois jours identique aux trois fréquences.
- `test_valuation_notes.py` : grille séparée des effets de marché, contributions réconciliées avec l’écart total ; conservation du rejeu et des notes PDF.
- Autres régressions ciblées exécutées : `test_chaine_pricing_booking_mtm.py`, `test_mtm_explain.py`, `test_valuation_context.py`, `test_greeks_stateful.py`, `test_mtf_models.py`, `test_engine_golden.py`, `test_market_data_lot4.py`.
- Frontend : 994 tests passés, `npm run build` réussi. Contrôles navigateur sur une installation de recette isolée : reprise du booking à 104, avertissement et résultats à 52 et 208 pour SG–STM, puis STM à 104 ; sélecteur et avertissement du Pricer.

Les tests de chaîne utilisent 1 000 paires pour contrôler la propagation et le rejeu ; ils ne qualifient pas la convergence économique ou les P95. Le contrôle Heston émission/MtM est dans l’incertitude Monte Carlo : le calendrier d’émission est arrondi à six décimales, le résiduel utilise ACT/365.25 exact, ce qui peut changer l’indexation des chocs de variance sur un intervalle minuscule. L’identité bit à bit à l’émission est vérifiée en Dupire.

## Limite LSV détectée avant le correctif résiduel

**Corrigée ensuite le 05/11 :** voir [LSV résiduel](LSV_RESIDUAL_2026-11-05.md). Le paragraphe suivant conserve le constat de la recette initiale des grilles.

Le LSV à levier figé fonctionne à l’émission dans son périmètre existant. Le chemin résiduel avec `spot_base` ne réutilise actuellement pas ce levier et conserve son contrôle strict à 300 %. Sur STM, le smile Actions par défaut est donc refusé en MtM résiduel aux trois fréquences. Le panier contenant STM rencontre la même limite.

Vérification indépendante sur le code `HEAD` avant ce chantier et sur le code modifié, à 52 pas/an : même refus à **427,59 % de volatilité locale**, au niveau **1 % du spot de référence**, à **0,0096 an**. La recette Athena résiduelle datée atteint aussi 438,25 % à 208 pas/an. La fréquence ne corrige pas cette limite de modèle ; aucun passage implicite en GBM, changement d’intensité ou assouplissement du plafond n’est introduit.

Preuves locales détaillées et journaux sous `.runtime/grid-tests-*`, `.runtime/grid-ui-final.log` et `.runtime/grid-preview/`. Les services de recette sont arrêtés après vérification. Pas de commit ni push.
