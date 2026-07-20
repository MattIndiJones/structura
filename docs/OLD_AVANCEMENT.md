> ⚠️ **ARCHIVÉ (2026-07-16)** — snapshot d'état à une date donnée, non maintenu depuis. Plusieurs
> bugs listés ci-dessous comme "corrigés" ont été réexaminés, et de nombreux autres bugs trouvés et
> corrigés depuis n'y figurent pas. Le Bloc K n'existe pas encore dans ce document. Pour l'état
> courant : `docs/FIFO_MODULE.md`, `docs/PORTFOLIO_RECONCILIATION_LESSONS.md`, et la mémoire de
> session. Conservé pour l'historique, ne pas s'y fier pour des formules ou des chiffres actuels.

# Structura — Avancement du projet
**Dernière mise à jour : 27 juin 2026**

---

## 1. Vue d'ensemble

**Structura** est une plateforme d'analyse AMC (Actively Managed Certificate) produisant des rapports PDF institutionnels pour des clients tiers.

| Élément | Valeur |
|---------|--------|
| Stack backend | FastAPI + Python 3.x |
| Stack frontend | Vue 3 |
| Client actuel | UTI (société suisse) |
| Premier produit | CH1473733959 — LUKB NEÜ Infrastructures Basket (USD) |
| Société émettrice du rapport | TP Advisory Services |
| Environnement Python | `.venv\Scripts\python.exe` (numpy 1.26.4, statsmodels 0.14.6) |
| Run commande | `$env:PYTHONPATH = "...\backend"; python -X utf8 script.py` |

---

## 2. Architecture des blocs d'analyse

| Bloc | Nom | Statut | Poids MSS |
|------|-----|--------|-----------|
| A | Fama-French 5F+MOM OLS | ✅ Opérationnel | 30% |
| B | Attribution FIFO par sous-jacent | ✅ Opérationnel | — |
| C | Métriques de trading (round trips, turnover) | ✅ Opérationnel | — |
| D | Conviction matrix (winners/losers) | ✅ Opérationnel | 3% |
| E | VAG — Valeur Ajoutée de Gestion | ✅ Opérationnel | 20% |
| F | Réplicabilité (factor ETF portfolio) | ✅ Opérationnel | — |
| H | Timing score (entrées/sorties) | ✅ Opérationnel | 7% |
| I | Stock Picking Score (alpha vs IGF) | ✅ Opérationnel | 25% |
| J | Risk Management Score | ✅ Opérationnel | 15% |
| MSS | Manager Skill Score composite | ✅ Opérationnel | 100% |

**Poids MSS base** : Alpha 30% · Stock Picking 25% · VAG 20% · Risk 15% · Timing 7% · Conviction 3%
**Double score** : avec VAG et sans VAG (renormalisé), les deux affichés dans le rapport.

---

## 3. Résultats CH1473733959 (état au 27/06/2026)

### Données
- NAV : 175 observations (2025-10-14 → 2026-06-27)
- FF data : jusqu'au 30/04/2026 (lag structurel ~2 mois — 33 NAV points exclus de la régression)
- Overlap régression : 142 observations (2025-10-14 → 2026-04-30)
- Ordres : 2 fichiers JSON (data0 + data1), FIFO vérifié

### Résultats bloc par bloc

| Bloc | Résultat clé | Score MSS |
|------|-------------|-----------|
| **A** | Alpha=−4.43% (p=0.88 non-sig), R²=74.2%, Mkt-RF+0.96***, RMW−1.61***, MOM+1.23*** | **32/100** |
| **B** | Réalisé=+89k USD, latent=+381k, total=+471k. Glencore=125% du P&L total | — |
| **C** | 71 round trips, hold moyen=80.6j, win rate=56.3%, profit factor=3.27, 6.5x/an | — |
| **D** | 7 conviction winners, 3 stubborn losers, 8 tactiques, 23 incertitude | **37/100** |
| **E (VAG)** | AMC=+33% vs B&H initial=+112.7% → VAG=−79.7% (ann: −153.9%) | **~0/100** |
| **F** | 88/100 quasi-systématique, R²=74.2% (facteurs FF expliquent presque tout) | — |
| **H** | Score=0.492 (aléatoire, p=0.74) | **48/100** |
| **I** | Alpha=+24.4% moyen (74 achats), t=6.67, p=1.3e-10*** | **80/100** |
| **J** | Sharpe=1.21, Sortino=1.65, Calmar=2.28, MaxDD=−21.7%, eff_N=3.11 | **63/100** |

### MSS final
| Score | Label |
|-------|-------|
| **44/100 avec VAG** | Neutre |
| **55/100 sans VAG** | Neutre |

### Lecture analytique
Ce fonds se comporte comme un **fonds momentum sur actifs non-profitables** (RMW−1.61***, MOM+1.23***) — pas un fonds infrastructure malgré le nom. Glencore à 88% du portfolio actuel génère 125% du P&L total. Concentration extrême : eff_N=3.11.

Le **stock picking est excellent** (Bloc I, t=6.67***) mais le gérant a roté hors des positions AI/tech initiales (D-Wave Quantum, Bloom Energy, Credo) qui ont monté de +112% en passif → VAG très négatif.

---

## 4. Conventions techniques validées

### FX
- `usedFxRate` dans le JSON LUKB = devise locale → USD
- EUR×1.167, GBP×1.343, JPY×0.006274, CHF×1.297
- Cross-checkés vs yfinance, diff <1% ✅

### FIFO / Ordres
- `orderedQuantity` / `executedQuantity` signés : **négatif=SELL, positif=BUY**
- Formule P&L : `qty × (P1×F1 − P0×F0)` = price_pnl + fx_pnl ✅
- 45 ISINs en "excess sell" = positions pré-inception (P&L sous-estimé, limitation structurelle)

### VAG — Méthodologie
- Baseline B&H : BUY orders des **60 premiers jours** (pas snapshot actuel — évite le survivorship bias)
- Dual score avec/sans VAG car la méthodologie est discutable mais pertinente
- Disclaimer explicite dans le PDF

### Données FF
- Série : `Developed_5F_MOM` (Ken French's library)
- Lag structurel ~2 mois → données FF finissent 30/04/2026
- 33 points NAV (mai-juin 2026) exclus de la régression (+10.35% non capturé dans l'alpha)
- **Ce n'est pas un bug — c'est une limitation connue et documentée**

---

## 5. Bugs corrigés

| # | Fichier | Bug | Fix |
|---|---------|-----|-----|
| 1 | `amc_engine.py` | p-values ultra-faibles arrondies à 0.0 par `round(p, 4)` → `0.0 or 1 = 1.0` → pas d'étoiles dans le PDF | `_fmt_pval()` : garde le float brut si p < 0.0001 |
| 2 | `amc_engine.py` | Section benchmark retournait seulement la string "IGF" sans OLS | Ajout section 5b : OLS complet AMC vs IGF (alpha Jensen, beta, R²) |
| 3 | `amc_pdf.py` | `p_val = f.get("pvalue") or 1` → une p-value de 0.0 renvoyait 1.0 | `_pval_safe()` : None→1.0, garde 0.0 comme tel |
| 4 | `amc_pdf.py` | `f"{p_val:.4f}"` affichait "0.0000" pour t=4.87 | `_pfmt()` : affiche "<0.0001" si p < 0.0001 |
| 5 | `amc_managerskill.py` | `_alpha_score()` : mult appliqué sur `base` au lieu de `base−50` → alpha=0% insig → 35/100 au lieu de 50/100 | `50 + (base−50) × mult` (pull vers 50, pas vers 0) |
| 6 | `amc_stockpicking.py` | `round(p, 4)` pour le pvalue_alpha de Block I | `p if p < 0.0001 else round(p, 4)` |
| 7 | `amc_blocks.py` | Position cash USD (isin=None) incluse dans la conviction matrix comme "stubborn loser" | `if isin is None: continue` au début de la boucle |
| 8 | `amc_pdf.py` | KPI row Block B : "USD +381.4k" à 20pt wrappait → tuiles inégales | Enlève le préfixe `ccy` des valeurs, le met dans le label |

---

## 6. Architecture PDF

### Fonction principale
`generate_study_pdf(study_result, synthese_text, vag_result, company_name, client_name)`

### Structure du rapport (pages approximatives)
1. Couverture (canvas callback)
2. Executive Summary — Score Global (avec/sans VAG + radar)
3. Fiche produit (ISIN, NAV, frais, benchmark, etc.)
4. Bloc A — Analyse Factorielle FF (chart perf, KPIs, régression OLS, betas, benchmark OLS, rolling)
5. Bloc B — Attribution P&L par sous-jacent
6. Bloc C — Trading & Turnover
7. Bloc D — Conviction Matrix
8. Bloc E — VAG (B&H vs AMC)
9. Bloc F — Réplicabilité
10. Bloc H — Timing Score
11. Bloc I — Stock Picking Score
12. Bloc J — Risk Management
13. MSS — Manager Skill Score détaillé
14. Catalogue des blocs (méthodologie)
15. Confiance & Limites
16. Disclaimer (incl. avertissement VAG)
17. Annexe — Table complète timing

### Génération
```python
from app.core.amc_study import run_study
from app.core.amc_pdf import generate_study_pdf
from app.core.amc_vag import compute_vag
from app.core.amc_prices import load_prices

# 1. Run study
result = run_study(manifest, folder)

# 2. Load prices et compute VAG
prices = {p.stem: pd.read_parquet(p) for p in PRICE_STORE.glob("*.parquet")}
vag = compute_vag(result, prices, amc_currency='USD', folder=folder)

# 3. Generate PDF
pdf = generate_study_pdf(result, vag_result=vag,
                         company_name="TP Advisory Services", client_name="UTI")
```

---

## 7. Points en suspens / prochaines étapes

| Priorité | Item | Notes |
|----------|------|-------|
| 🔴 | Vérifier le PDF final (VAG + tuiles corrigées) | Demander retour client UTI |
| 🟡 | Block F — portfolio de réplication vide | `replication_portfolio=[]` dans le résultat ; le score est calculé sur les facteurs FF, pas sur des ETFs réels |
| 🟡 | Truncation FF documentée dans le PDF | Ajouter une note dans le rapport expliquant les 33 points NAV manquants |
| 🟡 | Multi-AMC | L'utilisateur a mentionné qu'il y aura d'autres AMCs. Pas de feature demandée pour l'instant |
| 🟢 | VAG négatif très marqué à expliquer au client | −79.7% total dû à la rotation hors positions AI/tech initiales |
| 🟢 | Noms ISIN non résolus dans Bloc D | Plusieurs positions n'affichent que l'ISIN (lookup name échoué) |

---

## 8. Commandes de référence

```powershell
# Environnement
$env:PYTHONPATH = "C:\Users\admin\GitHub\structura\backend"
$py = "C:\Users\admin\GitHub\structura\.venv\Scripts\python.exe"

# Lancer une étude complète + PDF
& $py -X utf8 gen_pdf_with_vag.py

# Tests unitaires
& $py -m pytest backend/tests/ -v
```

```
Dossier données UTI : C:\Users\phili\Downloads\UTI\Data\CH1473733959
Prix sous-jacents   : C:\Users\admin\GitHub\structura\backend\data\underlying_prices\ (119 fichiers)
Output PDF          : C:\Users\phili\Downloads\UTI\CH1473733959_rapport.pdf
```
