"""
HCS Design — Report Generator (Phase 7)
========================================
Reference : ACI/PCI CODE-319-25  |  PCI Design Handbook, 8th Edition
Units     : SI only — mm, kN, MPa

Output    : Word (.docx) via python-docx
            PDF  (.pdf)  via fpdf2

Format    : Professional step-by-step engineering calculation.
            Every formula shows:
              Description = formula = substitution = result  [Clause ref]

Charts    : SFD/BMD captured via plotly.io.to_image() into io.BytesIO.
            No files written to disk (Streamlit Cloud compatible).

Unicode   : All Greek / superscript chars replaced with ASCII before
            fpdf2 output to prevent UnicodeEncodeError.
"""

from __future__ import annotations

import io
import math
import traceback
from datetime import datetime
from typing import Any

import numpy as np

# ── python-docx ────────────────────────────────────────────────────────────────
try:
    from docx import Document
    from docx.shared import Mm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# ── fpdf2 ──────────────────────────────────────────────────────────────────────
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# ── Plotly image export ────────────────────────────────────────────────────────
try:
    import plotly.io as pio
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


# =============================================================================
# UTILITIES  (shared by Word and PDF builders)
# =============================================================================

def _g(ss: dict, key: str, default: Any = 0.0) -> Any:
    """Safe session-state getter — never raises KeyError."""
    return ss.get(key, default)


def _ascii(text: str) -> str:
    """
    Replace all non-ASCII / Unicode chars with plain ASCII equivalents.
    REQUIRED before any fpdf2 cell/multi_cell call.
    """
    table = {
        # superscripts / math
        "\u00b2": "^2",   "\u00b3": "^3",   "\u00b9": "1",
        "\u00b0": "deg",  "\u00b7": ".",     "\u22c5": ".",
        "\u221a": "sqrt", "\u00d7": "x",     "\u00f7": "/",
        "\u2212": "-",    "\u2013": "-",     "\u2014": "--",
        "\u00b1": "+/-",  "\u2264": "<=",    "\u2265": ">=",
        "\u2248": "~=",   "\u2260": "!=",    "\u221e": "inf",
        # fractions
        "\u00bd": "1/2",  "\u00bc": "1/4",   "\u00be": "3/4",
        # Greek lower-case
        "\u03b1": "alfa",  "\u03b2": "beta",   "\u03b3": "gamma",
        "\u03b4": "delta", "\u03b5": "epsilon","\u03b6": "zeta",
        "\u03b7": "eta",   "\u03b8": "theta",  "\u03bb": "lambda",
        "\u03bc": "mu",    "\u03bd": "nu",     "\u03c0": "pi",
        "\u03c1": "rho",   "\u03c3": "sigma",  "\u03c4": "tau",
        "\u03c6": "phi",   "\u03c8": "psi",    "\u03c9": "omega",
        # Greek upper-case
        "\u03a6": "Phi",   "\u03a9": "Omega",  "\u0394": "Delta",
        # quotation / apostrophe
        "\u2019": "'",    "\u2018": "'",
        "\u201c": '"',    "\u201d": '"',
        # misc
        "\u2026": "...",  "\u00a0": " ",
        "\u2032": "'",    "\u2033": "''",
        # accented Latin
        "\u00e9": "e",  "\u00e8": "e",  "\u00ea": "e",
        "\u00e0": "a",  "\u00e2": "a",  "\u00fc": "u",
        # arrows / bullets
        "\u2022": "*",  "\u25cf": "*",  "\u2192": "->",
        # dot operator used in kN.m notation
        "\u00b7": ".",
    }
    for uni, asc in table.items():
        text = text.replace(uni, asc)
    # strip any remaining non-ASCII
    return text.encode("ascii", errors="replace").decode("ascii")


def _fmt(val: Any, dec: int = 3) -> str:
    """Format a float, return '--' for missing / nan / inf."""
    try:
        v = float(val)
        if not math.isfinite(v):
            return "--"
        return f"{v:.{dec}f}"
    except (TypeError, ValueError):
        return str(val) if val is not None else "--"


def _span_table(ss: dict, n_seg: int = 10) -> list[dict]:
    """
    Build span distribution table at 0.0, 0.1 ... 1.0 x L_an.
    Interpolates from lb_x_arr / lb_Vu_arr / lb_Mu_arr.
    Returns list of dicts: {frac, x_mm, x_m, Vu_kN, Mu_kNm}
    """
    x_raw  = _g(ss, "lb_x_arr",  None)
    Vu_raw = _g(ss, "lb_Vu_arr", None)
    Mu_raw = _g(ss, "lb_Mu_arr", None)
    L_an   = float(_g(ss, "L_an", 5850.0))

    if x_raw is None or len(x_raw) < 2:
        # Fallback: parabolic approximation for Mu, linear for Vu
        wu    = float(_g(ss, "lb_wu_area", 5.0))
        bbot  = float(_g(ss, "b_bottom", 1199.0))
        w_lin = wu * bbot / 1e6          # kN/mm
        Ra    = w_lin * L_an / 2.0
        rows  = []
        for i in range(n_seg + 1):
            frac  = i / n_seg
            x     = frac * L_an
            Vu    = Ra - w_lin * x
            Mu    = Ra * x - w_lin * x**2 / 2.0
            rows.append({"frac": frac, "x_mm": x, "x_m": x / 1000,
                         "Vu_kN": Vu, "Mu_kNm": Mu / 1e6})
        return rows

    x_arr  = np.asarray(x_raw,  dtype=float)
    Vu_arr = np.asarray(Vu_raw, dtype=float)
    Mu_arr = np.asarray(Mu_raw, dtype=float)
    rows   = []
    for i in range(n_seg + 1):
        frac  = i / n_seg
        x_tgt = frac * L_an
        Vu_i  = float(np.interp(x_tgt, x_arr, Vu_arr))
        Mu_i  = float(np.interp(x_tgt, x_arr, Mu_arr)) / 1e6
        rows.append({"frac": frac, "x_mm": x_tgt, "x_m": x_tgt / 1000,
                     "Vu_kN": Vu_i, "Mu_kNm": Mu_i})
    return rows


def _build_sfd_bmd_fig(ss: dict):
    """Rebuild the SFD / BMD Plotly figure from session_state arrays."""
    if not HAS_PLOTLY:
        return None
    x_raw  = _g(ss, "lb_x_arr",  None)
    Vu_raw = _g(ss, "lb_Vu_arr", None)
    Mu_raw = _g(ss, "lb_Mu_arr", None)
    Vs_raw = _g(ss, "lb_Vs_arr", None)
    Ms_raw = _g(ss, "lb_Ms_arr", None)

    if x_raw is None:
        return None

    x_m   = np.asarray(x_raw,  dtype=float) / 1000.0
    Vu    = np.asarray(Vu_raw, dtype=float)
    Mu    = np.asarray(Mu_raw, dtype=float) / 1e6
    Vs    = np.asarray(Vs_raw, dtype=float) if Vs_raw is not None else None
    Ms    = np.asarray(Ms_raw, dtype=float) / 1e6 if Ms_raw is not None else None

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=(
            "Shear Force Diagram  (kN)",
            "Bending Moment Diagram  (kN.m)",
        ),
        vertical_spacing=0.18,
        shared_xaxes=True,
    )
    # SFD
    fig.add_trace(go.Scatter(
        x=x_m, y=Vu, name="Vu factored",
        line=dict(color="#1A476F", width=2.5),
    ), row=1, col=1)
    if Vs is not None:
        fig.add_trace(go.Scatter(
            x=x_m, y=Vs, name="Vs service",
            line=dict(color="#1A476F", width=1.5, dash="dash"),
        ), row=1, col=1)
    # transfer-length shading
    l_t_m = float(_g(ss, "lb_l_t", 0.0)) / 1000.0
    L_m   = float(_g(ss, "L_an", 5850.0)) / 1000.0
    for x0, x1 in [(0, l_t_m), (L_m - l_t_m, L_m)]:
        fig.add_shape(type="rect", xref="x", yref="paper",
                      x0=x0, x1=x1, y0=0, y1=1,
                      fillcolor="rgba(200,0,0,0.08)",
                      line=dict(color="rgba(200,0,0,0.3)", width=1),
                      row=1, col=1)

    # BMD
    fig.add_trace(go.Scatter(
        x=x_m, y=Mu, name="Mu factored",
        fill="tozeroy", fillcolor="rgba(26,71,111,0.10)",
        line=dict(color="#1A476F", width=2.5),
    ), row=2, col=1)
    if Ms is not None:
        fig.add_trace(go.Scatter(
            x=x_m, y=Ms, name="Ms service",
            line=dict(color="#2E74B5", width=1.5, dash="dash"),
        ), row=2, col=1)

    # Mu_max annotation
    Mu_max_val = float(np.max(Mu)) if len(Mu) else 0.0
    Mu_max_x   = float(x_m[np.argmax(Mu)]) if len(Mu) else L_m / 2
    fig.add_annotation(
        x=Mu_max_x, y=Mu_max_val,
        text=f"Mu_max = {Mu_max_val:.2f} kN.m",
        showarrow=True, arrowhead=2, arrowcolor="#333",
        font=dict(size=10), row=2, col=1,
    )

    fig.update_layout(
        height=500, width=780,
        paper_bgcolor="white", plot_bgcolor="#FAFAFA",
        font=dict(size=10, family="Arial, sans-serif"),
        legend=dict(orientation="h", y=1.08, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=65, r=25, t=80, b=50),
    )
    fig.update_xaxes(title_text="Distance from left support (m)",
                     gridcolor="#E0E0E0", zerolinecolor="#AAA", row=2, col=1)
    fig.update_xaxes(gridcolor="#E0E0E0", zerolinecolor="#AAA", row=1, col=1)
    fig.update_yaxes(title_text="Shear (kN)",
                     gridcolor="#E0E0E0", zerolinecolor="#AAA", row=1, col=1)
    fig.update_yaxes(title_text="Moment (kN.m)",
                     gridcolor="#E0E0E0", zerolinecolor="#AAA", row=2, col=1)
    return fig


def _fig_to_png(fig) -> bytes | None:
    """
    Export Plotly figure to PNG bytes in-memory.
    Primary: kaleido via pio.to_image().
    Fallback: matplotlib SFD/BMD reconstruction if kaleido fails.
    """
    if fig is None or not HAS_PLOTLY:
        return None
    # ── Primary: kaleido ──────────────────────────────────────────────────
    try:
        import kaleido  # noqa: F401
        return pio.to_image(fig, format="png", width=780, height=500, scale=2)
    except Exception:
        pass
    # ── Fallback: matplotlib simple SFD/BMD ───────────────────────────────
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        # Extract data from Plotly figure traces
        x_data, vu_data, mu_data = [], [], []
        for trace in fig.data:
            if hasattr(trace, "x") and trace.x is not None and len(trace.x) > 1:
                if "Vu" in (trace.name or "") or "Vs" in (trace.name or ""):
                    x_data = list(trace.x)
                    vu_data = list(trace.y)
                elif "Mu" in (trace.name or "") or "Ms" in (trace.name or ""):
                    mu_data = list(trace.y)

        fig_mpl, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 6),
                                             facecolor="white", sharex=True)
        fig_mpl.subplots_adjust(hspace=0.35)

        if x_data and vu_data:
            ax1.plot(x_data, vu_data, color="#1A476F", linewidth=2, label="Vu factored")
            ax1.axhline(0, color="black", linewidth=0.6)
            ax1.fill_between(x_data, vu_data, alpha=0.08, color="#1A476F")
        ax1.set_ylabel("Shear (kN)", fontsize=9)
        ax1.set_title("Shear Force Diagram  (kN)", fontsize=10, fontweight="bold")
        ax1.grid(True, linestyle="--", alpha=0.4)
        ax1.legend(fontsize=8)

        if x_data and mu_data:
            ax2.plot(x_data, mu_data, color="#1A476F", linewidth=2, label="Mu factored")
            ax2.axhline(0, color="black", linewidth=0.6)
            ax2.fill_between(x_data, mu_data, alpha=0.08, color="#1A476F")
        ax2.set_xlabel("Distance from left support (m)", fontsize=9)
        ax2.set_ylabel("Moment (kN·m)", fontsize=9)
        ax2.set_title("Bending Moment Diagram  (kN·m)", fontsize=10, fontweight="bold")
        ax2.grid(True, linestyle="--", alpha=0.4)
        ax2.legend(fontsize=8)

        note = mpatches.Patch(color="none",
                              label="[Diagram rendered via matplotlib fallback]")
        fig_mpl.legend(handles=[note], loc="lower center",
                       fontsize=7, framealpha=0)

        buf = io.BytesIO()
        fig_mpl.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                        facecolor="white")
        plt.close(fig_mpl)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


# =============================================================================
# WORD REPORT  (python-docx)
# =============================================================================

class _DocxReport:
    """
    Builds the Word calculation report chapter by chapter.
    All text uses python-docx Run objects — Unicode is fine here.
    """

    # Colour palette
    _NAVY  = RGBColor(0x1A, 0x47, 0x6F)
    _BLUE  = RGBColor(0x2E, 0x74, 0xB5)
    _GREEN = RGBColor(0x00, 0x51, 0x28)
    _GREY  = RGBColor(0x60, 0x60, 0x60)
    _RED   = RGBColor(0xC0, 0x00, 0x00)
    _WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    _LGREY = RGBColor(0xF2, 0xF2, 0xF2)

    def __init__(self, ss: dict):
        self.ss  = ss
        self.doc = Document()
        self._setup_page()

    # ── Page margins ────────────────────────────────────────────────────────
    def _setup_page(self):
        for sec in self.doc.sections:
            sec.top_margin    = Mm(20)
            sec.bottom_margin = Mm(20)
            sec.left_margin   = Mm(22)
            sec.right_margin  = Mm(18)

    # ── Heading helpers ─────────────────────────────────────────────────────
    def _h1(self, text: str):
        p = self.doc.add_heading(text, level=1)
        if p.runs:
            p.runs[0].font.color.rgb = self._NAVY

    def _h2(self, text: str):
        p = self.doc.add_heading(text, level=2)
        if p.runs:
            p.runs[0].font.color.rgb = self._BLUE

    def _h3(self, text: str):
        p = self.doc.add_heading(text, level=3)
        if p.runs:
            p.runs[0].font.color.rgb = self._BLUE

    # ── Body-text helpers ────────────────────────────────────────────────────
    def _calc(self, text: str, ref: str = ""):
        """Green Courier-New calculation line + optional grey ref tag."""
        p  = self.doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(1)
        pf.space_after  = Pt(1)
        r1 = p.add_run(text)
        r1.font.name      = "Courier New"
        r1.font.size      = Pt(9)
        r1.font.color.rgb = self._GREEN
        if ref:
            r2 = p.add_run(f"    [{ref}]")
            r2.font.name      = "Courier New"
            r2.font.size      = Pt(7.5)
            r2.font.italic    = True
            r2.font.color.rgb = self._GREY

    def _note(self, text: str):
        """Italic grey note line."""
        p  = self.doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(1)
        pf.space_after  = Pt(2)
        r  = p.add_run(text)
        r.font.italic    = True
        r.font.size      = Pt(8.5)
        r.font.color.rgb = self._GREY

    def _warn(self, text: str):
        """Bold red warning line."""
        p  = self.doc.add_paragraph()
        r  = p.add_run("  ⚠  " + text)
        r.font.bold      = True
        r.font.size      = Pt(9)
        r.font.color.rgb = self._RED

    def _ok(self, text: str):
        """Bold green OK line."""
        p  = self.doc.add_paragraph()
        r  = p.add_run("  ✓  " + text)
        r.font.bold      = True
        r.font.size      = Pt(9)
        r.font.color.rgb = self._GREEN

    def _status_line(self, text: str, ok: bool):
        if ok:
            self._ok(text)
        else:
            self._warn(text)

    # ── Table helpers ────────────────────────────────────────────────────────
    def _shd_cell(self, cell, hex_fill: str):
        """Set table cell background colour."""
        tc_pr = cell._tc.get_or_add_tcPr()
        shd   = OxmlElement("w:shd")
        shd.set(qn("w:fill"),  hex_fill)
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:val"),   "clear")
        tc_pr.append(shd)

    def _kv_table(self, rows: list[tuple]):
        """Two-column key-value table with navy header row."""
        t  = self.doc.add_table(rows=1, cols=2)
        t.style = "Table Grid"
        hdr = t.rows[0].cells
        for i, txt in enumerate(("Parameter", "Value")):
            hdr[i].text = txt
            run = hdr[i].paragraphs[0].runs[0]
            run.font.bold      = True
            run.font.size      = Pt(9)
            run.font.color.rgb = self._WHITE
            self._shd_cell(hdr[i], "1A476F")
        fill = False
        for key, val in rows:
            rc = t.add_row().cells
            rc[0].text = str(key)
            rc[1].text = str(val)
            for c in rc:
                c.paragraphs[0].runs[0].font.size = Pt(9)
                if fill:
                    self._shd_cell(c, "F2F2F2")
            fill = not fill
        self.doc.add_paragraph()

    def _wide_table(self, header: list[str], data: list[list]):
        """N-column table with navy header."""
        nc = len(header)
        t  = self.doc.add_table(rows=1, cols=nc)
        t.style = "Table Grid"
        hdr = t.rows[0].cells
        for i, txt in enumerate(header):
            hdr[i].text = str(txt)
            run = hdr[i].paragraphs[0].runs[0]
            run.font.bold      = True
            run.font.size      = Pt(8.5)
            run.font.color.rgb = self._WHITE
            self._shd_cell(hdr[i], "1A476F")
        fill = False
        for row in data:
            rc = t.add_row().cells
            for i, val in enumerate(row):
                rc[i].text = str(val)
                rc[i].paragraphs[0].runs[0].font.size = Pt(8.5)
                if fill:
                    self._shd_cell(rc[i], "F2F2F2")
            fill = not fill
        self.doc.add_paragraph()

    def _insert_image(self, img_bytes: bytes | None, width_mm: float = 160):
        if not img_bytes:
            self._note("(Diagram not available — plotly/kaleido not installed on this server.)")
            return
        buf = io.BytesIO(img_bytes)
        pic = self.doc.add_picture(buf, width=Mm(width_mm))
        self.doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ────────────────────────────────────────────────────────────────────────
    # COVER PAGE
    # ────────────────────────────────────────────────────────────────────────
    def _cover(self):
        doc = self.doc
        doc.add_paragraph()
        doc.add_paragraph()
        t = doc.add_paragraph("HOLLOW CORE SLAB\nSTRUCTURAL DESIGN CALCULATION")
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in t.runs:
            run.font.bold      = True
            run.font.size      = Pt(20)
            run.font.color.rgb = self._NAVY

        doc.add_paragraph()
        self._kv_table([
            ("Project",   "HCS Design — Automatically generated report"),
            ("Code ref.", "ACI/PCI CODE-319-25  |  PCI Design Handbook, 8th Edition"),
            ("Units",     "mm · kN · MPa  (SI only, no conversions)"),
            ("Date",      datetime.now().strftime("%d %B %Y   %H:%M")),
            ("Software",  "HCS Design App v1.0  (Streamlit Cloud)"),
        ])
        self._note(
            "DISCLAIMER: This report is auto-generated.  The engineer of record must verify "
            "all inputs, assumptions, and results before any use in design or construction."
        )
        doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 1 — DESIGN INPUTS
    # ────────────────────────────────────────────────────────────────────────
    def _ch1_inputs(self):
        ss = self.ss
        self._h1("1.  Design Inputs")

        # 1.1 Concrete
        self._h2("1.1  Concrete Properties")
        self._note("Elastic modulus per ACI 318-19 Eq. 19.2.2.1:  Ec = 0.043 × wc^1.5 × sqrt(f'c)  [wc in kg/m³]")
        rows = [
            ("f'ci  — strength at release / transfer",    f"{_g(ss,'f_ci'):.0f} MPa"),
            ("f'c_cut — strength at wire cutting",         f"{_g(ss,'f_c_cut'):.0f} MPa"),
            ("f'c_del — strength at delivery",             f"{_g(ss,'f_c_del'):.0f} MPa"),
            ("f'c_ere — strength at erection",             f"{_g(ss,'f_c_ere'):.0f} MPa"),
            ("f'c     — 28-day design strength",           f"{_g(ss,'f_c'):.0f} MPa"),
            ("wc      — HCS unit weight",                  f"{_g(ss,'wc'):.1f} kN/m³"),
            ("Ec_hcs  — HCS elastic modulus (auto)",       f"{_g(ss,'Ec_hcs'):.0f} MPa"),
            ("Structural topping",                         "Yes" if _g(ss,"has_topping") else "No"),
        ]
        if _g(ss, "has_topping"):
            rows += [
                ("f'c_top — topping strength",             f"{_g(ss,'f_c_top'):.0f} MPa"),
                ("wc_top  — topping unit weight",          f"{_g(ss,'wc_top'):.1f} kN/m³"),
                ("Ec_top  — topping modulus (auto)",       f"{_g(ss,'Ec_top'):.0f} MPa"),
                ("n_mod   — modular ratio Ec_top/Ec_hcs",  f"{_g(ss,'n_mod'):.4f}"),
            ]
        self._kv_table(rows)

        # 1.2 Section geometry
        self._h2("1.2  Section Geometry")
        cs   = _g(ss, "core_shape",  "Teardrop")
        rows = [
            ("b_nominal — nominal panel width",    f"{_g(ss,'b_nominal'):.0f} mm"),
            ("b_bottom  — actual bottom width",    f"{_g(ss,'b_bottom'):.0f} mm"),
            ("b_top     — top flange width",       f"{_g(ss,'b_top'):.0f} mm"),
            ("h         — total HCS thickness",    f"{_g(ss,'h'):.0f} mm"),
            ("tf_top    — top flange thickness",   f"{_g(ss,'tf_top'):.0f} mm"),
            ("tf_bot    — bottom flange thickness",f"{_g(ss,'tf_bot'):.0f} mm"),
            ("t_topping — structural topping",     f"{_g(ss,'t_topping'):.0f} mm"),
            ("HCS type",                           _g(ss,"hcs_type","Full HCS")),
            ("Core shape",                         cs),
            ("d_core    — core diameter",          f"{_g(ss,'d_core'):.0f} mm"),
            ("n_core    — number of cores",        f"{int(_g(ss,'n_core',9))}"),
        ]
        if cs == "Capsule":
            rows.append(("h_straight — capsule straight segment", f"{_g(ss,'h_straight'):.0f} mm"))
        if cs == "Teardrop":
            rows.append(("h_taper    — taper height",             f"{_g(ss,'h_taper'):.0f} mm"))
        rows += [
            ("h_core    — total void height (auto)",  f"{_g(ss,'h_core'):.1f} mm"),
            ("A_core_1  — area of one core (auto)",   f"{_g(ss,'A_core_1'):.1f} mm²"),
            ("A_voids_total (auto)",                  f"{_g(ss,'A_voids_total'):.0f} mm²"),
            ("bw_shear  — effective web width (auto)",f"{_g(ss,'bw_shear'):.0f} mm"),
        ]
        self._kv_table(rows)

        # 1.3 Prestressing steel
        self._h2("1.3  Prestressing Steel")
        ps_type = _g(ss, "ps_type", "PC Wire")
        rows = [
            ("Type",                       ps_type),
            ("Wire dia / Strand size",
             f"{_g(ss,'wire_dia'):.1f} mm" if "Wire" in ps_type else _g(ss,"strand_size","—")),
            ("ps_area — area per unit",    f"{_g(ss,'ps_area'):.2f} mm²"),
            ("fpu     — ultimate strength",f"{_g(ss,'fpu'):.0f} MPa"),
            ("fpy     — yield strength",   f"{_g(ss,'fpy'):.0f} MPa"),
            ("Eps     — elastic modulus",  f"{_g(ss,'Eps'):.0f} MPa"),
            ("n_bot   — bottom tendon count",     f"{int(_g(ss,'n_bot',0))}"),
            ("n_top   — top tendon count",        f"{int(_g(ss,'n_top',0))}"),
            ("cover_bot — clear cover to bot CL", f"{_g(ss,'cover_bot'):.0f} mm"),
            ("dp_bot    — effective depth (auto)", f"{_g(ss,'dp_bot'):.0f} mm"),
            ("fpi_pct   — initial prestress",     f"{_g(ss,'fpi_pct'):.1f} % of fpu"),
            ("fpi       — initial stress (auto)", f"{_g(ss,'fpi'):.1f} MPa"),
            ("Aps_bot   — total bottom area",     f"{_g(ss,'Aps_bot'):.1f} mm²"),
            ("Aps_top   — total top area",        f"{_g(ss,'Aps_top'):.1f} mm²"),
            ("Pi        — initial prestress force",f"{_g(ss,'Pi'):.2f} kN"),
        ]
        self._kv_table(rows)

        # 1.4 Span, bearings, loads
        self._h2("1.4  Span, Bearings and Loads")
        self._note(
            "Load combination: wu = 1.2(SW_HCS + SW_top + SDL) + 1.6LL "
            "[ASCE 7 / ACI 318-19 Table 5.3.1]"
        )
        rows = [
            ("L_cc     — centre-to-centre span",   f"{_g(ss,'L_cc'):.0f} mm"),
            ("b_bear_L — left bearing width",      f"{_g(ss,'b_bear_L'):.0f} mm"),
            ("b_bear_R — right bearing width",     f"{_g(ss,'b_bear_R'):.0f} mm"),
            ("L_clear  — clear span (auto)",       f"{_g(ss,'L_clear'):.0f} mm"),
            ("L_an     — analysis span (auto)",    f"{_g(ss,'L_an'):.0f} mm"),
            ("Span type",                          _g(ss,"span_type","Clear span")),
            ("Minimum bearing (auto)",             f"{_g(ss,'bear_min'):.1f} mm"),
            ("SW_HCS     — HCS self-weight",       f"{_g(ss,'SW_HCS'):.3f} kN/m²"),
            ("SW_topping — topping self-weight",   f"{_g(ss,'SW_topping'):.3f} kN/m²"),
            ("SDL  — superimposed dead load",      f"{_g(ss,'SDL'):.2f} kN/m²"),
            ("LL   — live load",                   f"{_g(ss,'LL'):.2f} kN/m²"),
            ("wu   — factored UDL (auto)",         f"{_g(ss,'lb_wu_area'):.3f} kN/m²"),
            ("Vu_max — max factored shear (auto)", f"{_g(ss,'lb_Vu_max'):.2f} kN"),
            ("Mu_max — max factored moment (auto)",f"{_g(ss,'lb_Mu_max',0)/1e6:.2f} kN·m"),
            ("Ra   — left reaction (auto)",        f"{_g(ss,'lb_Ra_u'):.2f} kN"),
            ("SDC  — seismic design category",     _g(ss,"sdc","B")),
            ("RH   — relative humidity",           f"{_g(ss,'RH'):.0f} %"),
            ("V/S  — volume/surface ratio",        f"{_g(ss,'V_S'):.1f} mm"),
        ]
        self._kv_table(rows)
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 2 — TRANSFER & DEVELOPMENT LENGTH
    # ────────────────────────────────────────────────────────────────────────
    def _ch2_transfer(self):
        ss   = self.ss
        self._h1("2.  Transfer Length and Development Length")
        self._note("Ref: PCI Design Handbook 8th Ed. Sec. 4.2.3  |  ACI 318-19 §25.8.6, §25.8.7")

        ps_type = _g(ss, "ps_type", "PC Wire")
        l_t   = float(_g(ss, "lb_l_t",     250.0))
        l_d   = float(_g(ss, "lb_l_d",     380.0))
        fse   = float(_g(ss, "lb_fse_est", 970.0))
        fps   = float(_g(ss, "lb_fps_est", 1500.0))
        fpi   = float(_g(ss, "fpi",        1213.5))
        fpu   = float(_g(ss, "fpu",        1618.0))
        fpy   = float(_g(ss, "fpy",        1432.0))
        L_an  = float(_g(ss, "L_an",       5850.0))
        d_ps  = (float(_g(ss,"wire_dia",5.0)) if "Wire" in ps_type
                 else l_t / 50.0)  # back-derive for strand display

        # 2.1 Transfer length
        self._h2("2.1  Transfer Length  l_t")
        if "Wire" in ps_type:
            d_ps = float(_g(ss, "wire_dia", 5.0))
            self._calc(
                f"  l_t  =  50 × d_ps",
                "PCI 8th Ed. Sec. 4.2.3"
            )
            self._calc(
                f"  l_t  =  50 × {d_ps:.1f}  =  {l_t:.1f} mm"
            )
        else:
            l_t60  = 60.0 * d_ps
            l_taci = fse / 20.7 * d_ps
            self._calc(
                f"  l_t  =  max( 60 × d_ps,  fse/20.7 × d_ps )",
                "ACI 318-19 §25.8.6.1"
            )
            self._calc(
                f"  l_t  =  max( 60 × {d_ps:.1f},  {fse:.1f}/20.7 × {d_ps:.1f} )"
            )
            self._calc(
                f"  l_t  =  max( {l_t60:.1f},  {l_taci:.1f} )  =  {l_t:.1f} mm"
            )

        # 2.2 Development length
        self._h2("2.2  Development Length  l_d")
        self._note(
            "Preliminary estimate: fps = min(fpu, fpy + 70);  fse = fpi × (1 − 0.20).\n"
            "Both values will be refined with exact losses (Phase 3) and fps iteration (Phase 5)."
        )
        self._calc(
            f"  fse  =  fpi × (1 − 0.20)  =  {fpi:.1f} × 0.80  =  {fse:.1f} MPa",
            "assumed 20% loss (PCI Sec. 4.7)"
        )
        self._calc(
            f"  fps  =  min( fpu, fpy + 70 )  =  min( {fpu:.1f}, {fpy:.1f} + 70 )  =  {fps:.1f} MPa",
            "ACI 318-19 §20.3.2.4 (conservative)"
        )
        self._calc(
            f"  l_d  =  l_t  +  (fps − fse) × d_ps / 20.7",
            "ACI 318-19 Eq. 25.8.7.1 (SI)"
        )
        self._calc(
            f"  l_d  =  {l_t:.1f}  +  ({fps:.1f} − {fse:.1f}) × {d_ps:.1f} / 20.7"
        )
        self._calc(
            f"  l_d  =  {l_t:.1f}  +  {(fps-fse)*d_ps/20.7:.1f}  =  {l_d:.1f} mm"
        )

        # 2.3 Status
        self._h2("2.3  Prestress Development Check")
        ratio  = L_an / l_d if l_d > 0 else 0.0
        status = _g(ss, "lb_ps_status", "FULL")
        msg    = _g(ss, "lb_ps_message", "")
        self._calc(
            f"  L_an / l_d  =  {L_an:.0f} / {l_d:.1f}  =  {ratio:.3f}",
            "ACI 318-19 §25.8.7"
        )
        if status == "FULL":
            self._ok(f"FULL development  (ratio = {ratio:.3f} ≥ 1.50)  —  {msg}")
        elif status == "PARTIAL":
            self._warn(f"PARTIAL development  (ratio = {ratio:.3f})  —  {msg}")
        else:
            self._warn(f"NON-PRESTRESSED  (ratio = {ratio:.3f} < 1.0)  —  {msg}")
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 3 — SECTION PROPERTIES
    # ────────────────────────────────────────────────────────────────────────
    def _ch3_section_props(self):
        ss = self.ss
        self._h1("3.  Section Properties")
        self._note(
            "Coordinate system: y measured upward from the BOTTOM FACE of HCS (topping excluded).\n"
            "Simplification: cross-section modelled as rectangular b_top × h; "
            "void centroid at y_void = tf_bot + h_core/2.  Accuracy > 97% (PCI practice).\n"
            "Transformed steel: (n_ps − 1) × Aps method (concrete already in gross).\n"
            "Ref: ACI/PCI CODE-319-25 Cl. 26.12  |  PCI Design Handbook 8th Ed. Sec. 2.2"
        )

        b_top  = float(_g(ss,"b_top",  1187.0))
        h      = float(_g(ss,"h",       200.0))
        tf_bot = float(_g(ss,"tf_bot",   50.0))
        h_core = float(_g(ss,"h_core",  120.0))
        n_core = int  (_g(ss,"n_core",    9))
        A_c1   = float(_g(ss,"A_core_1", 7107.0))
        A_void = float(_g(ss,"A_voids_total", 63959.0))
        Aps_b  = float(_g(ss,"Aps_bot",  196.0))
        Aps_t  = float(_g(ss,"Aps_top",    0.0))
        dp_bot = float(_g(ss,"dp_bot",   165.0))
        dp_top = float(_g(ss,"dp_top",    30.0))
        n_ps   = float(_g(ss,"sp_n_ps",   5.41))
        Ec_hcs = float(_g(ss,"Ec_hcs", 36793.0))
        Eps    = float(_g(ss,"Eps",   199050.0))

        # pulled from Phase 2 calculations
        Ag    = float(_g(ss,"sp_Ag",     b_top*h))
        yb_g  = float(_g(ss,"sp_yb_g",  h/2))
        Ig    = float(_g(ss,"sp_Ig",     b_top*h**3/12))
        Sb_g  = float(_g(ss,"sp_Sb_g",  Ig/yb_g if yb_g>0 else 0))
        St_g  = float(_g(ss,"sp_St_g",  Ig/(h-yb_g) if h-yb_g>0 else 0))

        An    = float(_g(ss,"sp_An",    1.0))
        yb    = float(_g(ss,"sp_yb",    1.0))
        yt    = float(_g(ss,"sp_yt",    1.0))
        In    = float(_g(ss,"sp_In",    1.0))
        Sb_n  = float(_g(ss,"sp_Sb",    1.0))
        St_n  = float(_g(ss,"sp_St",    1.0))
        r2    = float(_g(ss,"sp_r2",    1.0))
        e_bot = float(_g(ss,"sp_e_bot", 1.0))

        A_comp  = float(_g(ss,"sp_A_comp",   1.0))
        yb_comp = float(_g(ss,"sp_yb_comp",  1.0))
        yt_comp = float(_g(ss,"sp_yt_comp",  1.0))
        I_comp  = float(_g(ss,"sp_I_comp",   1.0))
        Sbc     = float(_g(ss,"sp_Sbc_comp", 1.0))
        Stc     = float(_g(ss,"sp_Stc_comp", 1.0))

        # ── 3.1 Gross ─────────────────────────────────────────────────────
        self._h2("3.1  Gross Section  (rectangular b_top × h, no voids, no steel)")
        self._note("Ref: ACI/PCI CODE-319-25 Cl. 26.12.1")
        self._calc(
            f"  Ag   =  b_top × h  =  {b_top:.0f} × {h:.0f}  =  {Ag:,.0f} mm²"
        )
        self._calc(
            f"  yb_g =  h / 2  =  {h:.0f} / 2  =  {yb_g:.1f} mm   (centroid from bottom)"
        )
        self._calc(
            f"  Ig   =  b_top × h³ / 12  =  {b_top:.0f} × {h:.0f}³ / 12  =  {Ig/1e6:.4f} × 10⁶ mm⁴"
        )
        self._calc(
            f"  Sb_g =  Ig / yb_g  =  {Ig/1e6:.4f}e6 / {yb_g:.1f}  =  {Sb_g/1e3:.2f} × 10³ mm³"
        )
        self._calc(
            f"  St_g =  Ig / yt_g  =  {Ig/1e6:.4f}e6 / {h-yb_g:.1f}  =  {St_g/1e3:.2f} × 10³ mm³"
        )

        # ── 3.2 Net ───────────────────────────────────────────────────────
        self._h2("3.2  Net HCS Section  (voids subtracted + transformed steel)")
        self._note("Ref: PCI Design Handbook 8th Ed. Sec. 2.2.1")

        y_void   = tf_bot + h_core / 2.0
        An_conc  = b_top * h - A_void
        dA_bot   = (n_ps - 1.0) * Aps_b
        dA_top   = (n_ps - 1.0) * Aps_t

        self._note("STEP A — Concrete net area:")
        self._calc(
            f"  y_void_c  =  tf_bot + h_core/2  =  {tf_bot:.0f} + {h_core:.1f}/2  =  {y_void:.2f} mm"
        )
        self._calc(
            f"  A_net_c   =  b_top × h − A_voids  =  {b_top:.0f} × {h:.0f} − {A_void:.0f}  =  {An_conc:,.0f} mm²"
        )

        self._note(f"STEP B — Transformed steel  (n_ps − 1) × Aps:  n_ps = Eps/Ec_hcs = {Eps:.0f}/{Ec_hcs:.0f} = {n_ps:.3f}")
        self._calc(
            f"  dA_bot  =  (n_ps − 1) × Aps_bot  =  ({n_ps:.3f} − 1) × {Aps_b:.1f}  =  {dA_bot:.1f} mm²"
        )
        if Aps_t > 0:
            self._calc(
                f"  dA_top  =  (n_ps − 1) × Aps_top  =  ({n_ps:.3f} − 1) × {Aps_t:.1f}  =  {dA_top:.1f} mm²"
            )

        self._note("STEP C — Net section totals (parallel-axis theorem):")
        self._calc(
            f"  An   =  A_net_c + dA_bot + dA_top  =  {An_conc:,.0f} + {dA_bot:.1f} + {dA_top:.1f}  =  {An:,.2f} mm²"
        )
        self._calc(
            f"  yb   =  Σ(A × y) / An  =  {yb:.4f} mm   (centroid from bottom)"
        )
        self._calc(
            f"  yt   =  h − yb  =  {h:.0f} − {yb:.4f}  =  {yt:.4f} mm"
        )
        self._calc(
            f"  In   =  {In/1e6:.4f} × 10⁶ mm⁴   (parallel-axis, all elements)"
        )
        self._calc(
            f"  Sb_n =  In / yb  =  {In/1e6:.4f}e6 / {yb:.4f}  =  {Sb_n/1e3:.3f} × 10³ mm³"
        )
        self._calc(
            f"  St_n =  In / yt  =  {In/1e6:.4f}e6 / {yt:.4f}  =  {St_n/1e3:.3f} × 10³ mm³"
        )
        self._calc(
            f"  r²   =  In / An  =  {In/1e6:.4f}e6 / {An:,.2f}  =  {r2:.2f} mm²   (radius of gyration²)"
        )
        self._calc(
            f"  e_bot =  dp_bot − yb  =  {dp_bot:.0f} − {yb:.4f}  =  {e_bot:.4f} mm   (+ve = below NA = favourable)"
        )

        kt = In / (An * yb)  if An * yb > 0 else 0.0
        kb = In / (An * yt)  if An * yt > 0 else 0.0
        self._note("Kern limits (no-tension zone boundary):")
        self._calc(
            f"  k_t  =  In / (An × yb)  =  {In/1e6:.4f}e6 / ({An:,.2f} × {yb:.4f})  =  {kt:.2f} mm   (upper kern from top)",
            "ACI/PCI 319-25 Cl. 22.5"
        )
        self._calc(
            f"  k_b  =  In / (An × yt)  =  {In/1e6:.4f}e6 / ({An:,.2f} × {yt:.4f})  =  {kb:.2f} mm   (lower kern from bottom)"
        )

        # ── 3.3 Composite ─────────────────────────────────────────────────
        has_top  = bool(_g(ss,"has_topping"))
        t_top    = float(_g(ss,"t_topping", 0.0))
        if has_top and t_top > 0:
            self._h2("3.3  Composite Section  (net HCS + transformed structural topping)")
            self._note("Ref: PCI Design Handbook 8th Ed. Sec. 4.2.3")
            n_mod    = float(_g(ss,"n_mod",   0.818))
            b_nom    = float(_g(ss,"b_nominal",1200.0))
            b_top_tr = b_nom / n_mod
            A_top_tr = b_top_tr * t_top
            y_top_c  = h + t_top / 2.0
            self._calc(
                f"  b_top_tr  =  b_nominal / n_mod  =  {b_nom:.0f} / {n_mod:.4f}  =  {b_top_tr:.2f} mm",
                "transformed topping width"
            )
            self._calc(
                f"  A_top_tr  =  b_top_tr × t_top  =  {b_top_tr:.2f} × {t_top:.0f}  =  {A_top_tr:,.2f} mm²"
            )
            self._calc(
                f"  y_top_c   =  h + t_top/2  =  {h:.0f} + {t_top:.0f}/2  =  {y_top_c:.1f} mm   (from HCS bottom)"
            )
            self._calc(
                f"  A_comp    =  An + A_top_tr  =  {An:,.2f} + {A_top_tr:,.2f}  =  {A_comp:,.2f} mm²"
            )
            self._calc(
                f"  yb_comp   =  Σ(A × y) / A_comp  =  {yb_comp:.4f} mm   (from HCS bottom)"
            )
            self._calc(
                f"  yt_comp   =  (h + t_top) − yb_comp  =  {h+t_top:.0f} − {yb_comp:.4f}  =  {yt_comp:.4f} mm   (from top)"
            )
            self._calc(
                f"  I_comp    =  {I_comp/1e6:.4f} × 10⁶ mm⁴   (parallel-axis)"
            )
            self._calc(
                f"  Sbc_comp  =  I_comp / yb_comp  =  {Sbc/1e3:.3f} × 10³ mm³   (HCS bottom fibre)"
            )
            self._calc(
                f"  Stc_comp  =  I_comp / yt_comp  =  {Stc/1e3:.3f} × 10³ mm³   (topping top fibre)"
            )
        else:
            self._h2("3.3  Composite Section")
            self._note("No structural topping — composite section equals net HCS section.")

        # ── 3.4 Summary table ─────────────────────────────────────────────
        self._h2("3.4  Summary Table")
        self._wide_table(
            ["Property", "Gross", "Net HCS", "Composite"],
            [
                ["Area A  (mm²)",         f"{Ag:,.0f}",       f"{An:,.2f}",        f"{A_comp:,.2f}"],
                ["yb  (mm)",              f"{yb_g:.2f}",      f"{yb:.4f}",         f"{yb_comp:.4f}"],
                ["yt  (mm)",              f"{h-yb_g:.2f}",    f"{yt:.4f}",         f"{yt_comp:.4f}"],
                ["I   (×10⁶ mm⁴)",        f"{Ig/1e6:.4f}",    f"{In/1e6:.4f}",     f"{I_comp/1e6:.4f}"],
                ["Sb  (×10³ mm³)",        f"{Sb_g/1e3:.3f}",  f"{Sb_n/1e3:.3f}",   f"{Sbc/1e3:.3f}"],
                ["St  (×10³ mm³)",        f"{St_g/1e3:.3f}",  f"{St_n/1e3:.3f}",   f"{Stc/1e3:.3f}"],
                ["r²  (mm²)",             "—",                f"{r2:.2f}",          "—"],
                ["e_bot (mm)",            "—",                f"{e_bot:.4f}",       "—"],
                ["k_t  (mm)",             "—",                f"{kt:.2f}",          "—"],
                ["k_b  (mm)",             "—",                f"{kb:.2f}",          "—"],
            ]
        )
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 4 — PRESTRESS LOSSES
    # ────────────────────────────────────────────────────────────────────────
    def _ch4_losses(self):
        ss = self.ss
        self._h1("4.  Prestress Losses")
        self._note(
            "Method: PCI Lump-Sum  (ES + CR + SH + RE)\n"
            "Ref: PCI Design Handbook 8th Ed. Sec. 4.7  |  ACI/PCI CODE-319-25 Cl. 26.10"
        )

        fpi    = float(_g(ss,"fpi",     1213.5))
        Pi     = float(_g(ss,"Pi",       237.8))
        Aps_b  = float(_g(ss,"Aps_bot",  196.0))
        Aps_t  = float(_g(ss,"Aps_top",    0.0))
        An     = float(_g(ss,"sp_An",  174000.0))
        In     = float(_g(ss,"sp_In",    776e6))
        e_bot  = float(_g(ss,"sp_e_bot",  68.35))
        r2     = float(_g(ss,"sp_r2",   4454.0))
        f_ci   = float(_g(ss,"f_ci",      35.0))
        f_c    = float(_g(ss,"f_c",       50.0))
        Ec_hcs = float(_g(ss,"Ec_hcs", 36793.0))
        Eps    = float(_g(ss,"Eps",   199050.0))
        RH     = float(_g(ss,"RH",       75.0))
        V_S    = float(_g(ss,"V_S",      38.0))
        ES     = float(_g(ss,"pl_ES",     0.0))
        CR     = float(_g(ss,"pl_CR",     0.0))
        SH     = float(_g(ss,"pl_SH",     0.0))
        RE     = float(_g(ss,"pl_RE",     0.0))
        total  = float(_g(ss,"pl_total_MPa", ES+CR+SH+RE))
        pct    = float(_g(ss,"pl_total_pct", total/fpi*100 if fpi>0 else 0))
        fse    = float(_g(ss,"pl_fse",  fpi-total))
        Pe     = float(_g(ss,"pl_Pe",   0.0))
        n_ps   = Eps / Ec_hcs

        # 4.1 Elastic shortening
        self._h2("4.1  Elastic Shortening  (ES)")
        self._note(
            "ES = n_ps × f_cir  ×  (K_es)\n"
            "For pretensioned members K_es ≈ 0.5 (average over strand length).\n"
            "f_cir = concrete stress at steel CG immediately after transfer."
        )
        self._calc(
            f"  n_ps  =  Eps / Ec_hcs  =  {Eps:.0f} / {Ec_hcs:.0f}  =  {n_ps:.4f}",
            "ACI 318-19 Eq. 19.2.2.1"
        )
        Pi_N   = Pi * 1000.0
        f_cir_est = Pi_N/An + Pi_N*e_bot**2/In
        self._calc(
            f"  f_cir =  Pi/An + Pi×e_bot²/In",
            "PCI 8th Ed. Eq. 4.7.2 (SW moment neglected for estimate)"
        )
        self._calc(
            f"  f_cir =  {Pi_N:.0f}/{An:.0f} + {Pi_N:.0f}×{e_bot:.2f}²/{In:.3e}"
        )
        self._calc(
            f"  f_cir =  {Pi_N/An:.4f} + {Pi_N*e_bot**2/In:.4f}  =  {f_cir_est:.4f} MPa"
        )
        self._calc(
            f"  ES    =  n_ps × 0.5 × f_cir  =  {n_ps:.4f} × 0.5 × {f_cir_est:.4f}  =  {ES:.3f} MPa",
            "PCI 8th Ed. Sec. 4.7.2"
        )

        # 4.2 Creep
        self._h2("4.2  Creep Loss  (CR)")
        self._note(
            "CR = 12 × (f_cir − f_cds)\n"
            "f_cds = stress at steel CG due to all sustained loads applied after transfer."
        )
        self._calc(
            f"  CR  =  12 × (f_cir − f_cds)  =  {CR:.3f} MPa",
            "PCI 8th Ed. Eq. 4.7.3"
        )

        # 4.3 Shrinkage
        self._h2("4.3  Shrinkage Loss  (SH)")
        self._calc(
            f"  SH  =  117 × (1 − 0.0123 × V/S) × (1 − 0.00327 × (RH − 40))",
            "PCI 8th Ed. Eq. 4.7.4"
        )
        self._calc(
            f"  SH  =  117 × (1 − 0.0123 × {V_S:.1f}) × (1 − 0.00327 × ({RH:.0f} − 40))"
        )
        self._calc(
            f"  SH  =  {SH:.3f} MPa"
        )

        # 4.4 Relaxation
        self._h2("4.4  Relaxation Loss  (RE)")
        self._note(
            "RE = [Kre − J × (SH + CR + ES)] × C\n"
            "Kre, J, C per PCI Table 4.7.5 (type-dependent)."
        )
        self._calc(
            f"  RE  =  [Kre − J × (SH + CR + ES)] × C  =  {RE:.3f} MPa",
            "PCI 8th Ed. Eq. 4.7.5"
        )

        # 4.5 Totals
        self._h2("4.5  Total Loss and Effective Prestress")
        self._calc(
            f"  Total loss  =  ES + CR + SH + RE"
        )
        self._calc(
            f"              =  {ES:.3f} + {CR:.3f} + {SH:.3f} + {RE:.3f}"
        )
        self._calc(
            f"              =  {total:.3f} MPa   ({pct:.2f} % of fpi = {fpi:.1f} MPa)"
        )
        self._calc(
            f"  fse  =  fpi − Total  =  {fpi:.1f} − {total:.3f}  =  {fse:.3f} MPa"
        )
        self._calc(
            f"  Pe   =  (Aps_bot + Aps_top) × fse / 1000"
        )
        self._calc(
            f"       =  ({Aps_b:.1f} + {Aps_t:.1f}) × {fse:.3f} / 1000  =  {Pe:.3f} kN"
        )
        self._calc(
            f"  Pe / Pi  =  {Pe:.3f} / {Pi:.3f}  =  {Pe/Pi:.4f}" if Pi > 0 else
            "  Pi not available."
        )

        # Summary table
        self._h2("4.6  Loss Summary Table")
        self._wide_table(
            ["Component", "Value (MPa)", "% of fpi"],
            [
                ["Elastic shortening  ES",  f"{ES:.3f}",   f"{ES/fpi*100:.2f}" if fpi>0 else "—"],
                ["Creep               CR",  f"{CR:.3f}",   f"{CR/fpi*100:.2f}" if fpi>0 else "—"],
                ["Shrinkage           SH",  f"{SH:.3f}",   f"{SH/fpi*100:.2f}" if fpi>0 else "—"],
                ["Relaxation          RE",  f"{RE:.3f}",   f"{RE/fpi*100:.2f}" if fpi>0 else "—"],
                ["TOTAL",                   f"{total:.3f}",f"{pct:.2f}"],
                ["fse  (effective)",        f"{fse:.3f}",  "—"],
                ["Pe   (effective force kN)",f"{Pe:.3f}",  "—"],
            ]
        )
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 5 — STRESS CHECKS
    # ────────────────────────────────────────────────────────────────────────
    def _ch5_stress(self):
        ss = self.ss
        self._h1("5.  Stress Checks at All Stages")
        self._note(
            "Sign convention:  compression (−) negative,  tension (+) positive.\n"
            "Code limits — ACI/PCI CODE-319-25 Table 24.5.3.1:\n"
            "  Compression limit:  −0.60 f'ci (release)  /  −0.45 f'c (service)\n"
            "  Tension limit:      +0.25√f'ci (release)  /  +0.50√f'c (Class U)  "
            "or Class T / C per engineer's choice."
        )

        Pe     = float(_g(ss,"pl_Pe",    200.0))
        An     = float(_g(ss,"sp_An", 174000.0))
        e_bot  = float(_g(ss,"sp_e_bot",  68.35))
        Sb_n   = float(_g(ss,"sp_Sb",   8032e3))
        St_n   = float(_g(ss,"sp_St",   7512e3))
        Sbc    = float(_g(ss,"sp_Sbc_comp", 13159e3))
        Stc    = float(_g(ss,"sp_Stc_comp", 16091e3))

        stages = [
            ("5.1  Transfer / Release",
             "sc_transfer",
             "f = −Pe/An  ±  Pe×e_bot/Sb  ∓  M_sw/Sb",
             "ACI/PCI 319-25 Table 24.5.3.1  |  release immediately after prestress transfer"),
            ("5.2  Lifting",
             "sc_lifting",
             "Transfer stresses plus handling moment (1% of span typical)",
             "PCI Design Handbook 8th Ed. Sec. 5.3"),
            ("5.3  Construction  (wet topping, non-composite)",
             "sc_construction",
             "f = −Pe/An  ±  Pe×e/Sb  ∓  M_DL/Sb   [non-composite section]",
             "ACI/PCI 319-25 Table 24.5.3.1"),
            ("5.4  Service  (composite section, SDL + LL)",
             "sc_service",
             "DL moment → net section (Sb_n, St_n);  SDL+LL moment → composite (Sbc, Stc)",
             "ACI/PCI 319-25 Table 24.5.3.1  |  Class T/U/C per project specification"),
        ]

        summary_rows = []
        for title, key, formula, ref in stages:
            self._h2(title)
            self._note(f"Formula:  {formula}")
            self._note(f"Ref: {ref}")

            d = ss.get(key, {})
            if not d:
                self._note("  (data not yet available — run calculations first)")
                summary_rows.append([title.split(" ")[1], "—", "—", "—", "—", "N/A"])
                continue

            f_top    = float(d.get("f_top",    0.0))
            f_bot    = float(d.get("f_bot",    0.0))
            lim_comp = float(d.get("limit_comp", 0.0))
            lim_tens = float(d.get("limit_tens", 0.0))
            status   = str(d.get("status", "N/A"))

            self._calc(f"  f_top  =  {f_top:.4f} MPa")
            self._calc(f"  f_bot  =  {f_bot:.4f} MPa")
            self._calc(f"  Limit (compression)  =  {lim_comp:.3f} MPa")
            self._calc(f"  Limit (tension)      =  {lim_tens:.4f} MPa")
            ok = status.upper() in ("OK", "PASS", "OK ")
            self._status_line(f"Status: {status}", ok)
            summary_rows.append([
                title.split("  ")[0].strip(),
                f"{f_top:.3f}",
                f"{f_bot:.3f}",
                f"{lim_comp:.2f}",
                f"{lim_tens:.4f}",
                status,
            ])

        self._h2("5.5  Stress Check Summary")
        self._wide_table(
            ["Stage", "f_top (MPa)", "f_bot (MPa)", "Lim comp (MPa)", "Lim tens (MPa)", "Status"],
            summary_rows
        )
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 6 — CAPACITY
    # ────────────────────────────────────────────────────────────────────────
    def _ch6_capacity(self):
        ss = self.ss
        self._h1("6.  Flexural and Shear Capacity")
        self._note("Ref: ACI/PCI CODE-319-25 Cl. 22.2 (flexure)  |  Cl. 22.5 (shear)")

        fps    = float(_g(ss,"cap_fps",        1400.0))
        a      = float(_g(ss,"cap_a",            30.0))
        Mn     = float(_g(ss,"cap_Mn",          200.0))
        phi_Mn = float(_g(ss,"cap_phi_Mn",      180.0))
        Mu_max = float(_g(ss,"lb_Mu_max",          0.0)) / 1e6
        DCR_M  = float(_g(ss,"cap_DCR_M",          1.0))
        phi_Vn = float(_g(ss,"cap_phi_Vn_min",    50.0))
        Vu_max = float(_g(ss,"lb_Vu_max",          0.0))
        DCR_V  = float(_g(ss,"cap_DCR_V",          1.0))
        Aps_b  = float(_g(ss,"Aps_bot",           196.0))
        dp_bot = float(_g(ss,"dp_bot",            165.0))
        f_c    = float(_g(ss,"f_c",               50.0))
        b_top  = float(_g(ss,"b_top",           1187.0))
        fpu    = float(_g(ss,"fpu",            1618.0))
        needs_Av = bool(_g(ss,"cap_needs_Av_min", False))

        # 6.1 Flexural
        self._h2("6.1  Flexural Capacity  Mn  (Whitney stress block)")
        self._calc(
            f"  fps  =  {fps:.2f} MPa   (ACI Eq. 20.3.2.4 — iterated)",
            "ACI 318-19 Cl. 20.3.2"
        )
        self._calc(
            f"  a    =  Aps_bot × fps / (0.85 × f'c × b_top)",
            "ACI 318-19 Eq. 22.2.2.4.1"
        )
        self._calc(
            f"       =  {Aps_b:.1f} × {fps:.2f} / (0.85 × {f_c:.0f} × {b_top:.0f})"
        )
        self._calc(
            f"       =  {Aps_b*fps:.1f} / {0.85*f_c*b_top:.1f}  =  {a:.4f} mm"
        )
        self._calc(
            f"  Mn   =  Aps_bot × fps × (dp_bot − a/2) / 1e6",
            "ACI 318-19 Eq. 22.2.1.1"
        )
        self._calc(
            f"       =  {Aps_b:.1f} × {fps:.2f} × ({dp_bot:.0f} − {a:.4f}/2) / 1e6"
        )
        self._calc(
            f"       =  {Aps_b:.1f} × {fps:.2f} × {dp_bot - a/2:.4f} / 1e6  =  {Mn:.4f} kN·m"
        )
        self._calc(
            f"  phi·Mn  =  0.90 × {Mn:.4f}  =  {phi_Mn:.4f} kN·m",
            "ACI 318-19 Table 21.2.2  (phi = 0.90 tension-controlled)"
        )
        self._calc(
            f"  Mu_max  =  {Mu_max:.4f} kN·m   (from factored load diagram)"
        )
        self._calc(
            f"  DCR_M   =  Mu / phi·Mn  =  {Mu_max:.4f} / {phi_Mn:.4f}  =  {DCR_M:.4f}"
        )
        self._status_line(
            f"Flexure: DCR = {DCR_M:.4f} {'≤' if DCR_M<=1.0 else '>'} 1.00  →  {'OK' if DCR_M<=1.0 else 'OVERSTRESS'}",
            DCR_M <= 1.0
        )

        # 6.2 Shear
        self._h2("6.2  Shear Capacity  Vn")
        self._note(
            "HCS unreinforced shear — envelope of Vcw (web-shear) and Vci (flexure-shear).\n"
            "phi = 0.75 per ACI/PCI 319-25 Cl. 22.5.1.1."
        )
        self._calc(
            f"  min phi·Vn along span  =  {phi_Vn:.4f} kN   (governs at critical section)"
        )
        self._calc(
            f"  Vu_max (factored)      =  {Vu_max:.4f} kN"
        )
        self._calc(
            f"  DCR_V  =  Vu / phi·Vn  =  {Vu_max:.4f} / {phi_Vn:.4f}  =  {DCR_V:.4f}"
        )
        self._status_line(
            f"Shear: DCR = {DCR_V:.4f} {'≤' if DCR_V<=1.0 else '>'} 1.00  →  {'OK' if DCR_V<=1.0 else 'OVERSTRESS'}",
            DCR_V <= 1.0
        )
        if needs_Av:
            self._warn(
                "h > 317 mm, no topping, and Vu > 0.5 phi·Vcw  →  "
                "minimum shear reinforcement Av,min REQUIRED per ACI/PCI 319-25 Cl. 9.6.3."
            )

        self._h2("6.3  Capacity Summary")
        self._wide_table(
            ["Check", "Demand", "Capacity phi·R", "DCR", "Status"],
            [
                ["Flexure  Mn",
                 f"{Mu_max:.3f} kN·m",
                 f"{phi_Mn:.3f} kN·m",
                 f"{DCR_M:.4f}",
                 "OK" if DCR_M <= 1.0 else "NG"],
                ["Shear   Vn",
                 f"{Vu_max:.3f} kN",
                 f"{phi_Vn:.3f} kN",
                 f"{DCR_V:.4f}",
                 "OK" if DCR_V <= 1.0 else "NG"],
            ]
        )
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 7 — DEFLECTION & CAMBER
    # ────────────────────────────────────────────────────────────────────────
    def _ch7_deflection(self):
        ss = self.ss
        self._h1("7.  Deflection and Camber")
        self._note(
            "Ref: PCI Design Handbook 8th Ed. Sec. 4.8 and Table 4.8.3\n"
            "     ACI 318-19 Table 24.2.2 (code limits)\n"
            "Method: Elastic formulas for instantaneous; PCI multipliers for long-term.\n"
            "Sign convention: upward camber positive (+), downward deflection positive (shown as downward)."
        )

        Pe        = float(_g(ss,"pl_Pe",               200.0))
        e_bot     = float(_g(ss,"sp_e_bot",             68.35))
        In        = float(_g(ss,"sp_In",               776e6))
        Ec_hcs    = float(_g(ss,"Ec_hcs",            36793.0))
        L_an      = float(_g(ss,"L_an",               5850.0))
        delta_ps  = float(_g(ss,"def_delta_ps_initial",  0.0))
        delta_sw  = float(_g(ss,"def_delta_sw",           0.0))
        net_rel   = float(_g(ss,"def_net_release",        0.0))
        total_lt  = float(_g(ss,"def_total_longterm",     0.0))
        lim_ll    = float(_g(ss,"def_limit_ll_mm",        0.0))
        lim_tot   = float(_g(ss,"def_limit_total_mm",     0.0))
        st_ll     = str  (_g(ss,"def_status_ll",        "N/A"))
        st_tot    = str  (_g(ss,"def_status_total",     "N/A"))

        # 7.1 Prestress camber
        self._h2("7.1  Initial Prestress Camber at Release  (upward)")
        self._note("Parabolic tendon profile — uniform equivalent upward load.")
        self._calc(
            "  delta_ps  =  5 × Pe × e_bot × L_an²  /  (48 × Ec_ci × In)",
            "PCI 8th Ed. Eq. 4.8.1"
        )
        self._calc(
            f"           =  5 × {Pe*1000:.0f} × {e_bot:.4f} × {L_an:.0f}²"
            f"  /  (48 × {Ec_hcs:.0f} × {In:.6e})"
        )
        self._calc(
            f"           =  {delta_ps:.4f} mm   (upward, positive)"
        )

        # 7.2 Self-weight
        self._h2("7.2  Self-Weight Deflection at Release  (downward)")
        self._calc(
            "  delta_sw  =  5 × w_sw × L_an⁴  /  (384 × Ec_ci × In_gross)",
            "PCI 8th Ed. Eq. 4.8.2"
        )
        self._calc(
            f"           =  {delta_sw:.4f} mm   (downward)"
        )

        # 7.3 Net at release
        self._h2("7.3  Net Deflection at Release")
        self._calc(
            f"  delta_net  =  delta_sw − delta_ps  =  {delta_sw:.4f} − {delta_ps:.4f}  =  {net_rel:.4f} mm"
        )
        self._note("+ve = net sag (downward);  −ve = net upward camber.")

        # 7.4 Long-term
        self._h2("7.4  Long-term Deflection  (PCI Multipliers)")
        self._note(
            "Typical PCI Table 4.8.3 multipliers:\n"
            "  Prestress camber × 2.20  (sustained)\n"
            "  Self-weight      × 2.40  (sustained)\n"
            "  SDL              × 1.80  (sustained)\n"
            "  LL               × 1.00  (transient, instantaneous)"
        )
        self._calc(
            f"  Total long-term net deflection  =  {total_lt:.4f} mm"
        )

        # 7.5 Code limits
        self._h2("7.5  Code Limit Checks")
        self._calc(
            f"  Limit (LL):    L / 360  =  {L_an:.0f} / 360  =  {lim_ll:.2f} mm",
            "ACI 318-19 Table 24.2.2  (floors supporting non-brittle partitions)"
        )
        self._calc(
            f"  Limit (total): L / 240  =  {L_an:.0f} / 240  =  {lim_tot:.2f} mm",
            "ACI 318-19 Table 24.2.2  (total after attachment of non-structural elements)"
        )
        ok_ll  = st_ll.upper()  in ("OK", "PASS")
        ok_tot = st_tot.upper() in ("OK", "PASS")
        self._status_line(f"Live-load deflection:    {st_ll}", ok_ll)
        self._status_line(f"Total (long-term) deflection: {st_tot}", ok_tot)

        # Summary table
        self._h2("7.6  Deflection Summary")
        self._wide_table(
            ["Item", "Value (mm)", "Limit (mm)", "Status"],
            [
                ["Prestress camber (initial)",  f"{delta_ps:.4f}",  "—",               "—"],
                ["Self-weight (initial)",        f"{delta_sw:.4f}",  "—",               "—"],
                ["Net at release",               f"{net_rel:.4f}",   "—",               "—"],
                ["Total long-term",              f"{total_lt:.4f}",  f"{lim_tot:.2f}",  st_tot],
                ["LL deflection (est.)",         "—",                f"{lim_ll:.2f}",   st_ll],
            ]
        )
        self.doc.add_page_break()

    # ────────────────────────────────────────────────────────────────────────
    # CH 8 — SPAN DISTRIBUTION TABLE
    # ────────────────────────────────────────────────────────────────────────
    def _ch8_span_table(self):
        ss = self.ss
        self._h1("8.  Span Distribution Table  —  Forces at 0.1 L Intervals")
        self._note(
            "Values interpolated from the factored load arrays  "
            "(lb_x_arr / lb_Vu_arr / lb_Mu_arr  in session_state).\n"
            "x = distance from left support;  Vu and Mu are FACTORED quantities (1.2D + 1.6L)."
        )
        rows = _span_table(ss, n_seg=10)
        L_an = float(_g(ss, "L_an", 5850.0))
        self._wide_table(
            ["x/L", "x  (m)", "x  (mm)", "Vu  (kN)", "Mu  (kN·m)"],
            [
                [
                    f"{r['frac']:.1f}",
                    f"{r['x_m']:.3f}",
                    f"{r['x_mm']:.0f}",
                    f"{r['Vu_kN']:.3f}",
                    f"{r['Mu_kNm']:.3f}",
                ]
                for r in rows
            ]
        )
        # note midspan vs. support values
        mid = rows[len(rows) // 2]
        self._note(
            f"At midspan (x = {mid['x_m']:.3f} m):  "
            f"Vu = {mid['Vu_kN']:.3f} kN,   Mu = {mid['Mu_kNm']:.3f} kN·m"
        )

    # ────────────────────────────────────────────────────────────────────────
    # CH 9 — SFD / BMD DIAGRAMS
    # ────────────────────────────────────────────────────────────────────────
    def _ch9_diagrams(self, img_bytes: bytes | None):
        self._h1("9.  Shear Force and Bending Moment Diagrams")
        self._note(
            "Factored loads  (1.2D + 1.6L).  Simply-supported span.\n"
            "Shaded zones near supports = transfer-length zone  (l_t).\n"
            "Dashed lines = service load diagrams."
        )
        self._insert_image(img_bytes, width_mm=162)

    # ────────────────────────────────────────────────────────────────────────
    # APPENDIX
    # ────────────────────────────────────────────────────────────────────────
    def _appendix(self):
        self.doc.add_page_break()
        self._h1("Appendix — Remarks and Code Compliance Notes")
        items = [
            "Report generated automatically by HCS Design App v1.0.",
            "Primary code references: ACI/PCI CODE-319-25 (all chapters) and PCI Design Handbook, 8th Edition.",
            "Units: mm, kN, MPa throughout.  No unit conversions are performed.",
            "Section properties: rectangular simplification (b_top × h) with voids subtracted "
            "at centroid y_void = tf_bot + h_core/2.  Accuracy > 97% for standard HCS shapes.",
            "Prestress losses: PCI lump-sum method (ES + CR + SH + RE).  "
            "For critical projects use detailed time-step or CEB-FIP method.",
            "Development length: preliminary fps = min(fpu, fpy + 70) per ACI Cl. 20.3.2.4.  "
            "Phase 5 uses the exact iterated fps value.",
            "Deflection multipliers from PCI Table 4.8.3 — parabolic tendon profile assumed.",
            "ACI/PCI CODE-319-25 Chapter 26 — design documentation requirements: "
            "see project drawings and specifications.",
            "For SDC D/E/F: in-plane diaphragm flexibility must be modelled; "
            "untopped HCS cannot be assumed rigid (ACI/PCI 319-25 Sec. 12; ACI CODE-550.5).",
            "DISCLAIMER: Engineer of record must verify all inputs, assumptions, and results "
            "before use in design, fabrication, or construction.",
        ]
        for item in items:
            p = self.doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            p.add_run(f"\u2022  {item}").font.size = Pt(9)

    # ────────────────────────────────────────────────────────────────────────
    # BUILD
    # ────────────────────────────────────────────────────────────────────────
    def build(self, img_bytes: bytes | None = None) -> io.BytesIO:
        self._cover()
        self._ch1_inputs()
        self._ch2_transfer()
        self._ch3_section_props()
        self._ch4_losses()
        self._ch5_stress()
        self._ch6_capacity()
        self._ch7_deflection()
        self._ch8_span_table()
        self._ch9_diagrams(img_bytes)
        self._appendix()
        buf = io.BytesIO()
        self.doc.save(buf)
        buf.seek(0)
        return buf


# =============================================================================
# PDF REPORT  (fpdf2)
# =============================================================================

class _PdfReport(FPDF):
    """
    fpdf2-based PDF — mirrors the Word report chapter by chapter.
    EVERY string is passed through _ascii() before printing to prevent
    UnicodeEncodeError on Streamlit Cloud.
    """

    # Colour palette  (R, G, B)
    _NAVY  = (26,  71, 111)
    _BLUE  = (46, 116, 181)
    _GREEN = ( 0,  81,  40)
    _GREY  = (96,  96,  96)
    _RED   = (192,   0,   0)
    _WHITE = (255, 255, 255)
    _LGREY = (242, 242, 242)
    _BLACK = (  0,   0,   0)

    def __init__(self, ss: dict):
        super().__init__("P", "mm", "A4")
        self.ss = ss
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 22, 15)
        self.add_page()

    # ── fpdf2 required callbacks ────────────────────────────────────────────
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*self._GREY)
        self.cell(
            0, 5,
            _ascii("HCS Structural Design Report  |  ACI/PCI CODE-319-25  |  PCI Design Handbook 8th Ed."),
            ln=False,
        )
        self.ln(6)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(*self._BLACK)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*self._GREY)
        date_str = datetime.now().strftime("%d %b %Y %H:%M")
        self.cell(
            0, 5,
            _ascii(f"Page {self.page_no()}   |   Generated {date_str}   |   HCS Design App v1.0"),
            align="C",
        )

    # ── Low-level print helpers ─────────────────────────────────────────────
    def _h1(self, text: str):
        self.ln(3)
        self.set_fill_color(*self._NAVY)
        self.set_text_color(*self._WHITE)
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, _ascii(text), fill=True, ln=True)
        self.set_text_color(*self._BLACK)
        self.ln(2)

    def _h2(self, text: str):
        self.ln(2)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self._BLUE)
        self.multi_cell(0, 6, _ascii(text), ln=True)
        self.set_text_color(*self._BLACK)

    def _h3(self, text: str):
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*self._BLUE)
        self.multi_cell(0, 5, _ascii(text), ln=True)
        self.set_text_color(*self._BLACK)

    def _calc(self, text: str, ref: str = ""):
        """
        Green Courier calculation line.
        If ref supplied, print it right-aligned in grey italic on the same line.
        """
        text = _ascii(text)
        ref  = _ascii(ref)
        self.set_font("Courier", "", 8.5)
        self.set_text_color(*self._GREEN)
        if ref:
            ref_str  = f"  [{ref}]"
            ref_w    = self.get_string_width(ref_str) + 4
            calc_w   = self.epw - ref_w
            self.cell(calc_w, 4.5, text, ln=False)
            self.set_font("Helvetica", "I", 7.5)
            self.set_text_color(*self._GREY)
            self.cell(ref_w, 4.5, ref_str, ln=True)
        else:
            self.multi_cell(0, 4.5, text, ln=True)
        self.set_text_color(*self._BLACK)

    def _note(self, text: str):
        text = _ascii(text)
        self.set_font("Helvetica", "I", 8.5)
        self.set_text_color(*self._GREY)
        self.multi_cell(0, 4.5, text, ln=True)
        self.set_text_color(*self._BLACK)

    def _status(self, text: str, ok: bool):
        text = _ascii(text)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*(self._GREEN if ok else self._RED))
        pfx = "  [OK]  " if ok else "  [NG]  "
        self.multi_cell(0, 5, pfx + text, ln=True)
        self.set_text_color(*self._BLACK)

    # ── Table helpers ────────────────────────────────────────────────────────
    def _kv_table(self, rows: list[tuple], col_w: tuple[float, float] = (110.0, 65.0)):
        """Two-column key-value table."""
        self.set_font("Helvetica", "B", 8.5)
        self.set_fill_color(*self._NAVY)
        self.set_text_color(*self._WHITE)
        self.cell(col_w[0], 5.5, "Parameter", fill=True, border=1, ln=False)
        self.cell(col_w[1], 5.5, "Value",     fill=True, border=1, ln=True)
        self.set_text_color(*self._BLACK)
        alt = False
        for key, val in rows:
            self.set_fill_color(*(self._LGREY if alt else self._WHITE))
            self.set_font("Helvetica", "", 8.5)
            self.cell(col_w[0], 5, _ascii(str(key)), fill=True, border=1, ln=False)
            self.cell(col_w[1], 5, _ascii(str(val)), fill=True, border=1, ln=True)
            alt = not alt
        self.ln(3)

    def _wide_table(self, header: list[str], data: list[list]):
        """N-column table — auto equal column widths."""
        nc    = len(header)
        col_w = self.epw / nc
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(*self._NAVY)
        self.set_text_color(*self._WHITE)
        for h in header:
            self.cell(col_w, 5.5, _ascii(str(h)), fill=True, border=1, ln=False)
        self.ln()
        self.set_text_color(*self._BLACK)
        alt = False
        for row in data:
            self.set_fill_color(*(self._LGREY if alt else self._WHITE))
            self.set_font("Helvetica", "", 8)
            for cell in row:
                self.cell(col_w, 5, _ascii(str(cell)), fill=True, border=1, ln=False)
            self.ln()
            alt = not alt
        self.ln(3)

    def _insert_image(self, img_bytes: bytes | None, w_mm: float = 170):
        if not img_bytes:
            self._note("(Diagram not available — plotly/kaleido not installed.)")
            return
        buf = io.BytesIO(img_bytes)
        self.image(buf, x=self.l_margin, w=w_mm)
        self.ln(3)

    # ── COVER ────────────────────────────────────────────────────────────────
    def _cover(self):
        self.ln(18)
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(*self._NAVY)
        self.multi_cell(
            0, 11,
            _ascii("HOLLOW CORE SLAB\nSTRUCTURAL DESIGN CALCULATION"),
            align="C", ln=True,
        )
        self.ln(8)
        self._kv_table([
            ("Project",   "HCS Design — Automatically generated report"),
            ("Code ref.", "ACI/PCI CODE-319-25  |  PCI Design Handbook, 8th Edition"),
            ("Units",     "mm   kN   MPa  (SI only, no conversions)"),
            ("Date",      datetime.now().strftime("%d %B %Y   %H:%M")),
            ("Software",  "HCS Design App v1.0  (Streamlit Cloud)"),
        ])
        self._note(
            "DISCLAIMER: This report is auto-generated.  The engineer of record must verify "
            "all inputs, assumptions, and results before any use in design or construction."
        )
        self.add_page()

    # ── CH 1 — INPUTS ────────────────────────────────────────────────────────
    def _ch1_inputs(self):
        ss = self.ss
        self._h1("1.  Design Inputs")

        self._h2("1.1  Concrete Properties")
        self._note("Ec = 0.043 x wc^1.5 x sqrt(f'c)  [wc in kg/m3]  [ACI 318-19 Eq. 19.2.2.1]")
        rows = [
            ("f'ci  — strength at release",            f"{_g(ss,'f_ci'):.0f} MPa"),
            ("f'c_cut — strength at wire cutting",      f"{_g(ss,'f_c_cut'):.0f} MPa"),
            ("f'c_del — strength at delivery",          f"{_g(ss,'f_c_del'):.0f} MPa"),
            ("f'c_ere — strength at erection",          f"{_g(ss,'f_c_ere'):.0f} MPa"),
            ("f'c     — 28-day design strength",        f"{_g(ss,'f_c'):.0f} MPa"),
            ("wc      — HCS unit weight",               f"{_g(ss,'wc'):.1f} kN/m3"),
            ("Ec_hcs  — HCS elastic modulus (auto)",    f"{_g(ss,'Ec_hcs'):.0f} MPa"),
            ("Structural topping",                      "Yes" if _g(ss,"has_topping") else "No"),
        ]
        if _g(ss, "has_topping"):
            rows += [
                ("f'c_top — topping strength",          f"{_g(ss,'f_c_top'):.0f} MPa"),
                ("Ec_top  — topping modulus (auto)",    f"{_g(ss,'Ec_top'):.0f} MPa"),
                ("n_mod   — Ec_top / Ec_hcs",           f"{_g(ss,'n_mod'):.4f}"),
            ]
        self._kv_table(rows)

        self._h2("1.2  Section Geometry")
        cs   = _g(ss,"core_shape","Teardrop")
        rows = [
            ("b_nominal", f"{_g(ss,'b_nominal'):.0f} mm"),
            ("b_bottom",  f"{_g(ss,'b_bottom'):.0f} mm"),
            ("b_top",     f"{_g(ss,'b_top'):.0f} mm"),
            ("h",         f"{_g(ss,'h'):.0f} mm"),
            ("tf_top",    f"{_g(ss,'tf_top'):.0f} mm"),
            ("tf_bot",    f"{_g(ss,'tf_bot'):.0f} mm"),
            ("t_topping", f"{_g(ss,'t_topping'):.0f} mm"),
            ("HCS type",  _g(ss,"hcs_type","Full HCS")),
            ("Core shape",cs),
            ("d_core",    f"{_g(ss,'d_core'):.0f} mm"),
            ("n_core",    f"{int(_g(ss,'n_core',9))}"),
        ]
        if cs == "Capsule":
            rows.append(("h_straight", f"{_g(ss,'h_straight'):.0f} mm"))
        if cs == "Teardrop":
            rows.append(("h_taper",    f"{_g(ss,'h_taper'):.0f} mm"))
        rows += [
            ("h_core    (auto)",         f"{_g(ss,'h_core'):.1f} mm"),
            ("A_core_1  (auto)",         f"{_g(ss,'A_core_1'):.1f} mm^2"),
            ("A_voids_total (auto)",     f"{_g(ss,'A_voids_total'):.0f} mm^2"),
            ("bw_shear  (auto)",         f"{_g(ss,'bw_shear'):.0f} mm"),
        ]
        self._kv_table(rows)

        self._h2("1.3  Prestressing Steel")
        ps_type = _g(ss,"ps_type","PC Wire")
        rows = [
            ("Type",        ps_type),
            ("Wire/strand", f"{_g(ss,'wire_dia'):.1f} mm" if "Wire" in ps_type else _g(ss,"strand_size","--")),
            ("ps_area",     f"{_g(ss,'ps_area'):.2f} mm^2"),
            ("fpu",         f"{_g(ss,'fpu'):.0f} MPa"),
            ("fpy",         f"{_g(ss,'fpy'):.0f} MPa"),
            ("Eps",         f"{_g(ss,'Eps'):.0f} MPa"),
            ("n_bot",       f"{int(_g(ss,'n_bot',0))}"),
            ("n_top",       f"{int(_g(ss,'n_top',0))}"),
            ("cover_bot",   f"{_g(ss,'cover_bot'):.0f} mm"),
            ("dp_bot (auto)",f"{_g(ss,'dp_bot'):.0f} mm"),
            ("fpi_pct",     f"{_g(ss,'fpi_pct'):.1f} % fpu"),
            ("fpi (auto)",  f"{_g(ss,'fpi'):.1f} MPa"),
            ("Aps_bot (auto)",f"{_g(ss,'Aps_bot'):.1f} mm^2"),
            ("Aps_top (auto)",f"{_g(ss,'Aps_top'):.1f} mm^2"),
            ("Pi (auto)",   f"{_g(ss,'Pi'):.2f} kN"),
        ]
        self._kv_table(rows)

        self._h2("1.4  Span, Bearings and Loads")
        self._note("Load combo: wu = 1.2(SW+SDL) + 1.6LL  [ASCE 7 / ACI 318-19 Table 5.3.1]")
        rows = [
            ("L_cc",          f"{_g(ss,'L_cc'):.0f} mm"),
            ("L_clear (auto)",f"{_g(ss,'L_clear'):.0f} mm"),
            ("L_an (auto)",   f"{_g(ss,'L_an'):.0f} mm"),
            ("Span type",     _g(ss,"span_type","Clear span")),
            ("bear_min (auto)",f"{_g(ss,'bear_min'):.1f} mm"),
            ("SW_HCS",        f"{_g(ss,'SW_HCS'):.3f} kN/m^2"),
            ("SW_topping",    f"{_g(ss,'SW_topping'):.3f} kN/m^2"),
            ("SDL",           f"{_g(ss,'SDL'):.2f} kN/m^2"),
            ("LL",            f"{_g(ss,'LL'):.2f} kN/m^2"),
            ("wu (auto)",     f"{_g(ss,'lb_wu_area'):.3f} kN/m^2"),
            ("Vu_max (auto)", f"{_g(ss,'lb_Vu_max'):.2f} kN"),
            ("Mu_max (auto)", f"{_g(ss,'lb_Mu_max',0)/1e6:.2f} kN.m"),
            ("Ra (auto)",     f"{_g(ss,'lb_Ra_u'):.2f} kN"),
            ("SDC",           _g(ss,"sdc","B")),
            ("RH",            f"{_g(ss,'RH'):.0f} %"),
            ("V/S ratio",     f"{_g(ss,'V_S'):.1f} mm"),
        ]
        self._kv_table(rows)
        self.add_page()

    # ── CH 2 — TRANSFER LENGTH ──────────────────────────────────────────────
    def _ch2_transfer(self):
        ss      = self.ss
        ps_type = _g(ss,"ps_type","PC Wire")
        l_t     = float(_g(ss,"lb_l_t",     250.0))
        l_d     = float(_g(ss,"lb_l_d",     380.0))
        fse     = float(_g(ss,"lb_fse_est", 970.0))
        fps     = float(_g(ss,"lb_fps_est", 1500.0))
        fpi     = float(_g(ss,"fpi",        1213.5))
        fpu     = float(_g(ss,"fpu",        1618.0))
        fpy     = float(_g(ss,"fpy",        1432.0))
        L_an    = float(_g(ss,"L_an",       5850.0))
        d_ps    = (float(_g(ss,"wire_dia",5.0)) if "Wire" in ps_type
                   else l_t / 50.0)

        self._h1("2.  Transfer Length and Development Length")
        self._note("Ref: PCI Design Handbook 8th Ed. Sec. 4.2.3  |  ACI 318-19 §25.8.6, §25.8.7")

        self._h2("2.1  Transfer Length  l_t")
        if "Wire" in ps_type:
            d_ps = float(_g(ss,"wire_dia",5.0))
            self._calc(f"  l_t  =  50 x d_ps  =  50 x {d_ps:.1f}  =  {l_t:.1f} mm",
                       "PCI 8th Ed. Sec. 4.2.3")
        else:
            l_t60  = 60.0 * d_ps
            l_taci = fse / 20.7 * d_ps
            self._calc("  l_t  =  max( 60 x d_ps,  fse/20.7 x d_ps )",
                       "ACI 318-19 §25.8.6.1")
            self._calc(f"  l_t  =  max( {l_t60:.1f},  {l_taci:.1f} )  =  {l_t:.1f} mm")

        self._h2("2.2  Development Length  l_d")
        self._note("fse = fpi x 0.80 (20% assumed loss).  fps = min(fpu, fpy+70) conservative.")
        self._calc(f"  fse  =  {fpi:.1f} x 0.80  =  {fse:.1f} MPa")
        self._calc(f"  fps  =  min( {fpu:.1f},  {fpy:.1f}+70 )  =  {fps:.1f} MPa")
        self._calc("  l_d  =  l_t  +  (fps - fse) x d_ps / 20.7",
                   "ACI 318-19 Eq. 25.8.7.1 (SI)")
        self._calc(f"  l_d  =  {l_t:.1f}  +  ({fps:.1f}-{fse:.1f}) x {d_ps:.1f} / 20.7")
        self._calc(f"  l_d  =  {l_t:.1f}  +  {(fps-fse)*d_ps/20.7:.1f}  =  {l_d:.1f} mm")

        self._h2("2.3  Prestress Development Check")
        ratio  = L_an / l_d if l_d > 0 else 0.0
        status = _g(ss,"lb_ps_status","FULL")
        msg    = _g(ss,"lb_ps_message","")
        self._calc(f"  L_an / l_d  =  {L_an:.0f} / {l_d:.1f}  =  {ratio:.3f}",
                   "ACI 318-19 §25.8.7")
        ok = status == "FULL"
        self._status(f"Status: {status}  --  {msg}", ok)
        self.add_page()

    # ── CH 3 — SECTION PROPERTIES ────────────────────────────────────────────
    def _ch3_section_props(self):
        ss     = self.ss
        b_top  = float(_g(ss,"b_top",  1187.0))
        h      = float(_g(ss,"h",       200.0))
        tf_bot = float(_g(ss,"tf_bot",   50.0))
        h_core = float(_g(ss,"h_core",  120.0))
        A_void = float(_g(ss,"A_voids_total", 63959.0))
        Aps_b  = float(_g(ss,"Aps_bot",  196.0))
        Aps_t  = float(_g(ss,"Aps_top",    0.0))
        dp_bot = float(_g(ss,"dp_bot",   165.0))
        n_ps   = float(_g(ss,"sp_n_ps",   5.41))
        Ec_hcs = float(_g(ss,"Ec_hcs", 36793.0))
        Eps    = float(_g(ss,"Eps",   199050.0))

        Ag    = float(_g(ss,"sp_Ag",     b_top*h))
        yb_g  = float(_g(ss,"sp_yb_g",  h/2))
        Ig    = float(_g(ss,"sp_Ig",     b_top*h**3/12))
        Sb_g  = float(_g(ss,"sp_Sb_g",  Ig/yb_g if yb_g>0 else 0))
        St_g  = float(_g(ss,"sp_St_g",  Ig/(h-yb_g) if h-yb_g>0 else 0))
        An    = float(_g(ss,"sp_An",    1.0))
        yb    = float(_g(ss,"sp_yb",    1.0))
        yt    = float(_g(ss,"sp_yt",    1.0))
        In    = float(_g(ss,"sp_In",    1.0))
        Sb_n  = float(_g(ss,"sp_Sb",    1.0))
        St_n  = float(_g(ss,"sp_St",    1.0))
        r2    = float(_g(ss,"sp_r2",    1.0))
        e_bot = float(_g(ss,"sp_e_bot", 1.0))
        A_comp  = float(_g(ss,"sp_A_comp",   1.0))
        yb_comp = float(_g(ss,"sp_yb_comp",  1.0))
        yt_comp = float(_g(ss,"sp_yt_comp",  1.0))
        I_comp  = float(_g(ss,"sp_I_comp",   1.0))
        Sbc     = float(_g(ss,"sp_Sbc_comp", 1.0))
        Stc     = float(_g(ss,"sp_Stc_comp", 1.0))

        self._h1("3.  Section Properties")
        self._note(
            "y = 0 at HCS bottom face.  Rectangular b_top x h simplification.  "
            "y_void = tf_bot + h_core/2.  Transformed steel: (n_ps-1) x Aps.\n"
            "Ref: ACI/PCI 319-25 Cl. 26.12  |  PCI 8th Ed. Sec. 2.2"
        )

        self._h2("3.1  Gross Section")
        self._calc(f"  Ag   =  b_top x h  =  {b_top:.0f} x {h:.0f}  =  {Ag:,.0f} mm^2",
                   "ACI/PCI 319-25 Cl. 26.12.1")
        self._calc(f"  yb_g =  h/2  =  {h:.0f}/2  =  {yb_g:.2f} mm")
        self._calc(f"  Ig   =  {b_top:.0f} x {h:.0f}^3 / 12  =  {Ig/1e6:.4f} x10^6 mm^4")
        self._calc(f"  Sb_g =  Ig/yb  =  {Sb_g/1e3:.3f} x10^3 mm^3")
        self._calc(f"  St_g =  Ig/yt  =  {St_g/1e3:.3f} x10^3 mm^3")

        self._h2("3.2  Net HCS Section")
        y_void   = tf_bot + h_core / 2.0
        An_conc  = b_top * h - A_void
        dA_bot   = (n_ps - 1.0) * Aps_b
        self._note(f"  n_ps = Eps/Ec_hcs = {Eps:.0f}/{Ec_hcs:.0f} = {n_ps:.3f}")
        self._calc(f"  y_void_c  =  tf_bot + h_core/2  =  {tf_bot:.0f}+{h_core:.1f}/2  =  {y_void:.2f} mm",
                   "PCI 8th Ed. Sec. 2.2.1")
        self._calc(f"  A_net_c   =  b_top x h - A_voids  =  {b_top:.0f}x{h:.0f}-{A_void:.0f}  =  {An_conc:,.0f} mm^2")
        self._calc(f"  dA_bot    =  (n_ps-1) x Aps_bot  =  ({n_ps:.3f}-1) x {Aps_b:.1f}  =  {dA_bot:.1f} mm^2")
        self._calc(f"  An   =  {An:,.2f} mm^2")
        self._calc(f"  yb   =  {yb:.4f} mm   (centroid from HCS bottom)")
        self._calc(f"  yt   =  h - yb  =  {h:.0f} - {yb:.4f}  =  {yt:.4f} mm")
        self._calc(f"  In   =  {In/1e6:.4f} x10^6 mm^4   (parallel-axis)")
        self._calc(f"  Sb_n =  In/yb  =  {Sb_n/1e3:.3f} x10^3 mm^3")
        self._calc(f"  St_n =  In/yt  =  {St_n/1e3:.3f} x10^3 mm^3")
        self._calc(f"  r2   =  In/An  =  {r2:.2f} mm^2   (radius of gyration^2)")
        self._calc(f"  e_bot =  dp_bot - yb  =  {dp_bot:.0f} - {yb:.4f}  =  {e_bot:.4f} mm")
        kt = In/(An*yb)  if An*yb>0 else 0
        kb = In/(An*yt)  if An*yt>0 else 0
        self._calc(f"  k_t  =  In/(An x yb)  =  {kt:.2f} mm  (upper kern from top)")
        self._calc(f"  k_b  =  In/(An x yt)  =  {kb:.2f} mm  (lower kern from bottom)")

        has_top = bool(_g(ss,"has_topping"))
        t_top   = float(_g(ss,"t_topping", 0.0))
        if has_top and t_top > 0:
            self._h2("3.3  Composite Section")
            n_mod    = float(_g(ss,"n_mod",   0.818))
            b_nom    = float(_g(ss,"b_nominal",1200.0))
            b_top_tr = b_nom / n_mod
            A_top_tr = b_top_tr * t_top
            y_top_c  = h + t_top / 2.0
            self._calc(f"  b_top_tr =  b_nom/n_mod  =  {b_nom:.0f}/{n_mod:.4f}  =  {b_top_tr:.2f} mm",
                       "PCI 8th Ed. Sec. 4.2.3")
            self._calc(f"  A_top_tr =  {b_top_tr:.2f} x {t_top:.0f}  =  {A_top_tr:,.2f} mm^2")
            self._calc(f"  A_comp   =  {A_comp:,.2f} mm^2")
            self._calc(f"  yb_comp  =  {yb_comp:.4f} mm  (from HCS bottom)")
            self._calc(f"  yt_comp  =  {yt_comp:.4f} mm  (from topping top)")
            self._calc(f"  I_comp   =  {I_comp/1e6:.4f} x10^6 mm^4")
            self._calc(f"  Sbc_comp =  {Sbc/1e3:.3f} x10^3 mm^3  (HCS bottom)")
            self._calc(f"  Stc_comp =  {Stc/1e3:.3f} x10^3 mm^3  (topping top)")
        else:
            self._h2("3.3  Composite Section")
            self._note("  No topping -- composite = net HCS.")

        self._h2("3.4  Summary Table")
        self._wide_table(
            ["Property", "Gross", "Net HCS", "Composite"],
            [
                ["A (mm^2)",        f"{Ag:,.0f}",       f"{An:,.2f}",        f"{A_comp:,.2f}"],
                ["yb (mm)",         f"{yb_g:.2f}",      f"{yb:.4f}",         f"{yb_comp:.4f}"],
                ["yt (mm)",         f"{h-yb_g:.2f}",    f"{yt:.4f}",         f"{yt_comp:.4f}"],
                ["I (x10^6 mm^4)",  f"{Ig/1e6:.4f}",    f"{In/1e6:.4f}",     f"{I_comp/1e6:.4f}"],
                ["Sb (x10^3 mm^3)", f"{Sb_g/1e3:.3f}",  f"{Sb_n/1e3:.3f}",   f"{Sbc/1e3:.3f}"],
                ["St (x10^3 mm^3)", f"{St_g/1e3:.3f}",  f"{St_n/1e3:.3f}",   f"{Stc/1e3:.3f}"],
                ["r2 (mm^2)",       "--",               f"{r2:.2f}",          "--"],
                ["e_bot (mm)",      "--",               f"{e_bot:.4f}",       "--"],
                ["k_t (mm)",        "--",               f"{kt:.2f}",          "--"],
                ["k_b (mm)",        "--",               f"{kb:.2f}",          "--"],
            ]
        )
        self.add_page()

    # ── CH 4 — PRESTRESS LOSSES ──────────────────────────────────────────────
    def _ch4_losses(self):
        ss     = self.ss
        fpi    = float(_g(ss,"fpi",   1213.5))
        Pi     = float(_g(ss,"Pi",     237.8))
        Aps_b  = float(_g(ss,"Aps_bot",196.0))
        Aps_t  = float(_g(ss,"Aps_top",  0.0))
        An     = float(_g(ss,"sp_An",174000.0))
        In     = float(_g(ss,"sp_In",  776e6))
        e_bot  = float(_g(ss,"sp_e_bot",68.35))
        Ec_hcs = float(_g(ss,"Ec_hcs",36793.0))
        Eps    = float(_g(ss,"Eps",  199050.0))
        RH     = float(_g(ss,"RH",     75.0))
        V_S    = float(_g(ss,"V_S",    38.0))
        ES     = float(_g(ss,"pl_ES",   0.0))
        CR     = float(_g(ss,"pl_CR",   0.0))
        SH     = float(_g(ss,"pl_SH",   0.0))
        RE     = float(_g(ss,"pl_RE",   0.0))
        total  = float(_g(ss,"pl_total_MPa", ES+CR+SH+RE))
        pct    = float(_g(ss,"pl_total_pct", total/fpi*100 if fpi>0 else 0))
        fse    = float(_g(ss,"pl_fse",  fpi-total))
        Pe     = float(_g(ss,"pl_Pe",   0.0))
        n_ps   = Eps / Ec_hcs

        self._h1("4.  Prestress Losses")
        self._note("Method: PCI Lump-Sum (ES + CR + SH + RE)  [PCI 8th Ed. Sec. 4.7]")

        self._h2("4.1  Elastic Shortening  (ES)")
        self._note("ES = n_ps x 0.5 x f_cir    [K_es = 0.5 for pretensioned average]")
        self._calc(f"  n_ps  =  Eps/Ec_hcs  =  {Eps:.0f}/{Ec_hcs:.0f}  =  {n_ps:.4f}",
                   "ACI 318-19 Eq. 19.2.2.1")
        Pi_N  = Pi * 1000.0
        fcir  = Pi_N/An + Pi_N*e_bot**2/In
        self._calc(f"  f_cir =  Pi/An + Pi x e_bot^2/In")
        self._calc(f"        =  {Pi_N:.0f}/{An:.0f} + {Pi_N:.0f}x{e_bot:.2f}^2/{In:.3e}")
        self._calc(f"        =  {Pi_N/An:.4f} + {Pi_N*e_bot**2/In:.4f}  =  {fcir:.4f} MPa")
        self._calc(f"  ES    =  n_ps x 0.5 x f_cir  =  {n_ps:.4f} x 0.5 x {fcir:.4f}  =  {ES:.3f} MPa",
                   "PCI 8th Ed. Sec. 4.7.2")

        self._h2("4.2  Creep Loss  (CR)")
        self._calc(f"  CR  =  12 x (f_cir - f_cds)  =  {CR:.3f} MPa",
                   "PCI 8th Ed. Eq. 4.7.3")

        self._h2("4.3  Shrinkage Loss  (SH)")
        self._calc("  SH  =  117 x (1 - 0.0123 x V/S) x (1 - 0.00327 x (RH-40))",
                   "PCI 8th Ed. Eq. 4.7.4")
        self._calc(f"  SH  =  117 x (1-0.0123x{V_S:.1f}) x (1-0.00327x({RH:.0f}-40))  =  {SH:.3f} MPa")

        self._h2("4.4  Relaxation Loss  (RE)")
        self._calc(f"  RE  =  [Kre - J x (SH+CR+ES)] x C  =  {RE:.3f} MPa",
                   "PCI 8th Ed. Eq. 4.7.5")

        self._h2("4.5  Total Loss and Effective Prestress")
        self._calc(f"  Total  =  {ES:.3f} + {CR:.3f} + {SH:.3f} + {RE:.3f}  =  {total:.3f} MPa  ({pct:.2f}%)")
        self._calc(f"  fse    =  fpi - Total  =  {fpi:.2f} - {total:.3f}  =  {fse:.3f} MPa")
        self._calc(f"  Pe     =  ({Aps_b:.1f}+{Aps_t:.1f}) x {fse:.3f} / 1000  =  {Pe:.3f} kN")

        self._h2("4.6  Loss Summary")
        self._wide_table(
            ["Component", "MPa", "% of fpi"],
            [
                ["ES  Elastic shortening",  f"{ES:.3f}", f"{ES/fpi*100:.2f}" if fpi>0 else "--"],
                ["CR  Creep",               f"{CR:.3f}", f"{CR/fpi*100:.2f}" if fpi>0 else "--"],
                ["SH  Shrinkage",           f"{SH:.3f}", f"{SH/fpi*100:.2f}" if fpi>0 else "--"],
                ["RE  Relaxation",          f"{RE:.3f}", f"{RE/fpi*100:.2f}" if fpi>0 else "--"],
                ["TOTAL",                   f"{total:.3f}", f"{pct:.2f}"],
                ["fse (effective, MPa)",    f"{fse:.3f}", "--"],
                ["Pe  (effective, kN)",     f"{Pe:.3f}",  "--"],
            ]
        )
        self.add_page()

    # ── CH 5 — STRESS CHECKS ────────────────────────────────────────────────
    def _ch5_stress(self):
        ss = self.ss
        self._h1("5.  Stress Checks at All Stages")
        self._note(
            "Sign: compression (-), tension (+).  "
            "Limits per ACI/PCI 319-25 Table 24.5.3.1.\n"
            "Comp limit: -0.60f'ci (release) / -0.45f'c (service).\n"
            "Tens limit: +0.25*sqrt(f'ci) (release) / Class T or U (service)."
        )
        stages = [
            ("5.1  Transfer / Release",                   "sc_transfer",
             "f = -Pe/An +/- Pe*e/Sb -/+ M_sw/Sb",       "ACI/PCI 319-25 Table 24.5.3.1"),
            ("5.2  Lifting",                              "sc_lifting",
             "Transfer + handling moment",                "PCI 8th Ed. Sec. 5.3"),
            ("5.3  Construction (wet topping, non-comp)","sc_construction",
             "f = -Pe/An +/- Pe*e/Sb -/+ M_DL/Sb",       "ACI/PCI 319-25 Table 24.5.3.1"),
            ("5.4  Service (composite, SDL+LL)",          "sc_service",
             "Net Sb/St for DL;  Sbc/Stc for SDL+LL",    "ACI/PCI 319-25 Table 24.5.3.1"),
        ]
        summary = []
        for title, key, formula, ref in stages:
            self._h2(title)
            self._note(f"  Formula: {formula}")
            d = ss.get(key, {})
            if not d:
                self._note("  (data not available)")
                summary.append([title[:22], "--", "--", "--", "--", "N/A"])
                continue
            f_top = float(d.get("f_top", 0.0));  f_bot = float(d.get("f_bot", 0.0))
            lc    = float(d.get("limit_comp",0.0)); lt = float(d.get("limit_tens",0.0))
            stat  = str(d.get("status","N/A"))
            self._calc(f"  f_top = {f_top:.4f} MPa    limit_comp = {lc:.3f} MPa", ref)
            self._calc(f"  f_bot = {f_bot:.4f} MPa    limit_tens = {lt:.4f} MPa")
            ok = stat.upper() in ("OK","PASS","OK ")
            self._status(f"Status: {stat}", ok)
            summary.append([title[:22], f"{f_top:.3f}", f"{f_bot:.3f}",
                            f"{lc:.2f}", f"{lt:.4f}", stat])

        self._h2("5.5  Summary Table")
        self._wide_table(
            ["Stage", "f_top MPa", "f_bot MPa", "Lim comp", "Lim tens", "Status"],
            summary
        )
        self.add_page()

    # ── CH 6 — CAPACITY ──────────────────────────────────────────────────────
    def _ch6_capacity(self):
        ss     = self.ss
        fps    = float(_g(ss,"cap_fps",        1400.0))
        a      = float(_g(ss,"cap_a",            30.0))
        Mn     = float(_g(ss,"cap_Mn",          200.0))
        phi_Mn = float(_g(ss,"cap_phi_Mn",      180.0))
        Mu_max = float(_g(ss,"lb_Mu_max",          0.0)) / 1e6
        DCR_M  = float(_g(ss,"cap_DCR_M",          1.0))
        phi_Vn = float(_g(ss,"cap_phi_Vn_min",    50.0))
        Vu_max = float(_g(ss,"lb_Vu_max",          0.0))
        DCR_V  = float(_g(ss,"cap_DCR_V",          1.0))
        Aps_b  = float(_g(ss,"Aps_bot",           196.0))
        dp_bot = float(_g(ss,"dp_bot",            165.0))
        f_c    = float(_g(ss,"f_c",               50.0))
        b_top  = float(_g(ss,"b_top",           1187.0))
        needs_Av = bool(_g(ss,"cap_needs_Av_min", False))

        self._h1("6.  Flexural and Shear Capacity")

        self._h2("6.1  Flexural Capacity  Mn  (Whitney stress block)")
        self._calc(f"  fps  =  {fps:.2f} MPa  (ACI Eq. 20.3.2.4 iterated)",
                   "ACI 318-19 Cl. 20.3.2")
        self._calc(
            f"  a    =  Aps x fps / (0.85 x f'c x b)  =  {Aps_b:.1f}x{fps:.2f}/(0.85x{f_c:.0f}x{b_top:.0f})",
            "ACI 318-19 Eq. 22.2.2.4.1"
        )
        self._calc(f"       =  {Aps_b*fps:.1f} / {0.85*f_c*b_top:.1f}  =  {a:.4f} mm")
        self._calc(
            f"  Mn   =  Aps x fps x (dp - a/2) / 1e6  =  {Aps_b:.1f}x{fps:.2f}x({dp_bot:.0f}-{a:.4f}/2)/1e6",
            "ACI 318-19 Eq. 22.2.1.1"
        )
        self._calc(f"       =  {Mn:.4f} kN.m")
        self._calc(f"  phi*Mn  =  0.90 x {Mn:.4f}  =  {phi_Mn:.4f} kN.m",
                   "phi=0.90 tension-controlled  [ACI 318-19 Table 21.2.2]")
        self._calc(f"  DCR_M  =  Mu/phi*Mn  =  {Mu_max:.4f}/{phi_Mn:.4f}  =  {DCR_M:.4f}")
        self._status(f"Flexure: DCR = {DCR_M:.4f} -- {'OK' if DCR_M<=1.0 else 'OVERSTRESS'}", DCR_M<=1.0)

        self._h2("6.2  Shear Capacity  Vn")
        self._note("Vcw and Vci enveloped along span.  phi = 0.75  [ACI/PCI 319-25 Cl. 22.5]")
        self._calc(f"  min phi*Vn  =  {phi_Vn:.4f} kN")
        self._calc(f"  Vu_max      =  {Vu_max:.4f} kN")
        self._calc(f"  DCR_V       =  Vu/phi*Vn  =  {Vu_max:.4f}/{phi_Vn:.4f}  =  {DCR_V:.4f}")
        self._status(f"Shear: DCR = {DCR_V:.4f} -- {'OK' if DCR_V<=1.0 else 'OVERSTRESS'}", DCR_V<=1.0)
        if needs_Av:
            self.set_font("Helvetica","B",9); self.set_text_color(*self._RED)
            self.multi_cell(0,5,_ascii(
                "  WARNING: h>317mm, no topping, Vu>0.5*phi*Vcw "
                "-> Av,min required [ACI/PCI 319-25 Cl. 9.6.3]"), ln=True)
            self.set_text_color(*self._BLACK)

        self._h2("6.3  Summary")
        self._wide_table(
            ["Check", "Demand", "phi*R", "DCR", "Status"],
            [
                ["Flexure Mn", f"{Mu_max:.3f} kN.m", f"{phi_Mn:.3f} kN.m",
                 f"{DCR_M:.4f}", "OK" if DCR_M<=1.0 else "NG"],
                ["Shear  Vn", f"{Vu_max:.3f} kN",   f"{phi_Vn:.3f} kN",
                 f"{DCR_V:.4f}", "OK" if DCR_V<=1.0 else "NG"],
            ]
        )
        self.add_page()

    # ── CH 7 — DEFLECTION ────────────────────────────────────────────────────
    def _ch7_deflection(self):
        ss        = self.ss
        Pe        = float(_g(ss,"pl_Pe",              200.0))
        e_bot     = float(_g(ss,"sp_e_bot",            68.35))
        In        = float(_g(ss,"sp_In",              776e6))
        Ec_hcs    = float(_g(ss,"Ec_hcs",           36793.0))
        L_an      = float(_g(ss,"L_an",              5850.0))
        delta_ps  = float(_g(ss,"def_delta_ps_initial", 0.0))
        delta_sw  = float(_g(ss,"def_delta_sw",          0.0))
        net_rel   = float(_g(ss,"def_net_release",       0.0))
        total_lt  = float(_g(ss,"def_total_longterm",    0.0))
        lim_ll    = float(_g(ss,"def_limit_ll_mm",       0.0))
        lim_tot   = float(_g(ss,"def_limit_total_mm",    0.0))
        st_ll     = str  (_g(ss,"def_status_ll",       "N/A"))
        st_tot    = str  (_g(ss,"def_status_total",    "N/A"))

        self._h1("7.  Deflection and Camber")
        self._note("Ref: PCI 8th Ed. Sec. 4.8 & Table 4.8.3  |  ACI 318-19 Table 24.2.2")

        self._h2("7.1  Initial Prestress Camber  (upward, parabolic tendon)")
        self._calc("  delta_ps  =  5 x Pe x e_bot x L^2  /  (48 x Ec_ci x In)",
                   "PCI 8th Ed. Eq. 4.8.1")
        self._calc(
            f"  delta_ps  =  5x{Pe*1000:.0f}x{e_bot:.2f}x{L_an:.0f}^2 / (48x{Ec_hcs:.0f}x{In:.3e})"
        )
        self._calc(f"           =  {delta_ps:.4f} mm  (upward)")

        self._h2("7.2  Self-Weight Deflection  (downward)")
        self._calc("  delta_sw  =  5 x w_sw x L^4  /  (384 x Ec_ci x In)",
                   "PCI 8th Ed. Eq. 4.8.2")
        self._calc(f"           =  {delta_sw:.4f} mm  (downward)")

        self._h2("7.3  Net at Release")
        self._calc(
            f"  delta_net  =  delta_sw - delta_ps  =  {delta_sw:.4f} - {delta_ps:.4f}  =  {net_rel:.4f} mm"
        )

        self._h2("7.4  Long-term  (PCI multipliers)")
        self._calc(f"  Total long-term  =  {total_lt:.4f} mm")

        self._h2("7.5  Code Limit Checks")
        self._calc(f"  L/360  =  {L_an:.0f}/360  =  {lim_ll:.2f} mm  (LL limit)",
                   "ACI 318-19 Table 24.2.2")
        self._calc(f"  L/240  =  {L_an:.0f}/240  =  {lim_tot:.2f} mm  (total limit)",
                   "ACI 318-19 Table 24.2.2")
        self._status(f"LL deflection: {st_ll}",    st_ll.upper() in ("OK","PASS"))
        self._status(f"Total deflection: {st_tot}", st_tot.upper() in ("OK","PASS"))

        self._h2("7.6  Deflection Summary")
        self._wide_table(
            ["Item", "Value (mm)", "Limit (mm)", "Status"],
            [
                ["Prestress camber (initial)", f"{delta_ps:.4f}", "--",            "--"],
                ["Self-weight (initial)",      f"{delta_sw:.4f}", "--",            "--"],
                ["Net at release",             f"{net_rel:.4f}",  "--",            "--"],
                ["Total long-term",            f"{total_lt:.4f}", f"{lim_tot:.2f}", st_tot],
                ["LL deflection (est.)",       "--",              f"{lim_ll:.2f}",  st_ll],
            ]
        )
        self.add_page()

    # ── CH 8 — SPAN DISTRIBUTION TABLE ──────────────────────────────────────
    def _ch8_span_table(self):
        ss = self.ss
        self._h1("8.  Span Distribution Table  (0.1 L intervals)")
        self._note(
            "Interpolated from factored load arrays lb_x_arr / lb_Vu_arr / lb_Mu_arr.\n"
            "Vu and Mu are FACTORED  (1.2D + 1.6L).  x = 0 at left support."
        )
        rows = _span_table(ss, n_seg=10)
        self._wide_table(
            ["x/L", "x (m)", "x (mm)", "Vu (kN)", "Mu (kN.m)"],
            [
                [
                    f"{r['frac']:.1f}",
                    f"{r['x_m']:.3f}",
                    f"{r['x_mm']:.0f}",
                    f"{r['Vu_kN']:.3f}",
                    f"{r['Mu_kNm']:.3f}",
                ]
                for r in rows
            ]
        )

    # ── CH 9 — DIAGRAMS ──────────────────────────────────────────────────────
    def _ch9_diagrams(self, img_bytes: bytes | None):
        self._h1("9.  Shear Force and Bending Moment Diagrams")
        self._note(
            "Factored loads (1.2D + 1.6L).  Simply-supported span.\n"
            "Red shaded zones = transfer-length zone (l_t) near supports.\n"
            "Dashed lines = service load diagrams."
        )
        self._insert_image(img_bytes, w_mm=170)

    # ── APPENDIX ─────────────────────────────────────────────────────────────
    def _appendix(self):
        self.add_page()
        self._h1("Appendix -- Remarks and Code Compliance Notes")
        items = [
            "Report generated automatically by HCS Design App v1.0.",
            "Primary references: ACI/PCI CODE-319-25 and PCI Design Handbook, 8th Edition.",
            "Units: mm, kN, MPa throughout.  No unit conversions performed.",
            "Section props: rectangular simplification (b_top x h); y_void = tf_bot + h_core/2.  >97% accuracy.",
            "Prestress losses: PCI lump-sum (ES+CR+SH+RE).  Use detailed method for critical projects.",
            "Development length: fps = min(fpu, fpy+70) preliminary; Phase 5 uses ACI Eq. 20.3.2.4.",
            "Deflection: PCI Table 4.8.3 multipliers; parabolic tendon profile assumed.",
            "SDC D/E/F: in-plane diaphragm flexibility must be modelled; "
            "untopped HCS not rigid [ACI/PCI 319-25 Sec. 12; ACI CODE-550.5].",
            "ACI/PCI CODE-319-25 Chapter 26 documentation requirements: see project drawings.",
            "DISCLAIMER: Engineer of record must verify all inputs and results before construction.",
        ]
        for item in items:
            self._note(f"  *  {item}")

    # ── BUILD ────────────────────────────────────────────────────────────────
    def build_pdf(self, img_bytes: bytes | None = None) -> io.BytesIO:
        self._cover()
        self._ch1_inputs()
        self._ch2_transfer()
        self._ch3_section_props()
        self._ch4_losses()
        self._ch5_stress()
        self._ch6_capacity()
        self._ch7_deflection()
        self._ch8_span_table()
        self._ch9_diagrams(img_bytes)
        self._appendix()
        raw = self.output()          # fpdf2 returns bytes
        buf = io.BytesIO(raw)
        buf.seek(0)
        return buf


# =============================================================================
# PUBLIC API  (called by 3_HCS_Design.py → hcs/report.py)
# =============================================================================

def generate_word_report(ss: dict, output_stream=None) -> io.BytesIO | None:
    """
    Generate detailed Word (.docx) report.
    Embeds the SFD/BMD chart as a PNG image (in-memory, no disk I/O).
    Returns BytesIO or None if python-docx is not installed.
    """
    if not HAS_DOCX:
        return None
    try:
        fig       = _build_sfd_bmd_fig(ss)
        img_bytes = _fig_to_png(fig)
        builder   = _DocxReport(ss)
        buf       = builder.build(img_bytes=img_bytes)
        if output_stream is not None:
            output_stream.write(buf.getvalue())
            output_stream.seek(0)
            return output_stream
        return buf
    except Exception:
        traceback.print_exc()
        return None


def generate_pdf_report(ss: dict, output_stream=None) -> io.BytesIO | None:
    """
    Generate detailed PDF report via fpdf2.
    All Unicode is sanitised through _ascii() before output.
    Returns BytesIO or None if fpdf2 is not installed.
    """
    if not HAS_FPDF:
        return None
    try:
        fig       = _build_sfd_bmd_fig(ss)
        img_bytes = _fig_to_png(fig)
        builder   = _PdfReport(ss)
        buf       = builder.build_pdf(img_bytes=img_bytes)
        if output_stream is not None:
            output_stream.write(buf.getvalue())
            output_stream.seek(0)
            return output_stream
        return buf
    except Exception:
        traceback.print_exc()
        return None


def get_report_bytes(ss: dict) -> tuple[bytes | None, bytes | None]:
    """
    Returns (word_bytes, pdf_bytes) for Streamlit st.download_button.
    Either element may be None if the corresponding library is not installed
    or if an error occurs during generation.
    """
    word_bytes: bytes | None = None
    pdf_bytes:  bytes | None = None

    if HAS_DOCX:
        word_io = generate_word_report(ss)
        if word_io is not None:
            word_bytes = word_io.getvalue()

    if HAS_FPDF:
        pdf_io = generate_pdf_report(ss)
        if pdf_io is not None:
            pdf_bytes = pdf_io.getvalue()

    return word_bytes, pdf_bytes
