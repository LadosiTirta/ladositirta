"""
pages/10_StripFooting.py
Continuous / Strip Footing Design — Streamlit UI
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import io, sys, os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from footing.geometry import compute_effective_depth, compute_footing_weights
from footing.soil_pressure import (
    bearing_capacity_all_spt, bearing_capacity_sondir,
    check_soil_pressure, METHOD_GUIDANCE, SELECTION_ADVICE,
)
from footing.settlement import (
    immediate_settlement, consolidation_settlement,
    stress_increase_boussinesq, check_settlement,
)
from footing_strip.geometry import strip_section_moduli, strip_corner_pressures
from footing_strip.shear import check_one_way_shear_strip
from footing_strip.reinforcement import (
    flexure_design_strip, reinforcement_schedule_strip,
)
from footing_strip.report import build_strip_report_lines, generate_word, generate_pdf

# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Strip Footing Design", layout="wide")
st.title("🧱 Continuous Strip Footing Design")
st.caption(
    "Ref: SNI 2847:2019 · SNI 8460:2017 · SNI 1726:2019 · SNI 1727:2020 | "
    "ACI 318-19"
)

tabs = st.tabs([
    "📋 Project Info",
    "🧱 Material",
    "🌍 Soil Data",
    "📐 Geometry & Wall",
    "🔩 Reinforcement Prefs",
    "📊 Results",
    "🖨️ Print Report",
])

# ── TAB 0: PROJECT INFO ────────────────────────────────────
with tabs[0]:
    st.subheader("Project Information")
    c1, c2 = st.columns(2)
    with c1:
        proj_name = st.text_input("Project Name", "My Strip Footing Project")
        proj_loc  = st.text_input("Location", "Jakarta, Indonesia")
        proj_eng  = st.text_input("Engineer Name", "Ir. Engineer")
    with c2:
        proj_date  = st.date_input("Date", date.today())
        proj_docno = st.text_input("Document No.", "STF-001")
        proj_notes = st.text_area("Notes", "", height=80)

# ── TAB 1: MATERIAL ────────────────────────────────────────
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

# ── TAB 2: SOIL DATA ────────────────────────────────────────
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

    if soil_method == "Direct qa input":
        qa_direct = st.number_input("Allowable bearing capacity qa (kN/m²)", 50.0, 1000.0, 150.0, 10.0)

    elif soil_method in ["SPT data", "SPT + Sondir (use lower)"]:
        st.markdown("#### SPT Data Input")
        col_dl, col_ul = st.columns([2, 1])
        with col_dl:
            spt_template_data = {
                "Depth_m": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "N_SPT_blows_30cm": [5, 8, 12, 15, 18, 22],
                "Soil_Description": ["Soft clay","Medium clay","Stiff clay","Dense sand","Dense sand","Very dense sand"],
                "Notes": [""]*6,
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
                df_up = pd.read_excel(up) if not up.name.endswith(".csv") else pd.read_csv(up)
                spt_depths = df_up.iloc[:, 0].tolist()
                spt_N = df_up.iloc[:, 1].tolist()
                st.success(f"Loaded {len(spt_depths)} SPT records")

        if len(spt_N) > 0:
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

# ── TAB 3: GEOMETRY & WALL ─────────────────────────────────
with tabs[3]:
    st.subheader("Footing Geometry & Wall Load")
    c1, c2 = st.columns(2)
    with c1:
        B = st.number_input("B — Footing width (m)", 0.5, 10.0, 1.5, 0.1)
        t = st.number_input("t — Footing thickness (m)", 0.3, 2.0, 0.5, 0.05)
        Df   = st.number_input("Df — Foundation depth from surface (m)", 0.3, 10.0, 1.2, 0.1)
        h_soil = st.number_input("Soil above top of footing, h_soil (m) [0 = flush with ground]",
                                  0.0, Df, max(0.0, Df - t), 0.05)
    with c2:
        bw = st.number_input("Wall thickness bw (m)", 0.15, 1.0, 0.3, 0.05)
        L_strip = st.number_input("Strip length considered L (m) — for per‑meter load conversion",
                                  1.0, 100.0, 10.0, 0.5)
        cover = st.number_input("Concrete cover (mm)", 50.0, 100.0, 75.0, 5.0)
        sloof_embedded = st.checkbox("Sloof embedded in footing thickness?", False)

    st.markdown("### Wall Loads")
    load_mode = st.radio("Load input mode:", ["Line load (kN/m)", "Total load over strip length L"])
    if load_mode == "Line load (kN/m)":
        NS_kNm = st.number_input("NS — Service axial load per meter (kN/m)", 0.0, 5000.0, 120.0, 5.0)
        Nu_kNm = st.number_input("Nu — Factored axial load per meter (kN/m)", 0.0, 8000.0, 180.0, 5.0)
        MSx_kNm = st.number_input("MSx — Service moment about X‑axis per meter (kN·m/m)", 0.0, 1000.0, 0.0, 1.0)
        Mux_kNm = st.number_input("Mux — Factored moment about X‑axis per meter (kN·m/m)", 0.0, 1500.0, 0.0, 1.0)
        VSx_kN = st.number_input("VSx — Service shear per meter (kN/m)", 0.0, 500.0, 0.0, 1.0)
        Vux_kN = st.number_input("Vux — Factored shear per meter (kN/m)", 0.0, 750.0, 0.0, 1.0)
    else:
        Ns_total = st.number_input("Total service axial load over length L (kN)", 0.0, 50000.0, 1200.0, 10.0)
        Nu_total = st.number_input("Total factored axial load over length L (kN)", 0.0, 80000.0, 1800.0, 10.0)
        Ms_total = st.number_input("Total service moment about X‑axis over L (kN·m)", 0.0, 10000.0, 0.0, 10.0)
        Mu_total = st.number_input("Total factored moment about X‑axis over L (kN·m)", 0.0, 15000.0, 0.0, 10.0)
        Vs_total = st.number_input("Total service shear over L (kN)", 0.0, 5000.0, 0.0, 10.0)
        Vu_total = st.number_input("Total factored shear over L (kN)", 0.0, 7500.0, 0.0, 10.0)
        NS_kNm = Ns_total / L_strip
        Nu_kNm = Nu_total / L_strip
        MSx_kNm = Ms_total / L_strip
        Mux_kNm = Mu_total / L_strip
        VSx_kN = Vs_total / L_strip
        Vux_kN = Vu_total / L_strip
        st.caption(f"Converted to line loads: NS = {NS_kNm:.2f} kN/m, Nu = {Nu_kNm:.2f} kN/m, etc.")

# ── TAB 5: REINFORCEMENT PREFS ─────────────────────────────
with tabs[5]:
    st.subheader("Reinforcement Preferences")
    c1, c2 = st.columns(2)
    with c1:
        pref_dia_trans = st.selectbox("Preferred bar dia — transverse (bottom)", [10,13,16,19,22,25,29,32], index=2)
        pref_dia_long  = st.selectbox("Preferred bar dia — longitudinal (bottom)", [10,13,16,19,22,25,29,32], index=2)
        pref_dia_top   = st.selectbox("Preferred bar dia — top/shrinkage", [10,13,16,19,22,25], index=1)
    with c2:
        max_s = st.number_input("Max bar spacing (mm)", 100.0, 300.0, 300.0, 25.0)
        phi_flex = st.number_input("φ flexure (SNI 2847:2019 Pasal 21.2.1)", 0.85, 0.90, 0.90, 0.01)
        phi_shear = st.number_input("φ shear (SNI 2847:2019 Pasal 21.2.1)", 0.70, 0.75, 0.75, 0.01)

# ── TAB 6: RESULTS ────────────────────────────────────────
with tabs[6]:
    st.subheader("Calculation Results")

    if st.button("▶️ Run Calculation", type="primary"):

        # 1. Effective depth
        dx, dy = compute_effective_depth(t*1000, cover, pref_dia_trans, pref_dia_long)
        d_use = dx   # for shear, use dx (larger)

        # 2. Footing weights (per meter length)
        # compute_footing_weights expects B & L; for strip we use B & L=1m to get weight per meter
        W_foot, W_soil, geo_detail = compute_footing_weights(
            B, 1.0, t, h_soil, gamma_c, gamma_s, sloof_embedded)
        # total weight per meter = W_foot + W_soil (already per metre because L=1)

        # 3. Bearing capacity
        if soil_method == "Direct qa input":
            qa_used = qa_direct
            method_name = "Direct Input"
            code_ref_bc = "Manual input by engineer"
        elif soil_method == "SPT data" and len(spt_N) > 0:
            Gwt_use = Gwt if Gwt < 99 else None
            bearing_results = bearing_capacity_all_spt(
                spt_depths, spt_N, B, 1.0, Df, gamma_s, Gwt_use, SF)
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
                cpt_depths, cpt_qc, cpt_fs, B, 1.0, Df, SF)
            qa_used = cpt_res["qa_kPa"]
            method_name = cpt_res["method"]
            code_ref_bc = cpt_res["code_ref"]
            st.info(f"Sondir: {cpt_res['formula_str']} → qa = {qa_used:.1f} kN/m²")
        else:
            qa_used = qa_direct
            method_name = "Direct Input"
            code_ref_bc = "Manual input"

        # 4. Service loads (per meter)
        N_service = NS_kNm + W_foot + W_soil   # kN/m
        arm_V = t + h_soil
        Mx_service = MSx_kNm + VSx_kN * arm_V  # moment about X per meter

        # 5. Soil pressure check (per meter width)
        A_strip, Wx_strip = strip_section_moduli(B)  # per m length
        q1, q2 = strip_corner_pressures(N_service, Mx_service, A_strip, Wx_strip)
        pcheck = check_soil_pressure(q1, q2, q1, q2, qa_used, B, 1.0,
                                     N_service, Mx_service, 0.0, A_strip, Wx_strip, Wx_strip)
        # Note: adjust for 2 corners only; reuse generic check
        pcheck["q_max_kPa"] = max(q1, q2)
        pcheck["q_min_kPa"] = min(q1, q2)
        pcheck["ok_bearing"] = pcheck["q_max_kPa"] <= qa_used
        pcheck["ok_no_uplift"] = pcheck["q_min_kPa"] >= 0

        # Eccentricity
        ex = abs(Mx_service) / N_service if N_service > 0 else 0
        pcheck["ex_m"] = ex
        pcheck["ok_ex"] = ex <= B / 6

        # 6. Factored loads (per meter)
        Nu_total_m = Nu_kNm + W_foot + W_soil
        Mu_total_m = Mux_kNm + Vux_kN * arm_V
        qu_avg = Nu_total_m / A_strip  # factored soil pressure (average)

        # 7. One-way shear (transverse direction)
        ow_result = check_one_way_shear_strip(
            fc, B, d_use, qu_avg, bw, phi_shear, lam)

        # 8. Flexural design
        flex = flexure_design_strip(
            qu_avg, B, bw, fc, fy, fy_s, t*1000, d_use, dx,
            pref_dia_trans, pref_dia_long, pref_dia_top,
            max_s, phi_flex)

        # 9. Settlement
        q_net = N_service / A_strip - gamma_s * Df
        delta_i_mm, settle_i_detail = 0.0, {}
        delta_c_mm, settle_c_detail = 0.0, {}
        if soil_type_settle in ["Sand", "Mixed"]:
            delta_i_mm, settle_i_detail = immediate_settlement(
                q_net, B, 1.0, Es_kPa, nu_soil, Df)
        if soil_type_settle in ["Clay", "Mixed"]:
            delta_sig, _ = stress_increase_boussinesq(q_net, B, 1.0, Hc / 2)
            delta_c_mm, settle_c_detail = consolidation_settlement(
                Cc, Cs, e0, Hc, sigma_v0, Pc, delta_sig)
        settle_check = check_settlement(delta_i_mm, delta_c_mm)

        # ── Display results ──────────────────────────
        ok_icon = lambda b: "✅" if b else "❌"
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.metric("q_max (service)", f"{pcheck['q_max_kPa']:.1f} kN/m²",
                      f"qa = {qa_used:.1f} kN/m²")
            st.write(ok_icon(pcheck["ok_bearing"]) + " Bearing capacity")
            st.write(ok_icon(pcheck["ok_no_uplift"]) + " No uplift")
            st.write(ok_icon(pcheck["ok_ex"]) + f" Eccentricity ex = {ex:.4f} m (limit B/6={B/6:.4f})")
        with col_r2:
            st.write(ok_icon(ow_result["ok"]) + f" One-way shear: Vu={ow_result['Vu_kN']:.1f} / φVc={ow_result['phiVc_kN']:.1f} kN")
            st.write(ok_icon(settle_check["ok_total"]) + f" Settlement: {settle_check['delta_total_mm']:.1f}/{settle_check['allow_total_mm']} mm")

        # Reinforcement schedule
        st.markdown("#### Reinforcement Schedule")
        sched = reinforcement_schedule_strip(flex)
        st.dataframe(pd.DataFrame(sched), use_container_width=True)

        # Sketch
        st.markdown("#### Footing Sketch")
        fig, ax = plt.subplots(figsize=(8, 4))
        # Section view
        ax.add_patch(mpatches.Rectangle((0, 0), B, t, ec='navy', fc='#e8f4f8'))
        ax.add_patch(mpatches.Rectangle((0, t), B, h_soil, ec='brown', fc='#d2b48c', alpha=0.5))
        # Wall
        ax.add_patch(mpatches.Rectangle(((B - bw) / 2, t), bw, 0.5, ec='red', fc='#ffcccc'))
        ax.set_xlim(-0.2, B + 0.2)
        ax.set_ylim(-0.3, t + h_soil + 0.6)
        ax.set_xlabel("Width B (m)")
        ax.set_ylabel("Depth (m)")
        ax.set_title("Strip Footing Section")
        ax.annotate(f"B={B}m, t={t}m", xy=(B/2, t/2), ha='center', fontsize=9, color='navy')
        st.pyplot(fig)

        fig_buf = io.BytesIO()
        fig.savefig(fig_buf, format="png", dpi=120, bbox_inches="tight")
        fig_buf.seek(0)
        fig_bytes = fig_buf.read()
        plt.close(fig)

        # Store for report
        st.session_state["_strip_report_data"] = {
            "proj": {
                "name": proj_name, "location": proj_loc, "engineer": proj_eng,
                "date": str(proj_date), "doc_no": proj_docno, "notes": proj_notes,
            },
            "mat": {"fc": fc, "fy": fy, "fy_s": fy_s, "gamma_c": gamma_c,
                    "gamma_s": gamma_s, "lambda": lam},
            "geo": {"B": B, "t": t, "Df": Df, "h_soil": h_soil, "bw": bw,
                    "cover": cover, "L_strip": L_strip, "load_mode": load_mode},
            "loads": {
                "NS_kNm": NS_kNm, "Nu_kNm": Nu_kNm,
                "MSx_kNm": MSx_kNm, "Mux_kNm": Mux_kNm,
                "VSx_kN": VSx_kN, "Vux_kN": Vux_kN,
                "W_foot_kNm": W_foot, "W_soil_kNm": W_soil,
            },
            "soil_result": {
                "method_name": method_name, "code_ref": code_ref_bc,
                "qa_kPa": qa_used,
                "pressure_check": pcheck,
            },
            "struct_result": {
                "qu_avg_kPa": qu_avg,
                "eff_depth": {"dx": dx, "dy": dy},
                "one_way": ow_result,
                "flexure": flex,
            },
            "settle_result": {
                "immediate": settle_i_detail if settle_i_detail else None,
                "consolidation": settle_c_detail if settle_c_detail else None,
                "check": settle_check,
            },
            "fig_bytes": fig_bytes,
        }
        st.success("✅ Calculation complete. Go to **Print Report** tab to download.")

# ── TAB 7: PRINT REPORT ──────────────────────────────────
with tabs[6]:
    st.subheader("Download Report")
    if "_strip_report_data" not in st.session_state:
        st.info("Run the calculation first in the **Results** tab.")
    else:
        d = st.session_state["_strip_report_data"]
        lines = build_strip_report_lines(d)
        col_w, col_p = st.columns(2)
        with col_w:
            try:
                word_bytes = generate_word(lines, [d.get("fig_bytes")])
                st.download_button(
                    "📄 Download Word (.docx)",
                    word_bytes,
                    f"strip_footing_{d['proj']['doc_no']}.docx",
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
                    f"strip_footing_{d['proj']['doc_no']}.pdf",
                    "application/pdf",
                )
            except Exception as e:
                st.error(f"PDF error: {e}")

        st.markdown("#### Report Preview")
        st.code("\n".join(lines[:80]) + "\n... (truncated — download for full report)", language="text")
