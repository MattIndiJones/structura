# Autocall 4 ans : smile actions baissier renforcé — 06/10/2026

**Nouveau benchmark au 07/10 :** [autocalls sur cible SSVI commune sans arbitrage](../../audits/AUTOCALL_SURFACE_COMMUNE_2026-10-07.md),
avec contrôles numériques, incertitudes, flux séparés et réserves sur les
ajustements Heston/SABR. Les prix ci-dessous restent des sorties historiques.

**Réserve après revue :** ces sorties ne sont pas validées comme prix d’une
surface commune. Le smile cible renforcé présente un arbitrage dans son aile
basse ; l’écart de reproduction persiste avec un pas affiné. Voir
[l’audit complémentaire](../../audits/AUDIT_AUTOCALL_SMILE_2026-10-06.md).

Suite à la première [comparaison](COMPARAISON_AUTOCALL_4ANS_MODELES_2026-10-06.md). Dix nouveaux prix ont été calculés dans Structura, puis cinq calculs de contrôle sur options vanilles ont mesuré le smile effectivement simulé.

## Contrat et hypothèses

Le contrat et les données hors volatilité sont inchangés : Athena 4 ans, coupon annuel de 10 % cumulé et payé au rappel, rappel à 100 %, protection européenne à 60 %, observations annuelles. Aucun coupon si le produit ne rappelle jamais. Sous 60 % à maturité, le remboursement est égal à la performance finale. Mono Société Générale ; panier worst-of SG / STMicro avec corrélation des chocs spot de 50 %. Taux 3 %, dividendes 2 % par actif, EUR, sans funding, frais ni quanto.

StartDate et date de valeur : 06/10/2026 ; dernière observation le 07/10/2030, règlement final le 10/10/2030. Calendrier TARGET, following et J+3 ouvrés. Les paramètres sont des hypothèses synthétiques identiques pour les deux actifs ; aucune donnée de marché ou calibration aux titres concernés.

La première série comportait déjà du skew négatif. Cette série le renforce ; elle ne compare donc pas un smile à une première série entièrement plate.

## Paramètres de volatilité

Valeurs internes en fractions :

| Modèle | Première série | Série renforcée |
|---|---|---|
| GBM | `sigma=0.20` | Inchangé, témoin sans smile |
| Heston | `xi=0.35`, `rho_h=-0.70` | `xi=0.50`, `rho_h=-0.80` ; `v0=theta=0.04`, `kappa=2` inchangés |
| SABR | `rho=-0.30`, `nu=0.40` | `rho=-0.60`, `nu=0.50` ; `alpha=0.20`, `beta=0.50` inchangés |
| Local Vol | `skew=-0.10`, `curvature=0.05` | `skew=-0.20`, `curvature=0.10`, `sigma=0.20` inchangé |
| LSV | Cible Local Vol et variance Heston précédentes | Nouvelle cible Local Vol et nouveaux paramètres Heston ci-dessus |

La cible Local Vol / LSV est `sigma_imp(K)=0.20-0.20*ln(K)+0.10*ln(K)^2`, avec `K` exprimé en proportion du fixing initial. Le point 100 % est donc ATM spot ; il ne désigne pas le forward, qui varie avec la maturité.

| Strike / fixing initial | Volatilité implicite cible LV / LSV |
|---|---:|
| 60 % | 32,83 % |
| 80 % | 24,96 % |
| 100 % | 20,00 % |
| 120 % | 16,69 % |

La volatilité initiale de Heston/SABR reste 20 %, mais leur volatilité implicite ATM peut changer lorsque la corrélation spot/vol et la vol de vol changent. Ils ne sont pas recalibrés à 20 % ATM ni à la surface LV. Les prix ne constituent donc pas une comparaison à surface implicite identique.

## Prix et écarts avec la première série

En % du nominal ; les crochets donnent l’intervalle Monte Carlo à 95 %. Les écarts sont en points de nominal, sans intervalle calculé sur la différence.

| Modèle | Mono : prix [IC95] | Écart mono | Worst-of : prix [IC95] | Écart worst-of |
|---|---:|---:|---:|---:|
| GBM — témoin plat | 98,93 [98,81 ; 99,05] | 0,00 | 92,45 [92,32 ; 92,57] | 0,00 |
| Heston | 100,08 [99,96 ; 100,20] | 0,48 | 93,84 [93,69 ; 93,98] | 0,72 |
| SABR | 97,95 [97,79 ; 98,10] | -0,08 | 89,79 [89,60 ; 89,97] | -0,06 |
| Local Vol | 98,37 [98,20 ; 98,54] | -0,12 | 90,78 [90,58 ; 90,97] | -0,46 |
| LSV | 99,10 [98,94 ; 99,26] | 0,00 | 91,32 [91,13 ; 91,51] | -0,35 |

Sur le worst-of Local Vol, le prix baisse de 0,46 point : le put vendu coûte environ 1,90 point supplémentaire, partiellement compensé par 1,00 point de coupons et 0,45 point de capital actualisé supplémentaires. Le rappel plus fréquent modifie les trois contributions. Le sens du prix total ne se déduit donc pas du seul coût du put.

Heston monte dans ce scénario, avec davantage de rappels et une volatilité implicite au strike 100 % qui reste inférieure à 20 %. Un choc à ATM implicite constant nécessiterait un recalibrage du niveau ; ce n’est pas celui effectué ici.

### Contributions actualisées et probabilités

Les probabilités sont celles de la mesure de pricing. Le rappel anticipé désigne un rappel avant la quatrième observation.

| Dimension | Modèle | Capital | Coupons | Put vendu | Rappel anticipé | Perte en capital |
|---|---|---:|---:|---:|---:|---:|
| Mono | GBM — témoin plat | 93,4821 | 9,9143 | -4,4663 | 65,96 % | 9,95 % |
| Mono | Heston | 94,3055 | 10,0859 | -4,3144 | 74,53 % | 8,48 % |
| Mono | SABR | 94,1405 | 10,4268 | -6,6219 | 73,73 % | 10,17 % |
| Mono | Local Vol | 94,2595 | 11,1971 | -7,0841 | 76,22 % | 9,99 % |
| Mono | LSV | 94,2291 | 11,0126 | -6,1424 | 75,51 % | 8,84 % |
| Worst-of | GBM — témoin plat | 92,0511 | 8,2242 | -7,8301 | 48,59 % | 17,34 % |
| Worst-of | Heston | 92,9633 | 8,9454 | -8,0732 | 59,09 % | 15,70 % |
| Worst-of | SABR | 92,7880 | 9,3610 | -12,3609 | 58,19 % | 18,72 % |
| Worst-of | Local Vol | 92,9424 | 10,3864 | -12,5526 | 61,44 % | 17,64 % |
| Worst-of | LSV | 92,8523 | 10,0795 | -11,6076 | 59,92 % | 16,59 % |

## Smile effectivement simulé

Volatilités implicites obtenues par inversion Black-Scholes de puts aux strikes 60 %, 80 %, 100 % et de calls au strike 120 %. Ces payoffs sont calculés par le même point d’entrée de production, sur les trajectoires sans arrêt anticipé, avec la même graine et le même nombre de chemins. Les sommes non actualisées et les temps effectifs du maillage permettent de retirer le décalage de règlement pour cette inversion.

| Horizon approximatif | Modèle | Vol 60 % | Vol 80 % | Vol 100 % | Vol 120 % |
|---|---|---:|---:|---:|---:|
| 1 an | GBM — témoin plat | 19,81 % | 20,05 % | 20,03 % | 20,06 % |
| 4 ans | GBM — témoin plat | 20,04 % | 20,02 % | 20,02 % | 20,06 % |
| 1 an | Heston | 28,90 % | 23,58 % | 18,23 % | 13,57 % |
| 4 ans | Heston | 23,33 % | 20,74 % | 18,62 % | 16,88 % |
| 1 an | SABR | 30,73 % | 24,79 % | 20,24 % | 17,24 % |
| 4 ans | SABR | 30,18 % | 24,60 % | 20,38 % | 17,36 % |
| 1 an | Local Vol | 32,45 % | 24,99 % | 20,10 % | 16,83 % |
| 4 ans | Local Vol | 30,85 % | 24,57 % | 20,02 % | 16,75 % |
| 1 an | LSV | 33,05 % | 25,15 % | 20,10 % | 16,81 % |
| 4 ans | LSV | 30,88 % | 24,56 % | 19,98 % | 16,77 % |

![Smiles implicites simulés](../../../output/autocall-4y-equity-smile-20261006/implied_smiles.png)

Le contrôle exige une volatilité strictement décroissante sur ces quatre strikes, à un an et quatre ans, pour chaque modèle avec smile. La cible LV / LSV et les vols obtenues sont distinguées : la conversion Dupire, la grille numérique et le levier estimé par particules ne reproduisent pas exactement tous les points cibles.

### Contrôle du forward simulé

| Horizon | Modèle | Écart relatif de moyenne à `exp((r-q)*T)` |
|---|---|---:|
| 1 an | GBM — témoin plat | 0,0075 % |
| 4 ans | GBM — témoin plat | 0,0336 % |
| 1 an | Heston | -0,0084 % |
| 4 ans | Heston | 0,0581 % |
| 1 an | SABR | 0,0106 % |
| 4 ans | SABR | -0,0471 % |
| 1 an | Local Vol | -0,0058 % |
| 4 ans | Local Vol | -0,0385 % |
| 1 an | LSV | -0,0079 % |
| 4 ans | LSV | 0,0326 % |

## Contrôles et limites

- 50 000 paires antithétiques, soit 100 000 trajectoires par calcul, graine 42 ; maillage d’environ 52 pas par an.
- Les deux prix GBM reproduisent exactement la première série.
- Pour les dix autocalls : somme du capital non actualisé égale à un nominal ; capital + coupons + put actualisés réconciliés avec le prix à moins de `1e-6` en fraction de nominal.
- Les IC sont ceux du moteur. Ils ne couvrent pas le biais de discrétisation, les écarts de surface ou le biais de modèle ; les particules LSV ne sont pas indépendantes.
- Pas de calibration à une même surface ni d’étude de convergence du pas. Un renforcement du skew ne constitue pas un choc isolé à volatilité ATM implicite constante.
- Aucune modification du moteur ou de deal nécessaire pour ces calculs.

## Reproduction

Depuis la racine du dépôt :

```powershell
.venv/Scripts/python.exe -X utf8 output/autocall-4y-equity-smile-20261006/price_comparison.py
.venv/Scripts/python.exe -X utf8 output/autocall-4y-equity-smile-20261006/build_report.py
```

[Requêtes, résultats et diagnostics complets](../../../output/autocall-4y-equity-smile-20261006/results.json).
