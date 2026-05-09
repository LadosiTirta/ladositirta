"""
footing_strip/shear.py
One‑way shear check for strip footing (SNI 2847:2019 Pasal 22.5).
"""
import numpy as np

def one_way_shear_capacity_strip(fc_MPa: float, bw_mm: float, d_mm: float,
                                  lambda_factor: float = 1.0, phi: float = 0.75):
    sqrt_fc = lambda_factor * np.sqrt(fc_MPa)
    Vc_N = 0.17 * sqrt_fc * bw_mm * d_mm
    phiVc_N = phi * Vc_N
    detail = {
        "formula": "Vc = 0.17 × λ × √f'c × bw × d",
        "code_ref": "SNI 2847:2019 Pasal 22.5.5.1 [ACI 318-19 §22.5.5.1]",
        "fc_MPa": fc_MPa, "lambda": lambda_factor,
        "bw_mm": bw_mm, "d_mm": d_mm, "phi": phi,
        "Vc_N": Vc_N, "phiVc_N": phiVc_N, "phiVc_kN": phiVc_N / 1000,
        "Vc_kN": Vc_N / 1000,
    }
    return phiVc_N, detail

def check_one_way_shear_strip(fc_MPa: float, B_m: float, d_mm: float,
                               qu_avg_kPa: float, bw_m: float,
                               phi_shear: float = 0.75, lam: float = 1.0):
    """
    One‑way shear check for strip footing.
    Critical section at distance d from wall face.
    Wall centred on footing width B.
    """
    d_m = d_mm / 1000
    arm = max((B_m - bw_m) / 2 - d_m, 0.0)   # distance from wall face to edge - d
    bw_unit = 1000.0  # per meter length (mm)

    # Demand
    Vu_kN = qu_avg_kPa * 1.0 * arm   # kN per meter length
    # Capacity
    phiVc_N, cap_detail = one_way_shear_capacity_strip(fc_MPa, bw_unit, d_mm, lam, phi_shear)
    phiVc_kN = phiVc_N / 1000
    ok = Vu_kN <= phiVc_kN

    return {
        "Vu_kN": Vu_kN,
        "phiVc_kN": phiVc_kN,
        "arm_m": arm,
        "ok": ok,
        "ratio": Vu_kN / phiVc_kN if phiVc_kN > 0 else 999,
        "capacity": cap_detail,
        "recommendation": "" if ok else "ONE‑WAY SHEAR FAILS. Increase footing thickness t."
    }
