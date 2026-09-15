> ⚠️ **ARCHIVÉ (2026-07-16)** — référence technique détaillée mais datée : utilise la terminologie
> obsolète "TVA"/`amc_tva.py` (renommé depuis en "VAG"/`amc_bh.py`), et documente au moins deux
> formules **désormais fausses** telles que présentées ici — le diviseur de `alpha_score` du Bloc I
> (documenté à 0.10, corrigé à 0.175 le 2026-07-16) et le signe du sous-score drawdown-vs-benchmark
> du Bloc J (documenté `50 − (...)`, corrigé en `50 + (...)` le 2026-07-16, l'ancien signe pénalisait
> à tort un gérant plus prudent que son benchmark). Ne pas s'y fier pour une formule sans vérifier
> le code actuel. Conservé pour l'historique et pour les sections encore valables (architecture
> générale, Blocs A/C/D/F/G non touchés par ces deux corrections).

# Structura — Fiche de Reprise de Travail

> **Projet :** Structura — Plateforme d'analyse AMC (Actively Managed Certificates)  
> **Stack :** FastAPI (Python) · Vue 3 (Vite) · ReportLab (PDF) · statsmodels (OLS)  
> **Client AMC en test :** ISIN CH1473733959 · LUKB NEÜ Infrastructures Basket · USD  
> **Société :** TP Advisory Services · Client rapport : UTI  
> **Dernière mise à jour :** 2026-06-26

---

## 1. Architecture générale

```
backend/
  app/
    api/
      amc.py           → endpoints étude (run, export PDF, manager-skill)
      amc_prices.py    → endpoint TVA (calcul + MSS embarqué)
      auth.py          → JWT auth
    core/
      amc_study.py         → orchestrateur principal run_study()
      amc_engine.py        → moteur Fama-French OLS (Block A)
      amc_blocks.py        → Blocks B (attribution), C (trading), D (conviction)
      amc_timing.py        → Block H — Timing Score
      amc_stockpicking.py  → Block I — Stock Picking Score
      amc_riskmanagement.py→ Block J — Risk Management Score (5 sous-scores)
      amc_tva.py           → Block E — Trading Value Added
      amc_replicability.py → Block F — Réplicabilité
      amc_managerskill.py  → Manager Skill Score (agrégateur)
      amc_confidence.py    → Score de confiance global
      amc_pdf.py           → Génération PDF ReportLab (export étude)
      amc_manifest.py      → Manifest StudyManifest + BLOCK_CATALOG
      amc_orderbook.py     → Reconstruction FIFO des positions

frontend/
  src/
    views/AmcView.vue  → Interface principale (tous les blocs, export PDF)
```

---

## 2. Flux d'exécution principal

```
POST /api/amc/study/run
  ├── load_study_data()        → charge NAV, ordres, composition (Def.txt)
  ├── reconstruct()            → reconstruction FIFO des round-trips
  ├── _run_block_a()           → régression FF OLS (gross + net)
  ├── block_b_attribution()    → P&L par ligne / FX
  ├── block_c_trading()        → activité trading
  ├── block_d_behaviour()      → matrice conviction
  ├── compute_timing_score()   → Block H (nécessite prix en cache)
  ├── compute_stockpicking_score() → Block I
  ├── compute_risk_management_score() → Block J
  ├── compute_manager_skill_score()   → MSS (sans TVA au stade initial)
  ├── compute_replicability()  → Block F (nécessite Block A)
  └── build_confidence()       → score de confiance

POST /api/amc/tva
  ├── calcule Block E (TVA) avec prix Yahoo Finance
  ├── recalcule MSS avec TVA embarquée
  └── result["manager_skill_score"] = { ...avec TVA..., "mss_no_tva": {...} }

POST /api/amc/manager-skill
  ├── compute_manager_skill_score(study_result, tva_result)  → avec TVA
  ├── compute_manager_skill_score(study_result, None)        → sans TVA
  └── retourne { ...mss_principal..., "mss_no_tva": { ... } }

POST /api/amc/study/export-pdf
  ├── company_name: "TP Advisory Services"
  ├── client_name:  "UTI"
  └── generate_study_pdf() → bytes PDF ReportLab
```

---

## 3. Modèles de facteurs disponibles

| Modèle | Facteurs |
|--------|----------|
| FF3 | Mkt-RF, SMB, HML |
| FF5 | Mkt-RF, SMB, HML, RMW, CMA |
| FF5+MOM | Mkt-RF, SMB, HML, RMW, CMA, MOM |

Source des facteurs : bibliothèque de **Kenneth R. French** (Tuck School of Business, Dartmouth), téléchargée via `pandas_datareader`.

---

## 4. BLOC A — Analyse Factorielle Fama-French

### 4.1 Régression OLS

**Modèle :**  
`excess_ret(AMC)_t = α + β₁·Mkt-RF_t + β₂·SMB_t + β₃·HML_t + [β₄·RMW_t + β₅·CMA_t] + [β₆·MOM_t] + ε_t`

- `excess_ret = rendement_AMC_quotidien − Rf` (taux sans risque)
- Données alignées sur la période commune NAV ↔ facteurs FF
- Minimum 20 observations requises (warning si < 20, erreur si < 10)
- Librairie : `statsmodels.OLS`

**Outputs régression :**
| Champ | Description |
|-------|-------------|
| `alpha_daily` | Alpha quotidien (intercept OLS) |
| `alpha_ann_pct` | `alpha_daily × 252 × 100` — annualisé en % |
| `alpha_tstat` | t-statistique de l'alpha |
| `alpha_pvalue` | p-value bilatérale via `scipy.stats.t.sf` |
| `alpha_ci_low/high` | IC 95% de l'alpha annualisé (%) |
| `r2` | R² de la régression |
| `adj_r2` | R² ajusté |
| `n_obs` | Nombre d'observations |
| `dw` | Durbin-Watson (autocorrélation des résidus) |
| `factors[]` | `{name, beta, ci_low, ci_high, tstat, pvalue}` par facteur |

### 4.2 Régression glissante (rolling)

- Fenêtre : `rolling_window` jours (défaut 126 = 6 mois)
- Minimum de fenêtre : `max(rolling_window, n_factors + 5)`
- Pas : 1 jour
- Output : série temporelle de `{date, r2, alpha_ann_pct, beta_facteur_1, ...}`

### 4.3 Score Alpha dans le Manager Skill Score

**Formule :**
```python
base = clamp(50 + 50 × tanh(alpha_ann_pct / 8))
mult = 1.00  si |t| ≥ 2.0   (significatif à 95%)
     = 0.90  si |t| ≥ 1.5
     = 0.80  si |t| ≥ 1.0
     = 0.70  si |t| < 1.0   (non significatif)
score_alpha = clamp(base × mult)
```

**Calibration du diviseur 8 :**
- alpha = 0%/an → score = 50
- alpha = +8%/an → score = 88
- alpha = −8%/an → score = 12
- alpha ≥ +20%/an → score → 100

**Poids dans le MSS : 30%** (dimension la plus pondérée)

### 4.4 Score de Dépendance Factorielle (0-100)

Mesure à quel point le gérant est "actif" vs passif. Score élevé = très idiosyncratique.

| Composante | Formule | Max |
|------------|---------|-----|
| A — Idiosyncratique | `(1 − R²) × 40` | 40 pts |
| B — Turnover | `min(turnover/2, 1) × 30` | 30 pts |
| C — Concentration | `min(HHI/0.15, 1) × 20` | 20 pts |
| D — Signif. alpha | `min(|t-stat|/3, 1) × 10` | 10 pts |

**Total = A + B + C + D (0-100)**

| Niveau | Seuil | Interprétation |
|--------|-------|----------------|
| High | ≥ 70 | Très dépendant du gérant — performance essentiellement idiosyncratique |
| Medium | 45–70 | Modérément dépendant — mélange gestion active + exposition factorielle |
| Low | < 45 | Faiblement dépendant — performance principalement factorielle |

### 4.5 Bloc F — Réplicabilité (dérivé de Block A)

Utilise les bêtas OLS pour construire un portefeuille répliquant à partir des facteurs FF. Compare NAV réelle vs NAV répliquée pour évaluer si la performance est "factorielle" ou vraiment alpha.

---

## 5. BLOC E — Trading Value Added (TVA)

### 5.1 Définition

Compare le rendement annualisé du fonds réel au rendement annualisé d'un investisseur ayant tenu le **portefeuille initial** (composition au lancement) sans aucun trade.

```
TVA_ann = ann_ret(NAV_réelle) − ann_ret(Buy_Hold_portefeuille_initial)
```

**Important :** le B&H utilise la composition au **départ** (pas la composition actuelle), ce qui évite le biais de regard vers le futur (look-ahead bias sur les poids courants).

### 5.2 Métriques calculées

```python
tva_metrics = {
    "total_pct":   real_total_pct   - bh_total_pct,    # cumulatif
    "ann_ret_pct": real_ann_ret_pct - bh_ann_ret_pct,  # annualisé (utilisé pour le score)
    "sharpe_diff": real_sharpe      - bh_sharpe,
    "max_dd_diff": real_max_dd      - bh_max_dd,
}
```

### 5.3 Score TVA dans le MSS

**Formule :**
```python
score_tva = clamp(50 + 50 × tanh(TVA_ann / 20))
```

**Calibration du diviseur 20** (choisi car la plage naturelle de TVA est ±20%/an, beaucoup plus large que l'alpha FF ±5%/an) :
- TVA = 0%/an → score = 50
- TVA = +10%/an → score = 73
- TVA = +20%/an → score = 84
- TVA = −10%/an → score = 27
- TVA = −20%/an → score = 16
- TVA = −30%/an → score ≈ 10

**Poids dans le MSS : 20%**

**Note :** la valeur brute `tva_ann_pct` est exposée dans la dimension TVA du MSS pour diagnostic.

---

## 6. BLOC H — Timing Score

### 6.1 Principe

Pour chaque ordre exécuté, positionne le prix d'exécution dans le range [min, max] observé sur une fenêtre ±30 jours autour de la date du trade.

```
Entry Score = (max_window − prix_achat)  / (max_window − min_window)
Exit  Score = (prix_vente − min_window)  / (max_window − min_window)
```

- Score = 1 → timing parfait (achat au plus bas, vente au plus haut)
- Score = 0 → pire timing possible
- Score = 0.5 → baseline aléatoire

Nécessite les prix en cache (peuplés par le module TVA/amc_prices.py via Yahoo Finance).

### 6.2 Score Timing dans le MSS

```python
# global_score_mean = moyenne des scores individuels (entrées + sorties)
score_timing = clamp(50 + 200 × (global_score_mean − 0.5))
```

- global_score = 0.5 → score = 50 (neutre)
- global_score = 0.75 → score = 100
- global_score = 0.25 → score = 0

Test statistique : one-sample t-test vs µ₀ = 0.5

**Poids dans le MSS : 7%**

---

## 7. BLOC I — Stock Picking Score

### 7.1 Principe

Mesure l'alpha généré par chaque position (achat → vente ou prix actuel) sur plusieurs horizons (1M, 3M, 6M, 12M) par rapport au benchmark.

### 7.2 Score composite (0-100)

```python
alpha_score = 50 + 50 × tanh(alpha_mean / 0.10)   # alpha moyen
sr_score    = clamp((success_rate - 0.30) / 0.40 × 100)  # % positions gagnantes
ir_score    = clamp((info_ratio + 0.5) / 2.0 × 100)      # information ratio

score_I = round(0.40×alpha_score + 0.35×sr_score + 0.25×ir_score)
```

| Seuil score | Label |
|-------------|-------|
| ≥ 75 | Excellent |
| ≥ 60 | Bon |
| ≥ 45 | Neutre |
| ≥ 30 | Faible |
| < 30 | Très faible |

**Poids dans le MSS : 25%**

---

## 8. BLOC J — Risk Management Score

5 sous-scores agrégés en un score global (0-100).

### 8.1 Sous-score Drawdown (35% du total J)

```python
max_dd_score = clamp(100 − |max_dd_pct| × 1.6)
ulcer_score  = clamp(100 − ulcer_pct × 3.0)
ep_score     = 0.6×clamp(100 − avg_duration × 0.8) + 0.4×clamp(100 − n_episodes × 8)
bench_score  = clamp(50 − (max_dd_pct − bench_max_dd_pct) × 2.5)  # vs benchmark

score_dd = round(0.35×max_dd_score + 0.30×ulcer_score + 0.20×ep_score + 0.15×bench_score)
```

### 8.2 Sous-score Downside Risk (25%)

```python
sortino_score = clamp(40 + 50 × tanh(sortino / 1.5))
sd_score      = clamp(100 − semi_deviation_ann × 2.5)
es_score      = clamp(100 − |ES_95| × 11)

score_dr = round(0.35×sd_score + 0.40×sortino_score + 0.25×es_score)
```

### 8.3 Sous-score Performance Ajustée (25%)

```python
sharpe_score  = clamp(40 + 50 × tanh(sharpe / 1.5))
calmar_score  = clamp(40 + 50 × tanh(calmar / 2.0))
capture_score = clamp(40 + 50 × tanh((up_capture/down_capture − 1) × 2))
ir_score      = clamp(40 + 50 × tanh(info_ratio / 0.8))

score_ra = round(0.35×sharpe + 0.25×calmar + 0.25×capture + 0.15×ir)
```

### 8.4 Sous-score Concentration (10%)

```python
mw_score = clamp(100 − max_weight_pct × 1.1)
en_score = clamp(100 × (1 − exp(−effective_N / 8)))   # effective_N = 1/HHI
t5_score = clamp(100 − top5_weight_pct × 0.9)

score_conc = round(0.40×mw + 0.35×en + 0.25×t5)
```

### 8.5 Sous-score Risque Factoriel (10%, nécessite Block A)

```python
# R² scoring : cible 20-70% (gérant actif mais pas pur beta)
r2_score = 45   si r2 < 20%
         = 70   si 20% ≤ r2 ≤ 70%
         = clamp(70 − (r2 − 70) × 2)   si r2 > 70%

# Beta marché scoring : cible 0.5 ≤ beta ≤ 1.2
beta_score = 80  si 0.5 ≤ beta ≤ 1.2
           = clamp(80 − (beta − 1.2) × 60)  si beta > 1.2
           = 30  si beta < 0
           = clamp(40 + beta × 80)  sinon

# Alpha t-stat scoring
alpha_score = clamp(70 + |t| × 5)  si t > 2
            = clamp(55 + t × 7)    si 0 < t ≤ 2
            = clamp(40 + t × 5)    si -2 ≤ t ≤ 0
            = clamp(30 + t × 3)    si t < -2

score_FR = round(0.30×r2 + 0.40×beta + 0.30×alpha)
```

### 8.6 Plafond de fiabilité (reliability cap)

```python
cap = 50   si n_obs < 30
    = 70   si n_obs < 60
    = 85   si n_obs < 120
    = 100  sinon

score_J = min(score_J_brut, cap)
```

**Poids dans le MSS : 15%**

---

## 9. BLOC D — Conviction vs Incertitude

### 9.1 Matrice 2×2

Chaque position clôturée est classée selon deux axes :

| Axe | Définition |
|-----|-----------|
| Conviction | poids > `conviction_weight_pct`% ET durée > `long_term_holding_days` jours |
| Résultat | P&L > 0 (gagnant) ou < 0 (perdant) |

**4 quadrants :**
- `conviction_winners` : conviction élevée + résultat positif (meilleur)
- `tactical_winners` : faible conviction + résultat positif (chance ?)
- `stubborn_losers` : conviction élevée + résultat négatif (entêtement)
- `uncertainty` : faible conviction + résultat négatif (pire)

### 9.2 Score Conviction dans le MSS

```python
quality = (conviction_winners + tactical_winners − stubborn_losers − uncertainty) / total
score_conviction = clamp(50 + quality × 50)
```

**Poids dans le MSS : 3%**

---

## 10. Manager Skill Score (MSS)

### 10.1 Poids de base

| Dimension | Clé | Poids base |
|-----------|-----|-----------|
| Alpha Fama-French (A) | `alpha` | **30%** |
| Stock Picking (I) | `stock_picking` | **25%** |
| Trading Value Added (E) | `tva` | **20%** |
| Risk Management (J) | `risk_mgmt` | **15%** |
| Timing (H) | `timing` | **7%** |
| Conviction (D) | `conviction` | **3%** |

### 10.2 Renormalisation

Si une dimension n'est pas disponible (bloc non calculé ou erreur), son poids est redistribué proportionnellement aux dimensions disponibles.

```python
total_w = sum(BASE_WEIGHTS[k] for k in available_keys)
norm_weights[k] = BASE_WEIGHTS[k] / total_w  pour k disponible
```

### 10.3 Score composite

```python
composite = sum(norm_weights[k] × raw_scores[k] for k in available_keys)
score = round(clamp(composite))   # entier 0-100
```

### 10.4 Labels

| Score | Label | Couleur |
|-------|-------|---------|
| ≥ 80 | Gérant exceptionnel | #10b981 (vert) |
| ≥ 60 | Bon gérant | #22c55e (vert clair) |
| ≥ 40 | Neutre | #f59e0b (ambre) |
| ≥ 20 | Faible valeur ajoutée | #f97316 (orange) |
| < 20 | Destructeur de valeur | #ef4444 (rouge) |

### 10.5 Deux scores systématiquement exposés

Depuis 2026-06-26, l'API retourne **toujours** les deux scores :

```json
{
  "score": 42,                    ← avec TVA
  "mss_no_tva": { "score": 55 }  ← sans TVA
}
```

- `POST /api/amc/manager-skill` → les deux
- `POST /api/amc/tva` → les deux embarqués dans `result["manager_skill_score"]`

---

## 11. PDF Export — Structure du document

| Page | Contenu |
|------|---------|
| 1 | **Cover** : logo société, titre, info box produit (ISIN, devise, performance), client UTI, confidentiel |
| 2 | **Executive Summary** : deux badges score (avec/sans TVA), radar chart, tableau critères avec barres de progression, jauge 5 zones, interprétation |
| 3 | **Fiche technique** : tableau 18 lignes (produit, NAV, AUM, ordres, benchmark, etc.) |
| 4+ | **Blocs A → J** : un bloc par section avec KPI cards, graphiques, tableaux, interprétation justifiée |
| Avant-dernière | **Score de confiance** : tableau dimensions, badge 80%, interprétation |
| Dernière | **Avertissements & Méthodologie** : disclaimer complet, propriété intellectuelle |

**Texte justifié (TA_JUSTIFY) sur :** synthèse, interprétations de blocs, disclaimer.

**Footer :** TP Advisory Services (gauche) · CONFIDENTIEL — UTI (rouge, centre) · Page N (droite)

---

## 12. Chantiers en cours / Points de vigilance

### Actifs
| Sujet | Fichier | État |
|-------|---------|------|
| TVA dans MSS | `amc_managerskill.py` | Score affiché mais TVA souvent très négative pour cet AMC — à surveiller si le B&H initial est correctement implémenté |
| KPI cards égales | `amc_pdf.py → _kpi_row()` | Fix appliqué (outer padding = 0) — à vérifier sur prochain PDF |
| Cover "UTI" | `amc_pdf.py → _draw_study_cover()` | Nécessite restart backend après ajout `client_name` dans `StudyExportRequest` |
| Deux scores MSS UI | `AmcView.vue` | Implémenté — badge "avec TVA" + badge "sans TVA" côte à côte |

### Modules futurs documentés (MDs)
| Module | Fichier MD | Priorité |
|--------|-----------|----------|
| Skill vs Luck Engine | `SKILL_VS_LUCK_ENGINE.md` | Haute (après stabilisation A-J) |
| Decision Analysis Engine | `DECISION_ANALYSIS_ENGINE.md` | Haute |
| Manager DNA Engine | `MANAGER_DNA_ENGINE.md` | Haute |

### Points techniques à ne pas oublier
- Le **Block G (Brinson-Fachler)** est calculé côté frontend via un endpoint séparé (nécessite prix par position)
- Les **prix des sous-jacents** sont mis en cache dans un store Parquet (peuplé lors du calcul TVA) — Blocks H et I en dépendent
- Le **rolling_window** par défaut = 126 jours (6 mois)
- La **série FF** est paramétrée dans le manifest (`ff_series` : ex. "Europe", "Global")
- Le **benchmark** Yahoo ticker est dans le manifest (`benchmark_ticker`)
- La **reconstruction FIFO** gère : BUY, SELL, SELL_ALL, round-trips partiels, ordres Discarded (comtabilisés séparément)

---

## 13. BLOC B — Attribution réalisée par sous-jacent

### 13.1 P&L par position

Pour chaque ISIN, le Bloc B accumule :

| Champ | Description |
|-------|-------------|
| `realized_pnl` | P&L réalisé total (tous round-trips clôturés) |
| `price_pnl` | Part prix du réalisé |
| `fx_pnl` | Part change du réalisé |
| `unreal_pnl` | P&L latent des positions ouvertes (mark courant × quantité résiduelle) |
| `total_pnl` | `realized_pnl + unreal_pnl` |
| `n_round_trips` | Nombre de round-trips complets pour ce titre |

Toutes les valeurs sont **dans la devise du produit (NAV)**.

### 13.2 Décomposition Prix / Change (P&L réalisé uniquement)

Pour chaque round-trip, la décomposition est issue du livre d'ordres FIFO :

```
pnl_prix = q × F_s × (P_s − P_e)
pnl_fx   = q × P_e × (F_s − F_e)
```

où :
- `q` = quantité exécutée
- `P_e` = prix local d'entrée, `P_s` = prix local de sortie
- `F_e` = FX à l'entrée, `F_s` = FX à la sortie (devise_produit / devise_locale)

**Part FX** (niveau global) :
```python
fx_share_pct = abs(tot_fx) / (abs(tot_price) + abs(tot_fx)) × 100
```

> **Limite :** le P&L latent des positions ouvertes n'est **pas** décomposé prix/FX (un seul mark courant, pas de série de prix continue).

### 13.3 Sorties temporelles

P&L réalisé agrégé par **trimestre de sortie** (`exit_quarter = "2024-Q3"`, etc.) — permet de voir si la performance est concentrée sur une période.

### 13.4 Outputs clés

| Champ | Description |
|-------|-------------|
| `per_name[]` | Toutes les lignes ISIN, triées par `total_pnl` desc |
| `top5` / `flop5` | 5 meilleures / 5 pires contributions |
| `quarterly_realized[]` | P&L réalisé par trimestre |
| `totals` | Sommes globales (realized, unreal, price, fx, fx_share_pct) |

---

## 14. BLOC C — Trading Quality / Turnover

### 14.1 Round-trips

| Métrique | Formule |
|----------|---------|
| `count` | Nombre total de round-trips clôturés |
| `win_rate_pct` | `n_gagnants / total × 100` |
| `profit_factor` | `sum(wins) / abs(sum(losses))` |
| `avg_win` / `avg_loss` | Moyenne P&L gagnants / perdants |
| `avg_holding_days` | Durée moyenne de détention (en jours) |
| `median_holding_days` | Durée médiane |
| `realized_pnl` | Somme des P&L réalisés |

### 14.2 Turnover

```python
gross_traded  = Σ notional_prod des ordres Done
avg_aum       = moyenne NAV × encours (from navs / composition)
turnover_rate = gross_traded / avg_aum
turnover_ann  = turnover_rate × 365 / period_days
```

- `period_days` = delta entre premier et dernier ordre exécuté

### 14.3 Timing à l'exécution (par ISIN)

Calcul du **prix moyen d'achat** vs **prix moyen de vente** par ISIN (en devise locale) :

```python
avg_buy  = Σ(qty × price_local) / Σ qty  [ordres Buy]
avg_sell = Σ(qty × price_local) / Σ qty  [ordres Sell]
sell_vs_buy_pct = (avg_sell / avg_buy − 1) × 100
```

Lignes triées par `sell_vs_buy_pct` croissant (les pires spread en tête).

> **Limite :** seuls les points d'exécution sont connus — pas de détection du timing intra-window (achat au plus bas sur ±30 jours = Block H).

### 14.4 Trading vs Portage

Décomposition proxy seulement (P&L clôturé vs P&L latent). La vraie décomposition "trading vs B&H continu" nécessite les prix quotidiens par constituant.

---

## 15. BLOC F — Réplicabilité

### 15.1 Principe

Reconstruit un **portefeuille réplicant passif** à partir des bêtas Fama-French (Block A) :

```
R_rep(t) = RF(t) + Σ β_i × F_i(t)
```

Compare la NAV simulée du réplicant à la NAV réelle de l'AMC sur toute la période.

**Aucune donnée externe supplémentaire** : tout vient du résultat Block A.

### 15.2 Score de réplicabilité (0-100)

3 composantes pondérées :

| Composante | Formule | Poids |
|------------|---------|-------|
| C1 — R² | `r2 × 100` | **40%** |
| C2 — Couverture de performance | `min(rep_total / amc_total, 1) × 100` (avec cas spéciaux si négatifs) | **35%** |
| C3 — Alpha non significatif | `(1 − min(\|t-stat\| / 3, 1)) × 100` | **25%** |

```python
score_F = round(0.40 × C1 + 0.35 × C2 + 0.25 × C3)  # clampé 0-100
```

**IC 95% du score** basé sur l'erreur d'échantillonnage du R² :
```
se(R²) ≈ 2 × √R² × (1 − R²) / √n   (méthode delta)
```

### 15.3 Profils

| Score | Profil |
|-------|--------|
| ≥ 80 | Quasi-systématique |
| ≥ 60 | Principalement systématique |
| ≥ 40 | Mixte |
| ≥ 20 | Principalement discrétionnaire |
| < 20 | Pur discrétionnaire |

**Interprétation :** plus le score est élevé, plus la stratégie peut être répliquée par des ETFs factoriels. Un score < 40 indique que le gérant s'écarte significativement des primes factorielles documentées.

### 15.4 Décomposition factorielle

Contribution cumulative de chaque facteur au portefeuille réplicant (approximation additive valide < 2 ans) :
```python
contrib_i = (∏(1 + β_i × F_i(t)) − 1) × 100    pour chaque jour t
```

### 15.5 Confiance Block F

| n_obs | Confiance |
|-------|-----------|
| ≥ 120 | **80%** |
| ≥ 60 | **65%** |
| < 60 | **50%** |

---

## 16. BLOC G — Attribution Brinson-Fachler

### 16.1 Formules

Attribution par secteur GICS (Brinson-Fachler 1985, single-période) :

```
allocation(s)  = (w_p − w_b) × (r_b − R_b)
selection(s)   = w_b          × (r_p − r_b)
interaction(s) = (w_p − w_b)  × (r_p − r_b)
total(s)       = allocation + selection + interaction
```

où :
- `w_p` = poids portefeuille dans le secteur s
- `w_b` = poids benchmark dans le secteur s
- `r_p` = rendement moyen des titres AMC dans le secteur s
- `r_b` = rendement de l'ETF SPDR sectoriel (XLK, XLF, XLV...)
- `R_b` = rendement total benchmark (correction Fachler)

### 16.2 Sources de données

| Élément | Source |
|---------|--------|
| Poids portefeuille | Ordres BUY des 60 premiers jours (inception weights, même méthode que TVA) |
| Poids benchmark | `yfinance.Ticker(bench).info["sectorWeightings"]` → fallback MSCI World statique 2024 |
| Rendements sectoriels | ETFs SPDR : XLK/XLF/XLV/XLE/XLI/XLY/XLP/XLC/XLB/XLRE/XLU (biais US/USD) |
| Secteurs par titre | `yfinance.Ticker(ticker).info["sector"]` → normalisé GICS |

### 16.3 Cache

- Fichier : `{study_folder}/brinson_prices.json`
- Contient : `price_keys`, `amc_currency`, `benchmark_ticker`, `sector_map`, `saved_at`
- Rechargé automatiquement pour éviter les re-fetches Yahoo Finance

### 16.4 Calcul depuis le frontend

Block G est calculé **côté frontend** via `POST /api/amc/prices/brinson` — il nécessite les prix par position (store Parquet peuplé par le calcul TVA). Pas intégré dans `run_study()`.

### 16.5 Confiance Block G

| Condition | Confiance |
|-----------|-----------|
| Poids inception + poids bench via yfinance | **80%** |
| Poids inception + poids bench statiques | **75%** |
| Poids actuels (fallback) + yfinance | **65%** |
| Poids actuels + statiques | **60%** |

---

## 17. Score de Confiance global

### 17.1 Niveaux de confiance par bloc

| Bloc | Condition | Confiance |
|------|-----------|-----------|
| A — Factoriel | n_obs ≥ 250 | 85% |
| | 120 ≤ n < 250 | 80% |
| | 60 ≤ n < 120 | 70% |
| | n < 60 | 55% |
| B — Attribution réalisée | Disponible | **90%** |
| B — Attribution pondérée | Nécessite prix continus | — (non faisable) |
| C — Round-trips / turnover | Disponible | **85%** |
| C — Timing fin | Disponible avec prix | **65%** |
| D — Conviction | Disponible | **85%** |
| E — TVA | real_nav + 0 missing | 85% |
| | real_nav + missing > 0 | 70% |
| | pas de real_nav | 55% |
| E — Attribution TVA | Disponible | **80%** |
| F — Réplicabilité | n_obs ≥ 120 | 80% |
| | 60 ≤ n < 120 | 65% |
| | n < 60 | 50% |
| H — Timing Score | couverture ≥ 50% | 80% |
| | couverture ≥ 20% | 65% |
| | couverture < 20% | 50% |
| I — Stock Picking | couverture ≥ 60% | 80% |
| | couverture ≥ 30% | 65% |
| | couverture < 30% | 50% |
| J — Risk Management | `reliability_cap / 100 × 0.85` | variable |
| G — Brinson | voir §16.5 | 60-80% |

### 17.2 Score global

```python
overall_pct = mean([r["confidence_pct"] for r in rows if r["feasible"] and r["confidence_pct"] > 0])
```

Moyenne simple (non pondérée) des dimensions **faisables** (disponibles et non nulles).

### 17.3 Interprétation

- **Blocs B et D** les plus robustes : données exactes du carnet d'ordres
- **Bloc A** très fiable si données FF disponibles + historique > 1 an
- **Blocs H, I, G** dépendent des prix par sous-jacent (store Parquet)
- Pour dépasser 90% de confiance : ajouter les prix marché par ISIN + facteurs locaux multi-devises

---

## 19. Commandes utiles

```bash
# Démarrer le backend
cd backend && python run.py

# Démarrer le frontend
cd frontend && npm run dev

# Lancer les tests
cd backend && pytest tests/ -v

# Vérifier syntaxe PDF sans ReportLab
python -c "import ast; ast.parse(open('backend/app/core/amc_pdf.py').read()); print('OK')"
```

---

*Document créé le 2026-06-26 — à mettre à jour à chaque session de travail*
