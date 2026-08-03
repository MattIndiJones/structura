# Rapport d'audit quantitatif — STRUCTURA

**Date de l'audit :** 1er août 2026
**Révision examinée :** worktree postérieur à `4167eeb`, 495 tests collectés
**Périmètre :** moteur PayScript, pricing, Monte Carlo, modèles, Greeks, volatilité,
corrélations, lifecycle, dates, fixings, backtests, risque, PRIIPs, MTF, VaR, données de
marché.
**Hors périmètre :** AMC et INDEX_STUDIO.
**Mode opératoire :** audit en lecture seule. Aucun fichier du dépôt n'a été modifié.
Les vérifications reposent sur 25 sondes numériques exécutées hors dépôt, comprenant des
benchmarks analytiques et une ré-implémentation indépendante du Monte Carlo pour les
barrières.

**Relation au rapport précédent.** Ce document succède à
`AUDIT_QUANTITATIF_COMPLET_HORS_AMC_2026-07-31.md`. Il ne le réécrit pas : il vérifie
numériquement lesquels de ses constats tiennent encore, en corrige un qui ne se reproduit
plus, et ajoute ce que les sondes ont trouvé de neuf.

---

## 1. Résumé exécutif

### Verdict

**Le noyau de pricing GBM à monitoring discret est désormais défendable.** C'est le
changement majeur depuis juillet, et il est démontré plutôt que déclaré : sur benchmarks
analytiques à N = 200 000, l'écart maximal est de 0,66 bp de nominal, la martingalité tient
sur les cinq modèles à moins de 1,7 bp, la convergence suit 1/√N, et le monitoring
hebdomadaire des barrières tombe dans l'intervalle de confiance d'une simulation
indépendante à 2 millions de trajectoires.

**Six des douze bloquants de juillet sont fermés**, revérifiés un par un plutôt qu'admis
sur la foi du diff. **Cinq défauts critiques subsistent**, dont trois que les sondes ont
permis de quantifier bien au-delà de ce qui était connu.

Le danger n'a pas changé de nature — il ne s'agit jamais de plantages mais de nombres
plausibles et faux — mais il s'est concentré : de douze bloquants diffus on est passé à
cinq modules identifiés, mesurés et bornés.

### Les cinq blocages restants

1. le monitoring « continu » price une barrière proche **14,3 % trop bas** ;
2. le Mark-to-Future marque un produit **rappelé** à 107 % pendant un an et demi ;
3. le vega Heston est multiplié par **(1 − ρ²)** — divisé par deux au skew usuel ;
4. les taux stochastiques ne refittent pas la courbe : **+164 bp** sur un ZC 5 ans ;
5. les horizons intermédiaires du KID **déclenchent la maturité** du produit.

### Zone utilisable aujourd'hui

Le moteur peut servir de calcul indicatif contrôlé lorsque toutes ces conditions sont
réunies : modèle `constant` ou courbe déterministe ; monitoring de barrière **discret** ;
pas de MTF ; pas de vega sous Heston ; pas de taux stochastiques ; pas de KID
réglementaire ; pas de VaR comme limite officielle ; contrôle indépendant du résultat.

### Notation

| Domaine | Note /10 | Juillet | Appréciation |
|---|---:|---:|---|
| Exactitude des payoffs | 6,0 | 5,5 | Évaluation validée ; pièges DSL et ambiguïtés de templates persistants |
| Qualité du Monte Carlo | 6,5 | 4,5 | Socle démontré ; grille hebdo, pont brownien et convexité HW ouverts |
| Exactitude des Greeks | 6,5 | 3,0 | Stateful et validés vs Black-Scholes ; vega Heston biaisé |
| Gestion des dates | 4,0 | 2,5 | Gouvernance des fixings excellente ; grilles 52/252 et calendriers absents |
| Qualité des données | 3,5 | 2,0 | Séparation indicatif/officiel acquise ; look-ahead et fallbacks intacts |
| Robustesse numérique | 3,5 | 3,5 | Exceptions non rattrapées, validations de modèle absentes |
| Qualité des backtests | 3,0 | 2,5 | Biais de sélection IRR et look-ahead non traités |
| Conformité réglementaire | 2,5 | 1,0 | Honnêteté rétablie (bandeau, MRM) ; méthodologie non conforme |
| Couverture des tests | 6,5 | 5,0 | Harnais golden et benchmarks ; MTF, pont et templates non couverts |
| Maintenabilité quantitative | 4,5 | 4,0 | Objet marché unifiant ; `deals.py` à 6 339 lignes |
| **Note quantitative globale** | **4,8/10** | **3,4/10** | **Pré-trade GBM utilisable sous contrôle ; modules aval non validés** |

---

## 2. Cartographie du moteur quantitatif

```
Frontend (Pricer / RFQ / Booking / Risk)
   │  % → fraction, PARAM en unités stockées
   ▼
Schémas Pydantic (schemas.py)          ← validation partielle : pas d'enum modèle
   ▼
Parseur PayScript (parser.py, 748 l.)  ← résolution CONSTAT, PARAM(), effective_T_max
   ▼
_build_rate_term  ─────────────┐        ← df / r_flat / step_fwd / zero, source unique
   ▼                           │
_build_lv_grid (Dupire) ←──────┤        ← 3ᵉ point d'entrée du taux, désormais câblé
   ▼                           │
run_mc  ←──────────────────────┘
   ├─ 5 simulateurs (GBM / Heston QE / SABR / Local Vol / LSV)
   ├─ _bridge_extrema (monitoring continu)
   ├─ _eval_paths (boucle Python par trajectoire)
   └─ actualisation df_arr
   ▼
Sorties : price, ic95, payoffs, flux_table, fugit
   ├─→ compute_greeks (stateful)   ─→ deal.greeks_json ─→ portfolios._aggregate_risk
   ├─→ run_mc_proba                 ─→ onglet Proba
   ├─→ run_mark_to_future           ─→ scénarios MTF
   ├─→ kid_compute                  ─→ PRIIPs
   ├─→ eval_script_on_history (252) ─→ backtest et replay lifecycle
   └─→ var_scenario / shocks        ─→ VaR, chocs
```

### Tailles des modules

| Module | Lignes |
|---|---:|
| `backend/app/api/deals.py` | 6 339 |
| `backend/app/core/payscript/engine.py` | 2 479 |
| `backend/app/api/rfq.py` | 875 |
| `backend/app/core/payscript/parser.py` | 748 |
| `backend/app/api/portfolios.py` | 644 |
| `backend/app/api/pricing.py` | 504 |
| `frontend/src/data/payscriptTemplates.js` | 447 |
| `backend/app/core/var_engine.py` | 359 |
| `backend/app/api/kid.py` | 293 |

### Unités et conventions

| Donnée | Convention |
|---|---|
| Prix moteur | Fraction du nominal (`0.985` = 98,5 %) |
| Prix RFQ / deal | Points de nominal (`98.5`) |
| Spot simulé | Normalisé à 1 au départ ; `spot_mult` pour un deal vivant |
| Volatilité, taux, dividende | Fraction côté backend |
| Temps MC | Années, grille fixe de **52 pas/an** |
| Temps replay historique | **252 lignes/an** (`SY_H`) |
| CONSTAT absolu | Écart calendaire / 365,25 |
| Seed par défaut | 42 |
| Delta / Gamma / Vega / Rho | Dérivées par unité de la variable bumpée (par 100 %) |
| Theta | Par jour calendaire, hors flux traversé |

### Points de perte ou de transformation d'information

Conversion pourcentage → fraction au frontend · prix moteur 0–1 vers prix RFQ 0–100 ·
arrondi `round(price, 6)` avant les différences finies · quantification `round(d × 52)`
des dates · divergence 52 pas/an contre 252 · perte des métadonnées `monitors` après
`resolve_constats` · état lifecycle non transmis au MTF · fallbacks silencieux sur
dividende, corrélation et FX.

---

## 3. Produits et modèles identifiés

**Seize templates :** Autocall Athena · Phoenix · Worst-of Athena · Autocall Gear Put ·
Gear Put worst-of · call · put · call spread · digital · capital garanti · reverse
convertible · Twin Win · Booster · Shark Note · Shark worst-of · zéro-coupon.

**Cinq modèles de diffusion :** GBM à volatilité constante · Heston (discrétisation QE) ·
SABR (schéma log-Euler/CEV) · volatilité locale « Dupire-like » sur smile polynomial ·
LSV par méthode particulaire. Plus un facteur de taux gaussien optionnel (ABM ou
Ornstein-Uhlenbeck présenté comme Hull-White) et un pont brownien pour le monitoring
continu.

---

## 4. Anomalies critiques confirmées

### QNT-101 — Le pont brownien price les barrières 14 % trop bas

**Catégorie :** simulation
**Statut :** confirmé
**Sévérité :** critique
**Probabilité :** forte
**Fichier :** `backend/app/core/payscript/engine.py`
**Fonction :** `_bridge_extrema`

**Comportement observé.** Down-and-out call, S₀ = K = 1, B = 0,95, σ = 30 %, r = q = 0,
T = 1 an, N = 400 000 :

| Mode | Prix | Référence | Écart |
|---|---:|---|---:|
| `weekly` | 0,060513 | 0,060367 ± 0,00025 (simulation indépendante 52 pas, 2 M trajectoires) | **+1,5 bp — exact** |
| `continuous` | 0,044237 | 0,051611 (Merton, exact) | **−73,7 bp, soit −14,3 %** |

**Comportement attendu.** Le mode continu doit converger vers la valeur de monitoring
continu. Le monitoring hebdomadaire est **validé** : il tombe dans l'intervalle de
confiance de la ré-implémentation indépendante. L'erreur est donc entièrement imputable
au pont, non au moteur de trajectoires.

**Justification.** Le pont tire minimum et maximum via deux uniformes indépendantes sur
le même pas et gèle la volatilité par pas. Il surestime la probabilité de franchissement
et tue trop de trajectoires.

**Scénario de reproduction.** Script `SET OUT = INDIC(S_MIN[1] < B)` puis
`PAY (1-OUT)*MAX(S[1]-K,0)`, `barrier_monitoring="continuous"`, comparé à
`C(S,K) − (B/S)^{2λ}·C(B²/S,K)` avec `λ = (r − q + σ²/2)/σ²`.

**Impact sur le prix.** Toute barrière KI/KO monitorée en continu est sous-valorisée
d'ordre 10 % en valeur relative pour une barrière proche.
**Impact sur les Greeks.** Les sensibilités de barrière héritent du biais.
**Impact utilisateur.** Le label « continu » promet une exactitude que le calcul ne
délivre pas.
**Impact réglementaire.** Documentation produit potentiellement incohérente.

**Correction recommandée.** Soit restreindre l'exactitude annoncée au monitoring discret,
soit refaire le tirage joint des extrema avec la loi conditionnelle correcte.
**Tests à ajouter.** Down-and-out contre Merton à trois niveaux de σ et deux distances de
barrière ; convergence du pont en nombre de sous-pas.
**Risque de régression.** Élevé — le pont est partagé par tous les modèles.

---

### QNT-102 — Le Mark-to-Future marque un produit mort

**Catégorie :** simulation
**Statut :** confirmé
**Sévérité :** critique
**Probabilité :** forte
**Fichier :** `engine.py`
**Fonctions :** `run_mark_to_future`, `_simulate_mtf_outer`

**Comportement observé.** Autocall à barrière 90 %, coupon 8 %, σ = 1 % : le rappel à
t = 0,5 est quasi certain, et le prix principal (1,0639 = df(0,5) × 1,08) le confirme.
MTF sur 5 dates, 2 000 scénarios outer :

| Date | Mark moyen | min | max | p05 | p95 |
|---:|---:|---:|---:|---:|---:|
| 0,396 | 107,689 | 107,689 | 107,689 | 107,689 | 107,689 |
| **0,792** | **107,317** | 107,317 | 107,317 | 107,317 | 107,317 |
| **1,189** | **107,008** | 107,008 | 107,008 | 107,008 | 107,008 |
| **1,585** | **104,816** | 100,256 | 109,598 | 102,655 | 107,022 |
| **1,981** | **106,117** | 100,402 | 111,265 | 103,689 | 108,565 |

**Comportement attendu.** Après t = 0,5 le contrat est éteint : le mark doit valoir zéro,
ou la valeur actuelle du flux déjà versé.

**Deux aggravations.** La distribution est **dégénérée** aux trois premières dates
(min = max sur 2 000 scénarios) : tout percentile lu dessus a une largeur nulle et donne
une fausse impression de certitude. Aux deux dernières dates elle « rouvre », parce que le
script résiduel refait tirer des observations déjà consommées.

**Justification.** L'outer n'évalue aucun événement antérieur à t₀ et ne transmet à
l'inner que `WOF_MIN` et `BOF_MAX` — 2 des 12 paramètres d'état. Le gap est explicitement
documenté dans la docstring de `_eval_paths`.

**Impact utilisateur.** Faux percentiles, fausse probabilité de revalorisation.
**Impact réglementaire.** Tout scénario documentaire adossé au MTF est non fiable pour un
produit rappelable, c'est-à-dire pour l'essentiel du catalogue.

**Correction recommandée.** Évaluer les événements jusqu'à t₀ dans l'outer, transporter
l'état complet, et marquer à zéro les trajectoires terminées.
**Tests à ajouter.** MTF d'un produit rappelé avant t₀ ; MTF avec `INDEX`, mémoire et
strike fixing ; convergence des quantiles.
**Risque de régression.** Élevé.

---

### QNT-103 — Le vega Heston est multiplié par (1 − ρ²)

**Catégorie :** Greeks / modèle
**Statut :** confirmé
**Sévérité :** critique
**Probabilité :** forte
**Fichier :** `engine.py`
**Fonctions :** `_simulate_heston` (bloc `vol_add`), `compute_greeks`

**Correction préalable au rapport de juillet.** Celui-ci affirmait (QNT-003) que le vega
Heston cassait la martingale. **Ce constat ne se reproduit pas sur le code actuel** : le
drift utilise `bumped_variance = ρ²·V̄ + (1−ρ²)·sv²`, et la sonde de martingalité donne
un écart de 0,00 bp sur un payoff linéaire à N = 400 000. Ce point est corrigé.

**Comportement observé.** Le correctif a un effet de bord silencieux : `vol_add` ne bumpe
que la jambe de diffusion indépendante. Call ATM, N = 200 000, référence GBM = 0,3967
(vega Black-Scholes analytique = 0,3970) :

| ρ_h | vega Heston | ratio / GBM | (1 − ρ²) |
|---:|---:|---:|---:|
| 0,00 | 0,3818 | 0,962 | 1,000 |
| −0,30 | 0,3478 | 0,877 | 0,910 |
| **−0,70** | **0,1958** | **0,494** | **0,510** |
| −0,90 | 0,0729 | 0,184 | 0,190 |
| −0,99 | 0,0075 | 0,019 | 0,020 |

La loi est exacte. Au skew actions usuel (ρ_h = −0,7) le vega publié vaut **la moitié** du
vega vrai ; à ρ_h = −0,9, **un cinquième**.

**Comportement attendu.** Un champ nommé « vega » doit mesurer une translation de la
volatilité totale, ou porter un nom qui dit ce qu'il mesure.

**Impact utilisateur.** Le chiffre est étiqueté comme les autres Greeks, agrégé sur le
livre comme les autres, et rien ne signale qu'il sous-estime la sensibilité vol d'un
facteur qui dépend d'un paramètre de modèle.

**Correction recommandée.** Bumper la variance totale de façon cohérente, ou renommer en
vega idiosyncratique et exposer un vega de surface distinct.
**Tests à ajouter.** Vega Heston contre un bump de variance totale ; ratio au vega GBM
borné sur une plage de ρ_h.
**Risque de régression.** Moyen.

---

### QNT-104 — Les taux stochastiques ne refittent pas la courbe

**Catégorie :** modèle
**Statut :** confirmé
**Sévérité :** critique
**Probabilité :** forte
**Fichier :** `engine.py`
**Fonction :** `_stochastic_rate_paths`

**Comportement observé.** Zéro-coupon 5 ans, courbe plate 3 %, valeur exacte 0,860708 :

| σ_r | Prix moteur | Écart |
|---:|---:|---:|
| 0 % | 0,860708 | 0,00 bp |
| 1 % | 0,862516 | +18,1 bp |
| 2 % | 0,867964 | +72,6 bp |
| **3 %** | **0,877119** | **+164,1 bp** |

**Comportement attendu.** Le modèle est présenté comme Hull-White, dont la propriété
définissante est de reproduire exactement la courbe initiale.

**Justification.** `E[exp(−∫x dt)] ≠ 1` dès que la variance est positive : il manque
l'ajustement de convexité. Le biais est systématiquement **haussier** sur les prix.

**Impact sur le prix.** Activer les taux stochastiques déplace le prix d'un instrument
sans risque de plus d'un demi-point.
**Impact utilisateur.** Le modèle est annoncé plus exact qu'il ne l'est.

**Correction recommandée.** Calibrer la dérive, ou renommer le mode pour ce qu'il est.
**Tests à ajouter.** ZCB à chaque pilier de courbe, pour plusieurs `a_r` et `σ_r`.
**Risque de régression.** Élevé.

---

### QNT-105 — Les horizons intermédiaires du KID déclenchent la maturité

**Catégorie :** réglementation / simulation
**Statut :** confirmé
**Sévérité :** critique
**Probabilité :** forte
**Fichiers :** `backend/app/api/kid.py` (`_mc_percentiles`), `engine.py` (`mat_events`)

**Comportement observé.** Autocall 5 ans, barrière 100 %, coupon 8 %, σ = 25 % :

| Horizon | Prix | Payoff brut médian |
|---:|---:|---:|
| T = 1 an | 0,9252 | **0,9988** — le bloc `AT MATURITY` a tiré |
| T = 2,5 ans | 0,9210 | 1,0800 |
| T = 5 ans | 0,9352 | 1,0800 |

À l'horizon 1 an le produit est valorisé comme s'il arrivait à échéance et payait le
worst-of, au lieu de valoir un autocall encore vivant. Le prix n'est même pas monotone en
horizon.

**Justification.** `step_map` est bien filtré au-delà de l'horizon tronqué
(`{k: v for k, v in step_map.items() if k <= ts}`), mais `mat_events` ne l'est jamais.

**Impact réglementaire.** Scénarios de performance et rendements annualisés faux à tous
les horizons intermédiaires.

**Correction recommandée.** Revalorisation résiduelle à l'horizon, même mécanique que le
MTF corrigé.
**Tests à ajouter.** Autocall à chaque horizon intermédiaire ; monotonie du prix en
horizon.
**Risque de régression.** Élevé.

---

## 5. Anomalies confirmées, sévérité élevée

Format compact — le format complet à quinze champs est réservé aux critiques ci-dessus.

| ID | Titre | Preuve mesurée | Impact |
|---|---|---|---|
| **QNT-106** | Réparation silencieuse des corrélations | Matrice 3×3 à ρ = −0,9 (indéfinie) acceptée et **réparée en ρ = −0,5**, sans report | Worst-of pricé sur une dépendance non saisie |
| **QNT-107** | Matrice PSD singulière → exception brute | `[[1,1],[1,1]]` lève un `LinAlgError` non rattrapé (le test `eigvals.min() < 0` est faux quand la plus petite vaut 0) | Erreur 500 au lieu d'un message métier |
| **QNT-108** | `BASKET` dilue silencieusement | `BASKET(0.5, 0.5)` sur **un** actif renvoie 0,4999 au lieu de 1,0 | Erreur de prix de 50 %, sans signal |
| **QNT-109** | `S[0]` pointe le dernier actif | Sur un panier de 3, `S[0]` et `S[3]` donnent 1,001651 à l'identique | Payoff silencieusement différent de l'intention |
| **QNT-110** | `PAY` d'un `PARAM()` tableau | `TypeError: can't multiply sequence by non-int` — hors du `try`, donc non converti en erreur métier | Erreur 500 ; `SET X = CPN` puis `PAY X` fonctionne (0,029260, exact) |
| **QNT-111** | Modèle inconnu → GBM silencieux | `model="modele_inexistant"` accepté, prix strictement égal au GBM | Calcul sous un modèle non demandé, non traçable |
| **QNT-112** | Paramètres Heston non validés | `xi=0` → `ZeroDivisionError` ; `kappa<0`, `v0<0`, **`rho_h=−1,5`** acceptés, prix finis | Une corrélation hors [−1,1] produit un prix plausible |
| **QNT-113** | Corrélation actions altérée par le facteur taux | À ρ_rS = 0,9 la corrélation effective devient ρ_rS² + (1−ρ_rS²)·0,30 = **0,867** au lieu de 0,30 ; le worst-of passe de 0,9058 à 0,9590 | 5,3 points de prix sur un paramètre présenté comme sans rapport |
| **QNT-114** | Horizon étendu silencieusement | Script avec observation à t = 3, `T` demandé = 1,0 → `effective_T_max` = **3,0** | L'échéance pricée diffère de celle affichée |
| **QNT-115** | Quantification hebdomadaire | Toute maturité < ~10 jours s'écrase sur un pas unique ; ZC à 0 jour vaut 0,999423 au lieu de 1,0 | Maturités courtes et Theta près d'un fixing faussés |
| **QNT-116** | VaR et ES incluent une observation de trop | `cut = floor(α·n)` puis `tail = arr[:cut+1]` : à n = 100 la VaR 95 % est la **6ᵉ** pire perte et l'ES moyenne les **6** pires au lieu des 5 | Sous-estimation systématique du risque, marquée à faible n |
| **QNT-117** | Deux définitions du même quantile | `var_eur` utilise `arr[cut]`, `distribution_summary.p5` utilise `np.percentile` (interpolation linéaire) | Deux chiffres incohérents dans le même payload |
| **QNT-118** | Surface de vol locale saturée | **17,2 % des cellules** au plafond de 1,5 ; smile non monotone à 1 an (K=0,5 : 0,684 → K=1,3 : 0,191 → K=2,0 : 0,203) | Retournement du smile : arbitrage papillon probable |
| **QNT-119** | Grilles temporelles divergentes | MC à 52 pas/an, replay historique à 252 (`SY_H`) | La même date CONSTAT ne tombe pas au même instant selon le moteur |
| **QNT-120** | IRR à point de départ unique | Newton-Raphson, `guess=0.1`, renvoie `None` en cas d'échec — et les fenêtres échouées sont **exclues** des statistiques | Biais de sélection : les fenêtres pathologiques disparaissent |

---

## 6. Analyse des payoffs

### Ambiguïtés de templates

**QNT-121 — La famille Athena n'est pas homogène (confirmé, élevée).**
`autocall_athena` teste `INDIC(WOF < M_KI_BAR)` **à maturité seulement** — barrière
européenne. `autocall_worst_of` teste `INDIC(WOF_MIN < M_KI_BAR)` — barrière
path-dependent. Deux produits du même groupe, portant tous deux « Athena », avec des
barrières de nature économique différente et un écart de prime substantiel. Rien dans le
libellé ne les distingue.

**QNT-122 — Le Phoenix fourni n'a pas de mémoire (confirmé).** `PAY CPN * COUPON`, sans
accumulation. Un Phoenix sans mémoire de coupon est un autre produit que ce que le nom
annonce sur le marché.

**QNT-123 — « Call Vanille » sur panier (confirmé, moyenne).** Le template utilise `WOF`
et non `S[1]` : ajouter un second sous-jacent le transforme silencieusement en call
worst-of.

**QNT-124 — Gear put relatif au strike (probable).**
`LOSS = MIN(1, GEARING × MAX(0, 1 − WOF/K_P))` : la perte est proportionnelle à la baisse
relative **au strike**, convention défendable mais différente du
`GEARING × MAX(0, K_P − WOF)` usuel. À documenter contre une term sheet de référence.

### Cas limites du langage

Les barrières KI utilisent `<` (l'égalité n'est pas un franchissement) ; les autocalls et
digitals utilisent `>=` (l'égalité déclenche). Le paiement du principal dépend entièrement
du script : rien ne garantit qu'il soit payé une fois et une seule. Aucune contrainte ne
vérifie `K2 > K1`, `Cap >= Floor`, un coupon positif ou des barrières ordonnées.

---

## 7. Analyse Monte Carlo

### Éléments correctement conçus

Formule GBM exacte · terme `−0,5σ²` présent · diffusion en `√dt` · seed déterministe ·
nombres aléatoires communs sur **tous** les termes des différences finies, centre compris ·
antithétiques appariés **avant** le calcul de l'erreur standard · actualisation de chaque
flux à sa propre date · objet marché unique d'où sortent forwards, facteurs
d'actualisation et calibration Dupire.

### Benchmarks analytiques

r = 3 %, q = 1 %, σ = 20 %, T = 1 an, N = 200 000 :

| Instrument | Moteur | Référence | Écart |
|---|---:|---:|---:|
| Call ATM | 0,088222 | 0,088273 | −0,51 bp |
| Put ATM | 0,068603 | 0,068669 | −0,66 bp |
| Forward prépayé | 0,990064 | 0,990050 | +0,14 bp |
| Zéro-coupon | 0,970446 | 0,970446 | 0,00 bp |
| Parité C − P | +0,019619 | +0,019604 | +0,15 bp |

### Martingalité par modèle

`E[S_T]·DF` doit valoir `exp(−qT)`, N = 100 000 : GBM +1,49 bp · Heston −1,00 bp ·
SABR +0,94 bp · Local Vol +1,65 bp · LSV +1,15 bp.

### Convergence

Call ATM, 5 seeds :

| N | Moyenne | σ inter-seeds | Biais |
|---:|---:|---:|---:|
| 1 000 | 0,088444 | 0,001393 | +1,71 bp |
| 5 000 | 0,088291 | 0,001182 | +0,17 bp |
| 20 000 | 0,088214 | 0,000321 | −0,59 bp |
| 100 000 | 0,088395 | 0,000131 | +1,21 bp |

Décroissance conforme à 1/√N (facteur 10,6 pour ×100 sur N). Aucun biais détectable
au-delà de 2 bp.

### Grille temporelle

Zéro-coupon à r = 3 % :

| Maturité | Moteur | Exact | Écart | pas simulés |
|---|---:|---:|---:|---:|
| 0 jour | 0,999423 | 1,000000 | −5,77 bp | 1 |
| 1 jour | 0,999423 | 0,999918 | −4,95 bp | 1 |
| 7 jours | 0,999423 | 0,999425 | −0,02 bp | 1 |
| 10 jours | 0,999423 | 0,999179 | +2,44 bp | 1 |
| 14 jours | 0,998847 | 0,998851 | −0,04 bp | 2 |

Toute maturité inférieure à environ une semaine et demie devient un pas hebdomadaire.

---

## 8. Analyse des Greeks

| Greek | Implémentation | Convention |
|---|---|---|
| Delta | `[P(1,01·b) − P(0,99·b)] / 0,02` | par unité de spot relatif à la baseline |
| Gamma | `[P(1,03·b) − 2P(b) + P(0,97·b)] / 0,03²` | central |
| Vega | `[P(σ+1pt) − P(σ−1pt)] / 0,02` | par 100 points de vol |
| Rho | `[P(dr+100bp) − P(dr−100bp)] / 0,02` | shift parallèle de courbe |
| Theta | vieillissement d'une semaine, / 7 | par jour calendaire, hors flux traversé |
| Corr | `[P(ρ+5pt) − P(ρ)] / 0,05` | unilatéral |

**Validé.** Vega GBM mesuré à 0,3967 contre 0,3970 analytique. Le bump est désormais
multiplicatif autour du spot courant du deal, l'état lifecycle est transporté, et `wof0`
est dérivé du vecteur bumpé plutôt que passé — ce qui rend impossible l'oubli qui
polluerait `REALVOL`.

**Theta décomposé.** `theta` mesure la décroissance entre deux produits également privés
de l'observation traversée ; `theta_event` porte séparément le flux détaché, ses libellés
et un drapeau de rappel. `theta` vaut `None` plutôt que faux quand rouler l'état
demanderait de deviner (fixing dans la fenêtre, script à volatilité réalisée).

**Greeks absents ou insuffisamment définis :** sensibilité dividende · key-rate rhos ·
Vanna · Volga · Greeks sticky-strike / sticky-delta · erreur standard par Greek.

---

## 9. Analyse volatilité et corrélation

### Surface de volatilité locale

Grille 104 × 50 construite sur un smile polynomial (σ₀ = 25 %, skew = −0,15,
curvature = 0,10) :

- volatilité locale entre 0,175 et **1,500** ;
- **17,17 % des cellules au plafond de 1,5** ;
- 0 % au plancher ;
- ATM par pas (1, 26, 52, 78, 104) : 0,2510 · 0,2453 · 0,2438 · 0,2408 · 0,2378 ;
- smile à 1 an : K=0,5 → 0,6835 · K=0,8 → 0,3279 · K=1,0 → 0,2438 · K=1,3 → **0,1910** ·
  K=2,0 → **0,2029**.

Le retournement du smile entre K = 1,3 et K = 2,0 signale un arbitrage papillon probable.
Une surface dont un sixième des cellules est saturé à un plafond arbitraire n'est pas une
surface calibrée. Aucune calibration à des quotes implicites n'est présente dans le code.

### Corrélations

`cholesky` vérifie diagonale, symétrie et bornes, puis applique un jitter si la plus
petite valeur propre est **strictement** négative. Deux conséquences mesurées : une
matrice PSD singulière échappe au test et lève un `LinAlgError` brut (QNT-107) ; une
matrice indéfinie est réparée sans que la matrice effectivement utilisée soit restituée
(QNT-106, ρ = −0,9 devient −0,5).

---

## 10. Dates, fixings et calendriers

**Acquis majeur depuis juillet.** La gouvernance des fixings est en place et solide :
`DealEvent` sépare `spots_json` (officiel ou manuel) de `indicative_spots_json` (données
Yahoo non opposables), avec versions immuables (`OfficialFixingVersion`), maker-checker
(`fixing_status` : EXPECTED → RECEIVED → VALIDATED → APPLIED), empreintes de preuve et
piste d'audit. Le refresh n'écrit plus que dans le champ indicatif. Le constat de juillet
selon lequel un fixing manuel était écrasé **ne s'applique plus**.

**Reste ouvert.** Aucun calendrier de jours ouvrés ni de jours fériés · aucune convention
de business-day adjustment · aucun décalage de règlement · `/365,25` partout · grilles
divergentes 52 (MC) contre 252 (replay) · `effective_T_max` étendant l'horizon sans
avertir.

**Point d'interface relevé.** Le message de `_mtm_core` sur détection d'un rappel
anticipé invite à « lancer le refresh du cycle de vie », alors que le refresh ne peut plus
résoudre un deal : la résolution exige désormais un fixing validé par un Checker. Le
message est antérieur à la refonte et envoie l'utilisateur dans une impasse. Par ailleurs
la colonne « statut » du tableau des constatations affiche `status` (opérationnel) alors
que l'information pertinente est `fixing_status` — un fixing affiché à côté du mot
« futur » est incompréhensible.

---

## 11. Backtests et risque

**Backtest.** Calendrier à 252 lignes divergeant de la grille de pricing · look-ahead
persistant via `.ffill().bfill()` (le passé pré-IPO est rempli par le premier prix futur) ·
cours `auto_adjust=True`, donc ajustés rétroactivement des dividendes et splits, donc
différents des fixings contractuels · IRR à point de départ unique dont les échecs sont
**exclus** des statistiques, ce qui retire précisément les fenêtres pathologiques.

**VaR / ES.** Deux biais concordants, tous deux dans le sens d'une sous-estimation :
la VaR 95 % lit la 6ᵉ pire perte sur 100 scénarios au lieu de la 5ᵉ, et l'ES moyenne
une observation de trop (`arr[:cut+1]`). À faible nombre de scénarios l'effet est
matériel. S'y ajoute la coexistence de deux estimateurs du même quantile dans le même
payload (QNT-117).

---

## 12. Données de marché

Sources : Yahoo Finance via `yfinance`, caches parquet locaux.

**Fallbacks silencieux recensés :** dividende à 0 en cas d'exception réseau comme en cas
de champ absent (`or 0.0` puis `except: 0.0`) · corrélation retombant sur l'identité, ce
qui **maximise** la valeur d'un worst-of · FX à 1,0 quand la paire est introuvable, sans
que le payload cesse d'annoncer `"reporting_ccy": "EUR"` · `fx.iloc[-1]` partout, donc les
deux jambes d'un P&L explain historique sont converties au taux d'aujourd'hui · trois
valeurs par défaut différentes pour le dividende selon le chemin d'appel (0 %, 0 %, 2 %).

---

## 13. Couverture de tests

**495 tests.** Points forts : harnais de bit-identité (`test_engine_golden.py`, littéraux
figés) · validation Black-Scholes · boucles de référence pour la vectorisation
Heston/SABR · état résiduel · cohérence de courbe · Greeks stateful · signe des positions ·
workflow lifecycle et maker-checker.

**Lacunes, par gravité :** aucun test de barrière contre formule fermée · aucun test MTF
sur produit rappelé · aucun vecteur PRIIPs · aucun golden par template · aucun test de
matrice de corrélation dégénérée · aucun test de convergence temporelle · aucun test de
validation des paramètres de modèle.

---

## 14. Ce qui a été fermé depuis juillet

Vérifié par sonde, pas admis sur la foi du diff.

| Finding de juillet | Statut | Preuve numérique |
|---|---|---|
| QNT-001 drift / courbe incohérents | **fermé** | Forward prépayé = 0,990050 exact ; parité C−P +0,15 bp sous courbe |
| QNT-002 Greeks de deal vivant | **fermé** | `compute_greeks(state=…)` ; barrière franchie → delta = spot |
| QNT-003 vega Heston non martingale | **fermé** | Biais du bump vol sur un linéaire : 0,00 bp sous Heston |
| QNT-006 perte totale → MRM 1 | **fermé** | `p1 ≤ 0` → MRM 7, VEV absente, bandeau « non conforme PRIIPs » |
| QNT-010 risque non signé | **fermé** | `position_sign` lève sur valeur inattendue ; long + short = 0 |
| QNT-029 Rho ignorant la courbe | **fermé** | Rho ZC = −1,84640 vs −T·DF = −1,84623 ; non nul sous taux stochastiques |
| Fixings manuels écrasés | **fermé** | Séparation `spots_json` / `indicative_spots_json` + maker-checker versionné |

S'y ajoutent deux défauts trouvés hors rapport et corrigés le 31 juillet : le MtM semé à
1,0 au lieu du spot courant sur les deals à `STRIKE_FIX` future (erreur mesurée = le
facteur de seeding lui-même, ×1,3000), et l'onglet Chocs qui soustrayait deux produits
différents (−0,30 point sous choc nul).

---

## 15. Plan de remédiation priorisé

### P0 — bloquants d'usage

1. Restreindre le monitoring « continu » au discret tant que le pont n'est pas refait.
2. Interdire le MTF sur produit rappelable, ou le rendre stateful.
3. Étiqueter le vega Heston pour ce qu'il mesure réellement.
4. Refuser un modèle inconnu ; valider les paramètres Heston/SABR.
5. Reporter toute réparation de matrice de corrélation dans le résultat.

### P1 — justesse

1. Convexité Hull-White, ou renommage du mode.
2. Horizons intermédiaires KID en produit vivant.
3. VaR/ES : corriger la queue et unifier la définition du quantile.
4. Validations statiques du DSL : `BASKET`, `S[0]`, `PAY PARAM()`, `effective_T_max`.
5. Message de résolution lifecycle pointant vers la file Checker.

### P2 — fondations

1. Calendrier contractuel avec jours ouvrés et fériés.
2. Unification des grilles 52 / 252.
3. Suppression du backward fill ; politique explicite sur les cours ajustés.
4. Golden scenarios pour les 16 templates, avec spécification économique écrite.

### P3 — industrialisation

1. Calibration ou étiquetage « démonstrateur » des surfaces SABR / Local Vol / LSV.
2. Backtest as-of avec journal des exclusions.
3. Intégration continue backend et frontend.

---

## 16. Éléments non vérifiables

Conformité juridique du KID à une version donnée des RTS · correspondance de chaque
template à une term sheet · conventions de barrière intraday par émetteur · licence Yahoo
pour une valorisation officielle · ségrégation effective des rôles maker-checker en
production · représentativité du modèle retenu par produit · frais implicites PRIIPs.

---

## 17. Conclusion sur l'aptitude à la production

**Le chemin pré-trade GBM à monitoring discret est désormais défendable.** Il est validé
contre des références analytiques et contre une implémentation indépendante, à moins de
2 bp. C'est un progrès réel et vérifié, pas une déclaration.

**Restent hors périmètre de production :** le monitoring continu, le Mark-to-Future, le
vega Heston, les taux stochastiques, le KID, le backtest, et la VaR comme limite
officielle.

### Les 10 risques quantitatifs les plus critiques

1. QNT-101 — pont brownien à −14,3 % sur barrière proche
2. QNT-102 — MTF marquant un produit mort à 107 pendant 1,5 an
3. QNT-103 — vega Heston divisé par 2 au skew usuel
4. QNT-104 — Hull-White à +164 bp sur un ZC 5 ans
5. QNT-105 — KID déclenchant la maturité aux horizons intermédiaires
6. QNT-106 — corrélation −0,9 silencieusement réparée en −0,5
7. QNT-108 — `BASKET` divisant le panier par deux
8. QNT-116 — VaR/ES incluant une observation de trop
9. QNT-118 — 17 % de la surface de vol locale saturée au plafond
10. QNT-127 — backward fill introduisant de l'information future

### Les 10 tests indispensables à ajouter

1. Down-and-out contre Merton, en discret et en continu
2. MTF d'un produit rappelé avant t₀
3. Vega Heston contre un bump de variance totale
4. ZCB Hull-White à chaque pilier de courbe
5. Autocall 5 ans évalué à l'horizon KID 1 an
6. Matrice indéfinie : corrélation effective restituée
7. `BASKET` à poids excédentaires
8. VaR et ES exactes sur petit échantillon
9. Absence d'arbitrage papillon sur la grille de vol locale
10. Backtest d'une IPO sans backward fill

### Défauts empêchant une utilisation en production

Pont brownien biaisé · MTF non stateful · vega Heston mal défini · absence de convexité
Hull-White · moteur PRIIPs non conforme et horizons faux · réparation silencieuse des
corrélations · absence de calendrier contractuel · look-ahead dans les données
historiques · biais de sélection du backtest · VaR/ES sous-estimées.

### Composants bien conçus à conserver

L'objet `_RateTerm` et son invariant `step_fwd is None ⇔ courbe vide` · le harnais golden
de bit-identité · l'appariement antithétique avant l'erreur standard · les nombres
aléatoires communs sur tous les termes des différences finies · le transport d'état
lifecycle vers `run_mc` et `compute_greeks` · `wof0` dérivé plutôt que passé · la
décomposition `theta` / `theta_event` · la gouvernance des fixings officiels (versions
immuables, maker-checker, preuves hachées, séparation indicatif/officiel) ·
`position_sign` qui lève au lieu de choisir · le chunking du Monte Carlo imbriqué · les
messages d'erreur PayScript contextualisés · la structure générale du DSL PayScript.

---

**Fin du rapport.**
