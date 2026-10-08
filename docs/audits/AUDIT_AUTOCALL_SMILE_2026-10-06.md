# Revue des prix d’autocall et du smile actions — 06/10/2026

**Suite au 07/10 :** le [benchmark sur cible SSVI sans arbitrage](AUTOCALL_SURFACE_COMMUNE_2026-10-07.md)
fournit de nouveaux prix, les contrôles numériques et les limites de calibration.
Les constats ci-dessous restent ceux de la cible historique ; ils ne qualifient
pas la nouvelle surface.

## Conclusion

Les résultats sont reproductibles et leurs flux se réconcilient. Le niveau GBM
est corroboré par un calcul indépendant. En revanche, le comparatif des modèles
ne constitue pas une validation à marché commun, et les résultats Local Vol / LSV
du smile renforcé ne sont pas validés comme prix de la surface cible annoncée.

La revue fait suite à la question de Philippe « ces résultats te semblent corrects ? ».
Elle complète la [première comparaison](../projects/pricing/COMPARAISON_AUTOCALL_4ANS_MODELES_2026-10-06.md)
et la [série avec skew renforcé](../projects/pricing/COMPARAISON_AUTOCALL_SMILE_ACTIONS_2026-10-06.md).
Aucun moteur, contrat ou deal n’a été modifié par cette revue.

## 1. Référence GBM indépendante

Calcul NumPy autonome, sans compilateur PayScript, sans simulateur Structura et
sans son actualisation : transitions lognormales exactes entre les quatre dates
contractuelles, formule Athena explicite, paiement à chaque date J+3, 500 000
paires antithétiques soit un million de trajectoires par dimension. Graine 731.

| Dimension | Prix Structura précédent | Référence indépendante | IC95 de la référence |
|---|---:|---:|---|
| Mono | 98,9301 % | 98,9722 % | [98,9349 % ; 99,0094 %] |
| Worst-of à deux actifs | 92,4451 % | 92,4500 % | [92,4111 % ; 92,4888 %] |

Les écarts sont compatibles avec l’incertitude combinée des deux simulations.
La référence utilise les dates contractuelles ; Structura rattache les dates
intermédiaires à son maillage. Ce contrôle corrobore le niveau GBM, sans valider
par extension les autres modèles.

## 2. Défaut de la surface paramétrique choisie

La cible renforcée est `sigma(K)=0.20-0.20*ln(K)+0.10*ln(K)^2`, `K=S/S0`.
L’extrapolation en strikes bas n’a pas été contrôlée avant la présentation des
prix. Cette omission relève de la préparation de la comparaison.

À l’échéance effective de 4,00273785 ans, le facteur de densité `g` associé à cette
surface vaut **−0,0296657 au strike 20 %**. Le zéro voisin est à **20,6909 %**.
Ce n’est pas une fluctuation Monte Carlo : le calcul est déterministe.

Le constat est également visible directement sur trois prix Black-Scholes
calculés avec les volatilités de la cible :

| Strike | Prix du call, nominal normalisé à 1 |
|---|---:|
| 19 % | 0,79358007545 |
| 20 % | 0,78463150110 |
| 21 % | 0,77567960197 |

Le butterfly `C(19%)-2*C(20%)+C(21%)` vaut **−0,00000332477**, alors que son
payoff est non négatif. La surface cible viole donc la convexité en strike dans
cette zone. Le critère de densité et son lien avec les prix convexes sont exposés
par [Gatheral et Jacquier, section 2.2](https://arxiv.org/pdf/1204.0646).

Le moteur gère cette situation dans `_dupire_vol` par une valeur de repli lorsque
le dénominateur n’est pas positif. Il impose aussi un plafond de 150 % à la vol
locale : à un an et au strike 20 %, la formule brute donnerait **222,60 %**, mais
la valeur utilisée est **150 %**. `_build_lv_grid` couvre les niveaux de 20 % à
300 % du spot initial ; la simulation borne l’interpolation hors de cette grille.

Ces dispositifs définissent une diffusion effective différente de la surface
demandée. Leur contribution exacte au biais de prix n’est pas isolée ici. La
constatation d’une surface cible invalide ne signifie pas que chaque prix produit
par la diffusion de repli comporte lui-même un arbitrage. Elle interdit en revanche
de présenter les chiffres comme ceux d’une calibration fidèle à cette cible.

## 3. Contrôle du pas de temps sur Local Vol

Contrôle isolé avec 52 puis 208 pas par an. La constante de pas n’est modifiée que
dans le processus de diagnostic et restaurée ensuite. Les plafonds de ressources
sont vérifiés pour le nombre réel de pas ; aucune limite de calcul n’est relevée.
L’estimation de ressources du JSON utilise une maturité équivalente à 52 pas,
soit 16,01 ans pour estimer le coût du calcul à 208 pas ; **le contrat reste à
quatre ans**.

### Put vanille 60 % à quatre ans

20 000 paires par calcul. L’IC de prix est inversé en IC de volatilité implicite,
en corrigeant le décalage de règlement. La cible est **32,8259 %**.

| Pas par an | Vol implicite produite | IC95 sur la vol implicite |
|---|---:|---|
| 52 | 30,9199 % | [30,5820 % ; 31,2549 %] |
| 208 | 30,7957 % | [30,4577 % ; 31,1308 %] |

Le défaut de reproduction du point cible subsiste nettement au-delà du bruit
Monte Carlo avec le pas affiné. Il ne s’explique pas uniquement par le maillage
hebdomadaire. Ce diagnostic ne constitue pas une étude complète de convergence.

### Autocall worst-of

12 500 paires par calcul, afin de rester dans les budgets mémoire et calcul :

| Pas par an | Prix | IC95 |
|---|---:|---|
| 52 | 90,4298 % | [90,0348 % ; 90,8248 %] |
| 208 | 90,9528 % | [90,5596 % ; 91,3460 %] |

Les intervalles se recouvrent ; les tirages n’ont pas été couplés par agrégation
brownienne entre les deux maillages. Ces chiffres ne démontrent ni une correction
de +0,52 point, ni la convergence du prix. Ils ne remplacent pas le précédent
prix à 50 000 paires et 52 pas par an.

## 4. Comparabilité des modèles

Les volatilités initiales sont proches de 20 %, mais les surfaces implicites
ne sont pas communes. Au strike 100 % et à quatre ans : Heston **18,62 %**,
SABR **20,38 %**, Local Vol **20,02 %**, LSV **19,98 %**. Au strike 60 %, Heston
est à **23,33 %**, contre environ **30–31 %** pour les trois autres modèles.

Le prix Heston supérieur au pair n’est pas une preuve d’erreur à lui seul.
En revanche, l’écart de prix entre modèles ne peut pas être interprété comme
un pur effet de dynamique. Même aligner un seul point ATM ne suffirait pas :
les maturités et strikes utiles au produit doivent être comparables.

La petite variation de prix entre les deux séries sous SABR ou LSV mono ne doit
pas être interprétée à partir des seuls IC des prix : il faudrait un IC sur la
différence avec tirages communs.

## 5. Ce qui reste nécessaire avant validation

1. Définir une surface actions synthétique sans arbitrage, y compris son
   extrapolation dans les ailes, avec une structure par maturité explicite.
2. Calibrer les modèles sur cette même cible en publiant leurs résidus de
   calibration ; certains modèles ne reproduiront pas tous les points exactement.
3. Contrôler prix de vanilles, digitaux et probabilités autour des barrières 60 %
   et 100 %, puis la convergence du temps et des particules LSV.
4. Refaire les autocalls mono et multi et séparer bruit Monte Carlo, erreur de
   calibration et écart de dynamique. Le GBM reste une référence à vol plate.

Ces travaux ne sont pas réalisés par cette revue. Les précédents résultats sont
conservés comme sorties de scénarios, avec la réserve explicite ci-dessus.

## Preuves reproductibles

- [Programme de diagnostic](../../output/autocall-4y-equity-smile-20261006/audit_results.py)
- [Résultats détaillés](../../output/autocall-4y-equity-smile-20261006/audit_results.json)

```powershell
.venv/Scripts/python.exe -X utf8 output/autocall-4y-equity-smile-20261006/audit_results.py
```
