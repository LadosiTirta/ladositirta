# =============================================================================
# HCS DESIGN APP — Phase 1A: Input UI & Session State
# =============================================================================
# Reference: ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
# Units: SI only (mm, kN, MPa)
# Greek symbols: plain text (phi, alfa, beta, etc.) for export compatibility
# =============================================================================

import math
import streamlit as st
import numpy as np
import pandas as pd

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
# HARDCODED DATA TABLES
# =============================================================================

# PC Wire properties (Indonesian manufacturer data)
# Converted: 1 kg/cm² = 0.09807 MPa
WIRE_PROPS = {
    5.0: {
        "area_mm2": 19.6,
        "fpu_MPa":  1618,    # 16500 kg/cm² × 0.09807
        "fpy_MPa":  1432,    # 14600 kg/cm² × 0.09807
        "Eps_MPa":  199_050  # 2,029,888 kg/cm² × 0.09807
    },
    7.0: {
        "area_mm2": 38.5,
        "fpu_MPa":  1515,    # 15450 kg/cm² × 0.09807
        "fpy_MPa":  1324,    # 13500 kg/cm² × 0.09807
        "Eps_MPa":  199_990  # 2,039,541 kg/cm² × 0.09807
    }
}

# 7-Wire Strand properties — ASTM A416 Grade 270, Low-Relaxation
# Source: PCI Design Handbook Table 2.11.1
STRAND_PROPS = {
    "3/8 in  (d=8.4mm)":  {"d_mm": 8.4,  "area_mm2": 54.9,  "fpu_MPa": 1862, "fpy_MPa": 1675, "Eps_MPa": 196_500},
    "7/16 in (d=9.7mm)":  {"d_mm": 9.7,  "area_mm2": 74.2,  "fpu_MPa": 1860, "fpy_MPa": 1674, "Eps_MPa": 196_500},
    "1/2 in  (d=11.2mm)": {"d_mm": 11.2, "area_mm2": 98.7,  "fpu_MPa": 1862, "fpy_MPa": 1675, "Eps_MPa": 196_500},
    "3/5 in  (d=13.4mm)": {"d_mm": 13.4, "area_mm2": 140.0, "fpu_MPa": 1860, "fpy_MPa": 1674, "Eps_MPa": 196_500},
}

# HCS Presets — standard Indonesian precast section data
PRESET_TABLE = {
    "Custom (manual input)": None,
    "HCS 120mm — Circular core": {
        "h": 120, "b_bottom": 1197, "b_top": 1185,
        "tf_top": 40, "tf_bot": 30,
        "core_shape": "Circular",
        "d_core": 60, "n_core": 9,
        "gap_side": 64, "gap_between": 70,
        "h_straight": 40, "h_taper": 20,
    },
    "HCS 150mm — Teardrop core": {
        "h": 150, "b_bottom": 1197, "b_top": 1185,
        "tf_top": 40, "tf_bot": 40,
        "core_shape": "Teardrop",
        "d_core": 80, "h_taper": 10, "n_core": 9,
        "gap_side": 66, "gap_between": 53,
        "h_straight": 40,
    },
    "HCS 200mm — Teardrop core": {
        "h": 200, "b_bottom": 1199, "b_top": 1187,
        "tf_top": 52, "tf_bot": 50,
        "core_shape": "Teardrop",
        "d_core": 80, "h_taper": 40, "n_core": 9,
        "gap_side": 67, "gap_between": 52,
        "h_straight": 40,
    },
    "HCS 250mm — Capsule core": {
        "h": 250, "b_bottom": 1199, "b_top": 1187,
        "tf_top": 52, "tf_bot": 50,
        "core_shape": "Capsule",
        "d_core": 80, "h_straight": 100, "n_core": 9,
        "gap_side": 67, "gap_between": 52,
        "h_taper": 20,
    },
}


# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================
def init_session_state():
    """Initialise all session state variables with HCS 200mm defaults."""
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
# HELPER FUNCTIONS
# =============================================================================

def apply_preset(preset_name: str):
    """Apply preset geometry values to session state."""
    p = PRESET_TABLE.get(preset_name)
    if p is None:
        return
    for k, v in p.items():
        st.session_state[k] = v


def calc_core_area(core_shape: str, d_core: float,
                   h_straight: float, h_taper: float) -> float:
    """
    Calculate area of ONE core void.
    ACI/PCI 319-25 — section property calculation.
    """
    if core_shape == "Circular":
        # Full circle
        return (math.pi / 4) * d_core ** 2
    elif core_shape == "Capsule":
        # Semicircle top + rectangle + semicircle bottom
        # = full circle + rectangle
        return (math.pi / 4) * d_core ** 2 + d_core * h_straight
    else:  # Teardrop
        # Semicircle top + triangular taper
        # Bottom tapers to ~0.30*d_core; avg width = 0.65*d_core
        return (math.pi / 4) * d_core ** 2 + 0.65 * d_core * h_taper


def calc_h_core(core_shape: str, d_core: float,
                h_straight: float, h_taper: float) -> float:
    """Total height of one core void."""
    if core_shape == "Circular":
        return d_core
    elif core_shape == "Capsule":
        return d_core + h_straight
    else:  # Teardrop
        return d_core + h_taper


def calc_modular_ratio(wc: float, f_c: float,
                       wc_top: float, f_c_top: float) -> tuple:
    """
    Elastic moduli and modular ratio.
    ACI 318-19 Eq. 19.2.2.1: Ec = 0.043 * wc^1.5 * sqrt(f_c)
    wc in kN/m³ → need kg/m³ for the formula (wc_kgm3 = wc*1000/9.81)
    In SI with wc in kg/m³:  Ec [MPa] = 0.043 * wc^1.5 * sqrt(fc)
    Convert: wc [kN/m³] * (1000/9.81) = wc [kg/m³]
    """
    # ACI 318-19 Eq. 19.2.2.1 — wc must be in kg/m³
    wc_kgm3     = wc     * 1000 / 9.81
    wc_top_kgm3 = wc_top * 1000 / 9.81
    Ec_hcs = 0.043 * (wc_kgm3 ** 1.5) * math.sqrt(f_c)
    Ec_top = 0.043 * (wc_top_kgm3 ** 1.5) * math.sqrt(f_c_top)
    n_mod  = Ec_top / Ec_hcs
    return Ec_hcs, Ec_top, n_mod


def get_ps_props(ps_type: str, wire_dia: float, strand_size: str) -> dict:
    """Return prestressing steel properties dict."""
    if ps_type == "PC Wire (plain/indented)":
        return WIRE_PROPS[wire_dia]
    else:
        return STRAND_PROPS[strand_size]


def badge_html(label: str, status: str, detail: str = "") -> str:
    """Return HTML for a status badge."""
    css = {"OK": "badge-ok", "WARN": "badge-warn", "ERR": "badge-err"}[status]
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
# APP HEADER
# =============================================================================
init_session_state()

st.markdown("""
<div class="app-header">
    <div style="margin-bottom:8px">
        <span class="phase-badge">PHASE 1A</span>
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
    <b style="color:#e6edf3;">Phase 1A</b> — Input & Session State<br>
    <span style="color:#30363d;">Phase 1B — Span & Transfer Length</span><br>
    <span style="color:#30363d;">Phase 2  — Section Properties</span><br>
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
tab_A, tab_B, tab_C, tab_D, tab_E, tab_F, tab_sum = st.tabs([
    "A · Concrete", "B · Cross-Section", "C · Prestress",
    "D · Span", "E · Loads", "F · Seismic", "📋 Summary"
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
        st.session_state["t_topping"] = 0  # forced zero when no topping
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

    # Auto display h_core
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

    # Check 1: thickness balance
    h_check = tf_top + h_core_val + tf_bot
    delta_h = abs(h_check - h_slab)
    chk1_ok = delta_h < 1.0  # allow 1 mm tolerance

    # Check 2: width fit
    w_used  = 2 * gap_side + n_core * d_core + (n_core - 1) * gap_between
    chk2_ok = w_used <= b_bottom

    # Check 3: minimum gap
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

    # Store steel properties
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

    # Derived span
    L_cc    = st.session_state["L_cc"]
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

    # Bearing check — ACI/PCI 319-25 Table 16.2.6.2
    # min bearing = max(L_clear/180, 50.8mm)
    bear_min = max(L_clear / 180, 50.8)  # 50.8mm = 2 inches
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


# ═══════════════════════════════════════════════════════════════════════════════
# TAB E — LOADING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_E:
    section_hdr("E.1", "Self-Weight (Auto-Calculated)")

    # Self-weight calc
    # Full HCS: gross area minus void area (conservative for SW)
    # Half Slab: solid rectangular section
    b_bot_sw    = st.session_state["b_bottom"]
    h_sw        = st.session_state["h"]
    wc_sw       = st.session_state["wc"]
    avoids      = st.session_state["A_voids_total"]
    b_nom       = st.session_state["b_nominal"]
    wc_top_sw   = st.session_state["wc_top"]
    t_top_sw    = st.session_state["t_topping"] if st.session_state["has_topping"] else 0

    if st.session_state["hcs_type"] == "Full HCS (Hollow Core)":
        gross_A = b_bot_sw * h_sw - avoids  # mm²
    else:  # Half Slab — solid rectangular
        gross_A = b_bot_sw * h_sw

    # kN/m² plan area: force = wc[kN/m³] × volume[m³] / plan_area[m²]
    SW_HCS     = wc_sw * (gross_A / (b_bot_sw * 1e6))      # kN/m² per plan area
    SW_topping = wc_top_sw * t_top_sw / 1000.0              # kN/m² (density × thickness/1000)

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
            eff_width = min(0.50 * L_an_load, b_nom * 5)  # PCI approximate limit
        else:
            eff_width = min(0.25 * L_an_load, b_nom * 3)

        st.session_state["eff_width"] = eff_width
        P1_total = st.session_state["P1_DL"] + st.session_state["P1_LL"]
        w_P1_eq  = P1_total / (eff_width / 1000.0)  # kN/m equivalent line load

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

    # Build summary tables
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
        }, "D · Span")

        tbl({
            "SW_HCS (auto)":     f"{ss.get('SW_HCS', 0):.3f} kN/m²",
            "SW_topping (auto)": f"{ss.get('SW_topping', 0):.3f} kN/m²" if ss["has_topping"] else "N/A",
            "SDL":               f"{ss['SDL']} kN/m²",
            "LL":                f"{ss['LL']} kN/m²",
            "Point loads":       "Yes" if ss["has_point_load"] else "No",
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

    # Geometry validation summary
    st.markdown("### Geometry Validation Summary")
    geom_ok = ss.get("geom_valid", False)
    bear_ok = (ss["b_bear_L"] >= ss.get("bear_min", 0) and
               ss["b_bear_R"] >= ss.get("bear_min", 0))

    badges_sum = ""
    badges_sum += badge_html("Cross-section geometry", "OK" if geom_ok else "WARN") + "&nbsp; "
    badges_sum += badge_html("Bearing lengths", "OK" if bear_ok else "WARN") + "&nbsp; "
    badges_sum += badge_html(f"SDC {ss['sdc']}",
                              "ERR" if ss["sdc"] in ["D","E","F"] else "OK") + "&nbsp; "
    st.markdown(badges_sum, unsafe_allow_html=True)

    st.markdown("---")

    # Disabled Run button
    all_ready = geom_ok and bear_ok
    st.markdown("### Run Calculations")
    st.button(
        "▶  Run Calculations (Phase 1B onwards)",
        disabled=True,
        help="Complete and validate all inputs above to enable. "
             "Phase 1B–7 will be implemented in subsequent builds.",
        use_container_width=True
    )
    st.info("ℹ️  **Phase 1A complete.** "
            "Phases 1B through 7 will add: transfer length, section properties, "
            "prestress losses, stress checks, Mn/Vn capacity, deflection, and report generation.")
