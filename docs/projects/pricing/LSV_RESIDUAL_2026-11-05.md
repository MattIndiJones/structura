# LSV résiduel : STM et SG–STM — 05/11/2026

## Correction

Les valorisations résiduelles SSVI portent maintenant un ancrage explicite au spot courant dans `ValuationContext.local_vol_anchor`. Les trajectoires et le payoff restent en unités du strike contractuel ; seule la recherche de volatilité/leverage utilise le rapport au spot courant. Le cadre est commun à Dupire et LSV. Les anciens contextes archivés sans ce champ conservent leur convention historique.

La surface et ses paramètres de maturité sont repris comme hypothèses de marché à la date du MtM (moneyness forward et tenors depuis cette date). Le `v0` du contexte est une hypothèse de variance initiale, pas une mesure observée ni une variance filtrée depuis l’historique. Les fixings, mémoire, extrema et compteur d’observations du produit sont repris séparément depuis le rejeu.

Le LSV résiduel utilise le levier estimé sur un échantillon indépendant puis figé, et non l’ancien ajustement particulaire dans chaque lot de pricing. Le MTF conserve ensuite cet ancrage, le même levier et son horloge, et transmet la variance simulée outer→inner. Aucune recalibration ni remise à v0 dans les repricings futurs. Les Greeks maintiennent l’ancrage de marché de leur contexte pour leurs chocs locaux ; l’attribution entre deux contextes déplace l’ancrage avec le spot.

## Qualification, caps et limites

- Plafond de volatilité effective **300 % inchangé**, bornes du levier **0,2–5 inchangées**.
- Prolongement SSVI uniquement selon la règle existante : dépassement contigu à une extrémité et entièrement hors 20–180 % du forward. Refus conservés dans la zone protégée, aux points intérieurs et pour des valeurs non finies/non positives.
- Calibration résiduelle : **131 072 particules**, graine 94607 ; contrôle indépendant : **1 048 576 chemins**, graines fixes 19213, 48017, 73417, 91691. Ces tirages sont distincts du pricing et du MTF.
- Qualification du levier **par rapport à Dupire sur la même grille numérique** : `abs(écart) + demi-IC95 ≤ 5 pb` sur vanilles et `≤ 10 pb` sur digitales. Prix de contrôle normalisés au spot courant. Niveaux 60/100/120 % du spot courant et barrières scalaires détectées dans les monitors, converties depuis le strike du contrat ; dates d’observation résiduelles, maturité et voisinage de six mois.
- Contrôles : intégration analytique du dernier pas et contrôle de martingale de coefficient analytique fixé à l’avance. Cette réduction de variance ne modifie pas l’espérance estimée. Aucun assouplissement des seuils. Le premier essai à 208, avec 65 536 particules, donnait notamment +4,13 ±1,02 pb : refus maintenu, puis précision renforcée.
- Comparaison directe distincte avec la surface SSVI continue, au moyen de prix Black–Scholes utilisant les vols de chaque strike. Les digitales proviennent de la dérivée du prix complet selon le strike, avec le smile ; elles ne sont pas des digitales BS à volatilité de strike gelée.

**La qualification relative du levier ne garantit pas une précision absolue de 5/10 pb par rapport à SSVI.** Sur STM à 52 pas/an, un contrôle à environ six mois donne pour Dupire +14,88 ±5,48 pb sur une vanille à 120 %, et +44,10 ±8,56 pb sur une digitale ATM. Le LSV partage ce biais de discrétisation. Ces écarts sont affichés séparément dans le Pricer, le Booking et les résultats MTF quand disponibles ; la grille doit être affinée pour les réduire. Les seuils du levier ne servent pas à masquer ce biais.

Périmètre : SSVI par sous-jacent, taux et dividendes plats, sans quanto, monitoring sur grille MC, après fixing initial. Le MTF reste soumis au budget cumulé, qui compte le contrôle renforcé : une grille fine peut nécessiter de réduire le calcul ou rester hors budget. Aucune ouverture implicite du CCR/KID.

## Recette numérique

Athena 3 ans à coupon cumulé 10 %, rappel 100 %, protection européenne 60 %, règlements J+3 TARGET, données et SQLite isolées. Strike 29/10/2025, maturité ajustée 30/10/2028, date de MtM 05/11/2026. Une observation passée sans rappel, spots courants à 90 % du strike.

Hypothèses : ATM STM 54,646136 %, q 0,7388 % ; ATM SG 34,952353 %, q 2,8009 % ; corrélation 0,32012317 ; r 3 %, sans funding. Smile Actions SSVI rho −0,75, intensité 0,85, shape_scale 0,04, ATM plate 1–10 ans. Variance Heston : v0=theta=ATM², kappa=2, xi=0,35, rho_H=−0,7.

Prix sur **8 192 paires antithétiques**, graine 42. La dernière colonne est la pire borne `abs(écart)+demi-IC95` de qualification du levier, et non l’erreur du prix Athena.

| Panier | Pas/an | MtM LSV | MtM Dupire | LSV − Dupire | Rappel LSV / Dupire | Borne vanille / digitale |
|---|---:|---:|---:|---:|---:|---:|
| STM | 52 | 84.0657 % | 83.5655 % | +50.02 pb | 55.9 / 55.7 % | 2.93 / 5.44 pb |
| STM | 104 | 83.8879 % | 83.5357 % | +35.22 pb | 55.8 / 55.8 % | 4.16 / 7.76 pb |
| STM | 208 | 83.6668 % | 83.4105 % | +25.63 pb | 55.9 / 55.7 % | 4.49 / 6.74 pb |
| SG-STM | 52 | 69.8411 % | 69.6648 % | +17.63 pb | 33.6 / 33.6 % | 2.93 / 6.03 pb |
| SG-STM | 104 | 70.1279 % | 70.0045 % | +12.34 pb | 34.0 / 34.0 % | 4.16 / 7.76 pb |
| SG-STM | 208 | 70.1089 % | 69.8569 % | +25.20 pb | 33.6 / 33.4 % | 4.49 / 7.20 pb |

Les six cas sont qualifiés, bookés depuis un reçu signé, valorisés et rejoués à l’identique depuis l’archive. Le snapshot du booking est inchangé. Les écarts de prix et de rappel du tableau sont des estimations ponctuelles : cette recette ne prouve ni leur significativité ni leur convergence. Elle n’exige pas l’égalité des prix d’Athena entre LSV et Dupire.

MTF à 52 pas/an, 200 scénarios extérieurs ×200 chemins intérieurs, référence indépendante à 8 192 paires : quatre calculs (deux modèles ×deux paniers). À chaque date, cash échu actualisé + MTM résiduel actualisé est rapproché de P0 avec l’incertitude extérieure et celle de la référence. Maximum observé `|z|=1.35`, donc inférieur à 1,96 pour tous les contrôles. Dernier MTM après règlement : zéro dans tous les scénarios. Le drill-down reproduit les marks ; écart maximal observé 0.00004900 point de nominal.

## Parcours, conservation et performance

Pricer résiduel, Booking, Greeks, scénarios, workers, MTF/drill-down et archives portent l’ancrage. La qualification conserve ses paramètres, taille de calibration, contrôles et empreinte du levier. Les caches dépendent de la grille, des paramètres et de la cible ; ils ne dépendent pas du nombre de chemins demandé pour le prix. Ils sont en mémoire du processus : un redémarrage ou un contexte différent nécessite une préparation.

Le premier calcul qualifié reste coûteux : environ 60/121/275 s pour STM et 114/195/250 s pour le panier dans cette recette partiellement mise en cache et exécutée avec d’autres contrôles simultanés. Ces temps ne sont pas des promesses de performance. Le repricing du panier dans le Pricer après préparation en cache a affiché 1 074 ms pour 1 000 chemins.

Validation navigateur sur installation isolée : MtM STM et SG–STM, réutilisation du cache, affichage séparé des diagnostics, reprise du Product dans le Pricer sans calibration Heston implicite, MTF LSV en cours de vie jusqu’à une dernière ligne à zéro après règlement. Aucun deal utilisateur modifié.

Tests ciblés : groupes de **81** et **67** cas backend passés (couverture partiellement commune), **2** contrôles MTF supplémentaires et **3** contrôles complémentaires sur horloge/variance/budget. Groupes antérieurs de 33 et 65 cas également passés pendant le développement. **997 tests frontend passés et build réussi**. Aucune suite backend complète lancée.

## Reproduction

Depuis la racine du dépôt, avec l’environnement de développement :

```powershell
.venv/Scripts/python.exe scripts/validate_lsv_residual.py --asof 2026-11-05
.venv/Scripts/python.exe scripts/validate_lsv_residual_mtf.py --asof 2026-11-05
```

Ces commandes utilisent uniquement des données synthétiques et des sessions SQLite isolées ; elles produisent leurs preuves sous `.runtime/lsv-residual-validation/`. Elles sont longues à froid à cause de la qualification indépendante. Les programmes renvoient un échec si un contrôle de recette échoue. Les preuves de cette livraison sont sous `.runtime/lsv-residual/` (JSON de contrôles, contextes, MTF et journaux).

Pas de commit ni push. Le serveur de recette est arrêté après vérification.
