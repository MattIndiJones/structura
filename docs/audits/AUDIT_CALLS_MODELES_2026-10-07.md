# Contrôle préalable des calls vanilles par modèle — 07/10/2026

**Suite livrée le même jour :** la [validation étendue](VALIDATION_MODELES_VOL_2026-10-07.md)
ajoute une référence SABR spot indépendante, corrige l'estimation conditionnelle
LSV et complète les digitaux/marginales multi. Les mesures ci-dessous décrivent
le moteur avant cette correction ; les réserves finales figurent dans la suite.

## Conclusion

Le contrôle des vanilles doit précéder la nouvelle surface et la comparaison des
autocalls. La première grille de contrôle corrobore GBM et Heston avec les paramètres
retenus. Elle confirme la mauvaise reproduction de la cible actuelle par Local Vol
et LSV. Elle révèle aussi un résidu LSV sur surface plate et une différence entre
SABR simulé et l’approximation Hagan à maturité longue.

Il s’agit d’une validation ciblée, en mono-actif. Elle ne valide pas l’ensemble des
régimes de paramètres ni les produits multi-actifs. Aucun moteur ou deal modifié.

## Grille et méthode

- Modèles : GBM, Heston, SABR, Local Vol et LSV.
- Maturités : 6 mois, 1, 2, 3 et 4 ans.
- Strikes : 40 %, 60 %, 80 %, 100 %, 120 % et 150 % du spot initial.
- Soit **150 calls et 150 puts** pour les cinq modèles avec leur smile actuel.
- Spot initial normalisé à 1, taux 3 %, dividende continu 2 %, paiement à l’échéance
  de chaque option. Les dates J+3 des autocalls ne sont pas utilisées pour ces vanilles.
- 50 000 paires antithétiques, graine 42, 52 pas par an. Les maturités sont ici des
  fractions exactes d’année, et toutes tombent sur le maillage.
- Les simulateurs appelés sont ceux de production. Payoffs et statistiques des
  calls/puts sont évalués directement sur leurs trajectoires, sans utiliser
  l’évaluateur PayScript. Ce contrôle vise la diffusion, pas la couche HTTP ou le
  chemin de saisie du Pricer.
- Tous les paramètres du scénario renforcé du 06/10 sont repris ; ils restent des
  hypothèses synthétiques, sans calibration de marché.

Les références sont calculées séparément des simulateurs :

| Modèle | Référence | Portée |
|---|---|---|
| GBM | Black-Scholes, calcul indépendant avec la CDF SciPy | Référence exacte du modèle |
| Heston | Fonction caractéristique et intégration de Fourier | Référence semi-analytique indépendante |
| SABR | Formule Hagan réimplémentée séparément | Approximation ; pas un oracle exact à quatre ans |
| Local Vol | Black-Scholes avec les vols de la cible déclarée | Mesure de reproduction de cible ; extrapolation déjà identifiée comme invalide |
| LSV | Même cible que Local Vol | Mesure de reproduction de cible et des résidus de particules |

Pour Heston, la borne d’intégration passe de 200 à 400 pour chaque point ; l’écart
doit être inférieur à `1e-7` en unité de spot. Le contrôle est satisfait.
La méthode de référence est issue de [Heston, 1993](https://finance.martinsewell.com/stylized-facts/volatility/Heston1993.pdf).

Hagan décrit une expansion asymptotique sur un forward sans drift. Le simulateur
Structura fait évoluer le spot avec son carry ; à carry non nul, la même valeur
numérique d’alpha ne suffit pas à identifier les conventions. Un scénario
supplémentaire `q=r=3%` retire cette différence. Voir
[Hagan et al., Managing Smile Risk](https://derivativesacademy.com/storage/uploads/files/modules/resources/1702213496_hagan_kumar_lesniewski_woodward_managing_smile_risk.pdf).

## Résultats sur les paramètres du smile renforcé

Un point est signalé lorsque l’écart absolu dépasse **3 erreurs standards + 1 bp
du spot initial**. C’est un seuil de diagnostic, pas une garantie de précision de
calibration. Les erreurs standards LSV calculées sur les paires ne corrigent pas
la dépendance entre particules.

| Modèle | Calls signalés / 30 | Puts signalés / 30 | Interprétation |
|---|---:|---:|---|
| GBM | 0 | 0 | Compatible avec Black-Scholes sur la grille |
| Heston | 0 | 0 | Compatible avec la référence Fourier sur la grille |
| SABR | 12 | 10 | Différence avec Hagan ; ne suffit pas à conclure à un bug du simulateur |
| Local Vol | 11 | 7 | Reproduction de la cible insuffisante, surtout dans l’aile basse |
| LSV | 6 | 6 | Reproduction de la cible insuffisante, surtout dans l’aile basse |

L’écart maximal de call vaut 11,96 bps pour GBM et 6,56 bps pour Heston. Ces maxima
restent compatibles avec leurs erreurs Monte Carlo : ce ne sont pas des mesures
de biais identifiées. Les points et leurs erreurs standards sont conservés dans
le JSON, afin d’éviter d’interpréter ces maxima seuls.

### Exemples de calls à quatre ans

Prix exprimés en % du spot initial ; écart en bps du spot initial.

| Modèle | Strike | Prix MC | Référence | Écart |
|---|---:|---:|---:|---:|
| GBM | 60 % | 40,2023 % | 40,1623 % | +3,99 bps |
| GBM | 100 % | 16,2731 % | 16,2268 % | +4,63 bps |
| Heston | 60 % | 41,0246 % | 40,9597 % | +6,49 bps |
| Heston | 100 % | 15,3047 % | 15,2626 % | +4,21 bps |
| SABR | 60 % | 43,0895 % | 43,7142 % | −62,47 bps |
| SABR | 100 % | 16,4511 % | 16,6662 % | −21,51 bps |
| Local Vol | 60 % | 43,3366 % | 44,0939 % | −75,73 bps |
| Local Vol | 100 % | 16,2042 % | 16,2268 % | −2,26 bps |
| LSV | 60 % | 43,4105 % | 44,0939 % | −68,34 bps |
| LSV | 100 % | 16,2441 % | 16,2268 % | +1,73 bps |

Pour Local Vol/LSV, l’accord à l’ATM ne valide donc pas la reproduction au strike
de protection 60 %. Les options très ITM sont également bruitées par l’estimation
du forward ; le contrôle des puts OTM est nécessaire en complément.

## Parité, forward et cas limites

La parité call-put est calculée sur chaque paire de trajectoires. Son résidu est
exactement celui du forward simulé actualisé, à l’arrondi flottant près. Les
moyennes des forwards sont à moins de trois erreurs standards de la théorie sur
la grille. Ce contrôle est utile pour repérer un drift incohérent ; il n’est pas
indépendant de la construction des payoffs et ne prouve pas la justesse du smile.

Quatre scénarios complémentaires, soit 120 calls et 120 puts, contrôlent le retour
à Black-Scholes :

| Scénario | Calls signalés / 30 | Puts signalés / 30 |
|---|---:|---:|
| Heston : `xi=0.0001`, `v0=theta=0.04` | 0 | 0 |
| SABR : `beta=1`, `nu=0`, `alpha=0.20` | 0 | 0 |
| Local Vol : `skew=curvature=0`, `sigma=0.20` | 0 | 0 |
| LSV : cible plate à 20 %, variance stochastique conservée | 0 | 5 |

Le scénario LSV plat mérite un diagnostic propre : à deux ans, le put strike
40 % donne un excès par rapport à Black-Scholes de **1,71 bp** avec la graine 42,
**1,12 bp** avec la graine 17 et **1,69 bp** avec la graine 93. Le résidu est
retrouvé avec des graines supplémentaires, mais sa cause n’est pas isolée ici.
Il faut distinguer erreur de particules, discrétisation et incertitude statistique
tenant compte de la dépendance entre chemins. Le bon niveau des calls ITM peut
masquer ce défaut par leur variance plus élevée.

## SABR : comparaison à Hagan et contrôle du pas

Le cas sans carry comporte 11 calls et 11 puts signalés sur 30. La différence
persiste donc après retrait du désalignement spot/forward.

Un contrôle supplémentaire à 20 000 paires utilise des incréments browniens
communs : les incréments à 208 pas par an sont agrégés pour construire ceux à
52 pas. Sur le put 60 % à quatre ans, `r=q=3%` :

| Calcul | Prix en fraction du spot initial |
|---|---:|
| MC, 52 pas/an | 0,04278298 |
| MC, 208 pas/an | 0,04279610 |
| Hagan | 0,04900231 |

La différence fine − grossière vaut **+0,13 bp**, avec une erreur standard de
**0,52 bp** sur cette différence. L’écart à Hagan est d’environ **−62 bps**.
Sur ce point, affiner le pas ne rapproche donc pas matériellement le simulateur
de Hagan. Ce contrôle ne démontre pas à lui seul lequel serait faux : Hagan est
une approximation à ces maturités et paramètres. Une référence indépendante de
l’équation SABR, par exemple PDE adaptée à la frontière zéro, reste nécessaire
pour valider son niveau sous ce régime de smile.

## Conséquences pour le chantier

1. Garder la grille de vanilles comme préalable à toute nouvelle comparaison.
2. Remplacer la cible invalide par une surface contrôlée sans arbitrage et refaire
   le contrôle de reproduction Local Vol / LSV.
3. Diagnostiquer le résidu LSV même sur cible plate avant de déclarer sa calibration
   validée.
4. Définir les conventions SABR et une référence numérique indépendante du modèle
   simulé avant de calibrer ce moteur à l’aide de Hagan.
5. Compléter ensuite les régimes de paramètres, les digitaux et les contrôles des
   marginales dans les simulations multi-actifs, puis reprendre les autocalls.

## Reproduction et preuves

Tous les calculs ont respecté les budgets mémoire et calcul. Les contrôles fins
emploient une durée équivalente à 52 pas pour estimer leurs ressources ; leurs
maturités financières restent celles indiquées. Aucune suite backend complète
n’a été lancée et aucun backend n’a été démarré pour ce diagnostic.

- [Programme de contrôle](../../output/vanilla-model-audit-20261007/audit_calls.py)
- [Prix et erreurs par point](../../output/vanilla-model-audit-20261007/results.json)
- [Contrôles complémentaires SABR / LSV](../../output/vanilla-model-audit-20261007/diagnose_sabr_lsv.py)
- [Résultats complémentaires](../../output/vanilla-model-audit-20261007/followup_results.json)

```powershell
.venv/Scripts/python.exe -X utf8 output/vanilla-model-audit-20261007/audit_calls.py
.venv/Scripts/python.exe -X utf8 output/vanilla-model-audit-20261007/diagnose_sabr_lsv.py
```
