"""
footing_strip/reinforcement.py
Flexural design for strip footing (per meter width).
"""
import numpy as np

BAR_DB = {
    10: 78.54, 13: 132.73, 16: 201.06, 19: 283.53,
    22: 380.13, 25: 490.87, 29: 660.52, 32: 804.25,
}
AVAILABLE_SPACINGS = [75, 100, 125, 150, 175, 200, 225, 250, 275, 300]

def design_flexure(Mu_kNm: float, fc_MPa: float, fy_MPa: float,
                   b_mm: float, d_mm: float, phi: float = 0.90):
    Mu_Nmm = Mu_kNm * 1e6
    Rn = Mu_Nmm / (phi * b_mm * d_mm**2)
    term = 1 - 2 * Rn / (0.85 * fc_MPa)
    if term < 0:
        term = 0
    rho = (0.85 * fc_MPa / fy_MPa) * (1 - np.sqrt(term))
    As_required = rho * b_mm * d_mm
    detail = {
        "Mu_kNm": Mu_kNm, "Rn_MPa": Rn, "rho": rho,
        "As_required_mm2": As_required,
        "code_ref": "SNI 2847:2019 Pasal 22.2 (Whitney stress block)",
    }
    return As_required, detail

def As_minimum(fc_MPa, fy_MPa, b_mm, d_mm, h_mm):
    As_min1 = (0.25 * np.sqrt(fc_MPa) / fy_MPa) * b_mm * d_mm
    As_min2 = (1.4 / fy_MPa) * b_mm * d_mm
    As_min_beam = max(As_min1, As_min2)
    As_shrink = 0.0018 * b_mm * h_mm
    return As_min_beam, As_shrink

def select_bars(As_design_mm2: float, b_mm: float,
                preferred_dia: int = None, max_spacing_mm: float = 300):
    results = []
    for dia, Ab in BAR_DB.items():
        s = (b_mm * Ab) / As_design_mm2
        if s < 75:
            continue
        s_rounded = min(AVAILABLE_SPACINGS, key=lambda x: abs(x - s) if x <= s else float('inf'))
        if s_rounded > max_spacing_mm:
            s_rounded = max_spacing_mm
        n_bars = int(b_mm / s_rounded) + 1
        As_provided = n_bars * Ab
        if As_provided >= As_design_mm2:
            results.append({
                "dia_mm": dia, "Ab_mm2": Ab,
                "spacing_mm": s_rounded, "n_bars": n_bars,
                "As_provided_mm2": As_provided, "ok": True,
            })
    if not results:
        dia = 32
        Ab = BAR_DB[32]
        s = 100
        n_bars = int(b_mm / s) + 1
        results.append({"dia_mm": dia, "Ab_mm2": Ab, "spacing_mm": s,
                        "n_bars": n_bars, "As_provided_mm2": n_bars * Ab, "ok": True})
    if preferred_dia and any(r["dia_mm"] == preferred_dia for r in results):
        best = next(r for r in results if r["dia_mm"] == preferred_dia)
    else:
        best = min(results, key=lambda r: r["dia_mm"])
    return best

def flexure_design_strip(qu_kPa: float, B_m: float, bw_m: float,
                          fc_MPa: float, fy_MPa: float, fy_s_MPa: float,
                          h_mm: float, d_shear_mm: float, d_flex_mm: float,
                          pref_dia_trans: int, pref_dia_long: int,
                          pref_dia_top: int, max_spacing_mm: float,
                          phi_flex: float):
    """
    Design transverse bottom bars, longitudinal bottom bars, and top bars.
    Returns dict with all reinforcement results.
    """
    arm = max((B_m - bw_m) / 2, 0.0)
    Mu_trans = qu_kPa * 1.0 * arm**2 / 2   # kN·m per meter

    # Transverse bottom
    As_req, flex_det = design_flexure(Mu_trans, fc_MPa, fy_MPa, 1000, d_flex_mm, phi_flex)
    As_min_b, As_shrink_trans = As_minimum(fc_MPa, fy_MPa, 1000, d_flex_mm, h_mm)
    As_design_trans = max(As_req, As_min_b)
    bar_trans = select_bars(As_design_trans, 1000, pref_dia_trans, max_spacing_mm)
    # Capacity check
    a = bar_trans["As_provided_mm2"] * fy_MPa / (0.85 * fc_MPa * 1000)
    phi_Mn = phi_flex * bar_trans["As_provided_mm2"] * fy_MPa * (d_flex_mm - a/2) / 1e6
    trans_result = {
        "direction": "Transverse (X)",
        "location": "Bottom",
        "Mu_kNm": Mu_trans,
        "As_design_mm2": As_design_trans,
        "bar": bar_trans,
        "phi_Mn_kNm": phi_Mn,
        "ok_strength": phi_Mn >= Mu_trans,
        "bar_description": (
            f"D{bar_trans['dia_mm']} @ {bar_trans['spacing_mm']} mm c/c\n"
            f"  → Bars RUN ALONG Y‑axis (length = 1 m strip), SPACED {bar_trans['spacing_mm']} mm apart in X‑direction"
        ),
    }

    # Longitudinal bottom (shrinkage/temperature)
    As_shrink_long = 0.0018 * 1000 * h_mm
    As_design_long = As_shrink_long  # no moment in long. dir.
    bar_long = select_bars(As_design_long, 1000, pref_dia_long, max_spacing_mm)
    long_result = {
        "direction": "Longitudinal (Y)",
        "location": "Bottom",
        "Mu_kNm": 0.0,
        "As_design_mm2": As_design_long,
        "bar": bar_long,
        "phi_Mn_kNm": 0.0,
        "ok_strength": True,
        "bar_description": (
            f"D{bar_long['dia_mm']} @ {bar_long['spacing_mm']} mm c/c\n"
            f"  → Bars RUN ALONG X‑axis (length = B), SPACED {bar_long['spacing_mm']} mm apart in Y‑direction"
        ),
    }

    # Top transverse (shrinkage)
    As_design_top_trans = max(0.0, As_shrink_trans)
    bar_top_trans = select_bars(As_design_top_trans, 1000, pref_dia_top, max_spacing_mm)
    top_trans_result = {
        "direction": "Transverse (X)",
        "location": "Top",
        "Mu_kNm": 0.0,
        "As_design_mm2": As_design_top_trans,
        "bar": bar_top_trans,
        "phi_Mn_kNm": 0.0,
        "ok_strength": True,
        "bar_description": (
            f"D{bar_top_trans['dia_mm']} @ {bar_top_trans['spacing_mm']} mm c/c\n"
            f"  → Bars RUN ALONG Y‑axis, SPACED {bar_top_trans['spacing_mm']} mm apart in X‑direction"
        ),
    }

    return {
        "transverse_bottom": trans_result,
        "longitudinal_bottom": long_result,
        "transverse_top": top_trans_result,
    }

def reinforcement_schedule_strip(flex: dict):
    rows = []
    for key, r in flex.items():
        bar = r["bar"]
        rows.append({
            "Location": r["location"],
            "Direction": r["direction"],
            "Bar Run Along": r["direction"].split()[-1] + "-axis",
            "Spacing Direction": (
                "X" if "Y" in r["direction"] else "Y"
            ),
            "Bar Size": f"D{bar['dia_mm']}",
            "Spacing (mm)": bar["spacing_mm"],
            "No. of Bars": bar["n_bars"],
            "As,req (mm²)": f"{r['As_design_mm2']:.0f}",
            "As,prov (mm²)": f"{bar['As_provided_mm2']:.0f}",
            "φMn (kN·m)": f"{r['phi_Mn_kNm']:.2f}",
            "Mu (kN·m)": f"{r['Mu_kNm']:.2f}",
            "Status": "✓ OK" if r["ok_strength"] else "✗ FAIL",
        })
    return rows
