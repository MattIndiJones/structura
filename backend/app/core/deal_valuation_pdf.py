"""Client-facing valuation note (PDF) for a live structured product deal.

Built from the residual-MtM output (api/deals.py:_mtm_core) — the PDF shows
EXACTLY the figure displayed in the Booking page (same seed, same body).
Light print-friendly palette (unlike the dark AMC report), French wording,
rule-based explanation sentences (no free text generation): every statement
is derived from fields of the MtM payload. Design: NOTE_VALO_DESIGN.md.

The builder is a pure function of a plain-dict `data` payload so it can be
unit-tested offline (see tests/test_valuation_pdf.py)."""
from __future__ import annotations

import io
import os
import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, PageBreak,
)

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static",
                          "tp_logo_blue_transparent.png")

# ── Light palette (print-friendly) ─────────────────────────────────────
C_TEXT    = colors.HexColor("#0f172a")   # slate-900
C_MUTED   = colors.HexColor("#475569")   # slate-600
C_FAINT   = colors.HexColor("#94a3b8")   # slate-400
C_BLUE    = colors.HexColor("#2563eb")   # blue-600
C_GREEN   = colors.HexColor("#059669")   # emerald-600
C_RED     = colors.HexColor("#dc2626")   # red-600
C_AMBER   = colors.HexColor("#d97706")   # amber-600
C_BORDER  = colors.HexColor("#e2e8f0")   # slate-200
C_CARD    = colors.HexColor("#f8fafc")   # slate-50

W, H    = A4
MARGIN  = 1.8 * cm
INNER_W = W - 2 * MARGIN

SERIES_COLORS = ["#2563eb", "#059669", "#d97706", "#db2777", "#7c3aed", "#ea580c"]


def _sty(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9, textColor=C_TEXT,
                leading=13, spaceAfter=0, spaceBefore=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_TITLE   = _sty("v_title", fontName="Helvetica-Bold", fontSize=19, leading=24)
S_SUB     = _sty("v_sub", fontSize=9, textColor=C_MUTED)
S_SECTION = _sty("v_section", fontName="Helvetica-Bold", fontSize=11,
                 textColor=C_BLUE, leading=15, spaceBefore=13, spaceAfter=5)
S_BODY    = _sty("v_body", fontSize=9, textColor=C_MUTED, leading=13.5,
                 alignment=TA_JUSTIFY)
S_LABEL   = _sty("v_label", fontSize=7.5, textColor=C_FAINT)
S_VAL     = _sty("v_val", fontName="Helvetica-Bold", fontSize=11)
S_BIG     = _sty("v_big", fontName="Helvetica-Bold", fontSize=17, textColor=C_BLUE,
                 leading=20)
S_SMALL   = _sty("v_small", fontSize=7.5, textColor=C_FAINT, leading=10)
S_CELL    = _sty("v_cell", fontSize=8.5, textColor=C_MUTED)
S_CELL_R  = _sty("v_cellr", fontSize=8.5, textColor=C_MUTED, alignment=TA_RIGHT)
S_CENTER  = _sty("v_center", fontSize=8.5, textColor=C_MUTED, alignment=TA_CENTER)


def _fmt_nominal(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _logo_image(max_w=3.4 * cm, max_h=0.95 * cm) -> Image | None:
    """Logo scaled to its intrinsic aspect ratio (a hardcoded ratio clipped it
    against the top margin) — bounded by max_w × max_h, right-aligned by the
    header table."""
    if not os.path.exists(_LOGO_PATH):
        return None
    iw, ih = ImageReader(_LOGO_PATH).getSize()
    scale = min(max_w / iw, max_h / ih)
    return Image(_LOGO_PATH, width=iw * scale, height=ih * scale)


def _header(story: list, title: str, subtitle: str) -> None:
    left = [Paragraph(title, S_TITLE), Spacer(1, 3), Paragraph(subtitle, S_SUB)]
    logo = _logo_image()
    if logo:
        head = Table([[left, logo]], colWidths=[INNER_W - 3.8 * cm, 3.8 * cm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(head)
    else:
        story.extend(left)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.2, color=C_BLUE))
    story.append(Spacer(1, 10))


def _footer(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 6.5)
    canv.setFillColor(C_FAINT)
    canv.drawString(MARGIN, 0.85 * cm,
                    "Structura — document indicatif, ne constitue pas un prix ferme")
    canv.drawRightString(W - MARGIN, 0.85 * cm, f"Page {canv.getPageNumber()}")
    canv.restoreState()


def _fig_to_image(fig, width_cm=17.0, height_cm=7.0) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight",
                facecolor="white")
    buf.seek(0)
    plt.close(fig)
    return Image(buf, width=width_cm * cm, height=height_cm * cm)


# ── Rule-based explanation ─────────────────────────────────────────────

def _monitor_label(m: dict) -> str:
    """Human name of an M_ barrier from its direction (usage-derived)."""
    if m.get("direction") == "up":
        return "barrière de rappel"
    if m.get("direction") == "down":
        return "barrière de protection"
    return "niveau surveillé"


def build_explanation(data: dict) -> list[str]:
    """French explanation sentences, each one derived from a payload field —
    no free-form generation, the note can be audited line by line."""
    mtm = data["mtm"]
    deal = data["deal"]
    uls = data["underlyings"]
    monitors = data.get("monitors") or []
    lines: list[str] = []

    # Spot positioning
    if len(uls) == 1:
        u = uls[0]
        lines.append(f"Le sous-jacent {u['name']} cote actuellement à "
                     f"{u['spot_pct'] * 100:.1f}% de son niveau de référence initial.")
    else:
        pos = ", ".join(f"{u['name']} à {u['spot_pct'] * 100:.1f}%" for u in uls)
        worst = min(uls, key=lambda u: u["spot_pct"])
        lines.append(f"Les sous-jacents cotent respectivement {pos} de leur niveau "
                     f"initial ; le moins performant est {worst['name']}.")

    cur_wof = min(u["spot_pct"] for u in uls)
    wof_min = mtm.get("wof_min_realized")

    for m in monitors:
        lvl = m.get("level")
        if lvl is None:
            continue
        lbl = _monitor_label(m)
        if m.get("direction") == "up":
            rel = "au-dessus" if cur_wof >= lvl else "en dessous"
            lines.append(f"Le produit se trouve {rel} de la {lbl} "
                         f"({lvl * 100:.0f}% du niveau initial).")
        elif m.get("direction") == "down" and wof_min is not None:
            if wof_min < lvl:
                lines.append(f"La {lbl} ({lvl * 100:.0f}%) a été touchée depuis le "
                             f"lancement (plus bas atteint : {wof_min * 100:.1f}%) — la "
                             f"protection conditionnelle du capital est désactivée.")
            else:
                lines.append(f"La {lbl} ({lvl * 100:.0f}%) n'a jamais été touchée depuis "
                             f"le lancement — plus bas atteint par le sous-jacent le moins "
                             f"performant : {wof_min * 100:.1f}% (observé sur les clôtures "
                             f"quotidiennes).")

    nxt = data.get("next_obs_date")
    if nxt:
        lines.append(f"Prochaine date d'observation : {nxt}.")

    p = mtm.get("prob_gt100")
    if p is not None:
        n_str = f"{mtm.get('n_paths', 0):,}".replace(",", " ")
        lines.append(f"Sur {n_str} trajectoires de marché simulées, la probabilité de "
                     f"percevoir au moins le capital initial est estimée à {p * 100:.0f}%.")

    fugit = mtm.get("fugit")
    t_rem = mtm.get("T_remaining")
    if fugit is not None and t_rem:
        s = (f"La durée de vie résiduelle attendue du produit est d'environ "
             f"{fugit:.1f} an(s), pour une maturité contractuelle dans {t_rem:.1f} an(s)")
        if fugit < 0.7 * t_rem:
            s += " — un remboursement anticipé est le scénario central"
        lines.append(s + ".")

    rt = mtm.get("realized_total")
    if rt:
        lines.append(f"Flux déjà perçus depuis le lancement : {rt * 100:.2f}% du nominal.")

    # Residual upside vs best possible outcome
    bc = mtm.get("best_case")
    if bc and bc.get("pv_max"):
        if bc.get("capped"):
            lines.append(
                f"Le meilleur dénouement possible du produit vaut aujourd'hui "
                f"{bc['pv_max'] * 100:.2f}% en valeur actualisée ; la valeur actuelle en "
                f"capture {bc['capture_ratio'] * 100:.1f}%. Le potentiel résiduel maximal "
                f"est de {bc['upside_pts']:.2f} point(s) sur une durée attendue de "
                f"{bc['horizon_years']:.1f} an(s), soit environ "
                f"{bc['upside_annualized_pct']:.1f}% en rythme annualisé.")
        elif bc.get("pv_p95"):
            # Top of the distribution not flat (open upside, or step coupons
            # spreading the call outcomes): no cap claim, no exit signal —
            # just the favourable-scenario quantile.
            lines.append(
                f"Dans un scénario favorable (95e centile des simulations), la valeur "
                f"de dénouement actualisée du produit atteint {bc['pv_p95'] * 100:.2f}% ; "
                f"le meilleur scénario simulé atteint {bc['pv_max'] * 100:.2f}%.")

    # Conclusion
    v = mtm["mtm"]
    rel_pair = "au-dessus du" if v >= 1.0 else "en dessous du"
    concl = (f"Au total, la valeur indicative (mark-to-market) du produit ressort à "
             f"{v * 100:.2f}% du nominal, {rel_pair} pair")
    pt = deal.get("price_traded")
    if pt is not None:
        d = v * 100 - pt
        concl += (f", soit {'+' if d >= 0 else ''}{d:.2f} point(s) par rapport au prix "
                  f"de transaction ({pt:.2f}%)")
    lines.append(concl + ".")
    return lines


# ── Chart: underlying paths since strike + barriers ───────────────────

def _chart_history(data: dict) -> Image | None:
    hist = data.get("history") or {}
    dates = hist.get("dates") or []
    series = hist.get("series") or {}
    if not dates or not series:
        return None
    fig, ax = plt.subplots(figsize=(9.5, 4.2), facecolor="white")
    ax.set_facecolor("white")
    n = len(dates)

    for i, (name, vals) in enumerate(series.items()):
        y = np.array([v if (v is not None and v > 0) else np.nan for v in vals],
                     dtype=float) * 100.0
        ax.plot(range(len(y)), y, linewidth=1.4,
                color=SERIES_COLORS[i % len(SERIES_COLORS)], label=name)

    ax.axhline(100.0, color="#94a3b8", linewidth=0.8, linestyle=":")
    for m in data.get("monitors") or []:
        lvl = m.get("level")
        if lvl is None:
            continue
        col = "#059669" if m.get("direction") == "up" else "#dc2626"
        ax.axhline(lvl * 100.0, color=col, linewidth=1.0, linestyle="--", alpha=0.8)
        ax.annotate(f"{_monitor_label(m)} {lvl * 100:.0f}%",
                    xy=(0.01, lvl * 100.0), xycoords=("axes fraction", "data"),
                    fontsize=6.5, color=col, va="bottom")

    # Past observation dates + today
    for ev in data.get("events") or []:
        if ev.get("t_years", 0) > 0 and ev.get("status") not in ("futur", "annulé"):
            try:
                idx = max(i for i, d in enumerate(dates) if d <= ev["date"])
            except ValueError:
                continue
            ax.axvline(idx, color="#cbd5e1", linewidth=0.7, alpha=0.6)
    ax.axvline(n - 1, color="#0f172a", linewidth=1.0)
    ax.annotate("aujourd'hui", xy=(n - 1, 1.0), xycoords=("data", "axes fraction"),
                fontsize=6.5, color="#0f172a", ha="right", va="bottom")

    ax.tick_params(colors="#64748b", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#e2e8f0")
    ax.grid(color="#f1f5f9", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_ylabel("% du niveau initial", color="#64748b", fontsize=7)
    step = max(1, n // 7)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=20,
                       ha="right", fontsize=6.5)
    ax.legend(fontsize=7, framealpha=0, labelcolor="#475569", loc="best")
    return _fig_to_image(fig, 17, 7.2)


# ── Tables ─────────────────────────────────────────────────────────────

def _tbl(rows, col_widths, header=False):
    t = Table(rows, colWidths=col_widths)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, C_BORDER),
    ]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.8, C_FAINT),
                  ("BACKGROUND", (0, 0), (-1, 0), C_CARD),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_CARD])]
    t.setStyle(TableStyle(style))
    return t


def _id_table(deal: dict, uls: list) -> Table:
    def row(l1, v1, l2, v2):
        return [Paragraph(l1, S_LABEL), Paragraph(v1, S_CELL),
                Paragraph(l2, S_LABEL), Paragraph(v2, S_CELL)]
    ul_names = " / ".join(f"{u['name']} ({u.get('ticker', '')})" for u in uls)
    rows = [
        row("Référence", deal.get("reference", "—"),
            "Type de produit", deal.get("product_type") or "Produit structuré"),
        row("Sous-jacent(s)", ul_names,
            "Sens", (deal.get("sens") or "").capitalize() or "—"),
        row("Nominal", f"{_fmt_nominal(deal.get('nominal', 0))} {deal.get('devise', '')}",
            "Contrepartie", deal.get("contrepartie") or "—"),
        row("Date de strike", deal.get("strike_date", "—"),
            "Date de valeur", deal.get("value_date", "—")),
        row("Maturité", deal.get("maturity_date", "—"),
            "Prix de transaction", f"{deal.get('price_traded', 0):.2f}%"),
    ]
    return _tbl(rows, [3.2 * cm, 5.4 * cm, 3.2 * cm, 5.2 * cm])


def _stat_tiles(cells: list[tuple[str, Paragraph]]) -> Table:
    """Row of stat tiles: one flat table, labels row + values row, equal
    columns — nested per-cell tables misaligned the baselines and let the big
    MtM figure overflow its box."""
    n = len(cells)
    labels = [Paragraph(lbl, S_LABEL) for lbl, _ in cells]
    values = [para for _, para in cells]
    t = Table([labels, values], colWidths=[INNER_W / n] * n)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
        ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, C_BORDER),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _headline(data: dict) -> Table:
    deal, mtm = data["deal"], data["mtm"]
    v = mtm["mtm"]
    nominal = deal.get("nominal", 0.0)
    cash = nominal * v
    pt = deal.get("price_traded")
    d_pts = v * 100 - pt if pt is not None else None
    d_cash = nominal * (v - pt / 100.0) if pt is not None else None
    col = C_GREEN if (d_pts or 0) >= 0 else C_RED
    s_val = _sty("v_val17", fontName="Helvetica-Bold", fontSize=13, leading=17)
    s_col = _sty("v_col17", fontName="Helvetica-Bold", fontSize=13, leading=17,
                 textColor=col)
    return _stat_tiles([
        ("MtM — valeur indicative", Paragraph(f"{v * 100:.2f}%", S_BIG)),
        ("Contre-valeur",
         Paragraph(f"{_fmt_nominal(cash)} {deal.get('devise', '')}", s_val)),
        ("Écart vs prix traité",
         Paragraph(f"{'+' if (d_pts or 0) >= 0 else ''}{d_pts:.2f} pts"
                   if d_pts is not None else "—", s_col)),
        ("P&amp;L latent",
         Paragraph(f"{'+' if (d_cash or 0) >= 0 else ''}{_fmt_nominal(d_cash)} "
                   f"{deal.get('devise', '')}" if d_cash is not None else "—", s_col)),
    ])


def _events_table(data: dict) -> Table | None:
    evs = [e for e in (data.get("events") or []) if e.get("t_years", 0) > 0]
    if not evs:
        return None
    cf_by_t: dict[float, float] = {}
    for cf in data["mtm"].get("realized_cash_flows") or []:
        cf_by_t[round(cf["t"], 3)] = cf_by_t.get(round(cf["t"], 3), 0.0) + cf["cf"]
    hdr = [Paragraph(x, S_LABEL) for x in
           ["Date", "Constatation", "Statut", "Flux payé"]]
    rows = [hdr]
    for e in evs:
        cf = cf_by_t.get(round(e.get("t_years", 0.0), 3))
        st = e.get("status", "")
        st_style = _sty(f"st_{st}", fontSize=8.5,
                        textColor=C_GREEN if st in ("observé", "callé")
                        else C_RED if st == "ki"
                        else C_MUTED if st in ("final",)
                        else C_FAINT)
        rows.append([
            Paragraph(e.get("date", ""), S_CELL),
            Paragraph(e.get("label", ""), S_CELL),
            Paragraph(st, st_style),
            Paragraph(f"{cf * 100:.2f}%" if cf is not None else "—", S_CELL_R),
        ])
    return _tbl(rows, [3.0 * cm, 8.0 * cm, 3.0 * cm, 3.0 * cm], header=True)


def _greeks_table(greeks: list) -> Table:
    hdr = [Paragraph(x, S_LABEL) for x in
           ["Sous-jacent", "Delta (+1% de spot)", "Gamma (convexité)",
            "Véga (+1 pt de vol)"]]
    rows = [hdr]
    for g in greeks:
        rows.append([
            Paragraph(g["name"], S_CELL),
            Paragraph(f"{g['delta_pts']:+.2f} pt", S_CELL_R),
            Paragraph(f"{g['gamma_pts']:+.3f}", S_CELL_R),
            Paragraph(f"{g['vega_pts']:+.2f} pt"
                      if g.get("vega_pts") is not None else "—", S_CELL_R),
        ])
    return _tbl(rows, [6.0 * cm, 4.0 * cm, 3.5 * cm, 3.5 * cm], header=True)


def _annex_market_table(mu: dict, uls: list) -> Table:
    hdr = [Paragraph(x, S_LABEL) for x in ["Sous-jacent", "Volatilité σ", "Dividende q"]]
    rows = [hdr]
    for u in uls:
        n = u["name"]
        rows.append([Paragraph(n, S_CELL),
                     Paragraph(f"{mu.get('sigma', {}).get(n, '—')}%", S_CELL_R),
                     Paragraph(f"{mu.get('q', {}).get(n, '—')}%", S_CELL_R)])
    return _tbl(rows, [7.0 * cm, 5.0 * cm, 5.0 * cm], header=True)


# ── Document assembly ──────────────────────────────────────────────────

def generate_valuation_pdf(data: dict) -> bytes:
    """data (plain dict, JSON-serializable except nothing exotic):
    {deal:{...}, mtm:{/mtm payload}, underlyings:[{name,ticker,s0,spot_pct}],
     monitors:[{name,observable,direction,level}], events:[{date,label,status,
     t_years}], history:{dates:[...], series:{name:[norm closes|None]}},
     next_obs_date: str|None}"""
    deal, mtm = data["deal"], data["mtm"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm,
        title=f"Note de valorisation — {deal.get('reference', '')}",
    )
    story = []
    today = datetime.date.today().isoformat()
    _header(story, "Note de valorisation",
            f"{deal.get('reference', '')} — valorisation indicative au {today}")

    # Identification + headline number
    story.append(_id_table(deal, data.get("underlyings") or []))
    story.append(Spacer(1, 10))
    story.append(_headline(data))

    # Life of the product
    ev_tbl = _events_table(data)
    if ev_tbl:
        story.append(Paragraph("Vie du produit", S_SECTION))
        story.append(ev_tbl)

    # Explanation
    story.append(Paragraph("Explication de la valorisation", S_SECTION))
    for line in build_explanation(data):
        story.append(Paragraph("•&nbsp;&nbsp;" + line, S_BODY))
        story.append(Spacer(1, 2))

    # Early-exit call-out — only for capped payoffs whose MtM already captures
    # nearly all of the best possible discounted outcome (deals.py:_EXIT_CAPTURE).
    bc = mtm.get("best_case") or {}
    if bc.get("exit_signal"):
        story.append(Spacer(1, 6))
        callout = Table([[Paragraph(
            f"<b>Opportunité de sortie anticipée</b> — la valeur actuelle du produit "
            f"capture {bc['capture_ratio'] * 100:.1f}% de son meilleur dénouement "
            f"possible. Le potentiel résiduel ({bc['upside_pts']:.2f} point(s), soit "
            f"≈ {bc['upside_annualized_pct']:.1f}% annualisé) est à mettre en regard du "
            f"risque de marché et du risque de crédit conservés jusqu'au dénouement. "
            f"Une sortie au niveau du MtM, suivie d'un réinvestissement aux conditions "
            f"de marché actuelles, peut être envisagée.",
            _sty("v_callout", fontSize=9, textColor=C_AMBER, leading=13.5))]],
            colWidths=[INNER_W])
        callout.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),   # amber-50
            ("BOX", (0, 0), (-1, -1), 0.8, C_AMBER),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(callout)

    # Chart
    img = _chart_history(data)
    if img:
        story.append(Paragraph("Trajectoire des sous-jacents depuis le strike", S_SECTION))
        story.append(img)

    # ── Annex (separate page — can be withheld from the client) ───────
    story.append(PageBreak())
    story.append(Paragraph("Annexe technique", S_SECTION))
    mu = mtm.get("market_used") or {}
    src = ("paramètres de marché figés au booking" if mu.get("source") == "booking"
           else f"paramètres de marché recalibrés (vol réalisée"
                f"{', ' + str(mu.get('window_returns')) + ' rendements quotidiens' if mu.get('window_returns') else ''})")
    model = "Black-Scholes / GBM" if mu.get("model") == "constant" else (mu.get("model") or "—")
    ic = mtm.get("ic95") or [None, None]
    story.append(Paragraph(
        f"Valorisation par simulation Monte Carlo ({mtm.get('n_paths', 0):,} trajectoires"
        .replace(",", " ") +
        f", variables antithétiques) du script de payoff figé au booking, sur la vie "
        f"résiduelle réelle du produit ({mtm.get('T_remaining', 0):.2f} an(s)). L'état "
        f"réalisé du produit (observations passées : {mtm.get('obs_passees', 0)}, extrema "
        f"atteints, coupons mémorisés) est hérité comme condition initiale de la "
        f"simulation. Modèle de diffusion : {model} ; taux d'actualisation : "
        f"{mu.get('r', '—')}% ; {src}.", S_BODY))
    story.append(Spacer(1, 6))
    story.append(_annex_market_table(mu, data.get("underlyings") or []))
    corr = mu.get("corr") or []
    if len(corr) > 1:
        pairs = []
        names = [u["name"] for u in data.get("underlyings") or []]
        for i in range(len(corr)):
            for j in range(i + 1, len(corr)):
                a = names[i] if i < len(names) else str(i)
                b = names[j] if j < len(names) else str(j)
                pairs.append(f"{a}/{b} : {corr[i][j] * 100:.0f}%")
        story.append(Spacer(1, 4))
        story.append(Paragraph("Corrélations : " + " · ".join(pairs), S_BODY))
    gks = data.get("greeks")
    if gks:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "Sensibilités de la valeur (bump-and-reprice sur la vie résiduelle, état "
            "réalisé hérité) — impact en points de MtM :", S_BODY))
        story.append(Spacer(1, 3))
        story.append(_greeks_table(gks))
    story.append(Spacer(1, 6))
    if ic[0] is not None:
        story.append(Paragraph(
            f"Intervalle de confiance à 95% de l'estimateur Monte Carlo : "
            f"[{ic[0] * 100:.2f}% – {ic[1] * 100:.2f}%]. Plus bas réalisé du sous-jacent "
            f"le moins performant depuis le strike : "
            f"{(mtm.get('wof_min_realized') or 0) * 100:.1f}% (clôtures quotidiennes).",
            S_BODY))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_BORDER))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "Document d'information établi à titre purement indicatif. La valorisation "
        "présentée est une estimation à la date indiquée, fondée sur des données de "
        "marché publiques (Yahoo Finance) et un modèle de simulation interne ; elle ne "
        "constitue ni un prix ferme, ni une offre d'achat ou de vente, ni un conseil en "
        "investissement. La valeur de remboursement effective du produit dépendra des "
        "conditions de marché futures et des termes contractuels du produit. "
        f"Généré par Structura le {today}.", S_SMALL))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ── Explain note (P&L waterfall between two dates) ─────────────────────

def _chart_waterfall(res: dict) -> Image:
    """Cumulative waterfall: MtM(d1), one floating bar per effect (green up,
    red down), residual, MtM(d2). Y-axis zoomed on the traversed range."""
    m1, m2 = res["mtm1"] * 100.0, res["mtm2"] * 100.0
    deltas = [(s["label"], s["delta_pts"]) for s in res["steps"]]
    deltas.append(("Résidu", res["residual_pts"]))
    labels = [f"MtM\n{res['date1']}"] + [l.replace("Effet ", "") for l, _ in deltas] \
             + [f"MtM\n{res['date2']}"]

    fig, ax = plt.subplots(figsize=(9.5, 3.8), facecolor="white")
    cums = [m1]
    cum = m1
    for _, d in deltas:
        cum += d
        cums.append(cum)
    lo = min(min(cums), m2) - 1.5
    hi = max(max(cums), m2) + 1.5

    ax.bar(0, m1 - lo, bottom=lo, color="#2563eb", width=0.62)
    ax.annotate(f"{m1:.2f}%", xy=(0, m1), ha="center", va="bottom",
                fontsize=7.5, fontweight="bold", color="#2563eb")
    cum = m1
    for k, (_, d) in enumerate(deltas, start=1):
        bottom = cum if d >= 0 else cum + d
        col = "#059669" if d >= 0 else "#dc2626"
        ax.bar(k, max(abs(d), 0.02), bottom=bottom, color=col, width=0.62)
        ax.plot([k - 1 + 0.31, k - 0.31], [cum, cum],
                color="#94a3b8", linewidth=0.7, linestyle=":")
        ax.annotate(f"{d:+.2f}", xy=(k, max(cum, cum + d)), ha="center",
                    va="bottom", fontsize=7, color=col)
        cum += d
    n_last = len(labels) - 1
    ax.plot([n_last - 1 + 0.31, n_last - 0.31], [cum, cum],
            color="#94a3b8", linewidth=0.7, linestyle=":")
    ax.bar(n_last, m2 - lo, bottom=lo, color="#2563eb", width=0.62)
    ax.annotate(f"{m2:.2f}%", xy=(n_last, m2), ha="center", va="bottom",
                fontsize=7.5, fontweight="bold", color="#2563eb")

    ax.set_ylim(lo, hi + 0.8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.tick_params(colors="#64748b", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#e2e8f0")
    ax.grid(color="#f1f5f9", linewidth=0.5, axis="y")
    ax.set_axisbelow(True)
    ax.set_ylabel("% du nominal", color="#64748b", fontsize=7)
    return _fig_to_image(fig, 17, 6.8)


def _explain_market_table(m1: dict, m2: dict, res: dict, uls: list) -> Table:
    hdr = [Paragraph(x, S_LABEL) for x in
           ["", f"Au {res['date1']}", f"Au {res['date2']}"]]
    rows = [hdr]
    for u in uls:
        n = u["name"]
        rows.append([Paragraph(f"Volatilité {n}", S_CELL),
                     Paragraph(f"{m1.get('sigma', {}).get(n, '—')}%", S_CELL_R),
                     Paragraph(f"{m2.get('sigma', {}).get(n, '—')}%", S_CELL_R)])
    rows.append([Paragraph("Taux d'actualisation", S_CELL),
                 Paragraph(f"{m1.get('r', '—')}%", S_CELL_R),
                 Paragraph(f"{m2.get('r', '—')}%", S_CELL_R)])
    rows.append([Paragraph("Modèle", S_CELL),
                 Paragraph("GBM" if m1.get("model") == "constant" else str(m1.get("model")), S_CELL_R),
                 Paragraph("GBM" if m2.get("model") == "constant" else str(m2.get("model")), S_CELL_R)])
    rows.append([Paragraph("Source des paramètres", S_CELL),
                 Paragraph("booking" if m1.get("source") == "booking" else "vol réalisée", S_CELL_R),
                 Paragraph("booking" if m2.get("source") == "booking" else "vol réalisée", S_CELL_R)])
    return _tbl(rows, [7.0 * cm, 5.0 * cm, 5.0 * cm], header=True)


def generate_explain_pdf(data: dict) -> bytes:
    """P&L explain note: data = {deal:{...}, res:{/mtm/explain payload},
    underlyings:[{name,ticker,spot_pct}], greeks:[...]|None}. Same layout
    language as the valuation note (light palette, French, footer)."""
    deal, res = data["deal"], data["res"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm,
        title=f"Explication de valorisation — {deal.get('reference', '')}",
    )
    story = []
    today = datetime.date.today().isoformat()
    _header(story, "Explication de valorisation",
            f"{deal.get('reference', '')} — du {res['date1']} au {res['date2']}")

    story.append(_id_table(deal, data.get("underlyings") or []))
    story.append(Spacer(1, 10))

    d_col = C_GREEN if res["delta_pts"] >= 0 else C_RED
    p_col = C_GREEN if res["pnl_total_pts"] >= 0 else C_RED
    s13 = dict(fontName="Helvetica-Bold", fontSize=13, leading=17)
    story.append(_stat_tiles([
        (f"MtM au {res['date1']}", Paragraph(f"{res['mtm1'] * 100:.2f}%",
                                             _sty("e_m1", **s13))),
        (f"MtM au {res['date2']}", Paragraph(f"{res['mtm2'] * 100:.2f}%",
                                             _sty("e_m2", **s13))),
        ("Variation de valeur",
         Paragraph(f"{res['delta_pts']:+.2f} pts", _sty("e_d", textColor=d_col, **s13))),
        ("P&amp;L total (avec flux)",
         Paragraph(f"{res['pnl_total_pts']:+.2f} pts", _sty("e_p", textColor=p_col, **s13))),
    ]))

    story.append(Paragraph("Décomposition de la variation", S_SECTION))
    story.append(_chart_waterfall(res))
    story.append(Spacer(1, 4))

    rows = [[Paragraph(x, S_LABEL) for x in ["Effet", "Contribution"]]]
    for s in res["steps"]:
        col = C_GREEN if s["delta_pts"] >= 0 else C_RED
        rows.append([Paragraph(s["label"], S_CELL),
                     Paragraph(f"{s['delta_pts']:+.2f} pt(s)",
                               _sty(f"e_s_{s['label']}", fontSize=8.5, textColor=col,
                                    alignment=TA_RIGHT))])
    rows.append([Paragraph("Résidu (effets croisés)", S_CELL),
                 Paragraph(f"{res['residual_pts']:+.2f} pt(s)", S_CELL_R)])
    if res.get("flows_total_pts"):
        rows.append([Paragraph("Flux détachés sur la période", S_CELL),
                     Paragraph(f"{res['flows_total_pts']:+.2f} pt(s)", S_CELL_R)])
    story.append(_tbl(rows, [11.0 * cm, 6.0 * cm], header=True))

    story.append(Paragraph("Lecture", S_SECTION))
    for line in res.get("phrases") or []:
        story.append(Paragraph("•&nbsp;&nbsp;" + line, S_BODY))
        story.append(Spacer(1, 2))

    # ── Annexe technique ──────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Annexe technique", S_SECTION))
    story.append(Paragraph(
        "Décomposition par réévaluations Monte Carlo successives à graine identique "
        "(Common Random Numbers) : chaque ligne du waterfall change un seul facteur — "
        "calendrier (temps), spots et état path-dependent réalisé (spot), volatilités "
        "(véga), corrélations — en partant de la photo complète du produit à la première "
        "date jusqu'à celle de la seconde. La chaîne est télescopique : la somme des "
        "effets et du résidu reproduit exactement la variation de valeur. Le taux "
        "d'actualisation est maintenu constant (pas de source de taux historiques).",
        S_BODY))
    story.append(Spacer(1, 6))
    story.append(_explain_market_table(res.get("market1") or {}, res.get("market2") or {},
                                       res, data.get("underlyings") or []))
    gks = data.get("greeks")
    if gks:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"Sensibilités de la valeur au {res['date2']} (bump-and-reprice sur la vie "
            f"résiduelle, état réalisé hérité) — impact en points de MtM :", S_BODY))
        story.append(Spacer(1, 3))
        story.append(_greeks_table(gks))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_BORDER))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "Document d'information établi à titre purement indicatif. Les valorisations et "
        "attributions présentées sont des estimations fondées sur des données de marché "
        "publiques (Yahoo Finance) et un modèle de simulation interne ; elles ne "
        "constituent ni un prix ferme, ni une offre d'achat ou de vente, ni un conseil "
        f"en investissement. Généré par Structura le {today}.", S_SMALL))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
