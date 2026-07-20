"""Professional PDF export for AMC Fama-French analysis reports."""
from __future__ import annotations

import io
import math
import datetime
import os
from typing import Any

# Blue logo (transparent bg) — designed for dark backgrounds
_LOGO_PATH      = os.path.join(os.path.dirname(__file__), "..", "static", "tp_logo_blue_transparent.png")
# Icon-only crop of the blue logo — for compact spaces (footers)
_LOGO_ICON_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "tp_logo_blue_icon.png")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

# ── Colour palette ─────────────────────────────────────────────────────
C_BG        = colors.HexColor("#0f172a")   # slate-950
C_CARD      = colors.HexColor("#1e293b")   # slate-800
C_BORDER    = colors.HexColor("#334155")   # slate-700
C_BLUE      = colors.HexColor("#3b82f6")   # blue-500
C_EMERALD   = colors.HexColor("#10b981")   # emerald-500
C_AMBER     = colors.HexColor("#f59e0b")   # amber-500
C_RED       = colors.HexColor("#ef4444")   # red-500
C_TEXT      = colors.HexColor("#f1f5f9")   # slate-100
C_MUTED     = colors.HexColor("#94a3b8")   # slate-400
C_FAINT     = colors.HexColor("#475569")   # slate-600
C_WHITE     = colors.white

W, H        = A4
MARGIN      = 1.8 * cm
INNER_W     = W - 2 * MARGIN

FACTOR_COLORS = ["#60a5fa","#34d399","#f59e0b","#f472b6","#a78bfa","#fb923c"]


# ── Styles ─────────────────────────────────────────────────────────────
def _sty(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9, textColor=C_TEXT,
                leading=13, spaceAfter=0, spaceBefore=0)
    base.update(kw)
    return ParagraphStyle(name, **base)

S_TITLE   = _sty("title",  fontName="Helvetica-Bold", fontSize=22, textColor=C_WHITE,
                 leading=28, spaceAfter=4)
S_SECTION = _sty("section",fontName="Helvetica-Bold", fontSize=11, textColor=C_BLUE,
                 leading=15, spaceBefore=14, spaceAfter=6)
S_BODY    = _sty("body",   fontSize=8.5, textColor=C_MUTED, leading=12)
S_SMALL   = _sty("small",  fontSize=7.5, textColor=C_FAINT, leading=10)
S_CENTER  = _sty("center", alignment=TA_CENTER, fontSize=8.5, textColor=C_MUTED)
S_NUM     = _sty("num",    fontName="Helvetica-Bold", alignment=TA_RIGHT,
                 fontSize=8.5, textColor=C_TEXT)
S_NUM_SM  = _sty("numsm",  alignment=TA_RIGHT, fontSize=8, textColor=C_MUTED)
S_LABEL   = _sty("label",  fontSize=8, textColor=C_FAINT)
S_WARN    = _sty("warn",   fontSize=7.5, textColor=C_AMBER, leading=11)
S_HDR     = _sty("hdr",    fontName="Helvetica-Bold", fontSize=8, textColor=C_FAINT,
                 alignment=TA_RIGHT)
S_JUST    = _sty("just",   fontSize=8.5, textColor=C_MUTED, leading=13,
                 alignment=TA_JUSTIFY)


class ColorRect(Flowable):
    """Filled rectangle used as divider / background."""
    def __init__(self, w, h, color, radius=0):
        super().__init__()
        self.w, self.h, self.color, self.radius = w, h, color, radius
    def draw(self):
        self.canv.setFillColor(self.color)
        if self.radius:
            self.canv.roundRect(0, 0, self.w, self.h, self.radius, fill=1, stroke=0)
        else:
            self.canv.rect(0, 0, self.w, self.h, fill=1, stroke=0)
    def wrap(self, *_): return self.w, self.h


# ── Matplotlib helpers ─────────────────────────────────────────────────
def _fig_to_image(fig, width_cm=17, height_cm=6) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return Image(buf, width=width_cm * cm, height=height_cm * cm)


def _dark_axes(ax, fig=None):
    BG = "#0f172a"
    if fig:
        fig.patch.set_facecolor(BG)
    ax.set_facecolor("#1e293b")
    ax.tick_params(colors="#64748b", labelsize=7)
    ax.xaxis.label.set_color("#64748b")
    ax.yaxis.label.set_color("#64748b")
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")
    ax.grid(color="#1e293b", linewidth=0.5, which="both")
    ax.set_axisbelow(True)


def _chart_performance(perf: dict, benchmark: str) -> Image:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 5.5),
                                    gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
                                    facecolor="#0f172a")
    dates = perf.get("dates", [])
    cum   = [v * 100 for v in perf.get("cum_amc", [])]
    dd    = [v * 100 for v in perf.get("drawdown", [])]
    cum_bm = [v * 100 for v in perf.get("cum_bm", [])]

    _dark_axes(ax1)
    _dark_axes(ax2)

    if dates and cum:
        ax1.plot(dates, cum, color="#60a5fa", linewidth=1.6, label="AMC")
        ax1.fill_between(dates, cum, alpha=0.06, color="#60a5fa")
        ax1.axhline(0, color="#334155", linewidth=0.8)
        if cum_bm:
            ax1.plot(dates, cum_bm, color="#f59e0b", linewidth=1.2,
                     linestyle="--", label=benchmark, alpha=0.85)
        ax1.set_ylabel("Rendement cumulé (%)", color="#64748b", fontsize=7)
        ax1.tick_params(labelbottom=False)
        ax1.legend(fontsize=7, framealpha=0, labelcolor="#94a3b8")
        # Show only a subset of x labels
        n = len(dates)
        step = max(1, n // 6)
        ax1.set_xticks(range(0, n, step))
        ax1.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=20, ha="right")

    if dates and dd:
        ax2.fill_between(range(len(dates)), dd, alpha=0.5, color="#ef4444")
        ax2.plot(range(len(dates)), dd, color="#ef4444", linewidth=1)
        ax2.set_ylabel("Drawdown (%)", color="#64748b", fontsize=7)
        n = len(dates)
        step = max(1, n // 6)
        ax2.set_xticks(range(0, n, step))
        ax2.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=20, ha="right")

    fig.patch.set_facecolor("#0f172a")
    return _fig_to_image(fig, 17, 8.5)


def _chart_rolling(rolling: list, factors: list) -> Image:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 5.5),
                                    gridspec_kw={"height_ratios": [3, 1.5], "hspace": 0.1},
                                    facecolor="#0f172a")
    _dark_axes(ax1)
    _dark_axes(ax2)

    dates = [r["date"] for r in rolling]
    n = len(dates)

    for i, f in enumerate(factors[:5]):
        vals = [r.get(f) for r in rolling]
        vals = [v if v is not None else float("nan") for v in vals]
        ax1.plot(vals, color=FACTOR_COLORS[i % len(FACTOR_COLORS)],
                 linewidth=1.4, label=f, alpha=0.9)

    ax1.axhline(0, color="#334155", linewidth=0.8)
    ax1.set_ylabel("Beta glissant", color="#64748b", fontsize=7)
    ax1.legend(fontsize=7, framealpha=0, labelcolor="#94a3b8", ncol=3)
    ax1.tick_params(labelbottom=False)

    r2_vals = [r.get("r2", 0) * 100 for r in rolling]
    ax2.fill_between(range(n), r2_vals, alpha=0.4, color="#a78bfa")
    ax2.plot(r2_vals, color="#a78bfa", linewidth=1.3)
    ax2.set_ylabel("R² glissant (%)", color="#64748b", fontsize=7)
    ax2.set_ylim(0, 100)

    step = max(1, n // 6)
    for ax in [ax2]:
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=20, ha="right")

    fig.patch.set_facecolor("#0f172a")
    return _fig_to_image(fig, 17, 8.5)


def _chart_dependency_gauge(score: int, level: str) -> Image:
    fig, ax = plt.subplots(figsize=(3.5, 2.2), facecolor="#0f172a",
                           subplot_kw={"aspect": "equal"})
    ax.set_facecolor("#0f172a")
    ax.axis("off")

    # Background arc
    theta = np.linspace(np.pi, 0, 200)
    ax.plot(np.cos(theta), np.sin(theta), color="#1e293b", linewidth=14, solid_capstyle="round")
    # Filled arc
    frac   = score / 100
    color  = "#10b981" if score < 45 else "#f59e0b" if score < 70 else "#ef4444"
    theta2 = np.linspace(np.pi, np.pi - frac * np.pi, 200)
    ax.plot(np.cos(theta2), np.sin(theta2), color=color, linewidth=14, solid_capstyle="round")
    # Score text
    ax.text(0, -0.05, str(score), ha="center", va="center",
            fontsize=28, fontweight="bold", color=color, fontfamily="monospace")
    ax.text(0, -0.42, "/100", ha="center", va="center", fontsize=9, color="#64748b")
    ax.text(0, -0.72, level, ha="center", va="center", fontsize=8,
            color=color, fontweight="bold")
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.9, 1.1)
    fig.patch.set_facecolor("#0f172a")
    return _fig_to_image(fig, 6, 4)


def _chart_exposures(sectors: list, countries: list, currencies: list) -> Image | None:
    datasets = [(sectors, "Secteurs"), (countries, "Pays"), (currencies, "Devises")]
    datasets = [(d, l) for d, l in datasets if d]
    if not datasets:
        return None

    n = len(datasets)
    fig, axes = plt.subplots(1, n, figsize=(9.5, 3.5), facecolor="#0f172a")
    if n == 1:
        axes = [axes]

    for ax, (data, label) in zip(axes, datasets):
        ax.set_facecolor("#0f172a")
        ax.axis("off")
        names   = [d["name"] for d in data[:8]]
        weights = [d["weight"] * 100 for d in data[:8]]
        palette = plt.cm.Blues(np.linspace(0.35, 0.85, len(names)))
        wedges, texts, autotexts = ax.pie(
            weights, labels=None, autopct="%1.0f%%",
            colors=palette, startangle=90,
            pctdistance=0.75, wedgeprops={"linewidth": 0.5, "edgecolor": "#0f172a"},
        )
        for at in autotexts:
            at.set_color("white"); at.set_fontsize(6.5)
        ax.legend(names, loc="lower center", fontsize=6, framealpha=0,
                  labelcolor="#94a3b8", ncol=1, bbox_to_anchor=(0.5, -0.25))
        ax.set_title(label, color="#94a3b8", fontsize=8, pad=6)

    fig.patch.set_facecolor("#0f172a")
    return _fig_to_image(fig, 17, 5.5)


# ── Table helpers ──────────────────────────────────────────────────────
def _tbl(data, col_widths, style_extra=None):
    ts = TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  C_CARD),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  C_FAINT),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_BG, colors.HexColor("#111827")]),
        ("LINEBELOW",   (0, 0), (-1, 0),  0.5, C_BORDER),
        ("LINEBELOW",   (0, 1), (-1, -2), 0.3, colors.HexColor("#1e293b")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0,0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])
    if style_extra:
        for s in style_extra:
            ts.add(*s)
    return Table(data, colWidths=col_widths, style=ts, repeatRows=1)


def _p(text, style=None): return Paragraph(str(text), style or S_BODY)
def _pn(text, style=None): return Paragraph(str(text), style or S_NUM)


def _sig(p):
    if p is None: return ""
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.10:  return "·"
    return ""


def _pfmt(p) -> str:
    """Format p-value for display, handling very small values that round to 0."""
    if p is None: return "—"
    if p < 0.0001: return "<0.0001"
    return f"{p:.4f}"


def _pval_safe(raw) -> float:
    """Return a p-value safe for `or`-chaining: maps None/missing → 1.0, keeps 0.0 as-is."""
    return raw if raw is not None else 1.0


def _pct(v, dec=1):
    if v is None: return "—"
    return f"{v:+.{dec}f}%" if isinstance(v, float) else f"{v}%"


def _kpi_row(items, n_cols=None):
    """Flexible KPI block: [(label, value, color), ...], n_cols defaults to len(items).

    Uses zero outer padding so each inner card gets exactly INNER_W/n width — guaranteeing
    visually equal column widths regardless of value length.
    """
    n = n_cols or max(len(items), 1)
    col_w = INNER_W / n
    val_size = 20 if n <= 4 else (16 if n == 5 else 13)
    cell_data = []
    for label, val, col in items:
        # Normalise newlines → <br/> so ReportLab renders them as actual line breaks
        lbl_html = label.replace("\n", "<br/>")
        cell_data.append(
            Table([[Paragraph(str(val),
                              ParagraphStyle(f"kv{n}_{id(val)}", fontName="Helvetica-Bold",
                                             fontSize=val_size,
                                             textColor=colors.HexColor(col),
                                             alignment=TA_CENTER,
                                             leading=val_size + 4))],
                   [Paragraph(lbl_html, S_CENTER)]],
                  colWidths=[col_w],
                  style=TableStyle([
                      ("ALIGN",          (0,0), (-1,-1), "CENTER"),
                      ("BACKGROUND",     (0,0), (-1,-1), C_CARD),
                      ("TOPPADDING",     (0,0), (-1,-1), 12),
                      ("BOTTOMPADDING",  (0,0), (-1,-1), 12),
                      ("LEFTPADDING",    (0,0), (-1,-1), 4),
                      ("RIGHTPADDING",   (0,0), (-1,-1), 4),
                      ("BOX",            (0,0), (-1,-1), 0.5, C_BORDER),
                  ]))
        )
    while len(cell_data) < n:
        cell_data.append(Table([[Paragraph("", S_CENTER)]], colWidths=[col_w],
                               style=TableStyle([("BACKGROUND", (0,0), (-1,-1), C_BG)])))
    # Zero outer padding → columns are exactly col_w, no uneven shrinkage
    return Table([cell_data], colWidths=[col_w] * n,
                 style=TableStyle([
                     ("LEFTPADDING",   (0,0), (-1,-1), 0),
                     ("RIGHTPADDING",  (0,0), (-1,-1), 0),
                     ("TOPPADDING",    (0,0), (-1,-1), 0),
                     ("BOTTOMPADDING", (0,0), (-1,-1), 0),
                 ]))


# ── Page template ──────────────────────────────────────────────────────
def _on_page(canvas, doc):
    """Legacy header/footer for the single-block FF analysis PDF."""
    canvas.saveState()
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(C_BLUE)
    canvas.rect(0, H - 1.2*cm, W, 1.2*cm, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN, H - 0.75*cm, "STRUCTURA  ·  Analyse Fama-French AMC")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#bfdbfe"))
    canvas.drawRightString(W - MARGIN, H - 0.75*cm,
                           datetime.datetime.now().strftime("%d/%m/%Y"))
    canvas.setFillColor(C_CARD)
    canvas.rect(0, 0, W, 1*cm, fill=1, stroke=0)
    canvas.setFillColor(C_FAINT)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, 0.35*cm,
        "Document généré par Structura — Usage interne uniquement.")
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(W - MARGIN, 0.35*cm, f"Page {doc.page}")
    canvas.restoreState()


def _make_study_page(company: str, client: str):
    """Returns onLaterPages callback for the study PDF (pages 2+)."""
    def _cb(canvas, doc):
        canvas.saveState()
        # Background
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        # Header bar
        canvas.setFillColor(colors.HexColor("#0f2441"))
        canvas.rect(0, H - 1.2*cm, W, 1.2*cm, fill=1, stroke=0)
        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(MARGIN, H - 0.72*cm, company)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#93c5fd"))
        canvas.drawCentredString(W / 2, H - 0.72*cm, "Analyse AMC — Étude de Gestion")
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawRightString(W - MARGIN, H - 0.72*cm,
                               datetime.datetime.now().strftime("%d/%m/%Y"))
        # Footer bar
        canvas.setFillColor(colors.HexColor("#0f172a"))
        canvas.rect(0, 0, W, 0.9*cm, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#1e3a5f"))
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, 0.9*cm, W - MARGIN, 0.9*cm)
        if os.path.exists(_LOGO_PATH):
            _fw = 0.7 * cm     # square logo in footer
            _fy = (0.9*cm - _fw) / 2
            canvas.drawImage(_LOGO_PATH, MARGIN, _fy, width=_fw, height=_fw,
                             preserveAspectRatio=True, mask='auto')
            _txt_x = MARGIN + _fw + 0.12*cm
        else:
            _txt_x = MARGIN
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(_txt_x, 0.32*cm, company)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.setFillColor(colors.HexColor("#dc2626"))
        canvas.drawCentredString(W / 2, 0.32*cm, f"CONFIDENTIEL — {client}")
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawRightString(W - MARGIN, 0.32*cm, f"Page {doc.page - 1}")
        canvas.restoreState()
    return _cb


def _draw_study_cover(meta: dict, company: str, client: str):
    """Returns onFirstPage callback that renders the full cover page."""
    prod  = meta.get("product_name", "AMC")
    isin  = meta.get("isin", "")
    theme = meta.get("theme", "")
    ccy   = meta.get("currency", "")
    # Fallback: also check meta dict in case client wasn't passed at endpoint level
    if not client or client == "—":
        client = meta.get("client_name", "") or "—"
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    nav_s = meta.get("nav_start_value")
    nav_c = meta.get("nav_current_value")
    perf_str = "—"
    if nav_s and nav_c and nav_s != 0:
        pv = (nav_c / nav_s - 1) * 100
        perf_str = f"{pv:+.2f}%"

    def _cover(canvas, doc):
        canvas.saveState()
        # Full dark background
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)

        # Top band — company identity
        canvas.setFillColor(colors.HexColor("#0f2441"))
        canvas.rect(0, H - 5.5*cm, W, 5.5*cm, fill=1, stroke=0)
        # Blue accent line at bottom of band
        canvas.setFillColor(C_BLUE)
        canvas.rect(0, H - 5.5*cm, W, 0.25*cm, fill=1, stroke=0)

        # Cover header: logo (square) + company name, group centered on page
        # Logo is 1254×1254 square — display at 2.4cm to stay compact next to text
        _icon_sz  = 2.4 * cm
        _gap      = 0.5 * cm
        _txt_w    = 9.2 * cm      # estimated width of "TP Advisory Services" at pt 26
        _group_w  = _icon_sz + _gap + _txt_w
        _group_x  = W / 2 - _group_w / 2

        # Vertical: text baseline H-2.6cm; cap height ≈ 0.92cm → mid at H-2.14cm
        _txt_base = H - 2.6 * cm
        _txt_mid  = _txt_base + 0.46 * cm
        _icon_y   = _txt_mid - _icon_sz / 2

        if os.path.exists(_LOGO_PATH):
            canvas.drawImage(_LOGO_PATH, _group_x, _icon_y,
                             width=_icon_sz, height=_icon_sz,
                             preserveAspectRatio=True, mask='auto')
            _name_x = _group_x + _icon_sz + _gap
        else:
            _name_x = None

        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 26)
        if _name_x:
            canvas.drawString(_name_x, _txt_base, company)
        else:
            canvas.drawCentredString(W / 2, _txt_base, company)

        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.HexColor("#93c5fd"))
        canvas.drawCentredString(W / 2, H - 3.3*cm, "Analyse & Conseil en Gestion d'Actifs")

        # Main title block (center of page)
        cy = H * 0.56
        canvas.setFont("Helvetica-Bold", 30)
        canvas.setFillColor(C_WHITE)
        canvas.drawCentredString(W / 2, cy, "Étude de Gestion AMC")
        canvas.setFont("Helvetica", 13)
        canvas.setFillColor(C_BLUE)
        canvas.drawCentredString(W / 2, cy - 1.1*cm,
                                 "Analyse de performance et comportement du gérant")

        # Separator
        canvas.setStrokeColor(colors.HexColor("#1e3a5f"))
        canvas.setLineWidth(0.8)
        canvas.line(MARGIN + 2*cm, cy - 1.8*cm, W - MARGIN - 2*cm, cy - 1.8*cm)

        # Product info card — width adapts to title length
        _BP   = 1.2 * cm         # horizontal padding from inner margin
        box_y = H * 0.26
        box_h = 5.0 * cm
        box_x = MARGIN + _BP
        box_w = INNER_W - 2 * _BP
        canvas.setFillColor(colors.HexColor("#111827"))
        canvas.roundRect(box_x, box_y, box_w, box_h, 6, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#1e3a5f"))
        canvas.setLineWidth(0.4)
        canvas.roundRect(box_x, box_y, box_w, box_h, 6, fill=0, stroke=1)

        # Title font size: reduce until title fits within box (with 0.6cm margin each side)
        _max_title_w = box_w - 1.2 * cm
        _title_fs = 12
        for _fs in range(12, 7, -1):
            if canvas.stringWidth(prod, "Helvetica-Bold", _fs) <= _max_title_w:
                _title_fs = _fs
                break

        # If still too long at 8pt, split into two lines at midpoint space
        _title_lines = [prod]
        if canvas.stringWidth(prod, "Helvetica-Bold", _title_fs) > _max_title_w:
            words = prod.split()
            mid = len(words) // 2
            _title_lines = [" ".join(words[:mid]), " ".join(words[mid:])]
            _title_fs = 10

        canvas.setFont("Helvetica-Bold", _title_fs)
        canvas.setFillColor(C_TEXT)
        _n = len(_title_lines)
        _line_h = _title_fs / 72 * 2.54 * cm * 1.3   # line height in points→cm
        _title_top = box_y + box_h - 0.7 * cm
        for _i, _line in enumerate(_title_lines):
            canvas.drawCentredString(W / 2, _title_top - _i * _line_h, _line)

        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(C_MUTED)
        canvas.drawCentredString(W / 2, box_y + box_h - 1.8*cm,
                                 f"ISIN : {isin}  ·  Devise : {ccy}  ·  {theme}")

        canvas.setFillColor(colors.HexColor("#1e3a5f"))
        canvas.rect(box_x + 0.4*cm, box_y + 1.55*cm, box_w - 0.8*cm, 0.25, fill=1, stroke=0)

        _lx = box_x + 0.6*cm
        _rx = box_x + box_w - 0.6*cm
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.setFillColor(colors.HexColor("#60a5fa"))
        canvas.drawString(_lx, box_y + 1.1*cm,
                          f"Préparé pour :  {client}")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_FAINT)
        canvas.drawRightString(_rx, box_y + 1.1*cm,
                               f"Performance totale : {perf_str}")

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_FAINT)
        canvas.drawCentredString(W / 2, box_y + 0.5*cm,
                                 f"Date de rapport : {date_str}")

        # Confidential footer box
        canvas.setFillColor(colors.HexColor("#1c0a0a"))
        canvas.roundRect(MARGIN, 1.8*cm, INNER_W, 1.2*cm, 4, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#7f1d1d"))
        canvas.setLineWidth(0.4)
        canvas.roundRect(MARGIN, 1.8*cm, INNER_W, 1.2*cm, 4, fill=0, stroke=1)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#ef4444"))
        canvas.drawCentredString(W / 2, 2.65*cm, "DOCUMENT CONFIDENTIEL")
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#9ca3af"))
        canvas.drawCentredString(W / 2, 2.1*cm,
            f"Destiné exclusivement à {client}. "
            "Toute reproduction ou diffusion est strictement interdite.")

        canvas.restoreState()
    return _cover


# ── Main export function ───────────────────────────────────────────────
def generate_pdf(result: dict, meta: dict | None = None) -> bytes:
    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.6*cm, bottomMargin=1.4*cm,
    )
    story  = []

    perf    = result.get("performance", {})
    reg     = result.get("regression", {})
    rolling = result.get("rolling", [])
    act     = result.get("activity", {})
    conc    = result.get("concentration", {})
    dep     = result.get("dependency_score", {})
    period  = result.get("period", {})
    factors = result.get("factors_used", [])
    warns   = result.get("warnings", [])
    ff_ser  = result.get("ff_series", "")
    bm      = result.get("benchmark", "")
    prod    = (meta or {}).get("product_name", "AMC") if meta else "AMC"
    isin    = (meta or {}).get("isin", "") if meta else ""

    def space(h=6): return Spacer(1, h)

    # ══════════════════════════════════════════════════════════════════
    # PAGE 1 — COVER + EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════════════
    story.append(space(18))
    story.append(Paragraph("Analyse Fama-French", S_TITLE))
    story.append(Paragraph("AMC — Dépendance au Gérant &amp; Décomposition Factorielle",
                           _sty("sub", fontSize=13, textColor=C_MUTED, leading=18)))
    story.append(space(8))
    story.append(HRFlowable(INNER_W, thickness=1, color=C_BLUE))
    story.append(space(10))

    # Product info block
    info_data = [
        [_p("Produit", S_LABEL),   _p(prod, _sty("pv", fontName="Helvetica-Bold", fontSize=9, textColor=C_TEXT))],
        [_p("ISIN", S_LABEL),      _p(isin or "—", S_BODY)],
        [_p("Série FF", S_LABEL),  _p(ff_ser, S_BODY)],
        [_p("Benchmark", S_LABEL), _p(bm, S_BODY)],
        [_p("Période analysée", S_LABEL),
         _p(f"{period.get('overlap_start','?')} → {period.get('overlap_end','?')} "
            f"({period.get('n_obs','?')} observations)", S_BODY)],
        [_p("Facteurs", S_LABEL),  _p("  ·  ".join(factors), S_BODY)],
        [_p("Généré le", S_LABEL), _p(datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), S_BODY)],
    ]
    tbl_info = Table(info_data, colWidths=[3.5*cm, INNER_W - 3.5*cm],
        style=TableStyle([
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_BG, colors.HexColor("#111827")]),
            ("LINEBELOW",(0,0),(-1,-2),0.3, C_BORDER),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),
            ("RIGHTPADDING",(0,0),(-1,-1),8),
            ("BOX",(0,0),(-1,-1),0.5,C_BORDER),
        ]))
    story.append(tbl_info)
    story.append(space(14))

    # Warnings
    if warns:
        for w in warns:
            story.append(Paragraph(f"⚠  {w}", S_WARN))
            story.append(space(3))
        story.append(space(6))

    # ── Executive summary: Score + KPIs side by side ──────────────────
    story.append(Paragraph("Résumé Exécutif", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(8))

    dep_total  = dep.get("total", 0)
    dep_level  = dep.get("level", "")
    dep_interp = dep.get("interpretation", "")
    level_fr   = {"high": "Forte dépendance", "medium": "Dépendance modérée",
                  "low": "Faible dépendance"}.get(dep_level, dep_level)

    gauge_img  = _chart_dependency_gauge(dep_total, level_fr)

    # Score details table
    comp_rows  = []
    comp_items = dep.get("components", {})
    COMP_LABELS = {
        "idiosyncratic": ("Risque idiosyncratique", 40, "R²"),
        "turnover":       ("Turnover portefeuille",  30, "Turnover"),
        "concentration":  ("Concentration (HHI)",    20, "HHI"),
        "alpha_signif":   ("Signif. alpha (|t|)",    10, "|t-stat|"),
    }
    for key, (lbl, mx, unit) in COMP_LABELS.items():
        comp = comp_items.get(key, {})
        sc   = comp.get("score", 0)
        comp_rows.append([
            _p(lbl, S_BODY),
            _pn(f"{sc:.0f} / {mx}", S_NUM),
        ])

    comp_tbl = _tbl(
        [[_p("Composante", S_HDR), _p("Score", S_HDR)]] + comp_rows,
        col_widths=[7.4*cm, 3.5*cm],
    )
    interp_para = Paragraph(dep_interp, S_WARN if dep_total >= 70 else
                            _sty("ip", fontSize=8, textColor=C_EMERALD, leading=11)
                            if dep_total < 45 else S_WARN)

    score_block = Table(
        [[gauge_img, Table([[comp_tbl],[space(6)],[interp_para]],
                           colWidths=[INNER_W - 6.5*cm])]],
        colWidths=[6.5*cm, INNER_W - 6.5*cm],
        style=TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                          ("LEFTPADDING",(0,0),(-1,-1),0),
                          ("RIGHTPADDING",(0,0),(-1,-1),0)])
    )
    story.append(score_block)
    story.append(space(12))

    # KPI row
    tot_ret = perf.get("total_ret_pct", 0) or 0
    ann_vol = perf.get("ann_vol_pct", 0) or 0
    sharpe  = perf.get("sharpe", 0) or 0
    max_dd  = perf.get("max_dd_pct", 0) or 0
    r2_pct  = round((reg.get("r2", 0) or 0) * 100, 1)
    alpha_a = reg.get("alpha_ann_pct", 0) or 0

    kpi = _kpi_row([
        ("Rendement total",  f"{tot_ret:+.1f}%", "#10b981" if tot_ret >= 0 else "#ef4444"),
        ("Volatilité ann.",  f"{ann_vol:.1f}%",  "#94a3b8"),
        ("Sharpe",           f"{sharpe:.2f}",    "#10b981" if sharpe >= 1 else "#f59e0b"),
        ("Max Drawdown",     f"{max_dd:.1f}%",   "#ef4444"),
    ])
    story.append(kpi)
    story.append(space(6))
    kpi2 = _kpi_row([
        ("R² (explication FF)", f"{r2_pct:.1f}%",  "#60a5fa"),
        ("Alpha annualisé",  f"{alpha_a:+.2f}%", "#10b981" if alpha_a >= 0 else "#ef4444"),
        ("Risque idiosync.", f"{100-r2_pct:.1f}%","#f59e0b"),
        ("Observations",     str(period.get("n_obs","?")), "#94a3b8"),
    ])
    story.append(kpi2)

    # ══════════════════════════════════════════════════════════════════
    # PAGE 2 — PERFORMANCE
    # ══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("Performance", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    if perf.get("dates"):
        story.append(_chart_performance(perf, bm))
        story.append(space(10))

    # Performance metrics table
    perf_rows = [
        [_p("Rendement total",    S_BODY), _pn(_pct(perf.get("total_ret_pct")))],
        [_p("Rendement annualisé",S_BODY), _pn(_pct(perf.get("ann_ret_pct")))],
        [_p("Volatilité annualisée",S_BODY),_pn(_pct(perf.get("ann_vol_pct"),1))],
        [_p("Sharpe",             S_BODY), _pn(f"{perf.get('sharpe') or 0:.3f}")],
        [_p("Max Drawdown",       S_BODY), _pn(_pct(perf.get("max_dd_pct")))],
        [_p("Tracking Error",     S_BODY), _pn(_pct(perf.get("tracking_err_pct")) if perf.get("tracking_err_pct") is not None else "—")],
        [_p("Information Ratio",  S_BODY), _pn(f"{perf.get('info_ratio') or 0:.3f}" if perf.get("info_ratio") is not None else "—")],
    ]
    perf_tbl = _tbl(
        [[_p("Indicateur", S_HDR), _p("Valeur", S_HDR)]] + perf_rows,
        col_widths=[11*cm, 6.4*cm],
    )
    story.append(KeepTogether([perf_tbl]))

    # ══════════════════════════════════════════════════════════════════
    # PAGE 3 — RÉGRESSION FAMA-FRENCH
    # ══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("Régression Fama-French — Coefficients OLS", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(8))

    # Regression summary
    reg_sum_data = [
        [_p("R²"), _pn(f"{(reg.get('r2') or 0)*100:.2f}%"),
         _p("Adj. R²"), _pn(f"{(reg.get('adj_r2') or 0)*100:.2f}%")],
        [_p("Alpha ann."), _pn(_pct(reg.get('alpha_ann_pct'), 2)),
         _p("t-stat α"),   _pn(f"{reg.get('alpha_tstat') or 0:.3f}")],
        [_p("p-value α"), _pn(f"{reg.get('alpha_pvalue') or 0:.4f}"),
         _p("Durbin-Watson"), _pn(f"{reg.get('dw') or 0:.3f}")],
    ]
    reg_sum_tbl = Table(reg_sum_data,
        colWidths=[4.6*cm, 4.1*cm, 4.6*cm, 4.1*cm],
        style=TableStyle([
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_CARD, C_BG]),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("BOX",(0,0),(-1,-1),0.5,C_BORDER),
        ]))
    story.append(reg_sum_tbl)
    story.append(space(12))

    # Factor coefficients table
    fac_rows = reg.get("factors", [])
    if fac_rows:
        tbl_data = [[_p("Facteur",S_HDR), _p("Beta",S_HDR), _p("IC 95% inf",S_HDR),
                     _p("IC 95% sup",S_HDR), _p("t-stat",S_HDR), _p("p-value",S_HDR),
                     _p("Signif.",S_HDR)]]
        # Alpha row first
        tbl_data.append([
            Paragraph("Alpha (ann.)", _sty("alf", fontName="Helvetica-Bold",
                      fontSize=8, textColor=colors.HexColor("#f59e0b"))),
            _pn(_pct(reg.get("alpha_ann_pct"), 2)),
            _pn(_pct(reg.get("alpha_ci_low"))),
            _pn(_pct(reg.get("alpha_ci_high"))),
            _pn(f"{reg.get('alpha_tstat') or 0:.3f}"),
            _pn(_pfmt(reg.get("alpha_pvalue"))),
            _p(_sig(_pval_safe(reg.get("alpha_pvalue"))), S_CENTER),
        ])
        for f in fac_rows:
            p_val = _pval_safe(f.get("pvalue"))
            bc = colors.HexColor("#60a5fa") if f.get("beta", 0) >= 0 else colors.HexColor("#f87171")
            tbl_data.append([
                Paragraph(f["name"], _sty("fn", fontName="Helvetica-Bold", fontSize=8,
                          textColor=C_TEXT)),
                Paragraph(f"{f.get('beta', 0):+.4f}",
                          _sty("bv", fontName="Helvetica-Bold", fontSize=8,
                               textColor=bc, alignment=TA_RIGHT)),
                _pn(f"{f.get('ci_low', 0):.4f}"),
                _pn(f"{f.get('ci_high', 0):.4f}"),
                _pn(f"{f.get('tstat', 0):.3f}"),
                _pn(_pfmt(p_val)),
                Paragraph(_sig(p_val), _sty("sig", alignment=TA_CENTER,
                          fontSize=9, textColor=colors.HexColor("#f59e0b"),
                          fontName="Helvetica-Bold")),
            ])
        fac_tbl = _tbl(tbl_data,
            col_widths=[3.0*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.2*cm, 2.2*cm, 2.8*cm])
        story.append(fac_tbl)
        story.append(space(6))
        story.append(Paragraph(
            "*** p&lt;0.001  · ** p&lt;0.01  · * p&lt;0.05  · · p&lt;0.10  — "
            "IC = intervalle de confiance à 95%. "
            "La régression est effectuée sur l'excès de rendement (rendement AMC — taux sans risque).",
            S_SMALL))

    # Rolling charts
    if rolling and len(rolling) > 5:
        story.append(space(14))
        story.append(Paragraph("Analyse Rolling — Betas et R² glissants", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        story.append(_chart_rolling(rolling, factors))
        story.append(space(6))
        story.append(Paragraph(
            f"Fenêtre glissante utilisée pour le calcul des betas et du R². "
            "Un R² faible et variable indique une gestion davantage pilotée par des décisions spécifiques "
            "du gérant (stock-picking) plutôt que par l'exposition systématique à des facteurs de risque.",
            S_SMALL))

    # ══════════════════════════════════════════════════════════════════
    # PAGE 4 — ACTIVITÉ & PORTEFEUILLE (optional)
    # ══════════════════════════════════════════════════════════════════
    has_activity   = act and act.get("total_trades", 0) > 0
    has_holdings   = conc.get("top_holdings")
    has_exposures  = conc.get("sectors") or conc.get("countries")

    if has_activity or has_holdings or has_exposures:
        story.append(PageBreak())
        story.append(Paragraph("Activité &amp; Portefeuille", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(8))

        if has_activity:
            act_rows = [
                [_p("Total transactions", S_BODY), _pn(str(act.get("total_trades","—")))],
                [_p("Jours actifs",        S_BODY), _pn(str(act.get("trading_days","—")))],
                [_p("Titres tradés",       S_BODY), _pn(str(act.get("unique_securities","—")))],
                [_p("Turnover depuis lancement", S_BODY),
                 _pn(f"{(act.get('turnover_rate') or 0)*100:.1f}%")],
                [_p("Achats (USD)",        S_BODY), _pn(_fmt_usd(act.get("buy_notional",0)))],
                [_p("Ventes (USD)",        S_BODY), _pn(_fmt_usd(act.get("sell_notional",0)))],
                [_p("Gross traded (USD)",  S_BODY), _pn(_fmt_usd(act.get("gross_traded",0)))],
            ]
            act_tbl = _tbl(
                [[_p("Indicateur d'activité", S_HDR), _p("Valeur", S_HDR)]] + act_rows,
                col_widths=[11*cm, 6.4*cm],
            )
            story.append(act_tbl)
            story.append(space(12))

        if has_holdings:
            story.append(Paragraph("Composition du portefeuille (top positions)", S_SECTION))
            story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
            story.append(space(6))
            h_data = [[_p("Titre", S_HDR), _p("Poids (%)", S_HDR)]]
            for h in conc["top_holdings"][:15]:
                h_data.append([_p(h["name"], S_BODY),
                                _pn(f"{h['weight']*100:.2f}%")])
            if conc.get("hhi") is not None:
                h_data.append([
                    Paragraph(f"HHI = {conc['hhi']}  ·  Top-5 = {conc.get('top5_weight',0)*100:.1f}%",
                              S_SMALL), _p("")])
            story.append(_tbl(h_data, col_widths=[13.5*cm, 3.9*cm]))
            story.append(space(12))

        if has_exposures:
            story.append(Paragraph("Expositions (secteurs · pays · devises)", S_SECTION))
            story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
            story.append(space(6))
            chart = _chart_exposures(
                conc.get("sectors",[]), conc.get("countries",[]), conc.get("currencies",[]))
            if chart:
                story.append(chart)

    # ══════════════════════════════════════════════════════════════════
    # LAST PAGE — DISCLAIMER
    # ══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(space(20))
    story.append(Paragraph("Avertissements &amp; Méthodologie", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(8))

    disc = [
        "<b>Régression OLS Fama-French :</b> La régression est effectuée sur les excès de rendements "
        "journaliers de l'AMC par rapport au taux sans risque (RF de Ken French) sur la période d'intersection "
        "entre les données NAV disponibles et les facteurs FF stockés. Les coefficients (betas) mesurent la "
        "sensibilité de l'AMC à chaque facteur de risque systématique. "
        "L'alpha (intercepte) est annualisé par multiplication × 252 × 100 ; "
        "les bornes de l'intervalle de confiance à 95 % sont annualisées par le même facteur.",
        "",
        "<b>Score de Dépendance au Gérant (0-100) :</b> Score composite calculé comme suit — "
        "Risque idiosyncratique (1-R²) × 40 pts : mesure la part de variance non expliquée par les facteurs ; "
        "Turnover × 30 pts : activité de trading normalisée ; "
        "Concentration HHI × 20 pts : mesure de concentration du portefeuille ; "
        "Signification de l'alpha × 10 pts : valeur absolue du t-stat de l'alpha normalisée. "
        "Un score élevé (>70) suggère une forte empreinte du gérant.",
        "",
        "<b>Qualité des données :</b> Les résultats sont d'autant plus fiables que l'historique NAV est long. "
        "Un minimum de 252 observations journalières (1 an) est recommandé. En deçà, les intervalles de "
        "confiance sont larges et les conclusions doivent être nuancées.",
        "",
        "<b>Données Fama-French :</b> Téléchargées depuis la bibliothèque de Kenneth R. French "
        "(Tuck School of Business, Dartmouth). Les facteurs sont exprimés en excès de rendement "
        "quotidien et divisés par 100 pour être en décimales.",
        "",
        "<b>Benchmark :</b> Données de prix ajustées téléchargées via Yahoo Finance (yfinance). "
        "Le tracking error et l'information ratio sont calculés sur la période d'intersection commune.",
        "",
        "<b>Avertissement général :</b> Ce document est produit à titre informatif et analytique. "
        "Il ne constitue pas un conseil en investissement, une recommandation d'achat ou de vente, "
        "ni une évaluation officielle au sens des réglementations applicables. "
        "Les performances passées ne préjugent pas des performances futures.",
    ]
    for line in disc:
        if line:
            story.append(Paragraph(line, _sty("disc", fontSize=7.5, textColor=C_FAINT,
                                              leading=11, spaceAfter=5)))
        else:
            story.append(space(4))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


def _fmt_usd(n):
    if not n: return "$0"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    if n >= 1e3: return f"${n/1e3:.1f}k"
    return f"${n:.0f}"


def _fmt_prod(n, ccy=""):
    """Format a product-currency amount."""
    prefix = f"{ccy} " if ccy else ""
    if n is None: return "—"
    if abs(n) >= 1e6: return f"{prefix}{n/1e6:+.2f}M"
    if abs(n) >= 1e3: return f"{prefix}{n/1e3:+.1f}k"
    return f"{prefix}{n:+.0f}"


# ── Block E chart: AMC NAV vs Buy & Hold ──────────────────────────────

def _chart_nav_bh(bh_records: list, real_records: list | None,
                  bh_label: str = "Buy & Hold passif") -> Image:
    """Line chart: AMC réel vs référence passive, both rebased to 100 at t0."""
    fig, ax = plt.subplots(figsize=(9.5, 4.2), facecolor="#0f172a")
    _dark_axes(ax, fig)

    if bh_records:
        vals_bh  = [r["value"] for r in bh_records]
        dates_bh = [r["date"]  for r in bh_records]
        n = len(dates_bh)
        ax.plot(range(n), vals_bh, color="#60a5fa", linewidth=1.6, label=bh_label)
        ax.fill_between(range(n), vals_bh, 100, alpha=0.07, color="#60a5fa")

    if real_records and bh_records:
        # Map real_nav dates to x-positions on the bh axis
        date_to_idx = {d: i for i, d in enumerate(dates_bh)}
        xs = [date_to_idx[r["date"]] for r in real_records if r["date"] in date_to_idx]
        ys = [r["value"] for r in real_records if r["date"] in date_to_idx]
        if xs:
            ax.plot(xs, ys, color="#10b981", linewidth=1.9, label="AMC réel")
            ax.fill_between(xs, ys, 100, alpha=0.07, color="#10b981")

    ax.axhline(100, color="#475569", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_ylabel("Performance (base 100)", color="#64748b", fontsize=7)

    if bh_records:
        n = len(dates_bh)
        step = max(1, n // 6)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([dates_bh[i] for i in range(0, n, step)],
                           rotation=20, ha="right", fontsize=7)

    ax.legend(fontsize=8, framealpha=0, labelcolor="#94a3b8")
    return _fig_to_image(fig, 17, 6)


def _chart_replicant_vs_amc(replicant_records: list, amc_records: list) -> Image:
    """Line chart: AMC réel vs portefeuille réplicant (facteurs FF)."""
    fig, ax = plt.subplots(figsize=(9.5, 4.2), facecolor="#0f172a")
    _dark_axes(ax, fig)

    if replicant_records:
        dates_r = [r["date"] for r in replicant_records]
        vals_r  = [r["value"] for r in replicant_records]
        n = len(dates_r)
        ax.plot(range(n), vals_r, color="#a78bfa", linewidth=1.6, label="Réplicant factoriel")
        ax.fill_between(range(n), vals_r, 100, alpha=0.07, color="#a78bfa")

    if amc_records and replicant_records:
        date_to_idx = {d: i for i, d in enumerate(dates_r)}
        xs = [date_to_idx[r["date"]] for r in amc_records if r["date"] in date_to_idx]
        ys = [r["value"] for r in amc_records if r["date"] in date_to_idx]
        if xs:
            ax.plot(xs, ys, color="#10b981", linewidth=1.9, label="AMC réel")
            ax.fill_between(xs, ys, 100, alpha=0.07, color="#10b981")

    ax.axhline(100, color="#475569", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_ylabel("Performance (base 100)", color="#64748b", fontsize=7)

    if replicant_records:
        n = len(dates_r)
        step = max(1, n // 6)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([dates_r[i] for i in range(0, n, step)],
                           rotation=20, ha="right", fontsize=7)

    ax.legend(fontsize=8, framealpha=0, labelcolor="#94a3b8")
    return _fig_to_image(fig, 17, 6)


def _chart_factor_contribs(factor_contributions: list) -> Image:
    """Horizontal bar chart: contribution de chaque facteur à la perf du réplicant."""
    if not factor_contributions:
        return None
    items = sorted(factor_contributions, key=lambda x: x["contribution_pct"])
    names  = [f["name"] for f in items]
    values = [f["contribution_pct"] for f in items]
    bar_colors = ["#10b981" if v >= 0 else "#ef4444" for v in values]

    fig, ax = plt.subplots(figsize=(9.5, max(2.5, len(items) * 0.5 + 0.8)),
                           facecolor="#0f172a")
    _dark_axes(ax, fig)
    y = range(len(names))
    ax.barh(list(y), values, color=bar_colors, alpha=0.85, height=0.55)
    ax.axvline(0, color="#334155", linewidth=0.8)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=8, color="#94a3b8")
    ax.set_xlabel("Contribution cumulée (%)", color="#64748b", fontsize=7)
    for i, (val, name) in enumerate(zip(values, names)):
        ax.text(val + (0.1 if val >= 0 else -0.1), i,
                f"{val:+.2f}%", va="center",
                ha="left" if val >= 0 else "right",
                fontsize=7, color="#94a3b8")
    fig.tight_layout()
    return _fig_to_image(fig, 17, max(3.5, len(items) * 0.55 + 1.0))


# ── New chart helpers (Blocks B / C / D) ──────────────────────────────

def _chart_quarterly_pnl(quarterly: list) -> Image:
    """Bar chart: realised P&L by exit quarter."""
    if not quarterly:
        return None
    quarters = [r["quarter"] for r in quarterly]
    pnls = [r["realized_pnl"] for r in quarterly]
    colors_ = ["#10b981" if p >= 0 else "#ef4444" for p in pnls]

    fig, ax = plt.subplots(figsize=(9.5, 3.2), facecolor="#0f172a")
    _dark_axes(ax, fig)
    x = range(len(quarters))
    ax.bar(x, pnls, color=colors_, alpha=0.85, width=0.6)
    ax.axhline(0, color="#334155", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(quarters, rotation=30, ha="right", fontsize=6.5)
    ax.set_ylabel("P&L réalisé (devise produit)", color="#64748b", fontsize=7)
    ax.set_title("P&L réalisé par trimestre", color="#94a3b8", fontsize=8)
    fig.tight_layout()
    return _fig_to_image(fig, 17, 5.5)


def _chart_holding_dist(closed_holds: list, cutoff: int) -> Image:
    """Histogram of closed holding periods with conviction cutoff line."""
    if not closed_holds:
        return None
    fig, ax = plt.subplots(figsize=(9.5, 3.2), facecolor="#0f172a")
    _dark_axes(ax, fig)
    bins = min(30, max(10, len(closed_holds) // 3))
    ax.hist(closed_holds, bins=bins, color="#60a5fa", alpha=0.7, edgecolor="#1e293b")
    ax.axvline(cutoff, color="#f59e0b", linewidth=1.5, linestyle="--",
               label=f"Seuil conviction ({cutoff}j)")
    ax.set_xlabel("Durée de détention (jours)", color="#64748b", fontsize=7)
    ax.set_ylabel("Nombre de positions", color="#64748b", fontsize=7)
    ax.set_title("Distribution des durées de détention (trades clôturés)",
                 color="#94a3b8", fontsize=8)
    ax.legend(fontsize=7, framealpha=0, labelcolor="#94a3b8")
    fig.tight_layout()
    return _fig_to_image(fig, 17, 5.5)


def _chart_conviction_matrix(matrix: dict, pnl: dict) -> Image:
    """2×2 conviction × result bubble chart, one bubble per quadrant."""
    labels = {
        "conviction_winners": ("Paris gagnants\nassumés", "#10b981"),
        "tactical_winners":   ("Coups tactiques\nréussis", "#60a5fa"),
        "stubborn_losers":    ("Entêtements\ncoûteux", "#ef4444"),
        "uncertainty":        ("Positions\nd'incertitude", "#f59e0b"),
    }
    # positions: conviction axis (x) vs result axis (y)
    pos = {
        "conviction_winners": (1, 1),
        "tactical_winners":   (-1, 1),
        "stubborn_losers":    (1, -1),
        "uncertainty":        (-1, -1),
    }
    fig, ax = plt.subplots(figsize=(7, 5.5), facecolor="#0f172a")
    _dark_axes(ax, fig)
    ax.axhline(0, color="#334155", linewidth=1)
    ax.axvline(0, color="#334155", linewidth=1)
    ax.set_xlim(-2, 2); ax.set_ylim(-2, 2)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlabel("← Tactique    Conviction →", color="#64748b", fontsize=8)
    ax.set_ylabel("← Perte    Gain →", color="#64748b", fontsize=8)
    ax.set_title("Matrice conviction × résultat", color="#94a3b8", fontsize=9)

    for q, (label, col) in labels.items():
        n = len(matrix.get(q, []))
        if n == 0:
            continue
        x, y = pos[q]
        size = max(300, min(3000, n * 200))
        ax.scatter(x, y, s=size, color=col, alpha=0.35, zorder=2)
        ax.scatter(x, y, s=50, color=col, zorder=3)
        p = pnl.get(q, 0.0)
        ax.text(x, y + 0.35, f"n={n}", ha="center", va="center",
                fontsize=8, color=col, fontweight="bold")
        ax.text(x, y - 0.35, _fmt_prod(p), ha="center", va="center",
                fontsize=7, color="#94a3b8")
        ax.text(x, y, label, ha="center", va="center",
                fontsize=7, color=col, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#0f172a", alpha=0.6, edgecolor="none"))

    # Quadrant backgrounds
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((-2, 0), 2, 2, facecolor="#60a5fa", alpha=0.03))
    ax.add_patch(Rectangle((0, 0), 2, 2, facecolor="#10b981", alpha=0.03))
    ax.add_patch(Rectangle((-2, -2), 2, 2, facecolor="#f59e0b", alpha=0.03))
    ax.add_patch(Rectangle((0, -2), 2, 2, facecolor="#ef4444", alpha=0.03))
    fig.tight_layout()
    return _fig_to_image(fig, 9.5, 6.5)


# ── Study PDF — Blocs B / C / D + Confiance ───────────────────────────

def generate_study_pdf(study_result: dict, synthese_text: str = "",
                        vag_result: dict | None = None,
                        attribution_result: dict | None = None,
                        brinson_result: dict | None = None,
                        market_shocks_result: dict | None = None,
                        company_name: str = "TP Advisory Services",
                        client_name: str = "",
                        include_annexes: bool = True) -> bytes:
    """Generate the extended report from a run_study() result.

    Wraps the existing generate_pdf() for Bloc A (if available) and appends
    new sections for Blocs B, C, D, E (VAG) and the confidence/limitations table.
    """
    buf = io.BytesIO()
    meta = study_result.get("meta", {})
    prod = meta.get("product_name", "AMC")
    isin = meta.get("isin", "")
    ccy  = meta.get("currency", "")
    theme = meta.get("theme", "")
    warns = study_result.get("warnings", [])

    block_a = study_result.get("block_a", {})
    block_b = study_result.get("block_b", {})
    block_c = study_result.get("block_c", {})
    block_d = study_result.get("block_d", {})
    block_f = study_result.get("block_f")
    confidence = study_result.get("confidence", {})
    catalog = study_result.get("block_catalog", [])

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.6*cm, bottomMargin=1.2*cm,
    )
    story = []

    def space(h=6): return Spacer(1, h)
    def section(title):
        story.append(space(14))
        story.append(Paragraph(title, S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))

    # ── Compute MSS early (needed for executive summary on page 2) ─────
    mss_early = study_result.get("manager_skill_score")
    mss_no_vag = None   # supprimé — VAG désormais intégré dans block_e

    # ── PAGE 1: COVER (drawn by canvas callback) ────────────────────────
    story.append(PageBreak())

    # ── PAGE 2: EXECUTIVE SUMMARY — Score Global ────────────────────────
    if mss_early and mss_early.get("available"):
        _append_executive_summary(story, mss_early, mss_no_vag, meta, space)
        story.append(PageBreak())

    story.append(space(6))

    # Performance totale depuis la NAV de départ
    nav_s = meta.get("nav_start_value")
    nav_c = meta.get("nav_current_value")
    perf_str = "—"
    if nav_s and nav_c and nav_s != 0:
        perf_val = (nav_c / nav_s - 1) * 100
        perf_str = f"{perf_val:+.2f}%"

    fee = meta.get("management_fee_pct")
    fee_str = f"{fee}% p.a." if fee is not None else "Non renseigné"

    aum = meta.get("total_aum")
    outstanding = meta.get("outstanding")
    aum_str = "—"
    if aum:
        if aum >= 1e6:
            aum_str = f"{aum/1e6:.2f}M {ccy}"
        elif aum >= 1e3:
            aum_str = f"{aum/1e3:.0f}k {ccy}"
        else:
            aum_str = f"{aum:.0f} {ccy}"

    cover_data = [
        [_p("Préparé pour", S_LABEL), _p(client_name or "—",
            _sty("pv_client", fontName="Helvetica-Bold", fontSize=9,
                 textColor=colors.HexColor("#60a5fa")))],
        [_p("Produit",   S_LABEL), _p(prod, _sty("pv2", fontName="Helvetica-Bold", fontSize=9, textColor=C_TEXT))],
        [_p("ISIN",      S_LABEL), _p(isin or "—", S_BODY)],
        [_p("Devise",    S_LABEL), _p(ccy or "—", S_BODY)],
        [_p("Thème",     S_LABEL), _p(theme or "—", S_BODY)],
        [_p("Commission de gestion", S_LABEL), _p(fee_str, S_BODY)],
        [_p("NAV de départ", S_LABEL), _p(
            f"{meta.get('nav_start_value', '—')}  ({meta.get('nav_start_date', '—')})", S_BODY)],
        [_p("NAV actuelle", S_LABEL), _p(
            f"{meta.get('nav_current_value', '—')}  ({meta.get('nav_current_date', '—')})", S_BODY)],
        [_p("Performance totale", S_LABEL), _p(perf_str,
            _sty("pperf", fontSize=9, textColor=(colors.HexColor("#34d399") if nav_c and nav_s and nav_c >= nav_s else colors.HexColor("#f87171"))))],
        [_p("Observations NAV", S_LABEL), _p(str(meta.get("nav_n_obs", "—")), S_BODY)],
        [_p("AUM estimé (snapshot)", S_LABEL), _p(aum_str, S_BODY)],
        [_p("Certificats en circulation", S_LABEL), _p(
            f"{outstanding:,}".replace(",", " ") if outstanding else "—", S_BODY)],
        [_p("Snapshot composition", S_LABEL), _p(str(meta.get("nav_snapshot_date", "—")), S_BODY)],
        [_p("Sous-jacents", S_LABEL), _p(str(meta.get("n_underlyings", "—")), S_BODY)],
        [_p("Ordres analysés", S_LABEL), _p(str(meta.get("n_orders", "—")), S_BODY)],
        [_p("Série FF / Modèle", S_LABEL), _p(
            f"{meta.get('ff_series', '—')}  ·  {meta.get('factor_model', '—')}", S_BODY)],
        [_p("Benchmark", S_LABEL), _p(str(meta.get("benchmark_ticker", "—")), S_BODY)],
        [_p("Audience", S_LABEL), _p({
            "committee": "Comité (technique)",
            "investor": "Investisseur (pédagogique)",
            "due_diligence": "Due Diligence (factuel/traçable)",
        }.get(str(meta.get("audience", "")), str(meta.get("audience", "—")) or "—"), S_BODY)],
        [_p("À la date du", S_LABEL), _p(str(meta.get("as_of", "—")), S_BODY)],
        [_p("Généré le", S_LABEL), _p(datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), S_BODY)],
    ]
    story.append(Table(cover_data, colWidths=[5.0*cm, INNER_W - 5.0*cm],
        style=TableStyle([
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_BG, colors.HexColor("#111827")]),
            ("LINEBELOW",(0,0),(-1,-2),0.3, C_BORDER),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8),
            ("BOX",(0,0),(-1,-1),0.5,C_BORDER),
        ])))
    story.append(space(12))

    # ── Synthèse rédigée (optionnelle) ─────────────────────────────────
    if synthese_text and synthese_text.strip():
        section("Synthèse")
        _synthese_sty = _sty("synth", fontSize=9, textColor=C_TEXT, leading=14,
                             spaceAfter=0, alignment=TA_JUSTIFY)
        for para in synthese_text.strip().split("\n"):
            stripped = para.strip()
            if stripped:
                story.append(Paragraph(stripped, _synthese_sty))
                story.append(space(4))
            else:
                story.append(space(8))
        story.append(PageBreak())

    # Warnings at the top (before analysis blocks)
    if warns:
        for w in warns:
            story.append(Paragraph(f"⚠  {w}", S_WARN))
        story.append(space(8))

    # ── BLOC A ─────────────────────────────────────────────────────────
    if block_a and block_a.get("available"):
        story.append(PageBreak())
        net_result = block_a.get("net", {})
        gross_result = block_a.get("gross", {})
        fee_drag = block_a.get("fee_drag_pct")
        _append_block_a_sections(story, net_result, gross_result, fee_drag, meta, space)
    elif block_a and not block_a.get("available"):
        story.append(PageBreak())
        section("A — Analyse Factorielle (non disponible)")
        story.append(Paragraph(f"⚠  {block_a.get('error', 'Données indisponibles.')}", S_WARN))

    # ── BLOC B — Attribution ────────────────────────────────────────────
    _t0_disclaimer = (
        "⚠  Les positions initiales ont été reconstruites par BUY synthétiques à T0. "
        "Les métriques de P&L réalisé et de round trips sont donc plus cohérentes "
        "qu'en mode inventaire clampé, mais restent dépendantes des hypothèses de "
        "reconstruction du stock initial."
    )
    if block_b:
        story.append(PageBreak())
        section("B — Attribution de Performance par Sous-jacent")
        if meta.get("recon_mode") == "t0_synthetic":
            story.append(Paragraph(_t0_disclaimer, S_WARN))
            story.append(space(8))
        _append_block_b(story, block_b, ccy, space, meta)

    # ── BLOC C — Trading / Turnover ─────────────────────────────────────
    if block_c:
        story.append(PageBreak())
        section("C — Qualité des Décisions de Trading & Turnover")
        if meta.get("recon_mode") == "t0_synthetic":
            story.append(Paragraph(_t0_disclaimer, S_WARN))
            story.append(space(8))
        _append_block_c(story, block_c, ccy, space, meta)

    # ── BLOC D — Comportement ───────────────────────────────────────────
    if block_d:
        story.append(PageBreak())
        section("D — Comportement du Gérant : Conviction vs Incertitude")
        _append_block_d(story, block_d, space, meta)

    # ── BLOC E — Référentiel Inertiel (B&H) ─────────────────────────────
    block_e = study_result.get("block_e")
    if block_e:
        story.append(PageBreak())
        section("E — Référentiel Inertiel : Valeur Ajoutée par la Gestion Active (B&amp;H passif)")
        _append_block_bh(story, block_e, ccy, space, meta)

    # ── BLOC F — Réplicabilité ───────────────────────────────────────────
    if block_f:
        story.append(PageBreak())
        section("F — Réplicabilité de la Stratégie")
        _append_block_f_replicability(story, block_f, space)

    # ── BLOC H — Brinson-Fachler Attribution ────────────────────────────
    if brinson_result and brinson_result.get("available"):
        story.append(PageBreak())
        section("G — Attribution Brinson-Fachler")
        _append_block_g_brinson(story, brinson_result, space)

    # ── BLOC I — Timing Score ─────────────────────────────────────────────
    block_h = study_result.get("block_h")
    if block_h:
        story.append(PageBreak())
        section("H — Timing Score : Qualité des Points d'Entrée et de Sortie")
        _append_block_h_timing(story, block_h, space, meta)

    # ── BLOC J — Stock Picking Score ─────────────────────────────────────
    block_i = study_result.get("block_i")
    if block_i:
        story.append(PageBreak())
        section("I — Stock Picking Score : Qualité de la Sélection de Titres")
        _append_block_i_stockpicking(story, block_i, space, meta)

    # ── BLOC K — Risk Management Score ───────────────────────────────────
    block_j = study_result.get("block_j")
    if block_j:
        story.append(PageBreak())
        section("J — Risk Management Score : Évaluation de la Gestion du Risque")
        _append_block_j_rms(story, block_j, space, meta)

    # ── BLOC K — Réactivité aux Chocs de Marché ──────────────────────────
    # Not read from study_result — like Bloc G/Brinson, only included when
    # explicitly selected upfront (manifest.blocks.K_marketshocks) or run on
    # demand from its own tab, then explicitly opted into the PDF export.
    if market_shocks_result and market_shocks_result.get("available"):
        story.append(PageBreak())
        section("K — Réactivité aux Chocs de Marché")
        _append_block_k_marketshocks(story, market_shocks_result, space)

    # ── MANAGER SKILL SCORE (detailed breakdown) ─────────────────────────
    # mss_early already computed at top (with VAG) — reuse it here
    mss = mss_early
    if mss and mss.get("available"):
        story.append(PageBreak())
        section("Manager Skill Score — Évaluation Globale du Gérant")
        _append_manager_skill(story, mss, space)

    # ── CATALOGUE DES BLOCS (méthodologie — en fin de document) ─────────
    story.append(PageBreak())
    section("Blocs d'analyse — Contenu et méthodes")
    for bl in catalog:
        story.append(KeepTogether([
            Paragraph(bl["title"], _sty("btit", fontName="Helvetica-Bold", fontSize=9, textColor=C_BLUE)),
            space(2),
            Paragraph(f"<b>Quoi :</b> {bl['what']}", _sty("bw", fontSize=7.5, textColor=C_MUTED, leading=11)),
            Paragraph(f"<b>Comment :</b> {bl['how']}", _sty("bh", fontSize=7.5, textColor=C_MUTED, leading=11)),
            Paragraph(f"<b>Avec :</b> {bl['inputs']}", _sty("bi", fontSize=7.5, textColor=C_FAINT, leading=11)),
            space(8),
        ]))

    # ── CONFIANCE & LIMITES ─────────────────────────────────────────────
    if confidence:
        story.append(PageBreak())
        # Rebuild confidence with all available data
        from .amc_confidence import build_confidence
        blocks_run = set(meta.get("blocks_run", []))
        block_a_r  = study_result.get("block_a")
        n_orders   = meta.get("n_orders", 0)
        confidence = build_confidence(
            blocks_run, block_a_r, n_orders,
            block_e_result=study_result.get("block_e"),
            attribution_result=attribution_result,
            block_f_result=block_f,
            block_h_result=study_result.get("block_h"),
            block_i_result=study_result.get("block_i"),
            block_j_result=study_result.get("block_j"),
        )
        _append_confidence(story, confidence, space)

    # ── DISCLAIMER ──────────────────────────────────────────────────────
    story.append(PageBreak())
    _append_disclaimer(story, space)

    if include_annexes:
        # ── ANNEXE — Timing Score detail ──────────────────────────────
        if block_h and block_h.get("available") and block_h.get("trades"):
            _append_block_h_appendix(story, block_h, space)

        # ── ANNEXE — Stock Picking detail ─────────────────────────────
        if block_i and block_i.get("available") and block_i.get("trades"):
            _append_block_i_appendix(story, block_i, space)

    cover_cb = _draw_study_cover(meta, company_name, client_name or "—")
    page_cb  = _make_study_page(company_name, client_name or "—")
    doc.build(story, onFirstPage=cover_cb, onLaterPages=page_cb)
    return buf.getvalue()


def _append_block_a_sections(story, net, gross, fee_drag, meta, space):
    """Inline the core FF regression sections from net (and gross if available)."""
    perf    = net.get("performance", {})
    reg     = net.get("regression", {})
    rolling = net.get("rolling", [])
    period  = net.get("period", {})
    factors = net.get("factors_used", [])
    ff_ser  = net.get("ff_series", "")
    bm      = net.get("benchmark", "")
    warns   = net.get("warnings", [])
    prod    = (meta or {}).get("product_name", "AMC")
    isin    = (meta or {}).get("isin", "")

    story.append(Paragraph("A — Analyse Factorielle Fama-French", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(8))

    if warns:
        for w in warns:
            story.append(Paragraph(f"⚠  {w}", S_WARN))
        story.append(space(6))

    # Performance chart
    if perf.get("dates"):
        story.append(_chart_performance(perf, bm))
        story.append(space(8))

    # KPIs
    tot_ret = perf.get("total_ret_pct", 0) or 0
    ann_vol = perf.get("ann_vol_pct", 0) or 0
    sharpe  = perf.get("sharpe", 0) or 0
    max_dd  = perf.get("max_dd_pct", 0) or 0
    story.append(_kpi_row([
        ("Rendement total", f"{tot_ret:+.1f}%", "#10b981" if tot_ret >= 0 else "#ef4444"),
        ("Volatilité ann.", f"{ann_vol:.1f}%", "#94a3b8"),
        ("Sharpe",          f"{sharpe:.2f}", "#10b981" if sharpe >= 1 else "#f59e0b"),
        ("Max Drawdown",    f"{max_dd:.1f}%", "#ef4444"),
    ]))
    story.append(space(8))

    # Gross vs net comparison (if fee provided)
    if gross and gross.get("regression"):
        g_reg = gross["regression"]
        n_reg = reg
        story.append(Paragraph("Alpha brut vs net (ajout des frais en accrual quotidien)", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        gn_data = [
            [_p("Métrique", S_HDR), _p("Net (client)", S_HDR), _p("Brut (gérant)", S_HDR),
             _p("Delta (frais)", S_HDR)],
            [_p("Alpha ann.", S_BODY),
             _pn(_pct(n_reg.get("alpha_ann_pct"), 2)),
             _pn(_pct(g_reg.get("alpha_ann_pct"), 2)),
             _pn(_pct(round((g_reg.get("alpha_ann_pct") or 0) - (n_reg.get("alpha_ann_pct") or 0), 2), 2))],
            [_p("t-stat α", S_BODY),
             _pn(f"{n_reg.get('alpha_tstat') or 0:.3f}"),
             _pn(f"{g_reg.get('alpha_tstat') or 0:.3f}"),
             _pn("—")],
            [_p("R²", S_BODY),
             _pn(f"{(n_reg.get('r2') or 0)*100:.2f}%"),
             _pn(f"{(g_reg.get('r2') or 0)*100:.2f}%"),
             _pn("—")],
        ]
        story.append(_tbl(gn_data, col_widths=[5.4*cm, 4.0*cm, 4.0*cm, 4.0*cm]))
        story.append(space(6))
        story.append(Paragraph(
            f"Frais de gestion utilisés pour le gross add-back : {fee_drag:.2f}% p.a. "
            f"(accrual quotidien = {fee_drag/252:.4f}%). Source : term sheet produit.",
            S_SMALL))
        story.append(space(12))

    # Regression table
    story.append(Paragraph("Régression OLS — Coefficients", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    reg_sum = Table([
        [_p("R²"), _pn(f"{(reg.get('r2') or 0)*100:.2f}%"),
         _p("Adj. R²"), _pn(f"{(reg.get('adj_r2') or 0)*100:.2f}%")],
        [_p("Alpha ann."), _pn(_pct(reg.get("alpha_ann_pct"), 2)),
         _p("t-stat α"),   _pn(f"{reg.get('alpha_tstat') or 0:.3f}")],
        [_p("p-value α"), _pn(f"{reg.get('alpha_pvalue') or 0:.4f}"),
         _p("Durbin-Watson"), _pn(f"{reg.get('dw') or 0:.3f}")],
    ], colWidths=[4.6*cm, 4.1*cm, 4.6*cm, 4.1*cm],
    style=TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_CARD, C_BG]),
        ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8),
        ("BOX",(0,0),(-1,-1),0.5,C_BORDER),
    ]))
    story.append(reg_sum)
    story.append(space(10))

    fac_rows = reg.get("factors", [])
    if fac_rows:
        tbl_data = [[_p("Facteur",S_HDR), _p("Beta",S_HDR), _p("IC 95% inf",S_HDR),
                     _p("IC 95% sup",S_HDR), _p("t-stat",S_HDR), _p("p-value",S_HDR),
                     _p("Signif.",S_HDR)]]
        tbl_data.append([
            Paragraph("Alpha (ann.)", _sty("alf2", fontName="Helvetica-Bold", fontSize=8,
                      textColor=colors.HexColor("#f59e0b"))),
            _pn(_pct(reg.get("alpha_ann_pct"), 2)),
            _pn(_pct(reg.get("alpha_ci_low"))),
            _pn(_pct(reg.get("alpha_ci_high"))),
            _pn(f"{reg.get('alpha_tstat') or 0:.3f}"),
            _pn(_pfmt(reg.get("alpha_pvalue"))),
            _p(_sig(_pval_safe(reg.get("alpha_pvalue"))), S_CENTER),
        ])
        for f in fac_rows:
            p_val = _pval_safe(f.get("pvalue"))
            bc = colors.HexColor("#60a5fa") if f.get("beta", 0) >= 0 else colors.HexColor("#f87171")
            tbl_data.append([
                Paragraph(f["name"], _sty("fn2", fontName="Helvetica-Bold", fontSize=8, textColor=C_TEXT)),
                Paragraph(f"{f.get('beta', 0):+.4f}", _sty("bv2", fontName="Helvetica-Bold",
                          fontSize=8, textColor=bc, alignment=TA_RIGHT)),
                _pn(f"{f.get('ci_low', 0):.4f}"), _pn(f"{f.get('ci_high', 0):.4f}"),
                _pn(f"{f.get('tstat', 0):.3f}"), _pn(_pfmt(p_val)),
                Paragraph(_sig(p_val), _sty("sig2", alignment=TA_CENTER, fontSize=9,
                          textColor=colors.HexColor("#f59e0b"), fontName="Helvetica-Bold")),
            ])
        story.append(_tbl(tbl_data, col_widths=[3.0*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.2*cm, 2.2*cm, 2.8*cm]))
        story.append(space(6))
        story.append(Paragraph("*** p<0.001  · ** p<0.01  · * p<0.05  · · p<0.10", S_SMALL))

    # ── Benchmark composition (synthetic only) ────────────────────────
    bm_comp = net.get("benchmark_composition")
    if bm_comp:
        story.append(space(12))
        story.append(Paragraph("Composition du benchmark synthétique", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        story.append(Paragraph(
            f"<b>{bm_comp.get('label', '')}</b> — {bm_comp.get('description', '')}",
            S_BODY))
        story.append(space(6))
        bm_tbl = [[_p("Composant", S_HDR), _p("Ticker", S_HDR), _p("Poids", S_HDR)]]
        for comp in bm_comp.get("components", []):
            bm_tbl.append([
                _p(comp.get("label", ""), S_BODY),
                _p(comp.get("ticker", ""), _sty("bmt", fontName="Helvetica-Bold",
                    fontSize=8, textColor=C_BLUE)),
                _pn(f"{comp.get('weight', 0)*100:.0f}%"),
            ])
        story.append(_tbl(bm_tbl, col_widths=[8.5*cm, 4.0*cm, 3.0*cm]))
        story.append(space(4))
        story.append(Paragraph(
            "Benchmark composite repondéré quotidiennement. "
            "Les rendements sont calculés en pondérant les rendements journaliers de chaque composant.",
            S_SMALL))
        story.append(space(8))

    # ── Benchmark regression (Jensen's alpha vs benchmark) ────────────
    bench_reg = net.get("benchmark_regression")
    if bench_reg and isinstance(bench_reg, dict):
        story.append(space(12))
        story.append(Paragraph(f"Régression vs Benchmark ({bench_reg.get('ticker', bm)})", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        story.append(Paragraph(
            "OLS : R<sub>AMC</sub> − R<sub>f</sub> = α + β × (R<sub>benchmark</sub> − R<sub>f</sub>) + ε  "
            "— mesure l'alpha de Jensen et la sensibilité au benchmark sectoriel.",
            S_SMALL))
        story.append(space(4))
        b_alpha = bench_reg.get("alpha_ann_pct", 0) or 0
        b_alpha_col = "#10b981" if b_alpha >= 0 else "#ef4444"
        bm_data = [
            [_p("Métrique", S_HDR), _p("Valeur", S_HDR),
             _p("t-stat", S_HDR), _p("p-value", S_HDR), _p("Signif.", S_HDR)],
            [_p("Alpha (Jensen) ann.", S_BODY),
             Paragraph(f"{b_alpha:+.3f}%", _sty("ba", fontName="Helvetica-Bold", fontSize=8,
                       textColor=colors.HexColor(b_alpha_col), alignment=TA_RIGHT)),
             _pn(f"{bench_reg.get('alpha_tstat', 0) or 0:.3f}"),
             _pn(_pfmt(bench_reg.get("alpha_pvalue"))),
             _p(_sig(_pval_safe(bench_reg.get("alpha_pvalue"))), S_CENTER)],
            [_p(f"Beta ({bench_reg.get('ticker', bm)})", S_BODY),
             _pn(f"{bench_reg.get('beta', 0) or 0:+.4f}"),
             _pn(f"{bench_reg.get('beta_tstat', 0) or 0:.3f}"),
             _pn(_pfmt(bench_reg.get("beta_pvalue"))),
             _p(_sig(_pval_safe(bench_reg.get("beta_pvalue"))), S_CENTER)],
            [_p("R² vs benchmark", S_BODY),
             _pn(f"{(bench_reg.get('r2', 0) or 0)*100:.2f}%"),
             _p("—", S_NUM), _p("—", S_NUM), _p("", S_CENTER)],
        ]
        story.append(_tbl(bm_data, col_widths=[5.5*cm, 3.5*cm, 3.0*cm, 3.0*cm, 2.4*cm]))
        story.append(space(6))

    if rolling and len(rolling) > 5:
        story.append(space(12))
        story.append(Paragraph("Betas & R² glissants", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        story.append(_chart_rolling(rolling, factors))


def _append_block_b(story, b, ccy, space, meta=None):
    totals = b.get("totals", {})
    fx_share = totals.get("fx_share_of_realized_pct")

    # Summary KPIs — valeurs sans préfixe devise pour éviter le wrap à 20pt
    ccy_lbl = f" ({ccy})" if ccy else ""
    story.append(_kpi_row([
        (f"P&L réalisé total{ccy_lbl}", _fmt_prod(totals.get("realized_pnl")),
         "#10b981" if (totals.get("realized_pnl") or 0) >= 0 else "#ef4444"),
        (f"P&L latent total{ccy_lbl}", _fmt_prod(totals.get("unreal_pnl")),
         "#10b981" if (totals.get("unreal_pnl") or 0) >= 0 else "#ef4444"),
        (f"P&L total{ccy_lbl}",  _fmt_prod(totals.get("total_pnl")),
         "#10b981" if (totals.get("total_pnl") or 0) >= 0 else "#ef4444"),
        ("Part FX réalisé", f"{fx_share:.1f}%" if fx_share is not None else "—", "#f59e0b"),
    ]))
    story.append(space(10))

    _meta = meta or {}
    if _meta.get("nav_start_date") and _meta.get("nav_current_date"):
        story.append(Paragraph(
            f"Période d'étude : {_meta['nav_start_date']} → {_meta['nav_current_date']}"
            f"  ·  {_meta.get('nav_n_obs', '—')} observations NAV", S_SMALL))
        story.append(space(4))

    recon = totals.get("reconciliation")
    if recon:
        story.append(Paragraph(f"Réconciliation NAV (as of {recon.get('as_of', '—')})", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        gap_pct = recon.get("gap_pct")
        story.append(_kpi_row([
            (f"P&L FIFO (brut){ccy_lbl}", _fmt_prod(totals.get("total_pnl")),
             "#10b981" if (totals.get("total_pnl") or 0) >= 0 else "#ef4444"),
            (f"Frais cumulés{ccy_lbl}", _fmt_prod(totals.get("fee_drag_prod")), "#ef4444"),
            (f"P&L net estimé{ccy_lbl}", _fmt_prod(totals.get("total_pnl_net_of_fees")),
             "#10b981" if (totals.get("total_pnl_net_of_fees") or 0) >= 0 else "#ef4444"),
            (f"P&L implicite NAV{ccy_lbl}", _fmt_prod(recon.get("nav_implied_pnl_prod")), "#10b981"),
            ("Écart résiduel", f"{gap_pct:+.1f}%" if gap_pct is not None else "—",
             "#f59e0b" if (gap_pct is not None and abs(gap_pct) > 15) else "#10b981"),
        ]))
        story.append(space(8))

        fb = recon.get("fee_breakdown") or {}
        if any(fb.get(k) for k in ("management_fee_prod", "performance_fee_prod", "transaction_cost_prod")):
            mgmt_pct = fb.get("management_fee_pct")
            perf_pct = fb.get("performance_fee_pct")
            txn_pct = fb.get("transaction_cost_pct")
            fee_rows = [
                [_p(f"Gestion ({mgmt_pct}% p.a., accrual quotidien)" if mgmt_pct else "Gestion — non renseigné", S_BODY),
                 _pn(_fmt_prod(fb.get("management_fee_prod"), ccy))],
                [_p(f"Performance ({perf_pct}% sur High Water Mark, {fb.get('performance_fee_events', '—')} plus-hauts, prélevé le jour même)"
                    if perf_pct else "Performance — non renseigné", S_BODY),
                 _pn(_fmt_prod(fb.get("performance_fee_prod"), ccy))],
                [_p(f"Transaction ({txn_pct}% du notionnel par rebalancement)" if txn_pct else "Transaction — non renseigné", S_BODY),
                 _pn(_fmt_prod(fb.get("transaction_cost_prod"), ccy))],
            ]
            story.append(Paragraph("Décomposition des frais", S_SMALL))
            story.append(space(3))
            story.append(_tbl([[_p("Composante", S_HDR), _p("Montant", S_HDR)]] + fee_rows,
                              col_widths=[13.4*cm, 4.0*cm]))
            story.append(space(6))
        else:
            story.append(Paragraph(
                "⚠ Aucun frais renseigné (management_fee_pct / perf_fee_pct / txn_cost_pct) — "
                "l'écart résiduel ci-dessus est probablement surestimé.", S_SMALL))
            story.append(space(6))

        story.append(Paragraph(
            "P&L implicite NAV calculé directement depuis la NAV quotidienne et les flux de "
            "souscription/rachat (Δ Outstanding × NAV à chaque mouvement), indépendamment du "
            "carnet d'ordres. Frais de performance modélisés en High Water Mark journalier "
            "(prélevé uniquement les jours de nouveau plus-haut, pas un accrual continu).", S_SMALL))
        story.append(space(12))

    story.append(Paragraph("P&L par sous-jacent (réalisé + latent, devise produit)", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    rows_all = b.get("per_name", [])
    hdr = [_p("Titre", S_HDR), _p("P&L réalisé", S_HDR), _p("Dont prix", S_HDR),
           _p("Dont FX", S_HDR), _p("P&L latent", S_HDR), _p("P&L total", S_HDR),
           _p("Poids %", S_HDR)]
    tbl_data = [hdr]
    style_extra = []
    for i, r in enumerate(rows_all[:30], 1):
        total = r.get("total_pnl", 0) or 0
        col = colors.HexColor("#10b981") if total >= 0 else colors.HexColor("#ef4444")
        tbl_data.append([
            _p(r["name"][:28], S_BODY),
            Paragraph(_fmt_prod(r.get("realized_pnl")), _sty(f"rp{i}", alignment=TA_RIGHT, fontSize=8,
                      fontName="Helvetica-Bold", textColor=(colors.HexColor("#10b981") if (r.get("realized_pnl") or 0) >= 0 else colors.HexColor("#ef4444")))),
            _pn(_fmt_prod(r.get("price_pnl"))),
            _pn(_fmt_prod(r.get("fx_pnl"))),
            _pn(_fmt_prod(r.get("unreal_pnl"))),
            Paragraph(_fmt_prod(total), _sty(f"tp{i}", alignment=TA_RIGHT, fontSize=8,
                      fontName="Helvetica-Bold", textColor=col)),
            _pn(f"{(r.get('weight') or 0)*100:.2f}%"),
        ])
    story.append(_tbl(tbl_data,
        col_widths=[4.2*cm, 2.4*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.4*cm, 1.8*cm]))
    story.append(space(6))
    story.append(Paragraph(b.get("note", ""), S_SMALL))

    # Quarterly chart
    qchart = _chart_quarterly_pnl(b.get("quarterly_realized", []))
    if qchart:
        story.append(space(12))
        story.append(Paragraph("P&L réalisé par trimestre", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        story.append(qchart)


def _append_block_c(story, c, ccy, space, meta=None):
    rt = c.get("round_trips", {})
    tv = c.get("turnover", {})

    story.append(_kpi_row([
        ("Round-trips clôturés", str(rt.get("count", "—")), "#94a3b8"),
        ("Hit ratio", f"{rt.get('win_rate_pct') or 0:.1f}%",
         "#10b981" if (rt.get("win_rate_pct") or 0) >= 50 else "#f59e0b"),
        ("Profit factor", f"{rt.get('profit_factor') or 0:.2f}",
         "#10b981" if (rt.get("profit_factor") or 0) >= 1 else "#ef4444"),
        ("Durée médiane", f"{rt.get('median_holding_days') or 0:.0f}j", "#60a5fa"),
    ]))
    story.append(space(10))

    # Trading stats table
    story.append(Paragraph("Statistiques de trading (positions clôturées)", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))
    ts_data = [
        [_p("Round-trips", S_BODY),   _pn(str(rt.get("count", "—")))],
        [_p("Hit ratio",   S_BODY),   _pn(f"{rt.get('win_rate_pct') or 0:.1f}%")],
        [_p("P&L moyen gain", S_BODY), _pn(_fmt_prod(rt.get("avg_win"), ccy))],
        [_p("P&L moyen perte",S_BODY), _pn(_fmt_prod(rt.get("avg_loss"), ccy))],
        [_p("Profit factor",  S_BODY), _pn(f"{rt.get('profit_factor') or 0:.2f}")],
        [_p("Durée moy. détention", S_BODY), _pn(f"{rt.get('avg_holding_days') or 0:.1f} jours")],
        [_p("Durée méd. détention", S_BODY), _pn(f"{rt.get('median_holding_days') or 0:.1f} jours")],
        [_p("P&L réalisé total", S_BODY), _pn(_fmt_prod(rt.get("realized_pnl"), ccy))],
    ]
    story.append(_tbl([[_p("Indicateur", S_HDR), _p("Valeur", S_HDR)]] + ts_data,
                      col_widths=[10.4*cm, 7.0*cm]))
    story.append(space(10))

    story.append(Paragraph("Turnover", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))
    tv_data = [
        [_p("Gross traded (devise produit)", S_BODY), _pn(_fmt_prod(tv.get("gross_traded_prod"), ccy))],
        [_p("AUM moyen estimé", S_BODY),              _pn(_fmt_prod(tv.get("avg_aum_prod"), ccy))],
        [_p("Turnover (période entière)", S_BODY),    _pn(f"{(tv.get('turnover_rate') or 0)*100:.1f}%")],
        [_p("Turnover annualisé", S_BODY),            _pn(f"{(tv.get('turnover_annualized') or 0)*100:.1f}%")],
        [_p("Période couverte", S_BODY), _pn(
            f"{(meta or {}).get('nav_start_date', '—')} → {(meta or {}).get('nav_current_date', '—')}"
            f"  ({tv.get('period_days', '—')} jours)")],
    ]
    story.append(_tbl([[_p("Indicateur", S_HDR), _p("Valeur", S_HDR)]] + tv_data,
                      col_widths=[10.4*cm, 7.0*cm]))
    story.append(space(8))

    hold_note = c.get("trading_vs_hold", {}).get("note", "")
    if hold_note:
        story.append(Paragraph(hold_note, S_SMALL))


def _append_block_d(story, d, space, meta=None):
    hd = d.get("holding_distribution", {})
    oh = d.get("order_hygiene", {})
    cm_ = d.get("conviction_matrix", {})
    cutoff = hd.get("long_term_days_cutoff", 180)
    p_params = cm_.get("params", {})
    lt_days  = p_params.get("long_term_days", 180)
    conv_pct = p_params.get("conviction_weight_pct", 4.0)

    # ── KPI row — contextualisé ──────────────────────────────────────────
    story.append(_kpi_row([
        (f"Positions long terme\n(>{lt_days}j)", str(hd.get("long_term_count", "—")), "#10b981"),
        ("Positions tactiques\n(court terme)", str(hd.get("tactical_count", "—")), "#f59e0b"),
        ("Taux d'annulation\n(ordres Discarded)",
         f"{oh.get('discarded_ratio_pct') or 0:.1f}%",
         "#f59e0b" if (oh.get("discarded_ratio_pct") or 0) > 15 else "#94a3b8"),
        ("Durée moy. détention\n(positions clôturées)",
         f"{hd.get('avg_holding_days') or 0:.0f}j", "#60a5fa"),
    ]))
    story.append(space(10))

    _meta = meta or {}
    if _meta.get("nav_start_date") and _meta.get("nav_current_date"):
        story.append(Paragraph(
            f"Période d'étude : {_meta['nav_start_date']} → {_meta['nav_current_date']}"
            f"  ·  {_meta.get('nav_n_obs', '—')} observations NAV", S_SMALL))
        story.append(space(4))

    # ── Intro conceptuel ────────────────────────────────────────────────
    story.append(Paragraph(
        f"<b>Lecture de la matrice :</b> Chaque position clôturée est classée sur deux axes — "
        f"la <b>conviction</b> (poids &gt; {conv_pct}% du portefeuille ET durée &gt; {lt_days} jours) "
        f"et le <b>résultat</b> (P&amp;L positif ou négatif). "
        f"Un gérant discipliné maximise les quadrants gauche (forte conviction) "
        f"et positifs (haut), et minimise les positions en bas à droite (incertitude + perte).",
        _sty("d_intro", fontSize=7.5, textColor=colors.HexColor("#94a3b8"),
             leading=10, spaceAfter=8)))

    # ── Matrice conviction 2×2 — tableau propre ─────────────────────────
    matrix = cm_.get("quadrants", {})
    pnl    = cm_.get("pnl", {})
    counts = cm_.get("counts", {})

    story.append(Paragraph("Matrice conviction × résultat", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    # Axis label row (top)
    ax_style = _sty("d_ax", fontSize=7, textColor=colors.HexColor("#7c3aed"),
                    fontName="Helvetica-Bold", alignment=TA_CENTER)
    ax_right = _sty("d_axr", fontSize=7, textColor=colors.HexColor("#64748b"),
                    fontName="Helvetica-Bold", alignment=TA_CENTER)
    ax_row = Table(
        [[Paragraph("← Forte conviction", ax_style), Paragraph("Faible conviction →", ax_right)]],
        colWidths=[INNER_W/2, INNER_W/2],
        style=TableStyle([("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
                          ("BOTTOMPADDING",(0,0),(-1,-1),2)]))
    story.append(ax_row)

    def _quad_cell(q_key, icon, title, subtitle, bg_hex, txt_hex, top_n=3):
        """Build one 2×2 quadrant cell as a KeepTogether block."""
        cnt = counts.get(q_key, 0)
        pnl_val = pnl.get(q_key) or 0
        pnl_col = "#10b981" if pnl_val >= 0 else "#ef4444"
        rows_inner = [
            Paragraph(f"<b>{icon} {title}</b>",
                      _sty(f"qt_{q_key}", fontSize=8, textColor=colors.HexColor(txt_hex),
                           fontName="Helvetica-Bold", leading=10)),
            Paragraph(subtitle,
                      _sty(f"qs_{q_key}", fontSize=6.5, textColor=colors.HexColor("#64748b"),
                           leading=8, spaceAfter=3)),
            Paragraph(f"<b>{cnt}</b> positions",
                      _sty(f"qc_{q_key}", fontSize=11, textColor=colors.HexColor(txt_hex),
                           fontName="Helvetica-Bold", leading=14)),
            Paragraph(_fmt_prod(pnl_val),
                      _sty(f"qp_{q_key}", fontSize=9, textColor=colors.HexColor(pnl_col),
                           fontName="Helvetica-Bold", leading=11, spaceAfter=4)),
        ]
        for pos in (matrix.get(q_key) or [])[:top_n]:
            pos_pnl = pos.get("total_pnl") or 0
            pos_col = "#10b981" if pos_pnl >= 0 else "#ef4444"
            nm  = (pos.get("name") or pos.get("isin") or "")[:28]
            rows_inner.append(
                Paragraph(f"{nm}  <font color='{pos_col}'><b>{_fmt_prod(pos_pnl)}</b></font>",
                          _sty(f"qi_{q_key}_{nm}", fontSize=6, textColor=colors.HexColor("#64748b"),
                               leading=8)))
        cell_tbl = Table(
            [[r] for r in rows_inner],
            colWidths=[INNER_W/2 - 12],
            style=TableStyle([
                ("BACKGROUND",(0,0),(-1,-1),colors.HexColor(bg_hex)),
                ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),6),
                ("TOPPADDING",(0,0),(0,0),8),    ("BOTTOMPADDING",(-1,-1),(-1,-1),8),
            ]))
        return cell_tbl

    # Row labels (left axis)
    def _ax_v(text, col):
        return Paragraph(text, _sty("axv_"+text, fontSize=7,
                                    textColor=colors.HexColor(col), fontName="Helvetica-Bold",
                                    alignment=TA_CENTER))

    cw = INNER_W / 2
    grid = Table([
        [_quad_cell("conviction_winners", "✓", "Paris gagnants assumés",
                    "Forte conviction · P&L positif", "#052e16", "#10b981"),
         _quad_cell("tactical_winners", "✓", "Coups tactiques réussis",
                    "Faible conviction · P&L positif", "#172554", "#60a5fa")],
        [_quad_cell("stubborn_losers", "✗", "Entêtements coûteux",
                    "Forte conviction · P&L négatif", "#2d0a0a", "#ef4444"),
         _quad_cell("uncertainty", "⚠", "Positions d'incertitude",
                    "Faible conviction · P&L négatif", "#1c1002", "#f59e0b")],
    ], colWidths=[cw, cw],
    style=TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0),  ("BOTTOMPADDING",(0,0),(-1,-1),0),
        ("LINEAFTER",(0,0),(0,-1),1,colors.HexColor("#1e293b")),
        ("LINEBELOW",(0,0),(-1,0),1,colors.HexColor("#1e293b")),
    ]))
    story.append(grid)
    story.append(space(4))
    story.append(Paragraph(
        f"Seuil long terme : {lt_days} jours · Seuil conviction : {conv_pct}% de poids.",
        S_SMALL))

    # ── Auto-interprétation ──────────────────────────────────────────────
    total = sum(counts.get(q, 0) for q in ["conviction_winners","tactical_winners","stubborn_losers","uncertainty"])
    if total > 0:
        winners = counts.get("conviction_winners",0) + counts.get("tactical_winners",0)
        win_pct = round(winners / total * 100)
        unc_pct = round(counts.get("uncertainty",0) / total * 100)
        conv_win_pct = round(counts.get("conviction_winners",0) / total * 100)
        parts = [f"Sur {total} positions clôturées : {winners} gagnantes ({win_pct}%)."]
        if conv_win_pct >= 25:
            parts.append(f"Le gérant génère de la valeur avec conviction ({conv_win_pct}% de paris gagnants assumés).")
        if unc_pct > 35:
            parts.append(f"⚠ {unc_pct}% des positions sont en zone d'incertitude (faible conviction + perte) — signal de décisions non structurées.")
        elif unc_pct < 20:
            parts.append(f"Le taux d'incertitude ({unc_pct}%) est faible — processus de décision discipliné.")
        stub_pnl = pnl.get("stubborn_losers") or 0
        if counts.get("stubborn_losers",0) > 0 and stub_pnl < -50000:
            parts.append(f"Les entêtements coûteux représentent {_fmt_prod(stub_pnl)} — biais comportemental à surveiller.")
        story.append(space(6))
        story.append(Paragraph(" ".join(parts),
                               _sty("d_interp", fontSize=7.5, textColor=colors.HexColor("#94a3b8"),
                                    leading=10, borderPad=0)))

    # Order hygiene
    story.append(space(12))
    story.append(Paragraph("Hygiène des ordres & flip-flop", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))
    hyg_data = [
        [_p("Ordres exécutés (Done)", S_BODY), _pn(str(oh.get("n_done", "—")))],
        [_p("Ordres annulés (Discarded)", S_BODY), _pn(str(oh.get("n_discarded", "—")))],
        [_p("Ratio d'annulation", S_BODY), _pn(f"{oh.get('discarded_ratio_pct') or 0:.1f}%")],
        [_p("Fills partiels", S_BODY), _pn(str(oh.get("n_partial_fills", "—")))],
    ]
    story.append(_tbl([[_p("Indicateur", S_HDR), _p("Valeur", S_HDR)]] + hyg_data,
                      col_widths=[10.4*cm, 7.0*cm]))

    disc_top = oh.get("discarded_top", [])
    if disc_top:
        story.append(space(8))
        story.append(Paragraph("Titres avec le plus d'ordres annulés", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        dt_data = [[_p("Titre", S_HDR), _p("Annulés", S_HDR)]]
        for r in disc_top:
            dt_data.append([_p(r["name"], S_BODY), _pn(str(r["discarded"]))])
        story.append(_tbl(dt_data, col_widths=[13.9*cm, 3.5*cm]))

    # Holding distribution chart
    all_holds = [rt["max_hold_days"] for q in matrix.values()
                 for rt in q if rt.get("max_hold_days")]
    if all_holds:
        story.append(space(12))
        hchart = _chart_holding_dist(all_holds, cutoff)
        if hchart:
            story.append(hchart)


def _append_block_g_brinson(story, bg, space):
    """Render Block G — Brinson-Fachler Attribution."""
    if not bg or not bg.get("available"):
        story.append(Paragraph("Bloc G non disponible.", S_SMALL))
        return

    port_r   = bg.get("port_return_pct", 0)
    bench_r  = bg.get("bench_return_pct", 0)
    active_r = bg.get("active_return_pct", 0)
    alloc    = bg.get("allocation_pct", 0)
    selec    = bg.get("selection_pct", 0)
    inter    = bg.get("interaction_pct", 0)

    p_start = bg.get("period_start", "")
    p_end   = bg.get("period_end", "")
    bench   = bg.get("benchmark_ticker", "")
    n_hold  = bg.get("n_holdings", 0)

    story.append(Paragraph(
        f"Période : {p_start} → {p_end}  ·  Benchmark : {bench}  ·  {n_hold} sous-jacents",
        S_SMALL))
    story.append(space(6))

    # ── KPI row ──────────────────────────────────────────────────────
    active_hex = "#10b981" if active_r >= 0 else "#ef4444"
    story.append(_kpi_row([
        ("Portefeuille",  f"{port_r:+.2f}%",                   "#3b82f6"),
        ("Benchmark",     f"{bench_r:+.2f}%",                  "#94a3b8"),
        ("Retour actif",  f"{active_r:+.2f}%",                 active_hex),
        ("Vérif A+S+I",   f"{bg.get('check_pct', 0):+.2f}%",  "#475569"),
    ]))
    story.append(space(8))

    # ── Réconciliation NAV ────────────────────────────────────────────
    nav_r   = bg.get("nav_return_pct")
    recon   = bg.get("recon_gap_pct")
    n_avail = bg.get("n_holdings", 0)
    n_total = bg.get("n_total_holdings", n_avail)
    if nav_r is not None and recon is not None:
        gap_col = "#f59e0b" if abs(recon) > 2 else "#64748b"
        recon_txt = (
            f"<b>Réconciliation NAV :</b> le rendement portefeuille Brinson ({port_r:+.2f}%) "
            f"est calculé sur {n_avail}/{n_total} titres disponibles dans le Price Store. "
            f"NAV réelle sur la même période : <b>{nav_r:+.2f}%</b>. "
            f"Écart de réconciliation : <font color='{gap_col}'><b>{recon:+.2f}%</b></font>. "
            f"Causes : titres absents du Price Store, différences de pondération, "
            f"FX, dividendes et frais non capturés par les séries de prix."
        )
        story.append(Paragraph(recon_txt,
            _sty("recon", fontSize=7.5, textColor=colors.HexColor("#94a3b8"),
                 leading=11, spaceAfter=4)))
        story.append(space(6))
    else:
        story.append(space(10))

    # ── Brinson waterfall chart ───────────────────────────────────────
    story.append(Paragraph("Décomposition Brinson-Fachler", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import io as _io

        labels    = ["Allocation", "Sélection", "Interaction", "Retour actif"]
        values    = [alloc, selec, inter, active_r]
        bar_cols  = [
            "#3b82f6" if alloc    >= 0 else "#ef4444",
            "#10b981" if selec    >= 0 else "#ef4444",
            "#f59e0b" if inter    >= 0 else "#ef4444",
            "#10b981" if active_r >= 0 else "#ef4444",
        ]

        fig, ax = plt.subplots(figsize=(7, 2.2))
        fig.patch.set_facecolor("#0f172a")
        ax.set_facecolor("#1e293b")

        bars = ax.barh(labels, values, color=bar_cols, height=0.55)
        ax.axvline(0, color="#475569", linewidth=0.8)

        for bar, val in zip(bars, values):
            x = bar.get_width()
            ax.text(x + (0.05 if x >= 0 else -0.05),
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:+.2f}%",
                    va="center", ha="left" if x >= 0 else "right",
                    fontsize=8, color="#f1f5f9")

        ax.tick_params(colors="#94a3b8", labelsize=8)
        ax.set_xlabel("%", color="#94a3b8", fontsize=8)
        for spine in ax.spines.values():
            spine.set_color("#334155")

        buf2 = _io.BytesIO()
        fig.tight_layout(pad=0.5)
        fig.savefig(buf2, format="png", dpi=130, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf2.seek(0)

        img = Image(buf2, width=INNER_W * 0.7, height=INNER_W * 0.22)
        story.append(img)
    except Exception:
        pass

    story.append(space(12))

    # ── Sector table ─────────────────────────────────────────────────
    story.append(Paragraph("Détail par secteur", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    sector_rows = bg.get("sector_rows", [])
    if sector_rows:
        col_w = [3.8*cm, 1.3*cm, 1.3*cm, 1.3*cm, 1.4*cm, 1.4*cm,
                 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm]
        hdr = [_p(h, S_HDR) for h in [
            "Secteur", "w_p%", "w_b%", "Δw%", "R_p%", "R_b%",
            "Alloc", "Sélect", "Inter", "Total"
        ]]
        rows_data = [hdr]
        for r in sector_rows:
            def _cell(v, pos=True):
                c = C_EMERALD if v > 0 else (C_RED if v < 0 else C_MUTED)
                sign = "+" if v > 0 else ""
                return _p(f"{sign}{v:.2f}%",
                          _sty(f"br_{v}", fontSize=7, textColor=c,
                               alignment=TA_RIGHT))
            rows_data.append([
                _p(r["sector"], _sty("brs", fontSize=7, textColor=C_TEXT)),
                _p(f"{r['w_p']:.1f}%", S_NUM_SM),
                _p(f"{r['w_b']:.1f}%", S_NUM_SM),
                _cell(r["active_w"]),
                _cell(r["r_p"]),
                _cell(r["r_b"]),
                _cell(r["allocation"]),
                _cell(r["selection"]),
                _cell(r["interaction"]),
                _cell(r["total"]),
            ])

        tbl = Table(rows_data, colWidths=col_w)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  C_CARD),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  C_FAINT),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_BG, colors.HexColor("#111827")]),
            ("LINEBELOW",    (0, 0), (-1, 0),  0.5, C_BORDER),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("BOX",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ]))
        story.append(tbl)

    story.append(space(14))

    # ── Top/Bottom contributors ────────────────────────────────────────
    top5    = bg.get("top5",    [])
    bottom5 = bg.get("bottom5", [])
    if top5 or bottom5:
        story.append(Paragraph("Classements — Contribution par titre", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))

        def _rank_table(items, title, color):
            story.append(Paragraph(title,
                _sty(f"rk_{title}", fontSize=8, textColor=color, leading=12)))
            story.append(space(3))
            for item in items:
                c_pct = item.get("contribution_pct", 0)
                c_col = C_EMERALD if c_pct >= 0 else C_RED
                sign  = "+" if c_pct >= 0 else ""
                story.append(Paragraph(
                    f"<b>{item['name']}</b>  "
                    f"<font color='#475569'>sect: {item['sector']}  "
                    f"w: {item['weight_pct']:.1f}%  "
                    f"r: {item['return_pct']:+.1f}%  "
                    f"contrib: {sign}{c_pct:.2f}%</font>",
                    _sty(f"ri_{item['name']}", fontSize=7.5, textColor=C_TEXT,
                         leading=11, spaceAfter=2)))

        half = INNER_W / 2 - 0.3*cm
        top_col   = [_p("Top 5 contributeurs", _sty("th", fontName="Helvetica-Bold",
                        fontSize=8, textColor=C_EMERALD))]
        bot_col   = [_p("Bottom 5 contributeurs", _sty("bh", fontName="Helvetica-Bold",
                        fontSize=8, textColor=C_RED))]

        for item in (top5 or []):
            c_pct = item.get("contribution_pct", 0)
            top_col.append(_p(
                f"{item['name']}  w:{item['weight_pct']:.1f}%  "
                f"r:{item['return_pct']:+.1f}%  → {c_pct:+.2f}%",
                _sty("tc", fontSize=7, textColor=C_EMERALD, leading=10, spaceAfter=2)))
        for item in (bottom5 or []):
            c_pct = item.get("contribution_pct", 0)
            bot_col.append(_p(
                f"{item['name']}  w:{item['weight_pct']:.1f}%  "
                f"r:{item['return_pct']:+.1f}%  → {c_pct:+.2f}%",
                _sty("bc", fontSize=7, textColor=C_RED, leading=10, spaceAfter=2)))

        side_tbl = Table(
            [[Table([[r] for r in top_col], colWidths=[half]),
              Table([[r] for r in bot_col], colWidths=[half])]],
            colWidths=[half, half],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]),
        )
        story.append(side_tbl)

    story.append(space(12))

    # ── Méthodologie ─────────────────────────────────────────────────
    story.append(Paragraph("Note méthodologique", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(4))
    story.append(Paragraph(bg.get("methodology_note", ""), S_SMALL))
    story.append(Paragraph(
        f"Poids portefeuille : {bg.get('weights_method', '')}  ·  "
        f"Poids benchmark : {bg.get('bench_weight_method', '')}",
        S_SMALL))
    story.append(space(4))


def _append_block_f_replicability(story, block_f, space):
    """Render Block F — Réplicabilité de la stratégie."""
    if not block_f or not block_f.get("available"):
        story.append(Paragraph(
            f"⚠  {block_f.get('error', 'Bloc F non disponible.')}" if block_f else
            "⚠  Bloc F — Réplicabilité non calculé (Bloc A requis).",
            S_WARN))
        return

    score      = block_f.get("score", 0)
    ci_low     = block_f.get("score_ci_low", score)
    ci_high    = block_f.get("score_ci_high", score)
    profile    = block_f.get("profile", "")
    r2_pct     = block_f.get("r2_pct", 0)
    alpha_a    = block_f.get("alpha_ann_pct", 0) or 0
    alpha_t    = block_f.get("alpha_tstat", 0) or 0
    rep_tot    = block_f.get("replicant_total_pct", 0) or 0
    amc_tot    = block_f.get("amc_total_pct", 0) or 0
    gap        = block_f.get("alpha_gap_pct", 0) or 0
    n_obs      = block_f.get("n_obs", 0)
    period_start = block_f.get("period_start", "")
    period_end   = block_f.get("period_end", "")
    comps      = block_f.get("score_components") or {}

    # ── Période et profil ─────────────────────────────────────────────
    story.append(Paragraph(
        f"Période : {period_start} → {period_end}  ·  {n_obs} observations  ·  Profil : {profile}",
        S_SMALL))
    story.append(space(6))

    # ── Score gauge-style et KPIs ─────────────────────────────────────
    score_color = "#10b981" if score < 40 else "#f59e0b" if score < 70 else "#60a5fa"
    story.append(_kpi_row([
        ("Score réplicabilité", f"{score}/100", score_color),
        ("IC 95% score",        f"[{ci_low} – {ci_high}]", "#64748b"),
        ("R² factoriel",        f"{r2_pct:.1f}%", "#60a5fa"),
        ("Écart AMC vs réplicant", f"{gap:+.2f}%", "#10b981" if gap >= 0 else "#ef4444"),
    ]))
    story.append(space(8))

    # ── Tableau performances comparées ────────────────────────────────
    story.append(Paragraph("Performances comparées", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(4))

    def _cv(v, good_pos=True):
        if v is None:
            return _pn("—")
        col = colors.HexColor("#10b981" if (v >= 0) == good_pos else "#ef4444")
        return Paragraph(f"{v:+.2f}%",
                         _sty("fv", alignment=TA_RIGHT, fontSize=8,
                              fontName="Helvetica-Bold", textColor=col))

    perf_data = [
        [_p("Métrique", S_HDR), _p("AMC réel", S_HDR), _p("Réplicant", S_HDR), _p("Écart", S_HDR)],
        [_p("Performance totale", S_BODY), _cv(amc_tot), _cv(rep_tot), _cv(gap)],
        [_p("R² modèle factoriel", S_BODY),
         _pn(f"{r2_pct:.1f}%"), _pn("100%"), _pn(f"{100 - r2_pct:.1f}% idiosync.")],
        [_p("Alpha annualisé", S_BODY),
         _cv(alpha_a), _pn("0.00%"),
         Paragraph(f"t = {alpha_t:.2f}", _sty("ts", alignment=TA_RIGHT, fontSize=8,
             textColor=colors.HexColor("#10b981" if abs(alpha_t) >= 2 else "#f59e0b")))],
    ]
    story.append(_tbl(perf_data, col_widths=[5.5*cm, 3.5*cm, 3.5*cm, 4.9*cm]))
    story.append(space(8))

    # ── Décomposition du score ────────────────────────────────────────
    story.append(Paragraph("Décomposition du score de réplicabilité", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(4))
    sc_data = [
        [_p("Composante", S_HDR), _p("Pondération", S_HDR),
         _p("Score brut", S_HDR), _p("Contribution", S_HDR)],
        [_p("R² (variance expliquée)", S_BODY), _pn("40%"),
         _pn(f"{comps.get('r2_component', 0):.1f}/100"),
         _pn(f"{0.40 * comps.get('r2_component', 0):.1f}")],
        [_p("Couverture de performance", S_BODY), _pn("35%"),
         _pn(f"{comps.get('perf_coverage', 0):.1f}/100"),
         _pn(f"{0.35 * comps.get('perf_coverage', 0):.1f}")],
        [_p("Alpha non-significatif", S_BODY), _pn("25%"),
         _pn(f"{comps.get('alpha_insig', 0):.1f}/100"),
         _pn(f"{0.25 * comps.get('alpha_insig', 0):.1f}")],
        [_p("Score total", _sty("sbt", fontName="Helvetica-Bold", fontSize=8, textColor=C_TEXT)),
         _pn("100%"), _pn("—"),
         Paragraph(f"{score}/100",
                   _sty("stot", alignment=TA_RIGHT, fontSize=9,
                        fontName="Helvetica-Bold",
                        textColor=colors.HexColor(score_color)))],
    ]
    story.append(_tbl(sc_data, col_widths=[6.0*cm, 2.8*cm, 3.0*cm, 5.6*cm]))
    story.append(space(10))

    # ── Graphique AMC vs Réplicant ────────────────────────────────────
    rep_records = block_f.get("replicant_nav") or []
    amc_records = block_f.get("amc_nav") or []
    if rep_records:
        story.append(Paragraph("AMC réel vs Réplicant factoriel (base 100)", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        try:
            story.append(_chart_replicant_vs_amc(rep_records, amc_records))
        except Exception:
            pass
        story.append(space(8))

    # ── Graphique contributions factorielles ──────────────────────────
    factor_contribs = block_f.get("factor_contributions") or []
    if factor_contribs:
        story.append(Paragraph("Contribution de chaque facteur à la performance du réplicant", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        try:
            img = _chart_factor_contribs(factor_contribs)
            if img:
                story.append(img)
        except Exception:
            pass
        story.append(space(6))

        fc_data = [[_p("Facteur", S_HDR), _p("Bêta", S_HDR),
                    _p("Contribution cumulée", S_HDR)]]
        for fc in factor_contribs:
            cv = float(fc.get("contribution_pct") or 0)
            fc_data.append([
                _p(fc.get("name", ""), S_BODY),
                _pn(f"{fc.get('beta', 0):+.4f}"),
                _cv(cv),
            ])
        story.append(_tbl(fc_data, col_widths=[5.5*cm, 4.5*cm, 7.4*cm]))
        story.append(space(8))

    # ── Interprétation ────────────────────────────────────────────────
    interp = block_f.get("interpretation", "")
    if interp:
        story.append(Paragraph("Interprétation", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        story.append(Paragraph(interp, _sty("ai_interp", fontSize=8.5,
                                            textColor=C_MUTED, leading=13,
                                            alignment=TA_JUSTIFY)))
        story.append(space(6))

    # ── Théorie, Score et Limites ────────────────────────────────────
    story.append(space(14))
    story.append(Paragraph("Théorie, Score & Limites", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    # Score : méthodologie interne
    story.append(Paragraph(
        "<b>Score STRUCTURA interne (méthodologie non standardisée)</b>",
        _sty("sc_hdr", fontSize=8, textColor=C_AMBER, leading=12)))
    story.append(space(3))
    story.append(Paragraph(
        "Score = 40% × R² + 35% × min(Perf_réplicant / Perf_AMC, 1) + 25% × (1 − min(|t_alpha|/3, 1))  "
        f"  →  {score}/100   IC 95% : [{ci_low} – {ci_high}]  "
        "(IC basé sur l'erreur d'échantillonnage du R² par méthode delta.)",
        _sty("sc_form", fontSize=7.5, textColor=C_FAINT, leading=11)))
    story.append(space(3))
    story.append(Paragraph(
        "Le R² mesure la fraction de variance expliquée ; le ratio de performance mesure combien "
        "du rendement total est capturé par le réplicant ; le terme alpha pénalise les stratégies "
        "dont l'alpha est statistiquement significatif (significatif = peu réplicable).",
        S_SMALL))
    story.append(space(8))

    # Construction du réplicant
    story.append(Paragraph(
        "<b>Construction du portefeuille réplicant</b>",
        _sty("rep_hdr", fontSize=8, textColor=C_BLUE, leading=12)))
    story.append(space(3))
    story.append(Paragraph(
        "R_réplicant(t) = RF(t) + Σ βᵢ × Fᵢ(t) — reconstruction théorique <i>ex-post</i> à partir "
        "des bêtas estimés sur la même période. Les facteurs Fama-French sont des portefeuilles "
        "long-short dollar-neutres (SMB = long small caps / short large caps ; HML = long value / "
        "short growth ; MOM = long gagnants récents / short perdants). Ils ne sont pas directement "
        "investissables en ETF. L'approximation pratique serait un panier d'ETFs smart-beta "
        "(MTUM, VLUE, IWM…) pondéré selon les bêtas, mais avec des coûts de transaction réels.",
        S_SMALL))
    story.append(space(8))

    # Limites
    story.append(Paragraph(
        "<b>Limites à prendre en compte</b>",
        _sty("lim_hdr", fontSize=8, textColor=C_AMBER, leading=12)))
    story.append(space(3))
    limits = [
        ("Biais ex-post", "Les bêtas sont estimés sur la même période que la comparaison. "
         "En temps réel, un investisseur ne les connaîtrait qu'avec retard — "
         "la réplication effective aurait nécessité des rééquilibrages."),
        ("Facteurs en USD", "Les données Ken French sont libellées en USD. Pour un AMC en CHF/EUR, "
         "les bêtas absorbent une part du risque de change non séparable des expositions de style."),
        ("Bêtas statiques", "La régression utilise une moyenne sur toute la fenêtre. Si le gérant a "
         "changé de style, les bêtas moyens masquent cette évolution (cf. bêtas glissants, Bloc A)."),
        ("Score non standardisé", "La pondération 40/35/25% est une convention interne. "
         "D'autres pondérations donneraient un score différent — seule la direction compte."),
    ]
    for title, desc in limits:
        story.append(Paragraph(
            f"<b>⚠ {title} :</b> {desc}",
            _sty(f"lim_{title}", fontSize=7.5, textColor=C_FAINT, leading=11,
                 spaceBefore=3)))
    story.append(space(4))


def _append_block_e_vag(story, tva, attribution, meta, space):
    """Render the VAG section (B&H vs real NAV + attribution)."""
    ccy = (meta or {}).get("currency", "")

    # ── Période et métriques clés ──────────────────────────────────────
    period_label = tva.get("nav_period_label", "")
    start_date   = tva.get("start_date", "")
    end_date     = tva.get("end_date", "")
    bh_met   = (tva.get("metrics") or {}).get("bh",   {}) or {}
    real_met = (tva.get("metrics") or {}).get("real",  {}) or {}
    vag_met  = (tva.get("metrics") or {}).get("vag",   {}) or {}

    if period_label:
        story.append(Paragraph(f"Période : {period_label}  ·  {start_date} → {end_date}", S_SMALL))
        story.append(space(6))

    # ── KPI 3 colonnes ────────────────────────────────────────────────
    bh_tot   = bh_met.get("total_pct", 0) or 0
    real_tot = real_met.get("total_pct", 0) or 0
    vag_tot  = vag_met.get("total_pct", 0) or 0

    story.append(_kpi_row([
        ("AMC réel",               f"{real_tot:+.2f}%" if real_met else "—",
         "#10b981" if real_tot >= 0 else "#ef4444"),
        ("Réf. Inertiel",          f"{bh_tot:+.2f}%",
         "#60a5fa" if bh_tot >= 0 else "#f87171"),
        ("Val. Ajoutée Gestion",   f"{vag_tot:+.2f}%" if vag_met else "—",
         "#f59e0b" if abs(vag_tot) > 0 else "#94a3b8"),
        ("AUM ref.",               _fmt_prod(tva.get("aum_for_attr") or (meta.get("total_aum")), ccy),
         "#94a3b8"),
    ]))
    story.append(space(10))

    # ── Graphique AMC vs Référentiel Inertiel ─────────────────────────
    bh_records   = tva.get("bh_nav") or []
    real_records = tva.get("real_nav")
    if bh_records:
        story.append(Paragraph("AMC réel vs Référentiel Inertiel (base 100)", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        try:
            story.append(_chart_nav_bh(bh_records, real_records, bh_label="Référentiel Inertiel"))
        except Exception:
            pass
        story.append(space(8))

    # ── Tableau métriques complet si real_nav disponible ────────────────
    if real_met and bh_met:
        story.append(Paragraph("Métriques comparées", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        hdr = [_p("Métrique", S_HDR), _p("AMC réel", S_HDR),
               _p("Réf. Inertiel", S_HDR), _p("Val. Ajoutée Gestion", S_HDR)]
        def _c(v, good_pos=True):
            if v is None:
                return _pn("—")
            col = colors.HexColor("#10b981" if (v >= 0) == good_pos else "#ef4444")
            return Paragraph(f"{v:+.2f}%" if abs(v) < 1000 else f"{v:+.0f}%",
                             _sty("tv", alignment=TA_RIGHT, fontSize=8,
                                  fontName="Helvetica-Bold", textColor=col))
        tbl_data = [
            hdr,
            [_p("Perf. totale", S_BODY),
             _pn(f"{real_tot:+.2f}%"), _pn(f"{bh_tot:+.2f}%"),
             _c(vag_met.get("total_pct"))],
            [_p("Perf. annualisée", S_BODY),
             _pn(f"{real_met.get('ann_ret_pct',0):+.2f}%"),
             _pn(f"{bh_met.get('ann_ret_pct',0):+.2f}%"),
             _c(vag_met.get("ann_ret_pct"))],
            [_p("Volatilité ann.", S_BODY),
             _pn(f"{real_met.get('ann_vol_pct',0):.2f}%"),
             _pn(f"{bh_met.get('ann_vol_pct',0):.2f}%"), _pn("—")],
            [_p("Sharpe", S_BODY),
             _pn(f"{real_met.get('sharpe',0):.3f}"),
             _pn(f"{bh_met.get('sharpe',0):.3f}"),
             _c(vag_met.get("sharpe_diff"), good_pos=True)],
            [_p("Max Drawdown", S_BODY),
             _pn(f"{real_met.get('max_dd_pct',0):.2f}%"),
             _pn(f"{bh_met.get('max_dd_pct',0):.2f}%"),
             _c(vag_met.get("max_dd_diff"), good_pos=False)],
        ]
        story.append(_tbl(tbl_data, col_widths=[4.5*cm, 3.6*cm, 3.6*cm, 5.7*cm]))
        story.append(space(6))

    # ── Poids B&H ──────────────────────────────────────────────────────
    bh_weights = tva.get("bh_weights") or {}
    if bh_weights:
        story.append(space(10))
        story.append(Paragraph("Poids initiaux — Référentiel Inertiel", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        w_items = sorted(bh_weights.items(), key=lambda x: -x[1])[:20]
        w_data = [[_p("Sous-jacent", S_HDR), _p("Poids initial", S_HDR)]]
        for name, w in w_items:
            w_data.append([_p(name[:40], S_BODY), _pn(f"{w*100:.2f}%")])
        story.append(_tbl(w_data, col_widths=[13.5*cm, 3.9*cm]))
        story.append(space(6))

    # FX note
    fx_applied = tva.get("fx_applied") or []
    if fx_applied:
        pairs = ", ".join(f"{f['from']}/{f['to']}" for f in fx_applied[:6])
        story.append(Paragraph(f"Conversions FX appliquées : {pairs}.", S_SMALL))
        story.append(space(4))

    # ── Attribution si disponible ──────────────────────────────────────
    if attribution and not attribution.get("error"):
        story.append(space(14))
        story.append(Paragraph("Attribution — Timing des achats & Sélection des sorties", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))

        aum_attr = attribution.get("aum", 0)
        t_pct = attribution.get("timing_pct", 0) or 0
        e_pct = attribution.get("exits_pct", 0) or 0
        vag_pct = attribution.get("vag_pct", 0) or 0

        story.append(_kpi_row([
            ("Timing achats",     f"{t_pct:+.2f}%",
             "#10b981" if t_pct >= 0 else "#ef4444"),
            ("Sélection sorties", f"{e_pct:+.2f}%",
             "#10b981" if e_pct >= 0 else "#ef4444"),
            ("Val. Ajoutée Gest.", f"{vag_pct:+.2f}%",
             "#f59e0b"),
            ("AUM référence",     _fmt_prod(aum_attr, ccy), "#94a3b8"),
        ]))
        story.append(space(8))
        story.append(Paragraph(
            f"Basé sur {attribution.get('n_orders',0)} ordres exécutés · "
            f"{attribution.get('n_underlyings',0)} sous-jacents · "
            f"Période : {attribution.get('period_start','')} → {attribution.get('period_end','')}",
            S_SMALL))
        story.append(space(8))

        per_u = attribution.get("per_underlying") or []
        if per_u:
            story.append(Paragraph("Contribution par sous-jacent (% AUM)", S_SECTION))
            story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
            story.append(space(4))
            ua_hdr = [_p("Titre", S_HDR), _p("Timing achats", S_HDR),
                      _p("Sél. sorties", S_HDR), _p("Total", S_HDR)]
            ua_data = [ua_hdr]
            for r in per_u[:25]:
                def _vc(v):
                    c = colors.HexColor("#10b981" if (v or 0) >= 0 else "#ef4444")
                    return Paragraph(f"{v:+.4f}%" if v is not None else "—",
                                     _sty("uc", alignment=TA_RIGHT, fontSize=8,
                                          fontName="Helvetica-Bold", textColor=c))
                ua_data.append([
                    _p(r.get("name","")[:30], S_BODY),
                    _vc(r.get("timing_pct")),
                    _vc(r.get("exits_pct")),
                    _vc(r.get("vag_pct")),
                ])
            story.append(_tbl(ua_data, col_widths=[6.4*cm, 3.6*cm, 3.6*cm, 3.8*cm]))

        # Top trades
        top_t = attribution.get("top_trades") or []
        if top_t:
            story.append(space(12))
            story.append(Paragraph("Top 10 trades par impact", S_SECTION))
            story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
            story.append(space(4))
            tt_hdr = [_p("Date", S_HDR), _p("Sens", S_HDR), _p("Titre", S_HDR),
                      _p("Qté", S_HDR), _p("Exec.", S_HDR), _p("Final", S_HDR),
                      _p("Impact", S_HDR)]
            tt_data = [tt_hdr]
            for t in top_t[:10]:
                cp = t.get("contribution_pct") or 0
                cc = colors.HexColor("#10b981" if cp >= 0 else "#ef4444")
                tt_data.append([
                    _p(str(t.get("date",""))[:10], S_SMALL),
                    Paragraph(t.get("side",""),
                              _sty("ts2", fontSize=7, fontName="Helvetica-Bold",
                                   textColor=colors.HexColor("#60a5fa" if t.get("side")=="BUY" else "#f97316"))),
                    _p(t.get("name","")[:22], S_BODY),
                    _pn(f"{abs(t.get('qty',0)):.0f}"),
                    _pn(f"{t.get('price_exec',0):.1f}"),
                    _pn(f"{t.get('price_terminal',0):.1f}"),
                    Paragraph(f"{cp:+.4f}%", _sty("tc2", alignment=TA_RIGHT, fontSize=8,
                              fontName="Helvetica-Bold", textColor=cc)),
                ])
            story.append(_tbl(tt_data,
                col_widths=[2.0*cm, 1.4*cm, 4.0*cm, 1.6*cm, 2.0*cm, 2.0*cm, 2.4*cm]))

    story.append(space(8))
    story.append(Paragraph(tva.get("bh_note", ""), S_SMALL))


def _append_confidence(story, confidence, space):
    story.append(Paragraph("Confiance dans les Résultats & Limites des Données", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    overall = confidence.get("overall_pct", 0)
    col_overall = "#10b981" if overall >= 80 else "#f59e0b" if overall >= 60 else "#ef4444"
    # Single centered confidence score — no empty filler columns
    badge = Table(
        [[
            Paragraph(f"{overall:.0f}%",
                      _sty("ov_score", fontSize=28, fontName="Helvetica-Bold",
                           textColor=colors.HexColor(col_overall),
                           alignment=TA_CENTER, leading=34)),
            Paragraph(confidence.get("narrative", ""),
                      _sty("ov_narr", fontSize=8, textColor=C_MUTED,
                           leading=12, alignment=TA_LEFT)),
        ]],
        colWidths=[3.5*cm, INNER_W - 3.5*cm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), C_CARD),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#111827")),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (0, 0), 10),
            ("RIGHTPADDING", (0, 0), (0, 0), 10),
            ("LEFTPADDING",  (1, 0), (1, 0), 14),
            ("RIGHTPADDING", (1, 0), (1, 0), 10),
            ("TOPPADDING",   (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
            ("BOX", (0, 0), (-1, -1), 0.4, C_BORDER),
            ("LINEAFTER", (0, 0), (0, 0), 0.4, C_BORDER),
        ]),
    )
    story.append(badge)
    story.append(space(8))
    # Label below the badge
    story.append(Paragraph("Confiance globale estimée",
                            _sty("ov_lbl", fontSize=7, textColor=C_FAINT,
                                 alignment=TA_LEFT)))
    story.append(space(10))

    rows_conf = confidence.get("rows", [])
    if rows_conf:
        story.append(Paragraph("Tableau de confiance par dimension", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        hdr = [_p("Dimension", S_HDR), _p("✓", S_HDR), _p("Confiance", S_HDR),
               _p("Données manquantes / limites", S_HDR)]
        tbl_data = [hdr]
        for r in rows_conf:
            feas = "✓" if r.get("feasible") else "—"
            conf_v = r.get("confidence_pct", 0)
            ccol = colors.HexColor("#10b981" if conf_v >= 80 else "#f59e0b" if conf_v >= 60 else "#ef4444")
            miss = r.get("missing_data") or "—"
            tbl_data.append([
                _p(r.get("dimension", ""), S_BODY),
                Paragraph(feas, _sty("fe", alignment=TA_CENTER, fontName="Helvetica-Bold",
                          textColor=colors.HexColor("#10b981") if r.get("feasible") else C_FAINT)),
                Paragraph(f"{conf_v:.0f}%" if conf_v else "N/A",
                          _sty("cv", alignment=TA_RIGHT, fontName="Helvetica-Bold",
                               fontSize=8, textColor=ccol)),
                _p(miss[:90] + ("…" if len(miss) > 90 else ""), S_SMALL),
            ])
        story.append(_tbl(tbl_data,
            col_widths=[5.8*cm, 1.2*cm, 1.9*cm, 8.5*cm]))
        story.append(space(6))
        story.append(Paragraph(confidence.get("coverage_note", ""), S_SMALL))


def _chart_timing_distributions(dist_entry: dict, dist_exit: dict,
                                dist_global: dict) -> Image:
    """Histograms of entry, exit and global timing scores."""
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.4), facecolor="#0f172a")
    configs = [
        (axes[0], dist_entry,  "Scores Entrée (BUY)",  "#60a5fa"),
        (axes[1], dist_exit,   "Scores Sortie (SELL)", "#34d399"),
        (axes[2], dist_global, "Score Global",         "#a78bfa"),
    ]
    for ax, dist, title, color in configs:
        _dark_axes(ax)
        centers = dist.get("bin_centers", [])
        counts  = dist.get("counts", [])
        if centers and counts:
            ax.bar(centers, counts, width=0.08, color=color, alpha=0.80, edgecolor="#0f172a")
            ax.axvline(0.5, color="#f59e0b", linewidth=1.2, linestyle="--",
                       label="Hasard = 0.5")
        ax.set_xlim(0, 1)
        ax.set_title(title, fontsize=7.5, color="#94a3b8", pad=4)
        ax.set_xlabel("Score (0 = pire · 1 = meilleur)", fontsize=6.5, color="#64748b")
        ax.set_ylabel("Nbre de trades", fontsize=6.5, color="#64748b")
        ax.legend(fontsize=6, framealpha=0, labelcolor="#94a3b8")
    fig.tight_layout(pad=1.5)
    fig.patch.set_facecolor("#0f172a")
    return _fig_to_image(fig, 17, 5.5)


def _chart_alpha_distributions(stats_by_horizon: dict) -> Image:
    """4-panel histogram of alpha distributions per horizon."""
    horizons = [h for h in ("1M", "3M", "6M", "12M")
                if (stats_by_horizon.get(h) or {}).get("available")]
    n = len(horizons)
    if n == 0:
        return None
    cols = min(n, 4)
    fig, axes = plt.subplots(1, cols, figsize=(9.5, 3.4), facecolor="#0f172a")
    if cols == 1:
        axes = [axes]
    palette = ["#60a5fa", "#34d399", "#f59e0b", "#a78bfa"]
    for i, h in enumerate(horizons):
        ax = axes[i]
        dist = (stats_by_horizon[h] or {}).get("distribution", {})
        _dark_axes(ax)
        centers = dist.get("bin_centers", [])
        counts  = dist.get("counts", [])
        if centers and counts:
            width = (centers[1] - centers[0]) * 0.8 if len(centers) > 1 else 0.03
            bar_colors = [palette[i] if c > 0 else "#ef4444" for c in centers]
            ax.bar(centers, counts, width=width, color=bar_colors, alpha=0.80,
                   edgecolor="#0f172a")
            ax.axvline(0, color="#f59e0b", linewidth=1.2, linestyle="--", label="α=0")
        alpha_m = (stats_by_horizon[h] or {}).get("alpha_mean", 0)
        pct_pos = dist.get("pct_positive", 0)
        ax.set_title(f"Alpha {h}  (moy {alpha_m*100:+.1f}%  {pct_pos:.0f}% >0)",
                     fontsize=7.5, color="#94a3b8", pad=4)
        ax.set_xlabel("Alpha vs benchmark", fontsize=6.5, color="#64748b")
        ax.set_ylabel("Nbre d'achats", fontsize=6.5, color="#64748b")
        ax.legend(fontsize=6, framealpha=0, labelcolor="#94a3b8")
    for j in range(cols, 4):
        if j < len(axes):
            axes[j].set_visible(False)
    fig.tight_layout(pad=1.5)
    fig.patch.set_facecolor("#0f172a")
    return _fig_to_image(fig, 17, 5.5)


def _append_block_i_stockpicking(story, bi: dict, space, meta=None):
    """Render Block I — Stock Picking Score."""
    if not bi.get("available"):
        story.append(Paragraph(f"⚠  {bi.get('error', 'Données non disponibles.')}", S_WARN))
        return

    warn = bi.get("warning")
    if warn:
        story.append(Paragraph(f"⚠  {warn}", S_WARN))
        story.append(space(4))

    score = bi.get("score", 0)
    def _score_col(s):
        if s >= 60: return "#10b981"
        if s >= 45: return "#f59e0b"
        return "#ef4444"

    global_alpha = bi.get("global_alpha_mean", 0) or 0
    global_sr    = bi.get("global_success_rate", 0) or 0
    cov          = bi.get("coverage_pct", 0)
    ir           = bi.get("information_ratio", 0) or 0

    story.append(_kpi_row([
        ("Score /100",      str(score),                            _score_col(score)),
        ("Alpha moyen",     f"{global_alpha*100:+.2f}%",          _score_col(score)),
        ("Taux de succès",  f"{global_sr*100:.0f}%",              "#60a5fa"),
        ("Couverture",      f"{cov:.0f}%",                        "#64748b"),
    ]))
    story.append(space(8))

    _meta = meta or {}
    if _meta.get("nav_start_date") and _meta.get("nav_current_date"):
        story.append(Paragraph(
            f"Période d'étude : {_meta['nav_start_date']} → {_meta['nav_current_date']}"
            f"  ·  {bi.get('n_buys_analyzed', '—')} achats analysés", S_SMALL))
        story.append(space(4))

    # ── Stats by horizon table ────────────────────────────────────────────
    stats = bi.get("stats_by_horizon") or {}
    horizon_keys = [h for h in ("1M", "3M", "6M", "12M")]

    hdr = [_p("Horizon", S_HDR), _p("n achats", S_HDR),
           _p("Alpha moy.", S_HDR), _p("Alpha méd.", S_HDR),
           _p("Taux succès", S_HDR), _p("Sigma alpha", S_HDR)]
    rows = [hdr]
    for h in horizon_keys:
        hs = stats.get(h) or {}
        if not hs.get("available"):
            rows.append([_p(h, S_BODY), _pn("—"), _pn("—"), _pn("—"), _pn("—"), _pn("—")])
            continue
        am = hs.get("alpha_mean", 0)
        col = "#10b981" if am > 0 else "#ef4444"
        rows.append([
            _p(h, S_BODY),
            _pn(str(hs.get("n", "—"))),
            Paragraph(f"{am*100:+.2f}%",
                      _sty(f"am{h}", fontSize=8, textColor=colors.HexColor(col),
                           alignment=TA_RIGHT)),
            Paragraph(f"{(hs.get('alpha_median') or 0)*100:+.2f}%",
                      _sty(f"med{h}", fontSize=8,
                           textColor=colors.HexColor("#10b981" if (hs.get("alpha_median") or 0) > 0 else "#ef4444"),
                           alignment=TA_RIGHT)),
            _pn(f"{(hs.get('success_rate') or 0)*100:.0f}%"),
            _pn(f"{(hs.get('alpha_std') or 0)*100:.2f}%"),
        ])

    # Add global row
    tstat = bi.get("tstat_alpha", 0) or 0
    pval  = bi.get("pvalue_alpha", 1) or 1
    rows.append([
        _p("Global pondéré", _sty("gbold", fontName="Helvetica-Bold", fontSize=8,
                                  textColor=C_TEXT)),
        _pn(str(bi.get("n_buys_analyzed", "—"))),
        Paragraph(f"{global_alpha*100:+.2f}%",
                  _sty("ga", fontSize=8, fontName="Helvetica-Bold",
                       textColor=colors.HexColor(_score_col(score)), alignment=TA_RIGHT)),
        _pn("—"),
        Paragraph(f"{global_sr*100:.0f}%",
                  _sty("gsr", fontSize=8, fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#60a5fa"), alignment=TA_RIGHT)),
        _pn(f"IR={ir:+.2f}"),
    ])
    story.append(_tbl(rows, col_widths=[3.0*cm, 2.0*cm, 3.0*cm, 3.0*cm, 2.8*cm, 3.6*cm]))
    story.append(space(6))

    # t-stat / p-value note
    story.append(Paragraph(
        f"Test t (vs µ₀=0) : t={tstat:+.3f}  p={pval:.4f}  "
        f"— benchmark : {bi.get('benchmark_ticker', '—')}  "
        f"({'disponible' if bi.get('benchmark_available') else 'indisponible — retour brut'}).",
        S_SMALL))
    story.append(space(8))

    # ── Interpretation ────────────────────────────────────────────────────
    interp = bi.get("interpretation", "")
    if interp:
        story.append(Paragraph(interp, _sty("si", fontSize=8, textColor=C_TEXT,
                                            leading=12.5, spaceAfter=4,
                                            alignment=TA_JUSTIFY)))
        story.append(space(8))

    # ── Alpha distribution charts ─────────────────────────────────────────
    chart = _chart_alpha_distributions(stats)
    if chart:
        story.append(Paragraph("Distribution des Alphas par Horizon", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        story.append(chart)
        story.append(space(4))
        story.append(Paragraph(
            "La ligne jaune (α=0) représente la performance du benchmark. "
            "Les barres à droite de 0 indiquent une surperformance du titre sélectionné.",
            S_SMALL))
        story.append(space(12))

    # ── Best / worst ideas ────────────────────────────────────────────────
    def _ideas_table(ideas_list, title, positive):
        if not ideas_list:
            return
        col = "#10b981" if positive else "#ef4444"
        story.append(Paragraph(title, _sty("ih", fontName="Helvetica-Bold",
                                           fontSize=8.5, textColor=C_BLUE)))
        story.append(space(3))
        hdr2 = [_p("Date achat", S_HDR), _p("Titre", S_HDR),
                _p("ISIN", S_HDR), _p("Alpha 1M", S_HDR), _p("Alpha 3M", S_HDR),
                _p("Alpha 6M", S_HDR), _p("Alpha 12M", S_HDR), _p("Alpha pondéré", S_HDR)]
        rows2 = [hdr2]
        for t in ideas_list:
            hz = t.get("horizons") or {}
            def _ah(h):
                d = hz.get(h, {})
                v = d.get("alpha") if d.get("available") else None
                if v is None: return _p("—", S_SMALL)
                c = "#10b981" if v > 0 else "#ef4444"
                return Paragraph(f"{v*100:+.1f}%",
                                 _sty(f"a{h}{t.get('date','')}", fontSize=7.5,
                                      textColor=colors.HexColor(c), alignment=TA_RIGHT))
            aw = t.get("alpha_weighted") or 0
            rows2.append([
                _p(t.get("date", ""), S_SMALL),
                _p(str(t.get("name", ""))[:28], S_BODY),
                _p(str(t.get("isin", ""))[:14], S_SMALL),
                _ah("1M"), _ah("3M"), _ah("6M"), _ah("12M"),
                Paragraph(f"{aw*100:+.1f}%",
                          _sty("paw", fontSize=8, fontName="Helvetica-Bold",
                               textColor=colors.HexColor(col), alignment=TA_RIGHT)),
            ])
        story.append(_tbl(rows2, col_widths=[2.0*cm, 4.2*cm, 2.0*cm,
                                              1.9*cm, 1.9*cm, 1.9*cm, 1.9*cm, 2.6*cm]))
        story.append(space(8))

    best_ideas  = bi.get("best_ideas") or []
    worst_ideas = bi.get("worst_ideas") or []
    if best_ideas or worst_ideas:
        story.append(Paragraph("Meilleures et Pires Idées de Sélection", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
    _ideas_table(best_ideas,  "Meilleures idées — alpha pondéré le plus élevé", True)
    _ideas_table(worst_ideas, "Pires idées — alpha pondéré le plus faible",    False)


def _append_block_i_appendix(story, bi: dict, space):
    """Annexe — table complète des achats du Stock Picking Score."""
    all_trades = bi.get("trades", [])
    if not all_trades:
        return

    story.append(PageBreak())
    story.append(space(10))
    story.append(Paragraph(
        "Annexe — Bloc I : Détail Complet des Achats (Stock Picking Score)",
        _sty("ann_i", fontName="Helvetica-Bold", fontSize=11,
             textColor=C_BLUE, leading=15, spaceAfter=4)))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))
    story.append(Paragraph(
        "Pour chaque achat exécuté : retour du titre à 1M/3M/6M/12M moins le retour benchmark "
        "sur la même période. Alpha pondéré = moyenne pondérée sur les horizons disponibles "
        "(poids : 1M×15%, 3M×25%, 6M×30%, 12M×30%). Les positions ouvertes utilisent "
        "le dernier prix disponible (alpha latent). Lignes grisées = prix non disponibles.",
        S_SMALL))
    story.append(space(6))

    hdr = [_p("Date", S_HDR), _p("Titre", S_HDR), _p("ISIN", S_HDR),
           _p("α 1M", S_HDR), _p("α 3M", S_HDR),
           _p("α 6M", S_HDR), _p("α 12M", S_HDR), _p("α pondéré", S_HDR)]
    rows = [hdr]
    style_extra = []

    for i, t in enumerate(all_trades, start=1):
        avail = t.get("available", False)
        hz    = t.get("horizons") or {}

        def _ac(h):
            if not avail: return _p("—", S_SMALL)
            d = hz.get(h, {})
            v = d.get("alpha") if d.get("available") else None
            if v is None: return _p("—", S_SMALL)
            c = "#10b981" if v > 0 else "#ef4444"
            return Paragraph(f"{v*100:+.1f}%",
                             _sty(f"ac{h}{i}", fontSize=7.5,
                                  textColor=colors.HexColor(c), alignment=TA_RIGHT))

        aw = t.get("alpha_weighted")
        if avail and aw is not None:
            col = "#10b981" if aw > 0 else "#ef4444"
            aw_cell = Paragraph(f"{aw*100:+.1f}%",
                                _sty(f"aw{i}", fontSize=7.5, fontName="Helvetica-Bold",
                                     textColor=colors.HexColor(col), alignment=TA_RIGHT))
        else:
            aw_cell = _p(t.get("reason", "—"), S_SMALL)
            style_extra.append(("TEXTCOLOR", (0, i), (-1, i), C_FAINT))

        rows.append([
            _p(t.get("date", ""), S_SMALL),
            _p(str(t.get("name", ""))[:28], S_BODY),
            _p(str(t.get("isin", ""))[:14], S_SMALL),
            _ac("1M"), _ac("3M"), _ac("6M"), _ac("12M"),
            aw_cell,
        ])

    story.append(_tbl(rows,
        col_widths=[2.0*cm, 4.4*cm, 2.0*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 2.8*cm],
        style_extra=style_extra))


def _append_block_h_timing(story, h: dict, space, meta=None):
    """Render Block H — Timing Score."""
    if not h.get("available"):
        story.append(Paragraph(f"⚠  {h.get('error', 'Données non disponibles.')}", S_WARN))
        n_tot = h.get("n_trades_total")
        trades = h.get("trades") or []
        if trades:
            story.append(space(6))
            story.append(Paragraph("Ordres sans données de prix :", S_SMALL))
            for t in trades[:8]:
                story.append(Paragraph(
                    f"  • {t.get('date','')} {t.get('side','')} {t.get('name','')} — "
                    f"{t.get('reason', 'inconnu')}",
                    _sty("tm", fontSize=7, textColor=C_FAINT, leading=10)))
        return

    warn = h.get("warning")
    if warn:
        story.append(Paragraph(f"⚠  {warn}", S_WARN))
        story.append(space(4))

    # ── KPI row ───────────────────────────────────────────────────────────
    def _score_color(v):
        if v is None: return "#94a3b8"
        if v >= 0.60: return "#10b981"
        if v >= 0.45: return "#f59e0b"
        return "#ef4444"

    em = h.get("entry_score_mean")
    xm = h.get("exit_score_mean")
    gm = h.get("global_score_mean")
    cov = h.get("coverage_pct", 0)

    story.append(_kpi_row([
        ("Score Entrées",    f"{em:.2f}" if em is not None else "—",  _score_color(em)),
        ("Score Sorties",    f"{xm:.2f}" if xm is not None else "—",  _score_color(xm)),
        ("Score Global",     f"{gm:.2f}" if gm is not None else "—",  _score_color(gm)),
        ("Couverture",       f"{cov:.0f}%", "#64748b"),
    ]))
    story.append(space(8))

    _meta = meta or {}
    if _meta.get("nav_start_date") and _meta.get("nav_current_date"):
        story.append(Paragraph(
            f"Période d'étude : {_meta['nav_start_date']} → {_meta['nav_current_date']}"
            f"  ·  {h.get('n_trades_total', '—')} ordres analysés", S_SMALL))
        story.append(space(4))

    # ── Stats summary table ───────────────────────────────────────────────
    n_tot = h.get("n_trades_total", 0)
    n_ana = h.get("n_trades_analyzed", 0)
    tg = h.get("tstat_global", 0)
    pg = h.get("pvalue_global", 1)

    stat_data = [
        [_p("Métrique", S_HDR), _p("Entrées (BUY)", S_HDR),
         _p("Sorties (SELL)", S_HDR), _p("Global", S_HDR)],
        [_p("Score moyen", S_BODY),
         _pn(f"{em:.3f}" if em is not None else "—"),
         _pn(f"{xm:.3f}" if xm is not None else "—"),
         _pn(f"{gm:.3f}" if gm is not None else "—")],
        [_p("vs hasard (0.500)", S_BODY),
         _pn(f"{(em-0.5):+.3f}" if em is not None else "—"),
         _pn(f"{(xm-0.5):+.3f}" if xm is not None else "—"),
         _pn(f"{(gm-0.5):+.3f}" if gm is not None else "—")],
        [_p("t-stat (vs µ₀=0.5)", S_BODY),
         _pn(f"{h.get('tstat_entry',0):+.2f}"),
         _pn(f"{h.get('tstat_exit',0):+.2f}"),
         _pn(f"{tg:+.2f}")],
        [_p("p-value global", S_BODY), _pn("—"), _pn("—"), _pn(f"{pg:.4f}")],
        [_p("Trades analysés / total", S_BODY),
         _pn(str(h.get("n_buy","—"))),
         _pn(str(h.get("n_sell","—"))),
         _pn(f"{n_ana} / {n_tot}")],
    ]
    story.append(_tbl(stat_data, col_widths=[5.5*cm, 3.5*cm, 3.5*cm, 4.9*cm]))
    story.append(space(8))

    # ── Interpretation ────────────────────────────────────────────────────
    interp = h.get("interpretation", "")
    if interp:
        story.append(Paragraph(interp, _sty("ti", fontSize=8, textColor=C_TEXT,
                                            leading=12.5, spaceAfter=4,
                                            alignment=TA_JUSTIFY)))
        story.append(space(8))

    # ── Histograms ────────────────────────────────────────────────────────
    de = h.get("dist_entry", {})
    dx = h.get("dist_exit", {})
    dg = h.get("dist_global", {})
    if any(d.get("counts") for d in [de, dx, dg]):
        story.append(Paragraph("Distribution des Scores de Timing", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))
        story.append(_chart_timing_distributions(de, dx, dg))
        story.append(space(6))
        story.append(Paragraph(
            "La ligne jaune (0.5) représente la performance théorique d'un trader aléatoire. "
            "Un score > 0.5 indique un timing supérieur au hasard sur cette dimension.",
            S_SMALL))
        story.append(space(12))

    # ── Pattern tables ────────────────────────────────────────────────────
    def _pattern_table(trades_list, title, score_color_fn):
        if not trades_list:
            return
        story.append(Paragraph(title, _sty("ph", fontName="Helvetica-Bold",
                                           fontSize=8.5, textColor=C_BLUE)))
        story.append(space(3))
        rows = [[_p("Date", S_HDR), _p("Titre", S_HDR),
                 _p("Prix exec.", S_HDR), _p("Min 30j", S_HDR),
                 _p("Max 30j", S_HDR), _p("Score", S_HDR)]]
        for t in trades_list[:10]:
            sc = t.get("score", 0)
            rows.append([
                _p(t.get("date",""), S_SMALL),
                _p(str(t.get("name",""))[:30], S_BODY),
                _pn(f"{t.get('price_local',0):.3f}"),
                _pn(f"{t.get('price_min_window',0):.3f}"),
                _pn(f"{t.get('price_max_window',0):.3f}"),
                Paragraph(f"{sc:.2f} {t.get('label','')}",
                          _sty("sc", fontSize=8, textColor=colors.HexColor(score_color_fn(sc)),
                               alignment=TA_RIGHT)),
            ])
        story.append(_tbl(rows, col_widths=[2.2*cm, 4.8*cm, 2.4*cm, 2.2*cm, 2.2*cm, 3.6*cm]))
        story.append(space(8))

    near_lows  = h.get("near_lows_buys", [])
    near_highs = h.get("near_highs_buys", [])
    good_exits = h.get("near_highs_sells", [])
    early_sells= h.get("early_sells", [])

    if near_lows or near_highs or good_exits or early_sells:
        story.append(Paragraph("Patterns de Timing Identifiés", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(6))

    _pattern_table(near_lows,  "Achats proches des plus bas  (score ≥ 0.70) — Timing favorable",
                   lambda s: "#10b981")
    _pattern_table(near_highs, "Achats proches des plus hauts (score ≤ 0.25) — Timing défavorable",
                   lambda s: "#ef4444")
    _pattern_table(good_exits, "Ventes proches des plus hauts (score ≥ 0.70) — Bonnes sorties",
                   lambda s: "#10b981")
    _pattern_table(early_sells,"Ventes prématurées / mal timées (score ≤ 0.30) — Sorties défavorables",
                   lambda s: "#f59e0b")

    # full trade detail moved to appendix (_append_block_h_appendix)


def _append_block_h_appendix(story, h: dict, space):
    """Annexe — table complète des trades du Timing Score (toutes lignes)."""
    all_trades = h.get("trades", [])
    if not all_trades:
        return

    story.append(PageBreak())
    story.append(space(10))
    story.append(Paragraph(
        "Annexe — Bloc H : Détail Complet des Trades (Timing Score)",
        _sty("ann_title", fontName="Helvetica-Bold", fontSize=11,
             textColor=C_BLUE, leading=15, spaceAfter=4)))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))
    story.append(Paragraph(
        "Chaque ligne correspond à un ordre exécuté. "
        "Score : 1 = prix d'exécution au plus bas/haut absolu de la fenêtre ±30 j ; "
        "0.5 = performance d'un trader aléatoire. "
        "Les lignes grisées n'ont pas de prix disponibles dans le Price Store.",
        S_SMALL))
    story.append(space(6))

    rows = [[_p("Date", S_HDR), _p("Côté", S_HDR), _p("Titre", S_HDR),
             _p("ISIN", S_HDR), _p("Prix exec.", S_HDR),
             _p("Min 30j", S_HDR), _p("Max 30j", S_HDR),
             _p("Score", S_HDR), _p("Verdict", S_HDR)]]

    style_extra = []
    for i, t in enumerate(all_trades, start=1):
        sc   = t.get("score")
        avail = t.get("available", False)
        if avail and sc is not None:
            col = "#10b981" if sc >= 0.60 else ("#ef4444" if sc < 0.40 else "#f59e0b")
            score_cell  = _pn(f"{sc:.3f}")
            verdict_cell = Paragraph(t.get("label",""),
                _sty(f"lv{i}", fontSize=7.5, textColor=colors.HexColor(col), alignment=TA_RIGHT))
        else:
            col = "#475569"
            score_cell   = _p("—", S_SMALL)
            verdict_cell = _p(t.get("reason","—"), S_SMALL)
            style_extra.append(("TEXTCOLOR", (0, i), (-1, i), C_FAINT))

        rows.append([
            _p(t.get("date",""), S_SMALL),
            _p(t.get("side",""), S_SMALL),
            _p(str(t.get("name",""))[:28], S_BODY),
            _p(str(t.get("isin",""))[:14], S_SMALL),
            _pn(f"{t.get('price_local',0):.3f}") if avail else _p("—", S_SMALL),
            _pn(f"{t.get('price_min_window',0):.3f}") if avail else _p("—", S_SMALL),
            _pn(f"{t.get('price_max_window',0):.3f}") if avail else _p("—", S_SMALL),
            score_cell,
            verdict_cell,
        ])

    story.append(_tbl(rows,
        col_widths=[1.9*cm, 1.2*cm, 4.0*cm, 2.2*cm, 1.9*cm, 1.9*cm, 1.9*cm, 1.5*cm, 2.9*cm],
        style_extra=style_extra))


def _chart_radar_scores(dim_labels: list, scores: list,
                         title: str = "", size_cm: float = 9.5) -> Image:
    """Radar/spider chart for Manager Skill dimensions."""
    n = len(dim_labels)
    if n < 3:
        return None
    angles = [2 * math.pi * i / n for i in range(n)]
    angles_closed = angles + [angles[0]]
    scores_closed = list(scores) + [scores[0]]
    DIM_COLORS = ["#60a5fa","#34d399","#f59e0b","#a78bfa","#fb923c","#f472b6"]

    sz = size_cm / 2.54 * 1.2   # convert cm → inches (approx)
    fig, ax = plt.subplots(figsize=(sz, sz), subplot_kw=dict(polar=True),
                           facecolor="#0f172a")
    ax.set_facecolor("#1e293b")
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    fs_tick = max(5, 7 - (n - 4))
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=5.5, color="#475569")
    ax.set_xticks(angles)
    ax.set_xticklabels(dim_labels, fontsize=fs_tick, color="#94a3b8")
    ax.plot(angles_closed, scores_closed, color="#3b82f6", linewidth=2)
    ax.fill(angles_closed, scores_closed, alpha=0.22, color="#3b82f6")
    for i, (angle, score, col) in enumerate(zip(angles, scores, DIM_COLORS)):
        ax.scatter([angle], [score], s=30, color=col, zorder=5)
    ax.grid(color="#334155", linewidth=0.5)
    ax.spines["polar"].set_color("#334155")
    if title:
        ax.set_title(title, color="#94a3b8", fontsize=9, pad=15)
    fig.patch.set_facecolor("#0f172a")
    fig.tight_layout(pad=1.0)
    return _fig_to_image(fig, size_cm, size_cm)


# ── Progress bar helper ───────────────────────────────────────────────────────

def _make_progress_bar(score: float, color_hex: str, bar_max_cm: float) -> Table:
    """Two-cell horizontal progress bar: filled | empty."""
    s = max(0.0, min(100.0, score))
    w_fill  = bar_max_cm * s / 100 * cm
    w_empty = bar_max_cm * (100 - s) / 100 * cm
    widths = [w_fill, w_empty] if w_empty > 0.01*cm else [bar_max_cm * cm]
    cells  = [Paragraph("", _sty(f"pbf{color_hex}")),
              Paragraph("", _sty(f"pbe{color_hex}"))] if w_empty > 0.01*cm else \
             [Paragraph("", _sty(f"pbf2{color_hex}"))]
    tbl = Table([cells], colWidths=widths,
                style=TableStyle([
                    ("BACKGROUND", (0,0), (0,0), colors.HexColor(color_hex)),
                    ("BACKGROUND", (1,0), (1,0), colors.HexColor("#1e293b")) if len(cells) > 1 else ("BACKGROUND", (0,0), (0,0), colors.HexColor(color_hex)),
                    ("TOPPADDING",    (0,0), (-1,-1), 0),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 0),
                    ("LEFTPADDING",   (0,0), (-1,-1), 0),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 0),
                ]))
    return tbl


def _gauge_strip(score: float, width_cm: float) -> Table:
    """5-zone horizontal gauge bar showing score position."""
    zones = [
        ((0,  40), "#ef4444", "Peu convaincant"),
        ((40, 60), "#f97316", "Correct"),
        ((60, 75), "#f59e0b", "Bon"),
        ((75, 90), "#22c55e", "Très bon"),
        ((90,100), "#10b981", "Exceptionnel"),
    ]
    total_w = width_cm * cm
    zone_widths = [(hi - lo) / 100 * total_w for (lo, hi), _, _ in zones]

    bar_row, lbl_row, rng_row = [], [], []
    bar_styles = []
    for i, ((lo, hi), col, lbl) in enumerate(zones):
        active  = lo <= score < hi or (score == 100 and hi == 100)
        reached = score > lo
        bg = colors.HexColor(col) if reached or active else colors.HexColor("#1e293b")
        marker = f" ◀ {score:.0f}" if active else ""
        bar_row.append(Paragraph(marker,
            _sty(f"gz{i}", fontSize=7, fontName="Helvetica-Bold",
                 textColor=C_WHITE, alignment=TA_CENTER)))
        bar_styles.append(("BACKGROUND", (i,0), (i,0), bg))
        lbl_row.append(Paragraph(lbl,
            _sty(f"gl{i}", fontSize=6.5, alignment=TA_CENTER,
                 fontName="Helvetica-Bold" if active else "Helvetica",
                 textColor=colors.HexColor(col) if reached or active else C_FAINT)))
        rng_row.append(Paragraph(f"{lo}–{hi}",
            _sty(f"gr{i}", fontSize=5.5, alignment=TA_CENTER, textColor=C_FAINT)))

    return Table(
        [bar_row, lbl_row, rng_row],
        colWidths=zone_widths,
        style=TableStyle([
            ("TOPPADDING",    (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("LEFTPADDING",   (0,0), (-1,-1), 1),
            ("RIGHTPADDING",  (0,0), (-1,-1), 1),
            ("ROWHEIGHT",     (0,0), (0,0),   14),
            ("BOX",           (0,0), (-1,0),  0.5, C_BORDER),
            ("LINEAFTER",     (0,0), (-2,0),  0.4, colors.HexColor("#0f172a")),
        ] + bar_styles)
    )


# ── Executive Summary ─────────────────────────────────────────────────────────

_DIM_FRIENDLY = {
    "alpha":         "Alpha factoriel (Bloc A)",
    "stock_picking": "Sélection de titres (Bloc I)",
    "vag":           "Référentiel Inertiel / VAG (Bloc E)",
    "risk_mgmt":     "Gestion du risque (Bloc J)",
    "timing":        "Timing des ordres (Bloc H)",
    "conviction":    "Discipline de conviction (Bloc D)",
}
_DIM_COLORS_HEX = {
    "alpha":         "#60a5fa",
    "stock_picking": "#34d399",
    "vag":           "#f59e0b",
    "risk_mgmt":     "#a78bfa",
    "timing":        "#fb923c",
    "conviction":    "#f472b6",
}


def _append_executive_summary(story, mss: dict, mss_no_vag: dict | None,
                               meta: dict, space):
    """Full one-page executive summary: Score Global + criteria table + gauge + radar."""
    score     = mss.get("score", 0)
    label     = mss.get("score_label", "")
    col_hex   = mss.get("score_color", "#f59e0b")
    dims      = mss.get("dimensions") or []
    interp    = mss.get("interpretation", "")
    n_avail   = mss.get("n_dimensions_available", 0)
    has_two   = bool(mss_no_vag and mss_no_vag.get("dimensions"))

    story.append(Paragraph("Score Global du Gérant — Synthèse Exécutive", S_TITLE))
    story.append(HRFlowable(INNER_W, thickness=1, color=C_BLUE))
    story.append(space(8))

    # ── Radar chart ──────────────────────────────────────────────────────
    avail = [d for d in dims if d.get("available") and d.get("score") is not None]
    radar_img = None
    if len(avail) >= 3:
        try:
            lbl_r = [_DIM_FRIENDLY.get(d["key"], d["label"]).split(" (")[0] for d in avail]
            sc_r  = [float(d["score"]) for d in avail]
            radar_img = _chart_radar_scores(lbl_r, sc_r, size_cm=8.0)
        except Exception:
            pass

    # ── Score badge ──────────────────────────────────────────────────────
    def _make_badge(sc: int, lbl: str, col: str, subtitle: str, nd: int,
                    w_cm: float) -> Table:
        return Table(
            [[Paragraph(str(sc),
                        _sty(f"exb_sc_{sc}", fontSize=46, fontName="Helvetica-Bold",
                             textColor=colors.HexColor(col),
                             alignment=TA_CENTER, leading=50))],
             [Paragraph("/100", _sty(f"exb_100_{sc}", fontSize=11,
                                     textColor=C_FAINT, alignment=TA_CENTER))],
             [Paragraph(lbl, _sty(f"exb_lbl_{sc}", fontSize=9.5,
                                   fontName="Helvetica-Bold",
                                   textColor=colors.HexColor(col),
                                   alignment=TA_CENTER, leading=13))],
             [Paragraph(subtitle, _sty(f"exb_sub_{sc}", fontSize=6,
                                        textColor=C_FAINT, alignment=TA_CENTER))],
             [Paragraph(f"{nd} dimension(s)", _sty(f"exb_nd_{sc}", fontSize=6,
                                                    textColor=C_FAINT,
                                                    alignment=TA_CENTER))],
            ],
            colWidths=[w_cm * cm],
            style=TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), C_CARD),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("BOX",           (0,0), (-1,-1), 0.4, C_BORDER),
            ])
        )

    badge_col = _make_badge(score, label, col_hex, "Score composite", n_avail, 6.3)
    radar_w   = INNER_W - 6.8*cm

    if radar_img:
        story.append(Table(
            [[badge_col, radar_img]],
            colWidths=[INNER_W - radar_w, radar_w],
            style=TableStyle([
                ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
                ("LEFTPADDING",  (0,0), (-1,-1), 0),
                ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ])))
    else:
        story.append(badge_col)
    story.append(space(10))

    # ── Criteria table with progress bars ────────────────────────────────
    # Columns: Critère | Poids | Score (avec VAG) | [Score sans VAG] | Progression
    if has_two:
        # Build no-vag score lookup
        sc2     = mss_no_vag.get("score", 0)
        col2    = mss_no_vag.get("score_color", "#f59e0b")
        sc2_map = {d["key"]: d.get("score") for d in (mss_no_vag.get("dimensions") or [])}
        BAR_W = INNER_W / cm - 5.8 - 1.3 - 1.5 - 1.5
        hdr = [_p("Critère", S_HDR), _p("Poids", S_HDR),
               _p("Avec VAG", S_HDR), _p("Sans VAG", S_HDR),
               _p("Progression", S_HDR)]
        rows = [hdr]
        for d in dims:
            key   = d.get("key", "")
            s     = d.get("score")
            s2    = sc2_map.get(key)
            w_ef  = d.get("weight_effective_pct", 0)
            dcol  = _DIM_COLORS_HEX.get(key, "#94a3b8")
            fname = _DIM_FRIENDLY.get(key, d.get("label", key))
            def _sc_cell(v, tag):
                if v is None:
                    return Paragraph("N/D", _sty(tag, alignment=TA_RIGHT,
                                                  fontSize=8, textColor=C_FAINT))
                vc = "#10b981" if v >= 65 else "#f59e0b" if v >= 50 else "#ef4444"
                return Paragraph(f"{v:.0f}",
                                 _sty(tag, alignment=TA_RIGHT,
                                      fontName="Helvetica-Bold", fontSize=10,
                                      textColor=colors.HexColor(vc)))
            bar = _make_progress_bar(s if s is not None else 0,
                                     dcol if s is not None else "#334155", BAR_W)
            rows.append([_p(fname, S_BODY), _pn(f"{w_ef:.0f}%"),
                         _sc_cell(s, f"exd_{key}"), _sc_cell(s2, f"exd2_{key}"), bar])
        rows.append([
            Paragraph("Score Global", _sty("ex_tot", fontName="Helvetica-Bold",
                                            fontSize=9, textColor=C_TEXT)),
            Paragraph("100%", _sty("ex_tw2", fontName="Helvetica-Bold", fontSize=8,
                                    textColor=C_TEXT, alignment=TA_RIGHT)),
            Paragraph(str(score), _sty("ex_ts1", fontName="Helvetica-Bold", fontSize=11,
                                        textColor=colors.HexColor(col_hex),
                                        alignment=TA_RIGHT)),
            Paragraph(str(sc2), _sty("ex_ts2", fontName="Helvetica-Bold", fontSize=11,
                                      textColor=colors.HexColor(col2),
                                      alignment=TA_RIGHT)),
            _make_progress_bar(score, col_hex, BAR_W),
        ])
        story.append(Table(rows,
            colWidths=[5.8*cm, 1.3*cm, 1.5*cm, 1.5*cm, BAR_W*cm],
            style=TableStyle([
                ("ROWBACKGROUNDS", (0,1), (-2,-2), [C_BG, colors.HexColor("#111827")]),
                ("BACKGROUND",     (0,-1), (-1,-1), colors.HexColor("#0f2441")),
                ("LINEABOVE",      (0,-1), (-1,-1), 0.8, C_BLUE),
                ("TOPPADDING",     (0,0), (-1,-1), 6),
                ("BOTTOMPADDING",  (0,0), (-1,-1), 6),
                ("LEFTPADDING",    (0,0), (-1,-1), 5),
                ("RIGHTPADDING",   (0,0), (-1,-1), 5),
                ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
                ("BOX",            (0,0), (-1,-1), 0.5, C_BORDER),
                ("LINEBELOW",      (0,0), (-1,0),  0.8, C_BORDER),
            ])))
    else:
        BAR_W = INNER_W / cm - 6.2 - 1.5 - 1.7
        hdr = [_p("Critère", S_HDR), _p("Poids", S_HDR),
               _p("Score", S_HDR), _p("Progression", S_HDR)]
        rows = [hdr]
        for d in dims:
            key   = d.get("key", "")
            s     = d.get("score")
            w_ef  = d.get("weight_effective_pct", 0)
            dcol  = _DIM_COLORS_HEX.get(key, "#94a3b8")
            fname = _DIM_FRIENDLY.get(key, d.get("label", key))
            if d.get("available") and s is not None:
                sc_col = "#10b981" if s >= 65 else "#f59e0b" if s >= 50 else "#ef4444"
                s_cell = Paragraph(f"{s:.0f}",
                                   _sty(f"exd_{key}", alignment=TA_RIGHT,
                                        fontName="Helvetica-Bold", fontSize=10,
                                        textColor=colors.HexColor(sc_col)))
                bar = _make_progress_bar(s, dcol, BAR_W)
            else:
                s_cell = Paragraph("N/D", _sty(f"exna_{key}", alignment=TA_RIGHT,
                                               fontSize=8, textColor=C_FAINT))
                bar = _make_progress_bar(0, "#334155", BAR_W)
            rows.append([_p(fname, S_BODY), _pn(f"{w_ef:.0f}%"), s_cell, bar])
        rows.append([
            Paragraph("Score Global", _sty("ex_tot", fontName="Helvetica-Bold",
                                            fontSize=9, textColor=C_TEXT)),
            Paragraph("100%", _sty("ex_tw", fontName="Helvetica-Bold", fontSize=8,
                                    textColor=C_TEXT, alignment=TA_RIGHT)),
            Paragraph(str(score), _sty("ex_ts", fontName="Helvetica-Bold", fontSize=12,
                                        textColor=colors.HexColor(col_hex),
                                        alignment=TA_RIGHT)),
            _make_progress_bar(score, col_hex, BAR_W),
        ])
        story.append(Table(rows,
            colWidths=[6.2*cm, 1.5*cm, 1.7*cm, BAR_W*cm],
            style=TableStyle([
                ("ROWBACKGROUNDS", (0,1), (-2,-2), [C_BG, colors.HexColor("#111827")]),
                ("BACKGROUND",     (0,-1), (-1,-1), colors.HexColor("#0f2441")),
                ("LINEABOVE",      (0,-1), (-1,-1), 0.8, C_BLUE),
                ("TOPPADDING",     (0,0), (-1,-1), 6),
                ("BOTTOMPADDING",  (0,0), (-1,-1), 6),
                ("LEFTPADDING",    (0,0), (-1,-1), 6),
                ("RIGHTPADDING",   (0,0), (-1,-1), 6),
                ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
                ("BOX",            (0,0), (-1,-1), 0.5, C_BORDER),
                ("LINEBELOW",      (0,0), (-1,0),  0.8, C_BORDER),
            ])))

    story.append(space(10))

    # ── 5-zone gauge ────────────────────────────────────────────────────
    story.append(Paragraph("Positionnement sur l'échelle de qualité",
                            _sty("ex_gttl", fontSize=7.5, textColor=C_MUTED,
                                 fontName="Helvetica-Bold", spaceAfter=4)))
    story.append(_gauge_strip(score, INNER_W / cm))
    story.append(space(8))

    # ── Short interpretation (justified) ──────────────────────────────────
    if interp:
        story.append(Paragraph(interp,
                               _sty("ex_interp", fontSize=7.5, textColor=C_MUTED,
                                    leading=11.5, alignment=TA_JUSTIFY)))


def _append_block_j_rms(story, bj: dict, space, meta=None):
    """Render Block J — Risk Management Score."""
    if not bj.get("available"):
        story.append(Paragraph(f"⚠  {bj.get('error', 'Données non disponibles.')}", S_WARN))
        return

    warn = bj.get("warning")
    if warn:
        story.append(Paragraph(f"⚠  {warn}", S_WARN))
        story.append(space(4))

    score = bj.get("score", 0)
    score_raw = bj.get("score_raw", score)
    cap = bj.get("reliability_cap", 100)

    def _sc_col(s):
        if s >= 65: return "#10b981"
        if s >= 50: return "#f59e0b"
        return "#ef4444"

    sub = bj.get("sub_scores") or {}
    weights = bj.get("weights") or {}

    sub_labels = [
        ("risk_adjusted", "Perf. ajustée"),
        ("drawdown",      "Drawdown"),
        ("downside_risk", "Risque baissier"),
        ("concentration", "Concentration"),
        ("factor_risk",   "Facteurs"),
    ]

    # Rangée 1 : 5 sous-scores côte à côte
    sub_kpi = []
    for key, lbl in sub_labels:
        s = (sub.get(key) or {}).get("score", 0)
        w_pct = round((weights.get(key) or 0) * 100)
        sub_kpi.append((f"{lbl} ({w_pct}%)", str(s), _sc_col(s)))
    story.append(_kpi_row(sub_kpi, n_cols=5))
    story.append(space(4))

    # Rangée 2 : score global + contexte
    bm_ok = bj.get("benchmark_available", False)
    story.append(_kpi_row([
        ("Score global /100",  str(score),    _sc_col(score)),
        ("Score brut /100",    str(score_raw), "#64748b"),
        ("Cap fiabilité",      f"{cap}/100",   "#64748b"),
        ("Benchmark",          "✓" if bm_ok else "N/D", "#10b981" if bm_ok else "#64748b"),
    ], n_cols=4))
    story.append(space(10))

    _meta = meta or {}
    n_obs_j = bj.get("n_obs", "—")
    if _meta.get("nav_start_date") and _meta.get("nav_current_date"):
        story.append(Paragraph(
            f"Période d'étude : {_meta['nav_start_date']} → {_meta['nav_current_date']}"
            f"  ·  {n_obs_j} observations NAV", S_SMALL))
        story.append(space(4))

    # ── Sub-score summary table ─────────────────────────────────────────
    story.append(Paragraph("Tableau des Sous-Scores", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    hdr = [_p("Dimension", S_HDR), _p("Poids", S_HDR),
           _p("Score /100", S_HDR), _p("Métriques clés", S_HDR)]
    rows = [hdr]

    def _row_metrics(key: str) -> str:
        s = sub.get(key) or {}
        if key == "risk_adjusted":
            return (f"Sharpe {s.get('sharpe_ratio', 0):.2f} | "
                    f"Calmar {s.get('calmar_ratio', 0):.2f} | "
                    f"Sortino {s.get('sortino_ratio', 0):.2f}")
        if key == "drawdown":
            return (f"Max DD {s.get('max_drawdown_pct', 0):.1f}% | "
                    f"Ulcer {s.get('ulcer_index_pct', 0):.1f}% | "
                    f"{s.get('n_drawdown_episodes', 0)} épisodes")
        if key == "downside_risk":
            return (f"VaR95 {s.get('var_95_pct', 0):.1f}% | "
                    f"ES95 {s.get('es_95_pct', 0):.1f}% | "
                    f"Sortino {s.get('sortino_ratio', 0):.2f}")
        if key == "concentration":
            return (f"Max poids {s.get('max_weight_pct', 0):.1f}% | "
                    f"HHI {s.get('hhi', 0):.4f} | "
                    f"Neff {s.get('effective_n', 0):.1f}")
        if key == "factor_risk":
            if not s.get("available"):
                return "Bloc A non disponible"
            return (f"R² {s.get('r2_pct', 0):.1f}% | "
                    f"Beta mkt {s.get('market_beta', '—')} | "
                    f"alpha t={s.get('alpha_tstat', 0):.2f}")
        return ""

    for key, lbl in sub_labels:
        s = (sub.get(key) or {}).get("score", 0)
        col = _sc_col(s)
        rows.append([
            _p(lbl, S_BODY),
            _pn(f"{round((weights.get(key) or 0) * 100)}%"),
            Paragraph(str(s), _sty(f"js{key}", alignment=TA_RIGHT, fontName="Helvetica-Bold",
                                   fontSize=8, textColor=colors.HexColor(col))),
            _p(_row_metrics(key), S_SMALL),
        ])

    story.append(_tbl(rows, col_widths=[3.8*cm, 1.8*cm, 2.4*cm, 9.4*cm]))
    story.append(space(8))

    # ── Detailed tables — layout 4 colonnes pour compacité ─────────────
    ra = sub.get("risk_adjusted") or {}
    dd = sub.get("drawdown") or {}
    dr = sub.get("downside_risk") or {}
    conc = sub.get("concentration") or {}
    fr = sub.get("factor_risk") or {}

    # Performance ajustée + Drawdown côte à côte (4 colonnes)
    if ra or dd:
        story.append(Paragraph("Ratios de Performance & Drawdown", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        W2 = INNER_W / 2 - 3
        ra_rows = [
            [_p("Sharpe",          S_HDR), _pn(f"{ra.get('sharpe_ratio', 0):.3f}"),
             _p("Max Drawdown",    S_HDR), Paragraph(f"{dd.get('max_drawdown_pct', 0):.2f}%",
                                                     _sty("ddp", alignment=TA_RIGHT, fontSize=8,
                                                          textColor=colors.HexColor("#ef4444")))],
            [_p("Sortino",         S_HDR), _pn(f"{ra.get('sortino_ratio', 0):.3f}"),
             _p("Ulcer Index",     S_HDR), _pn(f"{dd.get('ulcer_index_pct', 0):.2f}%")],
            [_p("Calmar",          S_HDR), _pn(f"{ra.get('calmar_ratio', 0):.3f}"),
             _p("Épisodes DD",     S_HDR), _pn(str(dd.get("n_drawdown_episodes", 0)))],
        ]
        if ra.get("information_ratio") is not None:
            ra_rows.append([
                _p("Info Ratio",   S_HDR), _pn(f"{ra['information_ratio']:.3f}"),
                _p("Durée moy. DD",S_HDR), _pn(f"{dd.get('avg_episode_duration_days', 0):.0f}j"),
            ])
        if ra.get("upside_capture_pct") is not None:
            ra_rows.append([
                _p("Capture hausse", S_HDR), _pn(f"{ra['upside_capture_pct']:.1f}%"),
                _p("Capture baisse", S_HDR), _pn(f"{ra.get('downside_capture_pct', 0):.1f}%")
                    if ra.get("downside_capture_pct") is not None else _pn("—"),
            ])
        if ra.get("tracking_error_pct") is not None:
            ra_rows.append([
                _p("Tracking Error", S_HDR), _pn(f"{ra['tracking_error_pct']:.2f}%"),
                _p(""), _pn(""),
            ])
        cw4 = [3.5*cm, 4.2*cm, 3.5*cm, 6.2*cm]
        story.append(_tbl(ra_rows, col_widths=cw4))
        story.append(space(8))

    # Risque baissier + Factor Risk
    if dr or fr.get("available"):
        story.append(Paragraph("Risque Baissier & Facteurs", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        dr_rows = [
            [_p("Semi-déviation",  S_HDR), _pn(f"{dr.get('semi_deviation_ann_pct', 0):.2f}%"),
             _p("R² (facteurs)",   S_HDR), _pn(f"{fr.get('r2_pct', 0):.1f}%") if fr.get("available") else _pn("—")],
            [_p("Sortino",         S_HDR), _pn(f"{dr.get('sortino_ratio', 0):.3f}"),
             _p("Bêta marché",     S_HDR), _pn(f"{fr.get('market_beta', '—')}") if fr.get("available") else _pn("—")],
            [_p("VaR 95%",         S_HDR), _pn(f"{dr.get('var_95_pct', 0):.2f}%"),
             _p("Alpha (t-stat)",  S_HDR), _pn(f"{fr.get('alpha_tstat', 0):.2f}") if fr.get("available") else _pn("—")],
            [_p("ES 95%",          S_HDR), _pn(f"{dr.get('es_95_pct', 0):.2f}%"),
             _p("Facteurs signif.",S_HDR), _pn(str(fr.get("significant_factors", "—"))) if fr.get("available") else _pn("—")],
            [_p("Pire journée",    S_HDR), Paragraph(f"{dr.get('worst_day_pct', 0):.2f}%",
                                                     _sty("wdp", alignment=TA_RIGHT, fontSize=8,
                                                          textColor=colors.HexColor("#ef4444"))),
             _p("Jours négatifs",  S_HDR), _pn(f"{dr.get('pct_negative_days', 0):.1f}%")],
        ]
        story.append(_tbl(dr_rows, col_widths=[3.5*cm, 4.2*cm, 3.5*cm, 6.2*cm]))
        story.append(space(8))

    # Pires épisodes de drawdown (table compacte)
    eps = dd.get("worst_episodes") or []
    if eps:
        story.append(Paragraph("Pires Épisodes de Drawdown", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        ep_data = [[_p("#", S_HDR), _p("Profondeur", S_HDR), _p("Durée (j)", S_HDR)]]
        for j, ep in enumerate(eps, 1):
            ep_data.append([
                _p(f"#{j}", S_BODY),
                Paragraph(f"{ep.get('depth_pct', 0):.2f}%",
                          _sty(f"ep{j}", alignment=TA_RIGHT, fontSize=8,
                               textColor=colors.HexColor("#ef4444"))),
                _pn(str(ep.get("duration_days", "—"))),
            ])
        story.append(_tbl(ep_data, col_widths=[1.5*cm, 6.0*cm, 9.9*cm]))
        story.append(space(8))

    # Concentration top-5
    top5 = conc.get("top5_holdings") or []
    if top5 or conc.get("n_holdings"):
        story.append(Paragraph("Concentration du Portefeuille", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        # Summary row
        summ = [
            [_p("Nbre de titres",  S_HDR), _pn(str(conc.get("n_holdings", "—"))),
             _p("HHI",             S_HDR), _pn(f"{conc.get('hhi', 0):.4f}"),
             _p("N effectif",      S_HDR), _pn(f"{conc.get('effective_n', 0):.1f}"),
             _p("Poids max",       S_HDR), _pn(f"{conc.get('max_weight_pct', 0):.1f}%")],
            [_p("Top 3",           S_HDR), _pn(f"{conc.get('top3_weight_pct', 0):.1f}%"),
             _p("Top 5",           S_HDR), _pn(f"{conc.get('top5_weight_pct', 0):.1f}%"),
             _p("Top 10",          S_HDR), _pn(f"{conc.get('top10_weight_pct', 0):.1f}%"),
             _p(""), _pn("")],
        ]
        story.append(_tbl(summ, col_widths=[2.8*cm, 2.5*cm, 1.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.6*cm]))
        story.append(space(4))
        if top5:
            c_data = [[_p("Titre", S_HDR), _p("Poids (%)", S_HDR)]]
            for pos in top5:
                c_data.append([
                    _p(pos.get("name", ""), S_BODY),
                    _pn(f"{pos.get('weight_pct', 0):.2f}%"),
                ])
            story.append(_tbl(c_data, col_widths=[13.5*cm, 3.9*cm]))
        story.append(space(8))

    # Interpretation
    interp = bj.get("interpretation", "")
    if interp:
        story.append(Paragraph("Interprétation", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        story.append(Paragraph(interp, _sty("ji", fontSize=8, textColor=C_TEXT,
                                            leading=12.5, spaceAfter=4,
                                            alignment=TA_JUSTIFY)))
        story.append(space(6))


def _append_block_k_marketshocks(story, bk: dict, space):
    """Render Block K — Réactivité aux Chocs de Marché."""
    if not bk.get("available"):
        story.append(Paragraph(f"⚠  {bk.get('error', 'Données non disponibles.')}", S_WARN))
        return

    warn = bk.get("warning")
    if warn:
        story.append(Paragraph(f"⚠  {warn}", S_WARN))
        story.append(space(4))

    story.append(Paragraph(
        f"Période analysée : {bk.get('fund_start', '—')} → {bk.get('fund_end', '—')}", S_SMALL))
    story.append(space(4))

    interp = bk.get("interpretation", "")
    if interp:
        story.append(Paragraph(interp, _sty("ki", fontSize=8, textColor=C_TEXT,
                                            leading=12.5, spaceAfter=4,
                                            alignment=TA_JUSTIFY)))
        story.append(space(8))

    events = bk.get("events") or []
    if not events:
        story.append(Paragraph(
            "Aucun choc de marché du calendrier ne chevauche l'historique de ce fonds.", S_SMALL))
        return

    story.append(Paragraph("Événements de Marché", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    hdr = [_p("Événement", S_HDR), _p("Période", S_HDR), _p("Trades", S_HDR),
           _p("Ratio activité", S_HDR), _p("Flux net", S_HDR), _p("Diagnostic", S_HDR)]
    rows = [hdr]
    for e in events:
        ratio = e.get("activity_ratio")
        net_flow = e.get("net_flow") or 0
        rows.append([
            _p(f"{e.get('label','')}", S_BODY),
            _p(f"{e.get('start','')} → {e.get('end','')}", S_SMALL),
            _pn(str(e.get("n_trades", 0))),
            _pn(f"x{ratio:.2f}" if ratio is not None else "—"),
            Paragraph(f"{net_flow:+,.0f}", _sty("kf", alignment=TA_RIGHT, fontSize=8,
                      textColor=colors.HexColor("#10b981" if net_flow > 0 else
                                                 "#ef4444" if net_flow < 0 else "#64748b"))),
            _p(e.get("reaction_label", ""), S_SMALL),
        ])
    story.append(_tbl(rows, col_widths=[4.2*cm, 3.2*cm, 1.6*cm, 2.2*cm, 2.4*cm, 3.8*cm]))
    story.append(space(6))


def _append_manager_skill(story, mss: dict, space):
    """Render Manager Skill Score section."""
    if not mss or not mss.get("available"):
        story.append(Paragraph(
            f"⚠  Manager Skill Score non disponible : {mss.get('error', 'Blocs insuffisants.')}",
            S_WARN))
        return

    score = mss.get("score", 0)
    label = mss.get("score_label", "")
    color_hex = mss.get("score_color", "#f59e0b")

    # ── Big score centered ────────────────────────────────────────────────
    score_cell = Table(
        [[Paragraph(str(score),
                    _sty("mss_big", fontName="Helvetica-Bold", fontSize=40,
                         textColor=colors.HexColor(color_hex),
                         alignment=TA_CENTER, leading=46))],
         [Paragraph("/100", _sty("mss_sub", fontSize=11, textColor=C_MUTED, alignment=TA_CENTER))],
         [Paragraph(label,   _sty("mss_lbl", fontName="Helvetica-Bold", fontSize=11,
                                  textColor=colors.HexColor(color_hex), alignment=TA_CENTER))]],
        colWidths=[7.0*cm],
        style=TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ])
    )

    # ── Radar chart ───────────────────────────────────────────────────────
    dims = mss.get("dimensions") or []
    avail_dims = [d for d in dims if d.get("available") and d.get("score") is not None]
    radar_img = None
    if len(avail_dims) >= 3:
        try:
            labels_r = [d["label"].replace(" (", "\n(") for d in avail_dims]
            scores_r = [float(d["score"]) for d in avail_dims]
            radar_img = _chart_radar_scores(labels_r, scores_r)
        except Exception:
            pass

    if radar_img:
        side_by_side = Table(
            [[score_cell, radar_img]],
            colWidths=[7.5*cm, INNER_W - 7.5*cm],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ])
        )
        story.append(side_by_side)
    else:
        story.append(score_cell)
    story.append(space(10))

    # ── Contribution table ────────────────────────────────────────────────
    story.append(Paragraph("Décomposition du Score par Dimension", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(6))

    hdr = [_p("Dimension", S_HDR), _p("Poids base", S_HDR),
           _p("Poids eff.", S_HDR), _p("Score /100", S_HDR),
           _p("Contribution", S_HDR)]
    rows = [hdr]
    for d in dims:
        s = d.get("score")
        contrib = d.get("weighted_contribution")
        if d.get("available") and s is not None:
            s_col = "#10b981" if s >= 65 else "#f59e0b" if s >= 50 else "#ef4444"
            s_cell = Paragraph(f"{s:.0f}",
                               _sty("msd", alignment=TA_RIGHT, fontName="Helvetica-Bold",
                                    fontSize=8, textColor=colors.HexColor(s_col)))
            c_cell = _pn(f"{contrib:.1f}") if contrib is not None else _pn("—")
        else:
            s_cell = Paragraph("N/A", _sty("msna", alignment=TA_RIGHT, fontSize=8,
                                           textColor=C_FAINT))
            c_cell = _pn("—")

        rows.append([
            _p(d.get("label", ""), S_BODY),
            _pn(f"{d.get('weight_base_pct', 0):.1f}%"),
            _pn(f"{d.get('weight_effective_pct', 0):.1f}%"),
            s_cell,
            c_cell,
        ])

    # Total row
    rows.append([
        Paragraph("TOTAL", _sty("mstot", fontName="Helvetica-Bold", fontSize=8, textColor=C_TEXT)),
        _pn("100%"),
        _pn("100%"),
        _pn("—"),
        Paragraph(str(score),
                  _sty("mstv", alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=9,
                       textColor=colors.HexColor(color_hex))),
    ])
    story.append(_tbl(rows, col_widths=[5.5*cm, 2.4*cm, 2.4*cm, 2.8*cm, 4.3*cm]))
    story.append(space(10))

    # Interpretation
    interp = mss.get("interpretation", "")
    if interp:
        story.append(Paragraph("Interprétation", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))
        story.append(Paragraph(interp, _sty("mssi", fontSize=8, textColor=C_TEXT,
                                            leading=12.5, spaceAfter=4,
                                            alignment=TA_JUSTIFY)))
        story.append(space(6))


def _append_block_bh(story, bh: dict, ccy: str, space, meta=None):
    """B&H Baseline: Référentiel Passif section."""
    if not bh.get("available"):
        story.append(Paragraph(
            f"⚠  {bh.get('error', 'Données B&amp;H indisponibles.')}", S_WARN))
        return

    bh_nav      = bh.get("bh_nav", 0)
    bh_perf     = bh.get("bh_perf_pct", 0)
    actual_nav  = bh.get("actual_nav", 0)
    actual_perf = bh.get("actual_perf_pct", 0)
    va          = bh.get("value_added_pct", 0)
    nav_t0      = bh.get("nav_t0", 100)

    va_col  = "#10b981" if va >= 0 else "#ef4444"
    bh_col  = "#60a5fa"
    act_col = "#10b981" if actual_perf >= 0 else "#ef4444"

    # Intro
    intro = (
        "Ce bloc répond à la question : <i>« Si le gérant n'avait rien fait depuis l'émission — "
        "aucune vente, aucun achat — quelle serait la performance aujourd'hui ? »</i> "
        "On reconstitue le portefeuille tel qu'il était à la date d'émission, puis on le laisse "
        "évoluer sans intervention jusqu'à aujourd'hui. C'est le <b>contrefactuel de l'inertie</b> : "
        "la performance qu'aurait obtenue n'importe quel gérant en ne faisant rien après la constitution "
        "du portefeuille initial. Une valeur ajoutée positive prouve que les décisions de trading "
        "ont créé de la richesse ; une valeur négative signifie que l'inertie aurait été préférable."
    )
    story.append(Paragraph(intro, _sty("bh_intro", fontSize=8, textColor=C_MUTED,
                                       leading=12, spaceAfter=10, alignment=TA_JUSTIFY)))
    story.append(space(6))

    story.append(_kpi_row([
        ("B&amp;H Passif\n(sans gestion)",
         f"{bh_perf:+.1f}%", bh_col),
        ("NAV Réelle\n(gestion active)",
         f"{actual_perf:+.1f}%", act_col),
        ("Valeur Ajoutée\npar la Gestion",
         f"{va:+.2f}%", va_col),
    ], n_cols=3))
    story.append(space(4))

    _bh_meta = meta or {}
    _bh_start = _bh_meta.get("nav_start_date", "—")
    _bh_end   = _bh_meta.get("nav_current_date", "—")
    story.append(Paragraph(
        f"Période B&amp;H : {_bh_start} → {_bh_end}", S_SMALL))
    story.append(space(4))

    # Interpretation line
    if va > 0:
        interp = (f"Le gérant a <b>créé {va:+.2f}%</b> de valeur par rapport au portefeuille passif. "
                  f"La gestion active a surperformé le B&amp;H de {va:.2f} points.")
    elif va < 0:
        interp = (f"Le portefeuille passif aurait surperformé de <b>{abs(va):.2f}%</b>. "
                  f"L'inertie aurait été préférable à la gestion active sur cette période.")
    else:
        interp = "La gestion active n'a ni créé ni détruit de valeur par rapport au B&amp;H passif."
    story.append(Paragraph(interp, _sty("bh_interp", fontSize=8, textColor=C_TEXT,
                                        leading=12, spaceBefore=4)))
    story.append(space(12))

    # Positions table
    positions = bh.get("positions", [])
    if positions:
        story.append(Paragraph("Composition du portefeuille initial reconstruit", S_SECTION))
        story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
        story.append(space(4))

        tbl_data = [[
            _p("Sous-jacent", S_HDR),
            _p("Poids T0", S_HDR),
            _p("Retour total", S_HDR),
            _p("Contribution B&amp;H", S_HDR),
            _p("Source prix T0", S_HDR),
        ]]
        for pos in positions:
            ret_col = "#10b981" if pos["total_return_pct"] >= 0 else "#ef4444"
            ctb_col = "#10b981" if pos["bh_contribution_pts"] >= 0 else "#ef4444"
            tbl_data.append([
                _p(pos["name"], S_BODY),
                _pn(f"{pos['initial_weight_pct']:.1f}%"),
                _p(f"{pos['total_return_pct']:+.1f}%",
                   _sty(f"bh_ret_{pos['isin']}", fontSize=8,
                        textColor=colors.HexColor(ret_col), alignment=TA_CENTER,
                        leading=12)),
                _p(f"{pos['bh_contribution_pts']:+.2f} pts",
                   _sty(f"bh_ctb_{pos['isin']}", fontSize=8,
                        textColor=colors.HexColor(ctb_col), alignment=TA_CENTER,
                        leading=12)),
                _p(pos.get("initial_price_source", "—"), S_SMALL),
            ])

        story.append(_tbl(tbl_data, col_widths=[7.0*cm, 2.2*cm, 2.8*cm, 3.0*cm, 2.4*cm]))
        story.append(space(8))

    # Methodology note
    story.append(Paragraph(bh.get("methodology", ""), S_SMALL))
    story.append(space(6))


def _append_disclaimer(story, space):
    story.append(space(20))
    story.append(Paragraph("Avertissements &amp; Méthodologie", S_SECTION))
    story.append(HRFlowable(INNER_W, thickness=0.5, color=C_BORDER))
    story.append(space(8))
    disc = [
        "<b>Reconstruction FIFO des positions :</b> les round-trips sont reconstitués "
        "par appariement FIFO (first in, first out) des ordres exécutés (état « Done »). "
        "Les ordres annulés (« Discarded ») sont comptabilisés séparément comme indicateur "
        "d'hésitation mais n'entrent pas dans le calcul du P&L.",
        "",
        "<b>Décomposition P&L prix vs FX :</b> sur chaque aller-retour clôturé, "
        "le P&L total en devise produit est décomposé : effet-prix (FX fixé au niveau "
        "de sortie) et effet-FX (prix fixé au niveau d'entrée). Formules : "
        "pnl_prix = q × F_s × (P_s − P_e)  ·  pnl_fx = q × P_e × (F_s − F_e).",
        "",
        "<b>P&L latent :</b> marqué au dernier prix disponible dans le Price Store local "
        "(série historique de clôture ajustée des dividendes, parquet). "
        "Fallback yfinance si le titre n'est pas encore dans le store. "
        "Un seul mark courant par titre — pas de décomposition prix/FX pour les positions ouvertes.",
        "",
        "<b>Brut vs net :</b> la série brute est obtenue par gross add-back en accrual "
        "quotidien du taux de frais annuel fourni dans le manifeste (terme sheet). "
        "Le delta brut−net est déterministe.",
        "",
        "<b>Matrice conviction × résultat :</b> le classement d'une position dans un "
        "quadrant dépend des seuils renseignés dans le manifeste (jours long terme, poids "
        "conviction). Une position peut migrer d'un quadrant à l'autre selon ces seuils.",
        "",
        "<b>Bloc E — Référentiel Inertiel (B&amp;H / VAG) :</b> répond à la question "
        "« Si le gérant n'avait rien fait depuis l'émission, quelle serait la performance ? ». "
        "Source primaire : poids de la term sheet (params.termsheet_positions). "
        "Fallback : identité comptable qty_initiale = position_actuelle + ventes_totales − achats_réels. "
        "Total return = prix_ajusté_aujourd'hui / prix_ajusté_T0 (dividendes inclus via yfinance). "
        "FX intégré pour les actifs hors devise produit. "
        "VAG = performance AMC réelle − Référentiel B&amp;H : &gt; 0 → le gérant a créé de la valeur. "
        "Le score Manager Skill intègre le VAG au poids de 20 %. "
        "LIMITES : (1) Les prix T0 issus de yfinance peuvent diverger des cours réels "
        "(splits, corporate actions, données manquantes). (2) L'identité comptable "
        "suppose un carnet d'ordres complet — des ordres manquants surestiment les quantités initiales. "
        "(3) Le B&amp;H ne tient pas compte des frais de transaction. "
        "Interpréter le VAG comme un ordre de grandeur indicatif.",
        "",
        "<b>Bloc H — Timing Score :</b> chaque score est calculé en positionnant le prix "
        "d'exécution dans le range [min, max] des prix de clôture observés sur les 30 jours "
        "calendaires précédant et suivant la date du trade (fenêtre ±30 j). "
        "Entry Score = (max − prix_achat) / (max − min) ; Exit Score = (prix_vente − min) / "
        "(max − min). Un score de 0.5 est la performance d'un trader aléatoire. "
        "Le test t (one-sample, µ₀ = 0.5) évalue la significativité statistique. "
        "GARDE OUTLIER : tout trade dont le prix d'exécution dépasse ×3 le range de la fenêtre "
        "est exclu du calcul et signalé dans l'annexe (suspicion de split non ajusté ou de "
        "saisie erronée dans le carnet d'ordres). "
        "LIMITE : les prix du Price Store sont split-adjusted (yfinance auto_adjust=True) ; "
        "les prix d'exécution du carnet sont as-traded — un split survenu après l'achat crée "
        "un écart apparent qui est détecté et exclu par la garde ×3. "
        "Le calcul utilise des prix futurs (partie droite de la fenêtre) — métrique ex-post uniquement.",
        "",
        "<b>Cohérence des métriques de risque (Bloc A vs Bloc J) :</b> le Bloc A (Fama-French) "
        "et le Bloc J (Risk Management) utilisent des fenêtres temporelles différentes. "
        "Le Bloc A travaille sur la fenêtre de régression FF, qui commence à la première "
        "observation disponible dans les facteurs Fama-French après l'émission — souvent "
        "légèrement postérieure à la date de première NAV. Le Bloc J utilise l'historique "
        "NAV complet depuis la première valeur liquidative disponible. "
        "Cette différence explique les écarts observables entre les métriques (Sharpe, "
        "drawdown maximum, performance) affichées dans les deux blocs : les deux calculs "
        "sont corrects mais portent sur des périodes distinctes. "
        "La période exacte de chaque bloc est indiquée dans son en-tête respectif.",
        "",
        "<b>Avertissement général :</b> Ce document est produit par TP Advisory Services "
        "à titre informatif et analytique. Il ne constitue pas un conseil en investissement, "
        "une recommandation d'achat ou de vente, ni une évaluation officielle au sens des "
        "réglementations applicables (MiFID II, LSFin/LEFin, LPCC). Les analyses présentées "
        "reposent sur des données reconstituées et des modèles quantitatifs soumis à des "
        "limites inhérentes. Les résultats dépendent de la qualité et de l'exhaustivité des "
        "données fournies par le mandant. "
        "Les performances passées ne préjugent pas des performances futures.",
        "",
        "<b>Responsabilité :</b> TP Advisory Services décline toute responsabilité pour "
        "les décisions d'investissement prises sur la base de ce document. L'analyse "
        "multi-factorielle et les scores présentés sont des outils d'aide à la décision "
        "et non des indicateurs certifiés ou réglementés. La précision des modèles est "
        "conditionnée à la complétude du carnet d'ordres et à l'intégrité des séries "
        "de NAV fournies.",
        "",
        "<b>Sources de données :</b> facteurs Fama-French — bibliothèque de Kenneth R. French "
        "(Tuck School of Business, Dartmouth) ; prix des sous-jacents — Price Store local "
        "(séries parquet, auto-alimentées depuis Yahoo Finance / yfinance à la première étude "
        "sur chaque AMC, mises à jour manuellement via upload Excel/JSON) ; "
        "composition et ordres — exports du dépositaire (fichiers Def.txt et JSON). "
        "NOTE : les prix yfinance sont auto-ajustés des dividendes et des splits (auto_adjust=True). "
        "Pour les sous-jacents ayant subi un split post-émission, les prix du store peuvent "
        "diverger des prix d'exécution as-traded du carnet d'ordres — ces cas sont détectés "
        "et signalés (garde ×3 en Bloc H).",
        "",
        "<b>Propriété intellectuelle :</b> les méthodologies, algorithmes et outils "
        "d'analyse utilisés dans ce rapport sont la propriété exclusive de TP Advisory Services. "
        "Leur reproduction, adaptation ou utilisation commerciale sans autorisation préalable "
        "écrite est strictement interdite.",
        "",
        "<b>Confidentialité :</b> ce rapport est destiné exclusivement au destinataire identifié "
        "en couverture. Il est strictement confidentiel et ne peut être communiqué, reproduit "
        "ou diffusé, même partiellement, sans l'accord préalable écrit de TP Advisory Services. "
        "Tout manquement à cette obligation engage la responsabilité du destinataire.",
    ]
    for line in disc:
        if line:
            story.append(Paragraph(line, _sty("disc2", fontSize=7.5, textColor=C_FAINT,
                                              leading=11, spaceAfter=5,
                                              alignment=TA_JUSTIFY)))
        else:
            story.append(space(4))
