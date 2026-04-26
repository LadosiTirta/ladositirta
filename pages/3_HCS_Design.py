# =============================================================================
# HCS DESIGN APP — Phase 2: Section Properties
# =============================================================================
# Reference: ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
# Units: SI only (mm, kN, MPa)
# Greek symbols: plain text (phi, alfa, beta, etc.) for export compatibility
# =============================================================================

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── hcs/ module imports ────────────────────────────────────────────────────────
from hcs.constants   import WIRE_PROPS, STRAND_PROPS, PRESET_TABLE
from hcs.geometry    import (calc_core_area, calc_h_core,
                              calc_modular_ratio, get_ps_props)
from hcs.span_loads  import (calc_transfer_development_length,
                              check_prestress_development,
                              calc_factored_loads_and_diagrams)
from hcs.section_props import get_all_section_props

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HCS Design — ACI/PCI 319-25",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}
code, .mono { font-family: 'IBM Plex Mono', monospace; }

/* ── Color palette ── */
:root {
    --bg-dark:     #0d1117;
    --bg-panel:    #161b22;
    --bg-card:     #1c2128;
    --accent-blue: #388bfd;
    --accent-teal: #39d353;
    --accent-warn: #f0883e;
    --accent-err:  #f85149;
    --text-main:   #e6edf3;
    --text-muted:  #8b949e;
    --border:      #30363d;
}

/* Force dark background */
.stApp { background-color: var(--bg-dark); color: var(--text-main); }
section[data-testid="stSidebar"] { background-color: var(--bg-panel); border-right: 1px solid var(--border); }

/* ── App header ── */
.app-header {
    background: linear-gradient(135deg, #0d1117 0%, #1a2332 50%, #0d1117 100%);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent-blue);
    border-radius: 8px;
    padding: 20px 28px;
    margin-bottom: 24px;
}
.app-header h1 {
    font-size: 1.7rem;
    font-weight: 700;
    color: var(--text-main);
    margin: 0 0 4px 0;
    letter-spacing: -0.02em;
}
.app-header .subtitle {
    color: var(--text-muted);
    font-size: 0.85rem;
    font-family: 'IBM Plex Mono', monospace;
}
.phase-badge {
    display: inline-block;
    background: #1f2d3d;
    border: 1px solid var(--accent-blue);
    color: var(--accent-blue);
    font-size: 0.72rem;
    font-family: 'IBM Plex Mono', monospace;
    padding: 2px 10px;
    border-radius: 12px;
    margin-right: 8px;
    letter-spacing: 0.05em;
}

/* ── Section headers ── */
.section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0 6px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
}
.section-header .section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: var(--accent-blue);
    background: rgba(56,139,253,0.1);
    padding: 2px 8px;
    border-radius: 4px;
    letter-spacing: 0.08em;
}
.section-header h3 {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-main);
    margin: 0;
}

/* ── Validation badges ── */
.badge-ok {
    display: inline-flex; align-items: center; gap: 5px;
    background: rgba(57,211,83,0.1);
    border: 1px solid rgba(57,211,83,0.4);
    color: var(--accent-teal);
    padding: 3px 10px; border-radius: 12px;
    font-size: 0.8rem; font-family: 'IBM Plex Mono', monospace;
}
.badge-warn {
    display: inline-flex; align-items: center; gap: 5px;
    background: rgba(240,136,62,0.1);
    border: 1px solid rgba(240,136,62,0.4);
    color: var(--accent-warn);
    padding: 3px 10px; border-radius: 12px;
    font-size: 0.8rem; font-family: 'IBM Plex Mono', monospace;
}
.badge-err {
    display: inline-flex; align-items: center; gap: 5px;
    background: rgba(248,81,73,0.1);
    border: 1px solid rgba(248,81,73,0.4);
    color: var(--accent-err);
    padding: 3px 10px; border-radius: 12px;
    font-size: 0.8rem; font-family: 'IBM Plex Mono', monospace;
}

/* ── Metric cards ── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 10px;
    margin: 12px 0;
}
.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
}
.metric-card .metric-label {
    font-size: 0.72rem;
    font-family: 'IBM Plex Mono', monospace;
    color: var(--text-muted);
    margin-bottom: 4px;
}
.metric-card .metric-value {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--accent-blue);
    font-family: 'IBM Plex Mono', monospace;
}
.metric-card .metric-unit {
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-left: 3px;
}

/* ── Info box ── */
.info-box {
    background: rgba(56,139,253,0.06);
    border: 1px solid rgba(56,139,253,0.25);
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 0.82rem;
    color: #7db8f7;
    margin: 8px 0;
}

/* ── Summary table ── */
.summary-section {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    margin-top: 24px;
}

/* ── Run button (disabled) ── */
.run-btn-wrapper {
    text-align: center;
    margin-top: 20px;
}

/* Streamlit overrides */
div[data-testid="stExpander"] {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg-panel);
}
.stSelectbox label, .stRadio label, .stNumberInput label,
.stSlider label, .stCheckbox label {
    font-size: 0.85rem !important;
    color: var(--text-main) !important;
}
.stMetric { background: var(--bg-card); border-radius: 8px; padding: 8px; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================
def init_session_state():
    """Initialise all session state variables with HCS 200mm defaults."""
    _default_A_core_1      = 7106.5
    _default_A_voids_total = 9 * _default_A_core_1   # ≈ 63959
    _default_h_core        = 120.0
    _default_bw_shear      = 1199 - 9 * 80           # 479
    _default_Ec_hcs        = 33_000.0
    _default_Ec_top        = 27_000.0
    _default_n_mod         = _default_Ec_top / _default_Ec_hcs if _default_Ec_hcs > 0 else 1.0

    defaults = {
        # ── A. Concrete ──
        "f_ci":        35.0,
        "f_c_cut":     40.0,
        "f_c_del":     45.0,
        "f_c_ere":     50.0,
        "f_c":         50.0,
        "wc":          24.0,
        "has_topping": True,
        "f_c_top":     30.0,
        "wc_top":      24.0,

        # ── B. Cross-section ──
        "b_nominal":   1200,
        "b_bottom":    1199,
        "b_top":       1187,
        "h":           200,
        "tf_top":      52,
        "tf_bot":      50,
        "t_topping":   60,
        "hcs_type":    "Full HCS (Hollow Core)",
        "core_shape":  "Teardrop",
        "d_core":      80,
        "n_core":      9,
        "h_straight":  40,
        "h_taper":     40,
        "gap_side":    67,
        "gap_between": 52,
        "preset":      "HCS 200mm — Teardrop core",

        # ── C. Prestress ──
        "ps_type":     "PC Wire (plain/indented)",
        "wire_dia":    5.0,
        "strand_size": "1/2 in  (d=11.2mm)",
        "n_bot":       10,
        "n_top":       0,
        "cover_bot":   35,
        "cover_top":   30,
        "fpi_pct":     75.0,
        "fpu":         1618.0,
        "fpy":         1432.0,
        "Eps":         199050.0,
        "ps_area":     19.6,
        "fpi":         1213.5,
        "Aps_bot":     196.0,
        "Aps_top":     0.0,
        "dp_bot":      165.0,
        "dp_top":      30.0,
        "Pi":          237.8,

        # ── Derived geometry (pre-calculated for HCS 200mm) ──
        "A_core_1":      _default_A_core_1,
        "A_voids_total": _default_A_voids_total,
        "h_core":        _default_h_core,
        "bw_shear":      _default_bw_shear,

        # ── Material-derived defaults ──
        "Ec_hcs":        _default_Ec_hcs,
        "Ec_top":        _default_Ec_top,
        "n_mod":         _default_n_mod,

        # ── Auto-calc defaults ──
        "SW_HCS":      3.5,
        "SW_topping":  1.44,
        "L_clear":     5850.0,
        "L_an":        5850.0,
        "bear_min":    50.8,

        # ── D. Span ──
        "L_cc":        6000,
        "b_bear_L":    150,
        "b_bear_R":    150,
        "span_type":   "Clear span",

        # ── E. Loads ──
        "SDL":         1.5,
        "LL":          2.0,
        "has_point_load": False,
        "P1_DL":       5.0,
        "P1_LL":       5.0,
        "x_P1":        2000,
        "P2_DL":       0.0,
        "P2_LL":       0.0,
        "x_P2":        4000,
        "slab_position": "Interior slab",

        # ── F. Seismic ──
        "sdc":         "B",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# =============================================================================
# UI HELPER FUNCTIONS  (pure UI — no calculations)
# =============================================================================

def apply_preset(preset_name: str):
    """Apply preset geometry values to session state."""
    p = PRESET_TABLE.get(preset_name)
    if p is None:
        return
    for k, v in p.items():
        st.session_state[k] = v


def get_ps_diameter_mm() -> float:
    """Return nominal diameter of the prestressing steel in mm (reads session_state)."""
    if st.session_state["ps_type"] == "PC Wire (plain/indented)":
        return float(st.session_state["wire_dia"])
    else:
        return STRAND_PROPS[st.session_state["strand_size"]]["d_mm"]


def badge_html(label: str, status: str, detail: str = "") -> str:
    """Return HTML for a status badge."""
    css   = {"OK": "badge-ok", "WARN": "badge-warn", "ERR": "badge-err"}[status]
    icons = {"OK": "✓", "WARN": "⚠", "ERR": "✗"}[status]
    return f'<span class="{css}">{icons} {label}{" — " + detail if detail else ""}</span>'


def metric_card(label: str, value: str, unit: str = "") -> str:
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}<span class="metric-unit">{unit}</span></div>
    </div>"""


def section_hdr(code: str, title: str):
    st.markdown(f"""
    <div class="section-header">
        <span class="section-label">{code}</span>
        <h3>{title}</h3>
    </div>""", unsafe_allow_html=True)


# =============================================================================
# APP STARTUP
# =============================================================================
init_session_state()

# ── Phase 1B: auto-calculations (run every render) ─────────────────────────
_ss = st.session_state

_fpu_def     = _ss.get("fpu", 1618.0)
_fpi_pct_def = _ss.get("fpi_pct", 75.0)
_fpi         = _ss.get("fpi", _fpu_def * _fpi_pct_def / 100.0)
_Aps_bot     = _ss.get("Aps_bot", _ss.get("n_bot", 10) * _ss.get("ps_area", 19.6))

_d_ps_mm = get_ps_diameter_mm()
_td = calc_transfer_development_length(
    ps_type          = _ss["ps_type"],
    d_ps             = _d_ps_mm,
    fpu              = _ss["fpu"],
    fpi              = _fpi,
    fpy              = _ss.get("fpy", _ss["fpu"] * 0.885),
    assumed_loss_pct = 20.0,
)
_ss["lb_l_t"]       = _td["l_t"]
_ss["lb_l_d"]       = _td["l_d"]
_ss["lb_fse_est"]   = _td["fse_est"]
_ss["lb_fps_est"]   = _td["fps_est"]
_ss["lb_lt_method"] = _td["method_lt"]
_ss["lb_loss_note"] = _td["loss_note"]

_L_an = _ss.get("L_an",
                _ss["L_cc"] - _ss["b_bear_L"] / 2.0 - _ss["b_bear_R"] / 2.0)
_dev  = check_prestress_development(_L_an, _td["l_d"])
_ss["lb_ps_status"]  = _dev["status"]
_ss["lb_ps_is_ps"]   = _dev["is_prestressed"]
_ss["lb_ps_message"] = _dev["message"]

_A_voids_total = _ss.get("A_voids_total", 63959.0)
_SW_HCS     = _ss.get("SW_HCS",
                       _ss["wc"] * (_ss["b_bottom"] * _ss["h"] - _A_voids_total)
                       / (_ss["b_bottom"] * 1e6))
_SW_topping = _ss.get("SW_topping",
                       _ss["wc_top"] * _ss["b_nominal"] * _ss["t_topping"]
                       / (_ss["b_nominal"] * 1e6) if _ss["has_topping"] else 0.0)

_ld = calc_factored_loads_and_diagrams(
    L_an           = _L_an,
    b_bottom       = _ss["b_bottom"],
    t_topping      = _ss["t_topping"],
    wc             = _ss["wc"],
    wc_top         = _ss["wc_top"],
    has_topping    = _ss["has_topping"],
    SW_HCS         = _SW_HCS,
    SW_topping     = _SW_topping,
    SDL            = _ss["SDL"],
    LL             = _ss["LL"],
    has_point_load = _ss["has_point_load"],
    P1_DL          = _ss["P1_DL"],    P1_LL = _ss["P1_LL"],    x_P1 = _ss["x_P1"],
    P2_DL          = _ss["P2_DL"],    P2_LL = _ss["P2_LL"],    x_P2 = _ss["x_P2"],
    slab_position  = _ss["slab_position"],
    N              = 200,
)
for _k, _v in _ld.items():
    _ss[f"lb_{_k}"] = _v

# ── Phase 2: Section Properties auto-calc (run every render) ──────────────
# Reference: ACI/PCI CODE-319-25 Cl. 26.12 | PCI Design Handbook Sec. 2.2 & 4.2.3
_sp = get_all_section_props(dict(_ss))
for _k, _v in _sp.items():
    _ss[f"sp_{_k}"] = _v

# =============================================================================
# APP HEADER
# =============================================================================
st.markdown("""
<div class="app-header">
    <div style="margin-bottom:8px">
        <span class="phase-badge">PHASE 2</span>
        <span class="phase-badge">ACI/PCI 319-25</span>
        <span class="phase-badge">PCI 8th Ed.</span>
    </div>
    <h1>🏗️ Hollow Core Slab Design</h1>
    <div class="subtitle">Structural Design Calculator · SI Units (mm · kN · MPa) · v1.0-alpha</div>
</div>
""", unsafe_allow_html=True)


# =============================================================================
# SIDEBAR — Navigation
# =============================================================================
with st.sidebar:
    st.markdown("### 📐 HCS Design App")
    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.8rem; color:#8b949e;">
    <span style="color:#39d353;">&#10003; Phase 1A</span> — Input &amp; Session State<br>
    <span style="color:#39d353;">&#10003; Phase 1B</span> — Span &amp; Transfer Length<br>
    <b style="color:#388bfd;">&#9654; Phase 2</b> &nbsp;— Section Properties<br>
    <span style="color:#30363d;">Phase 3  — Prestress Losses</span><br>
    <span style="color:#30363d;">Phase 4  — Stress Checks</span><br>
    <span style="color:#30363d;">Phase 5  — Mn & Vn Capacity</span><br>
    <span style="color:#30363d;">Phase 6  — Deflection & Camber</span><br>
    <span style="color:#30363d;">Phase 7  — Report Generator</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    st.caption("References:")
    st.caption("• ACI/PCI CODE-319-25, Ch. 7,12,16,26")
    st.caption("• PCI Design Handbook, 8th Edition")


# =============================================================================
# MAIN TABS
# =============================================================================
tab_A, tab_B, tab_C, tab_D, tab_E, tab_F, tab_G, tab_sum, tab_P2 = st.tabs([
    "A · Concrete", "B · Cross-Section", "C · Prestress",
    "D · Span", "E · Loads", "F · Seismic", "G · Section Props",
    "📋 Summary", "📐 Appendix A · Section Props"
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB A — CONCRETE MATERIAL
# ═══════════════════════════════════════════════════════════════════════════════
with tab_A:
    section_hdr("A.1", "HCS Concrete — Multi-Stage Strengths")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state["f_ci"] = st.number_input(
            "f'ci — Strength at transfer / release (MPa)",
            min_value=20.0, max_value=80.0, step=1.0,
            value=float(st.session_state["f_ci"]), key="_f_ci")

        st.session_state["f_c_cut"] = st.number_input(
            "f'c_cut — Strength at wire cutting (MPa)",
            min_value=20.0, max_value=80.0, step=1.0,
            value=float(st.session_state["f_c_cut"]), key="_f_c_cut")

    with col2:
        st.session_state["f_c_del"] = st.number_input(
            "f'c_del — Strength at delivery (MPa)",
            min_value=20.0, max_value=80.0, step=1.0,
            value=float(st.session_state["f_c_del"]), key="_f_c_del")

        st.session_state["f_c_ere"] = st.number_input(
            "f'c_ere — Strength at erection (MPa)",
            min_value=20.0, max_value=80.0, step=1.0,
            value=float(st.session_state["f_c_ere"]), key="_f_c_ere")

    with col3:
        st.session_state["f_c"] = st.number_input(
            "f'c — 28-day design strength (MPa)",
            min_value=20.0, max_value=100.0, step=1.0,
            value=float(st.session_state["f_c"]), key="_f_c")

        st.session_state["wc"] = st.number_input(
            "wc — Unit weight (kN/m³)",
            min_value=18.0, max_value=30.0, step=0.5,
            value=float(st.session_state["wc"]), key="_wc")

    st.markdown("---")
    section_hdr("A.2", "Topping Concrete")

    st.session_state["has_topping"] = st.checkbox(
        "Structural Topping Present?",
        value=st.session_state["has_topping"], key="_has_topping")

    if st.session_state["has_topping"]:
        col1, col2 = st.columns(2)
        with col1:
            st.session_state["f_c_top"] = st.number_input(
                "f'c_top — Topping 28-day strength (MPa)",
                min_value=17.0, max_value=60.0, step=1.0,
                value=float(st.session_state["f_c_top"]), key="_f_c_top")
        with col2:
            st.session_state["wc_top"] = st.number_input(
                "wc_top — Topping unit weight (kN/m³)",
                min_value=18.0, max_value=30.0, step=0.5,
                value=float(st.session_state["wc_top"]), key="_wc_top")
    else:
        st.session_state["t_topping"] = 0
        st.info("No structural topping — topping thickness forced to 0 mm in calculations.")

    st.markdown("---")
    section_hdr("A.3", "Elastic Moduli (Auto-Calculated)")
    st.markdown("""
    <div class="info-box">
    ACI 318-19 Eq. 19.2.2.1 &nbsp;→&nbsp; <code>Ec = 0.043 × wc<sup>1.5</sup> × √f'c</code>
    &nbsp;[MPa] &nbsp;·&nbsp; wc in kg/m³
    </div>
    """, unsafe_allow_html=True)

    Ec_hcs, Ec_top, n_mod = calc_modular_ratio(
        st.session_state["wc"],    st.session_state["f_c"],
        st.session_state["wc_top"], st.session_state["f_c_top"]
    )
    st.session_state["Ec_hcs"] = Ec_hcs
    st.session_state["Ec_top"] = Ec_top
    st.session_state["n_mod"]  = n_mod

    col1, col2, col3 = st.columns(3)
    col1.metric("Ec_HCS", f"{Ec_hcs:,.0f} MPa")
    col2.metric("Ec_top", f"{Ec_top:,.0f} MPa" if st.session_state["has_topping"] else "N/A")
    col3.metric("n (modular ratio)", f"{n_mod:.3f}" if st.session_state["has_topping"] else "N/A")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB B — CROSS-SECTION GEOMETRY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_B:
    section_hdr("B.0", "Quick-Fill Preset Selector")

    preset_choice = st.selectbox(
        "HCS Standard Preset",
        options=list(PRESET_TABLE.keys()),
        index=list(PRESET_TABLE.keys()).index(st.session_state["preset"]),
        key="_preset_select"
    )
    if preset_choice != st.session_state["preset"]:
        st.session_state["preset"] = preset_choice
        apply_preset(preset_choice)
        st.rerun()

    st.markdown("---")
    section_hdr("B.1", "Panel Width & Overall Dimensions")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state["b_nominal"] = st.number_input(
            "b_nominal — Nominal panel width (mm)",
            min_value=600, max_value=2400, step=1,
            value=int(st.session_state["b_nominal"]), key="_b_nominal")

        st.session_state["b_bottom"] = st.number_input(
            "b_bottom — Actual bottom width (mm)",
            min_value=600, max_value=2400, step=1,
            value=int(st.session_state["b_bottom"]), key="_b_bottom")

        st.session_state["b_top"] = st.number_input(
            "b_top — Top flange width (mm)",
            min_value=600, max_value=2400, step=1,
            value=int(st.session_state["b_top"]), key="_b_top")

    with col2:
        st.session_state["h"] = st.number_input(
            "h — Total HCS thickness (mm)",
            min_value=80, max_value=600, step=1,
            value=int(st.session_state["h"]), key="_h")

        st.session_state["tf_top"] = st.number_input(
            "tf_top — Top flange thickness (mm)",
            min_value=0, max_value=200, step=1,
            value=int(st.session_state["tf_top"]), key="_tf_top")

        st.session_state["tf_bot"] = st.number_input(
            "tf_bot — Bottom flange thickness (mm)",
            min_value=20, max_value=200, step=1,
            value=int(st.session_state["tf_bot"]), key="_tf_bot")

    with col3:
        if st.session_state["has_topping"]:
            st.session_state["t_topping"] = st.number_input(
                "t_topping — Structural topping thickness (mm)",
                min_value=0, max_value=200, step=5,
                value=int(st.session_state["t_topping"]), key="_t_topping")
        else:
            st.info("t_topping = 0 mm\n(no topping)")

        gap_panel = st.session_state["b_nominal"] - st.session_state["b_bottom"]
        st.markdown(f"""
        <div class="info-box">
        Panel gap = {gap_panel} mm<br>
        Shear key wedge = {st.session_state['b_bottom'] - st.session_state['b_top']} mm
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    section_hdr("B.2", "HCS Section Type")

    st.session_state["hcs_type"] = st.radio(
        "HCS Type",
        options=["Full HCS (Hollow Core)", "Half Slab (Open Top)"],
        index=0 if st.session_state["hcs_type"] == "Full HCS (Hollow Core)" else 1,
        horizontal=True, key="_hcs_type"
    )
    if st.session_state["hcs_type"] == "Half Slab (Open Top)":
        st.session_state["tf_top"] = 0
        st.markdown("""
        <div class="info-box">
        ℹ️ Half Slab: top flange thickness forced = 0 mm.
        When composite topping is added, the section becomes fully solid rectangular
        — core voids are filled by topping concrete.
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    section_hdr("B.3", "Core / Void Geometry")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.session_state["core_shape"] = st.radio(
            "Core Shape",
            options=["Circular", "Capsule", "Teardrop"],
            index=["Circular", "Capsule", "Teardrop"].index(
                st.session_state["core_shape"]),
            key="_core_shape"
        )
    with col2:
        shape_desc = {
            "Circular":  "Full circle · h_core = d_core",
            "Capsule":   "Semicircle top + straight segment + semicircle bottom · h_core = d_core + h_straight",
            "Teardrop":  "Semicircle top + tapered bottom (triangle, ~0.3×d at tip) · h_core = d_core + h_taper",
        }
        st.markdown(f'<div class="info-box">🔷 {shape_desc[st.session_state["core_shape"]]}</div>',
                    unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.session_state["d_core"] = st.number_input(
            "d_core — Core diameter (mm)",
            min_value=40, max_value=300, step=1,
            value=int(st.session_state["d_core"]), key="_d_core")

    with col2:
        st.session_state["n_core"] = st.number_input(
            "n_core — Number of cores",
            min_value=1, max_value=20, step=1,
            value=int(st.session_state["n_core"]), key="_n_core")

    with col3:
        st.session_state["gap_side"] = st.number_input(
            "gap_side — Edge to first core CL (mm)",
            min_value=20, max_value=200, step=1,
            value=int(st.session_state["gap_side"]), key="_gap_side")

    with col4:
        st.session_state["gap_between"] = st.number_input(
            "gap_between — Clear gap between cores (mm)",
            min_value=10, max_value=200, step=1,
            value=int(st.session_state["gap_between"]), key="_gap_between")

    if st.session_state["core_shape"] == "Capsule":
        st.session_state["h_straight"] = st.number_input(
            "h_straight — Height of straight middle segment (mm)",
            min_value=0, max_value=400, step=5,
            value=int(st.session_state["h_straight"]), key="_h_straight")

    if st.session_state["core_shape"] == "Teardrop":
        st.session_state["h_taper"] = st.number_input(
            "h_taper — Height of tapered portion (mm)",
            min_value=0, max_value=400, step=5,
            value=int(st.session_state["h_taper"]), key="_h_taper")

    # ── Derived core geometry ──
    d_core      = st.session_state["d_core"]
    n_core      = st.session_state["n_core"]
    h_straight  = st.session_state["h_straight"]
    h_taper     = st.session_state["h_taper"]
    core_shape  = st.session_state["core_shape"]
    gap_side    = st.session_state["gap_side"]
    gap_between = st.session_state["gap_between"]
    b_bottom    = st.session_state["b_bottom"]

    A_core_1      = calc_core_area(core_shape, d_core, h_straight, h_taper)
    A_voids_total = n_core * A_core_1
    h_core_val    = calc_h_core(core_shape, d_core, h_straight, h_taper)
    bw_shear      = b_bottom - n_core * d_core

    st.session_state["A_core_1"]      = A_core_1
    st.session_state["A_voids_total"] = A_voids_total
    st.session_state["h_core"]        = h_core_val
    st.session_state["bw_shear"]      = bw_shear

    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("h_core (auto)", f"{h_core_val:.1f}", "mm")}
        {metric_card("A_core_1", f"{A_core_1:,.0f}", "mm²")}
        {metric_card("A_voids_total", f"{A_voids_total:,.0f}", "mm²")}
        {metric_card("bw_shear (web)", f"{bw_shear:.0f}", "mm")}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="info-box">
    ℹ️ Section simplification: cross-section is modelled as rectangular using b_top width.
    Void areas are subtracted based on core shape geometry.
    This approximation gives accuracy &gt; 97% for design purposes.
    </div>""", unsafe_allow_html=True)

    # ── Geometry Validation ──
    st.markdown("---")
    section_hdr("B.4", "Geometry Validation")

    tf_top   = st.session_state["tf_top"]
    tf_bot   = st.session_state["tf_bot"]
    h_slab   = st.session_state["h"]

    h_check = tf_top + h_core_val + tf_bot
    delta_h = abs(h_check - h_slab)
    chk1_ok = delta_h < 1.0

    w_used  = 2 * gap_side + n_core * d_core + (n_core - 1) * gap_between
    chk2_ok = w_used <= b_bottom
    chk3_ok = gap_between >= 25

    badges = ""
    badges += badge_html(
        f"Check 1: tf_top + h_core + tf_bot = {h_check:.1f} mm (h = {h_slab} mm)",
        "OK" if chk1_ok else "ERR",
        "" if chk1_ok else f"delta = {delta_h:.1f} mm"
    ) + "&nbsp; "

    badges += badge_html(
        f"Check 2: Width used = {w_used:.0f} mm ≤ b_bottom = {b_bottom} mm",
        "OK" if chk2_ok else "WARN",
        "" if chk2_ok else f"overflow {w_used - b_bottom:.0f} mm"
    ) + "&nbsp; "

    badges += badge_html(
        f"Check 3: gap_between = {gap_between} mm ≥ 25 mm",
        "OK" if chk3_ok else "WARN",
        "" if chk3_ok else "increase gap_between"
    )

    st.markdown(badges, unsafe_allow_html=True)
    st.session_state["geom_valid"] = chk1_ok and chk2_ok and chk3_ok


# ═══════════════════════════════════════════════════════════════════════════════
# TAB C — PRESTRESSING REINFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_C:
    section_hdr("C.1", "Prestressing Type & Steel Properties")

    st.session_state["ps_type"] = st.radio(
        "Prestressing Type",
        options=["PC Wire (plain/indented)", "7-Wire Strand (low relax)"],
        index=0 if st.session_state["ps_type"] == "PC Wire (plain/indented)" else 1,
        horizontal=True, key="_ps_type"
    )

    ps = st.session_state["ps_type"]
    col1, col2 = st.columns([1, 2])

    if ps == "PC Wire (plain/indented)":
        with col1:
            wire_dia_opts = [5.0, 7.0]
            st.session_state["wire_dia"] = st.selectbox(
                "Wire Diameter (mm)",
                options=wire_dia_opts,
                index=wire_dia_opts.index(st.session_state["wire_dia"]),
                key="_wire_dia"
            )
        props = WIRE_PROPS[st.session_state["wire_dia"]]
        ps_area = props["area_mm2"]
        fpu     = props["fpu_MPa"]
        fpy     = props["fpy_MPa"]
        Eps     = props["Eps_MPa"]
        with col2:
            st.markdown(f"""
            <div class="metric-grid">
                {metric_card("Area/wire", f"{ps_area:.1f}", "mm²")}
                {metric_card("fpu", f"{fpu:,}", "MPa")}
                {metric_card("fpy", f"{fpy:,}", "MPa")}
                {metric_card("Eps", f"{Eps:,}", "MPa")}
            </div>""", unsafe_allow_html=True)

    else:  # 7-Wire Strand
        with col1:
            strand_opts = list(STRAND_PROPS.keys())
            st.session_state["strand_size"] = st.selectbox(
                "Strand Size",
                options=strand_opts,
                index=strand_opts.index(st.session_state["strand_size"]),
                key="_strand_size"
            )
        props   = STRAND_PROPS[st.session_state["strand_size"]]
        ps_area = props["area_mm2"]
        fpu     = props["fpu_MPa"]
        fpy     = props["fpy_MPa"]
        Eps     = props["Eps_MPa"]
        with col2:
            st.markdown(f"""
            <div class="metric-grid">
                {metric_card("d", f"{props['d_mm']:.1f}", "mm")}
                {metric_card("Area/strand", f"{ps_area:.1f}", "mm²")}
                {metric_card("fpu", f"{fpu:,}", "MPa")}
                {metric_card("fpy", f"{fpy:,}", "MPa")}
                {metric_card("Eps", f"{Eps:,}", "MPa")}
            </div>""", unsafe_allow_html=True)

    st.session_state["ps_area"] = ps_area
    st.session_state["fpu"]     = fpu
    st.session_state["fpy"]     = fpy
    st.session_state["Eps"]     = Eps

    st.markdown("---")
    section_hdr("C.2", "Tendon Layout & Initial Prestress")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state["n_bot"] = st.number_input(
            "n_bot — Bottom layer count",
            min_value=0, max_value=30, step=1,
            value=int(st.session_state["n_bot"]), key="_n_bot")

        st.session_state["cover_bot"] = st.number_input(
            "cover_bot — Clear cover to bottom wire CL (mm)",
            min_value=15, max_value=100, step=1,
            value=int(st.session_state["cover_bot"]), key="_cover_bot")

    with col2:
        st.session_state["n_top"] = st.number_input(
            "n_top — Top layer count (0 = none)",
            min_value=0, max_value=20, step=1,
            value=int(st.session_state["n_top"]), key="_n_top")

        if st.session_state["n_top"] > 0:
            st.session_state["cover_top"] = st.number_input(
                "cover_top — Clear cover to top wire CL (mm)",
                min_value=15, max_value=100, step=1,
                value=int(st.session_state["cover_top"]), key="_cover_top")

    with col3:
        st.session_state["fpi_pct"] = st.slider(
            "fpi_pct — Initial prestress (% of fpu)",
            min_value=70.0, max_value=80.0, step=0.5,
            value=float(st.session_state["fpi_pct"]), key="_fpi_pct")

    # ── Derived prestress values ──
    n_bot     = st.session_state["n_bot"]
    n_top     = st.session_state["n_top"]
    cover_bot = st.session_state["cover_bot"]
    cover_top = st.session_state["cover_top"]
    fpi_pct   = st.session_state["fpi_pct"]
    h_slab    = st.session_state["h"]

    Aps_bot = n_bot * ps_area
    Aps_top = n_top * ps_area
    fpi     = fpi_pct / 100.0 * fpu
    Pi      = (Aps_bot + Aps_top) * fpi / 1000.0  # kN
    dp_bot  = h_slab - cover_bot
    dp_top  = cover_top if n_top > 0 else 0.0

    st.session_state["Aps_bot"] = Aps_bot
    st.session_state["Aps_top"] = Aps_top
    st.session_state["fpi"]     = fpi
    st.session_state["Pi"]      = Pi
    st.session_state["dp_bot"]  = dp_bot
    st.session_state["dp_top"]  = dp_top

    st.markdown("---")
    section_hdr("C.3", "Derived Prestress Values (Auto)")

    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("Aps_bot", f"{Aps_bot:,.1f}", "mm²")}
        {metric_card("Aps_top", f"{Aps_top:,.1f}" if n_top > 0 else "—", "mm²")}
        {metric_card("fpi", f"{fpi:,.1f}", "MPa")}
        {metric_card("Pi (initial force)", f"{Pi:,.1f}", "kN")}
        {metric_card("dp_bot", f"{dp_bot:.0f}", "mm")}
        {metric_card("dp_top", f"{dp_top:.0f}" if n_top > 0 else "—", "mm")}
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB D — SPAN GEOMETRY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_D:
    section_hdr("D.1", "Span Dimensions & Bearing")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state["L_cc"] = st.number_input(
            "L_cc — Center-to-center span (mm)",
            min_value=1000, max_value=30000, step=100,
            value=int(st.session_state["L_cc"]), key="_L_cc")

    with col2:
        st.session_state["b_bear_L"] = st.number_input(
            "b_bear_L — Left bearing width (mm)",
            min_value=50, max_value=500, step=5,
            value=int(st.session_state["b_bear_L"]), key="_b_bear_L")

    with col3:
        st.session_state["b_bear_R"] = st.number_input(
            "b_bear_R — Right bearing width (mm)",
            min_value=50, max_value=500, step=5,
            value=int(st.session_state["b_bear_R"]), key="_b_bear_R")

    L_cc     = st.session_state["L_cc"]
    b_bear_L = st.session_state["b_bear_L"]
    b_bear_R = st.session_state["b_bear_R"]

    L_clear = L_cc - b_bear_L / 2 - b_bear_R / 2
    st.session_state["L_clear"] = L_clear

    st.markdown("---")
    section_hdr("D.2", "Analysis Span Selection")

    st.session_state["span_type"] = st.radio(
        "Analysis Span",
        options=["Clear span", "Clear + 1/2 bearing"],
        index=0 if st.session_state["span_type"] == "Clear span" else 1,
        horizontal=True, key="_span_type"
    )

    if st.session_state["span_type"] == "Clear span":
        L_an = L_clear
        span_label = "L_clear"
    else:
        L_an = L_clear + (b_bear_L + b_bear_R) * 0.25
        span_label = "L_clear + ½ bearing"

    st.session_state["L_an"] = L_an

    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("L_cc", f"{L_cc:,}", "mm")}
        {metric_card("L_clear", f"{L_clear:,.0f}", "mm")}
        {metric_card(f"L_an ({span_label})", f"{L_an:,.0f}", "mm")}
    </div>
    """, unsafe_allow_html=True)

    bear_min = max(L_clear / 180, 50.8)
    st.session_state["bear_min"] = bear_min

    st.markdown("---")
    section_hdr("D.3", "Bearing Length Check")
    st.caption("Ref: ACI/PCI 319-25 Table 16.2.6.2")

    bear_ok_L = b_bear_L >= bear_min
    bear_ok_R = b_bear_R >= bear_min

    col1, col2, col3 = st.columns(3)
    col1.metric("Minimum Bearing Required", f"{bear_min:.1f} mm")
    col2.metric("Left Bearing",  f"{b_bear_L} mm",
                delta="OK" if bear_ok_L else f"Short by {bear_min - b_bear_L:.1f} mm",
                delta_color="normal" if bear_ok_L else "inverse")
    col3.metric("Right Bearing", f"{b_bear_R} mm",
                delta="OK" if bear_ok_R else f"Short by {bear_min - b_bear_R:.1f} mm",
                delta_color="normal" if bear_ok_R else "inverse")

    if not (bear_ok_L and bear_ok_R):
        st.error(f"⚠️ ACI/PCI 319-25 Table 16.2.6.2: Minimum bearing length = {bear_min:.1f} mm. "
                 f"One or both bearings are insufficient. Increase bearing width.")

    # ── Phase 1B additions: Transfer & Development Length ─────────────────────
    st.markdown("---")
    section_hdr("D.4", "Transfer & Development Length")
    st.caption("Ref: PCI Sec. 4.2.3  |  ACI 318-19 §25.8.6 & §25.8.7")

    _d_ps_ui = get_ps_diameter_mm()
    col1, col2, col3 = st.columns(3)
    col1.metric("Transfer Length  l_t",
                f"{st.session_state['lb_l_t']:.0f} mm",
                help="Length over which prestress is transferred to concrete")
    col2.metric("Development Length  l_d",
                f"{st.session_state['lb_l_d']:.0f} mm",
                help="Length required for full flexural bond strength")
    col3.metric("d_ps (wire/strand diameter)",
                f"{_d_ps_ui:.1f} mm")

    st.markdown(f"""
    <div class="info-box">
    <b>Method:</b> {st.session_state['lb_lt_method']}<br>
    <b>fse (est.):</b> {st.session_state['lb_fse_est']:.1f} MPa &nbsp;·&nbsp;
    <b>fps (est.):</b> {st.session_state['lb_fps_est']:.1f} MPa<br>
    <b>Note:</b> {st.session_state['lb_loss_note']}
    </div>""", unsafe_allow_html=True)

    _ps_stat   = st.session_state["lb_ps_status"]
    _ps_colors = {"FULL": "badge-ok", "PARTIAL": "badge-warn",
                  "NON-PRESTRESSED": "badge-err"}
    _ps_icons  = {"FULL": "&#10003;", "PARTIAL": "&#9888;",
                  "NON-PRESTRESSED": "&#10007;"}
    st.markdown(
        f'<span class="{_ps_colors[_ps_stat]}">'
        f'{_ps_icons[_ps_stat]} Prestress development: {_ps_stat} '
        f'&nbsp;(L_an = {L_an:,.0f} mm &nbsp;/&nbsp;'
        f' l_d = {st.session_state["lb_l_d"]:.0f} mm)</span>',
        unsafe_allow_html=True,
    )
    if _ps_stat != "FULL":
        st.warning(st.session_state["lb_ps_message"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB E — LOADING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_E:
    section_hdr("E.1", "Self-Weight (Auto-Calculated)")

    b_bot_sw  = st.session_state["b_bottom"]
    h_sw      = st.session_state["h"]
    wc_sw     = st.session_state["wc"]
    avoids    = st.session_state["A_voids_total"]
    b_nom     = st.session_state["b_nominal"]
    wc_top_sw = st.session_state["wc_top"]
    t_top_sw  = st.session_state["t_topping"] if st.session_state["has_topping"] else 0

    if st.session_state["hcs_type"] == "Full HCS (Hollow Core)":
        gross_A = b_bot_sw * h_sw - avoids
    else:
        gross_A = b_bot_sw * h_sw

    SW_HCS     = wc_sw * (gross_A / (b_bot_sw * 1e6))
    SW_topping = wc_top_sw * t_top_sw / 1000.0

    st.session_state["SW_HCS"]     = SW_HCS
    st.session_state["SW_topping"] = SW_topping

    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("SW_HCS", f"{SW_HCS:.3f}", "kN/m²")}
        {metric_card("SW_topping", f"{SW_topping:.3f}" if st.session_state["has_topping"] else "—", "kN/m²")}
        {metric_card("SW_total", f"{SW_HCS + SW_topping:.3f}", "kN/m²")}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    section_hdr("E.2", "Superimposed Loads (per m² plan area)")

    col1, col2 = st.columns(2)
    with col1:
        st.session_state["SDL"] = st.number_input(
            "SDL — Superimposed dead load (kN/m²)",
            min_value=0.0, max_value=50.0, step=0.25,
            value=float(st.session_state["SDL"]), key="_SDL")

    with col2:
        st.session_state["LL"] = st.number_input(
            "LL — Live load (kN/m²)",
            min_value=0.0, max_value=100.0, step=0.25,
            value=float(st.session_state["LL"]), key="_LL")

    st.markdown("---")
    section_hdr("E.3", "Point Loads (Optional)")

    st.session_state["has_point_load"] = st.checkbox(
        "Point Loads Present?",
        value=st.session_state["has_point_load"], key="_has_point_load")

    if st.session_state["has_point_load"]:
        st.markdown("**Point Load P1**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.session_state["P1_DL"] = st.number_input(
                "P1_DL (kN)", min_value=0.0, step=0.5,
                value=float(st.session_state["P1_DL"]), key="_P1_DL")
        with col2:
            st.session_state["P1_LL"] = st.number_input(
                "P1_LL (kN)", min_value=0.0, step=0.5,
                value=float(st.session_state["P1_LL"]), key="_P1_LL")
        with col3:
            st.session_state["x_P1"] = st.number_input(
                "x_P1 — Distance from left support (mm)",
                min_value=0, step=50,
                value=int(st.session_state["x_P1"]), key="_x_P1")

        st.markdown("**Point Load P2** *(set DL=LL=0 to ignore)*")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.session_state["P2_DL"] = st.number_input(
                "P2_DL (kN)", min_value=0.0, step=0.5,
                value=float(st.session_state["P2_DL"]), key="_P2_DL")
        with col2:
            st.session_state["P2_LL"] = st.number_input(
                "P2_LL (kN)", min_value=0.0, step=0.5,
                value=float(st.session_state["P2_LL"]), key="_P2_LL")
        with col3:
            st.session_state["x_P2"] = st.number_input(
                "x_P2 — Distance from left support (mm)",
                min_value=0, step=50,
                value=int(st.session_state["x_P2"]), key="_x_P2")

        st.markdown("---")
        section_hdr("E.4", "Point Load Distribution — PCI Fig. 4.10.1.1")
        st.caption("Ref: PCI Design Handbook 8th Ed., Fig. 4.10.1.1")

        st.session_state["slab_position"] = st.radio(
            "Slab Position for Load Distribution",
            options=["Interior slab", "Edge slab"],
            index=0 if st.session_state["slab_position"] == "Interior slab" else 1,
            horizontal=True, key="_slab_position"
        )

        L_an_load = st.session_state["L_an"]
        if st.session_state["slab_position"] == "Interior slab":
            eff_width = min(0.50 * L_an_load, b_nom * 5)
        else:
            eff_width = min(0.25 * L_an_load, b_nom * 3)

        st.session_state["eff_width"] = eff_width
        P1_total = st.session_state["P1_DL"] + st.session_state["P1_LL"]
        w_P1_eq  = P1_total / (eff_width / 1000.0)

        st.markdown(f"""
        <div class="metric-grid">
            {metric_card("Effective dist. width", f"{eff_width:,.0f}", "mm")}
            {metric_card("P1 equiv. line load", f"{w_P1_eq:.2f}", "kN/m")}
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div class="info-box">
        ℹ️ PCI Fig. 4.10.1.1 — load distribution pattern is octagonal (not simple trapezoid).
        Effective width varies linearly from support (narrow) to 0.25×L_an from midspan (full width).
        </div>""", unsafe_allow_html=True)

    # ── Phase 1B additions: Factored Load Summary ──────────────────────────────
    st.markdown("---")
    section_hdr("E.5", "Factored Load Summary")
    st.caption("Ref: ASCE 7 / ACI 318-19 Table 5.3.1  |  1.2D + 1.6L")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("wu (factored UDL)",  f"{st.session_state['lb_wu_area']:.3f} kN/m²")
    col2.metric("Vu_max (factored)",  f"{st.session_state['lb_Vu_max']:.2f} kN")
    col3.metric("Mu_max (factored)",  f"{st.session_state['lb_Mu_max']/1e6:.2f} kN·m")
    col4.metric("Ra (left reaction)", f"{st.session_state['lb_Ra_u']:.2f} kN")

    st.markdown("---")
    section_hdr("E.6", "Shear Force & Bending Moment Diagrams")
    st.caption("Solid = factored  |  Dashed = service  |  Shaded = transfer length zone")

    _sst   = st.session_state
    _x_m   = _sst["lb_x_arr"] / 1000.0
    _L_m   = float(_sst.get("L_an", 6000)) / 1000.0
    _l_t_m = _sst["lb_l_t"] / 1000.0

    _fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=("Shear Force Diagram — Vu (kN)",
                        "Bending Moment Diagram — Mu (kN·m)"),
        vertical_spacing=0.14,
        shared_xaxes=True,
    )

    _fig.add_trace(go.Scatter(
        x=_x_m, y=_sst["lb_Vu_arr"],
        name="Vu factored",
        line=dict(color="#388bfd", width=2),
    ), row=1, col=1)
    _fig.add_trace(go.Scatter(
        x=_x_m, y=_sst["lb_Vs_arr"],
        name="Vs service",
        line=dict(color="#388bfd", width=1.5, dash="dash"),
    ), row=1, col=1)
    _fig.add_trace(go.Scatter(
        x=[0, _L_m], y=[0, 0],
        mode="lines",
        line=dict(color="#30363d", width=1),
        showlegend=False,
    ), row=1, col=1)

    _vu_abs_max = max(float(np.max(np.abs(_sst["lb_Vu_arr"]))), 1.0)
    _fig.add_shape(type="rect", xref="x", yref="y",
                   x0=0, x1=_l_t_m, y0=-_vu_abs_max*1.3, y1=_vu_abs_max*1.3,
                   fillcolor="rgba(248,81,73,0.10)",
                   line=dict(color="rgba(248,81,73,0.40)", width=1), row=1, col=1)
    _fig.add_shape(type="rect", xref="x", yref="y",
                   x0=_L_m-_l_t_m, x1=_L_m, y0=-_vu_abs_max*1.3, y1=_vu_abs_max*1.3,
                   fillcolor="rgba(248,81,73,0.10)",
                   line=dict(color="rgba(248,81,73,0.40)", width=1), row=1, col=1)
    _fig.add_annotation(x=_l_t_m/2, y=_vu_abs_max*1.15,
                        text="← l_t →", font=dict(size=9, color="#f85149"),
                        showarrow=False, row=1, col=1)
    _fig.add_annotation(x=_L_m-_l_t_m/2, y=_vu_abs_max*1.15,
                        text="← l_t →", font=dict(size=9, color="#f85149"),
                        showarrow=False, row=1, col=1)

    if _sst["has_point_load"] and _sst["lb_Pu1_red"] > 0:
        _fig.add_shape(type="line", xref="x", yref="y",
                       x0=_sst["lb_x_P1_use"]/1000, x1=_sst["lb_x_P1_use"]/1000,
                       y0=-_vu_abs_max*1.2, y1=_vu_abs_max*1.2,
                       line=dict(color="#f0883e", width=1.5, dash="dot"), row=1, col=1)
        _fig.add_annotation(x=_sst["lb_x_P1_use"]/1000, y=_vu_abs_max*0.85,
                            text="P1", font=dict(size=10, color="#f0883e"),
                            showarrow=False, row=1, col=1)
    if _sst["has_point_load"] and _sst["lb_Pu2_red"] > 0:
        _fig.add_shape(type="line", xref="x", yref="y",
                       x0=_sst["lb_x_P2_use"]/1000, x1=_sst["lb_x_P2_use"]/1000,
                       y0=-_vu_abs_max*1.2, y1=_vu_abs_max*1.2,
                       line=dict(color="#f0883e", width=1.5, dash="dot"), row=1, col=1)
        _fig.add_annotation(x=_sst["lb_x_P2_use"]/1000, y=_vu_abs_max*0.85,
                            text="P2", font=dict(size=10, color="#f0883e"),
                            showarrow=False, row=1, col=1)

    _fig.add_trace(go.Scatter(
        x=_x_m, y=_sst["lb_Mu_arr"] / 1e6,
        name="Mu factored",
        fill="tozeroy",
        fillcolor="rgba(56,139,253,0.08)",
        line=dict(color="#388bfd", width=2),
    ), row=2, col=1)
    _fig.add_trace(go.Scatter(
        x=_x_m, y=_sst["lb_Ms_arr"] / 1e6,
        name="Ms service",
        line=dict(color="#39d353", width=1.5, dash="dash"),
    ), row=2, col=1)
    _fig.add_annotation(
        x=_sst["lb_Mu_max_x"]/1000, y=_sst["lb_Mu_max"]/1e6,
        text=f"Mu_max = {_sst['lb_Mu_max']/1e6:.1f} kN·m",
        showarrow=True, arrowhead=2, arrowcolor="#e6edf3",
        font=dict(size=11, color="#e6edf3"), row=2, col=1)

    _mu_max_v = max(float(np.max(_sst["lb_Mu_arr"] / 1e6)), 1.0)
    _fig.add_shape(type="rect", xref="x", yref="y",
                   x0=0, x1=_l_t_m, y0=0, y1=_mu_max_v*1.15,
                   fillcolor="rgba(248,81,73,0.07)",
                   line=dict(color="rgba(248,81,73,0.30)", width=1), row=2, col=1)
    _fig.add_shape(type="rect", xref="x", yref="y",
                   x0=_L_m-_l_t_m, x1=_L_m, y0=0, y1=_mu_max_v*1.15,
                   fillcolor="rgba(248,81,73,0.07)",
                   line=dict(color="rgba(248,81,73,0.30)", width=1), row=2, col=1)

    _fig.update_layout(
        height=540,
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b22",
        font=dict(color="#e6edf3", size=11, family="IBM Plex Mono, monospace"),
        legend=dict(orientation="h", y=1.06, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=10)),
        margin=dict(l=60, r=30, t=70, b=50),
    )
    _fig.update_xaxes(gridcolor="#30363d", zerolinecolor="#30363d", row=1, col=1)
    _fig.update_xaxes(title_text="Distance from left support (m)",
                      gridcolor="#30363d", zerolinecolor="#30363d", row=2, col=1)
    _fig.update_yaxes(title_text="Shear (kN)",
                      gridcolor="#30363d", zerolinecolor="#30363d", row=1, col=1)
    _fig.update_yaxes(title_text="Moment (kN·m)",
                      gridcolor="#30363d", zerolinecolor="#30363d", row=2, col=1)

    st.plotly_chart(_fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB F — SEISMIC & INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_F:
    section_hdr("F.1", "Seismic Design Category")

    sdc_opts = ["A", "B", "C", "D", "E", "F"]
    st.session_state["sdc"] = st.selectbox(
        "Seismic Design Category (SDC)",
        options=sdc_opts,
        index=sdc_opts.index(st.session_state["sdc"]),
        key="_sdc"
    )

    sdc = st.session_state["sdc"]
    if sdc in ["D", "E", "F"]:
        st.error("""
**ACI/PCI CODE-319-25 Section 12 — SDC D/E/F Warning:**

- In-plane diaphragm flexibility **MUST** be modeled.
- Untopped HCS **cannot** be assumed as a rigid diaphragm.
- Panel connections require validation per **ACI CODE-550.5**.
- Special connection detailing is required at all panel-to-panel and panel-to-support interfaces.
        """)
    elif sdc == "C":
        st.warning("SDC C: Review ACI/PCI 319-25 Section 12 for intermediate seismic requirements. "
                   "Connection detailing may require special attention.")
    else:
        st.success(f"SDC {sdc}: Standard design provisions apply. "
                   "Seismic detailing requirements are minimal.")

    st.markdown("---")
    section_hdr("F.2", "Structural Integrity (ACI/PCI 319-25 Cl. 16.5)")
    st.markdown("""
    <div class="info-box">
    ℹ️ Structural integrity reinforcement will be verified in Phase 1B / Phase 5.<br>
    Minimum tie force requirements per ACI/PCI 319-25 Section 16.5 apply to all HCS connections.
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB — SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sum:
    st.markdown("## 📋 Input Summary")
    st.caption("All values as currently entered — review before running calculations.")

    ss = st.session_state

    def tbl(data: dict, title: str):
        """Render a clean summary table."""
        df = pd.DataFrame(list(data.items()), columns=["Parameter", "Value"])
        st.markdown(f"**{title}**")
        st.dataframe(df, use_container_width=True, hide_index=True)

    col_l, col_r = st.columns(2)

    with col_l:
        tbl({
            "f'ci (transfer)":    f"{ss['f_ci']} MPa",
            "f'c_cut (cutting)":  f"{ss['f_c_cut']} MPa",
            "f'c_del (delivery)": f"{ss['f_c_del']} MPa",
            "f'c_ere (erection)": f"{ss['f_c_ere']} MPa",
            "f'c (28-day)":       f"{ss['f_c']} MPa",
            "wc":                 f"{ss['wc']} kN/m³",
            "Topping":            "Yes" if ss["has_topping"] else "No",
            "f'c_top":            f"{ss['f_c_top']} MPa" if ss["has_topping"] else "N/A",
            "Ec_HCS (auto)":      f"{ss.get('Ec_hcs', 0):,.0f} MPa",
            "Ec_top (auto)":      f"{ss.get('Ec_top', 0):,.0f} MPa" if ss["has_topping"] else "N/A",
            "n (modular ratio)":  f"{ss.get('n_mod', 0):.3f}" if ss["has_topping"] else "N/A",
        }, "A · Concrete")

        tbl({
            "L_cc":          f"{ss['L_cc']:,} mm",
            "b_bear_L":      f"{ss['b_bear_L']} mm",
            "b_bear_R":      f"{ss['b_bear_R']} mm",
            "L_clear (auto)":f"{ss.get('L_clear', 0):,.0f} mm",
            "L_an (auto)":   f"{ss.get('L_an', 0):,.0f} mm",
            "Span type":     ss["span_type"],
            "Bear. min (auto)": f"{ss.get('bear_min', 0):.1f} mm",
            "l_t (auto)":    f"{ss.get('lb_l_t', 0):.0f} mm",
            "l_d (auto)":    f"{ss.get('lb_l_d', 0):.0f} mm",
            "PS status":     ss.get("lb_ps_status", "—"),
        }, "D · Span")

        tbl({
            "SW_HCS (auto)":     f"{ss.get('SW_HCS', 0):.3f} kN/m²",
            "SW_topping (auto)": f"{ss.get('SW_topping', 0):.3f} kN/m²" if ss["has_topping"] else "N/A",
            "SDL":               f"{ss['SDL']} kN/m²",
            "LL":                f"{ss['LL']} kN/m²",
            "Point loads":       "Yes" if ss["has_point_load"] else "No",
            "wu (factored)":     f"{ss.get('lb_wu_area', 0):.3f} kN/m²",
            "Vu_max (fact.)":    f"{ss.get('lb_Vu_max', 0):.2f} kN",
            "Mu_max (fact.)":    f"{ss.get('lb_Mu_max', 0)/1e6:.2f} kN·m",
            "Ra (left)":         f"{ss.get('lb_Ra_u', 0):.2f} kN",
        }, "E · Loads")

    with col_r:
        tbl({
            "b_nominal":      f"{ss['b_nominal']} mm",
            "b_bottom":       f"{ss['b_bottom']} mm",
            "b_top":          f"{ss['b_top']} mm",
            "h":              f"{ss['h']} mm",
            "tf_top":         f"{ss['tf_top']} mm",
            "tf_bot":         f"{ss['tf_bot']} mm",
            "t_topping":      f"{ss['t_topping']} mm" if ss["has_topping"] else "0 mm",
            "HCS type":       ss["hcs_type"],
            "Core shape":     ss["core_shape"],
            "d_core":         f"{ss['d_core']} mm",
            "n_core":         ss["n_core"],
            "h_core (auto)":  f"{ss.get('h_core', 0):.1f} mm",
            "A_voids (auto)": f"{ss.get('A_voids_total', 0):,.0f} mm²",
            "bw_shear (auto)":f"{ss.get('bw_shear', 0):.0f} mm",
            "Geom. valid":    "✓ OK" if ss.get("geom_valid") else "⚠ Check geometry",
        }, "B · Cross-Section")

        tbl({
            "PS type":       ss["ps_type"],
            "Wire/strand":   f"{ss['wire_dia']} mm" if "Wire" in ss["ps_type"] else ss["strand_size"],
            "Area/unit":     f"{ss.get('ps_area', 0):.1f} mm²",
            "fpu":           f"{ss.get('fpu', 0):,} MPa",
            "fpy":           f"{ss.get('fpy', 0):,} MPa",
            "Eps":           f"{ss.get('Eps', 0):,} MPa",
            "n_bot":         ss["n_bot"],
            "n_top":         ss["n_top"],
            "cover_bot":     f"{ss['cover_bot']} mm",
            "dp_bot (auto)": f"{ss.get('dp_bot', 0):.0f} mm",
            "fpi_pct":       f"{ss['fpi_pct']:.1f} % fpu",
            "fpi (auto)":    f"{ss.get('fpi', 0):,.1f} MPa",
            "Pi (auto)":     f"{ss.get('Pi', 0):,.1f} kN",
            "Aps_bot (auto)":f"{ss.get('Aps_bot', 0):,.1f} mm²",
        }, "C · Prestress")

        tbl({
            "SDC": ss["sdc"],
            "High seismic (D/E/F)": "YES — special detailing required" if ss["sdc"] in ["D","E","F"] else "No",
        }, "F · Seismic")

    st.markdown("---")
    st.markdown("### Geometry Validation Summary")
    geom_ok = ss.get("geom_valid", False)
    bear_ok = (ss["b_bear_L"] >= ss.get("bear_min", 0) and
               ss["b_bear_R"] >= ss.get("bear_min", 0))

    badges_sum = ""
    badges_sum += badge_html("Cross-section geometry", "OK" if geom_ok else "WARN") + "&nbsp; "
    badges_sum += badge_html("Bearing lengths", "OK" if bear_ok else "WARN") + "&nbsp; "
    badges_sum += badge_html(f"SDC {ss['sdc']}",
                              "ERR" if ss["sdc"] in ["D","E","F"] else "OK") + "&nbsp; "
    badges_sum += badge_html(
        "Prestress dev.",
        "OK"   if ss.get("lb_ps_status") == "FULL"
              else ("WARN" if ss.get("lb_ps_status") == "PARTIAL" else "ERR"),
    ) + "&nbsp; "
    st.markdown(badges_sum, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Run Calculations")
    all_ready = geom_ok and bear_ok
    st.button(
        "▶  Run Calculations (Phase 3 onwards)",
        disabled=True,
        help="Complete and validate all inputs above to enable. "
             "Phase 3–7 will be implemented in subsequent builds.",
        use_container_width=True
    )
    st.info("ℹ️  **Phase 2 complete.** "
            "Section properties (gross, net, composite) are now computed every render. "
            "See **Appendix A · Section Props** tab for full details. "
            "Phase 3 will add prestress losses.")

    st.markdown("---")
    st.markdown("### Appendix A Preview — Section Properties")
    col1, col2, col3 = st.columns(3)
    with col1:
        tbl({
            "A_gross": f"{ss.get('sp_A_gross',0):,.0f} mm²",
            "I_gross": f"{ss.get('sp_I_gross',0)/1e6:.2f} ×10⁶ mm⁴",
            "yb_gross":f"{ss.get('sp_yb_gross',0):.1f} mm",
        }, "Gross Section")
    with col2:
        tbl({
            "A_net":   f"{ss.get('sp_A_net',0):,.0f} mm²",
            "I_net":   f"{ss.get('sp_I_net',0)/1e6:.2f} ×10⁶ mm⁴",
            "yb_net":  f"{ss.get('sp_yb_net',0):.1f} mm",
            "e_bot":   f"{ss.get('sp_e_bot',0):.1f} mm",
        }, "Net HCS Section")
    with col3:
        tbl({
            "A_comp":  f"{ss.get('sp_A_comp',0):,.0f} mm²",
            "I_comp":  f"{ss.get('sp_I_comp',0)/1e6:.2f} ×10⁶ mm⁴",
            "yb_comp": f"{ss.get('sp_yb_comp',0):.1f} mm",
            "h_total": f"{ss.get('sp_h_total',0):.0f} mm",
        }, "Composite Section")


# ═══════════════════════════════════════════════════════════════════════════════
# APPENDIX A — SECTION PROPERTIES (Phase 2)
# Reference: ACI/PCI CODE-319-25 Cl. 26.12
#            PCI Design Handbook 8th Ed. Sec. 2.2 & 4.2.3
# ═══════════════════════════════════════════════════════════════════════════════
with tab_P2:
    st.markdown("## 📐 Appendix A — Section Properties")
    st.caption("Ref: ACI/PCI CODE-319-25 Cl. 26.12  |  PCI Design Handbook 8th Ed. Sec. 2.2 & 4.2.3")
    st.markdown("""
    <div class="info-box">
    <b>Coordinate system:</b> y measured upward from <b>bottom face of HCS</b> (excluding topping).<br>
    <b>Simplification:</b> Section modelled as rectangular b_top × h; voids subtracted at centroid
    y_void = tf_bot + h_core/2. Accuracy &gt;97% per PCI practice.<br>
    <b>Transformed steel:</b> (n−1)×Aps method — concrete area at steel location already in gross.
    </div>""", unsafe_allow_html=True)

    _s = st.session_state

    section_hdr("A.1", "Input Parameters Used")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("b_top",    f"{_s['b_top']} mm")
    col2.metric("h",        f"{_s['h']} mm")
    col3.metric("n_core",   f"{_s['n_core']}")
    col4.metric("d_core",   f"{_s['d_core']} mm")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("tf_top",   f"{_s['tf_top']} mm")
    col2.metric("tf_bot",   f"{_s['tf_bot']} mm")
    col3.metric("h_core",   f"{_s.get('h_core',0):.1f} mm")
    col4.metric("A_voids",  f"{_s.get('A_voids_total',0):,.0f} mm²")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Aps_bot",  f"{_s.get('Aps_bot',0):.1f} mm²")
    col2.metric("dp_bot",   f"{_s.get('dp_bot',0):.0f} mm")
    col3.metric("n_ps (Eps/Ec)", f"{_s.get('sp_n_ps',0):.2f}")
    col4.metric("n_mod (Ec_top/Ec_hcs)", f"{_s.get('n_mod',0):.3f}")

    st.markdown("---")

    section_hdr("A.2", "Gross Section  (rectangular b_top × h, no voids, no steel)")
    st.caption("Ref: ACI/PCI 319-25 Cl. 26.12.1")
    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("A_gross", f"{_s.get('sp_A_gross',0):,.0f}", "mm²")}
        {metric_card("yb_gross", f"{_s.get('sp_yb_gross',0):.1f}", "mm")}
        {metric_card("yt_gross", f"{_s.get('sp_yt_gross',0):.1f}", "mm")}
        {metric_card("I_gross", f"{_s.get('sp_I_gross',0)/1e6:.3f}", "×10⁶ mm⁴")}
        {metric_card("Sb_gross", f"{_s.get('sp_Sb_gross',0)/1e3:.1f}", "×10³ mm³")}
        {metric_card("St_gross", f"{_s.get('sp_St_gross',0)/1e3:.1f}", "×10³ mm³")}
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    section_hdr("A.3", "Net HCS Section  (voids subtracted + transformed prestress steel)")
    st.caption("Ref: PCI Design Handbook 8th Ed. Sec. 2.2.1  |  Transformed section — (n−1)·Aps method")
    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("A_net", f"{_s.get('sp_A_net',0):,.0f}", "mm²")}
        {metric_card("yb_net", f"{_s.get('sp_yb_net',0):.2f}", "mm")}
        {metric_card("yt_net", f"{_s.get('sp_yt_net',0):.2f}", "mm")}
        {metric_card("I_net", f"{_s.get('sp_I_net',0)/1e6:.3f}", "×10⁶ mm⁴")}
        {metric_card("Sb_net", f"{_s.get('sp_Sb_net',0)/1e3:.1f}", "×10³ mm³")}
        {metric_card("St_net", f"{_s.get('sp_St_net',0)/1e3:.1f}", "×10³ mm³")}
        {metric_card("r² (kern radius²)", f"{_s.get('sp_r2_net',0):.1f}", "mm²")}
        {metric_card("y_void_c", f"{_s.get('sp_y_void_c',0):.1f}", "mm")}
    </div>""", unsafe_allow_html=True)

    st.markdown("**Eccentricity of prestress tendons from section centroid:**")
    ecol1, ecol2 = st.columns(2)
    ecol1.metric("e_bot  (bottom tendons, + = below NA)",
                 f"{_s.get('sp_e_bot',0):.2f} mm",
                 help="dp_bot − yb_net  (positive = below neutral axis = favourable)")
    if _s.get("n_top", 0) > 0:
        ecol2.metric("e_top  (top tendons, − = above NA)",
                     f"{_s.get('sp_e_top',0):.2f} mm")
    else:
        ecol2.info("No top tendons (n_top = 0)")

    kt = _s.get('sp_I_net', 1.0) / (_s.get('sp_A_net', 1.0) * _s.get('sp_yb_net', 1.0))
    kb = _s.get('sp_I_net', 1.0) / (_s.get('sp_A_net', 1.0) * _s.get('sp_yt_net', 1.0))
    st.markdown(f"""
    <div class="info-box">
    <b>Kern limits</b> (ACI/PCI 319-25 — no tension criteria zone):<br>
    k_t = I_net / (A_net × yb_net) = <b>{kt:.1f} mm</b> (upper kern — measured from top)<br>
    k_b = I_net / (A_net × yt_net) = <b>{kb:.1f} mm</b> (lower kern — measured from bottom)<br>
    Prestress within kern → no tension in concrete under prestress alone.
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    section_hdr("A.4", "Composite Section  (net HCS + transformed topping)")
    st.caption("Ref: PCI Design Handbook 8th Ed. Sec. 4.2.3  |  n_mod = Ec_top / Ec_hcs")

    if _s.get("has_topping") and _s.get("t_topping", 0) > 0:
        st.markdown(f"""
        <div class="metric-grid">
            {metric_card("A_comp", f"{_s.get('sp_A_comp',0):,.0f}", "mm²")}
            {metric_card("yb_comp", f"{_s.get('sp_yb_comp',0):.2f}", "mm from HCS bot")}
            {metric_card("yt_comp", f"{_s.get('sp_yt_comp',0):.2f}", "mm from top topping")}
            {metric_card("I_comp", f"{_s.get('sp_I_comp',0)/1e6:.3f}", "×10⁶ mm⁴")}
            {metric_card("Sbc_comp", f"{_s.get('sp_Sbc_comp',0)/1e3:.1f}", "×10³ mm³ (bot)")}
            {metric_card("Stc_comp", f"{_s.get('sp_Stc_comp',0)/1e3:.1f}", "×10³ mm³ (top)")}
            {metric_card("Stc_hcs", f"{_s.get('sp_Stc_hcs',0)/1e3:.1f}", "×10³ mm³ (HCS top)")}
            {metric_card("h_total", f"{_s.get('sp_h_total',0):.0f}", "mm")}
            {metric_card("b_top_tr (topping)", f"{_s.get('sp_b_top_tr',0):.1f}", "mm")}
        </div>""", unsafe_allow_html=True)
    else:
        st.info("No structural topping — composite section = net HCS section.")
        st.markdown(f"""
        <div class="metric-grid">
            {metric_card("A_comp = A_net", f"{_s.get('sp_A_comp',0):,.0f}", "mm²")}
            {metric_card("I_comp = I_net", f"{_s.get('sp_I_comp',0)/1e6:.3f}", "×10⁶ mm⁴")}
            {metric_card("yb_comp = yb_net", f"{_s.get('sp_yb_comp',0):.2f}", "mm")}
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    section_hdr("A.5", "Complete Section Properties Table")
    st.caption("For use in Phase 4 stress checks and Phase 5 capacity calculations")

    _sp_table = {
        "Property": [
            "Area A (mm²)",
            "Centroid from bottom yb (mm)",
            "Centroid from top yt (mm)",
            "Moment of inertia I (×10⁶ mm⁴)",
            "Section modulus bottom Sb (×10³ mm³)",
            "Section modulus top St (×10³ mm³)",
        ],
        "Gross": [
            f"{_s.get('sp_A_gross',0):,.0f}",
            f"{_s.get('sp_yb_gross',0):.2f}",
            f"{_s.get('sp_yt_gross',0):.2f}",
            f"{_s.get('sp_I_gross',0)/1e6:.4f}",
            f"{_s.get('sp_Sb_gross',0)/1e3:.1f}",
            f"{_s.get('sp_St_gross',0)/1e3:.1f}",
        ],
        "Net HCS": [
            f"{_s.get('sp_A_net',0):,.0f}",
            f"{_s.get('sp_yb_net',0):.2f}",
            f"{_s.get('sp_yt_net',0):.2f}",
            f"{_s.get('sp_I_net',0)/1e6:.4f}",
            f"{_s.get('sp_Sb_net',0)/1e3:.1f}",
            f"{_s.get('sp_St_net',0)/1e3:.1f}",
        ],
        "Composite": [
            f"{_s.get('sp_A_comp',0):,.0f}",
            f"{_s.get('sp_yb_comp',0):.2f}",
            f"{_s.get('sp_yt_comp',0):.2f}",
            f"{_s.get('sp_I_comp',0)/1e6:.4f}",
            f"{_s.get('sp_Sbc_comp',0)/1e3:.1f}",
            f"{_s.get('sp_Stc_comp',0)/1e3:.1f}",
        ],
    }
    st.dataframe(pd.DataFrame(_sp_table), use_container_width=True, hide_index=True)

    st.markdown("""
    <div class="info-box">
    ℹ️ <b>Usage in subsequent phases:</b><br>
    &nbsp;• Phase 3 (Prestress Losses): uses A_net, I_net, e_bot, r²<br>
    &nbsp;• Phase 4 (Stress Checks Release): uses A_net, Sb_net, St_net with gross section for SW<br>
    &nbsp;• Phase 4 (Stress Checks Service): uses Sb_net (DL) and Sbc_comp / Stc_comp (SDL+LL)<br>
    &nbsp;• Phase 5 (Mn/Vn Capacity): uses dp_bot, Aps_bot, composite section geometry<br>
    &nbsp;• Phase 6 (Deflection): uses I_net (prestress/DL) and I_comp (SDL+LL)
    </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB G — SECTION PROPERTIES  (quick view)
# Reference: ACI/PCI CODE-319-25 Cl. 26.12
#            PCI Design Handbook, 8th Edition Sec. 2.2 & 4.2.3
# ═══════════════════════════════════════════════════════════════════════════════
with tab_G:
    st.markdown("## G · Section Properties")
    st.caption(
        "Ref: ACI/PCI CODE-319-25 Cl. 26.12  |  PCI Design Handbook 8th Ed. Sec. 2.2 & 4.2.3  "
        "|  Full detail → Appendix A tab"
    )

    _g = st.session_state   # local alias

    # ── G.1 Gross Section ─────────────────────────────────────────────────────
    section_hdr("G.1", "Gross Section  (b_top × h, no voids, no steel)")
    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("Ag",      f"{_g.get('sp_Ag',  0):,.0f}",               "mm²")}
        {metric_card("yb_g",    f"{_g.get('sp_yb_g', 0):.1f}",               "mm")}
        {metric_card("yt_g",    f"{_g.get('sp_yt_g', 0):.1f}",               "mm")}
        {metric_card("Ig",      f"{_g.get('sp_Ig',  0)/1e6:.3f}",            "×10⁶ mm⁴")}
        {metric_card("Sb_g",    f"{_g.get('sp_Sb_g', 0)/1e3:.1f}",           "×10³ mm³")}
        {metric_card("St_g",    f"{_g.get('sp_St_g', 0)/1e3:.1f}",           "×10³ mm³")}
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── G.2 Net HCS Section ───────────────────────────────────────────────────
    section_hdr("G.2", "Net HCS Section  (voids subtracted, concrete only)")
    st.markdown(f"""
    <div class="metric-grid">
        {metric_card("An",      f"{_g.get('sp_An',  0):,.0f}",               "mm²")}
        {metric_card("yb",      f"{_g.get('sp_yb',  0):.2f}",                "mm")}
        {metric_card("yt",      f"{_g.get('sp_yt',  0):.2f}",                "mm")}
        {metric_card("In",      f"{_g.get('sp_In',  0)/1e6:.3f}",            "×10⁶ mm⁴")}
        {metric_card("Sb",      f"{_g.get('sp_Sb',  0)/1e3:.1f}",            "×10³ mm³")}
        {metric_card("St",      f"{_g.get('sp_St',  0)/1e3:.1f}",            "×10³ mm³")}
        {metric_card("r²",      f"{_g.get('sp_r2',  0):.1f}",                "mm²")}
        {metric_card("y_void_c",f"{_g.get('sp_y_void_c', 0):.1f}",          "mm")}
    </div>""", unsafe_allow_html=True)

    # Kern points
    st.markdown(f"""
    <div class="info-box">
    <b>Kern points</b> — no-tension zone  (ACI/PCI 319-25 Cl. 24.5.2):<br>
    k_b = In / (An × yb) = <b>{_g.get('sp_kb', 0):.1f} mm</b>
          (lower kern — from bottom fibre)<br>
    k_t = In / (An × yt) = <b>{_g.get('sp_kt', 0):.1f} mm</b>
          (upper kern — from top fibre)<br>
    Prestress resultant within kern → no tensile stress in concrete under P alone.
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── G.3 Eccentricity ──────────────────────────────────────────────────────
    section_hdr("G.3", "Prestress Eccentricity  (from net section centroid)")
    st.caption("Ref: PCI Design Handbook Sec. 2.2  |  ACI/PCI 319-25 Cl. 26.10")

    ecol1, ecol2, ecol3 = st.columns(3)
    ecol1.metric(
        "e_bot  (bottom steel)",
        f"{_g.get('sp_e_bot', 0):.2f} mm",
        help="dp_bot − yb  (+ve = below centroid = sagging favourable)"
    )
    if _g.get("n_top", 0) > 0:
        ecol2.metric(
            "e_top  (top steel)",
            f"{_g.get('sp_e_top', 0):.2f} mm",
            help="dp_top − yb  (−ve = above centroid)"
        )
    else:
        ecol2.info("No top tendons (n_top = 0)")
    ecol3.metric(
        "e_net  (resultant)",
        f"{_g.get('sp_e_net', 0):.2f} mm",
        help="(Aps_bot×e_bot + Aps_top×e_top) / Aps_total"
    )

    st.markdown("---")

    # ── G.4 Composite Section ─────────────────────────────────────────────────
    section_hdr("G.4", "Composite Section  (HCS + topping)")
    st.caption("Ref: PCI Design Handbook 8th Ed. Sec. 2.2.3  |  n_mod = Ec_top / Ec_hcs")

    if _g.get("has_topping") and _g.get("t_topping", 0) > 0:
        st.markdown(f"""
        <div class="metric-grid">
            {metric_card("A_comp",    f"{_g.get('sp_A_comp',   0):,.0f}",          "mm²")}
            {metric_card("yb_comp",   f"{_g.get('sp_yb_comp',  0):.2f}",           "mm from HCS bot")}
            {metric_card("yt_comp",   f"{_g.get('sp_yt_comp',  0):.2f}",           "mm from top")}
            {metric_card("I_comp",    f"{_g.get('sp_I_comp',   0)/1e6:.3f}",       "×10⁶ mm⁴")}
            {metric_card("Sb_comp",   f"{_g.get('sp_Sb_comp',  0)/1e3:.1f}",       "×10³ mm³ (bot)")}
            {metric_card("St_comp",   f"{_g.get('sp_St_comp',  0)/1e3:.1f}",       "×10³ mm³ (top topping)")}
            {metric_card("St_hcs",    f"{_g.get('sp_St_hcs',   0)/1e3:.1f}",       "×10³ mm³ (HCS top)")}
            {metric_card("St_top_tr", f"{_g.get('sp_St_top_tr',0)/1e3:.1f}",       "×10³ mm³ (topping units)")}
            {metric_card("h_total",   f"{_g.get('sp_h_total',  0):.0f}",           "mm")}
            {metric_card("b_top_tr",  f"{_g.get('sp_b_top_tr', 0):.1f}",           "mm (transformed)")}
        </div>""", unsafe_allow_html=True)

        st.markdown(f"""
        <div class="info-box">
        <b>n_mod</b> = Ec_top / Ec_hcs = <b>{_g.get('n_mod', 0):.3f}</b>
        &nbsp;·&nbsp; Topping transformed width = b_top × n_mod = <b>{_g.get('sp_b_top_tr', 0):.1f} mm</b><br>
        <b>St_top_tr</b> = St_comp × n_mod — used in Phase 4 to check stress in topping concrete.
        </div>""", unsafe_allow_html=True)
    else:
        st.info("No structural topping — composite section equals net HCS section.")
        st.markdown(f"""
        <div class="metric-grid">
            {metric_card("A_comp = An", f"{_g.get('sp_A_comp', 0):,.0f}",        "mm²")}
            {metric_card("I_comp = In", f"{_g.get('sp_I_comp', 0)/1e6:.3f}",     "×10⁶ mm⁴")}
            {metric_card("yb_comp = yb",f"{_g.get('sp_yb_comp',0):.2f}",         "mm")}
            {metric_card("h_total = h", f"{_g.get('sp_h_total', 0):.0f}",        "mm")}
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div class="info-box">
    ℹ️  Full step-by-step calculation trace (void I derivations, parallel-axis tables,
    kern diagram) is available in <b>Appendix A · Section Props</b> tab.
    </div>""", unsafe_allow_html=True)
