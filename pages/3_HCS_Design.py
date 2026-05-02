# =============================================================================
# HCS DESIGN APP — Phase 7: Complete (All phases 1-7)
# =============================================================================
# Reference: ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
# Units: SI only (mm, kN, MPa)
# CHANGES vs previous version:
#   - Tab order reorg: A=Section, B=Materials, C=Span, D=Loads, E=Seismic...
#   - HCS Type selector moved to top of Section tab
#   - Preset now triggers st.rerun() reliably
#   - Topping inputs moved to Section tab
#   - Materials tab merged (Concrete + Prestress + Loss params)
#   - SW_HCS formula FIXED: wc[kN/m³] × A_conc[mm²] / b_bottom[mm] / 1e6
#   - Span tab: beam width inputs → correct L_clear & L_an formula
#   - Load tab: load factors editable, line loads added
# =============================================================================

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import math

# hcs imports
from hcs.constants import WIRE_PROPS, STRAND_PROPS, PRESET_TABLE
from hcs.geometry import calc_core_area, calc_h_core, calc_modular_ratio, get_ps_props
from hcs.span_loads import calc_transfer_development_length, check_prestress_development, calc_factored_loads_and_diagrams
from hcs.section_props import get_all_section_props
from hcs.prestress_loss import get_prestress_losses
from hcs.stress_check import get_all_stress_checks
from hcs.capacity import get_capacity_results
from hcs.deflection import get_deflection_results
from hcs.report import get_report_bytes

st.set_page_config(
    page_title="HCS Design — ACI/PCI 319-25",
    page_icon="🏗️", layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================
def init_session_state():
    _default_A_core_1   = 7106.5
    _default_A_voids    = 9 * _default_A_core_1
    _default_h_core     = 120.0
    _default_bw_shear   = 1199 - 9 * 80
    _default_Ec_hcs     = 33000.0
    _default_Ec_top     = 27000.0
    _default_n_mod      = _default_Ec_top / _default_Ec_hcs

    defaults = {
        # Concrete
        "f_ci": 35.0, "f_c_cut": 40.0, "f_c_del": 45.0, "f_c_ere": 50.0,
        "f_c": 50.0,  "wc": 24.0,
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
        # Prestress
        "ps_type": "PC Wire (plain/indented)", "wire_dia": 5.0,
        "strand_size": "1/2 in  (d=11.2mm)", "n_bot": 10, "n_top": 0,
        "cover_bot": 35, "cover_top": 30, "fpi_pct": 75.0,
        "fpu": 1618.0, "fpy": 1432.0, "Eps": 199050.0, "ps_area": 19.6,
        "fpi": 1213.5, "Aps_bot": 196.0, "Aps_top": 0.0,
        "dp_bot": 165.0, "dp_top": 30.0, "Pi": 237.8,
        # Derived geometry
        "A_core_1": _default_A_core_1, "A_voids_total": _default_A_voids,
        "h_core": _default_h_core, "bw_shear": _default_bw_shear,
        # Moduli
        "Ec_hcs": _default_Ec_hcs, "Ec_top": _default_Ec_top, "n_mod": _default_n_mod,
        # Self-weight
        "SW_HCS": 3.52, "SW_topping": 1.44,
        # Span
        "L_cc": 6000, "bw_beam_L": 300, "bw_beam_R": 300,
        "b_bear_L": 150, "b_bear_R": 150,
        "L_clear": 5700.0, "L_an": 5850.0, "bear_min": 50.8,
        "span_type": "Clear span",
        # Loads
        "SDL": 1.5, "LL": 2.0,
        "lf_DL": 1.2, "lf_LL": 1.6,          # load factors (editable)
        "wL_long_DL": 0.0, "wL_long_LL": 0.0, # line load memanjang (kN/m)
        "wL_trans_DL": 0.0, "wL_trans_LL": 0.0,# line load melintang (kN)
        "has_point_load": False,
        "P1_DL": 5.0, "P1_LL": 5.0, "x_P1": 2000,
        "P2_DL": 0.0, "P2_LL": 0.0, "x_P2": 4000,
        "slab_position": "Interior slab",
        # Seismic
        "sdc": "B",
        # Loss parameters
        "RH": 75.0, "V_S": 38.0, "vs_auto": True,
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
    else:
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
    SW_HCS [kN/m²]
    Formula: wc[kN/m³] × A_conc[mm²] / b_bottom[mm] / 1e6
    = wc × (b_bottom×h - A_voids) / b_bottom / 1e6
    Untuk HCS200: 24 × (1199×200-63959) / 1199 / 1e6 ≈ 3.52 kN/m²
    """
    if hcs_type == "Full HCS (Hollow Core)":
        A_conc = b_bottom * h - A_voids_total   # mm²
    else:
        A_conc = b_bottom * h                   # half slab – no voids
    return wc * (A_conc / b_bottom) / 1e6      # kN/m²

def calc_SW_topping(wc_top, t_topping, has_topping):
    """SW_topping [kN/m²] = wc_top[kN/m³] × t_topping[mm] / 1000"""
    if has_topping and t_topping > 0:
        return wc_top * t_topping / 1000.0
    return 0.0

# =============================================================================
# INIT
# =============================================================================
init_session_state()
_ss = st.session_state

# -----------------------------------------------------------------------------
# PRESET GUARD — must run BEFORE tabs are created
# -----------------------------------------------------------------------------
if _ss.get("_preset_applied") != _ss["preset"]:
    apply_preset(_ss["preset"])
    _ss["_preset_applied"] = _ss["preset"]
    st.rerun()

# =============================================================================
# AUTO-CALCULATIONS  (run every rerun so all phases are fresh)
# =============================================================================

# ── Geometry-derived values ──────────────────────────────────────────────────
_A_core_1     = calc_core_area(_ss["core_shape"], _ss["d_core"],
                                _ss["h_straight"], _ss["h_taper"])
_A_voids_total = _ss["n_core"] * _A_core_1
_h_core_val   = calc_h_core(_ss["core_shape"], _ss["d_core"],
                             _ss["h_straight"], _ss["h_taper"])
_bw_shear     = _ss["b_bottom"] - _ss["n_core"] * _ss["d_core"]
_ss["A_core_1"]       = _A_core_1
_ss["A_voids_total"]  = _A_voids_total
_ss["h_core"]         = _h_core_val
_ss["bw_shear"]       = _bw_shear

# ── Elastic moduli ───────────────────────────────────────────────────────────
_Ec_hcs, _Ec_top, _n_mod = calc_modular_ratio(
    _ss["wc"], _ss["f_c"], _ss["wc_top"], _ss["f_c_top"])
_ss["Ec_hcs"] = _Ec_hcs
_ss["Ec_top"] = _Ec_top
_ss["n_mod"]  = _n_mod

# ── SW_HCS — CORRECTED formula ───────────────────────────────────────────────
_SW_HCS = calc_SW_HCS(
    _ss["wc"], _ss["b_bottom"], _ss["h"],
    _A_voids_total, _ss["hcs_type"]
)
_SW_topping = calc_SW_topping(_ss["wc_top"], _ss["t_topping"], _ss["has_topping"])
_ss["SW_HCS"]     = _SW_HCS
_ss["SW_topping"] = _SW_topping

# ── V/S auto ────────────────────────────────────────────────────────────────
if _ss.get("vs_auto", True):
    # V/S = A_net_concrete / perimeter ≈ (b_bottom×h - A_voids) / (2×(b_bottom+h))
    _A_conc_mm2 = _ss["b_bottom"] * _ss["h"] - _A_voids_total
    _perim      = 2 * (_ss["b_bottom"] + _ss["h"])
    _ss["V_S"]  = round(_A_conc_mm2 / _perim, 1) if _perim > 0 else 38.0

# ── Span — L_clear & L_an using beam widths ─────────────────────────────────
# L_clear = L_cc - 1/2*bw_beam_L - 1/2*bw_beam_R
_L_clear = _ss["L_cc"] - _ss["bw_beam_L"] / 2.0 - _ss["bw_beam_R"] / 2.0
# L_an    = L_clear + 1/2*b_bear_L + 1/2*b_bear_R
_L_an    = _L_clear + _ss["b_bear_L"] / 2.0 + _ss["b_bear_R"] / 2.0
_bear_min = max(_L_clear / 180.0, 50.8)
_ss["L_clear"]  = _L_clear
_ss["L_an"]     = _L_an
_ss["bear_min"] = _bear_min

# ── Phase 1B — Transfer & development length ─────────────────────────────────
_fpi   = _ss.get("fpi", _ss["fpu"] * _ss["fpi_pct"] / 100.0)
_d_ps  = get_ps_diameter_mm()
_td    = calc_transfer_development_length(
    ps_type=_ss["ps_type"], d_ps=_d_ps, fpu=_ss["fpu"],
    fpi=_fpi, fpy=_ss.get("fpy", _ss["fpu"] * 0.885),
    assumed_loss_pct=20.0)
for k in ["l_t", "l_d", "fse_est", "fps_est", "method_lt", "loss_note"]:
    _ss[f"lb_{k}"] = _td[k]
_dev = check_prestress_development(_L_an, _td["l_d"])
_ss["lb_ps_status"]  = _dev["status"]
_ss["lb_ps_is_ps"]   = _dev["is_prestressed"]
_ss["lb_ps_message"] = _dev["message"]

# ── Effective line loads including line loads memanjang ──────────────────────
# wL_long (kN/m) is a line load running longitudinally → adds to area load
# Convert: wL_long / b_nominal → kN/m²  (spread over panel width)
_b_nom_m       = _ss["b_nominal"] / 1000.0   # m
_SDL_eff       = (_ss["SDL"]
                  + _ss["wL_long_DL"] / _b_nom_m
                  + _ss["wL_trans_DL"] / (_L_an / 1000.0) / _b_nom_m)
_LL_eff        = (_ss["LL"]
                  + _ss["wL_long_LL"] / _b_nom_m
                  + _ss["wL_trans_LL"] / (_L_an / 1000.0) / _b_nom_m)
_ss["SDL_eff"] = _SDL_eff
_ss["LL_eff"]  = _LL_eff

# ── Phase 1C — Factored load diagrams ────────────────────────────────────────
# Pass user-defined load factors into the module through wu_override approach.
# span_loads.py uses 1.2/1.6 internally; we scale SDL/LL proportionally so
# the module still works. For actual wu we recalculate below.
_ld = calc_factored_loads_and_diagrams(
    L_an=_L_an, b_bottom=_ss["b_bottom"], t_topping=_ss["t_topping"],
    wc=_ss["wc"], wc_top=_ss["wc_top"], has_topping=_ss["has_topping"],
    SW_HCS=_SW_HCS, SW_topping=_SW_topping,
    SDL=_SDL_eff, LL=_LL_eff,
    has_point_load=_ss["has_point_load"],
    P1_DL=_ss["P1_DL"], P1_LL=_ss["P1_LL"], x_P1=_ss["x_P1"],
    P2_DL=_ss["P2_DL"], P2_LL=_ss["P2_LL"], x_P2=_ss["x_P2"],
    slab_position=_ss["slab_position"], N=200)
for k, v in _ld.items():
    _ss[f"lb_{k}"] = v

# Recalculate wu with user-defined LF (informational display)
_wu_user = (_ss["lf_DL"] * (_SW_HCS + _SW_topping + _SDL_eff)
            + _ss["lf_LL"] * _LL_eff)
_ss["lb_wu_user"] = _wu_user

# ── Phase 2 — Section properties ─────────────────────────────────────────────
_sp = get_all_section_props(dict(_ss))
for k, v in _sp.items():
    _ss[f"sp_{k}"] = v

# ── Phase 3 — Prestress losses ────────────────────────────────────────────────
_losses = get_prestress_losses(_ss)
for k, v in _losses.items():
    _ss[k] = v

# ── Phase 4 — Stress checks ───────────────────────────────────────────────────
_stress = get_all_stress_checks(_ss)
for k, v in _stress.items():
    _ss[k] = v

# ── Phase 5 — Capacity ────────────────────────────────────────────────────────
_cap = get_capacity_results(_ss)
for k, v in _cap.items():
    _ss[k] = v

# ── Phase 6 — Deflection ──────────────────────────────────────────────────────
_def = get_deflection_results(_ss)
for k, v in _def.items():
    _ss[k] = v

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
    # Quick summary in sidebar
    if "cap_phi_Mn" in _ss and "cap_DCR_M" in _ss:
        dcr_m = _ss["cap_DCR_M"]
        dcr_v = _ss.get("cap_DCR_V", 999)
        st.markdown(f"**SW_HCS** = `{_ss['SW_HCS']:.3f}` kN/m²")
        st.markdown(f"**L_an** = `{_ss['L_an']:.0f}` mm")
        st.markdown(f"**DCR_M** = `{dcr_m:.3f}` {'✅' if dcr_m<=1.0 else '❌'}")
        st.markdown(f"**DCR_V** = `{dcr_v:.3f}` {'✅' if dcr_v<=1.0 else '❌'}")

# =============================================================================
# TABS — new order
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
# TAB A — Section  (was B, restructured)
# =============================================================================
with tab_A:
    # ── A.0  HCS Type selector — FIRST ──────────────────────────────────────
    section_hdr("A.0", "HCS Type")
    _ss["hcs_type"] = st.radio(
        "HCS Type",
        ["Full HCS (Hollow Core)", "Half Slab (Open Top)"],
        index=0 if _ss["hcs_type"] == "Full HCS (Hollow Core)" else 1,
        horizontal=True, key="_hcs_type"
    )
    if _ss["hcs_type"] == "Half Slab (Open Top)":
        _ss["tf_top"] = 0
        st.info("Half slab: top flange tf_top = 0 (forced).")

    st.markdown("---")

    # ── A.1  Preset selector (depends on HCS Type) ───────────────────────────
    section_hdr("A.1", "Standard Preset")
    if _ss["hcs_type"] == "Full HCS (Hollow Core)":
        preset_keys = list(PRESET_TABLE.keys())
    else:
        # For half slab show only Custom (presets are full HCS only)
        preset_keys = ["Custom (manual input)"]
        st.info("Half Slab: use manual input below. Preset only available for Full HCS.")

    _preset_idx = preset_keys.index(_ss["preset"]) if _ss["preset"] in preset_keys else 0
    preset_choice = st.selectbox(
        "Select preset", preset_keys,
        index=_preset_idx, key="_preset_select"
    )
    if preset_choice != _ss["preset"]:
        _ss["preset"] = preset_choice
        _ss["_preset_applied"] = ""   # force re-apply on next rerun
        st.rerun()

    if preset_choice != "Custom (manual input)":
        st.caption(f"✓ Preset applied: **{preset_choice}**  "
                   f"(h={_ss['h']} mm, d_core={_ss['d_core']} mm, n_core={_ss['n_core']})")

    st.markdown("---")

    # ── A.2  Dimensions ───────────────────────────────────────────────────────
    section_hdr("A.2", "Dimensions")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["b_nominal"] = st.number_input(
            "b_nominal (mm)", 600, 2400, int(_ss["b_nominal"]), 1, key="_b_nominal")
        _ss["b_bottom"] = st.number_input(
            "b_bottom (mm)", 600, 2400, int(_ss["b_bottom"]), 1, key="_b_bottom")
        _ss["b_top"] = st.number_input(
            "b_top (mm)", 600, 2400, int(_ss["b_top"]), 1, key="_b_top")
    with col2:
        _ss["h"] = st.number_input(
            "h HCS (mm)", 80, 600, int(_ss["h"]), 1, key="_h")
        if _ss["hcs_type"] == "Full HCS (Hollow Core)":
            _ss["tf_top"] = st.number_input(
                "tf_top (mm)", 0, 200, int(_ss["tf_top"]), 1, key="_tf_top")
        else:
            st.markdown("**tf_top = 0** (Half Slab)")
        _ss["tf_bot"] = st.number_input(
            "tf_bot (mm)", 10, 200, int(_ss["tf_bot"]), 1, key="_tf_bot")
    with col3:
        # Topping MOVED HERE from Concrete tab
        _ss["has_topping"] = st.checkbox(
            "Structural Topping Present?", _ss["has_topping"], key="_has_topping")
        if _ss["has_topping"]:
            _ss["t_topping"] = st.number_input(
                "t_topping (mm)", 0, 200, int(_ss["t_topping"]), 5, key="_t_topping")
        else:
            _ss["t_topping"] = 0
            st.info("No topping → t_topping = 0")

    st.markdown("---")

    # ── A.3  Core Geometry (only for Full HCS) ────────────────────────────────
    if _ss["hcs_type"] == "Full HCS (Hollow Core)":
        section_hdr("A.3", "Core Geometry")
        col1, col2 = st.columns([1, 2])
        with col1:
            _ss["core_shape"] = st.radio(
                "Core shape",
                ["Circular", "Capsule", "Teardrop"],
                index=["Circular", "Capsule", "Teardrop"].index(_ss["core_shape"]),
                key="_core_shape"
            )
        with col2:
            desc = {
                "Circular": "h_core = d_core (full circle)",
                "Capsule":  "h_core = d_core + h_straight (circle + rectangle)",
                "Teardrop": "h_core = d_core + h_taper (circle + taper)"
            }
            st.info(desc[_ss["core_shape"]])

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _ss["d_core"] = st.number_input(
                "d_core (mm)", 40, 300, int(_ss["d_core"]), 1, key="_d_core")
        with col2:
            _ss["n_core"] = st.number_input(
                "n_core", 1, 20, int(_ss["n_core"]), 1, key="_n_core")
        with col3:
            _ss["gap_side"] = st.number_input(
                "gap_side (mm)", 20, 200, int(_ss["gap_side"]), 1, key="_gap_side")
        with col4:
            _ss["gap_between"] = st.number_input(
                "gap_between (mm)", 10, 200, int(_ss["gap_between"]), 1, key="_gap_between")

        if _ss["core_shape"] == "Capsule":
            _ss["h_straight"] = st.number_input(
                "h_straight (mm)", 0, 400, int(_ss["h_straight"]), 5, key="_h_straight")
        if _ss["core_shape"] == "Teardrop":
            _ss["h_taper"] = st.number_input(
                "h_taper (mm)", 0, 400, int(_ss["h_taper"]), 5, key="_h_taper")

        # Update derived values immediately for display
        _A1   = calc_core_area(_ss["core_shape"], _ss["d_core"],
                               _ss["h_straight"], _ss["h_taper"])
        _Av   = _ss["n_core"] * _A1
        _hc   = calc_h_core(_ss["core_shape"], _ss["d_core"],
                            _ss["h_straight"], _ss["h_taper"])
        _bws  = _ss["b_bottom"] - _ss["n_core"] * _ss["d_core"]
        _ss["A_core_1"] = _A1
        _ss["A_voids_total"] = _Av
        _ss["h_core"] = _hc
        _ss["bw_shear"] = _bws

        st.markdown(
            f"""<div class="metric-grid">
            {metric_card("h_core",       f"{_hc:.1f}",    "mm")}
            {metric_card("A_core_1",     f"{_A1:,.0f}",   "mm²")}
            {metric_card("A_voids_total",f"{_Av:,.0f}",   "mm²")}
            {metric_card("bw_shear",     f"{_bws:.0f}",   "mm")}
            </div>""",
            unsafe_allow_html=True
        )
        st.markdown("---")
    else:
        # Half slab — no voids
        _ss["core_shape"]    = "Circular"
        _ss["A_core_1"]      = 0.0
        _ss["A_voids_total"] = 0.0
        _ss["h_core"]        = 0.0
        _ss["bw_shear"]      = _ss["b_bottom"]
        st.info("Half Slab: no core voids. bw_shear = b_bottom.")

    # ── A.4  Geometry Validation ──────────────────────────────────────────────
    section_hdr("A.4", "Geometry Validation")
    _hc_disp = _ss["h_core"]
    h_check  = _ss["tf_top"] + _hc_disp + _ss["tf_bot"]
    chk1_ok  = abs(h_check - _ss["h"]) < 1.0
    w_used   = (2 * _ss["gap_side"]
                + _ss["n_core"] * _ss["d_core"]
                + (_ss["n_core"] - 1) * _ss["gap_between"])
    chk2_ok  = w_used <= _ss["b_bottom"]
    chk3_ok  = _ss["gap_between"] >= 25

    # SW_HCS live preview
    _sw_prev = calc_SW_HCS(
        _ss["wc"], _ss["b_bottom"], _ss["h"],
        _ss["A_voids_total"], _ss["hcs_type"]
    )
    _sw_top_prev = calc_SW_topping(_ss["wc_top"], _ss["t_topping"], _ss["has_topping"])

    badges = ""
    if _ss["hcs_type"] == "Full HCS (Hollow Core)":
        badges += badge_html(
            f"Flange+core: {h_check:.1f} mm (h={_ss['h']})",
            "OK" if chk1_ok else "ERR") + "  "
        badges += badge_html(
            f"Width fit: {w_used} ≤ {_ss['b_bottom']}",
            "OK" if chk2_ok else "WARN") + "  "
        badges += badge_html(
            "gap_between ≥ 25 mm",
            "OK" if chk3_ok else "WARN")
    else:
        badges = badge_html("Half slab — no core validation needed", "OK")

    st.markdown(badges, unsafe_allow_html=True)
    _ss["geom_valid"] = (chk1_ok and chk2_ok and chk3_ok
                         if _ss["hcs_type"] == "Full HCS (Hollow Core)" else True)

    # Live SW preview box
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("SW_HCS (live)",    f"{_sw_prev:.3f}",     "kN/m²")}
        {metric_card("SW_topping (live)",f"{_sw_top_prev:.3f}", "kN/m²")}
        {metric_card("SW_total (live)",  f"{_sw_prev+_sw_top_prev:.3f}", "kN/m²")}
        </div>""",
        unsafe_allow_html=True
    )
    st.caption(
        "Formula: SW_HCS = wc × (b×h − A_voids) / b / 1e6  "
        f"= {_ss['wc']} × ({_ss['b_bottom']}×{_ss['h']} − {_ss['A_voids_total']:.0f}) "
        f"/ {_ss['b_bottom']} / 1e6 = **{_sw_prev:.3f} kN/m²**"
    )

# =============================================================================
# TAB B — Materials  (merged: Concrete + Prestress + Loss params)
# =============================================================================
with tab_B:

    # ── B.1  Concrete ─────────────────────────────────────────────────────────
    section_hdr("B.1", "HCS Concrete Properties")
    st.caption("Ref: ACI 318-19 Eq. 19.2.2.1  Ec = 0.043 × wc^1.5 × √f'c  [wc in kg/m³]")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["f_ci"]    = st.number_input("f'ci transfer (MPa)",  20.0, 80.0,  _ss["f_ci"],    1.0, key="_f_ci")
        _ss["f_c_cut"] = st.number_input("f'c cut (MPa)",        20.0, 80.0,  _ss["f_c_cut"], 1.0, key="_f_c_cut")
    with col2:
        _ss["f_c_del"] = st.number_input("f'c delivery (MPa)",   20.0, 80.0,  _ss["f_c_del"], 1.0, key="_f_c_del")
        _ss["f_c_ere"] = st.number_input("f'c erection (MPa)",   20.0, 80.0,  _ss["f_c_ere"], 1.0, key="_f_c_ere")
    with col3:
        _ss["f_c"] = st.number_input("f'c 28-day (MPa)", 20.0, 100.0, _ss["f_c"],  1.0, key="_f_c")
        _ss["wc"]  = st.number_input("wc (kN/m³)",       18.0,  30.0, _ss["wc"],   0.5, key="_wc")

    # Topping concrete (only if has_topping set in Tab A)
    if _ss["has_topping"]:
        st.markdown("---")
        section_hdr("B.1a", "Topping Concrete")
        col1, col2 = st.columns(2)
        with col1:
            _ss["f_c_top"] = st.number_input(
                "f'c_top (MPa)", 17.0, 60.0, _ss["f_c_top"], 1.0, key="_f_c_top")
        with col2:
            _ss["wc_top"] = st.number_input(
                "wc_top (kN/m³)", 18.0, 30.0, _ss["wc_top"], 0.5, key="_wc_top")
    else:
        st.info("No structural topping selected (set in Tab A · Section).")

    # Compute & display moduli
    _Ec_h, _Ec_t, _nm = calc_modular_ratio(
        _ss["wc"], _ss["f_c"], _ss["wc_top"], _ss["f_c_top"])
    _ss["Ec_hcs"] = _Ec_h
    _ss["Ec_top"] = _Ec_t
    _ss["n_mod"]  = _nm
    st.markdown("---")
    section_hdr("B.1b", "Elastic Moduli (auto)")
    col1, col2, col3 = st.columns(3)
    col1.metric("Ec_HCS", f"{_Ec_h:.0f} MPa")
    col2.metric("Ec_top",  f"{_Ec_t:.0f} MPa" if _ss["has_topping"] else "N/A")
    col3.metric("n_mod",   f"{_nm:.4f}"        if _ss["has_topping"] else "N/A")

    st.markdown("---")

    # ── B.2  Prestressing Steel ───────────────────────────────────────────────
    section_hdr("B.2", "Prestressing Steel")
    _ss["ps_type"] = st.radio(
        "Steel type",
        ["PC Wire (plain/indented)", "7-Wire Strand (low relax)"],
        index=0 if _ss["ps_type"] == "PC Wire (plain/indented)" else 1,
        horizontal=True, key="_ps_type"
    )
    if _ss["ps_type"] == "PC Wire (plain/indented)":
        _ss["wire_dia"] = st.selectbox(
            "Wire dia (mm)", [5.0, 7.0],
            index=[5.0, 7.0].index(_ss["wire_dia"]), key="_wire_dia")
        props = WIRE_PROPS[_ss["wire_dia"]]
    else:
        _ss["strand_size"] = st.selectbox(
            "Strand size", list(STRAND_PROPS.keys()),
            index=list(STRAND_PROPS.keys()).index(_ss["strand_size"]),
            key="_strand_size")
        props = STRAND_PROPS[_ss["strand_size"]]

    _ss["ps_area"] = props["area_mm2"]
    _ss["fpu"]     = props["fpu_MPa"]
    _ss["fpy"]     = props["fpy_MPa"]
    _ss["Eps"]     = props["Eps_MPa"]

    st.markdown("---")
    section_hdr("B.2b", "Tendon Layout")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["n_bot"]     = st.number_input("n_bot",           0, 30, _ss["n_bot"],     1, key="_n_bot")
        _ss["cover_bot"] = st.number_input("cover_bot (mm)", 15, 100, _ss["cover_bot"], 1, key="_cover_bot")
    with col2:
        _ss["n_top"] = st.number_input("n_top", 0, 20, _ss["n_top"], 1, key="_n_top")
        if _ss["n_top"] > 0:
            _ss["cover_top"] = st.number_input(
                "cover_top (mm)", 15, 100, _ss["cover_top"], 1, key="_cover_top")
    with col3:
        _ss["fpi_pct"] = st.slider("fpi_pct (% fpu)", 70.0, 80.0, _ss["fpi_pct"], 0.5, key="_fpi_pct")

    _Aps_bot = _ss["n_bot"] * _ss["ps_area"]
    _Aps_top = _ss["n_top"] * _ss["ps_area"]
    _fpi_val = _ss["fpi_pct"] / 100.0 * _ss["fpu"]
    _Pi_val  = (_Aps_bot + _Aps_top) * _fpi_val / 1000.0
    _dp_bot  = _ss["h"] - _ss["cover_bot"]
    _dp_top  = _ss["cover_top"] if _ss["n_top"] > 0 else 0
    _ss["Aps_bot"] = _Aps_bot
    _ss["Aps_top"] = _Aps_top
    _ss["fpi"]     = _fpi_val
    _ss["Pi"]      = _Pi_val
    _ss["dp_bot"]  = _dp_bot
    _ss["dp_top"]  = _dp_top

    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("Aps_bot", f"{_Aps_bot:.1f}", "mm²")}
        {metric_card("Aps_top", f"{_Aps_top:.1f}" if _Aps_top > 0 else "—", "mm²")}
        {metric_card("fpi",     f"{_fpi_val:.1f}", "MPa")}
        {metric_card("Pi",      f"{_Pi_val:.1f}",  "kN")}
        {metric_card("dp_bot",  f"{_dp_bot:.0f}",  "mm")}
        {metric_card("dp_top",  f"{_dp_top:.0f}" if _dp_top > 0 else "—", "mm")}
        </div>""",
        unsafe_allow_html=True
    )

    st.markdown("---")

    # ── B.3  Loss Parameters ──────────────────────────────────────────────────
    section_hdr("B.3", "Loss Parameters")
    with st.expander("⚙️ Settings (RH, V/S)", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            _ss["RH"] = st.slider("RH — Relative Humidity (%)", 40.0, 100.0,
                                  _ss["RH"], 1.0, key="_rh")
        with col2:
            _ss["vs_auto"] = st.toggle("Auto-calculate V/S ratio", _ss.get("vs_auto", True),
                                        key="_vs_auto")
            if _ss["vs_auto"]:
                _A_conc_vs = _ss["b_bottom"] * _ss["h"] - _ss["A_voids_total"]
                _perim_vs  = 2 * (_ss["b_bottom"] + _ss["h"])
                _vs_calc   = _A_conc_vs / _perim_vs if _perim_vs > 0 else 38.0
                _ss["V_S"] = round(_vs_calc, 1)
                st.metric("V/S (auto)", f"{_ss['V_S']:.1f} mm")
                st.caption("V/S = A_conc / Perimeter = "
                           f"({_A_conc_vs:.0f}) / ({_perim_vs:.0f}) = {_ss['V_S']:.1f} mm")
            else:
                _ss["V_S"] = st.number_input(
                    "V/S (mm) — manual", 20.0, 100.0, _ss["V_S"], 1.0, key="_vs")
                st.caption("Manual override: enter V/S for non-standard sections.")

    if "pl_total_MPa" in _ss:
        section_hdr("B.3b", "Loss Results (auto)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total loss", f"{_ss['pl_total_MPa']:.1f} MPa")
        col2.metric("Total %",    f"{_ss['pl_total_pct']:.1f} %")
        col3.metric("fse",        f"{_ss['pl_fse']:.1f} MPa")
        st.caption(
            f"ES={_ss['pl_ES']:.1f} | CR={_ss['pl_CR']:.1f} | "
            f"SH={_ss['pl_SH']:.1f} | RE={_ss['pl_RE']:.1f} MPa"
        )
        st.success(f"Effective prestress force Pe = {_ss['pl_Pe']:.1f} kN")

# =============================================================================
# TAB C — Span  (was D, + beam width inputs)
# =============================================================================
with tab_C:
    section_hdr("C.1", "Span & Support Geometry")
    st.caption(
        "L_clear = L_cc − ½·bw_beam_L − ½·bw_beam_R  |  "
        "L_an = L_clear + ½·b_bear_L + ½·b_bear_R"
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["L_cc"] = st.number_input(
            "L_cc — centre-to-centre (mm)", 1000, 30000,
            int(_ss["L_cc"]), 100, key="_L_cc")
    with col2:
        _ss["bw_beam_L"] = st.number_input(
            "bw_beam_L — lebar balok kiri (mm)", 100, 2000,
            int(_ss["bw_beam_L"]), 50, key="_bw_beam_L")
    with col3:
        _ss["bw_beam_R"] = st.number_input(
            "bw_beam_R — lebar balok kanan (mm)", 100, 2000,
            int(_ss["bw_beam_R"]), 50, key="_bw_beam_R")

    st.markdown("---")
    section_hdr("C.2", "Bearing Width")
    col1, col2 = st.columns(2)
    with col1:
        _ss["b_bear_L"] = st.number_input(
            "b_bear_L — bearing kiri (mm)", 50, 500,
            int(_ss["b_bear_L"]), 5, key="_b_bear_L")
    with col2:
        _ss["b_bear_R"] = st.number_input(
            "b_bear_R — bearing kanan (mm)", 50, 500,
            int(_ss["b_bear_R"]), 5, key="_b_bear_R")

    # Compute & display span
    _Lcl = _ss["L_cc"] - _ss["bw_beam_L"] / 2.0 - _ss["bw_beam_R"] / 2.0
    _Lan = _Lcl + _ss["b_bear_L"] / 2.0 + _ss["b_bear_R"] / 2.0
    _ss["L_clear"] = _Lcl
    _ss["L_an"]    = _Lan
    _bm = max(_Lcl / 180.0, 50.8)
    _ss["bear_min"] = _bm

    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("L_cc",    f"{_ss['L_cc']:.0f}",  "mm")}
        {metric_card("L_clear", f"{_Lcl:.0f}",         "mm  = L_cc − ½bw_L − ½bw_R")}
        {metric_card("L_an",    f"{_Lan:.0f}",          "mm  = L_clear + ½bear_L + ½bear_R")}
        {metric_card("bear_min",f"{_bm:.1f}",           "mm")}
        </div>""",
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("L_clear", f"{_Lcl:.0f} mm")
    col2.metric("b_bear_L", f"{_ss['b_bear_L']} mm",
                delta="OK" if _ss['b_bear_L'] >= _bm else f"Short by {_bm - _ss['b_bear_L']:.1f} mm",
                delta_color="normal" if _ss['b_bear_L'] >= _bm else "inverse")
    col3.metric("b_bear_R", f"{_ss['b_bear_R']} mm",
                delta="OK" if _ss['b_bear_R'] >= _bm else f"Short by {_bm - _ss['b_bear_R']:.1f} mm",
                delta_color="normal" if _ss['b_bear_R'] >= _bm else "inverse")

    st.markdown("---")
    section_hdr("C.3", "Transfer & Development Length")
    col1, col2, col3 = st.columns(3)
    col1.metric("l_t",  f"{_ss['lb_l_t']:.0f} mm")
    col2.metric("l_d",  f"{_ss['lb_l_d']:.0f} mm")
    col3.metric("d_ps", f"{get_ps_diameter_mm():.1f} mm")
    _ps_badge_cls = ("ok" if _ss["lb_ps_status"] == "FULL"
                     else "warn" if _ss["lb_ps_status"] == "PARTIAL" else "err")
    st.markdown(
        f'<span class="badge-{_ps_badge_cls}">'
        f'{_ss["lb_ps_status"]} — {_ss["lb_ps_message"]}</span>',
        unsafe_allow_html=True
    )

# =============================================================================
# TAB D — Loads  (was E, + load factors + line loads)
# =============================================================================
with tab_D:
    # ── D.1  Self-weight (display only) ──────────────────────────────────────
    section_hdr("D.1", "Self-Weight (auto, dari Tab A & B)")
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("SW_HCS",     f"{_ss['SW_HCS']:.3f}",     "kN/m²")}
        {metric_card("SW_topping", f"{_ss['SW_topping']:.3f}" if _ss['has_topping'] else "—", "kN/m²")}
        {metric_card("SW_total",   f"{_ss['SW_HCS']+_ss['SW_topping']:.3f}", "kN/m²")}
        </div>""",
        unsafe_allow_html=True
    )
    st.caption(
        f"SW_HCS = wc × (b×h − A_voids) / b / 1e6 = "
        f"{_ss['wc']} × ({_ss['b_bottom']}×{_ss['h']} − {_ss['A_voids_total']:.0f}) "
        f"/ {_ss['b_bottom']} / 1e6 = **{_ss['SW_HCS']:.3f} kN/m²**"
    )

    st.markdown("---")

    # ── D.2  Load Factors ─────────────────────────────────────────────────────
    section_hdr("D.2", "Load Factors")
    st.caption("Default: ACI 318-19 Table 5.3.1  |  wu = γ_D × (SW + SDL) + γ_L × LL")
    col1, col2 = st.columns(2)
    with col1:
        _ss["lf_DL"] = st.number_input(
            "γ_DL — Dead load factor", 1.0, 2.0, float(_ss["lf_DL"]), 0.05, key="_lf_DL")
    with col2:
        _ss["lf_LL"] = st.number_input(
            "γ_LL — Live load factor",  1.0, 2.0, float(_ss["lf_LL"]), 0.05, key="_lf_LL")
    st.caption(
        f"wu (user LF) = {_ss['lf_DL']:.2f}×(SW+SDL) + {_ss['lf_LL']:.2f}×LL = "
        f"**{_ss.get('lb_wu_user', 0):.3f} kN/m²**"
    )
    st.info(
        "ℹ️ Catatan: modul hcs/span_loads.py menggunakan LF=1.2/1.6 secara internal. "
        "Nilai γ_DL/γ_LL di sini ditampilkan untuk dokumentasi & laporan. "
        "Untuk custom LF penuh, edit fungsi calc_factored_loads_and_diagrams()."
    )

    st.markdown("---")

    # ── D.3  Area Loads (SDL & LL) ────────────────────────────────────────────
    section_hdr("D.3", "Beban Merata Bidang (Area Load)")
    col1, col2 = st.columns(2)
    with col1:
        _ss["SDL"] = st.number_input(
            "SDL — Superimposed Dead (kN/m²)", 0.0, 50.0, float(_ss["SDL"]), 0.25, key="_SDL")
    with col2:
        _ss["LL"] = st.number_input(
            "LL — Live Load (kN/m²)", 0.0, 100.0, float(_ss["LL"]), 0.25, key="_LL")

    st.markdown("---")

    # ── D.4  Line Loads ───────────────────────────────────────────────────────
    section_hdr("D.4", "Beban Garis (Line Loads)")
    st.caption(
        "Beban garis dikonversikan ke beban bidang ekivalen.\n"
        "• Memanjang (longitudinal) [kN/m] → dibagi lebar panel b_nominal\n"
        "• Melintang (transverse) [kN] → dibagi (b_nominal × L_an) — ekivalen 1 baris"
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Beban Garis Memanjang (Longitudinal)**")
        _ss["wL_long_DL"] = st.number_input(
            "wL_long_DL (kN/m) — DL memanjang",
            0.0, 500.0, float(_ss["wL_long_DL"]), 0.5, key="_wL_long_DL")
        _ss["wL_long_LL"] = st.number_input(
            "wL_long_LL (kN/m) — LL memanjang",
            0.0, 500.0, float(_ss["wL_long_LL"]), 0.5, key="_wL_long_LL")
    with col2:
        st.markdown("**Beban Garis Melintang (Transverse / 1 baris)**")
        _ss["wL_trans_DL"] = st.number_input(
            "wL_trans_DL (kN) — total DL melintang",
            0.0, 5000.0, float(_ss["wL_trans_DL"]), 1.0, key="_wL_trans_DL")
        _ss["wL_trans_LL"] = st.number_input(
            "wL_trans_LL (kN) — total LL melintang",
            0.0, 5000.0, float(_ss["wL_trans_LL"]), 1.0, key="_wL_trans_LL")

    _b_m = _ss["b_nominal"] / 1000.0
    _L_m = _ss["L_an"] / 1000.0 if _ss["L_an"] > 0 else 1.0
    _sdl_eff = (_ss["SDL"]
                + _ss["wL_long_DL"] / _b_m
                + _ss["wL_trans_DL"] / (_L_m * _b_m))
    _ll_eff  = (_ss["LL"]
                + _ss["wL_long_LL"] / _b_m
                + _ss["wL_trans_LL"] / (_L_m * _b_m))
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("SDL_eff (total)", f"{_sdl_eff:.3f}", "kN/m²")}
        {metric_card("LL_eff (total)",  f"{_ll_eff:.3f}",  "kN/m²")}
        </div>""",
        unsafe_allow_html=True
    )
    _ss["SDL_eff"] = _sdl_eff
    _ss["LL_eff"]  = _ll_eff

    st.markdown("---")

    # ── D.5  Point Loads ──────────────────────────────────────────────────────
    section_hdr("D.5", "Beban Terpusat (Point Loads)")
    _ss["has_point_load"] = st.checkbox(
        "Ada beban terpusat?", _ss["has_point_load"], key="_has_point_load")
    if _ss["has_point_load"]:
        st.caption("P1 & P2 = beban terpusat (kN). x = jarak dari tumpuan kiri (mm).")
        col1, col2, col3 = st.columns(3)
        with col1:
            _ss["P1_DL"] = st.number_input(
                "P1_DL (kN)", 0.0, step=0.5, value=float(_ss["P1_DL"]), key="_P1_DL")
        with col2:
            _ss["P1_LL"] = st.number_input(
                "P1_LL (kN)", 0.0, step=0.5, value=float(_ss["P1_LL"]), key="_P1_LL")
        with col3:
            _ss["x_P1"] = st.number_input(
                "x_P1 (mm)", 0, step=50, value=int(_ss["x_P1"]), key="_x_P1")
        col1, col2, col3 = st.columns(3)
        with col1:
            _ss["P2_DL"] = st.number_input(
                "P2_DL (kN)", 0.0, step=0.5, value=float(_ss["P2_DL"]), key="_P2_DL")
        with col2:
            _ss["P2_LL"] = st.number_input(
                "P2_LL (kN)", 0.0, step=0.5, value=float(_ss["P2_LL"]), key="_P2_LL")
        with col3:
            _ss["x_P2"] = st.number_input(
                "x_P2 (mm)", 0, step=50, value=int(_ss["x_P2"]), key="_x_P2")
        _ss["slab_position"] = st.radio(
            "Posisi slab",
            ["Interior slab", "Edge slab"],
            index=0 if _ss["slab_position"] == "Interior slab" else 1,
            horizontal=True, key="_slab_position"
        )

    st.markdown("---")

    # ── D.6  Factored Load Summary ────────────────────────────────────────────
    section_hdr("D.6", "Factored Load Summary (auto)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("wu (kN/m²)",     f"{_ss.get('lb_wu_area', 0):.3f}")
    col2.metric("Vu_max (kN)",    f"{_ss.get('lb_Vu_max', 0):.2f}")
    col3.metric("Mu_max (kN·m)",  f"{_ss.get('lb_Mu_max', 0)/1e6:.2f}")
    col4.metric("Ra (kN)",        f"{_ss.get('lb_Ra_u', 0):.2f}")

    # SFD/BMD quick chart
    if "lb_x_arr" in _ss and len(_ss["lb_x_arr"]) > 1:
        _x_m  = _ss["lb_x_arr"] / 1000.0
        _Vu   = _ss["lb_Vu_arr"]
        _Mu   = _ss["lb_Mu_arr"] / 1e6
        _fig  = make_subplots(rows=2, cols=1,
                              subplot_titles=("SFD — Shear Force (kN)",
                                              "BMD — Bending Moment (kN·m)"),
                              vertical_spacing=0.18, shared_xaxes=True)
        _fig.add_trace(go.Scatter(x=_x_m, y=_Vu, name="Vu factored",
                                  line=dict(color="#1A476F", width=2)),
                       row=1, col=1)
        _fig.add_trace(go.Scatter(x=_x_m, y=_Mu, name="Mu factored",
                                  fill="tozeroy",
                                  fillcolor="rgba(26,71,111,0.10)",
                                  line=dict(color="#1A476F", width=2)),
                       row=2, col=1)
        _fig.update_layout(height=400, margin=dict(l=50, r=20, t=60, b=30),
                           legend=dict(orientation="h", y=1.08))
        _fig.update_xaxes(title_text="x (m)", row=2, col=1)
        st.plotly_chart(_fig, use_container_width=True)

# =============================================================================
# TAB E — Seismic  (was F)
# =============================================================================
with tab_E:
    section_hdr("E.1", "Seismic Design Category")
    sdc_opts = ["A", "B", "C", "D", "E", "F"]
    _ss["sdc"] = st.selectbox(
        "SDC", sdc_opts,
        index=sdc_opts.index(_ss["sdc"]), key="_sdc")
    if _ss["sdc"] in ["D", "E", "F"]:
        st.error("SDC D/E/F: special detailing required. See ACI/PCI 319-25 Sec. 12.")
    elif _ss["sdc"] == "C":
        st.warning("SDC C: intermediate seismic requirements.")
    else:
        st.success(f"SDC {_ss['sdc']}: standard provisions apply.")
    st.markdown("---")
    section_hdr("E.2", "Structural Integrity")
    st.info("Integrity reinforcement checked in Capacity phase (Phase 5).")

# =============================================================================
# TAB F — Section Properties  (was G)
# =============================================================================
with tab_F:
    st.markdown("## F · Section Properties")
    st.caption("Ref: ACI/PCI 319-25 Cl. 26.12 | Full detail in Report")
    section_hdr("F.1", "Gross")
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("Ag",   f"{_ss.get('sp_Ag',0):,.0f}",           "mm²")}
        {metric_card("yb_g", f"{_ss.get('sp_yb_g',0):.1f}",          "mm")}
        {metric_card("Ig",   f"{_ss.get('sp_Ig',0)/1e6:.3f}",        "×10⁶ mm⁴")}
        </div>""",
        unsafe_allow_html=True
    )
    section_hdr("F.2", "Net HCS")
    st.markdown(
        f"""<div class="metric-grid">
        {metric_card("An",    f"{_ss.get('sp_An',0):,.0f}",          "mm²")}
        {metric_card("yb",    f"{_ss.get('sp_yb',0):.2f}",           "mm")}
        {metric_card("In",    f"{_ss.get('sp_In',0)/1e6:.3f}",       "×10⁶ mm⁴")}
        {metric_card("e_bot", f"{_ss.get('sp_e_bot',0):.2f}",        "mm")}
        </div>""",
        unsafe_allow_html=True
    )
    section_hdr("F.3", "Composite")
    if _ss.get("has_topping") and _ss.get("t_topping", 0) > 0:
        st.markdown(
            f"""<div class="metric-grid">
            {metric_card("A_comp",  f"{_ss.get('sp_A_comp',0):,.0f}",  "mm²")}
            {metric_card("yb_comp", f"{_ss.get('sp_yb_comp',0):.2f}",  "mm")}
            {metric_card("I_comp",  f"{_ss.get('sp_I_comp',0)/1e6:.3f}", "×10⁶ mm⁴")}
            </div>""",
            unsafe_allow_html=True
        )
    else:
        st.info("No topping → composite = net HCS.")

# =============================================================================
# TAB G — Stress Checks  (was H)
# =============================================================================
with tab_G:
    st.markdown("## G · Stress Checks")
    st.caption("Ref: ACI/PCI 319-25 Table 24.5.3.1")
    if "sc_transfer" not in _ss:
        st.info("Calculating stress checks...")
    else:
        for _stage_key, _stage_title in [
            ("sc_transfer",    "Transfer (release)"),
            ("sc_lifting",     "Lifting (after ES)"),
            ("sc_construction","Construction (topping + SDL, non-composite)"),
            ("sc_service",     f"Service (composite, class {_ss.get('sc_service_class','T')})"),
        ]:
            _d = _ss.get(_stage_key, {})
            if not _d:
                continue
            st.markdown(f"### {_stage_title}")
            col1, col2 = st.columns(2)
            col1.metric("Top fiber",    f"{_d.get('f_top', 0):.2f} MPa")
            col2.metric("Bottom fiber", f"{_d.get('f_bot', 0):.2f} MPa")
            st.caption(
                f"Limit comp: {_d.get('limit_comp',0):.1f} MPa  |  "
                f"tens: {_d.get('limit_tens',0):.2f} MPa  |  "
                f"Status: **{_d.get('status','—')}**"
            )

        _sv = _ss.get("sc_service", {})
        if _sv.get("status") == "NG":
            st.error("Stress check FAILED. Adjust section or prestress.")
        else:
            st.success("All stress checks passed.")

# =============================================================================
# TAB H — Capacity  (was I)
# =============================================================================
with tab_H:
    st.markdown("## H · Flexural & Shear Capacity")
    st.caption("Ref: ACI/PCI 319-25 Cl. 22.2, 22.5, 22.6")
    if "cap_phi_Mn" not in _ss:
        st.info("Calculating capacity...")
    else:
        st.markdown("### Flexural Capacity")
        col1, col2, col3 = st.columns(3)
        col1.metric("fps",    f"{_ss['cap_fps']:.1f} MPa")
        col2.metric("Mn",     f"{_ss['cap_Mn']:.1f} kN·m")
        col3.metric("φMn",    f"{_ss['cap_phi_Mn']:.1f} kN·m")
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
            st.warning("⚠️ h > 317 mm, no topping, Vu > 0.5φVcw → Av,min required.")
        else:
            st.info("No minimum shear reinforcement required per ACI/PCI 319-25.")

        if "cap_phi_Vn_arr" in _ss and len(_ss["cap_phi_Vn_arr"]) > 0:
            _xm  = _ss["lb_x_arr"] / 1000.0
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(
                x=_xm, y=_ss["cap_phi_Vn_arr"],
                name="φVn (capacity)", line=dict(color="green", width=2)))
            _fig.add_trace(go.Scatter(
                x=_xm, y=abs(_ss["lb_Vu_arr"]),
                name="|Vu| (demand)", line=dict(color="red", width=2, dash="dash")))
            _fig.update_layout(
                title="Shear Capacity vs Demand along span",
                xaxis_title="Distance from left support (m)",
                yaxis_title="Shear (kN)", height=380)
            st.plotly_chart(_fig, use_container_width=True)

# =============================================================================
# TAB I — Deflection  (was J)
# =============================================================================
with tab_I:
    st.markdown("## I · Deflection & Camber")
    st.caption("Ref: PCI Handbook 8th Ed. Sec. 4.8 & Table 4.8.3 | ACI 318-19 Table 24.2.2")
    if "def_delta_ps_initial" not in _ss:
        st.info("Calculating deflections...")
    else:
        st.markdown("### Initial (at release)")
        col1, col2 = st.columns(2)
        col1.metric("Prestress camber",      f"{_ss['def_delta_ps_initial']:.2f} mm  ↑")
        col2.metric("Self-weight deflection", f"{_ss['def_delta_sw']:.2f} mm  ↓")
        st.metric("Net at release", f"{_ss['def_net_release']:.2f} mm")

        st.markdown("### Long-term (final stage)")
        col1, col2 = st.columns(2)
        col1.metric("Final camber (×mult)", f"{_ss['def_delta_ps_initial']*2.0:.2f} mm")
        col2.metric("Total long-term",       f"{_ss['def_total_longterm']:.2f} mm")

        st.markdown("### Code Limit Checks (ACI 318-19 Table 24.2.2)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Limit LL  (L/360)",    f"{_ss['def_limit_ll_mm']:.1f} mm")
        col2.metric("Limit total (L/240)",   f"{_ss['def_limit_total_mm']:.1f} mm")
        col3.metric("Actual total",          f"{_ss['def_total_longterm']:.1f} mm")

        _stll  = _ss["def_status_ll"]
        _sttot = _ss["def_status_total"]
        st.markdown(f"**LL status:** {_stll}  |  **Total status:** {_sttot}")
        if _sttot == "NG":
            st.error("Total deflection exceeds code limit.")
        else:
            st.success("Deflection within code limits.")

# =============================================================================
# TAB J — Report  (was K)
# =============================================================================
with tab_J:
    st.markdown("## J · Report Generator")
    st.caption("Generate professional calculation report (Word / PDF).")
    st.info("Report includes: inputs, transfer/dev length, section props, "
            "losses, stress checks, capacity, deflection.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Generate Word Report (.docx)", use_container_width=True):
            with st.spinner("Generating Word report..."):
                _wb, _ = get_report_bytes(_ss)
                if _wb:
                    st.download_button(
                        label="⬇ Download Word Report",
                        data=_wb,
                        file_name=f"HCS_Design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
                else:
                    st.error("Word generation failed. Check python-docx installation.")
    with col2:
        if st.button("📑 Generate PDF Report", use_container_width=True):
            with st.spinner("Generating PDF report..."):
                _, _pb = get_report_bytes(_ss)
                if _pb:
                    st.download_button(
                        label="⬇ Download PDF Report",
                        data=_pb,
                        file_name=f"HCS_Design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.error("PDF generation failed. Check fpdf2 / kaleido installation.")

    st.markdown("---")
    st.markdown("""
**Report includes:**
- All inputs (section, materials, span, loads)
- Transfer & development length
- Section properties (gross, net, composite)
- Prestress losses (ES, CR, SH, RE)
- Stress checks (transfer, lifting, construction, service)
- Flexural and shear capacity (Mn, Vn, DCR)
- Deflection and camber (initial, long-term, code limits)
- SFD/BMD diagrams
- Remarks and code references
""")

# =============================================================================
# TAB Summary
# =============================================================================
with tab_sum:
    st.markdown("## Summary")
    _ok_geom = _ss.get("geom_valid", False)
    _ok_M    = _ss.get("cap_DCR_M", 999) <= 1.0
    _ok_V    = _ss.get("cap_DCR_V", 999) <= 1.0
    _ok_def  = _ss.get("def_status_total", "NG") == "OK"
    _ok_str  = all(
        _ss.get(k, {}).get("status", "NG") == "OK"
        for k in ["sc_transfer", "sc_lifting", "sc_construction", "sc_service"]
        if k in _ss
    )
    summary_data = {
        "Check": [
            "Geometry valid",
            "SW_HCS",
            "Flexure  DCR_M",
            "Shear    DCR_V",
            "Stress checks",
            "Deflection",
            "L_clear",
            "L_an",
        ],
        "Value": [
            "✅ OK" if _ok_geom else "❌ Fail",
            f"{_ss.get('SW_HCS', 0):.3f} kN/m²",
            f"{_ss.get('cap_DCR_M', 999):.3f}  {'✅' if _ok_M else '❌'}",
            f"{_ss.get('cap_DCR_V', 999):.3f}  {'✅' if _ok_V else '❌'}",
            "✅ All OK" if _ok_str else "❌ Fail",
            f"{_ss.get('def_total_longterm', 0):.2f} mm  {'✅' if _ok_def else '❌'}",
            f"{_ss.get('L_clear', 0):.0f} mm",
            f"{_ss.get('L_an', 0):.0f} mm",
        ]
    }
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
    st.caption("Full detail: use J · Report tab to generate Word/PDF.")
