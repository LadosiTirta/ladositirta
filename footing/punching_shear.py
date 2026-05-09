"""
footing/punching_shear.py
Two-way (punching) shear and one-way (beam) shear for isolated footing.

References:
  - SNI 2847:2019 Pasal 22.6  (Two-way shear)
  - SNI 2847:2019 Pasal 22.5  (One-way shear)
  - ACI 318-19  Section 22.6, 22.5  (equivalent)
"""
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# TWO-WAY (PUNCHING) SHEAR — SNI 2847:2019 Pasal 22.6
# ─────────────────────────────────────────────────────────────────────────────

def punching_shear_capacity(fc_MPa: float, bo_mm: float, d_mm: float,
                             beta: float, alpha_s: int = 40,
                             lambda_factor: float = 1.0, phi: float = 0.75):
    """
    φVc for two-way punching shear — 3 equations per SNI 2847:2019 Pasal 22.6.5.2.

    Parameters:
        fc_MPa      : concrete compressive strength (MPa)
        bo_mm       : critical perimeter at d/2 from col face (mm)
        d_mm        : effective depth (mm)
        beta        : ratio of long to short column dimension (hc/bc ≥ 1)
        alpha_s     : 40 for interior col, 30 for edge, 20 for corner
        lambda_factor: 1.0 for normal weight concrete
        phi         : strength reduction factor = 0.75

    Returns:
        Vc1, Vc2, Vc3 (N) — three equations
        Vc_governing (N)  — minimum = governing
        phiVc (N)
        detail dict
    """
    sqrt_fc = lambda_factor * np.sqrt(fc_MPa)

    # SNI 2847:2019 Pasal 22.6.5.2 Butir (a)
    Vc1 = 0.33 * sqrt_fc * bo_mm * d_mm
    label1 = "0.33 × λ√f'c × bo × d"
    ref1 = "SNI 2847:2019 Pasal 22.6.5.2 Butir (a) [ACI 318-19 §22.6.5.2(a)]"

    # SNI 2847:2019 Pasal 22.6.5.2 Butir (b)
    Vc2 = (0.17 + 0.33 / beta) * sqrt_fc * bo_mm * d_mm
    label2 = "(0.17 + 0.33/β) × λ√f'c × bo × d"
    ref2 = "SNI 2847:2019 Pasal 22.6.5.2 Butir (b) [ACI 318-19 §22.6.5.2(b)]"

    # SNI 2847:2019 Pasal 22.6.5.2 Butir (c)
    Vc3 = (0.083 * (alpha_s * d_mm / bo_mm + 2)) * sqrt_fc * bo_mm * d_mm
    label3 = "0.083 × (αs×d/bo + 2) × λ√f'c × bo × d"
    ref3 = "SNI 2847:2019 Pasal 22.6.5.2 Butir (c) [ACI 318-19 §22.6.5.2(c)]"

    Vc_gov = min(Vc1, Vc2, Vc3)
    governing = ["(a)", "(b)", "(c)"][np.argmin([Vc1, Vc2, Vc3])]
    phiVc = phi * Vc_gov

    detail = {
        "fc_MPa": fc_MPa,
        "sqrt_fc": sqrt_fc,
        "bo_mm": bo_mm,
        "d_mm": d_mm,
        "beta": beta,
        "alpha_s": alpha_s,
        "lambda": lambda_factor,
        "phi": phi,
        "Vc1_N": Vc1, "label1": label1, "ref1": ref1,
        "Vc2_N": Vc2, "label2": label2, "ref2": ref2,
        "Vc3_N": Vc3, "label3": label3, "ref3": ref3,
        "Vc_governing_N": Vc_gov,
        "governing_eq": governing,
        "phiVc_N": phiVc,
        "phiVc_kN": phiVc / 1000,
    }
    return detail


def punching_shear_demand(qu_avg_kPa: float, B: float, L: float,
                           b_crit: float, h_crit: float,
                           Nu_col_kN: float):
    """
    Punching shear demand Vu.
    Vu = qu × A_outside_critical  (net upward pressure × area outside critical perimeter)
    OR  = Nu_col - qu × A_crit  (column force minus reaction on crit area)

    Both methods should give similar result. Use column-based (more direct).

    A_crit = b_crit × h_crit
    Vu = Nu_col - qu_avg × b_crit × h_crit

    Parameters:
        qu_avg_kPa  : average factored soil pressure (kPa)
        B, L        : footing dimensions (m)
        b_crit      : critical perimeter dim in X (m) = bc + d
        h_crit      : critical perimeter dim in Y (m) = hc + d
        Nu_col_kN   : factored axial load of this column (kN)

    Returns: Vu_kN, detail dict
    """
    A_crit = b_crit * h_crit
    Vu_kN = Nu_col_kN - qu_avg_kPa * A_crit

    detail = {
        "method": "Vu = Nu_col - qu_avg × A_crit",
        "code_ref": "SNI 2847:2019 Pasal 22.6.4",
        "qu_avg_kPa": qu_avg_kPa,
        "b_crit_m": b_crit,
        "h_crit_m": h_crit,
        "A_crit_m2": A_crit,
        "Nu_col_kN": Nu_col_kN,
        "Vu_kN": max(Vu_kN, 0.0),
    }
    return max(Vu_kN, 0.0), detail


def check_punching_shear(fc_MPa: float, bo_mm: float, d_mm: float,
                          beta: float, alpha_s: int,
                          qu_avg_kPa: float, B: float, L: float,
                          b_crit: float, h_crit: float,
                          Nu_col_kN: float,
                          lambda_factor: float = 1.0, phi: float = 0.75):
    """
    Full punching shear check for one column.
    Returns combined result dict.
    """
    Vu_kN, demand_detail = punching_shear_demand(
        qu_avg_kPa, B, L, b_crit, h_crit, Nu_col_kN)

    cap_detail = punching_shear_capacity(
        fc_MPa, bo_mm, d_mm, beta, alpha_s, lambda_factor, phi)

    ok = Vu_kN <= cap_detail["phiVc_kN"]
    ratio = Vu_kN / cap_detail["phiVc_kN"] if cap_detail["phiVc_kN"] > 0 else 999

    return {
        "Vu_kN": Vu_kN,
        "phiVc_kN": cap_detail["phiVc_kN"],
        "ratio": ratio,
        "ok": ok,
        "demand": demand_detail,
        "capacity": cap_detail,
        "recommendation": (
            "" if ok else
            f"PUNCHING SHEAR FAILS (ratio={ratio:.2f}). "
            "Increase footing thickness (t) or concrete strength (f'c)."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ONE-WAY (BEAM) SHEAR — SNI 2847:2019 Pasal 22.5
# ─────────────────────────────────────────────────────────────────────────────

def one_way_shear_capacity(fc_MPa: float, bw_mm: float, d_mm: float,
                            lambda_factor: float = 1.0, phi: float = 0.75):
    """
    φVc for one-way shear (no stirrups) — SNI 2847:2019 Pasal 22.5.5.1.

    Vc = 0.17 × λ × √f'c × bw × d

    Parameters:
        fc_MPa   : concrete strength (MPa)
        bw_mm    : beam width = footing width (mm)
        d_mm     : effective depth (mm)

    Returns: Vc_N, phiVc_N, detail dict
    """
    sqrt_fc = lambda_factor * np.sqrt(fc_MPa)
    Vc_N = 0.17 * sqrt_fc * bw_mm * d_mm
    phiVc_N = phi * Vc_N

    detail = {
        "formula": "Vc = 0.17 × λ × √f'c × bw × d",
        "code_ref": "SNI 2847:2019 Pasal 22.5.5.1 [ACI 318-19 §22.5.5.1]",
        "fc_MPa": fc_MPa,
        "sqrt_fc": sqrt_fc,
        "lambda": lambda_factor,
        "bw_mm": bw_mm,
        "d_mm": d_mm,
        "phi": phi,
        "Vc_N": Vc_N,
        "phiVc_N": phiVc_N,
        "phiVc_kN": phiVc_N / 1000,
        "Vc_kN": Vc_N / 1000,
    }
    return Vc_N, phiVc_N, detail


def one_way_shear_demand(qu_avg_kPa: float, bw_m: float, arm_m: float):
    """
    One-way shear demand at critical section (d from column face).

    Vu = qu_avg × bw × arm

    Parameters:
        qu_avg_kPa : average factored soil pressure
        bw_m       : width perpendicular to shear direction (m)
        arm_m      : distance from column face to footing edge minus d (m)

    Returns: Vu_kN, detail dict
    """
    Vu_kN = qu_avg_kPa * bw_m * arm_m
    detail = {
        "formula": "Vu = qu_avg × bw × arm",
        "code_ref": "SNI 2847:2019 Pasal 22.5 — critical section at d from col face",
        "qu_avg_kPa": qu_avg_kPa,
        "bw_m": bw_m,
        "arm_m": arm_m,
        "Vu_kN": Vu_kN,
    }
    return Vu_kN, detail


def check_one_way_shear(fc_MPa: float, B_m: float, L_m: float,
                         d_mm: float, qu_avg_kPa: float,
                         bc_m: float, hc_m: float,
                         col_x: float = 0.0, col_y: float = 0.0,
                         lambda_factor: float = 1.0, phi: float = 0.75):
    """
    One-way shear check in both X and Y directions.
    For multi-column, uses centroidal column position.

    Returns dict with X and Y results.
    """
    d_m = d_mm / 1000

    # --- X-DIRECTION shear (shear across width B, critical at d from col face in L-dir) ---
    # Arm = (L/2 - hc/2 - d) for one side (conservative: take max arm)
    arm_x = max((L_m / 2 - abs(col_x) - hc_m / 2 - d_m), 0.0)
    bw_x_mm = B_m * 1000

    Vu_x_kN, dem_x = one_way_shear_demand(qu_avg_kPa, B_m, arm_x)
    _, phiVc_x_N, cap_x = one_way_shear_capacity(fc_MPa, bw_x_mm, d_mm, lambda_factor, phi)
    phiVc_x_kN = phiVc_x_N / 1000
    ok_x = Vu_x_kN <= phiVc_x_kN

    # --- Y-DIRECTION shear (shear across length L, critical at d from col face in B-dir) ---
    arm_y = max((B_m / 2 - abs(col_y) - bc_m / 2 - d_m), 0.0)
    bw_y_mm = L_m * 1000

    Vu_y_kN, dem_y = one_way_shear_demand(qu_avg_kPa, L_m, arm_y)
    _, phiVc_y_N, cap_y = one_way_shear_capacity(fc_MPa, bw_y_mm, d_mm, lambda_factor, phi)
    phiVc_y_kN = phiVc_y_N / 1000
    ok_y = Vu_y_kN <= phiVc_y_kN

    return {
        "x_dir": {
            "direction": "X (shear perpendicular to X-axis, width = B)",
            "Vu_kN": Vu_x_kN,
            "phiVc_kN": phiVc_x_kN,
            "arm_m": arm_x,
            "bw_mm": bw_x_mm,
            "ok": ok_x,
            "ratio": Vu_x_kN / phiVc_x_kN if phiVc_x_kN > 0 else 999,
            "demand": dem_x,
            "capacity": cap_x,
        },
        "y_dir": {
            "direction": "Y (shear perpendicular to Y-axis, width = L)",
            "Vu_kN": Vu_y_kN,
            "phiVc_kN": phiVc_y_kN,
            "arm_m": arm_y,
            "bw_mm": bw_y_mm,
            "ok": ok_y,
            "ratio": Vu_y_kN / phiVc_y_kN if phiVc_y_kN > 0 else 999,
            "demand": dem_y,
            "capacity": cap_y,
        },
        "all_ok": ok_x and ok_y,
        "recommendation": (
            "" if (ok_x and ok_y) else
            "ONE-WAY SHEAR FAILS. Increase footing thickness (t). "
            "Note: stirrups in footings are generally not practical."
        ),
    }
