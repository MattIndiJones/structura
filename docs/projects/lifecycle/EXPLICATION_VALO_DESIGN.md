# Explication de valo (P&L explain entre deux dates) — design (2026-07-19)

**Statut : IMPLÉMENTÉ le 2026-07-19 (soir), 162/162 tests, build OK, validé en réel.**
Arbitrages : σ booking quand d1 = date de booking (σ réalisée sinon), waterfall
Temps/Spot/Vol/Corr + résidu + flux détachés, UI dans la fiche détail Booking.

Validation réelle DEMO-20260718-026 (booking 2025-11-05 → 2026-07-19) :
96.16% → 106.56% = +4.97 temps, +3.66 spot (SPX 98.8→108.8%), +1.78 véga (σ 22→13.3),
résidu 0.00 — chaîne télescopique exacte.

Notes d'implémentation : `_mtm_core(asof=...)` (troncature par la date de fin du fetch),
ctx enrichi (residual_script, engine_uls, corr, model_used, r_frac, yc…),
`_run_explain_step(cal, spot, uls, corr, model, common)` — bundle calendrier
(script résiduel + T_remaining + index_offset) / bundle spot (norm_spots + état
path-dependent) / bundle vol. La chaîne finit exactement sur la photo 2 → résidu ≈ 0
par construction (ligne gardée comme invariant affiché). Tests offline :
`tests/test_mtm_explain.py` (DB sqlite mémoire + load_hist_prices monkeypatché —
marché plat → tout dans le temps, rampe de spot → delta domine, identité télescopique,
gardes 422, phrases).

## Objectif

Répondre à « le produit a pris X% grâce au delta, perdu Y% par le véga » : décomposer
`MtM(d2) − MtM(d1)` en effets de risque, entre deux dates au choix (défauts : d1 = date
de valeur du booking, d2 = aujourd'hui). Réévaluations successives à seed identique (CRN).

## Méthodologie (ordre canonique, à documenter dans le code)

Deux photos complètes via la machinerie MtM résiduel existante, puis on change UN facteur
à la fois :

| # | Étape | Ce qui change | Lecture |
|---|-------|---------------|---------|
| 0 | MtM(d1) | — | point de départ |
| 1 | **Effet temps** | calendrier d1 → d2 (T_remaining, events shiftés), spots/σ/état de d1 | theta, pull-to-par |
| 2 | **Effet spot** | spots d1 → d2 **ET état path-dependent d1 → d2** (wof_min, s_min, index, memo, accum — un KI touché entre les deux est un effet spot) | delta (+ gamma) |
| 3 | **Effet vol** | σ(d1) → σ(d2) | véga |
| 4 | **Effet corrélation** | corr(d1) → corr(d2) — seulement si n_uls > 1 | cega |
| 5 | **Résidu** | ΔMtM − Σ effets | croisés + bruit MC (petit grâce au CRN) |

Ligne à part, hors modèle : **flux détachés entre d1 et d2** (coupons/remboursements
payés dans l'intervalle, depuis `realized_cash_flows` des deux replays — différence des
deux listes). Identité affichée : `MtM(d2) − MtM(d1) + flux détachés = P&L de la période`.

### Conventions de marché

- **σ à d1** : si d1 = value_date → **σ du snapshot booking** (l'effet véga répond à
  « pricé à 22 de vol, le marché a fait 13 ») ; sinon → σ réalisée fenêtre 252 j se
  terminant à d1 (`realized_market` sur historique tronqué). σ à d2 : réalisée à d2
  (ou booking si d2 = aujourd'hui et mode booking demandé — garder le body MtmRequest).
- **r constant** entre les deux dates (pas de source de taux historiques) — pas de ligne
  rho en v1, dit explicitement dans la réponse.
- Modèle : GBM dès qu'une σ réalisée intervient (même règle que la recalibration MtM).
- Chaque ligne du waterfall garde le même seed 42 et le même n_paths.

## Extension moteur nécessaire : MtM « as-of »

`_mtm_core(deal, session, n_paths, body, asof: date | None = None)` :
- tronquer l'historique à asof : `dates_list`/`prices` coupés au dernier index ≤ asof
  (le replay, l'état hérité, norm_spots, wof_min… suivent tout seuls) ;
- `T_elapsed`/`T_remaining` calculés vs asof au lieu de today ;
- `realized_market` sur l'historique tronqué (fenêtre finissant à asof) ;
- garde : si le replay tronqué détecte un rappel avant asof → 422.

Pour les étapes intermédiaires du waterfall (mix d'états), il faudra un helper qui
assemble un run_mc à partir de morceaux des deux photos (calendrier de l'une, spots/état
de l'autre…) — extraire de `_mtm_core` une fonction `_run_residual_mc(photo)` qui prend
une photo dict {T_remaining, residual_script, norm_spots, state, engine_uls, corr, r, yc}.

## API

`POST /api/deals/{id}/mtm/explain` body `{date1?: iso, date2?: iso, recalibrate?: ...}`
(défauts value_date / aujourd'hui) →
```json
{ "date1": ..., "date2": ..., "mtm1": ..., "mtm2": ...,
  "steps": [{"label": "Effet temps", "delta_pts": 0.8, "mtm_after": ...}, ...],
  "residual_pts": ..., "flows_detached": [{"t":..., "cf":...}], "flows_total_pts": ...,
  "market1": {...}, "market2": {...}, "phrases": ["...", ...] }
```
Phrases à base de règles comme la note de valo (signe + magnitude + cause).

Gardes : d2 ≤ d1 → 422 ; d1 < value_date → clamp à value_date ; produit rappelé/échu
entre d1 et d2 → 422 avec message « expliquer la résolution, pas un MtM » ; d2 dans le
futur → 422.

## UI (fiche détail Booking)

Dans l'accordéon du deal, nouveau bloc « Explication de valo » : deux `<input type=date>`
(d1 pré-rempli value_date, d2 aujourd'hui), bouton « Expliquer » → tableau waterfall
(une ligne par effet : label, points signés colorés, phrase), ligne flux détachés, ligne
résidu, total = ΔMtM. Petit graphique cascade optionnel (barres cumulées) si simple.
Réservé aux deals actifs.

## Tests (offline, patterns test_engine.py — séries synthétiques)

- Marché figé entre d1 et d2 (mêmes spots, même σ) → tous les effets ≈ 0 sauf temps ;
  résidu ≈ 0 (CRN).
- Choc de spot pur (σ identiques) → effet spot ≈ ΔMtM, véga ≈ 0.
- Choc de vol pur → véga ≈ ΔMtM.
- Coupon détaché entre d1 et d2 → ligne flux = coupon, identité P&L vérifiée.
- d2 ≤ d1 → 422 ; rappel entre les dates → 422.
- Somme des lignes + résidu == ΔMtM exactement (par construction).

## v2 (hors périmètre v1)

- Effet spot décomposé par sous-jacent (n runs de plus) — utile sur worst-of.
- Ligne rho si source de taux historiques un jour.
- Injection du waterfall dans la note de valo PDF (page 2).
