# Audit du module Pricing — 17 juillet 2026

**Périmètre** : moteur Monte Carlo PayScript (`backend/app/core/payscript/` : engine, parser, simulation, scenarios), couche API (`backend/app/api/` : pricing, simulation, scenarios, kid), schémas Pydantic (`core/schemas.py`), suite de tests (`backend/tests/test_engine.py`, `test_parser.py`).

**Méthode** : lecture exhaustive du code + exécution de la suite de tests. Les corrections listées ci-dessous ont été appliquées le jour même ; chaque correction est couverte par un test de régression nommé.

**État final** : suite complète verte — **83/83 tests** (76 préexistants, 7 ajoutés), aucune régression.

---

## 1. Constats corrigés

### 1.1 🔴 Theta = pur bruit Monte Carlo (sévérité : critique)

**Constat.** `compute_greeks` calculait theta comme `price(dt_add=1/365) − base_price`. Or `dt_add` n'agit que via `ts = round(T×52)` : ajouter 1 jour ne franchit pratiquement jamais la frontière d'arrondi de la grille hebdomadaire, donc le run « bumpé » était bit-à-bit identique au run de base. Le theta affiché n'était que l'écart d'échantillonnage entre un run à N/4 chemins et le prix de base à N chemins — du bruit, sans signe ni magnitude fiables. Dans le cas rare où l'arrondi basculait, le bump *allongeait* la vie du produit (AT MATURITY glissait d'une semaine) au lieu de le vieillir.

**Action.** Theta recalculé par **vieillissement réel du produit d'un pas de grille (1 semaine)** : toutes les dates d'événement restantes décalées de −1/52 (réutilisation de `_shift_events_for_mtf`, qui droppe les dates passées), fenêtre STRIKE_FIX décalée de même, horizon raccourci à T−1/52, même seed (les tirages normaux partagent leur préfixe entre les deux formes de tenseur → CRN effectif en GBM/LV), puis mise à l'échelle par jour calendaire : `theta = (P_vieilli − P_base_Ng) / 7`. Garde-fou : `theta = None` si T ≤ 2 semaines.

**Fichier** : `backend/app/core/payscript/engine.py` (`compute_greeks`).
**Test** : `test_greeks_delta_gamma_theta_match_bs` — theta MC vs theta Black-Scholes analytique quotidien sur le call ATM, tolérance 1,5 bp/jour.

### 1.2 🔴 Gamma / corr-sensi : mélange de deux estimateurs (critique)

**Constat.** Le terme central de gamma (`(P₊ + P₋ − 2·base) / 0.0009`) et de la sensi de corrélation réutilisait le prix du run principal à N chemins, alors que les termes bumpés étaient repricés à N/4. Le principe des common random numbers exige que le centre partage le bruit des bumps pour qu'il s'annule ; l'écart d'échantillonnage résiduel (~10 bp) était amplifié par le dénominateur 9·10⁻⁴ → jusqu'à ±2 points de gamma d'artefact pur.

**Action.** Un prix de base `base_g` est recalculé une fois **au même N/4 et au même seed** que les bumps, et sert de centre à gamma, theta et corr. Le paramètre `base_price` de `compute_greeks` est supprimé (signature + appelant `api/pricing.py` mis à jour).

**Test** : `test_greeks_delta_gamma_theta_match_bs` — gamma MC vs gamma BS analytique (1,93), tolérance ±0,6.

### 1.3 🔴 Courbe de taux ignorée par les greeks (critique)

**Constat.** `compute_greeks` n'acceptait pas `yield_curve` : prix principal actualisé sur la courbe, tous les repricings de greeks en taux flat. Pour gamma/theta/corr (qui comparaient au prix « courbe »), l'écart courbe-vs-flat entrait au premier ordre dans les petits dénominateurs.

**Action.** `yield_curve` ajouté à la signature de `compute_greeks`, propagé dans chaque `run_mc` interne (y compris le run vieilli du theta), transmis depuis `api/pricing.py`.

**Test** : `test_greeks_accept_yield_curve` — une courbe plate au niveau de r reproduit exactement les greeks flat-r.

### 1.4 🔴 Classification « KI » sur PV actualisée (élevée)

**Constat.** `_eval_paths_detailed` (onglets Probabilités et Chemins MC) classait un chemin non autocallé en « ki » si son **payoff actualisé** < 0.999. Un remboursement au pair à 3 ans, r=5 % → PV 0,86 → étiqueté knock-in. Le comptage P(KI) et le coloriage des chemins dépendaient du taux d'intérêt.

**Action.** La fonction suit désormais aussi le flux **non actualisé** (`total_cf_raw`) et classe sur celui-ci. Au passage, elle accepte un `df_arr` optionnel : `run_mc_proba` actualise maintenant sur la courbe de taux si fournie (prix et percentiles cohérents avec `/price`).

**Test** : `test_proba_ki_classification_is_discount_independent` — produit remboursant le pair à maturité, r=5 % → 0 chemin « ki », 100 % « normal ».

### 1.5 🔴 Endpoints `async def` bloquant l'event loop (élevée, opérationnel)

**Constat.** Tous les endpoints pricing étaient `async def` avec un calcul CPU-bound synchrone : un run Heston de 30 s gelait toute l'API (autres onglets, autres utilisateurs, health checks) — FastAPI exécute les `async def` sur l'event loop, les `def` sur le threadpool.

**Action.** Conversion `async def` → `def` de tous les endpoints MC : `/parse`, `/price`, `/profile`, `/paths`, `/proba`, `/mtf`, `/backtest`, `/backtest/compare` (`api/pricing.py`), `/solve`, `/grid` (`api/simulation.py`), `/scenarios` (`api/scenarios.py`). `api/kid.py` était déjà synchrone. Aucun de ces handlers n'utilisait `await`.

### 1.6 🟠 `yield_curve`/`sigma_r` acceptés puis silencieusement ignorés (moyenne)

**Constat.** Le schéma `AnalysisBase` expose `yield_curve`, mais `/solve`, `/grid`, `/scenarios` repriçaient en flat-rate ; conséquence type : le solver résout un COUPON pour un prix cible flat, l'utilisateur reprice avec la courbe et le prix ne colle plus, sans message. `sigma_r`/`a_r` n'existaient que sur `/price`.

**Action.** `sigma_r`/`a_r` ajoutés à `AnalysisBase` (mêmes bornes que `PricingRequest`). Propagation complète `yield_curve`+`sigma_r`+`a_r` à travers `solve_for_param`, `compute_price_grid` (`core/payscript/simulation.py`), `compute_scenario_grid` (`core/payscript/scenarios.py`) et leurs endpoints. `/proba` actualise sur la courbe (cf. 1.4). Non traité, documenté ci-dessous : `/mtf` reste volontairement flat-r.

### 1.7 🟠 Matrice de corrélation : réparation silencieuse non normalisée (moyenne)

**Constat.** `cholesky()` réparait une matrice non-PSD en ajoutant `(−λmin+ε)·I` sans renormaliser — diagonale > 1, toutes les vols implicitement gonflées de √(1+ε). Aucune validation d'entrée (symétrie, bornes [−1,1], diagonale unité) : une matrice absurde priçait silencieusement.

**Action.** `cholesky()` valide désormais diagonale ≈ 1, symétrie, |ρ| ≤ 1 (ValueError français → 422 automatique via les handlers existants), et renormalise `D^{-1/2} C D^{-1/2}` après le jitter PSD pour restaurer une diagonale unité.

**Test** : `test_corr_matrix_validation_raises` — hors-bornes, asymétrique, diagonale ≠ 1 rejetés ; matrice quasi dégénérée valide (ρ=0.999) price toujours.

### 1.8 🟠 Dates AT ≤ 0 : indexation négative = look-ahead (moyenne, cas limite)

**Constat.** `AT 0:` (et même `AT -1:`) était accepté au parse ; un pas 0 faisait lire `S_min[-1]`/`WOF_min[-1]` — l'état **terminal** du chemin — à t=0 (indexation négative Python). Une date négative indexait tout le tenseur depuis la fin.

**Action.** Double verrou : (a) `_parse_dates` rejette toute date ≤ 0 avec un message explicite ; (b) les 5 sites de construction de `step_map` (run_mc, profile, paths, proba, MTF) clampent `max(1, round(d·SY))` pour les dates minuscules positives qui arrondiraient à 0 — même clamp que `_strike_fix_steps` appliquait déjà.

**Test** : `test_at_date_zero_or_negative_rejected` (`test_parser.py`).

### 1.9 🟠 Trou de couverture : aucun test quantitatif Heston au-delà de la martingale (moyenne)

**Constat.** Le prix Heston n'était jamais confronté à une référence : le test de martingale attrape un drift faux, pas un vol-de-vol ou une corrélation spot-vol mal câblés.

**Action.** Deux tests de limites exactes, plus robustes qu'une réimplémentation de la formule semi-fermée (elle-même source d'erreur) :
- `test_heston_collapses_to_bs_when_xi_tiny` — ξ→0 avec v0=θ pince la variance : Heston doit reproduire Black-Scholes(√v0) à 30 bp.
- `test_heston_skew_direction_follows_rho` — un put OTM doit valoir plus cher sous ρ=−0,7 que sous ρ=+0,7 (direction du skew) ; attrape une erreur de signe sur `rho_h` invisible au test de martingale.

---

## 2. Constats non corrigés (assumés, à suivre)

| # | Constat | Sévérité | Raison du report |
|---|---------|----------|------------------|
| 2.1 | ~~Heston et SABR simulés en boucles Python par chemin~~ **CORRIGÉ le 17.07.2026 (3e passe)** — voir la section 5 ci-dessous. | — | — |
| 2.2 | ~~Barrières monitorées hebdomadairement sans correction de continuité~~ **CORRIGÉ le 17.07.2026 (2e passe)** — voir la section 4 ci-dessous : mode `barrier_monitoring="continuous"` par pont brownien, opt-in. Reste hebdo-seulement : le MTF (garde 422 explicite). Le backtest historique était le même symptôme mais une cause différente (données réelles ignorées, pas un modèle à construire) — **corrigé séparément, voir section 6**. | — | — |
| 2.3 | **Mark-to-Future reste en flat-r** : `MtfRequest` accepte `yield_curve` (héritage `AnalysisBase`) mais le moteur MTF actualise en flat. | Faible | Le MTF est un diagnostic de distribution « paramètres gelés » ; l'écart est de second ordre sur des trajectoires relatives. À câbler si le MTF devient un chiffre contractuel. |
| 2.4 | **Mémoire non bornée hors MTF** : à N=200 000 (borne haute du schéma) × 5 sous-jacents × 3 ans, pic ~5-6 Go (tenseurs base + antithétique + tirages coexistent). | Moyenne (ops) | Chunking à la MTF_MAX_BATCH à généraliser — chantier de plomberie à faire avec 2.1. |
| 2.5 | **Gaps d'héritage d'état documentés** : S_MIN/S_MAX/S_PREV/REALVOL et FIX_* ne sont pas hérités par le repricing résiduel MTF ni rejoués par le backtest historique (documenté dans les docstrings du moteur). | Faible | Connu et affiché ; ne fausse que les scripts utilisant ces mots-clés dans ces deux analyses. |
| 2.6 | **Transpileur basé sur `exec`** : sandbox étanche en pratique (identifiants réécrits en lookups memo, builtins vides, toute construction hostile → SyntaxError), mais robustesse par accident plutôt que par conception. | Faible (sécu) | Recommandation long terme : whitelist AST + fuzzing du parser. |
| 2.7 | Divers cosmétiques : rescaling antithétique uniforme de la table de flux (df par jambe légèrement distordus), sensi de corr one-sided, percentiles sans interpolation, PARAM sans défaut négatif/scientifique, payload `/price` ~500 Ko (40 000 payoffs). | Faible | Rapport coût/bénéfice défavorable pour l'instant. |

---

## 3. Fichiers modifiés

| Fichier | Modifications |
|---|---|
| `backend/app/core/payscript/engine.py` | `cholesky` (validation + renormalisation) ; clamp step≥1 (5 sites) ; `_eval_paths_detailed` (df_arr, total_cf_raw, classification non actualisée) ; `run_mc_proba` (yield_curve) ; refonte `compute_greeks` (centre CRN, theta par vieillissement, yield_curve, suppression de `base_price`) |
| `backend/app/core/payscript/parser.py` | `_parse_dates` : rejet des dates ≤ 0 |
| `backend/app/core/payscript/simulation.py` | Propagation yield_curve/sigma_r/a_r (solver + grid) |
| `backend/app/core/payscript/scenarios.py` | Propagation yield_curve/sigma_r/a_r |
| `backend/app/core/schemas.py` | `AnalysisBase` : + `sigma_r`, `a_r` |
| `backend/app/api/pricing.py` | 8 endpoints async→def ; appel `compute_greeks` (signature + courbe) ; `/proba` passe la courbe |
| `backend/app/api/simulation.py` | 2 endpoints async→def ; nouveaux kwargs |
| `backend/app/api/scenarios.py` | 1 endpoint async→def ; nouveaux kwargs |
| `backend/tests/test_engine.py` | +6 tests (greeks vs BS, greeks+courbe, KI non actualisé, validation corr, Heston ξ→0, direction du skew) |
| `backend/tests/test_parser.py` | +1 test (dates AT ≤ 0) |

**Impact API** : suppression du paramètre positionnel `base_price` de `compute_greeks` (interne, un seul appelant) ; champs optionnels `sigma_r`/`a_r` ajoutés aux requêtes d'analyse (défaut 0 = comportement antérieur) ; convention theta désormais « décroissance par jour calendaire » (valeur vieillie − valeur actuelle, typiquement négative pour une optionalité longue). Aucun changement de clé dans les réponses.

**Vérification** : `pytest backend/tests/test_engine.py backend/tests/test_parser.py` → **83 passed** (1 min 54).

---

## 4. Deuxième passe (même jour) — monitoring continu des barrières (constat 2.2)

**Méthodologie retenue : pont brownien**, pas de décalage BGK — le moteur est agnostique au payoff (il ne connaît pas « la barrière » : les scripts comparent `WOF_MIN`/`S_MIN`/`BOF_MAX` à des expressions arbitraires). La correction porte donc sur les grandeurs de monitoring elles-mêmes : à chaque pas hebdomadaire, le minimum/maximum continu intra-pas de chaque sous-jacent est tiré de la loi conditionnelle exacte de l'extremum d'un pont brownien connaissant les deux extrémités (loi indépendante du drift → valable aussi sous taux stochastiques). Les extrema courants (`WOF_MIN`, `S_MIN[i]`, `S_MAX[i]`, `BOF_MAX`) s'accumulent alors sur ces extrema continus ; les valeurs aux dates d'observation (`WOF`, `S[i]`, fixings `FIX_*`, `REALVOL`) restent des constats discrets contractuels, inchangés.

**Exactitude** : exacte sous GBM (vol constante par pas) ; approximation « vol gelée dans le pas » sous Heston/SABR/LV/LSV — la vol effective réellement appliquée par le simulateur à chaque pas (`vol_out`, nouveau canal de sortie des 5 simulateurs) alimente le pont. Min et max sont tirés d'uniformes indépendantes : chaque marginale est exacte, la loi jointe intra-pas ne l'est pas (aucun script n'observe les deux barrières franchies dans la même semaine).

**Opt-in, pas de changement silencieux** : nouveau champ `barrier_monitoring` (`"weekly"` par défaut = comportement historique bit-à-bit identique, y compris le flux rng ; `"continuous"` en option), sur `PricingRequest` et `AnalysisBase`, propagé à `/price`, greeks, `/proba`, `/paths`, `/solve`, `/grid`, `/scenarios`. MTF : refus explicite 422 (l'héritage d'état outer→inner reste hebdomadaire). Profil de payoff et backtest : sans objet (chemin épinglé / clôtures historiques). Toggle UI « Monitoring barrières » ajouté dans Marché & Paramètres (`MarketParams.vue`), persisté dans les scripts sauvegardés, transmis par `_baseBody()`.

**Fichiers** : `engine.py` (`_bridge_extrema`, `vol_out` dans les 5 simulateurs, plumbing run_mc/_eval_paths/_eval_paths_detailed/run_mc_proba/run_mc_paths/compute_greeks, garde MTF), `schemas.py`, `api/pricing.py`, `core+api simulation.py`/`scenarios.py`, `stores/pricing.js`, `MarketParams.vue`.

**Validation** :
- `test_continuous_barrier_matches_first_passage_analytic` — la probabilité de franchissement MC en mode continu reproduit la formule fermée de premier passage GBM (écart < 1,2 pt à N=20 000), et le mode hebdo la sous-estime d'au moins 1 pt (écart mesuré ≈ 3 pts à σ=20 %, B=80 %, 1 an).
- `test_continuous_barrier_monitoring_runs_on_every_model` — les 5 modèles tournent en continu et P(hit) ≥ hebdo.
- `test_barrier_monitoring_invalid_value_raises` — valeur inconnue → erreur explicite.
- Vérification end-to-end via TestClient : hebdo 26,45 % vs continu 29,66 % sur l'indicateur de franchissement ; défaut ≡ hebdo ; 422 sur valeur invalide et sur MTF+continu ; greeks+courbe fonctionnels en continu.
- Suite backend complète : **113/113 verts** (2 min 50). Frontend rebuilt (`npm run build`).

**Impact prix attendu (à communiquer aux utilisateurs)** : en mode continu, P(KI) monte de plusieurs points sur un autocall type (barrière 60-70 %, σ 20-30 %) — la jambe put down-and-in vaut plus cher, le prix du produit baisse de l'ordre de quelques dizaines de bps. C'est le mode à utiliser quand la barrière contractuelle est continue ou daily ; le mode hebdo reste le défaut pour la reproductibilité des prix déjà cotés.

---

## 5. Troisième passe (même jour) — vectorisation Heston/SABR (constat 2.1)

**Constat initial** : `_simulate_heston` et `_simulate_sabr` itéraient `for path in range(N): for step: for asset:` en Python pur — mesuré avant correction, **38,4 s** pour un Heston à N=20 000 (le défaut de l'UI), **32,2 s** pour un SABR équivalent, contre des millisecondes pour GBM/LV/LSV (déjà vectorisés).

**Action** : portage step-major/vectorisé des deux simulateurs sur le pattern déjà utilisé par `_simulate_lv`/`_simulate_lsv` — la corrélation inter-actifs se fait par un seul produit matriciel `L @ Z_flat` reshapé au lieu d'un `L @ z_raw` par chemin, et le tirage QE de la variance Heston utilise `_heston_qe_vectorized` (déjà écrit pour le LSV, déjà testé) au lieu de `_heston_qe_scalar` appelé N fois. **Aucun changement de formule** : signatures identiques (drop-in, zéro modification des sites d'appel), constructions préservant la martingalité gardées à l'identique (V_bar pour la dérive Heston + terme de correction d'Andersen, `alpha_old` — pas `alpha_bar` — pour le vol effectif CEV du SABR, avec le commentaire d'origine expliquant pourquoi).

**Validation de non-régression** : deux boucles de référence scalaires, copies littérales du code d'avant refactor, ajoutées uniquement dans les tests (`_heston_reference_loop`, `_sabr_reference_loop`) et comparées aux nouvelles versions vectorisées sur les **mêmes tirages aléatoires** (2 actifs corrélés, mêmes `Z`/`Zv`/`Za`/`L`) : `test_heston_vectorized_matches_reference_loop`, `test_sabr_vectorized_matches_reference_loop` — écart maximal < 1e-8 (identité flottante, aucune différence économique). Les tests existants de justesse (martingale Heston, Heston→BS quand ξ→0, direction du skew, SABR vs Hagan) restent tous verts sans modification, ce qui confirme indépendamment que le refactor n'a rien changé au niveau du modèle.

**Gain mesuré** (mêmes conditions avant/après, script call vanille, N=20 000 = défaut UI) :

| Modèle | N | Avant | Après | Gain |
|---|---|---|---|---|
| Heston | 5 000 | 9,53 s | 0,32 s | ×30 |
| Heston | 20 000 (défaut) | 38,37 s | 1,33 s | ×29 |
| Heston | 200 000 (max) | (non mesuré, extrapolé >6 min) | 24,0 s | — |
| SABR | 5 000 | 8,13 s | 0,28 s | ×29 |
| SABR | 20 000 (défaut) | 32,22 s | 1,04 s | ×31 |
| SABR | 200 000 (max) | (non mesuré, extrapolé >5 min) | 13,9 s | — |

**Fichiers** : `backend/app/core/payscript/engine.py` (`_simulate_heston`, `_simulate_sabr`, docstring de `_heston_qe_vectorized` mise à jour), `backend/tests/test_engine.py` (+2 tests, docstring de `test_heston_qe_vectorized_matches_scalar` corrigée — `_heston_qe_scalar` n'est plus utilisé en production, gardé uniquement comme référence testée).

**Vérification** : suite complète **115/115 verts** — et le temps d'exécution de la suite elle-même est passé de 170 s à **61 s** (2 min 50 → 1 min 01), la plupart des tests Heston/SABR à N=20 000 tournant maintenant en une fraction de seconde au lieu de dizaines de secondes chacun.

**Effet secondaire positif non recherché** : comme `compute_greeks` fait 4 à 10 repricings par calcul de greeks (chacun à N/4), et que `/scenarios`/`/solve`/`/grid` font des dizaines à des centaines de repricings, le gain se multiplie sur ces chemins — un calcul de greeks complet en Heston, qui prenait plusieurs minutes, prend maintenant quelques secondes.

---

## 6. Quatrième passe (même jour) — backtest : lecture des clôtures entre dates d'observation (partie restante du constat 2.2)

**Constat.** `eval_script_on_history` (utilisé par `/backtest` et `/backtest/compare`) ne regardait les prix historiques **qu'aux dates d'observation `AT` du script lui-même** — un autocall à constats trimestriels ne sondait le prix que tous les trimestres. Un franchissement de barrière survenu et récupéré *entre* deux dates de constat n'était jamais vu, alors que les clôtures quotidiennes réelles de cette période étaient déjà chargées en mémoire (`prices_by_ticker`, grille journalière 252 jours/an) — contrairement au moteur Monte Carlo (section 4), il ne s'agissait pas d'un modèle à construire, juste de données déjà disponibles et ignorées.

**Bug additionnel trouvé en cours de route** : `bof_max` (le maximum courant utilisé par un script via `BOF_MAX`) n'était **jamais accumulé dans le temps** — recalculé à chaque étape uniquement à partir des spots de l'étape courante, contrairement à `wof_min` qui, lui, accumulait déjà correctement. Un script utilisant `BOF_MAX` en backtest oubliait tout sommet atteint aux observations précédentes.

**Action.** Nouvelle fonction `_historical_running_extrema(prices_by_ticker, tickers, ref, lo_hi, hi_hi)` : balaie tous les jours de bourse entre deux dates de constat (bornes incluses côté fin) et retourne le vrai min/max réalisé sur la fenêtre — neutre (`math.inf`/`-math.inf`, sans effet sur un `min()`/`max()` appelant) si la fenêtre est vide ou sans données. `eval_script_on_history` l'appelle à chaque étape (boucle des observations `AT` et bloc de maturité), en conservant un curseur `prev_hi` de la dernière date scannée, et accumule maintenant `bof_run` exactement comme `wof_run`.

**Validation** :
- `test_historical_running_extrema_finds_mid_window_dip` / `..._empty_window_is_neutral` — la primitive elle-même.
- `test_backtest_replay_captures_intra_period_barrier_breach` — scénario construit : prix plat (spot=1.0) à toutes les dates de constat, avec un creux à 50 % un seul jour strictement entre deux dates `AT` ; barrière à 70 %. Avant le correctif, l'indicateur de franchissement ne se serait jamais déclenché (les deux dates de constat elles-mêmes affichent spot=1.0) — après, il se déclenche correctement.
- `test_backtest_replay_no_breach_when_price_stays_above_barrier` — contre-exemple : un creux qui reste au-dessus de la barrière ne déclenche rien (garde contre un correctif qui déclencherait à tort systématiquement).
- `test_backtest_bof_max_accumulates_across_observations` — un pic isolé avant la première date de constat survit jusqu'à la maturité.
- Vérification end-to-end via `/api/backtest` avec des données de marché réelles (AAPL, 2018-2026) : 26 fenêtres calculées sans erreur, endpoint inchangé au niveau contrat (aucun champ de requête/réponse modifié — le fix est entièrement interne à `eval_script_on_history`).
- Suite complète : **120/120 verts** (57 s).

**Fichiers** : `backend/app/core/payscript/engine.py` (nouvelle fonction `_historical_running_extrema`, `eval_script_on_history` modifiée), `backend/tests/test_engine.py` (+5 tests). Aucun changement de schéma ni d'endpoint — correctif entièrement interne, transparent pour le frontend.
