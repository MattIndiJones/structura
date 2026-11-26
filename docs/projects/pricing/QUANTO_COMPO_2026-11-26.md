# Sous-jacents quanto et compo — 26/11/2026

**État : fait, non commité.** Moteur (cinq modèles de vol), schéma, cours de vie, Pricer.
Validé contre formules fermées et par changement de numéraire (`backend/tests/test_quanto_compo.py`, 21 tests).

## Ce qui existait

Chaque sous-jacent portait `sigma_fx`, `rho_sfx` et `ccyh`, appliqués au drift :
`r_deal + ccyh − q − ρ·σ·σ_FX`. C'est la correction quanto **au taux du deal** : le forward
d'un S&P 500 dans un deal EUR partait du taux EUR au lieu du taux USD, soit environ
1,5 pt de drift par an faux à r_USD − r_EUR = 1,5 %. Seul un `ccyh` saisi à r_USD − r_EUR
compensait. Ce traitement n'avait jamais été validé (audits du 16 et du 18/11). Aucun compo.

## Ce qui est livré

Un champ `fx_mode` par sous-jacent, et `r_ccy`, le taux sans risque plat de la devise du
sous-jacent (`payscript/fx_overlay.py`).

| Mode | Payoff lu | Drift du sous-jacent sous la mesure du deal | Volatilité |
|---|---|---|---|
| absent (« Historique ») | performance en devise du sous-jacent | `r_deal + ccyh − q − ρσσ_FX` | σ |
| `quanto` | performance en devise du sous-jacent, payée en devise du deal | `r_ccy + ccyh − q − ρσσ_FX` | σ |
| `compo` | `S·X`, sous-jacent converti en devise du deal | `r_deal − q` (produit) | `√(σ² + σ_FX² + 2ρσσ_FX)` |

- **Convention de change** : `X` = unités de devise du deal pour une unité de devise du
  sous-jacent (EUR par USD pour un S&P 500 dans un deal EUR). `ρ` est la corrélation
  sous-jacent/`X`.
- **Compo** : le sous-jacent diffuse avec le drift quanto, puis une trajectoire de change
  `dX/X = (r_deal − r_ccy) dt + σ_FX dW_X`, avec `dW_X = ρ dW_S + √(1−ρ²) dW⊥`, est posée
  dessus. Elle est bâtie sur **le brownien même du sous-jacent**. Le pont brownien des
  barrières continues lit la volatilité composite. Les deux jambes antithétiques retournent
  aussi `dW⊥`.
- **Actualisation** : inchangée, au taux et au funding du deal.
- **Clause contre hypothèse** : `fx_mode` appartient à l'identité contractuelle du
  sous-jacent dans l'objet Product (`UnderlyingIdentity`, `IDENTITY_FIELDS`), avec le nom,
  le ticker et la devise. Un contexte de marché ne peut pas changer un quanto en compo, et
  une RFQ le gèle comme ses autres termes. `r_ccy`, `sigma_fx`, `rho_sfx` et `ccyh` restent
  des hypothèses de marché. Le deal enregistre le tout dans son instantané de marché
  (unités d'écran : `r_ccy` en %), que la revalorisation en cours de vie relit.
- **Mode absent** : le prix reste identique au bit (test dédié). Les produits enregistrés
  avant le 26/11 ne bougent pas.

## Par modèle de volatilité

Principe commun : la surface d'un sous-jacent étranger est cotée sous **sa** mesure. Le
changement de mesure ne touche que les drifts (Girsanov), jamais les coefficients de
diffusion. Tout processus dont le brownien est corrélé au change reçoit
`−(sa vol)·σ_FX·corr(W, W_X)`.

| Modèle | Spot | Facteur de vol | Calibration |
|---|---|---|---|
| Constante | `−ρσσ_FX` | — | — |
| Heston | `−ρ√V σ_FX` | dV gagne `−ξ σ_FX ρ_h ρ √V dt` : en **√V**, la variance du deal n'est plus un Heston affine. θ effectif par trajectoire, `θ − c√V/κ`, dans le QE et dans le terme d'Andersen | — |
| SABR | `−ρσσ_FX` | d(log α) gagne `−ν σ_FX ρ_SABR ρ dt`, constant | — |
| Vol locale | `−ρ σ_loc(S,t) σ_FX` | — | grille Dupire construite sur le portage `r_ccy + ccyh − q` du sous-jacent |
| LSV | `−ρ L√V σ_FX` | comme Heston | levier entraîné **sous la mesure propre** (`own_measure_leverage`), avec le même estimateur particulaire que le pricing, 131 072 trajectoires, graine fixe ; réutilisé tel quel sous la mesure du deal |

Une première version du 26/11 reparamétrait Heston en κ' = κ + ξσ_FXρ_hρ. C'est faux :
la correction est en √V, pas en V. Elle sous-estimait la correction d'un facteur 1/√V
(≈ ×4,5 à 22 % de vol) et le put 80 % sortait 0,27 pt trop cher. Le changement de
numéraire l'a trouvé.

Un levier LSV entraîné avec `_fit_marginal` (lissage gaussien, qualifié sur SSVI) laissait
un biais de −0,07 pt sur la nappe paramétrique. L'estimateur particulaire le ramène à
+0,02/+0,04 pt, du même ordre que le LSV particulaire historique.

## Courbe de taux de la devise du sous-jacent

`ccy_curve` par sous-jacent : piliers `[[maturité, taux zéro]]`, même format et même
validation que la courbe du deal, construits par le même `_build_rate_term` sur la même
grille. Vide, le taux plat `r_ccy` s'applique, au bit près comme avant. Elle porte, pas à pas :

- le drift quanto (`r_ccy(t) + ccyh − q − ρσσ_FX`) dans les cinq diffuseurs ;
- la trajectoire de change du compo (`r_deal(t) − r_ccy(t)`) ;
- le portage de la nappe de vol locale (taux zéro de la devise) ;
- l'entraînement du levier LSV (taux par pas).

L'actualisation reste celle du deal. Saisie dans le bloc « Quanto / CCY » du Pricer
(interrupteur « Courbe {devise} », piliers en années et en %). Le booking l'enregistre dans
l'instantané (`ccyCurve`, `ccyCurveEnabled`), et la revalorisation en cours de vie ne la lit
que derrière un interrupteur actif. C'est une hypothèse de marché, pas un terme du Product.

Contrôles (constante, r_deal 3 %, courbe 2 % à 6 mois, 3,5 % à 2 ans, 5,5 % à 5 ans) :

- call quanto européen à 5 ans : 30,903 contre 31,086 (Black-Scholes au taux zéro 5 ans,
  1,4 erreur standard) ;
- autocall Athena 5 ans **compo** : même prix au millionième, courbe pentue ou taux plat de
  même zéro 5 ans. La courbe étrangère entre dans S et ressort avec le change ;
- même autocall **quanto** : −0,40 pt à zéro 5 ans égal, par la pente lue aux dates de rappel ;
- vol locale à ρ = 0 : quanto × DF_ccy / DF_deal = prix en devise étrangère sur la même courbe,
  à 1e-5 près ; LSV dans son résidu de calibration (−0,04 pt).

## Mesures de validation (instances)

Constante, r_deal 3 %, r_ccy 4,5 %, q 2 %, σ 22 %, σ_FX 10 %, 3 ans :

| Cas | Moteur | Référence |
|---|---|---|
| Call quanto, ρ = −0,4 | 19,942 | 19,931 (BS, forward `r_ccy − q − ρσσ_FX`) |
| Call compo, ρ = −0,4 | 14,322 | 14,325 (BS, vol composite) |
| BRC compo, barrière 60 % continue | 92,756 | 92,787 |

Smile, put 80 % à 3 ans, σ_FX 20 %, ρ = −0,6, référence **par changement de numéraire**
(tout sous la mesure du sous-jacent, sans terme quanto, prix = `e^{−r_ccy T} E^f[f·X_0/X_T]`) :

| Modèle | Quanto moteur / réf. | Compo moteur / réf. |
|---|---|---|
| Heston (κ 1, ξ 0,8, ρ_h −0,7) | 3,057 / 3,031 | 4,855 / 4,881 |
| SABR (ν 0,8, ρ −0,5) | 4,654 / 4,572 | 5,806 / 5,757 |
| Vol locale (skew −0,10, convexité 0,05) | 3,471 / 3,447 | 3,939 / 3,956 |
| LSV (même nappe, κ 1,5, ξ 0,6) | 3,689 / 3,664 | 4,911 / 4,866 |

Vol locale à ρ = 0 : quanto × e^{(r_deal − r_ccy)T} = prix en devise étrangère, au 1e-6.

## Limites

- **LSV quanto/compo** : à l'émission seulement, sans taux stochastique ni courbe de dividende.
  La valorisation en cours de vie (spot ancré, fixings) le refuse avec un message explicite.
- **Mark-to-Future** : le compo et la courbe de la devise y sont refusés. Ses générateurs
  extérieurs et intérieurs ne passent pas par `run_mc` : ils ne posent pas la jambe de change
  et repartent d'un compteur de pas local à chaque date de marque. Le quanto à taux plat y est juste.
- **Cours de vie compo** : les fixings passés doivent être exprimés en devise du deal
  (S·X). Aucun historique de change n'est chargé automatiquement.
- **KID** : le bootstrap PRIIPs refuse toujours un sous-jacent en devise étrangère
  (point 22(c) de l'annexe II).
- Les études ATM, l'Optimizer et la calibration qualifiée refusent un mode de change.

## Fichiers

`core/payscript/fx_overlay.py` (nouveau), `diffusion.py` (drift via `asset_carry_rate`,
corrections de variance Heston/LSV et de α SABR), `local_vol.py` (portage propre),
`lsv_leverage.py` (`own_measure_leverage`),
`monte_carlo.py` (tirage `W_fx`, superposition sur les deux jambes), `core/schemas.py`,
`core/inlife_valuation.py`, `api/inlife.py`, `core/valuation_context.py`,
`core/ccr/*`, gardes de `api/pricing.py`, `services/calibration_evidence.py` et
`lsv_leverage.py` ; Pricer : `MarketParams.vue` (choix Historique / Quanto / Compo et
taux de la devise), conversions de `requestState.js` et `loaders.js`, récapitulatifs.
