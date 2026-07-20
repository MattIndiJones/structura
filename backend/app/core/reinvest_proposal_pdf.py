"""Note de proposition de réinvestissement (PDF) — un candidat retenu par le
scan Flow B (voir MEMORY investment-solution-module) devient un document
présentant ses caractéristiques économiques, son profil de risque et son
backtest historique. Document interne desk : pas encore pensé pour partir
tel quel chez le client (voir disclaimer en pied de page).

Pure function of a plain-dict `data` payload
(api/deals.py:_reinvest_proposal_data) — même logique que deal_valuation_pdf.py,
module volontairement autonome (pas de helpers partagés entre modules PDF,
même convention que amc_pdf.py/deal_valuation_pdf.py)."""
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
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable,
)

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static",
                          "tp_logo_blue_transparent.png")

C_TEXT   = colors.HexColor("#0f172a")
C_MUTED  = colors.HexColor("#475569")
C_FAINT  = colors.HexColor("#94a3b8")
C_BLUE   = colors.HexColor("#2563eb")
C_RED    = colors.HexColor("#dc2626")
C_BORDER = colors.HexColor("#e2e8f0")
C_CARD   = colors.HexColor("#f8fafc")

W, H = A4
MARGIN = 1.8 * cm
INNER_W = W - 2 * MARGIN


def _sty(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9, textColor=C_TEXT, leading=13)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_TITLE   = _sty("rp_title", fontName="Helvetica-Bold", fontSize=19, leading=24)
S_SUB     = _sty("rp_sub", fontSize=9, textColor=C_MUTED)
S_SECTION = _sty("rp_section", fontName="Helvetica-Bold", fontSize=11, textColor=C_BLUE,
                 leading=15, spaceBefore=13, spaceAfter=5)
S_BODY    = _sty("rp_body", fontSize=9, textColor=C_MUTED, leading=13.5, alignment=TA_JUSTIFY)
S_LABEL   = _sty("rp_label", fontSize=7.5, textColor=C_FAINT)
S_CELL    = _sty("rp_cell", fontSize=8.5, textColor=C_MUTED)
S_VAL     = _sty("rp_val", fontName="Helvetica-Bold", fontSize=13)
S_SMALL   = _sty("rp_small", fontSize=7.5, textColor=C_FAINT, leading=10)


def _logo_image(max_w=3.4 * cm, max_h=0.95 * cm):
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
                    "Structura — document de travail interne, ne constitue pas une offre")
    canv.drawRightString(W - MARGIN, 0.85 * cm, f"Page {canv.getPageNumber()}")
    canv.restoreState()


def _fig_to_image(fig, width_cm=17.0, height_cm=7.0) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    plt.close(fig)
    return Image(buf, width=width_cm * cm, height=height_cm * cm)


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


def _stat_tiles(cells: list[tuple[str, str]]) -> Table:
    n = len(cells)
    labels = [Paragraph(lbl, S_LABEL) for lbl, _ in cells]
    values = [Paragraph(val, S_VAL) for _, val in cells]
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


def _chart_backtest_history(history: dict, ticker: str, product: dict | None = None) -> Image | None:
    """Trajectoire du sous-jacent, annotée avec les barrières et les dates de
    flux réels de la fenêtre de replay la plus récente (product), recalées
    sur la MÊME base 100 que ce graphique (celle du début de tout
    l'historique récupéré) — voir _reinvest_proposal_data pour le recalage.

    Volontairement UN SEUL graphique, pas un second "trajectoire du produit"
    séparé : en mono-sous-jacent le worst-of EST le sous-jacent, une courbe
    à part ne ferait que redupliquer la queue de celle-ci à un autre point de
    rebasage (voir MEMORY investment-solution-module)."""
    dates = history.get("dates") or []
    series = history.get("normalized") or []
    if not dates or not series:
        return None
    date_idx = {d: i for i, d in enumerate(dates)}

    fig, ax = plt.subplots(figsize=(9.5, 4.2), facecolor="white")
    ax.set_facecolor("white")
    y = np.array([v if v is not None else np.nan for v in series], dtype=float) * 100.0
    ax.plot(range(len(y)), y, linewidth=1.2, color="#2563eb", label=ticker)
    ax.axhline(100.0, color="#94a3b8", linewidth=0.8, linestyle=":")

    if product:
        for b in product.get("barriers") or []:
            lvl = b.get("level")
            if lvl is None:
                continue
            col = "#059669" if b.get("direction") == "up" else "#dc2626"
            ax.axhline(lvl * 100.0, color=col, linewidth=1.0, linestyle="--", alpha=0.8)
            ax.annotate(f"{b.get('name', '')} {lvl * 100:.0f}%", xy=(0.01, lvl * 100.0),
                        xycoords=("axes fraction", "data"), fontsize=6.5, color=col, va="bottom")
        ws = product.get("window_start")
        if ws in date_idx:
            ax.axvline(date_idx[ws], color="#0f172a", linewidth=0.9, alpha=0.5)
            ax.annotate("départ replay", xy=(date_idx[ws], 1.0), xycoords=("data", "axes fraction"),
                        fontsize=6.5, color="#0f172a", ha="left", va="bottom")
        for cf in product.get("cash_flows") or []:
            idx = date_idx.get(cf.get("date"))
            if idx is not None:
                ax.plot(idx, y[idx], marker="o", markersize=5, color="#f59e0b", zorder=5)

    ax.tick_params(colors="#64748b", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#e2e8f0")
    ax.grid(color="#f1f5f9", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_ylabel("Niveau (base 100 au début de l'historique)", color="#64748b", fontsize=7)
    n = len(dates)
    step = max(1, n // 8)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=20, ha="right", fontsize=6.5)
    ax.legend(fontsize=7, framealpha=0, labelcolor="#475569", loc="best")
    return _fig_to_image(fig, 17, 7.0)


def _chart_window_irr(windows: list) -> Image | None:
    """TRI par fenêtre de backtest, alignées sur les mêmes dates que le
    graphique de prix — permet de vérifier visuellement où le produit se
    fait rappeler/perd du capital plutôt que de ne juger que sur les stats
    agrégées (médiane/moyenne peuvent masquer un régime d'historique
    fortement chevauchant, voir MEMORY investment-solution-module)."""
    if not windows:
        return None
    dates = [w["start_date"] for w in windows]
    irrs = [w["irr"] * 100.0 for w in windows]
    colors_ = ["#059669" if v >= 0 else "#dc2626" for v in irrs]
    fig, ax = plt.subplots(figsize=(9.5, 3.2), facecolor="white")
    ax.set_facecolor("white")
    ax.bar(range(len(irrs)), irrs, color=colors_, width=0.8)
    ax.axhline(0.0, color="#94a3b8", linewidth=0.8)
    ax.tick_params(colors="#64748b", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#e2e8f0")
    ax.grid(color="#f1f5f9", linewidth=0.5, axis="y")
    ax.set_axisbelow(True)
    ax.set_ylabel("TRI par fenêtre (%)", color="#64748b", fontsize=7)
    n = len(dates)
    step = max(1, n // 8)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=20, ha="right", fontsize=6.5)
    return _fig_to_image(fig, 17, 5.2)


def _fmt_param(value: float, is_pct: bool) -> str:
    return f"{value * 100:.3f}%" if is_pct else f"{value:.4f}"


def generate_reinvest_proposal_pdf(data: dict) -> bytes:
    """data: {deal:{reference,product_type,sens,devise,nominal},
    candidate:{ticker,name,sigma,q,param_name,solved_param,price,ki_pct,
    autocall_pct,capital_loss_pct,full_coupon_pct}, param_desc, param_is_pct,
    T, value_date, maturity_date, backtest:{stats,history,error?}}"""
    deal, cand = data["deal"], data["candidate"]
    is_pct = data.get("param_is_pct", True)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm,
        title=f"Proposition de réinvestissement — {deal.get('reference', '')}",
    )
    story = []
    today = datetime.date.today().isoformat()
    _header(story, "Proposition de réinvestissement",
            f"Alternative à {deal.get('reference', '')} — {today}")

    def row(l1, v1, l2, v2):
        return [Paragraph(l1, S_LABEL), Paragraph(v1, S_CELL),
                Paragraph(l2, S_LABEL), Paragraph(v2, S_CELL)]

    id_rows = [
        row("Produit d'origine", deal.get("reference", "—"),
            "Type", deal.get("product_type") or "Produit structuré"),
        row("Nouveau sous-jacent proposé", f"{cand['name']} ({cand['ticker']})",
            "Sens", (deal.get("sens") or "").capitalize() or "—"),
        row("Nominal", f"{deal.get('nominal', 0):,.0f} {deal.get('devise', '')}".replace(",", " "),
            "Maturité", f"{data['T']:.2f} an(s)"),
        row("Value date", data.get("value_date", "—"),
            "Échéance", data.get("maturity_date", "—")),
    ]
    story.append(_tbl(id_rows, [4.0 * cm, 4.8 * cm, 3.6 * cm, 4.8 * cm]))
    story.append(Spacer(1, 10))

    story.append(_stat_tiles([
        (data.get("param_desc", cand["param_name"]), _fmt_param(cand["solved_param"], is_pct)),
        ("Prix atteint", f"{cand['price'] * 100:.2f}%"),
        ("Volatilité utilisée", f"{cand['sigma'] * 100:.1f}%"),
        ("Dividende utilisé", f"{cand['q'] * 100:.1f}%"),
    ]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Profil de risque simulé", S_SECTION))
    story.append(_stat_tiles([
        ("P(KI)", f"{cand['ki_pct']:.1f}%"),
        ("P(autocall anticipé)", f"{cand['autocall_pct']:.1f}%"),
        ("P(perte nette)", f"{cand['capital_loss_pct']:.1f}%"),
        ("P(scénario optimal)", f"{cand['full_coupon_pct']:.1f}%"),
    ]))
    story.append(Paragraph(
        "Perte nette = probabilité que le payoff actualisé soit inférieur au prix "
        "cible de cette proposition. KI/autocall ne sont significatifs que si le "
        "produit a effectivement ce mécanisme.", S_SMALL))

    bt = data.get("backtest") or {}
    story.append(Paragraph("Backtest historique", S_SECTION))
    if bt.get("error") or not bt.get("stats"):
        story.append(Paragraph(f"Backtest indisponible : {bt.get('error', 'données insuffisantes')}.", S_BODY))
    else:
        st = bt["stats"]
        bt_rows = [
            [Paragraph("TRI médian", S_LABEL), Paragraph("TRI moyen", S_LABEL),
             Paragraph("P10 / pire", S_LABEL), Paragraph("% positif", S_LABEL),
             Paragraph("% rappel anticipé", S_LABEL), Paragraph("Fenêtres", S_LABEL)],
            [Paragraph(f"{st['median_irr'] * 100:.2f}%", S_CELL),
             Paragraph(f"{st['mean_irr'] * 100:.2f}%", S_CELL),
             Paragraph(f"{st['p10_irr'] * 100:.2f}% / {st['worst_irr'] * 100:.2f}%", S_CELL),
             Paragraph(f"{st['pct_positive']:.1f}%", S_CELL),
             Paragraph(f"{st['early_recall_pct']:.1f}%", S_CELL),
             Paragraph(str(st["n_windows"]), S_CELL)],
        ]
        story.append(_tbl(bt_rows, [2.7 * cm] * 6, header=True))
        story.append(Spacer(1, 8))
        prod = bt.get("product")
        img = _chart_backtest_history(bt.get("history") or {}, cand["ticker"], prod)
        if img:
            story.append(Paragraph(f"Trajectoire de {cand['ticker']}", S_SECTION))
            story.append(img)
            if prod:
                story.append(Paragraph(
                    f"Barrières et flux effectivement versés (point ambre) de la fenêtre de replay la "
                    f"plus récente (départ {prod.get('window_start', '—')}), recalés sur la base 100 de "
                    "cet historique complet.", S_SMALL))
        img2 = _chart_window_irr(st.get("windows") or [])
        if img2:
            story.append(Paragraph("TRI réalisé par fenêtre de backtest", S_SECTION))
            story.append(img2)
            story.append(Paragraph(
                "Fenêtres glissantes rapprochées sur une maturité pluriannuelle — des "
                "fenêtres voisines partagent l'essentiel de leur historique et ne "
                "constituent pas des observations indépendantes ; à lire comme une "
                "trajectoire, pas comme un échantillon i.i.d.", S_SMALL))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_BORDER))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "Document de travail interne établi à titre indicatif à partir de données de "
        "marché publiques (Yahoo Finance — volatilité historique, pas de vol implicite) "
        "et d'un modèle de simulation interne. Il ne constitue ni un prix ferme, ni une "
        "offre, ni un conseil en investissement, et n'a pas vocation à être transmis "
        f"tel quel à un client sans validation du desk. Généré par Structura le {today}.",
        S_SMALL))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
