# Comparaison d’un autocall Athena 4 ans — 06/10/2026

**Revue complémentaire :** le niveau GBM est corroboré par un calcul indépendant.
Les autres modèles n’ont pas été calibrés à une surface commune ; le comparatif
ne valide pas leurs écarts comme effets purs de dynamique. Voir
[l’audit de la comparaison et du smile renforcé](../../audits/AUDIT_AUTOCALL_SMILE_2026-10-06.md).

Dix prix calculés avec le moteur Structura : cinq modèles en mono-actif et les
mêmes cinq sur un panier worst-of de deux actifs. Hypothèses communes explicites
choisies avec Philippe ; aucune donnée de marché ni calibration externe utilisée.

## Contrat et hypothèses communes

- Athena, durée contractuelle de quatre ans, observations annuelles.
- Coupon de 10 % par année écoulée, cumulé et payé uniquement lors du rappel :
  110 %, 120 %, 130 % ou 140 % du nominal, capital compris.
- Rappel si la performance relative atteint 100 % à une observation, y compris
  la dernière. Après rappel, arrêt du produit.
- Sinon à maturité : remboursement de 100 % si la performance est au moins 60 % ;
  en dessous de 60 %, remboursement égal à la performance finale. Aucun coupon
  dans cette branche. La protection est européenne, sans surveillance continue.
- Mono : Société Générale (`GLE.PA`). Multi : worst-of Société Générale et
  STMicroelectronics (`STMPA.PA`). Les deux actifs reçoivent volontairement les
  mêmes hypothèses ; leurs noms ne signifient pas que les paramètres sont observés
  sur ces titres.
- EUR ; taux plat de 3 % et rendement de dividende continu de 2 % par actif.
- Corrélation des chocs spot entre les deux actifs : 50 %.
- Volatilité initiale de 20 %, sous les conventions propres à chaque modèle.
- Funding nul, taux déterministes, absence de quanto et de frais.
- Strike / StartDate et date de valeur : 06/10/2026. Les cours sont normalisés à
  1 au départ ; `Basket.yield` est le ratio au fixing initial. Aucun cours absolu
  de marché n’est nécessaire pour ce contrat en performance relative.
- Montants exprimés en pourcentage du nominal ; nominal illustratif de 1 M€.

Calendrier EUR / TARGET, report au jour ouvré suivant, règlement à J+3 ouvrés :

| Rang | Observation ajustée | Paiement |
|---|---|---|
| 1 | 06/10/2027 | 11/10/2027 |
| 2 | 06/10/2028 | 11/10/2028 |
| 3 | 08/10/2029 | 11/10/2029 |
| 4 | 07/10/2030 | 10/10/2030 |

## Paramètres propres aux modèles

Les valeurs ci-dessous sont les unités internes, en fractions, et non des
pourcentages d’affichage.

| Modèle | Paramètres effectivement utilisés |
|---|---|
| GBM / vol constante | `sigma = 0.20` |
| Heston | `v0 = theta = 0.04`, `kappa = 2`, `xi = 0.35`, `rho_h = -0.70` |
| SABR | `alpha = 0.20`, `beta = 0.50`, `rho = -0.30`, `nu = 0.40`, cours initial normalisé à 1 |
| Local Vol / Dupire | `sigma = 0.20`, `skew = -0.10`, `curvature = 0.05` |
| LSV | Paramètres de variance Heston ci-dessus et même cible de smile que Local Vol ; levier estimé par particules |

Pour Local Vol et la cible LSV, le smile paramétrique est
`sigma_imp(K) = 0.20 - 0.10 * ln(K) + 0.05 * ln(K)^2`, avec `K` normalisé au spot
initial, puis conversion Dupire par le moteur et ses garde-fous numériques.

Une même volatilité initiale ne donne pas une même surface de volatilité implicite.
Cette expérience compare les prix sous ces jeux de paramètres ; elle n’isole pas
le seul effet de la dynamique après calibration à une surface commune.

## Résultats

Prix et intervalles Monte Carlo à 95 %, en % du nominal :

| Modèle | Mono SG | IC95 mono | Worst-of SG / STMicro | IC95 worst-of | Écart multi − mono, points |
|---|---:|---|---:|---|---:|
| GBM | 98,9301 | [98,8117 ; 99,0484] | 92,4451 | [92,3225 ; 92,5678] | −6,4850 |
| Heston | 99,5963 | [99,4743 ; 99,7183] | 93,1111 | [92,9740 ; 93,2482] | −6,4852 |
| SABR | 98,0213 | [97,8753 ; 98,1672] | 89,8446 | [89,6774 ; 90,0119] | −8,1767 |
| Local Vol | 98,4897 | [98,3415 ; 98,6379] | 91,2354 | [91,0699 ; 91,4009] | −7,2543 |
| LSV | 99,1038 | [98,9633 ; 99,2444] | 91,6779 | [91,5164 ; 91,8394] | −7,4259 |

Sous ces hypothèses, le worst-of réduit la fréquence des rappels et augmente le
coût de la protection conditionnelle vendue par l’investisseur. Heston donne le
prix le plus élevé et SABR le plus bas dans les deux dimensions ; ce classement
est propre aux paramètres retenus.

### Contributions actualisées, en % du nominal

Le capital comprend les remboursements au rappel et à maturité. Le put est une
contribution négative distincte. Les éventuels écarts de dernière décimale sont
dus aux arrondis d’affichage.

| Dimension | Modèle | Capital | Coupons | Put vendu | Prix total |
|---|---|---:|---:|---:|---:|
| Mono | GBM | 93,4821 | 9,9143 | −4,4663 | 98,9301 |
| Mono | Heston | 94,0136 | 10,0562 | −4,4735 | 99,5963 |
| Mono | SABR | 93,8496 | 10,1823 | −6,0106 | 98,0213 |
| Mono | Local Vol | 93,8711 | 10,6257 | −6,0071 | 98,4897 |
| Mono | LSV | 93,8598 | 10,5751 | −5,3310 | 99,1038 |
| Worst-of | GBM | 92,0511 | 8,2242 | −7,8301 | 92,4451 |
| Worst-of | Heston | 92,6284 | 8,7081 | −8,2254 | 93,1111 |
| Worst-of | SABR | 92,4464 | 8,7926 | −11,3943 | 89,8446 |
| Worst-of | Local Vol | 92,4954 | 9,3906 | −10,6507 | 91,2354 |
| Worst-of | LSV | 92,4442 | 9,2317 | −9,9980 | 91,6779 |

### Indicateurs de distribution

Probabilités sous la mesure de pricing, sans interprétation comme prévisions
historiques. « Rappel anticipé » exclut la quatrième observation.

| Dimension | Modèle | Rappel avant maturité | Perte en capital à maturité |
|---|---|---:|---:|
| Mono | GBM | 65,956 % | 9,953 % |
| Mono | Heston | 71,568 % | 9,124 % |
| Mono | SABR | 70,245 % | 10,255 % |
| Mono | Local Vol | 71,136 % | 10,286 % |
| Mono | LSV | 70,905 % | 9,207 % |
| Worst-of | GBM | 48,586 % | 17,337 % |
| Worst-of | Heston | 55,294 % | 16,653 % |
| Worst-of | SABR | 53,704 % | 19,045 % |
| Worst-of | Local Vol | 55,027 % | 18,093 % |
| Worst-of | LSV | 54,162 % | 17,049 % |

## Exécution, contrôles et limites

- Appel direct du point d’entrée de pricing Python `price_endpoint`, avec les
  `PricingRequest` complets, le compilateur et le moteur de production. Aucun
  deal créé ou modifié. La couche HTTP et l’interface ne sont pas l’objet de ce calcul.
- Modèle du catalogue `autocall_athena`, écrit avec `UNDERLYING Basket`,
  `CONSTAT StartDate`, `CONSTAT() ObservationDates`, initialisation explicite de
  `Basket.spot0` et flux coupons / capital / put séparés.
- Par prix : `N = 50 000` paires antithétiques, soit 100 000 trajectoires simulées ;
  graine 42. L’IC est calculé sur les moyennes des paires. Les tirages portent la
  même graine, sans supposer un couplage identique entre tous les modèles.
- Maillage du moteur : environ 52 pas par an. Les constatations intermédiaires
  sont rattachées à cette grille ; leurs dates de règlement restent celles du
  calendrier contractuel. L’échéance finale de simulation est conservée.
- Quatre observations compilées, rangs 1 à 4 ; StartDate distincte de la première.
- Somme du capital non actualisé égale à un nominal pour chaque calcul.
- Somme des contributions de flux actualisés égale au prix : écart maximal
  `4.50e-7` en fraction du nominal, inférieur au seuil de `1e-6`, correspondant
  à l’arrondi du prix retourné.
- Les IC mesurent le bruit Monte Carlo estimé, pas l’erreur de discrétisation,
  de calibration ou de modèle. L’estimation par particules de LSV crée en outre
  une dépendance entre trajectoires que l’IC standard ne corrige pas.
- Pas d’étude de convergence du pas de temps ni de calibration de marché dans
  cette comparaison. Les chiffres sont des résultats du moteur sous hypothèses,
  pas des cotations de marché.

## Reproduction

Depuis la racine du dépôt :

```powershell
.venv/Scripts/python.exe -X utf8 output/autocall-4y-vol-comparison-20261006/price_comparison.py
```

- [Pilote du calcul](../../../output/autocall-4y-vol-comparison-20261006/price_comparison.py)
- [Requêtes complètes, résultats et flux par date](../../../output/autocall-4y-vol-comparison-20261006/results.json)

Le JSON conserve notamment le texte exact du script, les paramètres, la
StartDate, les observations et les dates de paiement de cette exécution.
