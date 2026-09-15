# MtM résiduel d'un deal actif — design (2026-07-19)

## Objectif

Valoriser les **cash-flows futurs restants** d'un deal vivant, au lieu de relancer le produit
"comme neuf" : calendrier résiduel réel, spots de départ au niveau actuel en % du strike,
état path-dependent réalisé (KI/extrema, coupons mémoire, index d'observation) injecté comme
condition initiale du Monte Carlo. Doit fonctionner pour les scripts **normaux** (`AT 1,2,3`)
et **experts** (calendriers `CONSTAT`).

## Principe : replay + shift (réutilise la machinerie Mark-to-Future)

```
   passé (réalisé)                    │ aujourd'hui          futur (simulé)
   ────────────────────────────────── │ ─────────────────────────────────────
   eval_script_on_history             │ run_mc sur T_remaining
   → cash-flows déjà payés           │ → spots initiaux = spot/strike actuels
   → état final : memo (SET/mémoire),│ → wof_min_init/bof_max_init = extrema réalisés
     index d'obs, wof_min/bof_max    │ → index_offset = nb d'obs passées (PARAM() dégressifs)
                                      │ → memo_init = état des variables du script
```

1. **Replay du passé** — `eval_script_on_history` (déjà utilisé par le cycle de vie) rejoue le
   script figé sur l'historique Yahoo depuis le strike. Étendu pour retourner aussi l'**état
   final du contexte** : `memo` (variables SET, coupons mémoire), `index` (compteur d'obs),
   `wof_min`/`bof_max` réalisés, `accum`. Si le replay détecte un rappel → le deal aurait dû
   être résolu : on renvoie l'issue réalisée (même court-circuit que le reprice actuel).
2. **Shift des events** — `_shift_events_for_mtf(events, T_elapsed)` (déjà écrit pour le
   Mark-to-Future) : les dates passées sont retirées, les futures translatées de −T_elapsed,
   `AT_MATURITY` inchangé (fire en fin d'horizon résiduel).
3. **MC résiduel** — `run_mc` sur `T_remaining = (maturity − today)/365.25` avec :
   - `spot_mult` = spots normalisés actuels (spot/S₀ par sous-jacent) — support existant ;
   - `wof_min_init`/`bof_max_init` (existants dans `_eval_paths`, à exposer dans `run_mc`) ;
   - `index_offset` (nouveau) : le compteur d'obs continue au bon rang — un PARAM() dégressif
     lit la bonne ligne de son tableau ;
   - `memo_init` (nouveau) : état des variables injecté **après** `init_fn` (sinon les SET
     réinitialiseraient les coupons mémoire).
   Le MtM = espérance actualisée des flux futurs uniquement (l'actualisation démarre à 0 =
   aujourd'hui, naturellement, puisque le tenseur simulé démarre aujourd'hui).

## Normal vs expert : un seul chemin de code

`resolve_constats` transforme les calendriers CONSTAT en `CompiledEvent.dates` (fractions
d'années) — même représentation que le mode `AT`. Deux prérequis :

- **Persister les constats au booking** : le frontend ajoute `constats: _buildConstats()` au
  `market_snapshot` (aujourd'hui ils ne sont envoyés qu'au pricing — c'est le "known gap" qui
  empêche déjà le replay cycle de vie des deals experts).
- **Ancre de résolution** : `resolve_constats` convertit les dates en années **depuis
  aujourd'hui** ; pour un deal booké dans le passé il faut une ancre explicite →
  paramètre `anchor` (défaut `date.today()`, comportement inchangé), le replay passe
  `value_date`.

Deals experts déjà bookés sans constats persistés : erreur claire (« calendriers CONSTAT non
persistés — re-booker le deal ») plutôt qu'une valo fausse.

## Héritage complet de l'état path-dependent (ajout 2026-07-19 après-midi)

Les observables restantes sont désormais héritées elles aussi (gap comblé) :

- **`S_MIN[i]`/`S_MAX[i]`** : extrema quotidiens per-asset réalisés (normalisés S₀), foldés
  dans les tenseurs `S_min`/`S_max` via `s_min_init`/`s_max_init` (même style broadcast que
  `wof_min_init`).
- **`S_PREV[i]`** : spots du dernier constat passé, injectés via `s_prev_init` (seed de
  `ctx["spots"]` — la mécanique existante fait le reste au premier constat résiduel).
- **`REALVOL`** : combinaison passé réel / futur simulé par **sommation des variations
  quadratiques** — `realvol = sqrt((sumsq_passé + sumsq_futur) / (t_passé + t_futur))`.
  L'estimateur du moteur (Σr²/t, sans centrage) est indépendant de la fréquence
  d'échantillonnage, donc quotidien (passé) + hebdo (futur) se combinent exactement.
  Nouveau `wof0_init` : la série WOF simulée démarre au niveau seedé (sinon le premier
  return hebdo log(spot/1.0) compterait tout le drift passé comme un rendement fictif.
- **`FIX_MIN/FIX_MAX/FIX_AVG`** (fenêtre STRIKE_FIX) : partie passée rejouée sur les closes
  réels (`fix_state`), partie future simulée ; moyenne pondérée par comptes, min/max croisés.
  Frontière unique `d ≤ T_elapsed` → passé, jamais de double comptage.
- Le replay (`eval_script_on_history`) calcule et retourne tout cet état dans `state` —
  et ne crashe plus sur un script lisant `S_MIN`/`S_PREV`/`REALVOL` à une observation passée
  (ces clés manquaient du ctx : hard-fail corrigé, pas seulement des valeurs fausses).

**Reste hors périmètre** : le Mark-to-Future n'hérite toujours pas de ces observables pour
ses scénarios outer (il faudrait des états par chunk + un wof0 par scénario) — documenté
dans la docstring de `_eval_paths`.

## Recalibration marché (ajout 2026-07-19 après-midi)

`POST /api/deals/{id}/mtm` accepte un body optionnel (absent = comportement historique,
bit-identique) :

```json
{ "recalibrate": "none" | "realized", "overrides": {"Nom": {"sigma": 35, "q": 2}},
  "r": 3.5, "window_days": 252 }
```

- **`realized`** : σ par sous-jacent = vol réalisée annualisée `sqrt(252·mean(r²))` (même
  convention RMS que REALVOL, cohérence interne) sur les 252 derniers rendements quotidiens
  communs — réutilise l'historique déjà fetché pour le replay, zéro fetch supplémentaire.
  Corrélations Pearson sur la même fenêtre, régularisées PSD (clip des valeurs propres,
  mini-Higham) → le cholesky du moteur ne lève jamais. `core/calibration.py`.
- **Modèle forcé à GBM en mode realized** (et dès qu'un override de σ est fourni) : la vol
  réalisée est un chiffre GBM-like ; garder Heston/SABR/LV avec juste σ échangé serait un
  no-op trompeur ou un mélange incohérent (niveau frais + smile figé). Visible dans la réponse.
- **Priorités** : overrides manuels > realized > booking. `q` jamais recalibré (pas de source
  dividendes). `r` fourni → taux flat, courbe du booking ignorée (mélange incohérent sinon).
- **`market_used`** toujours présent dans la réponse (source, modèle, r, σ/q par sous-jacent,
  corr, nb de rendements) — un MtM ne se quote jamais sans savoir ce qui l'a pricé.
- UI Booking : select « Params booking / Marché actuel » à côté du bouton 💰 MtM, badge
  « recalibré marché (GBM, N rendements) » sur le résultat (σ au survol). Overrides = API only.
- Le replay du passé et l'état hérité ne dépendent jamais de la recalibration (passé = réalisé).

## Limitations assumées (documentées dans le code)

- Le replay est anchoré au strike avec la convention « dernier close ≤ date » existante.
- REALVOL passé estimé sur closes quotidiens : un REALVOL contractuel défini sur fixings
  hebdo exacts différerait marginalement — assumé.
- Mark-to-Future : périmètre d'héritage inchangé (wof_min/bof_max seulement).

## API & UI

- `POST /api/deals/{id}/mtm` (deal actif uniquement) → `{mtm, ic95, T_remaining, T_elapsed,
  realized_cash_flows, norm_spots, wof_min_realized, obs_passees, obs_restantes}`.
- Fiche détail Booking : bouton « MtM résiduel » → affiche MtM % ± IC, comparaison au
  `price_traded`, flux déjà payés. (Le « → Ouvrir » vers le Pricer reste le repricing
  plein-édition, inchangé.)

## Tests

- Autocall certain d'être rappelé à la prochaine obs (WOF ≫ barrière, obs dans 3 mois) →
  MtM ≈ df(0.25)·(100% + coupon) — sanity analytique.
- PARAM() dégressif : avec `index_offset=k`, la barrière lue est la ligne k+1.
- Phoenix mémoire : coupons manqués injectés via `memo_init` payés si rattrapage simulé.
- KI déjà touché (`wof_min_init < KI_BAR`) → le put est vivant dans 100% des chemins.
- Un script normal et un script expert (CONSTAT persisté) donnent le même MtM à calendrier
  identique.

Ajouts 2026-07-19 après-midi (149/149) : KI per-asset `S_MIN` déjà franchi, REALVOL hérité
(variation quadratique, valeur analytique), phantom return tué par `wof0_init`, STRIKE_FIX
passé (valeur fermée spot/FIX_AVG) et à cheval (pondération par comptes), `S_PREV` hérité
(coupon momentum), état étendu du replay vérifié à la main sur série synthétique, régression
crash `S_MIN` à une obs passée ; calibration réalisée (σ exact, corr PSD + dégénérée
régularisée, fenêtre tronquée / minimum de rendements).
