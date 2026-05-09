"""
pages/9_Footing.py
Isolated Spread Footing Design — Streamlit UI
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import io, sys, os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from footing.geometry import (
    compute_effective_depth, compute_footing_weights,
    compute_section_moduli, corner_pressures,
    punching_critical_perimeter,
)
from footing.soil_pressure import (
    bearing_capacity_all_spt, bearing_capacity_sondir,
    check_soil_pressure, factored_pressure,
    METHOD_GUIDANCE, SELECTION_ADVICE,
)
from footing.punching_shear import check_punching_shear, check_one_way_shear
from footing.reinforcement import (
    flexure_design_full, compute_design_moment, reinforcement_schedule,
)
from footing.settlement import (
    immediate_settlement, consolidation_settlement,
    stress_increase_boussinesq, check_settlement,
)
from footing.report_footing import build_report_lines, generate_word, generate_pdf

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Spread Footing Design", layout="wide")
st.title("🏗️ Isolated Spread Footing Design")
st.caption(
    "Ref: SNI 2847:2019 · SNI 8460:2017 · SNI 1726:2019 · SNI 1727:2020 | "
    "Meyerhof (1963) · Bowles (1996) · ACI 318-19"
)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📋 Project Info",
    "🧱 Material",
    "🌍 Soil Data",
    "📐 Geometry",
    "🏛️ Columns",
    "🔩 Reinforcement",
    "📊 Results",
    "🖨️ Print Report",
])

# ── TAB 0: PROJECT INFO ────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Project Information")
    c1, c2 = st.columns(2)
    with c1:
        proj_name = st.text_input("Project Name", "My Project")
        proj_loc  = st.text_input("Location", "Jakarta, Indonesia")
        proj_eng  = st.text_input("Engineer Name", "Ir. Engineer")
    with c2:
        proj_date  = st.date_input("Date", date.today())
        proj_docno = st.text_input("Document No.", "FTG-001")
        proj_notes = st.text_area("Notes", "", height=80)

# ── TAB 1: MATERIAL ────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("Material Properties")
    c1, c2, c3 = st.columns(3)
    with c1:
        fc  = st.number_input("f'c — Concrete strength (MPa)", 20.0, 60.0, 30.0, 1.0)
        fy  = st.number_input("fy — Main bar yield strength (MPa)", 240.0, 600.0, 420.0, 10.0)
        fy_s = st.number_input("fy shrinkage bar (MPa)", 240.0, 600.0, 280.0, 10.0)
    with c2:
        gamma_c = st.number_input("γ_c — Concrete unit weight (kN/m³)", 20.0, 26.0, 24.0, 0.5)
        gamma_s = st.number_input("γ_s — Soil unit weight (kN/m³)", 14.0, 22.0, 18.0, 0.5)
        lam = st.number_input("λ — Lightweight factor (1.0 = normal)", 0.75, 1.0, 1.0, 0.05)
    with c3:
        st.info(
            "**φ factors (SNI 2847:2019 Pasal 21.2):**\n"
            "- Shear: φ = 0.75\n"
            "- Flexure (tension-ctrl): φ = 0.90\n"
            "- Bearing: φ = 0.65"
        )

# ── TAB 2: SOIL DATA ────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("Soil Bearing Capacity")
    soil_method = st.radio(
        "Select input method:",
        ["Direct qa input", "SPT data", "Sondir / CPT data", "SPT + Sondir (use lower)"],
        horizontal=True,
    )

    Gwt = st.number_input("Groundwater table depth from surface (m) — leave 99 if deep",
                          0.0, 99.0, 99.0, 0.5)
    SF = st.number_input("Safety factor for bearing capacity", 2.0, 5.0, 3.0, 0.5)

    qa_direct = 150.0
    spt_depths, spt_N = [], []
    cpt_depths, cpt_qc, cpt_fs = [], [], []
    bearing_results = {}

    # ── Direct qa ──
    if soil_method == "Direct qa input":
        qa_direct = st.number_input("Allowable bearing capacity qa (kN/m²)", 50.0, 1000.0, 150.0, 10.0)
        qa_used = qa_direct
        method_used = "direct"
        st.info("Using direct input. No bearing capacity method calculation applied.")

    # ── SPT ──
    elif soil_method in ["SPT data", "SPT + Sondir (use lower)"]:
        st.markdown("#### SPT Data Input")
        col_dl, col_ul = st.columns([2, 1])
        with col_dl:
            # Download template
            spt_template_data = {
                "Depth_m": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "N_SPT_blows_30cm": [5, 8, 12, 15, 18, 22],
                "Soil_Description": ["Soft clay","Medium clay","Stiff clay","Dense sand","Dense sand","Very dense sand"],
                "Notes": ["","","","","",""],
            }
            spt_df_tmpl = pd.DataFrame(spt_template_data)
            buf_tmpl = io.BytesIO()
            spt_df_tmpl.to_excel(buf_tmpl, index=False)
            st.download_button("⬇️ Download SPT Template (.xlsx)",
                               buf_tmpl.getvalue(), "SPT_template.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col_ul:
            spt_input_mode = st.radio("Input mode", ["Manual table", "Upload Excel"], key="spt_mode")

        if spt_input_mode == "Manual table":
            n_spt = st.number_input("Number of SPT data points", 3, 30, 6, 1)
            spt_edit = pd.DataFrame({
                "Depth (m)": [float(i+1) for i in range(int(n_spt))],
                "N-SPT": [10] * int(n_spt),
            })
            spt_edited = st.data_editor(spt_edit, num_rows="fixed", key="spt_tbl")
            spt_depths = spt_edited["Depth (m)"].tolist()
            spt_N = spt_edited["N-SPT"].tolist()
        else:
            up = st.file_uploader("Upload SPT Excel", type=["xlsx", "xls", "csv"], key="spt_up")
            if up:
                if up.name.endswith(".csv"):
                    df_up = pd.read_csv(up)
                else:
                    df_up = pd.read_excel(up)
                spt_depths = df_up.iloc[:, 0].tolist()
                spt_N = df_up.iloc[:, 1].tolist()
                st.success(f"Loaded {len(spt_depths)} SPT records")
                st.dataframe(df_up.head(10))

        if len(spt_N) > 0:
            st.markdown("##### SPT Method Selection & Guidance")
            with st.expander("📖 Method comparison & selection advice", expanded=True):
                for key in ["meyerhof", "bowles", "sni"]:
                    mg = METHOD_GUIDANCE[key]
                    st.markdown(f"**{mg['name']}**")
                    st.markdown(f"- Suitable for: {mg['suitable_for']}")
                    st.markdown(f"- Advantage: {mg['advantage']}")
                    st.markdown(f"- Limitation: {mg['limitation']}")
                    st.markdown(f"- 🔴 Consequence: *{mg['consequence']}*")
                    st.markdown(f"- ✅ Recommended when: {mg['recommended_when']}")
                    st.divider()
                st.info(SELECTION_ADVICE)

            spt_method_choice = st.selectbox(
                "Select SPT method to use for qa_design:",
                ["SNI 8460:2017 (Required for formal reports)",
                 "Meyerhof (1963) — Conservative",
                 "Bowles (1996) — Moderate",
                 "Use LOWEST of all 3 methods (most conservative)"],
            )

    # ── Sondir ──
    if soil_method in ["Sondir / CPT data", "SPT + Sondir (use lower)"]:
        st.markdown("#### Sondir / CPT Data Input")
        col_dl2, _ = st.columns([2, 1])
        with col_dl2:
            cpt_tmpl = pd.DataFrame({
                "Depth_m": [0.2*i for i in range(1, 11)],
                "qc_kg_cm2": [5.0 + i*2 for i in range(10)],
                "fs_kg_cm2": [0.1 + i*0.05 for i in range(10)],
                "FR_pct": [2.0]*10,
                "Notes": [""]*10,
            })
            buf_cpt = io.BytesIO()
            cpt_tmpl.to_excel(buf_cpt, index=False)
            st.download_button("⬇️ Download Sondir Template (.xlsx)",
                               buf_cpt.getvalue(), "Sondir_template.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        cpt_mode = st.radio("Input mode", ["Manual table", "Upload Excel"], key="cpt_mode")
        if cpt_mode == "Manual table":
            n_cpt = st.number_input("Number of Sondir points", 5, 100, 10, 1)
            cpt_edit = pd.DataFrame({
                "Depth (m)": [0.2*(i+1) for i in range(int(n_cpt))],
                "qc (kg/cm²)": [10.0]*int(n_cpt),
                "fs (kg/cm²)": [0.2]*int(n_cpt),
            })
            cpt_ed = st.data_editor(cpt_edit, num_rows="fixed", key="cpt_tbl")
            cpt_depths = cpt_ed["Depth (m)"].tolist()
            cpt_qc    = cpt_ed["qc (kg/cm²)"].tolist()
            cpt_fs    = cpt_ed["fs (kg/cm²)"].tolist()
        else:
            up2 = st.file_uploader("Upload Sondir Excel", type=["xlsx","xls","csv"], key="cpt_up")
            if up2:
                df2 = pd.read_excel(up2) if not up2.name.endswith(".csv") else pd.read_csv(up2)
                cpt_depths = df2.iloc[:,0].tolist()
                cpt_qc    = df2.iloc[:,1].tolist()
                cpt_fs    = df2.iloc[:,2].tolist()
                st.success(f"Loaded {len(cpt_depths)} CPT records")

    # Settlement soil params
    st.markdown("---")
    st.markdown("#### Soil Parameters for Settlement")
    soil_type_settle = st.selectbox("Soil type (for settlement)", ["Sand", "Clay", "Mixed"])
    if soil_type_settle in ["Clay", "Mixed"]:
        c1s, c2s, c3s = st.columns(3)
        with c1s:
            Cc = st.number_input("Cc — compression index", 0.01, 2.0, 0.35, 0.01)
            Cs = st.number_input("Cs — recompression index", 0.001, 0.5, 0.05, 0.005)
        with c2s:
            e0 = st.number_input("e₀ — initial void ratio", 0.3, 3.0, 0.8, 0.05)
            Pc = st.number_input("Pc — preconsolidation pressure (kPa)", 10.0, 500.0, 100.0, 5.0)
        with c3s:
            Hc = st.number_input("Hc — clay layer thickness (m)", 0.5, 30.0, 5.0, 0.5)
            sigma_v0 = st.number_input("σ'v0 — eff. overburden at mid-layer (kPa)", 10.0, 400.0, 60.0, 5.0)
    if soil_type_settle in ["Sand", "Mixed"]:
        Es_kPa = st.number_input("Es — Elastic modulus of soil (kPa)", 1000.0, 80000.0, 15000.0, 500.0)
        nu_soil = st.number_input("ν — Poisson's ratio", 0.1, 0.49, 0.3, 0.05)

# ── TAB 3: GEOMETRY ─────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Footing Geometry")
    c1, c2 = st.columns(2)
    with c1:
        shape = st.radio("Shape", ["Square (B×B)", "Rectangular (B×L)"], horizontal=True)
        B = st.number_input("B — Footing width (m)", 0.5, 20.0, 2.5, 0.1)
        L = B if shape == "Square (B×B)" else st.number_input("L — Footing length (m)", 0.5, 20.0, 3.0, 0.1)
        t = st.number_input("t — Footing thickness (m)", 0.3, 3.0, 0.6, 0.05)
    with c2:
        Df   = st.number_input("Df — Foundation depth from surface (m)", 0.3, 10.0, 1.5, 0.1)
        h_soil = st.number_input("Soil above top of footing, h_soil (m) [0 = flush with ground]",
                                  0.0, Df, max(0.0, Df - t), 0.05)
        cover = st.number_input("Concrete cover (mm)", 50.0, 100.0, 75.0, 5.0)
        sloof_embedded = st.checkbox("Sloof embedded in footing thickness?", False)
        sloof_note = "Sloof embedded in footing" if sloof_embedded else "Sloof sits on top of footing"

    st.info(
        "**Sign convention:** X = horizontal right (+), Y = horizontal up (+) in plan view. "
        "Column positions x, y measured from footing centroid."
    )

# ── TAB 4: COLUMNS ──────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Column Data (Multi-Column)")
    n_cols = st.number_input("Number of columns on this footing", 1, 10, 1, 1)

    col_labels = []
    col_inputs = []
    for i in range(int(n_cols)):
        with st.expander(f"Column C{i+1}", expanded=(i == 0)):
            label = st.text_input("Label", f"C{i+1}", key=f"lbl{i}")
            r1, r2, r3 = st.columns(3)
            with r1:
                bc_i = st.number_input("bc (m) — col width in X", 0.2, 2.0, 0.4, 0.05, key=f"bc{i}")
                hc_i = st.number_input("hc (m) — col depth in Y", 0.2, 2.0, 0.4, 0.05, key=f"hc{i}")
                x_i  = st.number_input("x position (m)", -5.0, 5.0, 0.0, 0.1, key=f"xi{i}")
                y_i  = st.number_input("y position (m)", -5.0, 5.0, 0.0, 0.1, key=f"yi{i}")
            with r2:
                st.markdown("**Ultimate (factored) loads**")
                Nu_i  = st.number_input("Nu (kN)", -5000.0, 20000.0, 800.0, 10.0, key=f"Nu{i}")
                Mux_i = st.number_input("Mux (kN·m)", -2000.0, 2000.0, 50.0, 5.0, key=f"Mux{i}")
                Muy_i = st.number_input("Muy (kN·m)", -2000.0, 2000.0, 30.0, 5.0, key=f"Muy{i}")
                Vux_i = st.number_input("Vux (kN)", -500.0, 500.0, 20.0, 5.0, key=f"Vux{i}")
                Vuy_i = st.number_input("Vuy (kN)", -500.0, 500.0, 15.0, 5.0, key=f"Vuy{i}")
            with r3:
                st.markdown("**Service (unfactored) loads**")
                Ns_i  = st.number_input("Ns (kN)", -5000.0, 20000.0, 550.0, 10.0, key=f"Ns{i}")
                Msx_i = st.number_input("Msx (kN·m)", -2000.0, 2000.0, 35.0, 5.0, key=f"Msx{i}")
                Msy_i = st.number_input("Msy (kN·m)", -2000.0, 2000.0, 20.0, 5.0, key=f"Msy{i}")
                Vsx_i = st.number_input("Vsx (kN)", -500.0, 500.0, 15.0, 5.0, key=f"Vsx{i}")
                Vsy_i = st.number_input("Vsy (kN)", -500.0, 500.0, 10.0, 5.0, key=f"Vsy{i}")

            col_inputs.append({
                "label": label, "bc": bc_i, "hc": hc_i, "x": x_i, "y": y_i,
                "Nu": Nu_i, "Mux": Mux_i, "Muy": Muy_i, "Vux": Vux_i, "Vuy": Vuy_i,
                "Ns": Ns_i, "Msx": Msx_i, "Msy": Msy_i, "Vsx": Vsx_i, "Vsy": Vsy_i,
            })

# ── TAB 5: REINFORCEMENT PREFS ──────────────────────────────────────────────
with tabs[5]:
    st.subheader("Reinforcement Preferences")
    c1, c2 = st.columns(2)
    with c1:
        pref_dia_x = st.selectbox("Preferred bar dia — bottom X", [10,13,16,19,22,25,29,32], index=2)
        pref_dia_y = st.selectbox("Preferred bar dia — bottom Y", [10,13,16,19,22,25,29,32], index=2)
        pref_dia_top = st.selectbox("Preferred bar dia — top/shrinkage", [10,13,16,19,22,25], index=1)
    with c2:
        max_s = st.number_input("Max bar spacing (mm)", 100.0, 300.0, 300.0, 25.0)
        phi_flex = st.number_input("φ flexure (SNI 2847:2019 Pasal 21.2.1)", 0.85, 0.90, 0.90, 0.01)
        phi_shear = st.number_input("φ shear (SNI 2847:2019 Pasal 21.2.1)", 0.70, 0.75, 0.75, 0.01)

# ── TAB 6: RESULTS ────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("Calculation Results")

    if st.button("▶️ Run Calculation", type="primary"):

        # ── 1. Effective depth ────────────────────────────────────────────
        dx, dy = compute_effective_depth(t*1000, cover, pref_dia_x, pref_dia_y)
        d_use = dx  # use dx (larger) for shear

        # ── 2. Footing weights ────────────────────────────────────────────
        W_foot, W_soil, geo_detail = compute_footing_weights(
            B, L, t, h_soil, gamma_c, gamma_s, sloof_embedded)

        # ── 3. Bearing capacity ───────────────────────────────────────────
        qa_calc = {}
        if soil_method == "Direct qa input":
            qa_used = qa_direct
            method_name = "Direct Input"
            code_ref_bc = "Manual input by engineer"
        elif soil_method == "SPT data" and len(spt_N) > 0:
            Gwt_use = Gwt if Gwt < 99 else None
            bearing_results = bearing_capacity_all_spt(
                spt_depths, spt_N, B, L, Df, gamma_s, Gwt_use, SF)
            choice_map = {
                "SNI 8460:2017 (Required for formal reports)": "sni",
                "Meyerhof (1963) — Conservative": "meyerhof",
                "Bowles (1996) — Moderate": "bowles",
                "Use LOWEST of all 3 methods (most conservative)": "lowest",
            }
            chosen = choice_map.get(spt_method_choice, "sni")
            if chosen == "lowest":
                qa_used = min(bearing_results[k]["qa_kPa"] for k in bearing_results)
                method_name = "Lowest of Meyerhof/Bowles/SNI"
            else:
                qa_used = bearing_results[chosen]["qa_kPa"]
                method_name = bearing_results[chosen]["method"]
            code_ref_bc = bearing_results.get("sni", {}).get("code_ref", "SNI 8460:2017")

            # Show comparison table
            st.markdown("##### Bearing Capacity Method Comparison")
            comp_data = []
            for k, v in bearing_results.items():
                comp_data.append({
                    "Method": v["method"],
                    "qu (kN/m²)": f"{v['qu_kPa']:.1f}",
                    "qa (kN/m²)": f"{v['qa_kPa']:.1f}",
                    "SF": SF,
                })
            st.table(pd.DataFrame(comp_data))
            st.success(f"**Selected qa = {qa_used:.1f} kN/m²** ({method_name})")

        elif soil_method == "Sondir / CPT data" and len(cpt_qc) > 0:
            cpt_res = bearing_capacity_sondir(
                cpt_depths, cpt_qc, cpt_fs, B, L, Df, SF)
            qa_used = cpt_res["qa_kPa"]
            method_name = cpt_res["method"]
            code_ref_bc = cpt_res["code_ref"]
            st.info(f"Sondir: {cpt_res['formula_str']} → qa = {qa_used:.1f} kN/m²")
        else:
            qa_used = qa_direct
            method_name = "Direct Input"
            code_ref_bc = "Manual input"

        # ── 4. Service loads ──────────────────────────────────────────────
        sum_Ns_col  = sum(c["Ns"]  for c in col_inputs)
        sum_Msx_col = sum(c["Msx"] for c in col_inputs)
        sum_Msy_col = sum(c["Msy"] for c in col_inputs)
        arm_V = t + h_soil
        Msx_from_V  = sum(c["Vsy"] * arm_V for c in col_inputs)
        Msy_from_V  = sum(c["Vsx"] * arm_V for c in col_inputs)
        sum_Msx_tot = sum_Msx_col + Msx_from_V
        sum_Msy_tot = sum_Msy_col + Msy_from_V
        sum_Ns_total= sum_Ns_col + W_foot + W_soil

        # ── 5. Soil pressure check ────────────────────────────────────────
        A_ft, Wx, Wy = compute_section_moduli(B, L)
        q1, q2, q3, q4 = corner_pressures(sum_Ns_total, sum_Msx_tot, sum_Msy_tot, A_ft, Wx, Wy)
        pcheck = check_soil_pressure(q1, q2, q3, q4, qa_used, B, L,
                                     sum_Ns_total, sum_Msx_tot, sum_Msy_tot, A_ft, Wx, Wy)
        pcheck.update({"q1": q1, "q2": q2, "q3": q3, "q4": q4})

        # ── 6. Factored loads ─────────────────────────────────────────────
        sum_Nu_total = sum(c["Nu"] for c in col_inputs) + W_foot + W_soil
        sum_Mux_tot  = sum(c["Mux"] + c["Vuy"]*arm_V for c in col_inputs)
        sum_Muy_tot  = sum(c["Muy"] + c["Vux"]*arm_V for c in col_inputs)
        fp = factored_pressure(sum_Nu_total, sum_Mux_tot, sum_Muy_tot, A_ft, Wx, Wy)
        qu_avg = fp["qu_avg_kPa"]

        # ── 7. Structural checks ──────────────────────────────────────────
        punch_results = {}
        for col in col_inputs:
            bo, b_crit, h_crit = punching_critical_perimeter(
                col["bc"], col["hc"], dx, B, L)
            beta = max(col["hc"] / col["bc"], col["bc"] / col["hc"])
            pr = check_punching_shear(
                fc, bo, dx, beta, 40, qu_avg, B, L, b_crit, h_crit,
                col["Nu"], lam, phi_shear)
            punch_results[col["label"]] = pr

        # Representative column (first or centroidal)
        rep = col_inputs[0]
        ow_result = check_one_way_shear(
            fc, B, L, dx, qu_avg,
            rep["bc"], rep["hc"], rep["x"], rep["y"], lam, phi_shear)

        # Moments
        Mu_x, Mu_y, mom_detail = compute_design_moment(
            qu_avg, B, L, rep["bc"], rep["hc"], rep["x"], rep["y"])

        flex_results = []
        for (direction, Mu, b_dim, d_mm, pdia) in [
            ("X", Mu_x, L, dx, pref_dia_x),   # X-bars: bending about X → width = L (for moment strip)
            ("Y", Mu_y, B, dy, pref_dia_y),
        ]:
            fr = flexure_design_full(
                Mu, fc, fy, b_dim, d_mm, t*1000,
                direction, "Bottom", pdia, max_s, phi_flex)
            flex_results.append(fr)
        # Top (shrinkage)
        for (direction, b_dim, d_mm) in [("X", L, dx), ("Y", B, dy)]:
            fr_top = flexure_design_full(
                0.0, fc, fy, b_dim, d_mm, t*1000,
                direction, "Top", pref_dia_top, max_s, phi_flex)
            flex_results.append(fr_top)

        # ── 8. Settlement ─────────────────────────────────────────────────
        q_net = sum_Ns_total / A_ft - gamma_s * Df
        delta_i_mm, settle_i_detail = 0.0, {}
        delta_c_mm, settle_c_detail = 0.0, {}

        if soil_type_settle in ["Sand", "Mixed"]:
            delta_i_mm, settle_i_detail = immediate_settlement(
                q_net, B, L, Es_kPa, nu_soil, Df)
        if soil_type_settle in ["Clay", "Mixed"]:
            delta_sig, _ = stress_increase_boussinesq(q_net, B, L, Hc / 2)
            delta_c_mm, settle_c_detail = consolidation_settlement(
                Cc, Cs, e0, Hc, sigma_v0, Pc, delta_sig)

        settle_check = check_settlement(delta_i_mm, delta_c_mm)

        # ── 9. Display results ─────────────────────────────────────────────
        st.markdown("---")
        ok_icon = lambda b: "✅" if b else "❌"

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.metric("q_max (service)", f"{pcheck['q_max_kPa']:.1f} kN/m²",
                      f"qa = {qa_used:.1f} kN/m²")
            st.write(ok_icon(pcheck["ok_bearing"]) + " Bearing capacity")
            st.write(ok_icon(pcheck["ok_no_uplift"]) + " No uplift")
        with col_r2:
            st.write(ok_icon(pcheck["ok_ex"]) + f" Eccentricity ex = {pcheck['ex_m']:.3f} m (limit {B/6:.3f})")
            st.write(ok_icon(pcheck["ok_ey"]) + f" Eccentricity ey = {pcheck['ey_m']:.3f} m (limit {L/6:.3f})")
            for lbl, pr in punch_results.items():
                st.write(ok_icon(pr["ok"]) + f" Punching {lbl}: Vu={pr['Vu_kN']:.1f} / φVc={pr['phiVc_kN']:.1f} kN")
        with col_r3:
            st.write(ok_icon(ow_result["x_dir"]["ok"]) + f" 1-Way shear X: {ow_result['x_dir']['Vu_kN']:.1f}/{ow_result['x_dir']['phiVc_kN']:.1f} kN")
            st.write(ok_icon(ow_result["y_dir"]["ok"]) + f" 1-Way shear Y: {ow_result['y_dir']['Vu_kN']:.1f}/{ow_result['y_dir']['phiVc_kN']:.1f} kN")
            st.write(ok_icon(settle_check["ok_total"]) + f" Settlement: {settle_check['delta_total_mm']:.1f}/{settle_check['allow_total_mm']} mm")

        # Reinforcement schedule
        st.markdown("#### Reinforcement Schedule")
        sched = reinforcement_schedule(flex_results)
        st.dataframe(pd.DataFrame(sched), use_container_width=True)

        # Sketch
        st.markdown("#### Footing Sketch")
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Plan view
        ax = axes[0]
        ax.set_aspect("equal")
        rect = mpatches.Rectangle((-B/2, -L/2), B, L, lw=2, edgecolor='navy', facecolor='#e8f4f8')
        ax.add_patch(rect)
        for col in col_inputs:
            cr = mpatches.Rectangle(
                (col["x"] - col["bc"]/2, col["y"] - col["hc"]/2),
                col["bc"], col["hc"], lw=1.5, edgecolor='red', facecolor='#ffcccc')
            ax.add_patch(cr)
            ax.text(col["x"], col["y"], col["label"], ha='center', va='center', fontsize=8, color='red')
        ax.set_xlim(-B/2 - 0.3, B/2 + 0.3)
        ax.set_ylim(-L/2 - 0.3, L/2 + 0.3)
        ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
        ax.set_title("Plan View — Footing")
        ax.axhline(0, color='gray', lw=0.5, ls='--')
        ax.axvline(0, color='gray', lw=0.5, ls='--')
        ax.annotate(f"B={B}m", xy=(0, -L/2-0.2), ha='center', fontsize=8)
        ax.annotate(f"L={L}m", xy=(-B/2-0.2, 0), ha='center', fontsize=8, rotation=90)

        # Section view
        ax2 = axes[1]
        ax2.set_aspect("equal")
        # Footing body
        foot_rect = mpatches.Rectangle((0, 0), B, t, lw=2, edgecolor='navy', facecolor='#e8f4f8')
        ax2.add_patch(foot_rect)
        # Soil above
        soil_rect = mpatches.Rectangle((0, t), B, h_soil, lw=1, edgecolor='brown',
                                        facecolor='#d2b48c', alpha=0.5)
        ax2.add_patch(soil_rect)
        ax2.set_xlim(-0.2, B + 0.5)
        ax2.set_ylim(-0.3, t + h_soil + 0.5)
        ax2.annotate(f"t={t}m", xy=(B+0.1, t/2), fontsize=8, color='navy')
        ax2.annotate(f"h_soil={h_soil}m", xy=(B+0.1, t+h_soil/2), fontsize=8, color='brown')
        ax2.annotate(f"cover={cover:.0f}mm", xy=(0.05, 0.05), fontsize=7, color='gray')
        ax2.annotate(f"dx={dx:.0f}mm", xy=(0.05, 0.15), fontsize=7, color='blue')
        ax2.set_xlabel("X (m)"); ax2.set_ylabel("Z (m)")
        ax2.set_title("Section A-A (X-direction)")

        st.pyplot(fig)
        fig_buf = io.BytesIO()
        fig.savefig(fig_buf, format="png", dpi=120, bbox_inches="tight")
        fig_buf.seek(0)
        fig_bytes = fig_buf.read()
        plt.close(fig)

        # Store for report
        st.session_state["_footing_report_data"] = {
            "proj": {
                "name": proj_name, "location": proj_loc, "engineer": proj_eng,
                "date": str(proj_date), "doc_no": proj_docno, "notes": proj_notes,
            },
            "mat": {
                "fc": fc, "fy": fy, "fy_s": fy_s, "gamma_c": gamma_c,
                "gamma_s": gamma_s, "lambda": lam,
            },
            "geo": {
                "shape": shape, "B": B, "L": L, "t": t, "Df": Df,
                "h_soil": h_soil, "cover": cover, "sloof_note": sloof_note,
            },
            "columns_data": col_inputs,
            "soil_result": {
                "method_name": method_name,
                "code_ref": code_ref_bc,
                "qa_kPa": qa_used,
                "geo_detail": geo_detail,
                "service_check": {
                    "sum_Ns_col": sum_Ns_col,
                    "W_foot": W_foot, "W_soil": W_soil,
                    "sum_Ns_total": sum_Ns_total,
                    "sum_Msx_col": sum_Msx_col, "Msx_from_V": Msx_from_V,
                    "sum_Msy_col": sum_Msy_col, "Msy_from_V": Msy_from_V,
                    "sum_Msx_total": sum_Msx_tot, "sum_Msy_total": sum_Msy_tot,
                },
                "pressure_check": pcheck,
            },
            "struct_result": {
                "qu_avg_kPa": qu_avg,
                "sum_Nu_total": sum_Nu_total,
                "eff_depth": {"dx": dx, "dy": dy, "bar_x_mm": pref_dia_x, "bar_y_mm": pref_dia_y},
                "punching": punch_results,
                "one_way": ow_result,
                "flexure": flex_results,
                "summary_checks": [
                    ["Soil bearing (q_max)", f"{pcheck['q_max_kPa']:.1f} kPa", f"{qa_used:.1f} kPa", "✓ OK" if pcheck["ok_bearing"] else "✗ FAIL"],
                    ["Eccentricity ex", f"{pcheck['ex_m']:.4f} m", f"B/6={B/6:.4f} m", "✓ OK" if pcheck["ok_ex"] else "✗ FAIL"],
                    ["Eccentricity ey", f"{pcheck['ey_m']:.4f} m", f"L/6={L/6:.4f} m", "✓ OK" if pcheck["ok_ey"] else "✗ FAIL"],
                ] + [
                    [f"Punching shear {lbl}", f"{pr['Vu_kN']:.1f} kN", f"{pr['phiVc_kN']:.1f} kN", "✓ OK" if pr["ok"] else "✗ FAIL"]
                    for lbl, pr in punch_results.items()
                ] + [
                    ["One-way shear X", f"{ow_result['x_dir']['Vu_kN']:.1f} kN", f"{ow_result['x_dir']['phiVc_kN']:.1f} kN", "✓ OK" if ow_result["x_dir"]["ok"] else "✗ FAIL"],
                    ["One-way shear Y", f"{ow_result['y_dir']['Vu_kN']:.1f} kN", f"{ow_result['y_dir']['phiVc_kN']:.1f} kN", "✓ OK" if ow_result["y_dir"]["ok"] else "✗ FAIL"],
                ] + [
                    [f"Flexure {fr['location']} {fr['direction']}", f"{fr['Mu_kNm']:.1f} kN·m", f"{fr['phi_Mn_kNm']:.1f} kN·m", "✓ OK" if fr["ok_strength"] else "✗ FAIL"]
                    for fr in flex_results
                ] + [
                    ["Settlement (total)", f"{settle_check['delta_total_mm']:.1f} mm", f"{settle_check['allow_total_mm']} mm", "✓ OK" if settle_check["ok_total"] else "✗ FAIL"],
                ],
            },
            "settle_result": {
                "immediate": settle_i_detail if settle_i_detail else None,
                "consolidation": settle_c_detail if settle_c_detail else None,
                "check": settle_check,
            },
            "fig_bytes": fig_bytes,
        }
        st.success("✅ Calculation complete. Go to **Print Report** tab to download.")

# ── TAB 7: PRINT ─────────────────────────────────────────────────────────────
with tabs[7]:
    st.subheader("Download Report")
    if "_footing_report_data" not in st.session_state:
        st.info("Run the calculation first in the **Results** tab.")
    else:
        d = st.session_state["_footing_report_data"]
        lines = build_report_lines(
            d["proj"], d["mat"], d["geo"],
            d["columns_data"], d["soil_result"],
            d["struct_result"], d["settle_result"],
        )
        col_w, col_p = st.columns(2)
        with col_w:
            try:
                word_bytes = generate_word(lines, [d.get("fig_bytes")])
                st.download_button(
                    "📄 Download Word (.docx)",
                    word_bytes,
                    f"footing_{d['proj']['doc_no']}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except Exception as e:
                st.error(f"Word error: {e}")
        with col_p:
            try:
                pdf_bytes = generate_pdf(lines, [d.get("fig_bytes")])
                st.download_button(
                    "📑 Download PDF",
                    pdf_bytes,
                    f"footing_{d['proj']['doc_no']}.pdf",
                    "application/pdf",
                )
            except Exception as e:
                st.error(f"PDF error: {e}")

        st.markdown("#### Report Preview")
        st.code("\n".join(lines[:80]) + "\n... (truncated — download for full report)", language="text")
