# =============================================================================
# HCS DESIGN APP — Phase 5: Capacity (Flexure & Shear)
# =============================================================================
# Reference: ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
# Units: SI only (mm, kN, MPa)
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
from hcs.prestress_loss import get_prestress_losses
from hcs.stress_check import get_all_stress_checks
from hcs.capacity import get_capacity_results   # Phase 5

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HCS Design — ACI/PCI 319-25",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================
def init_session_state():
    _default_A_core_1      = 7106.5
    _default_A_voids_total = 9 * _default_A_core_1
    _default_h_core        = 120.0
    _default_bw_shear      = 1199 - 9 * 80
    _default_Ec_hcs        = 33000.0
    _default_Ec_top        = 27000.0
    _default_n_mod         = _default_Ec_top / _default_Ec_hcs if _default_Ec_hcs > 0 else 1.0

    defaults = {
        "f_ci": 35.0, "f_c_cut": 40.0, "f_c_del": 45.0, "f_c_ere": 50.0,
        "f_c": 50.0, "wc": 24.0, "has_topping": True, "f_c_top": 30.0, "wc_top": 24.0,
        "b_nominal": 1200, "b_bottom": 1199, "b_top": 1187, "h": 200,
        "tf_top": 52, "tf_bot": 50, "t_topping": 60,
        "hcs_type": "Full HCS (Hollow Core)", "core_shape": "Teardrop",
        "d_core": 80, "n_core": 9, "h_straight": 40, "h_taper": 40,
        "gap_side": 67, "gap_between": 52, "preset": "HCS 200mm — Teardrop core",
        "ps_type": "PC Wire (plain/indented)", "wire_dia": 5.0,
        "strand_size": "1/2 in  (d=11.2mm)", "n_bot": 10, "n_top": 0,
        "cover_bot": 35, "cover_top": 30, "fpi_pct": 75.0,
        "fpu": 1618.0, "fpy": 1432.0, "Eps": 199050.0, "ps_area": 19.6,
        "fpi": 1213.5, "Aps_bot": 196.0, "Aps_top": 0.0, "dp_bot": 165.0, "dp_top": 30.0, "Pi": 237.8,
        "A_core_1": _default_A_core_1, "A_voids_total": _default_A_voids_total,
        "h_core": _default_h_core, "bw_shear": _default_bw_shear,
        "Ec_hcs": _default_Ec_hcs, "Ec_top": _default_Ec_top, "n_mod": _default_n_mod,
        "SW_HCS": 3.5, "SW_topping": 1.44, "L_clear": 5850.0, "L_an": 5850.0, "bear_min": 50.8,
        "L_cc": 6000, "b_bear_L": 150, "b_bear_R": 150, "span_type": "Clear span",
        "SDL": 1.5, "LL": 2.0, "has_point_load": False,
        "P1_DL": 5.0, "P1_LL": 5.0, "x_P1": 2000,
        "P2_DL": 0.0, "P2_LL": 0.0, "x_P2": 4000,
        "slab_position": "Interior slab",
        "sdc": "B",
        "RH": 75.0, "V_S": 38.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# =============================================================================
# UI HELPER FUNCTIONS
# =============================================================================
def apply_preset(preset_name: str):
    p = PRESET_TABLE.get(preset_name)
    if p is None:
        return
    for k, v in p.items():
        st.session_state[k] = v

def get_ps_diameter_mm() -> float:
    if st.session_state["ps_type"] == "PC Wire (plain/indented)":
        return float(st.session_state["wire_dia"])
    else:
        return STRAND_PROPS[st.session_state["strand_size"]]["d_mm"]

def badge_html(label: str, status: str, detail: str = "") -> str:
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
# APP STARTUP
# =============================================================================
init_session_state()
_ss = st.session_state

# Phase 1B
_fpu_def = _ss.get("fpu", 1618.0)
_fpi_pct_def = _ss.get("fpi_pct", 75.0)
_fpi = _ss.get("fpi", _fpu_def * _fpi_pct_def / 100.0)
_d_ps_mm = get_ps_diameter_mm()
_td = calc_transfer_development_length(
    ps_type=_ss["ps_type"], d_ps=_d_ps_mm, fpu=_ss["fpu"],
    fpi=_fpi, fpy=_ss.get("fpy", _ss["fpu"] * 0.885), assumed_loss_pct=20.0,
)
for k in ["l_t", "l_d", "fse_est", "fps_est", "method_lt", "loss_note"]:
    _ss[f"lb_{k}"] = _td[k]

_L_an = _ss.get("L_an", _ss["L_cc"] - _ss["b_bear_L"]/2 - _ss["b_bear_R"]/2)
_dev = check_prestress_development(_L_an, _td["l_d"])
_ss["lb_ps_status"] = _dev["status"]
_ss["lb_ps_is_ps"] = _dev["is_prestressed"]
_ss["lb_ps_message"] = _dev["message"]

_A_voids_total = _ss.get("A_voids_total", 63959.0)
_SW_HCS = _ss.get("SW_HCS", _ss["wc"] * (_ss["b_bottom"] * _ss["h"] - _A_voids_total) / (_ss["b_bottom"] * 1e6))
_SW_topping = _ss.get("SW_topping", _ss["wc_top"] * _ss["b_nominal"] * _ss["t_topping"] / (_ss["b_nominal"] * 1e6) if _ss["has_topping"] else 0.0)

_ld = calc_factored_loads_and_diagrams(
    L_an=_L_an, b_bottom=_ss["b_bottom"], t_topping=_ss["t_topping"],
    wc=_ss["wc"], wc_top=_ss["wc_top"], has_topping=_ss["has_topping"],
    SW_HCS=_SW_HCS, SW_topping=_SW_topping, SDL=_ss["SDL"], LL=_ss["LL"],
    has_point_load=_ss["has_point_load"],
    P1_DL=_ss["P1_DL"], P1_LL=_ss["P1_LL"], x_P1=_ss["x_P1"],
    P2_DL=_ss["P2_DL"], P2_LL=_ss["P2_LL"], x_P2=_ss["x_P2"],
    slab_position=_ss["slab_position"], N=200,
)
for k, v in _ld.items():
    _ss[f"lb_{k}"] = v

# Phase 2
_sp = get_all_section_props(dict(_ss))
for k, v in _sp.items():
    _ss[f"sp_{k}"] = v

# Phase 3
_losses = get_prestress_losses(_ss)
for k, v in _losses.items():
    _ss[k] = v

# Phase 4
_stress = get_all_stress_checks(_ss)
for k, v in _stress.items():
    _ss[k] = v

# Phase 5
_cap = get_capacity_results(_ss)
for k, v in _cap.items():
    _ss[k] = v

# =============================================================================
# HEADER & SIDEBAR
# =============================================================================
st.markdown("""
<div class="app-header">
    <div style="margin-bottom:8px">
        <span class="phase-badge">PHASE 5</span>
        <span class="phase-badge">ACI/PCI 319-25</span>
        <span class="phase-badge">PCI 8th Ed.</span>
    </div>
    <h1>🏗️ Hollow Core Slab Design</h1>
    <div class="subtitle">Structural Design Calculator · SI Units (mm · kN · MPa)</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📐 HCS Design App")
    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.8rem;">
    ✔ Phase 1A — Input<br>
    ✔ Phase 1B — Span & Transfer<br>
    ✔ Phase 2 — Section Props<br>
    ✔ Phase 3 — Prestress Losses<br>
    ✔ Phase 4 — Stress Checks<br>
    <b>▶ Phase 5 — Capacity (Mn & Vn)</b><br>
    <span style="color:gray;">Phase 6 — Deflection</span><br>
    <span style="color:gray;">Phase 7 — Report</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    st.caption("ACI/PCI 319-25, PCI Handbook 8th Ed.")

# =============================================================================
# TABS
# =============================================================================
tab_A, tab_B, tab_C, tab_D, tab_E, tab_F, tab_G, tab_H, tab_I, tab_sum, tab_P2 = st.tabs([
    "A · Concrete", "B · Section", "C · Prestress", "D · Span",
    "E · Loads", "F · Seismic", "G · Props", "H · Stress",
    "I · Capacity", "📋 Summary", "📐 Appendix A"
])

# =============================================================================
# TAB A (Concrete) - sederhana
# =============================================================================
with tab_A:
    section_hdr("A.1", "HCS Concrete")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["f_ci"] = st.number_input("f'ci transfer (MPa)", 20.0, 80.0, _ss["f_ci"], 1.0)
        _ss["f_c_cut"] = st.number_input("f'c cut (MPa)", 20.0, 80.0, _ss["f_c_cut"], 1.0)
    with col2:
        _ss["f_c_del"] = st.number_input("f'c delivery (MPa)", 20.0, 80.0, _ss["f_c_del"], 1.0)
        _ss["f_c_ere"] = st.number_input("f'c erection (MPa)", 20.0, 80.0, _ss["f_c_ere"], 1.0)
    with col3:
        _ss["f_c"] = st.number_input("f'c 28-day (MPa)", 20.0, 100.0, _ss["f_c"], 1.0)
        _ss["wc"] = st.number_input("wc (kN/m³)", 18.0, 30.0, _ss["wc"], 0.5)
    st.markdown("---")
    section_hdr("A.2", "Topping")
    _ss["has_topping"] = st.checkbox("Structural Topping", _ss["has_topping"])
    if _ss["has_topping"]:
        col1, col2 = st.columns(2)
        with col1: _ss["f_c_top"] = st.number_input("f'c_top (MPa)", 17.0, 60.0, _ss["f_c_top"], 1.0)
        with col2: _ss["wc_top"] = st.number_input("wc_top (kN/m³)", 18.0, 30.0, _ss["wc_top"], 0.5)
    else:
        _ss["t_topping"] = 0
        st.info("No topping")
    st.markdown("---")
    section_hdr("A.3", "Elastic Moduli")
    Ec_hcs, Ec_top, n_mod = calc_modular_ratio(_ss["wc"], _ss["f_c"], _ss["wc_top"], _ss["f_c_top"])
    _ss["Ec_hcs"], _ss["Ec_top"], _ss["n_mod"] = Ec_hcs, Ec_top, n_mod
    col1, col2, col3 = st.columns(3)
    col1.metric("Ec_HCS", f"{Ec_hcs:.0f} MPa")
    col2.metric("Ec_top", f"{Ec_top:.0f} MPa" if _ss["has_topping"] else "N/A")
    col3.metric("n_mod", f"{n_mod:.3f}" if _ss["has_topping"] else "N/A")

# =============================================================================
# TAB B (Cross-section) - disederhanakan
# =============================================================================
with tab_B:
    section_hdr("B.0", "Preset")
    preset_choice = st.selectbox("Standard Preset", list(PRESET_TABLE.keys()),
                                  index=list(PRESET_TABLE.keys()).index(_ss["preset"]))
    if preset_choice != _ss["preset"]:
        _ss["preset"] = preset_choice
        apply_preset(preset_choice)
        st.rerun()
    st.markdown("---")
    section_hdr("B.1", "Dimensions")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["b_nominal"] = st.number_input("b_nom (mm)", 600, 2400, _ss["b_nominal"], 1)
        _ss["b_bottom"] = st.number_input("b_bottom (mm)", 600, 2400, _ss["b_bottom"], 1)
        _ss["b_top"] = st.number_input("b_top (mm)", 600, 2400, _ss["b_top"], 1)
    with col2:
        _ss["h"] = st.number_input("h HCS (mm)", 80, 600, _ss["h"], 1)
        _ss["tf_top"] = st.number_input("tf_top (mm)", 0, 200, _ss["tf_top"], 1)
        _ss["tf_bot"] = st.number_input("tf_bot (mm)", 20, 200, _ss["tf_bot"], 1)
    with col3:
        if _ss["has_topping"]:
            _ss["t_topping"] = st.number_input("topping t (mm)", 0, 200, _ss["t_topping"], 5)
        else:
            st.info("topping = 0")
    st.markdown("---")
    section_hdr("B.2", "HCS Type")
    _ss["hcs_type"] = st.radio("Type", ["Full HCS (Hollow Core)", "Half Slab (Open Top)"],
                                 index=0 if _ss["hcs_type"]=="Full HCS (Hollow Core)" else 1, horizontal=True)
    if _ss["hcs_type"] == "Half Slab (Open Top)":
        _ss["tf_top"] = 0
        st.info("Half slab: top flange forced 0 mm.")
    st.markdown("---")
    section_hdr("B.3", "Core Geometry")
    col1, col2 = st.columns([1,2])
    with col1:
        _ss["core_shape"] = st.radio("Shape", ["Circular", "Capsule", "Teardrop"],
                                       index=["Circular","Capsule","Teardrop"].index(_ss["core_shape"]))
    with col2:
        desc = {"Circular":"h_core = d_core","Capsule":"+ straight","Teardrop":"+ taper"}
        st.markdown(f'<div class="info-box">{desc[_ss["core_shape"]]}</div>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: _ss["d_core"] = st.number_input("d_core (mm)", 40, 300, _ss["d_core"], 1)
    with col2: _ss["n_core"] = st.number_input("n_core", 1, 20, _ss["n_core"], 1)
    with col3: _ss["gap_side"] = st.number_input("gap_side (mm)", 20, 200, _ss["gap_side"], 1)
    with col4: _ss["gap_between"] = st.number_input("gap_between (mm)", 10, 200, _ss["gap_between"], 1)
    if _ss["core_shape"] == "Capsule":
        _ss["h_straight"] = st.number_input("h_straight (mm)", 0, 400, _ss["h_straight"], 5)
    if _ss["core_shape"] == "Teardrop":
        _ss["h_taper"] = st.number_input("h_taper (mm)", 0, 400, _ss["h_taper"], 5)
    A_core_1 = calc_core_area(_ss["core_shape"], _ss["d_core"], _ss["h_straight"], _ss["h_taper"])
    A_voids_total = _ss["n_core"] * A_core_1
    h_core_val = calc_h_core(_ss["core_shape"], _ss["d_core"], _ss["h_straight"], _ss["h_taper"])
    bw_shear = _ss["b_bottom"] - _ss["n_core"] * _ss["d_core"]
    _ss["A_core_1"], _ss["A_voids_total"], _ss["h_core"], _ss["bw_shear"] = A_core_1, A_voids_total, h_core_val, bw_shear
    st.markdown(f"""<div class="metric-grid">{metric_card("h_core", f"{h_core_val:.1f}", "mm")}{metric_card("A_voids_total", f"{A_voids_total:,.0f}", "mm²")}{metric_card("bw_shear", f"{bw_shear:.0f}", "mm")}</div>""", unsafe_allow_html=True)
    st.markdown("---")
    section_hdr("B.4", "Validation")
    h_check = _ss["tf_top"] + h_core_val + _ss["tf_bot"]
    chk1_ok = abs(h_check - _ss["h"]) < 1.0
    w_used = 2*_ss["gap_side"] + _ss["n_core"]*_ss["d_core"] + (_ss["n_core"]-1)*_ss["gap_between"]
    chk2_ok = w_used <= _ss["b_bottom"]
    chk3_ok = _ss["gap_between"] >= 25
    badges = badge_html(f"Flange+core: {h_check:.1f} mm", "OK" if chk1_ok else "ERR") + " " + \
             badge_html(f"Width fit: {w_used} ≤ {_ss['b_bottom']}", "OK" if chk2_ok else "WARN") + " " + \
             badge_html(f"gap_between ≥25", "OK" if chk3_ok else "WARN")
    st.markdown(badges, unsafe_allow_html=True)
    _ss["geom_valid"] = chk1_ok and chk2_ok and chk3_ok

# =============================================================================
# TAB C (Prestress + Losses) - disederhanakan
# =============================================================================
with tab_C:
    section_hdr("C.1", "Steel Type")
    _ss["ps_type"] = st.radio("Type", ["PC Wire (plain/indented)", "7-Wire Strand (low relax)"],
                                 index=0 if _ss["ps_type"]=="PC Wire (plain/indented)" else 1, horizontal=True)
    if _ss["ps_type"] == "PC Wire (plain/indented)":
        _ss["wire_dia"] = st.selectbox("Wire dia (mm)", [5.0,7.0], index=[5.0,7.0].index(_ss["wire_dia"]))
        props = WIRE_PROPS[_ss["wire_dia"]]
    else:
        _ss["strand_size"] = st.selectbox("Strand size", list(STRAND_PROPS.keys()),
                                           index=list(STRAND_PROPS.keys()).index(_ss["strand_size"]))
        props = STRAND_PROPS[_ss["strand_size"]]
    _ss["ps_area"] = props["area_mm2"]
    _ss["fpu"], _ss["fpy"], _ss["Eps"] = props["fpu_MPa"], props["fpy_MPa"], props["Eps_MPa"]
    st.markdown("---")
    section_hdr("C.2", "Tendon Layout")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["n_bot"] = st.number_input("n_bot", 0, 30, _ss["n_bot"], 1)
        _ss["cover_bot"] = st.number_input("cover_bot (mm)", 15, 100, _ss["cover_bot"], 1)
    with col2:
        _ss["n_top"] = st.number_input("n_top", 0, 20, _ss["n_top"], 1)
        if _ss["n_top"] > 0:
            _ss["cover_top"] = st.number_input("cover_top (mm)", 15, 100, _ss["cover_top"], 1)
    with col3:
        _ss["fpi_pct"] = st.slider("fpi_pct (% fpu)", 70.0, 80.0, _ss["fpi_pct"], 0.5)
    Aps_bot = _ss["n_bot"] * _ss["ps_area"]
    Aps_top = _ss["n_top"] * _ss["ps_area"]
    fpi = _ss["fpi_pct"]/100 * _ss["fpu"]
    Pi = (Aps_bot + Aps_top) * fpi / 1000
    dp_bot = _ss["h"] - _ss["cover_bot"]
    dp_top = _ss["cover_top"] if _ss["n_top"]>0 else 0
    _ss["Aps_bot"], _ss["Aps_top"], _ss["fpi"], _ss["Pi"], _ss["dp_bot"], _ss["dp_top"] = Aps_bot, Aps_top, fpi, Pi, dp_bot, dp_top
    st.markdown("---")
    section_hdr("C.3", "Derived Prestress")
    st.markdown(f"""<div class="metric-grid">{metric_card("Aps_bot", f"{Aps_bot:.1f}", "mm²")}{metric_card("Aps_top", f"{Aps_top:.1f}" if Aps_top>0 else "—", "mm²")}{metric_card("fpi", f"{fpi:.1f}", "MPa")}{metric_card("Pi", f"{Pi:.1f}", "kN")}{metric_card("dp_bot", f"{dp_bot:.0f}", "mm")}{metric_card("dp_top", f"{dp_top:.0f}" if dp_top>0 else "—", "mm")}</div>""", unsafe_allow_html=True)
    st.markdown("---")
    section_hdr("C.4", "Loss Parameters")
    with st.expander("⚙️ Settings", expanded=False):
        col1, col2 = st.columns(2)
        with col1: _ss["RH"] = st.slider("RH (%)", 40.0, 100.0, _ss["RH"], 1.0)
        with col2: _ss["V_S"] = st.number_input("V/S (mm)", 20.0, 100.0, _ss["V_S"], 1.0)
    section_hdr("C.5", "Loss Results")
    if "pl_total_MPa" in _ss:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total loss", f"{_ss['pl_total_MPa']:.1f} MPa")
        col2.metric("Total %", f"{_ss['pl_total_pct']:.1f} %")
        col3.metric("fse", f"{_ss['pl_fse']:.1f} MPa")
        st.caption(f"ES={_ss['pl_ES']:.1f} CR={_ss['pl_CR']:.1f} SH={_ss['pl_SH']:.1f} RE={_ss['pl_RE']:.1f}")
        st.success(f"Pe = {_ss['pl_Pe']:.1f} kN")
    else:
        st.info("Calculating...")

# =============================================================================
# TAB D (Span)
# =============================================================================
with tab_D:
    section_hdr("D.1", "Span & Bearings")
    col1, col2, col3 = st.columns(3)
    with col1: _ss["L_cc"] = st.number_input("L_cc (mm)", 1000, 30000, _ss["L_cc"], 100)
    with col2: _ss["b_bear_L"] = st.number_input("Left bearing (mm)", 50, 500, _ss["b_bear_L"], 5)
    with col3: _ss["b_bear_R"] = st.number_input("Right bearing (mm)", 50, 500, _ss["b_bear_R"], 5)
    L_clear = _ss["L_cc"] - _ss["b_bear_L"]/2 - _ss["b_bear_R"]/2
    _ss["L_clear"] = L_clear
    _ss["span_type"] = st.radio("Analysis span", ["Clear span", "Clear + 1/2 bearing"],
                                 index=0 if _ss["span_type"]=="Clear span" else 1, horizontal=True)
    L_an = L_clear if _ss["span_type"]=="Clear span" else L_clear + (_ss["b_bear_L"]+_ss["b_bear_R"])*0.25
    _ss["L_an"] = L_an
    bear_min = max(L_clear/180, 50.8)
    _ss["bear_min"] = bear_min
    st.markdown(f"""<div class="metric-grid">{metric_card("L_clear", f"{L_clear:.0f}", "mm")}{metric_card("L_an", f"{L_an:.0f}", "mm")}{metric_card("bear_min", f"{bear_min:.1f}", "mm")}</div>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    col1.metric("Min bearing", f"{bear_min:.1f} mm")
    col2.metric("Left", f"{_ss['b_bear_L']} mm", delta="OK" if _ss['b_bear_L']>=bear_min else f"Short {bear_min-_ss['b_bear_L']:.1f}")
    col3.metric("Right", f"{_ss['b_bear_R']} mm", delta="OK" if _ss['b_bear_R']>=bear_min else f"Short {bear_min-_ss['b_bear_R']:.1f}")
    st.markdown("---")
    section_hdr("D.2", "Transfer & Development")
    col1, col2, col3 = st.columns(3)
    col1.metric("l_t", f"{_ss['lb_l_t']:.0f} mm")
    col2.metric("l_d", f"{_ss['lb_l_d']:.0f} mm")
    col3.metric("d_ps", f"{get_ps_diameter_mm():.1f} mm")
    st.markdown(f'<span class="badge-{"ok" if _ss["lb_ps_status"]=="FULL" else "warn" if _ss["lb_ps_status"]=="PARTIAL" else "err"}">{_ss["lb_ps_status"]} dev.</span>', unsafe_allow_html=True)

# =============================================================================
# TAB E (Loads) - ringkas
# =============================================================================
with tab_E:
    section_hdr("E.1", "Self-weight")
    b_bot = _ss["b_bottom"]; h_hcs = _ss["h"]; wc = _ss["wc"]; A_void = _ss["A_voids_total"]
    gross_A = b_bot*h_hcs - A_void if _ss["hcs_type"]=="Full HCS (Hollow Core)" else b_bot*h_hcs
    SW_HCS = wc * (gross_A/(b_bot*1e6))
    SW_topping = _ss["wc_top"] * _ss["t_topping"]/1000 if _ss["has_topping"] else 0
    _ss["SW_HCS"], _ss["SW_topping"] = SW_HCS, SW_topping
    st.markdown(f"""<div class="metric-grid">{metric_card("SW_HCS", f"{SW_HCS:.3f}", "kN/m²")}{metric_card("SW_topping", f"{SW_topping:.3f}" if _ss["has_topping"] else "—", "kN/m²")}{metric_card("SW_total", f"{SW_HCS+SW_topping:.3f}", "kN/m²")}</div>""", unsafe_allow_html=True)
    st.markdown("---")
    section_hdr("E.2", "Superimposed")
    col1, col2 = st.columns(2)
    with col1: _ss["SDL"] = st.number_input("SDL (kN/m²)", 0.0, 50.0, _ss["SDL"], 0.25)
    with col2: _ss["LL"] = st.number_input("LL (kN/m²)", 0.0, 100.0, _ss["LL"], 0.25)
    st.markdown("---")
    section_hdr("E.3", "Point Loads")
    _ss["has_point_load"] = st.checkbox("Point loads", _ss["has_point_load"])
    if _ss["has_point_load"]:
        col1, col2, col3 = st.columns(3)
        with col1: _ss["P1_DL"] = st.number_input("P1_DL (kN)", 0.0, step=0.5, value=_ss["P1_DL"])
        with col2: _ss["P1_LL"] = st.number_input("P1_LL (kN)", 0.0, step=0.5, value=_ss["P1_LL"])
        with col3: _ss["x_P1"] = st.number_input("x_P1 (mm)", 0, step=50, value=_ss["x_P1"])
        col1, col2, col3 = st.columns(3)
        with col1: _ss["P2_DL"] = st.number_input("P2_DL (kN)", 0.0, step=0.5, value=_ss["P2_DL"])
        with col2: _ss["P2_LL"] = st.number_input("P2_LL (kN)", 0.0, step=0.5, value=_ss["P2_LL"])
        with col3: _ss["x_P2"] = st.number_input("x_P2 (mm)", 0, step=50, value=_ss["x_P2"])
        _ss["slab_position"] = st.radio("Slab position", ["Interior slab", "Edge slab"],
                                         index=0 if _ss["slab_position"]=="Interior slab" else 1, horizontal=True)
    st.markdown("---")
    section_hdr("E.4", "Factored Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("wu", f"{_ss['lb_wu_area']:.3f} kN/m²")
    col2.metric("Vu_max", f"{_ss['lb_Vu_max']:.2f} kN")
    col3.metric("Mu_max", f"{_ss['lb_Mu_max']/1e6:.2f} kN·m")
    col4.metric("Ra", f"{_ss['lb_Ra_u']:.2f} kN")

# =============================================================================
# TAB F (Seismic)
# =============================================================================
with tab_F:
    section_hdr("F.1", "Seismic Design Category")
    sdc_opts = ["A","B","C","D","E","F"]
    _ss["sdc"] = st.selectbox("SDC", sdc_opts, index=sdc_opts.index(_ss["sdc"]))
    if _ss["sdc"] in ["D","E","F"]:
        st.error("SDC D/E/F: special detailing required.")
    elif _ss["sdc"]=="C":
        st.warning("SDC C: intermediate requirements.")
    else:
        st.success(f"SDC {_ss['sdc']}")
    st.markdown("---")
    section_hdr("F.2", "Structural Integrity")
    st.info("Integrity reinforcement checked in Phase 5 (Av_min).")

# =============================================================================
# TAB G (Props quick)
# =============================================================================
with tab_G:
    st.markdown("## G · Section Properties")
    st.caption("Quick view | Full detail in Appendix A")
    g = _ss
    section_hdr("G.1", "Gross")
    st.markdown(f"""<div class="metric-grid">{metric_card("Ag", f"{g.get('sp_Ag',0):,.0f}", "mm²")}{metric_card("yb_g", f"{g.get('sp_yb_g',0):.1f}", "mm")}{metric_card("Ig", f"{g.get('sp_Ig',0)/1e6:.3f}", "x10⁶ mm⁴")}</div>""", unsafe_allow_html=True)
    section_hdr("G.2", "Net")
    st.markdown(f"""<div class="metric-grid">{metric_card("An", f"{g.get('sp_An',0):,.0f}", "mm²")}{metric_card("yb", f"{g.get('sp_yb',0):.2f}", "mm")}{metric_card("In", f"{g.get('sp_In',0)/1e6:.3f}", "x10⁶ mm⁴")}{metric_card("e_bot", f"{g.get('sp_e_bot',0):.2f}", "mm")}</div>""", unsafe_allow_html=True)
    section_hdr("G.3", "Composite")
    if g.get("has_topping") and g.get("t_topping",0)>0:
        st.markdown(f"""<div class="metric-grid">{metric_card("A_comp", f"{g.get('sp_A_comp',0):,.0f}", "mm²")}{metric_card("yb_comp", f"{g.get('sp_yb_comp',0):.2f}", "mm")}{metric_card("I_comp", f"{g.get('sp_I_comp',0)/1e6:.3f}", "x10⁶ mm⁴")}</div>""", unsafe_allow_html=True)
    else:
        st.info("No topping → composite = net.")

# =============================================================================
# TAB H (Stress Checks) - sudah diperbaiki
# =============================================================================
with tab_H:
    st.markdown("## H · Stress Checks")
    st.caption("Ref: ACI/PCI 319-25 Table 24.5.3.1")
    sc = _ss
    if "sc_transfer" not in sc:
        st.info("Calculating stress checks...")
    else:
        t = sc["sc_transfer"]
        st.markdown("### Transfer (release)")
        col1, col2 = st.columns(2)
        with col1: st.metric("Top fiber", f"{t['f_top']:.2f} MPa")
        with col2: st.metric("Bottom fiber", f"{t['f_bot']:.2f} MPa")
        st.caption(f"Limit comp {t['limit_comp']:.1f} MPa, tens {t['limit_tens']:.2f} MPa | Status: {t['status']}")
        li = sc["sc_lifting"]
        st.markdown("### Lifting (after ES)")
        col1, col2 = st.columns(2)
        with col1: st.metric("Top", f"{li['f_top']:.2f} MPa")
        with col2: st.metric("Bottom", f"{li['f_bot']:.2f} MPa")
        st.caption(f"Status: {li['status']}")
        co = sc["sc_construction"]
        st.markdown("### Construction (topping+SDL)")
        col1, col2 = st.columns(2)
        with col1: st.metric("Top", f"{co['f_top']:.2f} MPa")
        with col2: st.metric("Bottom", f"{co['f_bot']:.2f} MPa")
        st.caption(f"Status: {co['status']}")
        sv = sc["sc_service"]
        st.markdown(f"### Service (class {sc.get('sc_service_class','T')})")
        col1, col2 = st.columns(2)
        with col1: st.metric("Top", f"{sv['f_top']:.2f} MPa")
        with col2: st.metric("Bottom", f"{sv['f_bot']:.2f} MPa")
        st.caption(f"Limit comp {sv['limit_comp']:.1f} MPa, tens {sv['limit_tens']:.2f} MPa | Status: {sv['status']}")
        if sv['status'] == "NG":
            st.error("Stress check FAILED.")
        else:
            st.success("All stress checks passed.")

# =============================================================================
# TAB I — CAPACITY (Phase 5)
# =============================================================================
with tab_I:
    st.markdown("## I · Flexural & Shear Capacity")
    st.caption("Ref: ACI 318-19 Ch.22 | ACI/PCI 319-25 Sec.7")
    cap = _ss
    if "cap_phi_Mn_kNm" not in cap:
        st.info("Calculating capacity...")
    else:
        st.markdown("### Flexural Capacity (Mn)")
        col1, col2, col3 = st.columns(3)
        col1.metric("fps", f"{cap['cap_fps']:.1f} MPa")
        col2.metric("a (neutral axis)", f"{cap['cap_a']:.2f} mm")
        col3.metric("Mn", f"{cap['cap_Mn_kNm']:.1f} kN·m")
        st.metric("φ Mn (design)", f"{cap['cap_phi_Mn_kNm']:.1f} kN·m", 
                  delta=f"Mu_max = {_ss.get('lb_Mu_max',0)/1e6:.1f} kN·m")
        if cap['cap_flange_ok']:
            st.success("Neutral axis within flange (OK)")
        else:
            st.warning("Neutral axis exceeds topping thickness — T-section behavior not fully accounted.")
        dcr_m = cap['cap_DCR_M']
        st.metric("Demand-Capacity Ratio (DCR)", f"{dcr_m:.3f}", 
                  delta="PASS" if dcr_m<=1.0 else "FAIL")
        if dcr_m > 1.0:
            st.error("Flexural capacity insufficient. Increase prestress or section.")
        st.markdown("---")
        st.markdown("### Shear Capacity (Vn)")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Vci (flexure-shear)", f"{cap['cap_Vci_kN']:.1f} kN")
            st.metric("Vcw (web-shear)", f"{cap['cap_Vcw_kN']:.1f} kN")
        with col2:
            phi_vn = cap['cap_phi_Vn_kN']
            st.metric("φ Vn (design)", f"{phi_vn:.1f} kN",
                      delta=f"Vu_max = {_ss.get('lb_Vu_max',0):.1f} kN")
            dcr_v = cap['cap_DCR_V']
            st.metric("DCR (shear)", f"{dcr_v:.3f}", 
                      delta="PASS" if dcr_v<=1.0 else "FAIL")
        if cap['cap_needs_Av_min']:
            st.warning("Due to h > 317mm and no topping, minimum stirrups Av_min required per ACI/PCI 319-25.")
        else:
            st.info("No minimum stirrups required for shear.")
        if dcr_v > 1.0:
            st.error("Shear capacity insufficient. Increase section or concrete strength.")

# =============================================================================
# TAB SUMMARY & APPENDIX (placeholder)
# =============================================================================
with tab_sum:
    st.markdown("## Summary")
    st.info("Full summary will be added in Phase 7.")

with tab_P2:
    st.markdown("## Appendix A: Section Properties Details")
    st.caption("Detailed calculation steps will be shown in Phase 7.")
    st.info("Basic properties are shown in Tab G.")
