"""
footing/soil_pressure.py
Bearing capacity from SPT (Meyerhof, Bowles, SNI 8460:2017)
and Sondir/CPT (Schmertmann), plus soil pressure checks.

References:
  - SNI 8460:2017 Pasal 5 (Bearing Capacity of Shallow Foundations)
  - Meyerhof, G.G. (1963). Some recent research on the bearing capacity of foundations.
  - Bowles, J.E. (1996). Foundation Analysis and Design, 5th Ed.
  - Schmertmann, J.H. (1970). Static cone to compute static settlement.
"""
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# BEARING CAPACITY FROM SPT
# ─────────────────────────────────────────────────────────────────────────────

def _N60_average(depths, N_values, Df, B):
    """
    Average N60 from Df to (Df + B) depth range.
    N_values already corrected to N60 (energy ratio 60%).
    """
    z_top = Df
    z_bot = Df + B
    mask = (np.array(depths) >= z_top) & (np.array(depths) <= z_bot)
    vals = np.array(N_values)[mask]
    if len(vals) == 0:
        # fallback: use all values
        vals = np.array(N_values)
    return float(np.mean(vals))


def bearing_capacity_spt_meyerhof(depths, N_values, B, L, Df,
                                   Gwt_depth=None, SF=3.0):
    """
    Meyerhof (1956, 1963) bearing capacity from SPT.
    For settlement-controlled allowable bearing pressure.

    SNI 8460:2017 Lampiran / Meyerhof (1963):
    For B ≤ 1.2 m:  qa = N60/30 × Fd × Cw  (kN/m² per mm settlement)
    For B > 1.2 m:  qa = N60/50 × ((B+0.3)/B)² × Fd × Cw

    Settlement basis: 25 mm (isolated footing, SNI 8460:2017 Pasal 9.3)

    Parameters:
        depths    : list of depths (m)
        N_values  : list of N-SPT values (blows/30cm) — field N
        B, L      : footing dimensions (m)
        Df        : foundation depth (m)
        Gwt_depth : groundwater table depth from surface (m), None = deep
        SF        : safety factor (default 3.0)

    Returns: dict with qu, qa, steps
    """
    # Average N in influence zone Df to Df+B
    N_avg = _N60_average(depths, N_values, Df, B)

    # Depth factor Fd (Meyerhof)
    Fd = min(1.0 + 0.33 * (Df / B), 1.33)

    # Groundwater correction factor Cw
    if Gwt_depth is None or Gwt_depth >= (Df + B):
        Cw = 1.0
        Cw_note = "GWT deep (≥ Df+B) → Cw = 1.0"
    elif Gwt_depth <= Df:
        Cw = 0.5
        Cw_note = f"GWT at/above footing base (≤ Df={Df}m) → Cw = 0.5"
    else:
        Cw = 0.5 + 0.5 * (Gwt_depth - Df) / B
        Cw = min(max(Cw, 0.5), 1.0)
        Cw_note = f"GWT between Df and Df+B → Cw = {Cw:.3f}"

    # Allowable bearing pressure for 25mm settlement
    s_allow = 25  # mm
    if B <= 1.2:
        # qa_25 in kN/m²
        qa_25 = (N_avg / 30) * Fd * Cw * s_allow
        formula_str = f"qa = N60/30 × Fd × Cw × s_allow = {N_avg:.1f}/30 × {Fd:.3f} × {Cw:.3f} × {s_allow}"
    else:
        factor_B = ((B + 0.3) / B) ** 2
        qa_25 = (N_avg / 50) * factor_B * Fd * Cw * s_allow
        formula_str = (f"qa = N60/50 × ((B+0.3)/B)² × Fd × Cw × s_allow\n"
                       f"   = {N_avg:.1f}/50 × {factor_B:.4f} × {Fd:.3f} × {Cw:.3f} × {s_allow}")

    # qu not explicitly from Meyerhof SPT method (settlement-controlled)
    qu_equiv = qa_25 * SF

    steps = {
        "method": "Meyerhof (1963) — SPT Settlement-Controlled",
        "code_ref": "SNI 8460:2017 Lampiran B; Meyerhof (1963)",
        "N_avg": N_avg,
        "Fd": Fd,
        "Cw": Cw,
        "Cw_note": Cw_note,
        "B_m": B,
        "formula_str": formula_str,
        "qu_kPa": qu_equiv,
        "qa_kPa": qa_25,
        "SF": SF,
        "settlement_basis_mm": s_allow,
    }
    return steps


def bearing_capacity_spt_bowles(depths, N_values, B, L, Df,
                                 Gwt_depth=None, SF=3.0):
    """
    Bowles (1996) modified Meyerhof — bearing capacity from SPT.
    Applicable for sands and silty sands.

    qa (kPa) = N60/0.05 × Fd × Cw / SF   [for B ≤ 1.2m]
    qa (kPa) = N60/0.08 × ((B+0.3)/B)² × Fd × Cw / SF  [for B > 1.2m]

    Reference: Bowles (1996) Table 4-4; SNI 8460:2017 Pasal 5.4
    """
    N_avg = _N60_average(depths, N_values, Df, B)

    Fd = 1.0 + 0.33 * (Df / B)
    Fd = min(Fd, 1.33)

    if Gwt_depth is None or Gwt_depth >= (Df + B):
        Cw = 1.0
    elif Gwt_depth <= Df:
        Cw = 0.5
    else:
        Cw = 0.5 + 0.5 * (Gwt_depth - Df) / B
        Cw = min(max(Cw, 0.5), 1.0)

    if B <= 1.2:
        qu = N_avg / 0.05 * Fd * Cw
        formula_str = f"qu = N60/0.05 × Fd × Cw = {N_avg:.1f}/0.05 × {Fd:.3f} × {Cw:.3f}"
    else:
        factor_B = ((B + 0.3) / B) ** 2
        qu = N_avg / 0.08 * factor_B * Fd * Cw
        formula_str = (f"qu = N60/0.08 × ((B+0.3)/B)² × Fd × Cw\n"
                       f"   = {N_avg:.1f}/0.08 × {factor_B:.4f} × {Fd:.3f} × {Cw:.3f}")

    qa = qu / SF

    steps = {
        "method": "Bowles (1996) Modified Meyerhof — SPT",
        "code_ref": "Bowles (1996) Table 4-4; SNI 8460:2017 Pasal 5.4",
        "N_avg": N_avg,
        "Fd": Fd,
        "Cw": Cw,
        "B_m": B,
        "formula_str": formula_str,
        "qu_kPa": qu,
        "qa_kPa": qa,
        "SF": SF,
    }
    return steps


def bearing_capacity_spt_sni(depths, N_values, B, L, Df,
                               gamma_s: float, Gwt_depth=None, SF=3.0):
    """
    SNI 8460:2017 Pasal 5.3 — Terzaghi/Meyerhof general bearing capacity.
    N-SPT correlated to φ angle → Nq, Nc, Nγ factors.

    Correlation N → φ (Peck, Hanson, Thornburn 1974):
      φ = 28 + 0.4 × N60  (capped at 45°) — for sand
    qu = c·Nc·sc·dc + q·Nq·sq·dq + 0.5·γ·B·Nγ·sγ·dγ

    Shape factors (Meyerhof):
      sc = 1 + 0.2(B/L)
      sq = sγ = 1 + 0.1(B/L)  [for φ>10°]
    Depth factors (Meyerhof):
      dc = 1 + 0.2(Df/B)
      dq = dγ = 1 + 0.1(Df/B)  [for φ>10°]
    """
    N_avg = _N60_average(depths, N_values, Df, B)
    N_avg_cap = min(N_avg, 60)

    # Correlation N→φ
    phi_deg = min(28 + 0.4 * N_avg_cap, 45.0)
    phi_rad = np.radians(phi_deg)

    # Bearing capacity factors (Meyerhof)
    Nq = np.exp(np.pi * np.tan(phi_rad)) * np.tan(np.radians(45) + phi_rad / 2) ** 2
    Nc = (Nq - 1) / np.tan(phi_rad) if phi_deg > 0 else 5.14
    Ng = (Nq - 1) * np.tan(1.4 * phi_rad)

    # Shape factors
    sc = 1 + 0.2 * (B / L)
    sq = sg = 1 + 0.1 * (B / L) if phi_deg > 10 else 1.0

    # Depth factors
    dc = 1 + 0.2 * (Df / B)
    dq = dg = 1 + 0.1 * (Df / B) if phi_deg > 10 else 1.0

    # GWT correction for effective stress
    q = gamma_s * Df
    if Gwt_depth is not None and Gwt_depth < Df:
        gamma_eff = gamma_s - 9.81
        q = gamma_s * Gwt_depth + gamma_eff * (Df - Gwt_depth)
    
    gamma_b = gamma_s
    if Gwt_depth is not None and Gwt_depth < (Df + B / 2):
        gamma_b = gamma_s - 9.81

    c = 0  # for sand (N-SPT correlation)
    qu = (c * Nc * sc * dc
          + q * Nq * sq * dq
          + 0.5 * gamma_b * B * Ng * sg * dg)
    qa = qu / SF

    steps = {
        "method": "SNI 8460:2017 Pasal 5.3 — General Bearing Capacity (N→φ)",
        "code_ref": "SNI 8460:2017 Pasal 5.3; Meyerhof (1963); Peck et al. (1974)",
        "N_avg": N_avg,
        "phi_deg": phi_deg,
        "Nq": Nq, "Nc": Nc, "Ngamma": Ng,
        "sc": sc, "sq": sq, "sg": sg,
        "dc": dc, "dq": dq, "dg": dg,
        "q_kPa": q,
        "qu_kPa": qu,
        "qa_kPa": qa,
        "SF": SF,
    }
    return steps


def bearing_capacity_all_spt(depths, N_values, B, L, Df,
                              gamma_s, Gwt_depth=None, SF=3.0):
    """
    Run all 3 SPT methods and return comparison dict.
    """
    r1 = bearing_capacity_spt_meyerhof(depths, N_values, B, L, Df, Gwt_depth, SF)
    r2 = bearing_capacity_spt_bowles(depths, N_values, B, L, Df, Gwt_depth, SF)
    r3 = bearing_capacity_spt_sni(depths, N_values, B, L, Df, gamma_s, Gwt_depth, SF)
    return {"meyerhof": r1, "bowles": r2, "sni": r3}


# ─────────────────────────────────────────────────────────────────────────────
# BEARING CAPACITY FROM SONDIR / CPT
# ─────────────────────────────────────────────────────────────────────────────

def bearing_capacity_sondir(depths_cpt, qc_values, fs_values,
                             B, L, Df, SF=3.0):
    """
    Bearing capacity from Sondir (CPT) using Schmertmann (1970) + Meyerhof.

    qc_avg : average qc from Df to Df+B (influence zone)
    qa = qc_avg / (kc × SF)

    kc factor (Meyerhof 1956 from CPT):
      For sand: kc = 40 × (Df/B) ≤ 200
      For clay: kc = 9

    Also provides: qu = c·Nc + q·Nq (using qc→cu for clay)

    Reference: Schmertmann (1970); SNI 8460:2017 Lampiran C
    """
    depths_arr = np.array(depths_cpt)
    qc_arr = np.array(qc_values)   # in kg/cm²
    fs_arr = np.array(fs_values)   # in kg/cm²

    # Average qc in influence zone
    mask = (depths_arr >= Df) & (depths_arr <= (Df + B))
    qc_zone = qc_arr[mask]
    qc_avg_kgcm2 = float(np.mean(qc_zone)) if len(qc_zone) > 0 else float(np.mean(qc_arr))
    qc_avg_kPa = qc_avg_kgcm2 * 98.07   # 1 kg/cm² = 98.07 kPa

    # Friction ratio → soil type
    FR_avg = float(np.mean(fs_arr[mask] / qc_arr[mask])) * 100 if len(qc_zone) > 0 else 2.0

    # Meyerhof CPT correlation
    # For sand (FR < 1%): qa = qc/40 for B≤1.2m; qc/50×((B+0.3)/B)² for B>1.2m
    # For clay (FR > 3%): qu = qc/Nk → qa = qu/SF
    Nk = 15  # cone factor for clay (typical)

    if FR_avg < 1.5:
        soil_type = "Sand"
        if B <= 1.2:
            qa_kPa = qc_avg_kPa / 40
            formula_str = f"qa = qc_avg / 40 = {qc_avg_kPa:.1f} / 40"
        else:
            factor_B = ((B + 0.3) / B) ** 2
            qa_kPa = qc_avg_kPa / 50 * factor_B
            formula_str = f"qa = qc_avg/50 × ((B+0.3)/B)² = {qc_avg_kPa:.1f}/50 × {factor_B:.4f}"
        qu_kPa = qa_kPa * SF
    else:
        soil_type = "Clay/Silt"
        cu = qc_avg_kPa / Nk
        Nc = 5.14
        qu_kPa = cu * Nc
        qa_kPa = qu_kPa / SF
        formula_str = f"cu = qc/Nk = {qc_avg_kPa:.1f}/{Nk} = {cu:.1f} kPa; qu = cu×Nc = {cu:.1f}×{Nc}"

    steps = {
        "method": "Schmertmann (1970) + Meyerhof — CPT/Sondir",
        "code_ref": "SNI 8460:2017 Lampiran C; Schmertmann (1970)",
        "qc_avg_kgcm2": qc_avg_kgcm2,
        "qc_avg_kPa": qc_avg_kPa,
        "FR_avg_pct": FR_avg,
        "soil_type": soil_type,
        "formula_str": formula_str,
        "qu_kPa": qu_kPa,
        "qa_kPa": qa_kPa,
        "SF": SF,
    }
    return steps


# ─────────────────────────────────────────────────────────────────────────────
# METHOD SELECTION GUIDANCE
# ─────────────────────────────────────────────────────────────────────────────

METHOD_GUIDANCE = {
    "meyerhof": {
        "name": "Meyerhof (1963) — Settlement-Controlled",
        "suitable_for": "Sand, gravel, non-cohesive soils",
        "advantage": "Simple, widely used in Indonesia, settlement-based (25mm). "
                     "Conservative and safe for preliminary design.",
        "limitation": "Settlement-controlled only; does not compute shear failure qu. "
                      "Not suitable for clay or soft soils.",
        "consequence": "Selecting this gives the MOST CONSERVATIVE qa "
                       "(safest for preliminary/schematic design). "
                       "If footing size seems too large, try Bowles or SNI method.",
        "recommended_when": "Preliminary design, sand/gravel site, limited data.",
    },
    "bowles": {
        "name": "Bowles (1996) Modified Meyerhof",
        "suitable_for": "Sand, silty sand, gravelly sand",
        "advantage": "Slightly less conservative than Meyerhof (1963). "
                     "Widely referenced in practice.",
        "limitation": "Still empirical; based on settlement correlation. "
                      "Not suitable for clay.",
        "consequence": "qa typically 10–20% HIGHER than Meyerhof (1963). "
                       "More economical footing size but still safe.",
        "recommended_when": "Detailed design for sand sites with reasonable SPT data.",
    },
    "sni": {
        "name": "SNI 8460:2017 Pasal 5.3 — General Bearing Capacity",
        "suitable_for": "Sand (N→φ correlation), general use",
        "advantage": "Official Indonesian code method. Computes qu from shear failure "
                     "(not settlement). Includes shape + depth factors.",
        "limitation": "N→φ correlation has uncertainty. Clay not well-represented by N-SPT alone.",
        "consequence": "qa may be HIGHER or LOWER than Meyerhof/Bowles depending on site. "
                       "This is the REQUIRED method for formal/official reports in Indonesia.",
        "recommended_when": "Official submission, detailed design, Indonesian projects. "
                            "ALWAYS include this method in reports submitted to authorities.",
    },
    "sondir": {
        "name": "Schmertmann (1970) + Meyerhof — CPT/Sondir",
        "suitable_for": "All soil types (sand & clay via FR ratio)",
        "advantage": "CPT gives continuous profile; distinguishes sand vs clay automatically.",
        "limitation": "Nk factor for clay has uncertainty (Nk = 12–18); "
                      "local correlation recommended.",
        "consequence": "Good for clay sites where SPT is less reliable. "
                       "For formal Indonesian reports, combine with SPT if possible.",
        "recommended_when": "Soft clay sites, when only Sondir data available.",
    },
}

SELECTION_ADVICE = """
HOW TO SELECT THE BEARING CAPACITY METHOD:

━━ OFFICIAL/FORMAL REPORTS (submitted to government/client) ━━
  → MUST include SNI 8460:2017 Pasal 5.3 result.
  → Use the LOWER of SNI and Meyerhof/Bowles as qa_design.
  → State all methods in the report.

━━ PRELIMINARY / SCHEMATIC DESIGN ━━
  → Use Meyerhof (1963) for quick conservative estimate.

━━ CLAY SITES ━━
  → Use Sondir method (CPT). SPT-based methods unreliable in soft clay.

━━ SAND SITES WITH GOOD SPT DATA ━━
  → Compare all 3 SPT methods. Use SNI for official, Bowles for economy check.

━━ COMBINED SPT + SONDIR ━━
  → Use LOWER qa from both data sets → most conservative → safest.
"""


# ─────────────────────────────────────────────────────────────────────────────
# SOIL PRESSURE CHECK
# ─────────────────────────────────────────────────────────────────────────────

def check_soil_pressure(q1, q2, q3, q4, qa, B, L, sum_N,
                         sum_Mx, sum_My, A, Wx, Wy):
    """
    Check soil pressure adequacy.
    Returns dict with status for each check.
    """
    q_max = max(q1, q2, q3, q4)
    q_min = min(q1, q2, q3, q4)
    q_avg = (q1 + q2 + q3 + q4) / 4

    ex = abs(sum_My) / sum_N if sum_N > 0 else 0
    ey = abs(sum_Mx) / sum_N if sum_N > 0 else 0

    checks = {
        "q_max_kPa": q_max,
        "q_min_kPa": q_min,
        "q_avg_kPa": q_avg,
        "qa_kPa": qa,
        "ok_bearing": q_max <= qa,
        "ok_no_uplift": q_min >= 0,
        "ex_m": ex,
        "ey_m": ey,
        "ok_ex": ex <= B / 6,
        "ok_ey": ey <= L / 6,
        "B_6": B / 6,
        "L_6": L / 6,
    }
    checks["all_ok"] = all([
        checks["ok_bearing"],
        checks["ok_no_uplift"],
        checks["ok_ex"],
        checks["ok_ey"],
    ])
    return checks


def factored_pressure(sum_Nu: float, sum_Mux: float, sum_Muy: float,
                      A: float, Wx: float, Wy: float):
    """
    Compute average factored soil pressure qu for structural design.
    qu = ΣNu / A  (simplified uniform for structural checks)
    Also return moment-adjusted pressures at edges.
    """
    qu_avg = sum_Nu / A
    qu_max = sum_Nu / A + abs(sum_Muy) / Wx + abs(sum_Mux) / Wy
    qu_min = sum_Nu / A - abs(sum_Muy) / Wx - abs(sum_Mux) / Wy
    return {
        "qu_avg_kPa": qu_avg,
        "qu_max_kPa": qu_max,
        "qu_min_kPa": qu_min,
    }
