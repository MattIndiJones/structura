# Validation des modèles de volatilité — 07/10/2026

**Complément du même jour :** le [benchmark sur cible SSVI commune](AUTOCALL_SURFACE_COMMUNE_2026-10-07.md)
traite les réserves numériques de ce premier lot à 208 pas/an sur la grille testée,
puis calcule les dix autocalls avec incertitude, flux séparés et convergence.
Local Vol et LSV reproduisent cette nouvelle cible ; les ajustements Heston et
SABR restent imparfaits. Les mesures et réserves ci-dessous décrivent le premier
lot et sont conservées comme historique ; elles ne constituent pas son état final.

## Résultat et portée

Le premier lot de fiabilisation apporte une correction LSV, une référence SABR
numérique indépendante et un programme de contrôle reproductible des cinq
simulateurs, en mono et dans un panier de deux actifs corrélés à 50 %.

**GBM et Heston sont corroborés dans le régime testé. SABR et LSV restent sous
réserve pour certains digitaux et erreurs de discrétisation. La comparaison des
autocalls sur une surface commune n'est pas encore validée.** L'ancienne cible
polynomiale présente toujours une densité négative dans son aile basse ; aucune
calibration de marché ni surface de remplacement n'est livrée dans ce lot.

Les mesures utilisent des hypothèses synthétiques : spot normalisé à 1, taux
3 %, dividende continu 2 %, sans funding, quanto ou taux stochastiques.
Paramètres : sigma 20 % ; Heston/LSV `v0=theta=0.04`, `kappa=2`, `xi=0.5`,
`rho_h=-0.8` ; SABR `alpha=0.2`, `beta=0.5`, `rho=-0.6`, `nu=0.5` ; cible
Local Vol/LSV `skew=-0.2`, `curvature=0.1`. La cible plate retire skew et convexité
en conservant la variance stochastique LSV.

## Correction LSV

Deux défauts numériques identifiés dans l'estimation de `E[V|S]` :

1. Les buckets comptant moins de 30 particules utilisaient la variance globale
   `E[V]`. Dans la queue basse, cela effaçait la dépendance spot/variance.
   Ils élargissent désormais leur fenêtre aux buckets voisins jusqu'à obtenir
   au moins 30 particules, ou tout l'échantillon s'il est plus petit.
2. La grille de variance conditionnelle réutilisait les 50 nœuds de la cible
   locale. Elle emploie désormais 200 buckets indépendants de la grille de
   recherche de vol locale. Affiner seulement la grille avec l'ancien fallback
   global aggravait les puts profonds ; les deux corrections vont ensemble.

La variance reste celle connue au début du pas. Les caps de leverage et de
volatilité, les incréments browniens et les conventions de drift sont conservés.
Retirer les caps lors du diagnostic ne résolvait pas le défaut observé.
L'interpolation linéaire de moyennes conditionnelles a été expérimentée puis
écartée : elle dégradait les vanilles ATM sur cette grille.

Écart du put 40 % à deux ans, cible plate, en bps du spot initial :

| Graine | Avant | Après les deux corrections |
|---|---:|---:|
| 42 | +1,713 | +0,075 |
| 17 | +1,119 | −0,016 |
| 93 | +1,690 | +0,075 |

À quatre ans, les écarts après correction sont respectivement +0,203, +0,267 et
−0,043 bp. L'amélioration des puts profonds ne suffit pas à déclarer toute la
calibration exacte : des digitaux courts restent signalés, décrits ci-dessous.
L'identité des marginales LSV avec la cible est une propriété du modèle continu,
approchée par les particules et le maillage, pas une garantie du simulateur fini.

## Référence indépendante SABR

Le programme résout l'équation backward bidimensionnelle en spot et log-alpha :

```text
dS = (r-q) S dt + alpha S^beta dW
dalpha = nu alpha dZ ; corr(dW,dZ) = rho
```

Cette convention est celle du simulateur de production. Alpha porte sur le spot
normalisé, pas sur un forward différent. Le solveur n'importe aucune formule ni
fonction du moteur. Il utilise une frontière absorbante en zéro, des frontières
réfléchissantes en log-alpha, un stencil central avec dérivée mixte, et
Crank-Nicolson précédé de quatre demi-pas implicites. Le dividende alimente le
drift ; le taux alimente drift et actualisation.

La référence elle-même est testée : retour à Black-Scholes pour `beta=1, nu=0`,
puis à la loi CEV exacte pour `beta=0.5, nu=0, r=q`. Le test CEV fort utilise
`alpha=0.6` à quatre ans, soit environ 25 % de masse absorbée en zéro. La loi
chi-deux non centrale suit la représentation de
[CEVCalculator de QuantLib](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/vanilla/analyticcevengine.cpp).
La dégénérescence de l'équation SABR en zéro est traitée dans
[Horvath et Reichmann, 2018](https://arxiv.org/abs/1801.02719) ; notre solveur utilise
des différences finies, et ne reprend pas leur implémentation par éléments finis.

Contrôles numériques sur les 30 points de la grille :

| Contrôle | Écart maximal calls/puts | Écart maximal digitaux |
|---|---:|---:|
| Raffinement : `dS=0.025 → 0.0125`, log-alpha `0.1 → 0.075`, 100 → 200 pas/an | 1,759 bp | 6,713 bps |
| Domaine : spot maximal 6 → 12 et largeur log-alpha 3,5 → 4, à grille grossière | 0,003 bp | 0,005 bp |

Un raffinement supplémentaire (`dS=0.00625`, log-alpha 0,06, 300 pas/an, spot
maximal 4) déplace les vanilles de moins de 0,438 bp par rapport à la référence
fine. Ce contrôle supplémentaire modifie aussi le domaine ; il ne remplace pas
la comparaison de domaines à maillage identique.

La référence fine n'est pas qualifiée d'exacte. Le seuil de diagnostic SABR
ajoute aux 3 erreurs standards MC : 1 bp, l'écart entre les deux maillages et
l'écart de domaine. Cette enveloppe empirique n'est pas une borne mathématique.

Exemple : call 60 % à quatre ans, prix en % du spot initial :

| MC de production | PDE fine | Hagan du contrôle initial |
|---:|---:|---:|
| 43,08945 % | 43,11408 % | 43,7142 % |

L'écart MC/PDE est −2,46 bps, avec une erreur standard MC de 6,12 bps. Le put
associé vaut 4,03639 % en MC contre 4,01767 % en PDE (+1,87 bp, SE 3,64 bps).
La grande différence précédemment observée avec Hagan ne démontre donc pas un
bug de niveau du simulateur à ce point. Hagan reste une approximation asymptotique
sur un forward sans drift, pas l'oracle exact du spot SABR à quatre ans.

La dynamique SABR de production n'a pas été changée. Son plancher de spot et ses
caps de volatilité demeurent ; le contrôle ci-dessus ne certifie pas les régimes
extrêmes où ils interviennent matériellement.

## Grille étendue et statuts

50 000 paires antithétiques, graine 42, 52 pas/an, maturités 6 mois, 1, 2, 3 et
4 ans, strikes 40 %, 60 %, 80 %, 100 %, 120 % et 150 %. Chaque marginale du
panier reçoit la même référence mono. Les scénarios LSV plats ajoutent les
graines indépendantes 17 et 93. Au total : **690 calls, 690 puts, 690 digitaux**,
dont 230 digitaux aux seuils 60 % / 100 %, et 115 contrôles de forward.

Pour les références exactes, un point est signalé au-delà de 3 erreurs standards
+ 1 bp. Les erreurs standards des paires LSV ignorent l'interaction des
particules ; les graines supplémentaires complètent le diagnostic, sans
constituer une estimation exhaustive de cette incertitude.

| Régime | Calls signalés | Puts signalés | Digitaux signalés | Digitaux 60/100 % signalés |
|---|---:|---:|---:|---:|
| GBM mono / multi | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/10 ; 0/20 |
| Heston mono / multi | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/10 ; 0/20 |
| SABR mono / multi | 0/30 ; 1/60 | 0/30 ; 0/60 | 1/30 ; 0/60 | 0/10 ; 0/20 |
| Local Vol plat mono / multi | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/10 ; 0/20 |
| LSV plat mono / multi | 0/30 ; 0/60 | 0/30 ; 0/60 | 0/30 ; 4/60 | 0/10 ; 2/20 |
| LSV plat mono, graine 17 | 0/30 | 0/30 | 0/30 | 0/10 |
| LSV plat mono, graine 93 | 0/30 | 0/30 | 1/30 | 1/10 |

Les résidus restant ouverts sont explicitement conservés :

- SABR : digital 40 % à un an en mono (−9,31 bps, SE 2,53) et call 120 %
  à un an sur le deuxième actif (+6,76 bps, SE 1,46).
- LSV plat : digitaux 100 % à six mois sur les deux actifs (−29,37 / −29,57
  bps), digital 150 % à six mois sur le premier actif, et digital 80 % à un an
  sur le deuxième. La graine mono 93 retrouve −30,95 bps au seuil 100 % à six mois.

Un contrôle de pas SABR utilise les mêmes incréments grossiers et un pont brownien
pour passer de 52 à 208 pas/an. Le call 120 % à un an sur le deuxième actif
baisse de 1,51 bp (SE de la différence 0,13 bp) ; une partie de l'écart est donc
de la discrétisation. Le digital ATM à six mois baisse de 17,24 / 24,43 bps sur
les deux actifs (SE de la différence 3,97 / 3,89 bps). Le résidu de niveau et la
discrétisation doivent rester distingués.

Le contrôle LSV couplé à 20 000 paires déplace le digital ATM à six mois de
+22,41 bps, avec SE 8,51 bps sur la différence. Ce seul point ne permet pas
d'isoler entièrement l'erreur de temps de l'erreur de particules. Passer de
200 à 400 buckets ne ferme pas systématiquement les résidus ; ce changement
n'est pas retenu en production.

| Modèle | Statut retenu |
|---|---|
| GBM | Compatible avec BS sur la grille mono et les marginales multi testées |
| Heston | Compatible avec Fourier sur ces grilles ; bornes d'intégration 200/400 contrôlées |
| SABR | Référence spot indépendante disponible ; niveaux de vanilles corroborés, résidus courts sous réserve |
| Local Vol | Limite plate corroborée ; reproduction du smile renforcé bloquée par la cible invalide |
| LSV | Biais de puts profonds corrigé ; réserve sur digitaux courts et cible smile invalide |

Le contrôle d'identité multi/mono à incréments corrélés identiques passe pour
les cinq moteurs, avec des paramètres différents pour chaque actif, niveaux
courants et bump de vol. Il valide le câblage des marginales ; il ne valide pas
la copule, la dépendance des volatilités entre actifs ni le prix d'un worst-of.

## Livraison et vérification

- Moteur LSV partagé modifié : les consommateurs pricing, Greeks, chemins MC,
  probabilités, scénarios et MtM qui utilisent ce simulateur héritent de la
  correction. Aucun schéma, paramètre contractuel ou snapshot n'est migré.
- L'ancien test de marginale LSV comparait la vol implicite MC à la **vol locale**
  de Dupire. Il compare désormais à la cible **implicite** du script de surface.
- Références BS, CEV, Heston/Fourier et SABR/PDE dans
  [vol_model_references.py](../../backend/scripts/vol_model_references.py).
- Programme indépendant d'évaluation des payoffs sur les simulateurs de production :
  [validate_vol_models.py](../../backend/scripts/validate_vol_models.py).
- UI : « SABR (spot simulé) » ; aide corrigée pour distinguer hypothèses,
  cible paramétrique et calibration de marché.
- Deux baselines LSV rebasées délibérément après la correction : call ATM à
  `N=2000`, 0,088875 → 0,088815 avec antithétiques (−0,60 bp),
  0,084951 → 0,084686 sans (−2,65 bps). Les autres baselines restent inchangées.

**42 tests backend ciblés passent** : références, régressions de queue basse, identité des marginales,
marginale LSV existante, autocall LV/LSV, branche de monitoring continu et
goldens. Frontend : 243 tests passent et build réussi. Aucune suite backend
complète, aucune donnée réelle modifiée, aucun serveur démarré pour ce lot.

## Reproduction

```powershell
.venv/Scripts/python.exe -X utf8 backend/scripts/validate_vol_models.py
```

Le cache PDE vérifie les paramètres, maillages et empreinte de la référence.
Les résultats comportent les paramètres, budgets, références, erreurs par point,
statuts et empreintes des sources ; les données restent synthétiques.
Budget MC maximal estimé : 0,736 Gio par simulation, sous la limite synchrone.
Le solveur PDE plafonne séparément ses dimensions et son nombre de pas.

Preuves locales :

- [Grille et statuts](../../output/vol-model-validation-20261007/results.json)
- [Références PDE et maillages](../../output/vol-model-validation-20261007/sabr_reference.json)
- [Contrôle de pas couplé](../../output/vol-model-validation-20261007/coupled_steps.py)
- [Résultats couplés](../../output/vol-model-validation-20261007/coupled_steps_results.json)
- [Isolation des causes LSV](../../output/vanilla-model-audit-20261007/lsv_probe_results.json)
- [Résultats avant affinement conditionnel](../../output/vol-model-validation-20261007/results-before-finer-grid.json)

Suite du chantier : fermer les réserves de digitaux/discrétisation à une tolérance
économique explicite, définir une surface commune sans arbitrage et vérifier sa
reproduction, puis seulement refaire la comparaison des autocalls mono/worst-of.
