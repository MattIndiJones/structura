# Recette quantitative des profils intégrés — autocall 4 ans — 07/10/2026

**Le chemin de pricing API et les flux se réconcilient sur les 20 cas.**
Les contrôles numériques donnent 3 points signalés sur 600 calls, 600 puts et 600 digitaux ; 0 contrôles de forward et 0 contrôles temporels sont signalés.
La réplication indépendante ciblée des alertes multi, avec 20 000 paires par batch et huit nouvelles graines, donne 0 point signalé sur 80 calls, 80 puts et 80 digitaux. Les alertes de la passe principale restent visibles ci-dessous.
Les écarts de calibration Heston/SABR restent distincts de ces contrôles et de l’incertitude Monte Carlo.

## Périmètre et produit

Reprise du scénario précédent, avec les profils réellement fabriqués par `frontend/src/utils/volSurface.js`, la calibration du service `smile_calibration.py`, les schémas Pydantic et la grille LV/LSV de production `_build_lv_grid`. Aucune grille de surface externe n’est injectée dans la simulation.

- Athena quatre ans : coupon cumulé de 10 % par observation, payé au rappel à 100 %, y compris au quatrième constat.
- Sans rappel : capital 1, put vendu européen sous 60 %, sans coupon. Capital, coupons et put sont des flux distincts.
- StartDate = value date : 06/10/2026, conservée pour la comparaison. Observations : 06/10/2027, 06/10/2028, 08/10/2029, 07/10/2030.
- Paiements J+3 ouvrés TARGET : 11/10/2027, 11/10/2028, 11/10/2029, 10/10/2030. Actualisation aux paiements.
- EUR ; taux plat 3 %, dividende continu plat 2 %, funding nul, aucun quanto ou taux stochastique.
- Mono SG ; worst-of SG/STMicro, browniens de spot corrélés à 50 %. Les deux actifs reçoivent la même surface hypothétique.
- Actions ATM 30 % : défaut sans estimation de niveau. Actions ATM 20 % : contrôle au niveau de l’ancienne étude.
- Aucune acquisition de cotation d’options ou de données Yahoo ; les tickers désignent le scénario, pas une calibration de ces titres.

## Surface réellement utilisée

Piliers ATM 3 mois, 6 mois, 1, 2, 3, 5, 7 et 10 ans, initialement plats. Profil Actions : ρ = −0,75, η = 0,85, échelle 0,04 ; variance totale ATM croissante et certification SSVI sur 10 ans. Le niveau entre dans θ(t) et modifie donc aussi la forme relative du smile.

| Niveau ATM forward | K/F | Vol 1 an | Vol 4 ans |
|---|---:|---:|---:|
| 20 % | 60 % | 30,10 % | 26,73 % |
| 20 % | 80 % | 24,78 % | 23,09 % |
| 20 % | 100 % | 20,00 % | 20,00 % |
| 20 % | 120 % | 16,00 % | 17,41 % |
| 20 % | 140 % | 13,80 % | 15,43 % |
| 30 % | 60 % | 42,25 % | 37,33 % |
| 30 % | 80 % | 35,70 % | 33,31 % |
| 30 % | 100 % | 30,00 % | 30,00 % |
| 30 % | 120 % | 25,21 % | 27,24 % |
| 30 % | 140 % | 21,92 % | 24,98 % |

Le tableau ci-dessus est en strike/forward, comme l’éditeur. Les vanilles de contrôle sont en strike/spot initial ; leur référence inclut le carry de 1 %.

[Graphique des surfaces et des prix avec IC95](../../output/integrated-smile-20261007/comparison.png)

## Résultats à 208 pas/an

Huit batches indépendants de 20 000 paires antithétiques en mono et 10 000 en multi, graines 42, 17, 93, 731, 2026, 77, 123 et 991 : 320 000 / 160 000 trajectoires par cas, y compris LSV. Les IC95 utilisent Student à sept degrés de liberté entre batches, pour inclure la dépendance entre particules LSV. Les écarts au constant utilisent les différences par batch avec les mêmes browniens.

### Actions — ATM 30 %

| Modèle | Mono (% nominal) | IC95 mono | Δ constant (points) | Worst-of (% nominal) | IC95 worst-of | Δ constant (points) |
|---|---:|---|---:|---:|---|---:|
| Constant / GBM | 92,2059 | 92,0854–92,3264 | 0,0000 | 81,6882 | 81,5933–81,7831 | 0,0000 |
| Heston | 93,0439 | 92,9500–93,1378 | 0,8380 | 81,9638 | 81,8040–82,1237 | 0,2756 |
| SABR spot | 92,3501 | 92,2148–92,4855 | 0,1442 | 80,8039 | 80,6103–80,9975 | -0,8843 |
| Local Vol | 92,1246 | 92,0008–92,2484 | -0,0813 | 81,3032 | 81,1491–81,4572 | -0,3850 |
| LSV | 92,9129 | 92,7973–93,0286 | 0,7070 | 81,6449 | 81,4359–81,8539 | -0,0433 |

| Cas / modèle | PV capital | PV coupons | PV put vendu | Rappel avant maturité |
|---|---:|---:|---:|---:|
| Mono / Constant / GBM | 93,2296 % | 9,3853 % | -10,4090 % | 62,56 % |
| Mono / Heston | 94,1073 % | 9,6191 % | -10,6825 % | 71,89 % |
| Mono / SABR spot | 93,9567 % | 9,9615 % | -11,5681 % | 71,16 % |
| Mono / Local Vol | 94,0811 % | 9,9523 % | -11,9088 % | 72,32 % |
| Mono / LSV | 94,0353 % | 9,6936 % | -10,8160 % | 71,30 % |
| Worst-of / Constant / GBM | 91,7705 % | 7,4564 % | -17,5387 % | 44,43 % |
| Worst-of / Heston | 92,7218 % | 8,3276 % | -19,0855 % | 55,74 % |
| Worst-of / SABR spot | 92,5796 % | 8,7068 % | -20,4826 % | 55,10 % |
| Worst-of / Local Vol | 92,7330 % | 8,7430 % | -20,1728 % | 56,63 % |
| Worst-of / LSV | 92,6318 % | 8,3619 % | -19,3487 % | 54,90 % |

Local Vol mono : Δ constant = -0,0813 point ; IC95 de la différence -0,1340 à -0,0285 point.

Local Vol worst-of : Δ constant = -0,3850 point ; IC95 de la différence -0,4926 à -0,2774 point.

### Actions — ATM 20 %

| Modèle | Mono (% nominal) | IC95 mono | Δ constant (points) | Worst-of (% nominal) | IC95 worst-of | Δ constant (points) |
|---|---:|---|---:|---:|---|---:|
| Constant / GBM | 98,9911 | 98,9128–99,0695 | 0,0000 | 92,4393 | 92,3595–92,5191 | 0,0000 |
| Heston | 98,3549 | 98,2931–98,4166 | -0,6362 | 90,8053 | 90,6630–90,9476 | -1,6340 |
| SABR spot | 98,0620 | 97,9914–98,1326 | -0,9291 | 90,1897 | 90,0519–90,3274 | -2,2497 |
| Local Vol | 98,0254 | 97,9244–98,1264 | -0,9657 | 90,5789 | 90,4286–90,7291 | -1,8604 |
| LSV | 98,3383 | 98,2571–98,4194 | -0,6528 | 90,7008 | 90,5453–90,8563 | -1,7385 |

| Cas / modèle | PV capital | PV coupons | PV put vendu | Rappel avant maturité |
|---|---:|---:|---:|---:|
| Mono / Constant / GBM | 93,4906 % | 9,9184 % | -4,4179 % | 66,12 % |
| Mono / Heston | 94,2527 % | 10,1831 % | -6,0810 % | 74,38 % |
| Mono / SABR spot | 94,1144 % | 10,4088 % | -6,4611 % | 73,48 % |
| Mono / Local Vol | 94,2342 % | 10,4959 % | -6,7046 % | 74,79 % |
| Mono / LSV | 94,1977 % | 10,2580 % | -6,1174 % | 73,96 % |
| Worst-of / Constant / GBM | 92,0569 % | 8,2474 % | -7,8650 % | 48,63 % |
| Worst-of / Heston | 92,9193 % | 9,1234 % | -11,2374 % | 59,17 % |
| Worst-of / SABR spot | 92,7693 % | 9,3526 % | -11,9323 % | 58,07 % |
| Worst-of / Local Vol | 92,9168 % | 9,5039 % | -11,8418 % | 59,79 % |
| Worst-of / LSV | 92,8463 % | 9,1673 % | -11,3128 % | 58,48 % |

Local Vol mono : Δ constant = -0,9657 point ; IC95 de la différence -1,0122 à -0,9192 point.

Local Vol worst-of : Δ constant = -1,8604 point ; IC95 de la différence -1,9704 à -1,7505 point.

## Pourquoi l’effet du smile varie avec le niveau

La jambe put vendue devient plus coûteuse avec l’aile gauche. Mais le smile modifie aussi les rappels, les coupons reçus et la date de remboursement du capital. Le prix de la note est la somme de ces trois PV ; le coût supplémentaire du put ne mesure donc pas à lui seul l’écart au constant.

| ATM | Cas | Δ PV capital LV − GBM | Δ PV coupons | Δ PV put vendu | Δ prix total |
|---|---|---:|---:|---:|---:|
| 30 % | Mono | 0,8515 pt | 0,5670 pt | -1,4998 pt | -0,0813 pt |
| 30 % | Worst-of | 0,9625 pt | 1,2866 pt | -2,6342 pt | -0,3850 pt |
| 20 % | Mono | 0,7435 pt | 0,5775 pt | -2,2867 pt | -0,9657 pt |
| 20 % | Worst-of | 0,8599 pt | 1,2565 pt | -3,9768 pt | -1,8604 pt |

Ces mesures concernent ce payoff et cette famille de profils. La forme relative du smile s’atténue avec le niveau et la maturité ; aucun écart de prix fixé à l’avance n’est ajouté au moteur.

Local Vol et LSV visent les mêmes marginales vanilles. Cela ne fixe pas leur dépendance entre dates, ni la perte conditionnelle à l’absence de rappel. Leur différence sur l’autocall peut donc subsister même lorsque les contrôles de vanilles et de digitaux passent. En multi, une même corrélation de browniens ne fixe pas non plus la même dépendance terminale.

## Calibration et validations indépendantes

| ATM | Modèle | Erreur vanille annoncée au fit | Max vanille modèle / cible, contrôle indépendant | Max digital modèle / cible |
|---|---|---:|---:|---:|
| 20 % | Heston | 20,03 bps | 20,03 bps | 91,53 bps |
| 20 % | SABR spot | 74,44 bps | 79,23 bps | 237,35 bps |
| 30 % | Heston | 32,84 bps | 32,81 bps | 108,79 bps |
| 30 % | SABR spot | 130,63 bps | 142,82 bps | 402,97 bps |

Un optimiseur qui converge ne certifie pas la reproduction du smile. Heston ajuste cinq paramètres constants par Fourier ; SABR ajuste quatre paramètres par Monte Carlo avec 3 000 paires, 104 pas/an et graine 353. Le contrôle final utilise d’autres graines et une PDE SABR indépendante : il mesure aussi le bruit et le biais de cet ajustement.

La première passe, à 10 000 paires par batch dans les deux dimensions, signalait 42 points de vanilles/digitaux, dont certains sous GBM. Le nombre de paires a ensuite été doublé pour **tous** les modèles mono et les deux niveaux, avec conservation des premières estimations dans `initial-pricing.json` et `initial-results.json`. Les graines, seuils, paramètres et références restent identiques. Les tableaux présentent cette seconde passe en mono ; aucune alerte finale n’est supprimée.

Références : Black-Scholes pour GBM, Fourier adaptatif pour Heston, PDE spot/log-alpha pour SABR, prix et dérivée de strike SSVI pour LV/LSV. Les digitaux sont des cash puts sous le strike. Maturités : les quatre temps de grille effectivement observés ; strikes/spot initial : 60, 80, 100, 120 et 150 %. Tolérances : 2 bps vanille, 10 bps digital, plus trois erreurs standards entre batches ; pour SABR, ajout de l’enveloppe de raffinement et d’extension de domaine PDE.

| ATM | Cas | Modèle | Calls signalés | Puts signalés | Digitaux signalés | Forward signalé |
|---|---|---|---:|---:|---:|---:|
| 20 % | Mono | Constant / GBM | 0 | 0 | 0 | 0 |
| 20 % | Mono | Heston | 0 | 0 | 0 | 0 |
| 20 % | Mono | SABR spot | 0 | 0 | 0 | 0 |
| 20 % | Mono | Local Vol | 0 | 0 | 0 | 0 |
| 20 % | Mono | LSV | 0 | 0 | 0 | 0 |
| 20 % | Worst-of | Constant / GBM | 0 | 0 | 0 | 0 |
| 20 % | Worst-of | Heston | 0 | 0 | 0 | 0 |
| 20 % | Worst-of | SABR spot | 0 | 0 | 0 | 0 |
| 20 % | Worst-of | Local Vol | 0 | 0 | 0 | 0 |
| 20 % | Worst-of | LSV | 0 | 0 | 0 | 0 |
| 30 % | Mono | Constant / GBM | 0 | 0 | 0 | 0 |
| 30 % | Mono | Heston | 0 | 0 | 0 | 0 |
| 30 % | Mono | SABR spot | 0 | 0 | 0 | 0 |
| 30 % | Mono | Local Vol | 0 | 0 | 0 | 0 |
| 30 % | Mono | LSV | 0 | 0 | 0 | 0 |
| 30 % | Worst-of | Constant / GBM | 2 | 0 | 0 | 0 |
| 30 % | Worst-of | Heston | 0 | 0 | 0 | 0 |
| 30 % | Worst-of | SABR spot | 0 | 0 | 0 | 0 |
| 30 % | Worst-of | Local Vol | 1 | 0 | 0 | 0 |
| 30 % | Worst-of | LSV | 0 | 0 | 0 | 0 |

### Réplication indépendante des alertes multi à 30 %

GBM et Local Vol sont recalculés à 208 pas/an avec huit batches de 20 000 paires et les nouvelles graines 4242, 1717, 9393, 731731, 20262026, 7777, 123123 et 991991. Aucun seuil ni paramètre de modèle n’est changé. Le premier essai à 30 000 paires a été refusé par la limite mémoire du calcul ; le budget est respecté avec 20 000.

| Modèle | Actif | Maturité effective | Strike / S0 | Écart call initial | Seuil initial | Écart call réplication | Seuil réplication | Signal réplication |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Constant / GBM | 2 | 0,999483 | 60 % | 7,725 bps | 7,705 bps | -3,052 bps | 5,880 bps | Non |
| Constant / GBM | 2 | 0,999483 | 80 % | 10,000 bps | 9,925 bps | -4,360 bps | 7,517 bps | Non |
| Local Vol | 2 | 0,999483 | 120 % | 6,369 bps | 6,335 bps | -0,357 bps | 5,034 bps | Non |

Les prix multi de cette réplication sont GBM 81,6678 % et Local Vol 81,2702 %, compatibles avec les estimations principales. Les petites alertes initiales sont cohérentes avec du bruit statistique ; une réplication sans alerte ne constitue pas une preuve universelle d’absence de biais.


### Convergence temporelle du prix

Huit batches de 3 000 paires. Browniens couplés sur l’union des grilles 52/104/208 ; mêmes paiements contractuels. Signal si |variation| > 5 bps + 3 SE. Ce seuil est un contrôle statistique, pas une garantie d’un biais inférieur à 5 bps.

| ATM | Cas | Modèle | 208 − 52 (bps) | SE (bps) | Signal | 208 − 104 (bps) | SE (bps) | Signal |
|---|---|---|---:|---:|---|---:|---:|---|
| 20 % | Mono | Constant / GBM | 1,04 | 1,01 | Non | 1,04 | 1,01 | Non |
| 20 % | Mono | Heston | 0,25 | 2,11 | Non | -1,18 | 1,95 | Non |
| 20 % | Mono | SABR spot | 3,22 | 3,40 | Non | -0,59 | 1,66 | Non |
| 20 % | Mono | Local Vol | 6,52 | 1,55 | Non | 2,25 | 1,66 | Non |
| 20 % | Mono | LSV | 4,73 | 1,73 | Non | 3,15 | 2,17 | Non |
| 20 % | Worst-of | Constant / GBM | -1,49 | 1,16 | Non | -1,49 | 1,16 | Non |
| 20 % | Worst-of | Heston | -2,80 | 2,84 | Non | -1,87 | 2,23 | Non |
| 20 % | Worst-of | SABR spot | 0,92 | 3,45 | Non | -0,66 | 3,40 | Non |
| 20 % | Worst-of | Local Vol | 2,78 | 3,40 | Non | 0,98 | 3,01 | Non |
| 20 % | Worst-of | LSV | -0,52 | 4,10 | Non | -5,75 | 1,67 | Non |
| 30 % | Mono | Constant / GBM | 1,79 | 2,47 | Non | 1,79 | 2,47 | Non |
| 30 % | Mono | Heston | -2,60 | 1,91 | Non | -1,73 | 2,51 | Non |
| 30 % | Mono | SABR spot | 9,98 | 3,92 | Non | 4,72 | 4,55 | Non |
| 30 % | Mono | Local Vol | 13,22 | 3,30 | Non | 8,46 | 2,65 | Non |
| 30 % | Mono | LSV | 5,63 | 3,76 | Non | 2,02 | 1,87 | Non |
| 30 % | Worst-of | Constant / GBM | -1,79 | 1,67 | Non | -1,79 | 1,67 | Non |
| 30 % | Worst-of | Heston | -2,63 | 4,47 | Non | 0,59 | 2,18 | Non |
| 30 % | Worst-of | SABR spot | 10,58 | 4,40 | Non | 4,09 | 3,42 | Non |
| 30 % | Worst-of | Local Vol | 5,91 | 4,41 | Non | -0,23 | 2,54 | Non |
| 30 % | Worst-of | LSV | 10,15 | 7,07 | Non | 6,39 | 3,78 | Non |

Local Vol à 30 % est ensuite revérifié avec **10 000 paires par batch**, pour réduire l’incertitude des écarts de discrétisation observés. Les deux grilles grossières sont comparées à 208 pas/an avec les mêmes seuils.

| Cas | Grille grossière | 208 − grille grossière | SE | Signal |
|---|---:|---:|---:|---|
| Mono | 52 | 8,28 bps | 1,47 bps | Non |
| Mono | 104 | 3,49 bps | 2,02 bps | Non |
| Worst-of | 52 | 6,11 bps | 1,01 bps | Non |
| Worst-of | 104 | 2,58 bps | 1,19 bps | Non |

## Recette d’intégration et limites

- 20 calculs par appel direct de `price_endpoint`, au défaut applicatif de 52 pas/an, 3 000 paires : capital total égal à 1, réconciliation des PV et accord avec une évaluation indépendante des flux sur les mêmes diffusions à moins de 10⁻⁶.
- 12 repricings supplémentaires, au défaut de 52 pas/an et 10 000 paires, utilisent les fonctions d’édition de la courbe : translation de tous les piliers ATM de +1 point et déplacement de la poignée 80 % de +1 point de vol à 1 an. La translation modifie GBM et LV ; l’aile modifie LV et laisse exactement GBM inchangé, en mono comme en multi. Valeurs et variations mesurées dans `edits.json` ; cela valide les fonctions et leur consommation, pas un nouveau geste dans le navigateur.
- 9 tests backend ciblés de surface et 11 tests frontend ciblés de surface/calibration passent. Les profils Actions/Indices, l’édition de courbe/cellule et les conversions RFQ sont couverts par ces tests ; aucune nouvelle recette navigateur effectuée dans cette étude.
- La base réelle reste inchangée. Aucun serveur lancé, aucune suite backend complète, aucun commit ni push.
- Les prix affinés à 208 pas/an viennent des diffusions de production et d’un calcul indépendant du payoff ; le contrôle API à 52 établit leur cohérence avec PayScript. Le réglage de l’application reste 52 pas/an.
- Les IC95 ne couvrent ni le résidu de calibration, ni le biais numérique, ni le risque de modèle ou de corrélation. Une même corrélation de browniens ne fixe pas la même dépendance terminale entre modèles.
- Le profil Indices est vérifié par les tests ciblés, mais les 20 prix de cette étude concernent le profil Actions ; ni pricing résiduel, ni Greeks, ni courbes non plates ne sont recettés quantitativement ici.
- La largeur du smile et le payoff déterminent l’effet mesuré. Une baisse de plusieurs points en Local Vol n’est pas imposée comme résultat attendu.

## Reproduction

Depuis la racine du dépôt, Python du venv avec `-X utf8` :

```powershell
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage calibration
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage api
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage pricing
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage references
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage convergence
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage finalize
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage refine-mono
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage merge-refinement
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage finalize
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage edits
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage verification
.venv/Scripts/python.exe -X utf8 -c "from backend.scripts.study_integrated_smile import finalize; finalize('verification', 'verification-results')"
.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage temporal-lv
.venv/Scripts/python.exe -X utf8 backend/scripts/report_integrated_smile.py
```

Les requêtes, surfaces, paramètres, receipts, flux, prix par batch, références PDE, seuils, contrôles et empreintes des sources sont conservés dans `output/integrated-smile-20261007/`. Les anciennes études restent intactes.
