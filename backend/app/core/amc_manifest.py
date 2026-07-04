"""AMC study manifest — schema, folder auto-detection, template generation.

The manifest is the single input that launches a study. Raw data files (the
LUKB exports: composition `Def.txt`, NAV `timeseries` CSV, order-book JSON)
carry the *data*; the manifest carries everything that is NOT in the data and
must be supplied by the structurer (fees from the term sheet, the benchmark
ticker, factor model, behavioural thresholds) plus which analysis blocks to run.

`detect_study_folder()` scans an ISIN folder, maps each file to its role, and
pre-fills a manifest — leaving the manual fields flagged so the user knows
exactly what to complete for a brand-new AMC.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Optional

from typing import List, Optional as Opt
from pydantic import BaseModel, Field

# ── Manifest schema ────────────────────────────────────────────────────

# Sentinel for a manual field the auto-detector could not fill. Surfaces in
# the UI / template as an explicit "à compléter" rather than a silent default.
TODO = "<À COMPLÉTER>"


class ProductInfo(BaseModel):
    isin: str
    name: str = ""
    currency: str = "CHF"          # product (NAV) currency
    theme: str = ""                # e.g. "New Financials", "Infrastructures"


class FileRoles(BaseModel):
    """Paths are relative to the study folder (manifest lives there)."""
    composition: str = ""          # the "* Def.txt" snapshot
    nav_timeseries: str = ""       # the "* timeseries *.csv" NAV history
    orders: List[str] = Field(default_factory=list)  # order-book JSON files


class TermsheetPosition(BaseModel):
    """One equity line from the AMC term sheet. Used for the Référentiel Inertiel (Bloc E)."""
    isin: str
    name: str = ""
    weight_pct: float                # e.g. 5.0 for a 5% weight
    qty_per_cert: float              # exact quantity per certificate from the TS fixing
    fixing_price: float = 0.0       # TS fixing price — used as T0 cost basis in FIFO (t0_synthetic) and for NAV-units conversion
    ccy: str = "USD"                 # position currency (ISO 3-letter code)


class ManualParams(BaseModel):
    """Inputs that are NOT present in the raw exports — must be supplied."""
    management_fee_pct: Optional[float] = None   # term sheet; p.a. %, for gross add-back
    perf_fee_pct: Optional[float] = None         # term sheet; % of gains above high-water-mark,
                                                  # crystallised daily on new highs (NAV reconciliation)
    txn_cost_pct: Optional[float] = None         # term sheet; % of notional per rebalancing trade
                                                  # (NAV reconciliation)
    benchmark_ticker: str = "ACWI"               # thematic benchmark (2nd regression)
    factor_model: str = "FF5+MOM"                # FF3 | FF5 | FF5+MOM
    ff_series: str = "Developed_5F"              # key into amc_engine.FF_SERIES
    selected_factors: Optional[List[str]] = None # override factor_model with an explicit list
    rolling_window: int = 60                     # rolling regression window (days)
    risk_free: str = "auto"                      # "auto" = use FF RF column
    long_term_holding_days: int = 180            # conviction vs tactical cutoff (Bloc D)
    conviction_weight_pct: float = 4.0           # weight above which a name = high conviction
    # FIFO reconstruction mode:
    #   "t0_synthetic" — default: inject synthetic BUY orders at NAV inception date using yfinance
    #                    prices; gives a more realistic P&L at the cost of estimated entries
    #   "strict"       — clamp excess sells (P&L = 0 for pre-carnet positions), fully auditable
    recon_mode: str = "t0_synthetic"
    # Référentiel Inertiel (Bloc E) — sourced from the term sheet PDF
    n_certs: int = 75_000                                               # certificats à l'émission
    termsheet_positions: List[TermsheetPosition] = Field(default_factory=list)  # compositions TS


class BlockToggles(BaseModel):
    """Run the complete study or any subset. B/C/D share the order-book parser."""
    A_factor: bool = True          # Fama-French / style regression
    B_attribution: bool = True     # P&L by underlying (realised + latent)
    C_trading: bool = True         # turnover / round-trips / decision quality
    D_behaviour: bool = True       # conviction vs uncertainty
    F_replicability: bool = True   # replicating portfolio from FF betas (requires A)
    H_timing: bool = True          # entry/exit timing score (requires stored prices)
    I_stockpicking: bool = True    # stock picking alpha vs benchmark (requires stored prices)
    J_riskmanagement: bool = True  # risk management score (requires nav + composition)


class OutputOptions(BaseModel):
    language: str = "fr"
    audience: str = "committee"    # committee | investor | due_diligence


class StudyManifest(BaseModel):
    schema_version: str = "1.0"
    product: ProductInfo
    files: FileRoles
    params: ManualParams = Field(default_factory=ManualParams)
    blocks: BlockToggles = Field(default_factory=BlockToggles)
    output: OutputOptions = Field(default_factory=OutputOptions)


# ── Field documentation (rendered in the app, field by field) ──────────

MANIFEST_DOC: List[dict] = [
    {"path": "product.isin", "required": True, "auto": True,
     "desc": "Code ISIN de l'AMC. Détecté depuis le nom du dossier."},
    {"path": "product.name", "required": False, "auto": True,
     "desc": "Nom commercial du produit. Lu dans le fichier Def.txt."},
    {"path": "product.currency", "required": True, "auto": True,
     "desc": "Devise de la NAV (CHF/EUR/USD). Lue dans Def.txt."},
    {"path": "product.theme", "required": False, "auto": True,
     "desc": "Thème du panier (New Financials, Infrastructures…). Déduit du nom."},
    {"path": "files.composition", "required": True, "auto": True,
     "desc": "Snapshot de composition « * Def.txt » (positions, poids, marks)."},
    {"path": "files.nav_timeseries", "required": True, "auto": True,
     "desc": "Historique NAV « * timeseries *.csv » (base 100)."},
    {"path": "files.orders", "required": True, "auto": True,
     "desc": "Carnet d'ordres JSON. On privilégie le fichier « merged-*.json » "
             "(union dédoublonnée) ; sinon les « * DataN.json »."},
    {"path": "params.management_fee_pct", "required": True, "auto": False,
     "desc": "⚠️ MANUEL — commission de gestion p.a. (%), lue sur la term sheet PDF. "
             "Sert au calcul de l'alpha BRUT (NAV regrossie des frais) et à la réconciliation NAV (Bloc B)."},
    {"path": "params.perf_fee_pct", "required": False, "auto": False,
     "desc": "⚠️ MANUEL — commission de performance (%) sur les gains au-dessus du plus haut "
             "historique (High Water Mark), lue sur la term sheet PDF. Prélevée quotidiennement "
             "sur chaque nouveau plus-haut, pas annuellement. Sert à la réconciliation NAV (Bloc B)."},
    {"path": "params.txn_cost_pct", "required": False, "auto": False,
     "desc": "⚠️ MANUEL — coût de transaction (%) du notionnel à chaque rebalancement, lu sur la "
             "term sheet PDF. Sert à la réconciliation NAV (Bloc B)."},
    {"path": "params.benchmark_ticker", "required": True, "auto": False,
     "desc": "⚠️ MANUEL — ticker du benchmark sectoriel du thème (2ᵉ régression). "
             "Ex. XLF financières, PAVE/IGF infrastructures, XBI biotech."},
    {"path": "params.factor_model", "required": False, "auto": False,
     "desc": "Modèle factoriel : FF3, FF5 ou FF5+MOM (Carhart, ajoute le momentum)."},
    {"path": "params.ff_series", "required": False, "auto": True,
     "desc": "Série de facteurs Ken French (clé du catalogue). Déduite de la devise."},
    {"path": "params.long_term_holding_days", "required": False, "auto": False,
     "desc": "Seuil (jours) au-delà duquel une position est jugée « long terme / "
             "conviction » plutôt que tactique (Bloc D)."},
    {"path": "params.conviction_weight_pct", "required": False, "auto": False,
     "desc": "Poids (%) au-dessus duquel une position est dite « forte conviction » (Bloc D)."},
    {"path": "params.recon_mode", "required": False, "auto": False,
     "desc": "Mode de reconstruction FIFO. 'strict' (défaut) : P&L clampé à 0 pour les ventes "
             "sans lot connu (positions pré-carnet). 't0_synthetic' : injecte des BUY synthétiques "
             "à la date de départ de l'AMC (1ère NAV) au prix yfinance — plus précis mais estimé. "
             "Utiliser 'strict' pour un rapport auditoriable, 't0_synthetic' pour une analyse interne."},
    {"path": "blocks.*", "required": False, "auto": False,
     "desc": "Lancement modulaire : true/false par bloc. A=Factoriel, B=Attribution, "
             "C=Trading/turnover, D=Comportement. B/C/D partagent le parseur d'ordres."},
    {"path": "output.audience", "required": False, "auto": False,
     "desc": "Cible du rapport : committee (technique), investor (pédagogique), "
             "due_diligence (factuel/traçable). Ajuste le ton et le détail."},
]

# What each block does / how / with which inputs — shown before launch and in the report.
BLOCK_CATALOG: List[dict] = [
    {"key": "A_factor", "title": "A — Analyse factorielle (Fama-French)",
     "what": "Alpha du gérant et expositions de style ; brut (avant frais) et net.",
     "how": "Régression OLS FF5 (+ momentum), régression glissante, 2ᵉ régression "
            "sur benchmark sectoriel.",
     "inputs": "NAV (timeseries), facteurs Ken French, frais (pour le brut), benchmark."},
    {"key": "B_attribution", "title": "B — Attribution par sous-jacent & période",
     "what": "Quels sous-jacents ont créé/détruit de la performance, et quand. "
             "P&L réalisé + latent, décomposé prix vs change (FX).",
     "how": "Reconstruction des positions en FIFO depuis les ordres. "
            "Mark courant issu du Price Store (série historique de clôture ajustée, parquet) ; "
            "fallback yfinance si le titre n'est pas encore dans le store.",
     "inputs": "Carnet d'ordres + composition (Def.txt) + Price Store (parquet local)."},
    {"key": "C_trading", "title": "C — Trading, turnover & qualité des décisions",
     "what": "Taux de rotation, aller-retours (round-trips), hit ratio, P&L de "
             "trading vs portage.",
     "how": "Appariement achats/ventes, durées de détention, statistiques de trades.",
     "inputs": "Carnet d'ordres."},
    {"key": "D_behaviour", "title": "D — Comportement : conviction vs incertitude",
     "what": "Distingue les paris de conviction long terme des positions "
             "d'incertitude (churn, ordres annulés, flip-flop).",
     "how": "Durées de détention, ordres Discarded, fills partiels, sizing, "
            "matrice 2×2 conviction × résultat.",
     "inputs": "Carnet d'ordres + composition."},
    {"key": "E_bh", "title": "E — Référentiel Inertiel (Buy & Hold passif)",
     "what": "Répond à : « Si le gérant n'avait rien fait depuis l'émission, quelle serait la performance ? » "
             "Source primaire : poids de la term sheet (params.termsheet_positions). "
             "Fallback : identité comptable qty_initiale = position_actuelle + ventes − achats. "
             "VAG = performance AMC réelle − Référentiel. > 0 → le gérant a créé de la valeur.",
     "how": "Méthode TS : Σ(poids_TS_i × total_return_yfinance_i) / Σ(poids_TS_i). "
            "Total return = prix_ajusté_aujourd'hui / prix_ajusté_T0 (dividendes inclus). "
            "FX intégré pour les actifs hors devise produit. "
            "n_certs (params.n_certs, défaut 75 000) détermine les valeurs absolues.",
     "inputs": "params.termsheet_positions (recommandé) ou carnet d'ordres + Def.txt (fallback). "
               "yfinance pour les prix ajustés (total return)."},
    {"key": "F_replicability", "title": "F — Réplicabilité de la Stratégie",
     "what": "Construit un portefeuille réplicant passif à partir des bêtas FF5+MOM (Bloc A) "
             "et compare sa trajectoire à la NAV réelle. Calcule un score de réplicabilité 0-100 "
             "et décompose la performance du réplicant par facteur.",
     "how": "R_réplicant(t) = RF(t) + Σ βi × Fi(t). Score = 40% × R² + 35% × (perf_réplicant / "
            "perf_AMC) + 25% × (1 − min(|t_alpha|/3, 1)). Interprétation : 0-40 discrétionnaire, "
            "40-60 mixte, 60-100 systématique.",
     "inputs": "Résultat du Bloc A (bêtas, R², alpha, séries journalières data_used). "
               "Aucune donnée externe supplémentaire."},
    {"key": "G_brinson", "title": "G — Attribution Brinson-Fachler",
     "what": "Décompose la surperformance active (portefeuille − benchmark) en trois effets : "
             "Allocation (surpondération des bons secteurs), Sélection (meilleurs titres dans "
             "chaque secteur), Interaction (surpondéré précisément où on sur-sélectionne).",
     "how": "Brinson-Fachler single-période. Allocation = (w_p − w_b) × (r_b,s − R_b). "
            "Sélection = w_b × (r_p,s − r_b,s). Interaction = (w_p − w_b) × (r_p,s − r_b,s). "
            "NOTE : le snapshot de composition (Def.txt) reflète la date de la dernière NAV, "
            "non la composition initiale — l'écart avec les poids d'émission peut introduire "
            "un biais dans les effets Allocation et Sélection.",
     "inputs": "Price Store (parquet local, auto-alimenté à la première étude), "
               "composition snapshot (Def.txt), benchmark ETF iShares (yfinance)."},
    {"key": "H_timing", "title": "H — Timing Score : Qualité des Points d'Entrée et de Sortie",
     "what": "Mesure comportementale de la qualité du timing du gérant : pour chaque ordre "
             "exécuté, positionne le prix d'exécution dans le range de prix local observé "
             "sur ±30 jours. Score 0→1 (1 = acheté au plus bas / vendu au plus haut). "
             "Baseline aléatoire = 0.5. Produit des histogrammes et une conclusion statistique.",
     "how": "Entry Score = (max_window − prix_achat) / (max_window − min_window). "
            "Exit Score = (prix_vente − min_window) / (max_window − min_window). "
            "Test t one-sample vs µ₀ = 0.5. "
            "Garde outlier : tout trade dont le prix d'exécution dépasse ×3 le range de la "
            "fenêtre est exclu et signalé (suspicion de split non ajusté ou saisie erronée). "
            "LIMITE : les prix du store sont split-adjusted (yfinance auto_adjust=True) ; "
            "les prix d'exécution du carnet sont as-traded — un split post-achat peut créer "
            "un écart apparent. Ces trades sont identifiés et exclus par la garde ×3.",
     "inputs": "Price Store local (parquet, auto-alimenté depuis yfinance à la première étude "
               "sur chaque AMC). Couverture proportionnelle aux titres présents dans le store."},
    {"key": "I_stockpicking", "title": "I — Stock Picking Score : Qualité de la Sélection de Titres",
     "what": "Mesure si le gérant sélectionne des titres qui surperforment structurellement leur benchmark. "
             "Pour chaque achat, calcule le retour du titre à 1M, 3M, 6M et 12M, soustrait le retour "
             "du benchmark sur la même période, et agrège un alpha moyen, un taux de succès et un score 0-100.",
     "how": "Alpha_i(h) = Retour(titre, h) − Retour(benchmark, h). Score = 40% × alpha_score + "
            "35% × success_rate_score + 25% × information_ratio_score. Test t one-sample vs µ₀=0. "
            "Les positions ouvertes utilisent le dernier prix disponible (alpha latent). "
            "Un alpha tiré par 2-3 lignes extrêmes est identifié dans la table 'meilleures idées'.",
     "inputs": "Price Store local (parquet, auto-alimenté depuis yfinance à la première étude) "
               "+ prix du benchmark (yfinance, même ticker que le Bloc A). "
               "Couverture proportionnelle aux titres présents dans le store."},
    {"key": "J_riskmanagement", "title": "J — Risk Management Score",
     "what": "Évalue si le gérant a correctement géré le risque qu'il a pris — drawdowns, volatilité baissière, "
             "ratios ajustés du risque, concentration du portefeuille et exposition factorielle.",
     "how": "5 sous-scores pondérés : Performance ajustée du risque 30% (Sharpe, Calmar, capture ratios, IR), "
            "Gestion drawdown 25% (Max DD, Ulcer Index, épisodes), Risque baissier 20% (semi-écart, Sortino, "
            "VaR 95%, ES 95%), Concentration 15% (max poids, HHI, N effectif), Risque factoriel 10% "
            "(R², beta marché, alpha t-stat). Score plafonné selon le nombre d'observations (< 30 obs → cap 50). "
            "NOTE : fenêtre temporelle propre au Bloc J (NAV complète depuis première VL) — peut différer "
            "de la fenêtre du Bloc A (intersection avec facteurs FF).",
     "inputs": "NAV historique (timeseries), composition actuelle (Def.txt), résultat Bloc A (pour le risque factoriel), "
               "benchmark (yfinance — pour les capture ratios et le benchmark drawdown)."},
]


# ── Folder auto-detection ──────────────────────────────────────────────

def _theme_from_name(name: str) -> str:
    low = name.lower()
    if "financ" in low:
        return "New Financials"
    if "infrastructure" in low:
        return "Infrastructures"
    if "life" in low or "bio" in low or "health" in low:
        return "Life / Healthcare"
    return ""


def _ff_series_for_ccy(ccy: str) -> str:
    # Ken French factors are USD-denominated; Developed is the best broad proxy.
    return {"USD": "US_5F", "EUR": "EU_5F", "CHF": "Developed_5F"}.get(ccy.upper(), "Developed_5F")


def detect_study_folder(folder: str) -> dict:  # noqa: C901
    """Scan an ISIN folder and return a pre-filled manifest (as dict) plus the
    list of missing manual fields. Manual fields are set to the TODO sentinel."""
    p = Path(folder)
    if not p.is_dir():
        raise ValueError(f"Dossier introuvable : {folder}")

    isin = p.name  # folders are named by ISIN

    def _rel(path: str) -> str:
        return os.path.basename(path)

    # composition: "* Def.txt"
    comp = next(iter(glob.glob(str(p / "*Def.txt"))), "")
    # nav timeseries: "* timeseries *.csv"
    nav = next(iter(glob.glob(str(p / "*timeseries*.csv"))), "")
    if not nav:
        nav = next(iter(glob.glob(str(p / "*.csv"))), "")
    # orders: prefer merged-*.json (clean union), else the * DataN.json set
    merged = sorted(glob.glob(str(p / "merged*.json")))
    if merged:
        orders = merged
    else:
        orders = sorted(glob.glob(str(p / "*Data*.json")))

    # Read product meta from composition if available
    name = isin
    currency = "CHF"
    if comp:
        try:
            with open(comp, encoding="utf-8") as fh:
                d = json.load(fh)
            prod = d["data"]["products"]["items"][0]
            name = prod.get("name") or isin
            currency = prod.get("currency") or "CHF"
        except Exception:
            pass

    theme = _theme_from_name(name)

    # Auto-load termsheet positions from termsheet_positions.json if present
    ts_positions: list = []
    ts_file = p / "termsheet_positions.json"
    if ts_file.exists():
        try:
            with open(ts_file, encoding="utf-8") as fh:
                ts_positions = json.load(fh)
        except Exception:
            pass

    manifest = StudyManifest(
        product=ProductInfo(isin=isin, name=name, currency=currency, theme=theme),
        files=FileRoles(
            composition=_rel(comp) if comp else "",
            nav_timeseries=_rel(nav) if nav else "",
            orders=[_rel(o) for o in orders],
        ),
        params=ManualParams(
            management_fee_pct=None,            # ⚠ manual
            benchmark_ticker=TODO,              # ⚠ manual
            ff_series=_ff_series_for_ccy(currency),
            termsheet_positions=ts_positions,
        ),
    )

    missing = []
    if manifest.params.management_fee_pct is None:
        missing.append("params.management_fee_pct (commission p.a. — term sheet PDF)")
    if manifest.params.benchmark_ticker == TODO:
        missing.append("params.benchmark_ticker (benchmark sectoriel du thème)")
    if not manifest.files.composition:
        missing.append("files.composition (aucun *Def.txt trouvé)")
    if not manifest.files.nav_timeseries:
        missing.append("files.nav_timeseries (aucun *timeseries*.csv trouvé)")
    if not manifest.files.orders:
        missing.append("files.orders (aucun carnet d'ordres JSON trouvé)")

    return {
        "manifest": manifest.model_dump(),
        "missing_manual_fields": missing,
        "folder": str(p),
    }


def blank_template() -> dict:
    """A documented blank manifest for creating a study on a new AMC by hand."""
    m = StudyManifest(
        product=ProductInfo(isin=TODO, name="", currency="CHF", theme=""),
        files=FileRoles(composition="", nav_timeseries="", orders=[]),
        params=ManualParams(management_fee_pct=None, benchmark_ticker=TODO),
    )
    return m.model_dump()
