"""
footing/reinforcement.py
Flexure design and reinforcement selection for isolated spread footing.

References:
  - SNI 2847:2019 Pasal 22.6 (flexure)
  - SNI 2847:2019 Pasal 9.6.1.2  (As_min for beams/flexural members)
  - SNI 2847:2019 Pasal 24.4.3   (shrinkage and temperature reinforcement)
  - ACI 318-19 Section 9.6.1.2, 24.4.3
"""
import numpy as np


# Bar database: diameter (mm) → area (mm²)
BAR_DB = {
    10: 78.54,
    13: 132.73,
    16: 201.06,
    19: 283.53,
    22: 380.13,
    25: 490.87,
    29: 660.52,
    32: 804.25,
}

AVAILABLE_SPACINGS = [75, 100, 125, 150, 175, 200, 225, 250, 275, 300]


def design_flexure(Mu_kNm: float, fc_MPa: float, fy_MPa: float,
                   b_mm: float, d_mm: float, phi: float = 0.90):
    """
    Flexure design using Whitney rectangular stress block.
    SNI 2847:2019 Pasal 22.2 (stress block) & Pasal 9.3.3 (phi = 0.90 for tension-controlled).

    Mu_kNm : factored design moment (kN·m)
    b_mm   : footing width (mm)
    d_mm   : effective depth (mm)

    Returns: As_required (mm²), detail dict
    """
    Mu_Nmm = Mu_kNm * 1e6

    # Rn = Mu / (φ × b × d²)
    Rn = Mu_Nmm / (phi * b_mm * d_mm**2)

    # ρ from quadratic (Whitney)
    # ρ = (0.85×f'c/fy) × [1 - √(1 - 2Rn/(0.85×f'c))]
    term = 1 - 2 * Rn / (0.85 * fc_MPa)
    if term < 0:
        term = 0  # over-stressed; section must be enlarged
        rho = 0.85 * fc_MPa / fy_MPa
    else:
        rho = (0.85 * fc_MPa / fy_MPa) * (1 - np.sqrt(term))

    As_required = rho * b_mm * d_mm

    detail = {
        "Mu_kNm": Mu_kNm,
        "Mu_Nmm": Mu_Nmm,
        "fc_MPa": fc_MPa,
        "fy_MPa": fy_MPa,
        "b_mm": b_mm,
        "d_mm": d_mm,
        "phi": phi,
        "Rn_MPa": Rn,
        "rho": rho,
        "As_required_mm2": As_required,
        "code_ref": "SNI 2847:2019 Pasal 22.2 (Whitney stress block) [ACI 318-19 §22.2]",
    }
    return As_required, detail


def As_minimum(fc_MPa: float, fy_MPa: float, b_mm: float,
               d_mm: float, h_mm: float):
    """
    Minimum steel area — SNI 2847:2019 Pasal 9.6.1.2.
    As_min = max(0.25√f'c/fy × b×d, 1.4/fy × b×d)

    For footings (treated as slabs for shrinkage):
    Also compute As_shrink = 0.0018 × b × h (Pasal 24.4.3)
    """
    As_min1 = (0.25 * np.sqrt(fc_MPa) / fy_MPa) * b_mm * d_mm
    As_min2 = (1.4 / fy_MPa) * b_mm * d_mm
    As_min_beam = max(As_min1, As_min2)

    # Shrinkage & temperature (Pasal 24.4.3) — for slabs & footings
    As_shrink = 0.0018 * b_mm * h_mm

    detail = {
        "As_min1_mm2": As_min1,
        "label1": "0.25√f'c/fy × b × d",
        "As_min2_mm2": As_min2,
        "label2": "1.4/fy × b × d",
        "As_min_beam_mm2": As_min_beam,
        "As_shrink_mm2": As_shrink,
        "code_beam": "SNI 2847:2019 Pasal 9.6.1.2 [ACI 318-19 §9.6.1.2]",
        "code_shrink": "SNI 2847:2019 Pasal 24.4.3 [ACI 318-19 §24.4.3]",
    }
    return As_min_beam, As_shrink, detail


def select_bars(As_design_mm2: float, b_mm: float,
                preferred_dia: int = None,
                max_spacing_mm: float = 300):
    """
    Select reinforcing bars: diameter and spacing.

    Strategy:
    1. Try each available diameter.
    2. Spacing s = (b × Ab) / As_design
    3. Pick the combination closest to preferred_dia with s ≤ max_spacing_mm.

    Returns: best bar dict
    """
    results = []
    for dia, Ab in BAR_DB.items():
        s = (b_mm * Ab) / As_design_mm2
        if s < 75:   # too congested
            continue
        s_rounded = min(AVAILABLE_SPACINGS,
                        key=lambda x: abs(x - s) if x <= s else float('inf'))
        if s_rounded is None or s_rounded > max_spacing_mm:
            s_rounded = max_spacing_mm
        # Number of bars at rounded spacing
        n_bars = int(b_mm / s_rounded) + 1
        As_provided = n_bars * Ab
        if As_provided >= As_design_mm2:
            results.append({
                "dia_mm": dia,
                "Ab_mm2": Ab,
                "spacing_mm": s_rounded,
                "n_bars": n_bars,
                "As_provided_mm2": As_provided,
                "ok": True,
            })

    if not results:
        # Fallback: max diameter, min spacing
        dia = 32
        Ab = BAR_DB[32]
        s = 100
        n_bars = int(b_mm / s) + 1
        results.append({
            "dia_mm": dia,
            "Ab_mm2": Ab,
            "spacing_mm": s,
            "n_bars": n_bars,
            "As_provided_mm2": n_bars * Ab,
            "ok": True,
        })

    # Prefer matching preferred diameter
    if preferred_dia and any(r["dia_mm"] == preferred_dia for r in results):
        best = next(r for r in results if r["dia_mm"] == preferred_dia)
    else:
        # Pick smallest diameter that works (economy)
        best = min(results, key=lambda r: r["dia_mm"])

    return best


def flexure_design_full(Mu_kNm: float, fc_MPa: float, fy_MPa: float,
                         b_m: float, d_mm: float, h_mm: float,
                         direction: str, location: str,
                         preferred_dia: int = None,
                         max_spacing_mm: float = 300,
                         phi: float = 0.90):
    """
    Full flexure design for one strip (direction + location).

    direction: "X" or "Y"
    location : "Bottom" or "Top"

    Returns complete result dict.
    """
    b_mm = b_m * 1000

    As_req, flex_detail = design_flexure(Mu_kNm, fc_MPa, fy_MPa, b_mm, d_mm, phi)
    As_min_b, As_shrink, min_detail = As_minimum(fc_MPa, fy_MPa, b_mm, d_mm, h_mm)

    # For top bars (if Mu small), use shrinkage minimum
    if location == "Top":
        As_design = max(As_req, As_shrink)
        min_basis = "As_shrink (SNI 2847:2019 Pasal 24.4.3)"
    else:
        As_design = max(As_req, As_min_b)
        min_basis = "As_min (SNI 2847:2019 Pasal 9.6.1.2)"

    bar = select_bars(As_design, b_mm, preferred_dia, max_spacing_mm)

    # Direction description for report clarity
    if direction == "X":
        bar_description = (
            f"D{bar['dia_mm']} @ {bar['spacing_mm']} mm c/c\n"
            f"  → Bars RUN ALONG X-axis (bar length ≈ footing dimension in X)\n"
            f"  → Bars are SPACED {bar['spacing_mm']} mm apart in the Y-direction\n"
            f"  → Total {bar['n_bars']} bars"
        )
    else:
        bar_description = (
            f"D{bar['dia_mm']} @ {bar['spacing_mm']} mm c/c\n"
            f"  → Bars RUN ALONG Y-axis (bar length ≈ footing dimension in Y)\n"
            f"  → Bars are SPACED {bar['spacing_mm']} mm apart in the X-direction\n"
            f"  → Total {bar['n_bars']} bars"
        )

    # Moment capacity check
    a = bar["As_provided_mm2"] * fy_MPa / (0.85 * fc_MPa * b_mm)
    phi_Mn_Nmm = phi * bar["As_provided_mm2"] * fy_MPa * (d_mm - a / 2)
    phi_Mn_kNm = phi_Mn_Nmm / 1e6

    return {
        "direction": direction,
        "location": location,
        "Mu_kNm": Mu_kNm,
        "As_required_mm2": As_req,
        "As_min_mm2": As_min_b,
        "As_shrink_mm2": As_shrink,
        "As_design_mm2": As_design,
        "min_basis": min_basis,
        "bar": bar,
        "bar_description": bar_description,
        "phi_Mn_kNm": phi_Mn_kNm,
        "ok_strength": phi_Mn_kNm >= Mu_kNm,
        "ratio": Mu_kNm / phi_Mn_kNm if phi_Mn_kNm > 0 else 999,
        "flex_detail": flex_detail,
        "min_detail": min_detail,
        "a_mm": a,
    }


def compute_design_moment(qu_avg_kPa: float, B_m: float, L_m: float,
                           bc_m: float, hc_m: float,
                           col_x: float = 0.0, col_y: float = 0.0):
    """
    Compute design moments at column face for X and Y directions.
    Critical section: at face of column (SNI 2847:2019 Pasal 13.2.7.1).

    For X-direction moment (bending about X-axis):
      arm_x = L/2 - hc/2 (distance from col face to footing edge, in L-direction)
      Mu_x = qu_avg × B × arm_x × arm_x/2 = qu_avg × B × arm_x² / 2

    For Y-direction moment (bending about Y-axis):
      arm_y = B/2 - bc/2
      Mu_y = qu_avg × L × arm_y² / 2

    Returns: Mu_x (kN·m), Mu_y (kN·m), detail dict
    """
    # Conservative: use max arm (furthest edge from col face)
    arm_x = max(L_m / 2 - abs(col_x) - hc_m / 2, 0.0)
    arm_y = max(B_m / 2 - abs(col_y) - bc_m / 2, 0.0)

    Mu_x_kNm = qu_avg_kPa * B_m * arm_x**2 / 2
    Mu_y_kNm = qu_avg_kPa * L_m * arm_y**2 / 2

    detail = {
        "code_ref": "SNI 2847:2019 Pasal 13.2.7.1 — critical section at column face [ACI 318-19 §13.2.7.1]",
        "qu_avg_kPa": qu_avg_kPa,
        "arm_x_m": arm_x,
        "arm_y_m": arm_y,
        "Mu_x_kNm": Mu_x_kNm,
        "Mu_y_kNm": Mu_y_kNm,
        "formula_x": "Mu_x = qu_avg × B × arm_x² / 2",
        "formula_y": "Mu_y = qu_avg × L × arm_y² / 2",
        "sub_x": (f"      = {qu_avg_kPa:.2f} × {B_m:.2f} × {arm_x:.3f}² / 2"
                  f"      = {Mu_x_kNm:.2f} kN·m"),
        "sub_y": (f"      = {qu_avg_kPa:.2f} × {L_m:.2f} × {arm_y:.3f}² / 2"
                  f"      = {Mu_y_kNm:.2f} kN·m"),
    }
    return Mu_x_kNm, Mu_y_kNm, detail


def reinforcement_schedule(results: list):
    """
    Build reinforcement schedule table from list of flexure_design_full results.
    Returns list of dicts suitable for pandas DataFrame.
    """
    rows = []
    for r in results:
        bar = r["bar"]
        rows.append({
            "Location": r["location"],
            "Direction": r["direction"] + "-Direction",
            "Bar Run Along": r["direction"] + "-axis",
            "Spacing Direction": ("Y" if r["direction"] == "X" else "X"),
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
