# =============================================================================
# HCS DESIGN APP — Phase 7: Complete (All phases 1-7)
# =============================================================================
# Reference: ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
# Units: SI only (mm, kN, MPa)
# CHANGE LOG:
#   FIX-1: SW_HCS formula corrected (/1000)
#   FIX-2: Tab reorder, preset guard, beam width for span, line loads
#   FIX-3: Custom LF per load, line load with position, seismic detail,
#           UI fully in English
#   FIX-4: Editable PCI multipliers, thermal camber, custom defl limits,
#           vibration / natural frequency check (AISC DG11 / ISO 10137)
#   FIX-5: Timezone offset, Assumed loss input, Shoring input (multiple supports),
#           SFD/BMD fix, combined with all features of arsip4
# =============================================================================

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import math

# hcs imports
from hcs.constants import WIRE_PROPS, STRAND_PROPS, PRESET_TABLE
from hcs.geometry import calc_core_area, calc_h_core, calc_modular_ratio, get_ps_props
from hcs.span_loads import (calc_transfer_development_length,
                             check_prestress_development,
                             calc_factored_loads_and_diagrams)
from hcs.section_props import get_all_section_props
from hcs.prestress_loss import get_prestress_losses
from hcs.stress_check import get_all_stress_checks
from hcs.capacity import get_capacity_results
from hcs.deflection import get_deflection_results, get_pci_multiplier_defaults
from hcs.report import get_report_bytes

st.set_page_config(
    page_title="HCS Design — ACI/PCI 319-25",
    page_icon="🏗️", layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SESSION STATE DEFAULTS
# =============================================================================
def init_session_state():
    import math as _math
    _d_A1   = _math.pi / 4 * 80**2 + 0.65 * 80 * 40   # Teardrop d=80 h_taper=40
    _d_Av   = 9 * _d_A1
    defaults = {
        # Concrete
        "f_ci": 35.0, "f_c_cut": 40.0, "f_c_del": 45.0, "f_c_ere": 50.0,
        "f_c": 50.0, "wc": 24.0,
        # Topping
        "has_topping": True, "f_c_top": 30.0, "wc_top": 24.0,
        # Section geometry
        "b_nominal": 1200, "b_bottom": 1199, "b_top": 1187, "h": 200,
        "tf_top": 52, "tf_bot": 50, "t_topping": 60,
        "hcs_type": "Full HCS (Hollow Core)",
        "core_shape": "Teardrop",
        "d_core": 80, "n_core": 9, "h_straight": 40, "h_taper": 40,
        "gap_side": 67, "gap_between": 52,
        "preset": "HCS 200mm — Teardrop core",
        "_preset_applied": "",
        # Derived geometry (set at startup, always overwritten in auto-calc)
        "A_core_1": _d_A1, "A_voids_total": _d_Av,
        "h_core": 120.0, "bw_shear": 1199 - 9 * 80,
        # Moduli
        "Ec_hcs": 33000.0, "Ec_top": 27000.0, "n_mod": 27000.0 / 33000.0,
        # Self-weight (always overwritten)
        "SW_HCS": 3.52, "SW_topping": 1.44,
        # Prestress
        "ps_type": "PC Wire (plain/indented)", "wire_dia": 5.0,
        "strand_size": "1/2 in  (d=11.2mm)", "n_bot": 10, "n_top": 0,
        "cover_bot": 35, "cover_top": 30, "fpi_pct": 75.0,
        "fpu": 1618.0, "fpy": 1432.0, "Eps": 199050.0, "ps_area": 19.6,
        "fpi": 1213.5, "Aps_bot": 196.0, "Aps_top": 0.0,
        "dp_bot": 165.0, "dp_top": 30.0, "Pi": 237.8,
        # Span
        "L_cc": 6000, "bw_beam_L": 300, "bw_beam_R": 300,
        "b_bear_L": 150, "b_bear_R": 150,
        "L_clear": 5700.0, "L_an": 5850.0, "bear_min": 50.8,
        "span_type": "Clear span",
        # Construction shoring
        "has_construction_shoring": False,
        "n_support": 1,           # number of temporary supports
        "dist_support_left": 0.0,  # mm from left support (if n_support=1, auto mid)
        "dist_support_right": 0.0, # mm from right support (if n_support=1, auto mid)
        "L_shored": 3000,          # calculated effective span
        # Loads — area
        "SDL": 1.5, "LL": 2.0,
        # Load factors (FIX-3: per-load)
        "lf_DL": 1.2, "lf_LL": 1.6,
        "lf_SDL": 1.2,
        "lf_P1DL": 1.2, "lf_P1LL": 1.6,
        "lf_P2DL": 1.2, "lf_P2LL": 1.6,
        # Line loads (FIX-3)
        "has_line_load": False,
        "w_line_DL": 0.0, "w_line_LL": 0.0,
        "x_line_start": 0, "x_line_end": 5850,
        "lf_line_DL": 1.2, "lf_line_LL": 1.6,
        # Old line load keys (kept for backward compat)
        "wL_long_DL": 0.0, "wL_long_LL": 0.0,
        "wL_trans_DL": 0.0, "wL_trans_LL": 0.0,
        # Point loads
        "has_point_load": False,
        "P1_DL": 5.0, "P1_LL": 5.0, "x_P1": 2000,
        "P2_DL": 0.0, "P2_LL": 0.0, "x_P2": 4000,
        "slab_position": "Interior slab",
        # Seismic
        "sdc": "B",
        # Loss parameters
        "RH": 75.0, "V_S": 38.0, "vs_auto": True,
        "assumed_loss_pct": 20.0,   # assumed total loss (%)
        # Deflection settings (PCI multipliers & limits)
        "mult_camber_erection": 1.85,
        "mult_dw_erection":     1.85,
        "mult_camber_final":    2.70,
        "mult_dw_final":        2.40,
        "mult_sdl_final":       3.00,
        "mult_ll_final":        1.00,
        "limit_LL_fraction":    360,
        "limit_total_fraction": 240,
        "defl_structure_type":  "Office floor (L/360 LL, L/240 total)",
        # Thermal
        "has_thermal": False,
        "alpha_T": 10e-6,
        "delta_T": 0.0,
        # Vibration
        "vibration_mode": "Walking / Occupancy",
        "damping_ratio": 3.0,
        # Timezone
        "tz_offset": 7.0,  # WIB default
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def apply_preset(preset_name):
    p = PRESET_TABLE.get(preset_name)
    if p:
        for k, v in p.items():
            st.session_state[k] = v

def get_ps_diameter_mm():
    if st.session_state["ps_type"] == "PC Wire (plain/indented)":
        return float(st.session_state["wire_dia"])
    return STRAND_PROPS[st.session_state["strand_size"]]["d_mm"]

def badge_html(label, status, detail=""):
    css   = {"OK": "badge-ok", "WARN": "badge-warn", "ERR": "badge-err"}[status]
    icons = {"OK": "✓", "WARN": "⚠", "ERR": "✗"}[status]
    return f'<span class="{css}">{icons} {label}{" — " + detail if detail else ""}</span>'

def metric_card(label, value, unit=""):
    return (f'<div class="metric-card">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}'
            f'<span class="metric-unit">{unit}</span></div></div>')

def section_hdr(code, title):
    st.markdown(
        f'<div class="section-header">'
        f'<span class="section-label">{code}</span><h3>{title}</h3></div>',
        unsafe_allow_html=True
    )

def calc_SW_HCS(wc, b_bottom, h, A_voids_total, hcs_type):
    """
    SW_HCS [kN/m²] = wc [kN/m³] × (A_conc [mm²] / b_bottom [mm]) / 1000
    Example HCS200: 24 × ((1199×200 - 63959) / 1199) / 1000 ≈ 3.52 kN/m²
    """
    A_conc = float(b_bottom) * float(h) - float(A_voids_total)
    A_conc = max(A_conc, 0.0)
    return float(wc) * (A_conc / float(b_bottom)) / 1000.0

def calc_SW_topping(wc_top, t_topping, has_topping):
    """SW_topping [kN/m²] = wc_top [kN/m³] × t_topping [mm] / 1000"""
    if has_topping and t_topping > 0:
        return float(wc_top) * float(t_topping) / 1000.0
    return 0.0

# =============================================================================
# INIT
# =============================================================================
init_session_state()
_ss = st.session_state

# ── Timezone offset from sidebar (will be set below) ──────────────────────────
_tz_offset = _ss.get("tz_offset", 7.0)
_ss["report_datetime"] = (
    datetime.utcnow() + timedelta(hours=_tz_offset)
).strftime("%d %B %Y   %H:%M") + f"  (UTC{_tz_offset:+.1f})"

# PRESET GUARD
if _ss.get("_preset_applied") != _ss["preset"]:
    apply_preset(_ss["preset"])
    _ss["_preset_applied"] = _ss["preset"]
    st.rerun()

# =============================================================================
# AUTO-CALCULATIONS
# =============================================================================

# ── 1. Geometry ──────────────────────────────────────────────────────────────
_A_core_1     = calc_core_area(_ss["core_shape"], _ss["d_core"],
                                _ss["h_straight"], _ss["h_taper"])
_A_voids_total = float(_ss["n_core"]) * _A_core_1
_h_core_val   = calc_h_core(_ss["core_shape"], _ss["d_core"],
                             _ss["h_straight"], _ss["h_taper"])
_bw_shear     = float(_ss["b_bottom"]) - float(_ss["n_core"]) * float(_ss["d_core"])
_ss["A_core_1"]      = _A_core_1
_ss["A_voids_total"] = _A_voids_total
_ss["h_core"]        = _h_core_val
_ss["bw_shear"]      = _bw_shear

# ── 2. Elastic moduli ─────────────────────────────────────────────────────────
_Ec_hcs, _Ec_top, _n_mod = calc_modular_ratio(
    _ss["wc"], _ss["f_c"], _ss["wc_top"], _ss["f_c_top"])
_ss["Ec_hcs"] = _Ec_hcs
_ss["Ec_top"] = _Ec_top
_ss["n_mod"]  = _n_mod

# ── 3. SW_HCS ────────────────────────────────────────────────────────────────
_SW_HCS     = calc_SW_HCS(_ss["wc"], _ss["b_bottom"], _ss["h"],
                           _A_voids_total, _ss["hcs_type"])
_SW_topping = calc_SW_topping(_ss["wc_top"], _ss["t_topping"], _ss["has_topping"])
_ss["SW_HCS"]     = _SW_HCS
_ss["SW_topping"] = _SW_topping

# ── 4. V/S auto ──────────────────────────────────────────────────────────────
if _ss.get("vs_auto", True):
    _A_conc_vs = float(_ss["b_bottom"]) * float(_ss["h"]) - _A_voids_total
    _perim_vs  = 2.0 * (float(_ss["b_bottom"]) + float(_ss["h"]))
    _ss["V_S"] = round(_A_conc_vs / _perim_vs, 1) if _perim_vs > 0 else 38.0

# ── 5. Span ───────────────────────────────────────────────────────────────────
_L_clear  = float(_ss["L_cc"]) - float(_ss["bw_beam_L"]) / 2.0 - float(_ss["bw_beam_R"]) / 2.0
_L_an     = _L_clear + float(_ss["b_bear_L"]) / 2.0 + float(_ss["b_bear_R"]) / 2.0
_bear_min = max(_L_clear / 180.0, 50.8)
_ss["L_clear"]  = _L_clear
_ss["L_an"]     = _L_an
_ss["bear_min"] = _bear_min

# ── 6. Transfer & development length ─────────────────────────────────────────
_fpi_cur = float(_ss["fpi_pct"]) / 100.0 * float(_ss["fpu"])
_ss["fpi"] = _fpi_cur
_d_ps = get_ps_diameter_mm()
_td = calc_transfer_development_length(
    ps_type=_ss["ps_type"], d_ps=_d_ps, fpu=_ss["fpu"],
    fpi=_fpi_cur, fpy=_ss.get("fpy", _ss["fpu"] * 0.885),
    assumed_loss_pct=20.0)
for _k in ["l_t", "l_d", "fse_est", "fps_est", "method_lt", "loss_note"]:
    _ss[f"lb_{_k}"] = _td[_k]
_dev = check_prestress_development(_L_an, _td["l_d"])
_ss["lb_ps_status"]  = _dev["status"]
_ss["lb_ps_is_ps"]   = _dev["is_prestressed"]
_ss["lb_ps_message"] = _dev["message"]

# ── 7. Prestress derived ──────────────────────────────────────────────────────
_Aps_bot = float(_ss["n_bot"]) * float(_ss["ps_area"])
_Aps_top = float(_ss["n_top"]) * float(_ss["ps_area"])
_Pi_val  = (_Aps_bot + _Aps_top) * _fpi_cur / 1000.0
_dp_bot  = float(_ss["h"]) - float(_ss["cover_bot"])
_dp_top  = float(_ss["cover_top"]) if _ss["n_top"] > 0 else 0.0
_ss["Aps_bot"] = _Aps_bot
_ss["Aps_top"] = _Aps_top
_ss["Pi"]      = _Pi_val
_ss["dp_bot"]  = _dp_bot
_ss["dp_top"]  = _dp_top

# ── 8. Factored load diagrams ───────────────────────────────────────────────
_x_end_max  = int(_L_an * 1.1)
_x_line_end = int(_ss.get("x_line_end", int(_L_an)))
if _x_line_end <= 0:
    _x_line_end = int(_L_an)
_x_line_end = min(_x_line_end, _x_end_max)
_ss["x_line_end"] = _x_line_end

_ld = calc_factored_loads_and_diagrams(
    L_an=_L_an, b_bottom=_ss["b_bottom"], t_topping=_ss["t_topping"],
    wc=_ss["wc"], wc_top=_ss["wc_top"], has_topping=_ss["has_topping"],
    SW_HCS=_SW_HCS, SW_topping=_SW_topping,
    SDL=_ss["SDL"], LL=_ss["LL"],
    has_point_load=_ss["has_point_load"],
    P1_DL=_ss["P1_DL"], P1_LL=_ss["P1_LL"], x_P1=_ss["x_P1"],
    P2_DL=_ss["P2_DL"], P2_LL=_ss["P2_LL"], x_P2=_ss["x_P2"],
    slab_position=_ss["slab_position"], N=200,
    lf_DL=_ss["lf_DL"],   lf_LL=_ss["lf_LL"],
    lf_SDL=_ss["lf_SDL"],
    lf_P1DL=_ss["lf_P1DL"], lf_P1LL=_ss["lf_P1LL"],
    lf_P2DL=_ss["lf_P2DL"], lf_P2LL=_ss["lf_P2LL"],
    w_line_DL=_ss["w_line_DL"]    if _ss["has_line_load"] else 0.0,
    w_line_LL=_ss["w_line_LL"]    if _ss["has_line_load"] else 0.0,
    x_line_start=float(_ss["x_line_start"]),
    x_line_end=float(_x_line_end),
    lf_line_DL=_ss["lf_line_DL"],
    lf_line_LL=_ss["lf_line_LL"],
)
for _k, _v in _ld.items():
    _ss[f"lb_{_k}"] = _v

_wu_user = (_ss["lf_DL"] * (_SW_HCS + _SW_topping)
            + _ss["lf_SDL"] * _ss["SDL"]
            + _ss["lf_LL"]  * _ss["LL"])
_ss["lb_wu_user"] = _wu_user

# ── 9. Phases 2-6 ─────────────────────────────────────────────────────────────
_sp = get_all_section_props(dict(_ss))
for _k, _v in _sp.items():
    _ss[f"sp_{_k}"] = _v

_losses = get_prestress_losses(_ss)
for _k, _v in _losses.items():
    _ss[_k] = _v

_stress = get_all_stress_checks(_ss)
for _k, _v in _stress.items():
    _ss[_k] = _v

_cap = get_capacity_results(_ss)
for _k, _v in _cap.items():
    _ss[_k] = _v

_def = get_deflection_results(_ss)
for _k, _v in _def.items():
    _ss[_k] = _v

# =============================================================================
# APP HEADER & SIDEBAR
# =============================================================================
st.markdown("""
<div class="app-header">
    <div>
        <span class="phase-badge">PHASE 7</span>
        <span class="phase-badge">ACI/PCI 319-25</span>
        <span class="phase-badge">PCI 8th Ed.</span>
    </div>
    <h1>🏗️ Hollow Core Slab Design</h1>
    <div class="subtitle">Full Design Suite · SI Units · v1.0</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📐 HCS Design App")
    # Timezone selector
    st.number_input("UTC offset (hours)", -12.0, 14.0, _ss.get("tz_offset", 7.0), 0.5,
                    key="tz_offset", help="Your local time zone relative to UTC")
    st.markdown("---")
    st.markdown(
        "✔ A — Section<br>✔ B — Materials<br>✔ C — Span<br>"
        "✔ D — Loads<br>✔ E — Seismic<br>✔ F — Props<br>"
        "✔ G — Stress<br>✔ H — Capacity<br>✔ I — Deflection<br>"
        "▶ J — Report",
        unsafe_allow_html=True
    )
    st.caption("References: ACI/PCI 319-25, PCI Handbook 8th Ed.")
    st.markdown("---")
    if "cap_DCR_M" in _ss:
        _dcr_m = _ss["cap_DCR_M"]
        _dcr_v = _ss.get("cap_DCR_V", 999)
        st.markdown(f"**SW_HCS** = `{_ss['SW_HCS']:.3f}` kN/m²")
        st.markdown(f"**L_an**   = `{_ss['L_an']:.0f}` mm")
        st.markdown(f"**DCR_M**  = `{_dcr_m:.3f}` {'✅' if _dcr_m <= 1.0 else '❌'}")
        st.markdown(f"**DCR_V**  = `{_dcr_v:.3f}` {'✅' if _dcr_v <= 1.0 else '❌'}")

# =============================================================================
# TABS
# =============================================================================
tabs = st.tabs([
    "A · Section", "B · Materials", "C · Span", "D · Loads",
    "E · Seismic", "F · Props", "G · Stress", "H · Capacity",
    "I · Deflection", "J · Report", "📋 Summary"
])
(tab_A, tab_B, tab_C, tab_D,
 tab_E, tab_F, tab_G, tab_H,
 tab_I, tab_J, tab_sum) = tabs

# =============================================================================
# TAB A — Section
# =============================================================================
with tab_A:
    section_hdr("A.0", "HCS Type")
    _ss["hcs_type"] = st.radio(
        "HCS Type",
        ["Full HCS (Hollow Core)", "Half Slab (Open Top)"],
        index=0 if _ss["hcs_type"] == "Full HCS (Hollow Core)" else 1,
        horizontal=True, key="_hcs_type"
    )
    if _ss["hcs_type"] == "Half Slab (Open Top)":
        _ss["tf_top"] = 0
        st.info("Half Slab: top flange tf_top forced = 0.")
    st.markdown("---")

    section_hdr("A.1", "Standard Preset")
    _pkeys = list(PRESET_TABLE.keys()) if _ss["hcs_type"] == "Full HCS (Hollow Core)" \
             else ["Custom (manual input)"]
    if _ss["hcs_type"] == "Half Slab (Open Top)":
        st.info("Half Slab: preset not available. Use manual input below.")
    _pidx = _pkeys.index(_ss["preset"]) if _ss["preset"] in _pkeys else 0
    _preset_choice = st.selectbox("Select preset", _pkeys, index=_pidx, key="_preset_select")
    if _preset_choice != _ss["preset"]:
        _ss["preset"] = _preset_choice
        _ss["_preset_applied"] = ""
        st.rerun()
    if _preset_choice != "Custom (manual input)":
        st.caption(f"✓ Preset: **{_preset_choice}**  "
                   f"(h={_ss['h']} mm, d_core={_ss['d_core']} mm, n_core={_ss['n_core']})")
    st.markdown("---")

    section_hdr("A.2", "Dimensions")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["b_nominal"] = st.number_input("b_nominal (mm)", 600, 2400, int(_ss["b_nominal"]), 1, key="_b_nominal")
        _ss["b_bottom"]  = st.number_input("b_bottom (mm)",  600, 2400, int(_ss["b_bottom"]),  1, key="_b_bottom")
        _ss["b_top"]     = st.number_input("b_top (mm)",     600, 2400, int(_ss["b_top"]),     1, key="_b_top")
    with col2:
        _ss["h"]     = st.number_input("h HCS (mm)", 80, 600, int(_ss["h"]), 1, key="_h")
        if _ss["hcs_type"] == "Full HCS (Hollow Core)":
            _ss["tf_top"] = st.number_input("tf_top (mm)", 0, 200, int(_ss["tf_top"]), 1, key="_tf_top")
        else:
            st.markdown("**tf_top = 0** (Half Slab)")
        _ss["tf_bot"] = st.number_input("tf_bot (mm)", 10, 200, int(_ss["tf_bot"]), 1, key="_tf_bot")
    with col3:
        _ss["has_topping"] = st.checkbox("Structural Topping?", _ss["has_topping"], key="_has_topping")
        if _ss["has_topping"]:
            _ss["t_topping"] = st.number_input("t_topping (mm)", 0, 200, int(_ss["t_topping"]), 5, key="_t_topping")
        else:
            _ss["t_topping"] = 0
            st.info("No topping → t_topping = 0")
    st.markdown("---")

    if _ss["hcs_type"] == "Full HCS (Hollow Core)":
        section_hdr("A.3", "Core Geometry")
        col1, col2 = st.columns([1, 2])
        with col1:
            _ss["core_shape"] = st.radio(
                "Core shape", ["Circular", "Capsule", "Teardrop"],
                index=["Circular", "Capsule", "Teardrop"].index(_ss["core_shape"]),
                key="_core_shape")
        with col2:
            _desc = {"Circular": "h_core = d_core (circle)",
                     "Capsule":  "h_core = d_core + h_straight (circle + rectangle)",
                     "Teardrop": "h_core = d_core + h_taper (circle + taper)"}
            st.info(_desc[_ss["core_shape"]])
        col1, col2, col3, col4 = st.columns(4)
        with col1: _ss["d_core"]     = st.number_input("d_core (mm)",     40, 300, int(_ss["d_core"]),     1, key="_d_core")
        with col2: _ss["n_core"]     = st.number_input("n_core",           1,  20, int(_ss["n_core"]),     1, key="_n_core")
        with col3: _ss["gap_side"]   = st.number_input("gap_side (mm)",   20, 200, int(_ss["gap_side"]),   1, key="_gap_side")
        with col4: _ss["gap_between"]= st.number_input("gap_between (mm)",10, 200, int(_ss["gap_between"]),1, key="_gap_between")
        if _ss["core_shape"] == "Capsule":
            _ss["h_straight"] = st.number_input("h_straight (mm)", 0, 400, int(_ss["h_straight"]), 5, key="_h_straight")
        if _ss["core_shape"] == "Teardrop":
            _ss["h_taper"]    = st.number_input("h_taper (mm)",    0, 400, int(_ss["h_taper"]),    5, key="_h_taper")
        _A1  = calc_core_area(_ss["core_shape"], _ss["d_core"], _ss["h_straight"], _ss["h_taper"])
        _Av  = _ss["n_core"] * _A1
        _hcv = calc_h_core(_ss["core_shape"], _ss["d_core"], _ss["h_straight"], _ss["h_taper"])
        _bws = float(_ss["b_bottom"]) - float(_ss["n_core"]) * float(_ss["d_core"])
        _ss["A_core_1"] = _A1; _ss["A_voids_total"] = _Av
        _ss["h_core"]   = _hcv; _ss["bw_shear"]     = _bws
        st.markdown(
            f"""<div class="metric-grid">
            {metric_card("h_core",        f"{_hcv:.1f}", "mm")}
            {metric_card("A_core_1",      f"{_A1:,.0f}", "mm²")}
            {metric_card("A_voids_total", f"{_Av:,.0f}", "mm²")}
            {metric_card("bw_shear",      f"{_bws:.0f}", "mm")}
            </div>""", unsafe_allow_html=True)
        st.markdown("---")
    else:
        section_hdr("A.3", "Core Geometry (Half Slab — tf_top=0, cores present)")
        st.info(
            "Half Slab = hollow core slab with top flange removed (tf_top = 0).  "
            "Core voids are still present — enter core dimensions below."
        )
        col1, col2 = st.columns([1, 2])
        with col1:
            _ss["core_shape"] = st.radio(
                "Core shape", ["Circular", "Capsule", "Teardrop"],
                index=["Circular", "Capsule", "Teardrop"].index(_ss["core_shape"]),
                key="_core_shape_hs")
        with col2:
            _desc_hs = {"Circular": "h_core = d_core (circle)",
                        "Capsule":  "h_core = d_core + h_straight (circle + rectangle)",
                        "Teardrop": "h_core = d_core + h_taper (circle + taper)"}
            st.info(_desc_hs[_ss["core_shape"]])
        col1, col2, col3, col4 = st.columns(4)
        with col1: _ss["d_core"]      = st.number_input("d_core (mm)",     40, 300, int(_ss["d_core"]),     1, key="_d_core_hs")
        with col2: _ss["n_core"]      = st.number_input("n_core",           1,  20, int(_ss["n_core"]),     1, key="_n_core_hs")
        with col3: _ss["gap_side"]    = st.number_input("gap_side (mm)",   20, 200, int(_ss["gap_side"]),   1, key="_gap_side_hs")
        with col4: _ss["gap_between"] = st.number_input("gap_between (mm)",10, 200, int(_ss["gap_between"]),1, key="_gap_between_hs")
        if _ss["core_shape"] == "Capsule":
            _ss["h_straight"] = st.number_input("h_straight (mm)", 0, 400, int(_ss["h_straight"]), 5, key="_h_str_hs")
        if _ss["core_shape"] == "Teardrop":
            _ss["h_taper"]    = st.number_input("h_taper (mm)",    0, 400, int(_ss["h_taper"]),    5, key="_h_tap_hs")
        _A1_hs  = calc_core_area(_ss["core_shape"], _ss["d_core"], _ss["h_straight"], _ss["h_taper"])
        _Av_hs  = float(_ss["n_core"]) * _A1_hs
        _hcv_hs = calc_h_core(_ss["core_shape"], _ss["d_core"], _ss["h_straight"], _ss["h_taper"])
        _bws_hs = float(_ss["b_bottom"]) - float(_ss["n_core"]) * float(_ss["d_core"])
        _ss["A_core_1"]      = _A1_hs
        _ss["A_voids_total"] = _Av_hs
        _ss["h_core"]        = _hcv_hs
        _ss["bw_shear"]      = _bws_hs
        st.markdown(
            f"""<div class="metric-grid">
            {metric_card("h_core",        f"{_hcv_hs:.1f}", "mm")}
            {metric_card("A_core_1",      f"{_A1_hs:,.0f}", "mm²")}
            {metric_card("A_voids_total", f"{_Av_hs:,.0f}", "mm²")}
            {metric_card("bw_shear",      f"{_bws_hs:.0f}", "mm")}
            </div>""", unsafe_allow_html=True)
        st.markdown("---")

    section_hdr("A.4", "Geometry Validation & SW Preview")
    _hcv2    = _ss["h_core"]
    _hchk    = _ss["tf_top"] + _hcv2 + _ss["tf_bot"]
    _chk1    = abs(_hchk - _ss["h"]) < 1.0
    _wused   = 2 * _ss["gap_side"] + _ss["n_core"] * _ss["d_core"] + (_ss["n_core"] - 1) * _ss["gap_between"]
    _chk2    = _wused <= _ss["b_bottom"]
    _chk3    = _ss["gap_between"] >= 25
    _sw_prev  = calc_SW_HCS(_ss["wc"], _ss["b_bottom"], _ss["h"],
                             _A_voids_total, _ss["hcs_type"])
    _swtprev  = calc_SW_topping(_ss["wc_top"], _ss["t_topping"], _ss["has_topping"])

    if _ss["hcs_type"] == "Full HCS (Hollow Core)":
        _badges = (badge_html(f"Flange+core: {_hchk:.1f} mm (h={_ss['h']})", "OK" if _chk1 else "ERR") + "  " +
                   badge_html(f"Width fit: {_wused} ≤ {_ss['b_bottom']}", "OK" if _chk2 else "WARN") + "  " +
                   badge_html("gap_between ≥ 25 mm", "OK" if _chk3 else "WARN"))
    else:
        _hchk_hs = 0 + _hcv2 + _ss["tf_bot"]
        _chk1_hs = abs(_hchk_hs - _ss["h"]) < 1.0
        _badges  = (badge_html(f"Half Slab — core+tf_bot: {_hchk_hs:.1f} mm (h={_ss['h']})",
                               "OK" if _chk1_hs else "ERR") + "  " +
                    badge_html(f"Width fit: {_wused} ≤ {_ss['b_bottom']}",
                               "OK" if _chk2 else "WARN"))
    st.markdown(_badges, unsafe_allow_html=True)
    _ss["geom_valid"] = (_chk1 and _chk2 and _chk3) if _ss["hcs_type"] == "Full HCS (Hollow Core)" else (_chk1_hs if _ss["hcs_type"] != "Full HCS (Hollow Core)" else True)

    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("SW_HCS (live)",    f"{_sw_prev:.3f}",            "kN/m²")}
        {metric_card("SW_topping (live)",f"{_swtprev:.3f}",            "kN/m²")}
        {metric_card("SW_total (live)",  f"{_sw_prev + _swtprev:.3f}", "kN/m²")}
        </div>""", unsafe_allow_html=True)
    st.caption(
        f"SW_HCS = wc × (b×h − A_voids) / b / 1000 "
        f"= {_ss['wc']} × ({_ss['b_bottom']}×{_ss['h']} − {_A_voids_total:.0f}) "
        f"/ {_ss['b_bottom']} / 1000 = **{_sw_prev:.3f} kN/m²**"
    )

# =============================================================================
# TAB B — Materials
# =============================================================================
with tab_B:
    section_hdr("B.1", "HCS Concrete Properties")
    st.caption("Ref: ACI 318-19 Eq. 19.2.2.1  Ec = 0.043 × wc^1.5 × sqrt(f'c)  [wc in kg/m³]")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["f_ci"]    = st.number_input("f'ci transfer (MPa)", 20.0, 80.0,  _ss["f_ci"],    1.0, key="_f_ci")
        _ss["f_c_cut"] = st.number_input("f'c at cutting (MPa)",20.0, 80.0,  _ss["f_c_cut"], 1.0, key="_f_c_cut")
    with col2:
        _ss["f_c_del"] = st.number_input("f'c at delivery (MPa)",20.0,80.0,  _ss["f_c_del"], 1.0, key="_f_c_del")
        _ss["f_c_ere"] = st.number_input("f'c at erection (MPa)",20.0,80.0,  _ss["f_c_ere"], 1.0, key="_f_c_ere")
    with col3:
        _ss["f_c"] = st.number_input("f'c 28-day (MPa)", 20.0, 100.0, _ss["f_c"], 1.0, key="_f_c")
        _ss["wc"]  = st.number_input("wc (kN/m³)",       18.0,  30.0, _ss["wc"],  0.5, key="_wc")

    if _ss["has_topping"]:
        st.markdown("---")
        section_hdr("B.1a", "Topping Concrete")
        col1, col2 = st.columns(2)
        with col1:
            _ss["f_c_top"] = st.number_input("f'c_top (MPa)",   17.0, 60.0, _ss["f_c_top"], 1.0, key="_f_c_top")
        with col2:
            _ss["wc_top"]  = st.number_input("wc_top (kN/m³)",  18.0, 30.0, _ss["wc_top"],  0.5, key="_wc_top")
    else:
        st.info("No structural topping selected (set in Tab A).")

    _Ec_h2, _Ec_t2, _nm2 = calc_modular_ratio(_ss["wc"], _ss["f_c"], _ss["wc_top"], _ss["f_c_top"])
    _ss["Ec_hcs"] = _Ec_h2; _ss["Ec_top"] = _Ec_t2; _ss["n_mod"] = _nm2
    st.markdown("---")
    section_hdr("B.1b", "Elastic Moduli (auto)")
    col1, col2, col3 = st.columns(3)
    col1.metric("Ec_HCS", f"{_Ec_h2:.0f} MPa")
    col2.metric("Ec_top",  f"{_Ec_t2:.0f} MPa" if _ss["has_topping"] else "N/A")
    col3.metric("n_mod",   f"{_nm2:.4f}"         if _ss["has_topping"] else "N/A")
    st.markdown("---")

    section_hdr("B.2", "Prestressing Steel")
    _ss["ps_type"] = st.radio(
        "Steel type",
        ["PC Wire (plain/indented)", "7-Wire Strand (low relax)"],
        index=0 if _ss["ps_type"] == "PC Wire (plain/indented)" else 1,
        horizontal=True, key="_ps_type")
    if _ss["ps_type"] == "PC Wire (plain/indented)":
        _ss["wire_dia"] = st.selectbox("Wire dia (mm)", [5.0, 7.0],
                                        index=[5.0, 7.0].index(_ss["wire_dia"]), key="_wire_dia")
        _props = WIRE_PROPS[_ss["wire_dia"]]
    else:
        _ss["strand_size"] = st.selectbox("Strand size", list(STRAND_PROPS.keys()),
                                           index=list(STRAND_PROPS.keys()).index(_ss["strand_size"]),
                                           key="_strand_size")
        _props = STRAND_PROPS[_ss["strand_size"]]
    _ss["ps_area"] = _props["area_mm2"]
    _ss["fpu"]     = _props["fpu_MPa"]
    _ss["fpy"]     = _props["fpy_MPa"]
    _ss["Eps"]     = _props["Eps_MPa"]

    st.markdown("---")
    section_hdr("B.2b", "Tendon Layout")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["n_bot"]     = st.number_input("n_bot",           0, 30,  _ss["n_bot"],     1, key="_n_bot")
        _ss["cover_bot"] = st.number_input("cover_bot (mm)", 15, 100, _ss["cover_bot"], 1, key="_cover_bot")
    with col2:
        _ss["n_top"] = st.number_input("n_top", 0, 20, _ss["n_top"], 1, key="_n_top")
        if _ss["n_top"] > 0:
            _ss["cover_top"] = st.number_input("cover_top (mm)", 15, 100, _ss["cover_top"], 1, key="_cover_top")
    with col3:
        _ss["fpi_pct"] = st.slider("fpi_pct (% fpu)", 70.0, 80.0, _ss["fpi_pct"], 0.5, key="_fpi_pct")

    _Ab = float(_ss["n_bot"]) * float(_ss["ps_area"])
    _At = float(_ss["n_top"]) * float(_ss["ps_area"])
    _fp = _ss["fpi_pct"] / 100.0 * _ss["fpu"]
    _Pi = (_Ab + _At) * _fp / 1000.0
    _db = float(_ss["h"]) - float(_ss["cover_bot"])
    _dt = float(_ss["cover_top"]) if _ss["n_top"] > 0 else 0.0
    _ss["Aps_bot"] = _Ab; _ss["Aps_top"] = _At
    _ss["fpi"] = _fp; _ss["Pi"] = _Pi
    _ss["dp_bot"] = _db; _ss["dp_top"] = _dt
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("Aps_bot", f"{_Ab:.1f}", "mm²")}
        {metric_card("Aps_top", f"{_At:.1f}" if _At > 0 else "—", "mm²")}
        {metric_card("fpi",     f"{_fp:.1f}", "MPa")}
        {metric_card("Pi",      f"{_Pi:.1f}", "kN")}
        {metric_card("dp_bot",  f"{_db:.0f}", "mm")}
        {metric_card("dp_top",  f"{_dt:.0f}" if _dt > 0 else "—", "mm")}
        </div>""", unsafe_allow_html=True)
    st.markdown("---")

    section_hdr("B.3", "Loss Parameters")
    with st.expander("⚙️ Settings (RH, V/S, Assumed Loss)", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            _ss["RH"] = st.slider("RH — Relative Humidity (%)", 40.0, 100.0, _ss["RH"], 1.0, key="_rh")
        with col2:
            _ss["vs_auto"] = st.toggle("Auto-calculate V/S ratio", _ss.get("vs_auto", True), key="_vs_auto")
            if _ss["vs_auto"]:
                _Acvs  = float(_ss["b_bottom"]) * float(_ss["h"]) - _ss["A_voids_total"]
                _pvs   = 2.0 * (float(_ss["b_bottom"]) + float(_ss["h"]))
                _vscal = _Acvs / _pvs if _pvs > 0 else 38.0
                _ss["V_S"] = round(_vscal, 1)
                st.metric("V/S (auto)", f"{_ss['V_S']:.1f} mm")
                st.caption(f"V/S = A_conc / Perimeter = {_Acvs:.0f} / {_pvs:.0f} = {_ss['V_S']:.1f} mm")
            else:
                _ss["V_S"] = st.number_input("V/S (mm) — manual", 20.0, 100.0, _ss["V_S"], 1.0, key="_vs")
        st.markdown("---")
        # Assumed loss input
        _ss["assumed_loss_pct"] = st.number_input(
            "Assumed total prestress loss (%)",
            0.0, 50.0, float(_ss.get("assumed_loss_pct", 20.0)), 0.5,
            help="Initial guess for total loss; actual loss computed below"
        )
    if "pl_total_MPa" in _ss:
        section_hdr("B.3b", "Loss Results (auto)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total loss", f"{_ss['pl_total_MPa']:.1f} MPa")
        col2.metric("Total %",    f"{_ss['pl_total_pct']:.1f} %")
        col3.metric("fse",        f"{_ss['pl_fse']:.1f} MPa")
        st.caption(f"ES={_ss['pl_ES']:.1f} | CR={_ss['pl_CR']:.1f} | "
                   f"SH={_ss['pl_SH']:.1f} | RE={_ss['pl_RE']:.1f} MPa")

        _assumed = _ss.get("assumed_loss_pct", 20.0)
        _actual_pct = _ss.get("pl_total_pct", 0.0)
        _loss_ok = _assumed >= _actual_pct * 0.95  # assumed should be ≥ ~95% of actual
        st.metric("Assumed loss", f"{_assumed:.1f} %",
                  delta=f"vs actual {_actual_pct:.1f}% → {'OK' if _loss_ok else 'WARNING'}",
                  delta_color="normal" if _loss_ok else "inverse")
        st.success(f"Effective prestress force Pe = {_ss['pl_Pe']:.1f} kN")

# =============================================================================
# TAB C — Span
# =============================================================================
with tab_C:
    section_hdr("C.1", "Span & Support Geometry")
    st.caption(
        "L_clear = L_cc − ½·bw_beam_L − ½·bw_beam_R  |  "
        "L_an = L_clear + ½·b_bear_L + ½·b_bear_R"
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["L_cc"] = st.number_input("L_cc — centre-to-centre (mm)",
                                       1000, 30000, int(_ss["L_cc"]), 100, key="_L_cc")
    with col2:
        _ss["bw_beam_L"] = st.number_input(
            "bw_beam_L — left beam width (mm)", 100, 2000,
            int(_ss["bw_beam_L"]), 50, key="_bw_beam_L")
        st.caption("Width of left supporting beam (for L_clear & bearing detail)")
    with col3:
        _ss["bw_beam_R"] = st.number_input(
            "bw_beam_R — right beam width (mm)", 100, 2000,
            int(_ss["bw_beam_R"]), 50, key="_bw_beam_R")
        st.caption("Width of right supporting beam")

    st.markdown("---")
    section_hdr("C.2", "Bearing Width")
    col1, col2 = st.columns(2)
    with col1:
        _ss["b_bear_L"] = st.number_input("b_bear_L — left bearing (mm)",  50, 500,
                                           int(_ss["b_bear_L"]), 5, key="_b_bear_L")
    with col2:
        _ss["b_bear_R"] = st.number_input("b_bear_R — right bearing (mm)", 50, 500,
                                           int(_ss["b_bear_R"]), 5, key="_b_bear_R")

    _Lcl2 = float(_ss["L_cc"]) - float(_ss["bw_beam_L"]) / 2.0 - float(_ss["bw_beam_R"]) / 2.0
    _Lan2 = _Lcl2 + float(_ss["b_bear_L"]) / 2.0 + float(_ss["b_bear_R"]) / 2.0
    _bm2  = max(_Lcl2 / 180.0, 50.8)
    _ss["L_clear"] = _Lcl2; _ss["L_an"] = _Lan2; _ss["bear_min"] = _bm2

    _panel_gap = float(_ss["b_nominal"]) - float(_ss["b_bottom"])
    _bear_avail_L = (float(_ss["bw_beam_L"]) - _panel_gap) / 2.0
    _bear_avail_R = (float(_ss["bw_beam_R"]) - _panel_gap) / 2.0

    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("L_cc",       f"{_ss['L_cc']:.0f}",    "mm")}
        {metric_card("L_clear",    f"{_Lcl2:.0f}",          "mm")}
        {metric_card("L_an",       f"{_Lan2:.0f}",          "mm")}
        {metric_card("bear_min",   f"{_bm2:.1f}",           "mm")}
        {metric_card("Bear avail L",f"{_bear_avail_L:.1f}", "mm")}
        {metric_card("Bear avail R",f"{_bear_avail_R:.1f}", "mm")}
        </div>""", unsafe_allow_html=True)
    st.caption(
        "Bearing length available = (bw_beam − panel_gap) / 2"
        f"  |  panel_gap = b_nominal − b_bottom = {_panel_gap:.0f} mm"
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("L_clear", f"{_Lcl2:.0f} mm")
    col2.metric("b_bear_L", f"{_ss['b_bear_L']} mm",
                delta="OK" if _ss["b_bear_L"] >= _bm2 else f"Short by {_bm2 - _ss['b_bear_L']:.1f} mm",
                delta_color="normal" if _ss["b_bear_L"] >= _bm2 else "inverse")
    col3.metric("b_bear_R", f"{_ss['b_bear_R']} mm",
                delta="OK" if _ss["b_bear_R"] >= _bm2 else f"Short by {_bm2 - _ss['b_bear_R']:.1f} mm",
                delta_color="normal" if _ss["b_bear_R"] >= _bm2 else "inverse")
    st.markdown("---")
    section_hdr("C.3", "Transfer & Development Length")
    col1, col2, col3 = st.columns(3)
    col1.metric("l_t",  f"{_ss['lb_l_t']:.0f} mm")
    col2.metric("l_d",  f"{_ss['lb_l_d']:.0f} mm")
    col3.metric("d_ps", f"{get_ps_diameter_mm():.1f} mm")
    _pscls = "ok" if _ss["lb_ps_status"] == "FULL" else "warn" if _ss["lb_ps_status"] == "PARTIAL" else "err"
    st.markdown(f'<span class="badge-{_pscls}">{_ss["lb_ps_status"]} — {_ss["lb_ps_message"]}</span>',
                unsafe_allow_html=True)

# =============================================================================
# TAB D — Loads
# (Sama seperti sebelumnya, hanya perbaikan satuan grafik)
# =============================================================================
with tab_D:
    section_hdr("D.1", "Self-Weight (auto from Tab A & B)")
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("SW_HCS",     f"{_ss['SW_HCS']:.3f}",     "kN/m²")}
        {metric_card("SW_topping", f"{_ss['SW_topping']:.3f}" if _ss['has_topping'] else "—", "kN/m²")}
        {metric_card("SW_total",   f"{_ss['SW_HCS']+_ss['SW_topping']:.3f}", "kN/m²")}
        </div>""", unsafe_allow_html=True)
    st.caption(
        f"SW_HCS = wc × (b×h − A_voids) / b / 1000 = "
        f"{_ss['wc']} × ({_ss['b_bottom']}×{_ss['h']} − {_A_voids_total:.0f}) "
        f"/ {_ss['b_bottom']} / 1000 = **{_ss['SW_HCS']:.3f} kN/m²**"
    )
    st.markdown("---")

    section_hdr("D.2", "Area Loads — Superimposed Dead & Live")
    st.caption("Default load factors: ASCE 7 / ACI 318-19 Table 5.3.1.")
    col1, col2, col3 = st.columns([3, 1, 3])
    with col1:
        _ss["SDL"] = st.number_input("SDL — Superimposed Dead Load (kN/m²)",
                                      0.0, 50.0, float(_ss["SDL"]), 0.25, key="_SDL")
    with col2:
        st.markdown("**LF SDL:**")
        _ss["lf_SDL"] = st.number_input("γ_SDL", 1.0, 2.5, float(_ss["lf_SDL"]), 0.05, key="_lf_SDL")
    with col3:
        st.markdown(f"*Factored SDL = {_ss['lf_SDL']:.2f} × {_ss['SDL']:.2f} = "
                    f"**{_ss['lf_SDL']*_ss['SDL']:.3f} kN/m²***")
    col1, col2, col3 = st.columns([3, 1, 3])
    with col1:
        _ss["LL"] = st.number_input("LL — Live Load (kN/m²)",
                                     0.0, 100.0, float(_ss["LL"]), 0.25, key="_LL")
    with col2:
        st.markdown("**LF LL:**")
        _ss["lf_LL"] = st.number_input("γ_LL", 1.0, 2.5, float(_ss["lf_LL"]), 0.05, key="_lf_LL")
    with col3:
        st.markdown(f"*Factored LL = {_ss['lf_LL']:.2f} × {_ss['LL']:.2f} = "
                    f"**{_ss['lf_LL']*_ss['LL']:.3f} kN/m²***")
    _wu_disp = (_ss["lf_DL"] * (_ss["SW_HCS"] + _ss["SW_topping"])
                + _ss["lf_SDL"] * _ss["SDL"]
                + _ss["lf_LL"]  * _ss["LL"])
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("wu (user LF)", f"{_wu_disp:.3f}", "kN/m²")}
        </div>""", unsafe_allow_html=True)
    st.caption(
        f"wu = γ_DL×(SW_HCS+SW_top) + γ_SDL×SDL + γ_LL×LL = "
        f"{_ss['lf_DL']:.2f}×({_ss['SW_HCS']:.3f}+{_ss['SW_topping']:.3f}) + "
        f"{_ss['lf_SDL']:.2f}×{_ss['SDL']:.2f} + {_ss['lf_LL']:.2f}×{_ss['LL']:.2f} = "
        f"**{_wu_disp:.3f} kN/m²**"
    )
    st.markdown("---")

    section_hdr("D.3", "Dead Load Factor (for Self-Weight)")
    col1, col2 = st.columns(2)
    with col1:
        _ss["lf_DL"] = st.number_input("γ_DL — factor for SW_HCS & SW_topping",
                                        1.0, 2.5, float(_ss["lf_DL"]), 0.05, key="_lf_DL")
    with col2:
        st.metric("Factored SW_total",
                  f"{_ss['lf_DL'] * (_ss['SW_HCS'] + _ss['SW_topping']):.3f} kN/m²")
    st.markdown("---")

    section_hdr("D.4", "Line Load Along Span (Longitudinal)")
    st.caption("Use for partition walls or beams running **parallel to the HCS span**.\n"
               "For a wall **perpendicular to span** (transverse): enter as equivalent Point Load below.")
    _ss["has_line_load"] = st.checkbox("Line load present?", _ss["has_line_load"], key="_has_line_load")
    if _ss["has_line_load"]:
        col1, col2, col3 = st.columns([3, 1, 3])
        with col1:
            _ss["w_line_DL"] = st.number_input("w_line_DL — Dead line load (kN/m)",
                                                0.0, 500.0, float(_ss["w_line_DL"]), 0.5, key="_w_line_DL")
            st.caption("e.g. partition wall along span")
        with col2:
            st.markdown("**LF:**")
            _ss["lf_line_DL"] = st.number_input("γ_lineDL", 1.0, 2.5,
                                                  float(_ss["lf_line_DL"]), 0.05, key="_lf_line_DL")
        with col3:
            _ss["w_line_LL"] = st.number_input("w_line_LL — Live line load (kN/m)",
                                                0.0, 500.0, float(_ss["w_line_LL"]), 0.5, key="_w_line_LL")
        col1, col2, col3 = st.columns([3, 1, 3])
        with col1:
            _ss["x_line_start"] = st.number_input("x_line_start — Start from left support (mm)",
                                                  0, int(_L_an), int(_ss["x_line_start"]), 50, key="_x_line_start")
        with col2:
            st.markdown("**LF LL:**")
            _ss["lf_line_LL"] = st.number_input("γ_lineLL", 1.0, 2.5,
                                                  float(_ss["lf_line_LL"]), 0.05, key="_lf_line_LL")
        with col3:
            _x_end_max_w = int(_L_an * 1.1)
            _x_end_val_w = min(int(_ss.get("x_line_end", int(_L_an))), _x_end_max_w)
            _ss["x_line_end"] = st.number_input("x_line_end — End position from left (mm)",
                                                0, _x_end_max_w, _x_end_val_w, 50, key="_x_line_end")
        _wu_line_show = _ss["lf_line_DL"] * _ss["w_line_DL"] + _ss["lf_line_LL"] * _ss["w_line_LL"]
        _line_len_m   = (float(_ss["x_line_end"]) - float(_ss["x_line_start"])) / 1000.0
        st.markdown(
            f"""<div class="metric-grid">
            {metric_card("w_line factored", f"{_wu_line_show:.2f}", "kN/m")}
            {metric_card("Active length",   f"{max(_line_len_m,0):.2f}", "m")}
            {metric_card("Total line force",f"{_wu_line_show*max(_line_len_m,0):.1f}", "kN")}
            </div>""", unsafe_allow_html=True)
    else:
        _ss["w_line_DL"] = 0.0; _ss["w_line_LL"] = 0.0
        st.info("No longitudinal line load. For transverse wall → use Point Loads section.")
    st.markdown("---")

    section_hdr("D.5", "Point Loads")
    _ss["has_point_load"] = st.checkbox("Point loads present?", _ss["has_point_load"], key="_has_point_load")
    if _ss["has_point_load"]:
        st.caption("P1 & P2 = concentrated loads (kN). x = distance from left support (mm).")
        st.markdown("**Load P1**")
        col1, col2, col3, col4, col5 = st.columns([3, 1, 3, 1, 3])
        with col1:
            _ss["P1_DL"] = st.number_input("P1_DL (kN)", 0.0, step=0.5, value=float(_ss["P1_DL"]), key="_P1_DL")
        with col2:
            _ss["lf_P1DL"] = st.number_input("γ", 1.0, 2.5, float(_ss["lf_P1DL"]), 0.05, key="_lf_P1DL")
        with col3:
            _ss["P1_LL"] = st.number_input("P1_LL (kN)", 0.0, step=0.5, value=float(_ss["P1_LL"]), key="_P1_LL")
        with col4:
            _ss["lf_P1LL"] = st.number_input("γ ", 1.0, 2.5, float(_ss["lf_P1LL"]), 0.05, key="_lf_P1LL")
        with col5:
            _ss["x_P1"] = st.number_input("x_P1 (mm)", 0, step=50, value=int(_ss["x_P1"]), key="_x_P1")
        st.caption(f"Pu1 = {_ss['lf_P1DL']:.2f}×{_ss['P1_DL']:.1f} + {_ss['lf_P1LL']:.2f}×{_ss['P1_LL']:.1f} "
                   f"= **{_ss['lf_P1DL']*_ss['P1_DL']+_ss['lf_P1LL']*_ss['P1_LL']:.1f} kN** (before eff. width factor)")

        st.markdown("**Load P2**")
        col1, col2, col3, col4, col5 = st.columns([3, 1, 3, 1, 3])
        with col1:
            _ss["P2_DL"] = st.number_input("P2_DL (kN)", 0.0, step=0.5, value=float(_ss["P2_DL"]), key="_P2_DL")
        with col2:
            _ss["lf_P2DL"] = st.number_input("γ  ", 1.0, 2.5, float(_ss["lf_P2DL"]), 0.05, key="_lf_P2DL")
        with col3:
            _ss["P2_LL"] = st.number_input("P2_LL (kN)", 0.0, step=0.5, value=float(_ss["P2_LL"]), key="_P2_LL")
        with col4:
            _ss["lf_P2LL"] = st.number_input("γ   ", 1.0, 2.5, float(_ss["lf_P2LL"]), 0.05, key="_lf_P2LL")
        with col5:
            _ss["x_P2"] = st.number_input("x_P2 (mm)", 0, step=50, value=int(_ss["x_P2"]), key="_x_P2")
        _ss["slab_position"] = st.radio(
            "Slab position (for effective width reduction — PCI Fig. 4.10.1.1)",
            ["Interior slab", "Edge slab"],
            index=0 if _ss["slab_position"] == "Interior slab" else 1,
            horizontal=True, key="_slab_position")
    st.markdown("---")

    section_hdr("D.6", "Factored Load Summary (auto)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("wu (kN/m²)",   f"{_ss.get('lb_wu_area', 0):.3f}")
    col2.metric("Vu_max (kN)",  f"{_ss.get('lb_Vu_max',  0):.2f}")
    col3.metric("Mu_max (kN·m)",f"{_ss.get('lb_Mu_max',  0)/1e6:.2f}")
    col4.metric("Ra (kN)",      f"{_ss.get('lb_Ra_u',    0):.2f}")

    if "lb_x_arr" in _ss and len(_ss["lb_x_arr"]) > 1:
        _xm2 = _ss["lb_x_arr"] / 1000.0
        _fig2 = make_subplots(rows=2, cols=1,
                              subplot_titles=("SFD — Shear Force (kN)",
                                              "BMD — Bending Moment (kN·m)"),
                              vertical_spacing=0.18, shared_xaxes=True)
        _fig2.add_trace(go.Scatter(x=_xm2, y=_ss["lb_Vu_arr"],
                                   name="Vu factored", line=dict(color="#1A476F", width=2)),
                        row=1, col=1)
        _fig2.add_trace(go.Scatter(x=_xm2, y=_ss["lb_Mu_arr"] / 1e6,
                                   name="Mu factored", fill="tozeroy",
                                   fillcolor="rgba(26,71,111,0.10)",
                                   line=dict(color="#1A476F", width=2)),
                        row=2, col=1)
        _fig2.update_layout(height=400, margin=dict(l=50, r=20, t=60, b=30),
                            legend=dict(orientation="h", y=1.08))
        _fig2.update_xaxes(title_text="x (m)", row=2, col=1)
        st.plotly_chart(_fig2, use_container_width=True)

# =============================================================================
# TAB E — Seismic  (FIX-3 Addition 4: ACI/PCI 319-25 Sec. 12 detail)
# =============================================================================
with tab_E:
    section_hdr("E.1", "Seismic Design Category")
    _sdc_opts = ["A", "B", "C", "D", "E", "F"]
    _ss["sdc"] = st.selectbox("SDC", _sdc_opts, index=_sdc_opts.index(_ss["sdc"]), key="_sdc")

    if _ss["sdc"] in ["D", "E", "F"]:
        st.error(f"SDC {_ss['sdc']}: Special detailing required. "
                 "Untopped HCS diaphragm flexibility MUST be explicitly modelled. "
                 "See ACI/PCI 319-25 Chapter 12.")
        with st.expander("📋 ACI/PCI 319-25 Chapter 12 — Diaphragm Requirements (SDC D/E/F)",
                          expanded=True):
            st.markdown("""
**ACI/PCI CODE-319-25 Chapter 12 — Key Requirements for SDC D, E, and F:**

- **Sec. 12.3 — Diaphragm Flexibility:**
  Untopped HCS diaphragm flexibility must be **explicitly modelled** in the structural
  analysis. The rigid diaphragm assumption is **NOT permitted** for untopped HCS in SDC D/E/F.

- **Sec. 12.4.2 — Minimum Connection Force:**
  Minimum connection force = **0.04 × (floor dead load)** transferred as in-plane shear
  to the lateral force-resisting system. This must be verified for all connections.

- **Sec. 12.5 — Chord and Collector Design:**
  Chord and collector elements are required at **all diaphragm edges** and re-entrant
  corners. Reinforcement must be detailed to develop the required tension/compression.

- **Sec. 12.6 — Grouted Joint Shear:**
  Shear capacity of grouted longitudinal joints shall not exceed **0.55 MPa**
  (≈ 80 psi) per unit area of joint. Additional shear ties may be required.

- **ACI CODE-550.5:**
  Connection validation by **physical testing** is required for SDC D/E/F untopped HCS.
  Reliance on calculation alone is not permitted without test data.

- **Reference:** ACI/PCI CODE-319-25 Chapter 12 | ACI CODE-550.5 |
  PCI Design Handbook 8th Ed. Sec. 3.4

> ⚠️ **Engineer of record must verify all diaphragm assumptions.**
""")
    elif _ss["sdc"] == "C":
        st.warning("SDC C: Intermediate seismic requirements apply. "
                   "Check ACI/PCI 319-25 Chapter 12 for applicable provisions.")
    else:
        st.success(f"SDC {_ss['sdc']}: Standard provisions apply (ACI/PCI 319-25).")

    st.markdown("---")

    section_hdr("E.2", "Structural Integrity Ties")
    st.markdown("""
**Structural Integrity Ties per ACI/PCI CODE-319-25 Sec. 16.5:**

These tie requirements apply to **ALL SDC categories**:

| Tie Type | Minimum Requirement |
|---|---|
| **Longitudinal ties** | ≥ 0.9 kN per metre of floor width |
| **Transverse ties** | ≥ 0.9 kN per metre of floor length |
| **Peripheral ties** | ≥ 70 kN total force (around floor perimeter) |

> **Ref: ACI/PCI CODE-319-25 Sec. 16.5**
>
> Connections between HCS units and supporting members must be designed and detailed
> to transfer these forces under gravity and lateral load combinations.
""")

# =============================================================================
# TAB F — Section Properties
# =============================================================================
with tab_F:
    st.markdown("## F · Section Properties")
    st.caption("Ref: ACI/PCI 319-25 Cl. 26.12 | Full step-by-step in Report")
    section_hdr("F.1", "Gross Section")
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("Ag",   f"{_ss.get('sp_Ag',0):,.0f}",     "mm²")}
        {metric_card("yb_g", f"{_ss.get('sp_yb_g',0):.1f}",    "mm")}
        {metric_card("Ig",   f"{_ss.get('sp_Ig',0)/1e6:.3f}",  "×10⁶ mm⁴")}
        </div>""", unsafe_allow_html=True)
    section_hdr("F.2", "Net HCS Section")
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("An",    f"{_ss.get('sp_An',0):,.0f}",    "mm²")}
        {metric_card("yb",    f"{_ss.get('sp_yb',0):.2f}",     "mm")}
        {metric_card("In",    f"{_ss.get('sp_In',0)/1e6:.3f}", "×10⁶ mm⁴")}
        {metric_card("e_bot", f"{_ss.get('sp_e_bot',0):.2f}",  "mm")}
        </div>""", unsafe_allow_html=True)
    section_hdr("F.3", "Composite Section")
    if _ss.get("has_topping") and _ss.get("t_topping", 0) > 0:
        st.markdown(
            f"""<div class="metric-grid">
            {metric_card("A_comp",  f"{_ss.get('sp_A_comp',0):,.0f}",    "mm²")}
            {metric_card("yb_comp", f"{_ss.get('sp_yb_comp',0):.2f}",    "mm")}
            {metric_card("I_comp",  f"{_ss.get('sp_I_comp',0)/1e6:.3f}", "×10⁶ mm⁴")}
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No topping → composite section = net HCS section.")

# =============================================================================
# TAB G — Stress Checks
# =============================================================================
with tab_G:
    st.markdown("## G · Stress Checks")
    st.caption("Ref: ACI/PCI 319-25 Table 24.5.3.1 | Sign: compression (−), tension (+)")
    if "sc_transfer" not in _ss:
        st.info("Calculating stress checks...")
    else:
        for _skey, _stitle in [
            ("sc_transfer",    "Transfer / Release"),
            ("sc_lifting",     "Lifting (after ES)"),
            ("sc_construction","Construction (wet topping, non-composite)"),
            ("sc_service",     f"Service (composite, class {_ss.get('sc_service_class','T')})"),
        ]:
            _sd = _ss.get(_skey, {})
            if not _sd:
                continue
            st.markdown(f"### {_stitle}")
            col1, col2 = st.columns(2)
            col1.metric("Top fiber",    f"{_sd.get('f_top',0):.2f} MPa")
            col2.metric("Bottom fiber", f"{_sd.get('f_bot',0):.2f} MPa")
            st.caption(f"Limit comp: {_sd.get('limit_comp',0):.1f} MPa  |  "
                       f"Limit tens: {_sd.get('limit_tens',0):.2f} MPa  |  "
                       f"Status: **{_sd.get('status','—')}**")
        _svsv = _ss.get("sc_service", {})
        if _svsv.get("status") == "NG":
            st.error("Stress check FAILED. Adjust section or prestress level.")
        else:
            st.success("All stress checks passed.")

# =============================================================================
# TAB H — Capacity
# =============================================================================
with tab_H:
    st.markdown("## H · Flexural & Shear Capacity")
    st.caption("Ref: ACI/PCI 319-25 Cl. 22.2, 22.5, 22.6")
    if "cap_phi_Mn" not in _ss:
        st.info("Calculating capacity...")
    else:
        st.markdown("### Flexural Capacity")
        col1, col2, col3 = st.columns(3)
        col1.metric("fps",  f"{_ss['cap_fps']:.1f} MPa")
        col2.metric("Mn",   f"{_ss['cap_Mn']:.1f} kN·m")
        col3.metric("φMn",  f"{_ss['cap_phi_Mn']:.1f} kN·m")
        st.caption(f"Compression block depth a = {_ss['cap_a']:.1f} mm")
        _DCR_M = _ss["cap_DCR_M"]
        st.metric("DCR_M (Mu/φMn)", f"{_DCR_M:.3f}",
                  delta="OK" if _DCR_M <= 1.0 else "OVERSTRESS",
                  delta_color="normal" if _DCR_M <= 1.0 else "inverse")

        st.markdown("### Shear Capacity")
        col1, col2 = st.columns(2)
        col1.metric("min φVn", f"{_ss['cap_phi_Vn_min']:.1f} kN")
        col2.metric("DCR_V",   f"{_ss['cap_DCR_V']:.3f}")
        if _ss["cap_needs_Av_min"]:
            st.warning("⚠️ h > 317 mm, no topping, Vu > 0.5φVcw → Av,min required per ACI/PCI 319-25 Cl. 9.6.3.")
        else:
            st.info("No minimum shear reinforcement required per ACI/PCI 319-25.")
        if "cap_phi_Vn_arr" in _ss and len(_ss["cap_phi_Vn_arr"]) > 0:
            _xm3 = _ss["lb_x_arr"] / 1000.0
            _fig3 = go.Figure()
            _fig3.add_trace(go.Scatter(x=_xm3, y=_ss["cap_phi_Vn_arr"],
                                       name="φVn (capacity)", line=dict(color="green", width=2)))
            _fig3.add_trace(go.Scatter(x=_xm3, y=abs(_ss["lb_Vu_arr"]),
                                       name="|Vu| (demand)", line=dict(color="red", width=2, dash="dash")))
            _fig3.update_layout(title="Shear Capacity vs. Demand Along Span",
                                xaxis_title="Distance from left support (m)",
                                yaxis_title="Shear (kN)", height=380)
            st.plotly_chart(_fig3, use_container_width=True)

# =============================================================================
# TAB I — Deflection & Camber  (FIX-4 Enhanced)
# =============================================================================
with tab_I:
    st.markdown("## I · Deflection & Camber")
    st.caption(
        "Ref: PCI Design Handbook 8th Ed. Sec. 4.8 & Table 4.8.3  |  "
        "ACI 318-19 Table 24.2.2  |  AISC DG11 (Vibration)"
    )

    # ── I.0  PCI Multipliers (editable) ──────────────────────────────────────
    from hcs.deflection import get_pci_multiplier_defaults
    _has_top_defl = _ss.get("has_topping", False)
    _pci_def = get_pci_multiplier_defaults(_has_top_defl)

    with st.expander("⚙️ PCI Long-Term Multipliers (editable)", expanded=False):
        st.caption(
            "Defaults: PCI Design Handbook 8th Ed. Table 4.8.3. "
            "Modify only with engineering judgment."
        )
        _top_label = "WITH topping" if _has_top_defl else "WITHOUT topping"
        st.markdown(f"**{_top_label}** — currently active defaults:")

        col1, col2, col3 = st.columns(3)
        with col1:
            _ss["mult_camber_erection"] = st.number_input(
                "Camber at erection (×)",
                0.5, 5.0, float(_ss.get("mult_camber_erection", _pci_def["mult_camber_erection"])),
                0.05, key="_mult_camber_erect")
            _ss["mult_dw_erection"] = st.number_input(
                "SW defl at erection (×)",
                0.5, 5.0, float(_ss.get("mult_dw_erection", _pci_def["mult_dw_erection"])),
                0.05, key="_mult_dw_erect")
        with col2:
            _ss["mult_camber_final"] = st.number_input(
                "Final camber (×)",
                0.5, 5.0, float(_ss.get("mult_camber_final", _pci_def["mult_camber_final"])),
                0.05, key="_mult_camber_final")
            _ss["mult_dw_final"] = st.number_input(
                "Final SW deflection (×)",
                0.5, 5.0, float(_ss.get("mult_dw_final", _pci_def["mult_dw_final"])),
                0.05, key="_mult_dw_final")
        with col3:
            _ss["mult_sdl_final"] = st.number_input(
                "Final SDL deflection (×)",
                0.5, 5.0, float(_ss.get("mult_sdl_final", _pci_def["mult_sdl_final"])),
                0.05, key="_mult_sdl_final")
            _ss["mult_ll_final"] = st.number_input(
                "LL deflection factor (×)",
                0.5, 2.0, float(_ss.get("mult_ll_final", _pci_def["mult_ll_final"])),
                0.05, key="_mult_ll_final")

        if st.button("🔄 Reset to PCI Defaults", key="_reset_pci_mult"):
            for _mk, _mv in _pci_def.items():
                _ss[_mk] = _mv
            st.rerun()

        st.markdown(
            "| Stage | Camber | SW defl | SDL | LL |\n"
            "|---|---|---|---|---|\n"
            f"| At erection | ×{_ss.get('mult_camber_erection',1.85):.2f} | "
            f"×{_ss.get('mult_dw_erection',1.85):.2f} | — | — |\n"
            f"| Final | ×{_ss.get('mult_camber_final',2.70):.2f} | "
            f"×{_ss.get('mult_dw_final',2.40):.2f} | "
            f"×{_ss.get('mult_sdl_final',3.00):.2f} | "
            f"×{_ss.get('mult_ll_final',1.00):.2f} |"
        )

    st.markdown("---")

    # ── I.1  Instantaneous results ────────────────────────────────────────────
    section_hdr("I.1", "Instantaneous Deflection at Release")
    if "def_delta_ps_initial" not in _ss:
        st.info("Calculating deflections...")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Prestress camber",      f"{_ss['def_delta_ps_initial']:+.2f} mm  ↑")
        col2.metric("Self-weight defl.",     f"{_ss['def_delta_sw']:+.2f} mm  ↓")
        col3.metric("Net at release",        f"{_ss['def_net_release']:+.2f} mm")
        st.caption(
            "Sign: (+) = upward camber, (−) = downward deflection. "
            "e = eccentricity of PS centroid below section NA."
        )

        st.markdown("---")
        section_hdr("I.2", "Long-term Deflection (Final Stage)")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Final camber",
                    f"{_ss.get('def_final_camber', _ss['def_delta_ps_initial']*2.0):+.2f} mm")
        col2.metric("Final SW defl.",
                    f"{_ss.get('def_final_sw', _ss['def_delta_sw']*2.0):+.2f} mm")
        col3.metric("Final SDL defl.",
                    f"{_ss.get('def_final_sdl', _ss['def_delta_sdl']*3.0):+.2f} mm")
        col4.metric("LL defl. (instantaneous)",
                    f"{_ss.get('def_final_ll', _ss['def_delta_ll']):+.2f} mm")
        st.metric("Total net long-term deflection", f"{_ss['def_total_longterm']:+.2f} mm")

        st.markdown("---")
        section_hdr("I.3", "Code Limit Checks")

        # ── Editable deflection limits ─────────────────────────────────────
        with st.expander("⚙️ Deflection Limits (editable)", expanded=False):
            _struct_opts = [
                "Office floor (L/360 LL, L/240 total)",
                "Warehouse / Factory (L/240 LL, L/180 total)",
                "Roof (L/240 LL, L/180 total)",
                "Custom",
            ]
            _struct_presets = {
                "Office floor (L/360 LL, L/240 total)":          (360, 240),
                "Warehouse / Factory (L/240 LL, L/180 total)":   (240, 180),
                "Roof (L/240 LL, L/180 total)":                   (240, 180),
                "Custom":                                          (None, None),
            }
            _ss["defl_structure_type"] = st.selectbox(
                "Structure type", _struct_opts,
                index=_struct_opts.index(_ss.get("defl_structure_type", _struct_opts[0])),
                key="_defl_struct_type")

            _preset_lls, _preset_tot = _struct_presets[_ss["defl_structure_type"]]
            if _preset_lls is not None:
                _ss["limit_LL_fraction"]    = _preset_lls
                _ss["limit_total_fraction"] = _preset_tot

            col1, col2 = st.columns(2)
            with col1:
                _ss["limit_LL_fraction"] = st.number_input(
                    "L / [n] for LL limit", 100, 1000,
                    int(_ss.get("limit_LL_fraction", 360)), 10, key="_lim_ll_frac")
            with col2:
                _ss["limit_total_fraction"] = st.number_input(
                    "L / [n] for total deflection limit", 100, 1000,
                    int(_ss.get("limit_total_fraction", 240)), 10, key="_lim_tot_frac")

            _L_disp = float(_ss.get("L_an", 5850))
            st.markdown(
                f"**LL limit**    = L / {_ss['limit_LL_fraction']} = "
                f"{_L_disp / _ss['limit_LL_fraction']:.1f} mm  |  "
                f"**Total limit** = L / {_ss['limit_total_fraction']} = "
                f"{_L_disp / _ss['limit_total_fraction']:.1f} mm"
            )

        # Results
        col1, col2, col3 = st.columns(3)
        col1.metric(f"Limit LL  (L/{_ss.get('limit_LL_fraction',360)})",
                    f"{_ss['def_limit_ll_mm']:.1f} mm")
        col2.metric(f"Limit total  (L/{_ss.get('limit_total_fraction',240)})",
                    f"{_ss['def_limit_total_mm']:.1f} mm")
        col3.metric("Actual total (long-term)",
                    f"{_ss['def_total_longterm']:.1f} mm")

        _stll3  = _ss["def_status_ll"]
        _sttot3 = _ss["def_status_total"]
        st.markdown(f"**LL status:** {_stll3}  |  **Total status:** {_sttot3}")
        if _sttot3 == "NG":
            st.error("Total deflection exceeds code limit. Consider increasing depth or prestress.")
        else:
            st.success("Deflection within code limits.")

        st.markdown("---")

        # ── I.3b Thermal camber (FIX-4 Addition 2) ───────────────────────────
        section_hdr("I.3b", "Thermal Camber (optional)")
        _ss["has_thermal"] = st.checkbox(
            "Include temperature differential camber?",
            bool(_ss.get("has_thermal", False)), key="_has_thermal")
        if _ss["has_thermal"]:
            col1, col2 = st.columns(2)
            with col1:
                _ss["delta_T"] = st.number_input(
                    "ΔT — Temperature differential top-to-bottom (°C)",
                    -50.0, 50.0, float(_ss.get("delta_T", 0.0)), 0.5, key="_delta_T")
                st.caption("Positive = top warmer than bottom → upward hogging camber")
            with col2:
                _ss["alpha_T"] = st.number_input(
                    "α_T — Thermal expansion coefficient (per °C)",
                    1e-6, 20e-6, float(_ss.get("alpha_T", 10e-6)),
                    format="%.6f", step=1e-6, key="_alpha_T")
                st.caption("Normal concrete: 10 × 10⁻⁶ /°C")

            _dtherm = _ss.get("def_delta_thermal", 0.0)
            st.markdown(
                f"**Thermal camber formula:** δ_T = α_T × ΔT × L² / (8 × h)  "
                f"= {_ss['alpha_T']:.2e} × {_ss['delta_T']:.1f} × {_ss['L_an']:.0f}² "
                f"/ (8 × {_ss['h']:.0f}) = **{_dtherm:.3f} mm** "
                f"({'upward ↑' if _dtherm >= 0 else 'downward ↓'})"
            )
        else:
            _ss["delta_T"] = 0.0

        st.markdown("---")

    # ── I.4  Natural Frequency & Vibration (FIX-4 Addition 4) ────────────────
    section_hdr("I.4", "Natural Frequency & Vibration Check")
    st.caption(
        "Ref: AISC Design Guide 11 (DG11)  |  ISO 10137:2007  "
        "Simply-supported beam model."
    )

    col1, col2 = st.columns(2)
    with col1:
        _ss["vibration_mode"] = st.selectbox(
            "Occupancy / vibration mode",
            ["Walking / Occupancy", "Machine / Equipment", "Sensitive (Lab/Hospital)"],
            index=["Walking / Occupancy", "Machine / Equipment",
                   "Sensitive (Lab/Hospital)"].index(
                       _ss.get("vibration_mode", "Walking / Occupancy")),
            key="_vib_mode"
        )
    with col2:
        _ss["damping_ratio"] = st.number_input(
            "Damping ratio β (%)",
            0.5, 20.0, float(_ss.get("damping_ratio", 3.0)), 0.5,
            key="_damping_ratio",
            help="Typical: 3% office, 5% partition walls, 2% bare concrete"
        )

    # Vibration results (computed by auto-calc via get_deflection_results)
    _fn_val   = _ss.get("def_vib_fn",    0.0)
    _fn_lim   = _ss.get("def_vib_fn_limit", 8.0)
    _fn_ok    = _ss.get("def_vib_fn_ok", False)
    _ag_val   = _ss.get("def_vib_ag",    0.0)
    _ag_lim   = _ss.get("def_vib_ag_limit", 0.005)
    _ag_ok    = _ss.get("def_vib_ag_ok", False)
    _W_eff    = _ss.get("def_vib_W_eff", 0.0)

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Natural Frequency f_n",
        f"{_fn_val:.2f} Hz",
        delta=f"≥ {_fn_lim:.1f} Hz required → {'OK' if _fn_ok else 'NG'}",
        delta_color="normal" if _fn_ok else "inverse"
    )
    col2.metric(
        "Peak acceleration a/g",
        f"{_ag_val*100:.3f} %",
        delta=f"≤ {_ag_lim*100:.1f}% limit → {'OK' if _ag_ok else 'NG'}",
        delta_color="normal" if _ag_ok else "inverse"
    )
    col3.metric("Effective weight W_eff", f"{_W_eff:.1f} kN")

    if not _fn_ok:
        st.error(
            f"⚠️ Natural frequency f_n = {_fn_val:.2f} Hz < {_fn_lim:.1f} Hz limit "
            f"({_ss.get('vibration_mode','—')}). "
            "Consider increasing section depth, composite action, or adding tuned mass damper."
        )
    if not _ag_ok:
        st.warning(
            f"⚠️ Peak acceleration a/g = {_ag_val*100:.3f}% > {_ag_lim*100:.2f}% limit. "
            "Investigate damping or section stiffness."
        )
    if _fn_ok and _ag_ok:
        st.success("Vibration check passed: f_n and a/g within limits.")

    with st.expander("📐 Vibration Calculation Detail", expanded=False):
        _L_m_vib = _ss.get("def_vib_L_m",    float(_ss.get("L_an", 5850)) / 1000)
        _EI_vib  = _ss.get("def_vib_EI_SI",  0.0)
        _m_vib   = _ss.get("def_vib_W_eff",  0.0) / 9.81 / _L_m_vib if _L_m_vib > 0 else 0.0
        st.markdown(f"""
**Formula:** f_n = (π² / (2L²)) × √(EI / m)  [AISC DG11]

| Parameter | Value |
|---|---|
| Span L | {_L_m_vib:.3f} m |
| EI (composite) | {_EI_vib:.3e} N·m² |
| Mass/length m | {_m_vib:.2f} kg/m |
| Effective weight W_eff | {_W_eff:.1f} kN |
| Damping β | {_ss.get('damping_ratio', 3.0):.1f} % |
| **f_n** | **{_fn_val:.3f} Hz** |
| Limit f_n | {_fn_lim:.1f} Hz |
| **a/g** | **{_ag_val*100:.4f}%** |
| Limit a/g | {_ag_lim*100:.2f}% |

**Peak acceleration:** a/g = P₀ × e^(−2πβ) / W_eff  
P₀ = 0.29 kN (walking excitation, AISC DG11 Table 4.2)  
**Ref:** AISC Design Guide 11 | ISO 10137:2007
""")

# =============================================================================
# TAB J — Report
# =============================================================================
with tab_J:
    st.markdown("## J · Report Generator")
    st.caption("Generate professional calculation report — Word (.docx) or PDF.")
    st.info("Report includes: inputs, span, section props, losses, stress checks, capacity, deflection, SFD/BMD.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Generate Word Report (.docx)", use_container_width=True):
            with st.spinner("Generating Word report..."):
                _wb2, _ = get_report_bytes(_ss)
                if _wb2:
                    st.download_button(
                        label="⬇ Download Word Report", data=_wb2,
                        file_name=f"HCS_Design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True)
                else:
                    st.error("Word generation failed. Check python-docx installation.")
    with col2:
        if st.button("📑 Generate PDF Report", use_container_width=True):
            with st.spinner("Generating PDF report..."):
                _, _pb2 = get_report_bytes(_ss)
                if _pb2:
                    st.download_button(
                        label="⬇ Download PDF Report", data=_pb2,
                        file_name=f"HCS_Design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True)
                else:
                    st.error("PDF generation failed. Check fpdf2/kaleido installation.")
    st.markdown("---")
    st.markdown("""
**Report includes:**
- All inputs (section, materials, span, loads with load factors)
- Transfer & development length
- Section properties (gross, net, composite)
- Prestress losses (ES, CR, SH, RE)
- Stress checks at all stages (transfer, lifting, construction, service)
- Flexural and shear capacity (Mn, Vn, DCR)
- Deflection and camber (initial, long-term, code limits)
- SFD/BMD diagrams
- Code compliance remarks
""")

# =============================================================================
# TAB Summary
# =============================================================================
with tab_sum:
    st.markdown("## Design Summary")
    _ok_geom = _ss.get("geom_valid", False)
    _ok_M2   = _ss.get("cap_DCR_M", 999) <= 1.0
    _ok_V2   = _ss.get("cap_DCR_V", 999) <= 1.0
    _ok_def2 = _ss.get("def_status_total", "NG") == "OK"
    _ok_str2 = all(
        _ss.get(_k2, {}).get("status", "NG") == "OK"
        for _k2 in ["sc_transfer", "sc_lifting", "sc_construction", "sc_service"]
        if _k2 in _ss
    )
    _sum_df = pd.DataFrame({
        "Check": [
            "Geometry valid",   "SW_HCS",
            "L_clear",          "L_an",
            "Prestress dev.",   "Flexure DCR_M",
            "Shear DCR_V",      "Stress checks",
            "Deflection",       "Vibration f_n",
        ],
        "Value": [
            "✅ OK" if _ok_geom else "❌ Fail",
            f"{_ss.get('SW_HCS', 0):.3f} kN/m²",
            f"{_ss.get('L_clear', 0):.0f} mm",
            f"{_ss.get('L_an', 0):.0f} mm",
            _ss.get("lb_ps_status", "—"),
            f"{_ss.get('cap_DCR_M', 999):.3f}  {'✅' if _ok_M2 else '❌'}",
            f"{_ss.get('cap_DCR_V', 999):.3f}  {'✅' if _ok_V2 else '❌'}",
            "✅ All OK" if _ok_str2 else "❌ Fail",
            f"{_ss.get('def_total_longterm', 0):.2f} mm  {'✅' if _ok_def2 else '❌'}",
            f"{_ss.get('def_vib_fn', 0):.2f} Hz  "
            f"{'✅' if _ss.get('def_vib_fn_ok', False) else '❌'}",
        ]
    })
    st.dataframe(_sum_df, use_container_width=True, hide_index=True)
    st.caption("Full step-by-step calculations: use J · Report tab.")
