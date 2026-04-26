# =============================================================================
# HCS DESIGN APP — Phase 7: Complete (All phases 1-7)
# =============================================================================
# Reference: ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
# Units: SI only (mm, kN, MPa)
# =============================================================================

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

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

st.set_page_config(page_title="HCS Design — ACI/PCI 319-25", page_icon="🏗️", layout="wide", initial_sidebar_state="expanded")

# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================
def init_session_state():
    _default_A_core_1 = 7106.5
    _default_A_voids_total = 9 * _default_A_core_1
    _default_h_core = 120.0
    _default_bw_shear = 1199 - 9 * 80
    _default_Ec_hcs = 33000.0
    _default_Ec_top = 27000.0
    _default_n_mod = _default_Ec_top / _default_Ec_hcs if _default_Ec_hcs > 0 else 1.0
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

# UI Helper functions
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
    css = {"OK": "badge-ok", "WARN": "badge-warn", "ERR": "badge-err"}[status]
    icons = {"OK": "✓", "WARN": "⚠", "ERR": "✗"}[status]
    return f'<span class="{css}">{icons} {label}{" — " + detail if detail else ""}</span>'
def metric_card(label, value, unit=""):
    return f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}<span class="metric-unit">{unit}</span></div></div>'
def section_hdr(code, title):
    st.markdown(f'<div class="section-header"><span class="section-label">{code}</span><h3>{title}</h3></div>', unsafe_allow_html=True)

# =============================================================================
# AUTO-CALCULATIONS (Phase 1B to 6)
# =============================================================================
init_session_state()
_ss = st.session_state

# Phase 1B
_fpu_def = _ss.get("fpu", 1618.0)
_fpi_pct_def = _ss.get("fpi_pct", 75.0)
_fpi = _ss.get("fpi", _fpu_def * _fpi_pct_def / 100.0)
_d_ps_mm = get_ps_diameter_mm()
_td = calc_transfer_development_length(ps_type=_ss["ps_type"], d_ps=_d_ps_mm, fpu=_ss["fpu"],
    fpi=_fpi, fpy=_ss.get("fpy", _ss["fpu"] * 0.885), assumed_loss_pct=20.0)
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
    slab_position=_ss["slab_position"], N=200)
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

# Phase 6
_def = get_deflection_results(_ss)
for k, v in _def.items():
    _ss[k] = v

# =============================================================================
# APP HEADER & SIDEBAR
# =============================================================================
st.markdown("""
<div class="app-header">
    <div><span class="phase-badge">PHASE 7</span><span class="phase-badge">ACI/PCI 319-25</span><span class="phase-badge">PCI 8th Ed.</span></div>
    <h1>🏗️ Hollow Core Slab Design</h1>
    <div class="subtitle">Full Design Suite · SI Units · v1.0</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📐 HCS Design App")
    st.markdown("---")
    st.markdown("""✔ Phase 1A — Input<br>✔ Phase 1B — Span & Transfer<br>✔ Phase 2 — Section Props<br>✔ Phase 3 — Losses<br>✔ Phase 4 — Stress Checks<br>✔ Phase 5 — Capacity<br>✔ Phase 6 — Deflection<br>▶ Phase 7 — Report Generator""", unsafe_allow_html=True)
    st.caption("References: ACI/PCI 319-25, PCI Handbook 8th Ed.")

# =============================================================================
# TABS (A to K + Summary + Appendix)
# =============================================================================
tabs = st.tabs(["A · Concrete", "B · Section", "C · Prestress", "D · Span", "E · Loads", "F · Seismic", "G · Props", "H · Stress", "I · Capacity", "J · Deflection", "K · Report", "📋 Summary", "📐 Appendix A"])
tab_A, tab_B, tab_C, tab_D, tab_E, tab_F, tab_G, tab_H, tab_I, tab_J, tab_K, tab_sum, tab_P2 = tabs

# -----------------------------------------------------------------------------
# TAB A — Concrete
# -----------------------------------------------------------------------------
with tab_A:
    section_hdr("A.1", "HCS Concrete")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["f_ci"] = st.number_input("f'ci transfer (MPa)", 20.0, 80.0, _ss["f_ci"], 1.0, key="_f_ci")
        _ss["f_c_cut"] = st.number_input("f'c cut (MPa)", 20.0, 80.0, _ss["f_c_cut"], 1.0, key="_f_c_cut")
    with col2:
        _ss["f_c_del"] = st.number_input("f'c delivery (MPa)", 20.0, 80.0, _ss["f_c_del"], 1.0, key="_f_c_del")
        _ss["f_c_ere"] = st.number_input("f'c erection (MPa)", 20.0, 80.0, _ss["f_c_ere"], 1.0, key="_f_c_ere")
    with col3:
        _ss["f_c"] = st.number_input("f'c 28-day (MPa)", 20.0, 100.0, _ss["f_c"], 1.0, key="_f_c")
        _ss["wc"] = st.number_input("wc (kN/m³)", 18.0, 30.0, _ss["wc"], 0.5, key="_wc")
    st.markdown("---")
    section_hdr("A.2", "Topping")
    _ss["has_topping"] = st.checkbox("Structural Topping", _ss["has_topping"], key="_has_topping")
    if _ss["has_topping"]:
        col1, col2 = st.columns(2)
        with col1: _ss["f_c_top"] = st.number_input("f'c_top (MPa)", 17.0, 60.0, _ss["f_c_top"], 1.0, key="_f_c_top")
        with col2: _ss["wc_top"] = st.number_input("wc_top (kN/m³)", 18.0, 30.0, _ss["wc_top"], 0.5, key="_wc_top")
    else:
        _ss["t_topping"] = 0
        st.info("No topping → t_topping = 0")
    st.markdown("---")
    section_hdr("A.3", "Elastic Moduli")
    Ec_hcs, Ec_top, n_mod = calc_modular_ratio(_ss["wc"], _ss["f_c"], _ss["wc_top"], _ss["f_c_top"])
    _ss["Ec_hcs"], _ss["Ec_top"], _ss["n_mod"] = Ec_hcs, Ec_top, n_mod
    col1, col2, col3 = st.columns(3)
    col1.metric("Ec_HCS", f"{Ec_hcs:.0f} MPa")
    col2.metric("Ec_top", f"{Ec_top:.0f} MPa" if _ss["has_topping"] else "N/A")
    col3.metric("n_mod", f"{n_mod:.3f}" if _ss["has_topping"] else "N/A")

# -----------------------------------------------------------------------------
# TAB B — Cross-Section
# -----------------------------------------------------------------------------
with tab_B:
    section_hdr("B.0", "Preset")
    preset_choice = st.selectbox("HCS Standard Preset", list(PRESET_TABLE.keys()),
                                  index=list(PRESET_TABLE.keys()).index(_ss["preset"]), key="_preset_select")
    if preset_choice != _ss["preset"]:
        _ss["preset"] = preset_choice
        apply_preset(preset_choice)
        st.rerun()
    st.markdown("---")
    section_hdr("B.1", "Dimensions")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["b_nominal"] = st.number_input("b_nom (mm)", 600, 2400, _ss["b_nominal"], 1, key="_b_nominal")
        _ss["b_bottom"] = st.number_input("b_bottom (mm)", 600, 2400, _ss["b_bottom"], 1, key="_b_bottom")
        _ss["b_top"] = st.number_input("b_top (mm)", 600, 2400, _ss["b_top"], 1, key="_b_top")
    with col2:
        _ss["h"] = st.number_input("h HCS (mm)", 80, 600, _ss["h"], 1, key="_h")
        _ss["tf_top"] = st.number_input("tf_top (mm)", 0, 200, _ss["tf_top"], 1, key="_tf_top")
        _ss["tf_bot"] = st.number_input("tf_bot (mm)", 20, 200, _ss["tf_bot"], 1, key="_tf_bot")
    with col3:
        if _ss["has_topping"]:
            _ss["t_topping"] = st.number_input("topping t (mm)", 0, 200, _ss["t_topping"], 5, key="_t_topping")
        else:
            st.info("topping = 0")
    st.markdown("---")
    section_hdr("B.2", "HCS Type")
    _ss["hcs_type"] = st.radio("Type", ["Full HCS (Hollow Core)", "Half Slab (Open Top)"],
                                 index=0 if _ss["hcs_type"]=="Full HCS (Hollow Core)" else 1,
                                 horizontal=True, key="_hcs_type")
    if _ss["hcs_type"] == "Half Slab (Open Top)":
        _ss["tf_top"] = 0
        st.info("Half slab: top flange forced 0 mm.")
    st.markdown("---")
    section_hdr("B.3", "Core Geometry")
    col1, col2 = st.columns([1,2])
    with col1:
        _ss["core_shape"] = st.radio("Shape", ["Circular", "Capsule", "Teardrop"],
                                       index=["Circular","Capsule","Teardrop"].index(_ss["core_shape"]),
                                       key="_core_shape")
    with col2:
        desc = {"Circular":"h_core = d_core","Capsule":"+ straight","Teardrop":"+ taper"}
        st.markdown(f'<div class="info-box">{desc[_ss["core_shape"]]}</div>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: _ss["d_core"] = st.number_input("d_core (mm)", 40, 300, _ss["d_core"], 1, key="_d_core")
    with col2: _ss["n_core"] = st.number_input("n_core", 1, 20, _ss["n_core"], 1, key="_n_core")
    with col3: _ss["gap_side"] = st.number_input("gap_side (mm)", 20, 200, _ss["gap_side"], 1, key="_gap_side")
    with col4: _ss["gap_between"] = st.number_input("gap_between (mm)", 10, 200, _ss["gap_between"], 1, key="_gap_between")
    if _ss["core_shape"] == "Capsule":
        _ss["h_straight"] = st.number_input("h_straight (mm)", 0, 400, _ss["h_straight"], 5, key="_h_straight")
    if _ss["core_shape"] == "Teardrop":
        _ss["h_taper"] = st.number_input("h_taper (mm)", 0, 400, _ss["h_taper"], 5, key="_h_taper")
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
    badges = ""
    badges += badge_html(f"Flange+core: {h_check:.1f} mm (h={_ss['h']})", "OK" if chk1_ok else "ERR") + " "
    badges += badge_html(f"Width fit: {w_used} ≤ {_ss['b_bottom']}", "OK" if chk2_ok else "WARN") + " "
    badges += badge_html(f"gap_between ≥25", "OK" if chk3_ok else "WARN")
    st.markdown(badges, unsafe_allow_html=True)
    _ss["geom_valid"] = chk1_ok and chk2_ok and chk3_ok

# -----------------------------------------------------------------------------
# TAB C — Prestress + Losses
# -----------------------------------------------------------------------------
with tab_C:
    section_hdr("C.1", "Steel Type")
    _ss["ps_type"] = st.radio("Type", ["PC Wire (plain/indented)", "7-Wire Strand (low relax)"],
                                index=0 if _ss["ps_type"]=="PC Wire (plain/indented)" else 1, horizontal=True, key="_ps_type")
    if _ss["ps_type"] == "PC Wire (plain/indented)":
        _ss["wire_dia"] = st.selectbox("Wire dia (mm)", [5.0,7.0], index=[5.0,7.0].index(_ss["wire_dia"]), key="_wire_dia")
        props = WIRE_PROPS[_ss["wire_dia"]]
    else:
        _ss["strand_size"] = st.selectbox("Strand size", list(STRAND_PROPS.keys()),
                                           index=list(STRAND_PROPS.keys()).index(_ss["strand_size"]), key="_strand_size")
        props = STRAND_PROPS[_ss["strand_size"]]
    _ss["ps_area"] = props["area_mm2"]
    _ss["fpu"], _ss["fpy"], _ss["Eps"] = props["fpu_MPa"], props["fpy_MPa"], props["Eps_MPa"]
    st.markdown("---")
    section_hdr("C.2", "Tendon Layout")
    col1, col2, col3 = st.columns(3)
    with col1:
        _ss["n_bot"] = st.number_input("n_bot", 0, 30, _ss["n_bot"], 1, key="_n_bot")
        _ss["cover_bot"] = st.number_input("cover_bot (mm)", 15, 100, _ss["cover_bot"], 1, key="_cover_bot")
    with col2:
        _ss["n_top"] = st.number_input("n_top", 0, 20, _ss["n_top"], 1, key="_n_top")
        if _ss["n_top"] > 0:
            _ss["cover_top"] = st.number_input("cover_top (mm)", 15, 100, _ss["cover_top"], 1, key="_cover_top")
    with col3:
        _ss["fpi_pct"] = st.slider("fpi_pct (% fpu)", 70.0, 80.0, _ss["fpi_pct"], 0.5, key="_fpi_pct")
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
        with col1: _ss["RH"] = st.slider("RH (%)", 40.0, 100.0, _ss["RH"], 1.0, key="_rh")
        with col2: _ss["V_S"] = st.number_input("V/S (mm)", 20.0, 100.0, _ss["V_S"], 1.0, key="_vs")
    section_hdr("C.5", "Loss Results")
    if "pl_total_MPa" in _ss:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total loss", f"{_ss['pl_total_MPa']:.1f} MPa")
        col2.metric("Total %", f"{_ss['pl_total_pct']:.1f} %")
        col3.metric("fse effective", f"{_ss['pl_fse']:.1f} MPa")
        st.caption(f"ES = {_ss['pl_ES']:.1f} | CR = {_ss['pl_CR']:.1f} | SH = {_ss['pl_SH']:.1f} | RE = {_ss['pl_RE']:.1f} MPa")
        st.success(f"Effective force Pe = {_ss['pl_Pe']:.1f} kN")
    else:
        st.info("Calculating losses...")

# -----------------------------------------------------------------------------
# TAB D — Span
# -----------------------------------------------------------------------------
with tab_D:
    section_hdr("D.1", "Span & Bearings")
    col1, col2, col3 = st.columns(3)
    with col1: _ss["L_cc"] = st.number_input("L_cc (mm)", 1000, 30000, _ss["L_cc"], 100, key="_L_cc")
    with col2: _ss["b_bear_L"] = st.number_input("Left bearing (mm)", 50, 500, _ss["b_bear_L"], 5, key="_b_bear_L")
    with col3: _ss["b_bear_R"] = st.number_input("Right bearing (mm)", 50, 500, _ss["b_bear_R"], 5, key="_b_bear_R")
    L_clear = _ss["L_cc"] - _ss["b_bear_L"]/2 - _ss["b_bear_R"]/2
    _ss["L_clear"] = L_clear
    _ss["span_type"] = st.radio("Analysis span", ["Clear span", "Clear + 1/2 bearing"],
                                 index=0 if _ss["span_type"]=="Clear span" else 1, horizontal=True, key="_span_type")
    L_an = L_clear if _ss["span_type"]=="Clear span" else L_clear + (_ss["b_bear_L"]+_ss["b_bear_R"])*0.25
    _ss["L_an"] = L_an
    bear_min = max(L_clear/180, 50.8)
    _ss["bear_min"] = bear_min
    st.markdown(f"""<div class="metric-grid">{metric_card("L_clear", f"{L_clear:.0f}", "mm")}{metric_card("L_an", f"{L_an:.0f}", "mm")}{metric_card("bear_min", f"{bear_min:.1f}", "mm")}</div>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    col1.metric("Min bearing req", f"{bear_min:.1f} mm")
    col2.metric("Left bearing", f"{_ss['b_bear_L']} mm", delta="OK" if _ss['b_bear_L']>=bear_min else f"Short by {bear_min-_ss['b_bear_L']:.1f}")
    col3.metric("Right bearing", f"{_ss['b_bear_R']} mm", delta="OK" if _ss['b_bear_R']>=bear_min else f"Short by {bear_min-_ss['b_bear_R']:.1f}")
    st.markdown("---")
    section_hdr("D.2", "Transfer & Development")
    col1, col2, col3 = st.columns(3)
    col1.metric("l_t", f"{_ss['lb_l_t']:.0f} mm")
    col2.metric("l_d", f"{_ss['lb_l_d']:.0f} mm")
    col3.metric("d_ps", f"{get_ps_diameter_mm():.1f} mm")
    st.markdown(f'<span class="badge-{"ok" if _ss["lb_ps_status"]=="FULL" else "warn" if _ss["lb_ps_status"]=="PARTIAL" else "err"}">{_ss["lb_ps_status"]} prestress dev.</span>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# TAB E — Loads
# -----------------------------------------------------------------------------
with tab_E:
    section_hdr("E.1", "Self-weight")
    b_bot = _ss["b_bottom"]; h_hcs = _ss["h"]; wc = _ss["wc"]; A_void = _ss["A_voids_total"]
    gross_A = b_bot*h_hcs - A_void if _ss["hcs_type"]=="Full HCS (Hollow Core)" else b_bot*h_hcs
    SW_HCS = wc * (gross_A/(b_bot*1e6))
    SW_topping = _ss["wc_top"] * _ss["t_topping"]/1000 if _ss["has_topping"] else 0
    _ss["SW_HCS"], _ss["SW_topping"] = SW_HCS, SW_topping
    st.markdown(f"""<div class="metric-grid">{metric_card("SW_HCS", f"{SW_HCS:.3f}", "kN/m²")}{metric_card("SW_topping", f"{SW_topping:.3f}" if _ss["has_topping"] else "—", "kN/m²")}{metric_card("SW_total", f"{SW_HCS+SW_topping:.3f}", "kN/m²")}</div>""", unsafe_allow_html=True)
    st.markdown("---")
    section_hdr("E.2", "Superimposed Loads")
    col1, col2 = st.columns(2)
    with col1: _ss["SDL"] = st.number_input("SDL (kN/m²)", 0.0, 50.0, _ss["SDL"], 0.25, key="_SDL")
    with col2: _ss["LL"] = st.number_input("LL (kN/m²)", 0.0, 100.0, _ss["LL"], 0.25, key="_LL")
    st.markdown("---")
    section_hdr("E.3", "Point Loads")
    _ss["has_point_load"] = st.checkbox("Point loads", _ss["has_point_load"], key="_has_point_load")
    if _ss["has_point_load"]:
        col1, col2, col3 = st.columns(3)
        with col1: _ss["P1_DL"] = st.number_input("P1_DL (kN)", 0.0, step=0.5, value=_ss["P1_DL"], key="_P1_DL")
        with col2: _ss["P1_LL"] = st.number_input("P1_LL (kN)", 0.0, step=0.5, value=_ss["P1_LL"], key="_P1_LL")
        with col3: _ss["x_P1"] = st.number_input("x_P1 (mm)", 0, step=50, value=_ss["x_P1"], key="_x_P1")
        col1, col2, col3 = st.columns(3)
        with col1: _ss["P2_DL"] = st.number_input("P2_DL (kN)", 0.0, step=0.5, value=_ss["P2_DL"], key="_P2_DL")
        with col2: _ss["P2_LL"] = st.number_input("P2_LL (kN)", 0.0, step=0.5, value=_ss["P2_LL"], key="_P2_LL")
        with col3: _ss["x_P2"] = st.number_input("x_P2 (mm)", 0, step=50, value=_ss["x_P2"], key="_x_P2")
        _ss["slab_position"] = st.radio("Slab position", ["Interior slab", "Edge slab"],
                                         index=0 if _ss["slab_position"]=="Interior slab" else 1, horizontal=True, key="_slab_position")
    st.markdown("---")
    section_hdr("E.4", "Factored Load Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("wu (kN/m²)", f"{_ss['lb_wu_area']:.3f}")
    col2.metric("Vu_max (kN)", f"{_ss['lb_Vu_max']:.2f}")
    col3.metric("Mu_max (kN·m)", f"{_ss['lb_Mu_max']/1e6:.2f}")
    col4.metric("Ra (kN)", f"{_ss['lb_Ra_u']:.2f}")

# -----------------------------------------------------------------------------
# TAB F — Seismic
# -----------------------------------------------------------------------------
with tab_F:
    section_hdr("F.1", "Seismic Design Category")
    sdc_opts = ["A","B","C","D","E","F"]
    _ss["sdc"] = st.selectbox("SDC", sdc_opts, index=sdc_opts.index(_ss["sdc"]), key="_sdc")
    if _ss["sdc"] in ["D","E","F"]:
        st.error("SDC D/E/F: special detailing required. See ACI/PCI 319-25 Sec.12.")
    elif _ss["sdc"]=="C":
        st.warning("SDC C: intermediate requirements.")
    else:
        st.success(f"SDC {_ss['sdc']}: standard provisions.")
    st.markdown("---")
    section_hdr("F.2", "Structural Integrity")
    st.info("Integrity reinforcement will be checked in Phase 5.")

# -----------------------------------------------------------------------------
# TAB G — Section Properties (quick view)
# -----------------------------------------------------------------------------
with tab_G:
    st.markdown("## G · Section Properties")
    st.caption("Ref: ACI/PCI 319-25 Cl. 26.12 | Full detail in Appendix A")
    _g = _ss
    section_hdr("G.1", "Gross")
    st.markdown(f"""<div class="metric-grid">{metric_card("Ag", f"{_g.get('sp_Ag',0):,.0f}", "mm²")}{metric_card("yb_g", f"{_g.get('sp_yb_g',0):.1f}", "mm")}{metric_card("Ig", f"{_g.get('sp_Ig',0)/1e6:.3f}", "x10⁶ mm⁴")}</div>""", unsafe_allow_html=True)
    section_hdr("G.2", "Net")
    st.markdown(f"""<div class="metric-grid">{metric_card("An", f"{_g.get('sp_An',0):,.0f}", "mm²")}{metric_card("yb", f"{_g.get('sp_yb',0):.2f}", "mm")}{metric_card("In", f"{_g.get('sp_In',0)/1e6:.3f}", "x10⁶ mm⁴")}{metric_card("e_bot", f"{_g.get('sp_e_bot',0):.2f}", "mm")}</div>""", unsafe_allow_html=True)
    section_hdr("G.3", "Composite")
    if _g.get("has_topping") and _g.get("t_topping",0)>0:
        st.markdown(f"""<div class="metric-grid">{metric_card("A_comp", f"{_g.get('sp_A_comp',0):,.0f}", "mm²")}{metric_card("yb_comp", f"{_g.get('sp_yb_comp',0):.2f}", "mm")}{metric_card("I_comp", f"{_g.get('sp_I_comp',0)/1e6:.3f}", "x10⁶ mm⁴")}</div>""", unsafe_allow_html=True)
    else:
        st.info("No topping → composite = net.")

# -----------------------------------------------------------------------------
# TAB H — Stress Checks
# -----------------------------------------------------------------------------
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
        with col1:
            st.metric("Top fiber", f"{t['f_top']:.2f} MPa")
            st.caption(f"Limit comp: {t['limit_comp']:.1f} MPa, tens: {t['limit_tens']:.2f} MPa")
        with col2:
            st.metric("Bottom fiber", f"{t['f_bot']:.2f} MPa")
        st.caption(f"Status: {t['status']}")

        li = sc["sc_lifting"]
        st.markdown("### Lifting (after ES)")
        col1, col2 = st.columns(2)
        with col1: st.metric("Top fiber", f"{li['f_top']:.2f} MPa")
        with col2: st.metric("Bottom fiber", f"{li['f_bot']:.2f} MPa")
        st.caption(f"Status: {li['status']}")

        co = sc["sc_construction"]
        st.markdown("### Construction (topping + SDL, non-composite)")
        col1, col2 = st.columns(2)
        with col1: st.metric("Top fiber", f"{co['f_top']:.2f} MPa")
        with col2: st.metric("Bottom fiber", f"{co['f_bot']:.2f} MPa")
        st.caption(f"Status: {co['status']}")

        sv = sc["sc_service"]
        st.markdown(f"### Service (composite, class {sc.get('sc_service_class','T')})")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Top fiber", f"{sv['f_top']:.2f} MPa")
            st.caption(f"Limit comp: {sv['limit_comp']:.1f} MPa, tens: {sv['limit_tens']:.2f} MPa")
        with col2:
            st.metric("Bottom fiber", f"{sv['f_bot']:.2f} MPa")
        st.caption(f"Overall status: {sv['status']}")
        if sv['status'] == "NG":
            st.error("Stress check FAILED. Adjust section or prestress.")
        else:
            st.success("All stress checks passed.")

# -----------------------------------------------------------------------------
# TAB I — Capacity
# -----------------------------------------------------------------------------
with tab_I:
    st.markdown("## I · Flexural & Shear Capacity")
    st.caption("Ref: ACI/PCI 319-25 Cl. 22.2, 22.5, 22.6")
    cap = _ss
    if "cap_phi_Mn" not in cap:
        st.info("Calculating capacity...")
    else:
        st.markdown("### Flexural Capacity")
        col1, col2, col3 = st.columns(3)
        col1.metric("fps (stress in steel)", f"{cap['cap_fps']:.1f} MPa")
        col2.metric("Mn (nominal)", f"{cap['cap_Mn']:.1f} kN·m")
        col3.metric("φMn (design)", f"{cap['cap_phi_Mn']:.1f} kN·m")
        st.caption(f"Compression block depth a = {cap['cap_a']:.1f} mm")
        DCR_M = cap['cap_DCR_M']
        st.metric("Demand-Capacity Ratio (Mu/φMn)", f"{DCR_M:.2f}",
                  delta="OK" if DCR_M <= 1.0 else "OVERSTRESS",
                  delta_color="normal" if DCR_M <= 1.0 else "inverse")

        st.markdown("### Shear Capacity")
        col1, col2 = st.columns(2)
        col1.metric("Minimum φVn along span", f"{cap['cap_phi_Vn_min']:.1f} kN")
        col2.metric("Demand-Capacity Ratio (Vu/φVn)", f"{cap['cap_DCR_V']:.2f}")
        if cap['cap_needs_Av_min']:
            st.warning("⚠️ ACI/PCI requirement: h > 317mm, no topping, and Vu > 0.5φVcw → minimum shear reinforcement (Av,min) required.")
        else:
            st.info("No minimum shear reinforcement required per ACI/PCI 319-25.")

        if "cap_phi_Vn_arr" in cap and len(cap["cap_phi_Vn_arr"]) > 0:
            x_arr = _ss["lb_x_arr"] / 1000.0
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x_arr, y=cap["cap_phi_Vn_arr"], name="φVn (capacity)", line=dict(color="green", width=2)))
            fig.add_trace(go.Scatter(x=x_arr, y=abs(_ss["lb_Vu_arr"]), name="|Vu| (demand)", line=dict(color="red", width=2, dash="dash")))
            fig.update_layout(title="Shear Capacity vs Demand along span", xaxis_title="Distance from left support (m)", yaxis_title="Shear (kN)", height=400)
            st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB J — Deflection
# -----------------------------------------------------------------------------
with tab_J:
    st.markdown("## J · Deflection & Camber")
    st.caption("Ref: PCI Design Handbook 8th Ed. Sec. 4.8 & Table 4.8.3 | ACI 318-19 Table 24.2.2")
    d = _ss
    if "def_delta_ps_initial" not in d:
        st.info("Calculating deflections...")
    else:
        st.markdown("### Initial (at release)")
        col1, col2 = st.columns(2)
        col1.metric("Prestress camber", f"{d['def_delta_ps_initial']:.2f} mm (upward)")
        col2.metric("Self-weight deflection", f"{d['def_delta_sw']:.2f} mm (downward)")
        st.metric("Net deflection at release", f"{d['def_net_release']:.2f} mm")

        st.markdown("### Long-term (final stage)")
        col1, col2 = st.columns(2)
        col1.metric("Final camber", f"{d['def_delta_ps_initial'] * 2.0:.2f} mm (estimated)", help="Multiplier applied")
        col2.metric("Final self-weight + SDL + LL", f"{d['def_total_longterm']:.2f} mm")
        st.metric("Total net deflection (long-term)", f"{d['def_total_longterm']:.2f} mm")

        st.markdown("### Code Limit Checks (ACI 318-19 Table 24.2.2)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Limit LL deflection", f"L/360 = {d['def_limit_ll_mm']:.1f} mm")
        col2.metric("Limit total deflection", f"L/240 = {d['def_limit_total_mm']:.1f} mm")
        col3.metric("Actual total deflection", f"{d['def_total_longterm']:.1f} mm")

        status_ll = d['def_status_ll']
        status_total = d['def_status_total']
        st.markdown(f"**Live load deflection status:** {status_ll}  |  **Total deflection status:** {status_total}")
        if status_total == "NG":
            st.error("Total deflection exceeds code limit. Consider increasing section depth or prestress.")
        else:
            st.success("Deflection within code limits.")

# -----------------------------------------------------------------------------
# TAB K — REPORT GENERATOR (Phase 7)
# -----------------------------------------------------------------------------
with tab_K:
    st.markdown("## K · Report Generator")
    st.caption("Generate professional calculation report in Word or PDF format.")
    st.info("Reports include all design inputs, section properties, losses, stress checks, capacity, and deflection.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Generate Word Report (.docx)", use_container_width=True):
            with st.spinner("Generating Word report..."):
                word_bytes, _ = get_report_bytes(_ss)
                if word_bytes:
                    st.download_button(
                        label="Download Word Report",
                        data=word_bytes,
                        file_name=f"HCS_Design_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
                else:
                    st.error("Word generation failed. Please install python-docx.")
    with col2:
        if st.button("📑 Generate PDF Report", use_container_width=True):
            with st.spinner("Generating PDF report..."):
                _, pdf_bytes = get_report_bytes(_ss)
                if pdf_bytes:
                    st.download_button(
                        label="Download PDF Report",
                        data=pdf_bytes,
                        file_name=f"HCS_Design_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.error("PDF generation failed. Please install reportlab.")

    st.markdown("---")
    st.markdown("""
    **Note:** The report includes:
    - All input parameters
    - Transfer & development length
    - Section properties (gross, net, composite)
    - Prestress losses (ES, CR, SH, RE)
    - Stress checks (transfer, lifting, construction, service)
    - Flexural and shear capacity (Mn, Vn, DCR)
    - Deflection and camber (initial, long-term, code limits)
    - Remarks and code references
    """)

# -----------------------------------------------------------------------------
# TAB SUMMARY (placeholder)
# -----------------------------------------------------------------------------
with tab_sum:
    st.markdown("## Summary")
    st.info("Full summary table can be generated via Report tab.")

# -----------------------------------------------------------------------------
# TAB APPENDIX A (placeholder)
# -----------------------------------------------------------------------------
with tab_P2:
    st.markdown("## Appendix A: Detailed Section Properties")
    st.info("Detailed calculations are shown in the Report.")
