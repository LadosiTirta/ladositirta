"""
footing_strip/report.py
Professional report generator for strip footing — Word (.docx) and PDF.
"""
import io
import numpy as np
from datetime import datetime
# Gunakan generator dokumen yang sudah ada di footing.report_footing
from footing.report_footing import generate_word as gen_word, generate_pdf as gen_pdf

def _ok(flag): return "✓ OK" if flag else "✗ FAIL"
def _fmt(v, dec=2): return f"{v:,.{dec}f}"

def build_strip_report_lines(data: dict):
    lines = []
    A = lines.append

    proj = data["proj"]
    mat = data["mat"]
    geo = data["geo"]
    loads = data["loads"]
    soil = data["soil_result"]
    struc = data["struct_result"]
    settle = data["settle_result"]

    # COVER
    A("CONTINUOUS STRIP FOOTING DESIGN")
    A("Structural Calculation Report")
    A("")
    A(f"Project     : {proj['name']}")
    A(f"Location    : {proj['location']}")
    A(f"Engineer    : {proj['engineer']}")
    A(f"Date        : {proj['date']}")
    A(f"Document No : {proj['doc_no']}")
    A("")

    # DESIGN BASIS
    A("─"*60)
    A("1. DESIGN BASIS & REFERENCES")
    A("─"*60)
    A("[1] SNI 2847:2019 — Persyaratan Beton Struktural untuk Bangunan Gedung (ACI 318-19)")
    A("[2] SNI 8460:2017 — Persyaratan Perancangan Geoteknik")
    A("[3] SNI 1726:2019 — Tata Cara Perencanaan Ketahanan Gempa")
    A("[4] SNI 1727:2020 — Beban Minimum untuk Perancangan Bangunan")
    A("[5] Meyerhof, G.G. (1963). Some recent research on bearing capacity.")
    A("[6] Bowles, J.E. (1996). Foundation Analysis and Design, 5th Ed.")
    A("")

    # INPUT SUMMARY
    A("─"*60)
    A("2. INPUT SUMMARY")
    A("─"*60)
    A(f"2.1 Material: f'c={mat['fc']} MPa, fy={mat['fy']} MPa, fy_s={mat['fy_s']} MPa, γ_c={mat['gamma_c']} kN/m³, γ_s={mat['gamma_s']} kN/m³, λ={mat['lambda']}")
    A(f"2.2 Geometry: B={geo['B']} m, t={geo['t']} m, Df={geo['Df']} m, h_soil={geo['h_soil']} m, cover={geo['cover']} mm, wall bw={geo['bw']} m")
    A(f"2.3 Wall Loads (per meter): NS={loads['NS_kNm']:.2f} kN/m, Nu={loads['Nu_kNm']:.2f} kN/m, MSx={loads['MSx_kNm']:.2f} kN·m/m, Mux={loads['Mux_kNm']:.2f} kN·m/m")
    A(f"     Self-weight: W_foot={loads['W_foot_kNm']:.2f} kN/m, W_soil={loads['W_soil_kNm']:.2f} kN/m")
    A("")

    # BEARING CAPACITY
    A("─"*60)
    A("3. SOIL BEARING CAPACITY & PRESSURE CHECK (SERVICE)")
    A("─"*60)
    A(f"Method: {soil['method_name']}; qa = {soil['qa_kPa']:.2f} kN/m²; Ref: {soil['code_ref']}")
    pc = soil["pressure_check"]
    A(f"Total service load N = {loads['NS_kNm']+loads['W_foot_kNm']+loads['W_soil_kNm']:.2f} kN/m")
    A(f"Eccentricity ex = Mx/N = {pc['ex_m']:.4f} m; B/6 = {geo['B']/6:.4f} m → {_ok(pc['ok_ex'])}")
    A(f"q_max = {pc['q_max_kPa']:.2f} kN/m² ≤ qa → {_ok(pc['ok_bearing'])}")
    A(f"q_min = {pc['q_min_kPa']:.2f} kN/m² ≥ 0 → {_ok(pc['ok_no_uplift'])}")
    A("")

    # STRUCTURAL DESIGN
    A("─"*60)
    A("4. STRUCTURAL DESIGN (ULTIMATE)")
    A("─"*60)
    qu = struc["qu_avg_kPa"]
    A(f"qu_avg = Nu_total/A = {struc['qu_avg_kPa']:.2f} kN/m²")
    ed = struc["eff_depth"]
    A(f"Effective depth: dx={ed['dx']:.1f} mm, dy={ed['dy']:.1f} mm")

    # One-way shear
    ow = struc["one_way"]
    A("")
    A("4.1 One-Way Shear (SNI 2847:2019 Pasal 22.5)")
    cap = ow["capacity"]
    A(f"Critical section at d={ed['dx']:.1f} mm from wall face.")
    A(f"arm = (B - bw)/2 - d = ({geo['B']:.2f} - {geo['bw']:.2f})/2 - {ed['dx']/1000:.4f} = {ow['arm_m']:.4f} m")
    A(f"Vu = qu × 1.0m × arm = {qu:.2f} × 1.0 × {ow['arm_m']:.4f} = {ow['Vu_kN']:.2f} kN")
    A(f"Vc = 0.17 × λ × √f'c × bw × d  (Pasal 22.5.5.1)")
    A(f"   = 0.17 × {mat['lambda']} × √{mat['fc']} × 1000 × {ed['dx']:.1f} = {cap['Vc_kN']:.2f} kN")
    A(f"φVc = 0.75 × {cap['Vc_kN']:.2f} = {ow['phiVc_kN']:.2f} kN")
    A(f"Check: Vu ≤ φVc → {_ok(ow['ok'])}")

    # Flexure
    flex = struc["flexure"]
    A("")
    A("4.2 Flexural Design (SNI 2847:2019 Pasal 22.2, 13.2.7.1)")
    for key, fr in flex.items():
        A(f"")
        A(f"  {fr['location']} {fr['direction']} Bars:")
        A(f"  Moment at wall face: arm = (B - bw)/2 = ({geo['B']}-{geo['bw']})/2 = {max((geo['B']-geo['bw'])/2,0):.4f} m")
        A(f"  Mu = qu × 1.0 × arm²/2 = {qu:.2f} × 1.0 × ({max((geo['B']-geo['bw'])/2,0):.4f})²/2 = {fr['Mu_kNm']:.2f} kN·m")
        bar = fr["bar"]
        A(f"  As,req = {fr['As_design_mm2']:.1f} mm²/m")
        A(f"  Selected: D{bar['dia_mm']} @ {bar['spacing_mm']} mm → As,prov = {bar['As_provided_mm2']:.1f} mm²/m")
        A(f"  φMn = {fr['phi_Mn_kNm']:.2f} kN·m ≥ Mu → {_ok(fr['ok_strength'])}")
        A(f"  {fr['bar_description']}")

    # SETTLEMENT
    A("")
    A("─"*60)
    A("5. SETTLEMENT CHECK (SNI 8460:2017 Pasal 9)")
    A("─"*60)
    st = settle
    if st["immediate"]:
        si = st["immediate"]
        A(f"Immediate: δi = {si['delta_mm']:.2f} mm")
    if st["consolidation"]:
        sc = st["consolidation"]
        A(f"Consolidation: Sc = {sc['Sc_mm']:.2f} mm")
    stc = st["check"]
    A(f"Total δ = {stc['delta_total_mm']:.2f} mm ≤ {stc['allow_total_mm']} mm → {_ok(stc['ok_total'])}")

    # SUMMARY
    A("")
    A("─"*60)
    A("6. SUMMARY OF CHECKS")
    A("─"*60)
    A(f"  {'CHECK':<35} {'DEMAND':>12} {'CAPACITY':>12} {'STATUS':>8}")
    A(f"  Bearing             {pc['q_max_kPa']:.1f} kPa     {soil['qa_kPa']:.1f} kPa     {_ok(pc['ok_bearing'])}")
    A(f"  Eccentricity        {pc['ex_m']:.4f} m       B/6={geo['B']/6:.4f} m      {_ok(pc['ok_ex'])}")
    A(f"  One-way shear       {ow['Vu_kN']:.1f} kN      {ow['phiVc_kN']:.1f} kN      {_ok(ow['ok'])}")
    A(f"  Flexure transv.     {flex['transverse_bottom']['Mu_kNm']:.1f} kN·m    {flex['transverse_bottom']['phi_Mn_kNm']:.1f} kN·m    {_ok(flex['transverse_bottom']['ok_strength'])}")
    A(f"  Settlement          {stc['delta_total_mm']:.1f} mm      {stc['allow_total_mm']} mm      {_ok(stc['ok_total'])}")
    A("")
    A("━" * 60)
    A(f"  Prepared by : {proj['engineer']}")
    A(f"  Date        : {proj['date']}")
    A("━" * 60)

    return lines

def generate_word(lines, fig_bytes_list=None):
    return gen_word(lines, fig_bytes_list)

def generate_pdf(lines, fig_bytes_list=None):
    return gen_pdf(lines, fig_bytes_list)
