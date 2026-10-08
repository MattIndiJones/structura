# Autocall quatre ans — cible commune sans arbitrage — 07/10/2026

Les dix prix sont calculés avec les mêmes conventions contractuelles et une cible SSVI synthétique.
**Les contrôles numériques passent dans le régime testé. La reproduction de la cible reste approximative pour Heston et insuffisante pour SABR à paramètres constants.**
Leurs prix ci-dessous sont des valorisations de ces ajustements paramétriques ; leurs écarts aux autres modèles ne mesurent pas uniquement le risque de dynamique.
Local Vol et LSV reproduisent la même cible dans la tolérance du contrôle ; leur comparaison est la plus directement interprétable.

## Payoff et hypothèses

- Coupon cumulé de 10 % par observation, payé uniquement au rappel à 100 %, y compris au dernier constat.
- Quatre observations annuelles ; protection européenne à 60 %. Sans rappel : capital 1 et put vendu séparé, sans coupon.
- StartDate et value date : 06/10/2026 ; observations 06/10/2027, 06/10/2028, 08/10/2029 et 07/10/2030.
- Paiements : 11/10/2027, 11/10/2028, 11/10/2029 et 10/10/2030, soit J+3 ouvrés TARGET.
- Taux 3 %, dividendes continus 2 % par actif, corrélation des browniens de spot 50 %, EUR, sans funding ni quanto.
- Mono Société Générale ; worst-of Société Générale / STMicro : identités de scénario, avec la même surface synthétique pour les deux actifs. Aucune donnée de marché de ces titres.

## Surface et calibration

SSVI en log-moneyness forward : `theta(t)=0.04*t`, `rho=-0.75`, `phi(theta)=0.85/sqrt(0.04+theta)`, horizon certifié cinq ans.
Les conditions suffisantes de Gatheral-Jacquier sont vérifiées sur tout cet horizon et pour tous les strikes : borne de pente 0,6073 < 4, borne de courbure 1,0537 < 4 ; variance totale croissante à log-moneyness forward fixe.
Référence : [Gatheral et Jacquier, Arbitrage-free SVI volatility surfaces](https://arxiv.org/abs/1204.0646). Les dérivées de Dupire sont analytiques ; aucune aile polynomiale ni fallback silencieux.

| Strike / S0 | Vol cible 1 an | Vol cible 4 ans |
|---|---:|---:|
| 60 % | 30,2711 % | 27,2029 % |
| 80 % | 24,9792 % | 23,6197 % |
| 100 % | 20,2251 % | 20,5681 % |
| 120 % | 16,2024 % | 17,9671 % |

Le niveau de 20 % est l’ATM **forward** ; le strike égal au spot initial a une vol légèrement différente à cause du carry.

| Modèle | Paramètres ajustés | Reproduction de cible |
|---|---|---|
| Heston | v0=0.043321, theta=0.071067, kappa=0.382688, xi=0.312510, rho=-0.782479 | Ajustement approximatif |
| SABR | alpha=0.207557, beta=1.000000, rho=-0.814368, nu=0.456365 | Insuffisante ; beta atteint sa borne haute |
| Local Vol | Dupire analytique de SSVI | Contrôle MC de reproduction satisfait |
| LSV | Cible Dupire SSVI et variance du Heston ajusté | Contrôle MC de reproduction satisfait |
| GBM | Sigma constant 20 % | Référence ATM, sans ajustement du smile |

Heston est ajusté en prix avec pondération vega et contrôlé par Fourier indépendant. SABR est initialisé par Hagan puis ajusté sur les options OTM du Monte Carlo réellement simulé : 6 000 paires, 104 pas/an, graine 353. La validation finale utilise huit autres graines et une PDE indépendante aux paramètres ajustés.

| Modèle | Écart maximal vanille modèle / cible | Écart maximal digital modèle / cible |
|---|---:|---:|
| Heston | 19,76 bps | 99,83 bps |
| SABR | 84,12 bps | 226,52 bps |

Il s’agit d’écarts de **calibration** : ils persistent quand les simulateurs retrouvent correctement les prix de leur propre modèle. Les IC Monte Carlo ci-dessous ne les incluent pas.

## Prix et incertitude

| Modèle | Mono (% nominal) | IC95 mono | Worst-of (% nominal) | IC95 worst-of |
|---|---:|---|---:|---|
| GBM | 98,9911 | 98,9128–99,0695 | 92,4393 | 92,3595–92,5191 |
| Heston | 98,3642 | 98,3069–98,4214 | 90,8112 | 90,6674–90,9551 |
| SABR | 98,0975 | 98,0155–98,1796 | 90,4201 | 90,2826–90,5577 |
| Local Vol | 98,0253 | 97,9249–98,1257 | 90,5791 | 90,4290–90,7292 |
| LSV | 98,3512 | 98,2754–98,4271 | 90,6896 | 90,5164–90,8627 |

208 pas/an ; huit graines indépendantes : 42, 17, 93, 731, 2026, 77, 123 et 991. Chaque batch contient 20 000 paires en mono, 10 000 en multi, soit 320 000 / 160 000 trajectoires au total par modèle.
IC95 calculés entre batches avec Student à sept degrés de liberté, afin de prendre en compte la dépendance entre particules LSV. Ils restent estimés sur huit réplications ; ils ne couvrent ni le biais de calibration ni le risque de modèle.

## Flux séparés et rappels

Toutes les trajectoires paient exactement une jambe de capital. Capital + coupons + put réconcilient chaque prix à l’arrondi flottant.

| Cas | Modèle | PV capital | PV coupons | PV put vendu | Rappel avant maturité |
|---|---|---:|---:|---:|---:|
| Mono | GBM | 93,4906 % | 9,9184 % | -4,4179 % | 66,12 % |
| Mono | Heston | 94,2626 % | 10,1766 % | -6,0751 % | 74,46 % |
| Mono | SABR | 94,0831 % | 10,3777 % | -6,3633 % | 73,10 % |
| Mono | Local Vol | 94,2343 % | 10,4957 % | -6,7046 % | 74,79 % |
| Mono | LSV | 94,1961 % | 10,2514 % | -6,0963 % | 73,92 % |
| Worst-of | GBM | 92,0569 % | 8,2474 % | -7,8650 % | 48,63 % |
| Worst-of | Heston | 92,9291 % | 9,1239 % | -11,2418 % | 59,27 % |
| Worst-of | SABR | 92,7359 % | 9,3077 % | -11,6234 % | 57,61 % |
| Worst-of | Local Vol | 92,9170 % | 9,5034 % | -11,8414 % | 59,79 % |
| Worst-of | LSV | 92,8414 % | 9,1477 % | -11,2996 % | 58,40 % |

Les probabilités de rappel par observation et les flux par date de paiement sont dans le JSON de résultats.

## Comparaison à cible reproduite : LSV / Local Vol

Les mêmes graines et browniens de spot sont utilisés dans cette différence ; son incertitude est calculée entre les huit différences de batches.
- Mono : LSV − Local Vol = 32,59 bps ; IC95 26,60 à 38,58 bps.
- Worst-of : LSV − Local Vol = 11,05 bps ; IC95 0,66 à 21,44 bps.

En multi, la différence inclut aussi la dynamique de dépendance : une corrélation de browniens identique ne fixe pas une copule terminale identique.

## Contrôles et limites

- Réserves numériques initiales : huit batches de 25 000 paires sur deux actifs, contrôles aux maturités 6 mois / 1 an, 52 / 104 / 208 pas/an. Tolérances préalables : 2 bps vanille et 10 bps digital, plus trois erreurs standards entre batches. Aucun point signalé à 208 pas/an pour SABR natif et LSV plat.
- Validation des paramètres ajustés : 450 calls, 450 puts et 450 digitaux sur les cinq moteurs mono / marginales multi. Références propres : BS, Fourier Heston, PDE spot SABR, SSVI pour LV/LSV. Aucun point signalé sur cette grille.
- PDE SABR ajusté : raffinement et extension de domaine vérifiés ; enveloppe numérique ajoutée au seuil MC. Les résultats de convergence figurent dans le JSON.
- Contrôle de prix : 104 → 208 pas/an avec browniens couplés sur l’union des deux grilles, huit batches de 5 000 paires, seuil 5 bps plus trois erreurs standards de la différence.

| Cas | Modèle | Variation 208 − 104 | SE de la différence | Signalé |
|---|---|---:|---:|---|
| Mono | GBM | 0,85 bps | 0,70 bps | Non |
| Mono | Heston | -1,04 bps | 1,53 bps | Non |
| Mono | SABR | -2,19 bps | 2,09 bps | Non |
| Mono | Local Vol | 0,59 bps | 2,39 bps | Non |
| Mono | LSV | 1,73 bps | 1,53 bps | Non |
| Worst-of | GBM | -0,98 bps | 1,53 bps | Non |
| Worst-of | Heston | -2,20 bps | 1,33 bps | Non |
| Worst-of | SABR | 1,08 bps | 1,69 bps | Non |
| Worst-of | Local Vol | -0,34 bps | 1,72 bps | Non |
| Worst-of | LSV | 0,75 bps | 3,08 bps | Non |

Les dates de constatation sont quantifiées sur les grilles de simulation. La maturité du produit est atteinte exactement et les flux sont actualisés aux dates contractuelles de paiement. Les fractions d’année effectives des vanilles sont conservées et utilisées dans leurs références.
Le contrôle temporel emploie de petits batches LSV : il ne remplace pas une étude exhaustive de convergence en nombre de particules. Les batches de précision initiale et de pricing final utilisent également des régimes de variance différents, explicitement conservés dans les résultats.

## Livraison et reproduction

Livraison sous forme d’un benchmark hors interface : cible analytique réutilisable, calibration, contrôles et calcul indépendant des flux sur les simulateurs de production. Le pas de temps par défaut de l’application reste 52/an ; ces prix utilisent explicitement 208/an. La surface n’est pas un nouveau formulaire du Pricer et ces calibrations ne sont pas injectées dans des deals.
Le moteur LSV conserve désormais sa résolution conditionnelle lorsque le benchmark fournit une grille locale plus large. Le chemin historique sur [0,2 ; 3] reste à 200 buckets, vérifié par les goldens.
**29 tests ciblés passent** : six contrôles nouveaux SSVI/payoff, treize contrôles du lot précédent et dix goldens de modèles. Aucune suite backend complète, aucun changement frontend, aucune base réelle utilisée.

```powershell
.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage precision
.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage calibration
.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage reference
.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage pricing
.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage convergence
.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage finalize
.venv/Scripts/python.exe -X utf8 backend/scripts/report_common_surface.py
```

- [Cible SSVI](../../backend/app/core/volatility_surface.py)
- [Programme de comparaison](../../backend/scripts/compare_common_surface.py)
- [Prix, flux, probabilités et références](../../output/common-surface-20261007/autocalls.json)
- [Calibration](../../output/common-surface-20261007/calibration.json)
- [Précision native](../../output/common-surface-20261007/precision.json)
- [Convergence des prix](../../output/common-surface-20261007/convergence.json)
- [Graphique](../../output/common-surface-20261007/comparison.png)

La suite pertinente pour une comparaison plus stricte est d’améliorer la reproduction des digitaux par les modèles paramétriques, particulièrement SABR, puis d’intégrer un choix explicite de surface et de précision dans le workflow de l’application. Les dix prix actuels restent associés aux hypothèses et réserves ci-dessus.
