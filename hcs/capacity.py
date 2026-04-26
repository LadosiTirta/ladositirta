"""
HCS Design — Flexural & Shear Capacity (Phase 5)
==================================================
Reference : ACI/PCI CODE-319-25 Cl. 22.2, 22.5, 22.6, 26.9
            PCI Design Handbook, 8th Edition Sec. 4.2 & 5.2
Units     : SI only (mm, kN, MPa)
"""

import math
import numpy as np


def calc_fps(fpu, fpy, Eps, rho_p, f_c, beta1, gamma_p=0.28):
    """
    Stress in prestressing steel at nominal strength.
    ACI 318-19 Eq. 20.3.2.4.1 (approximate for bonded tendons)
    For HCS without mild steel: fps = fpu * (1 - (rho_p * fpu) / (beta1 * f_c) * gamma_p)
    """
    term = (rho_p * fpu) / (beta1 * f_c) * gamma_p
    fps = fpu * (1 - term)
    return min(fps, fpy)   # cannot exceed fpy per ACI


def calc_moment_capacity(Aps, fps, dp, f_c, b, a_limit=None, phi=0.9):
    """
    Nominal and design moment capacity.
    a = depth of compression block (mm)
    Mn = Aps * fps * (dp - a/2)   (N·mm)
    Returns: Mn (kN·m), phi_Mn (kN·m), a (mm)
    """
    if Aps <= 0 or fps <= 0:
        return 0.0, 0.0, 0.0
    # Compression block depth
    a = Aps * fps / (0.85 * f_c * b)   # mm
    # Check if a exceeds flange thickness (if provided)
    if a_limit is not None and a > a_limit:
        # T-section behavior (simplified: use limit as effective flange)
        a = a_limit
    Mn_Nmm = Aps * fps * (dp - a/2)   # N·mm
    Mn = Mn_Nmm / 1e6                 # kN·m
    phi_Mn = phi * Mn
    return Mn, phi_Mn, a


def calc_Vci(f_c, bw, dp, fpe, Vu, Mu, Mg, lambda_factor=1.0):
    """
    Flexure-shear capacity (Vci) in kN.
    ACI 318-19 Eq. 22.5.8.3.1:
    Vci = 0.05*lambda*sqrt(f_c)*bw*dp + Vd + Vi*Mcre/Mmax
    For simplicity, use conservative approach:
    Vci = 0.05*sqrt(f_c)*bw*dp + (Vu - Mg/dp)   (simplified)
    Returns Vci in kN.
    """
    sqrt_fc = math.sqrt(f_c)
    Vc_min = 0.05 * lambda_factor * sqrt_fc * bw * dp   # N -> kN
    Vc_min_kN = Vc_min / 1000.0
    # Simplified: take Vu as nominal, but we need consistent units
    # For design, we'll compute envelope later.
    # Return a base value; master function will compute along span.
    return Vc_min_kN


def calc_Vcw(f_c, bw, dp, fpc, Vp=0, lambda_factor=1.0):
    """
    Web-shear capacity (Vcw) in kN.
    ACI 318-19 Eq. 22.5.8.3.2:
    Vcw = (0.29*lambda*sqrt(f_c) + 0.3*fpc)*bw*dp + Vp
    """
    sqrt_fc = math.sqrt(f_c)
    term = 0.29 * lambda_factor * sqrt_fc + 0.3 * fpc
    Vcw_N = term * bw * dp + Vp
    return Vcw_N / 1000.0   # kN


def get_capacity_results(ss):
    """
    Master function to compute moment and shear capacity.
    Reads session_state and returns dict with prefix 'cap_'.
    Keys:
      cap_fps, cap_Mn, cap_phi_Mn, cap_a
      cap_Vci_arr, cap_Vcw_arr, cap_phi_Vn_arr (arrays along span)
      cap_DCR_M, cap_DCR_V, cap_needs_Av_min
    """
    # ----- Read from session_state -----
    # Materials
    f_c = ss["f_c"]
    fpu = ss["fpu"]
    fpy = ss["fpy"]
    Eps = ss["Eps"]   # not directly used here but kept
    # Prestress
    Aps = ss["Aps_bot"]   # assume only bottom steel for flexure
    dp = ss["dp_bot"]     # effective depth (mm)
    Pe = ss.get("pl_Pe", ss["Pi"])   # effective prestress after losses (kN)
    # Geometry for flexure
    b = ss["b_top"]       # width of compression flange (mm)
    # For T-section, check if a > topping thickness? Not implemented yet.
    # Beta1 from f_c (ACI 318-19 Table 22.2.2.4.3)
    if f_c <= 28:
        beta1 = 0.85
    elif f_c < 55:
        beta1 = 0.85 - 0.05 * (f_c - 28) / 7
    else:
        beta1 = 0.65
    # Reinforcement ratio rho_p
    rho_p = Aps / (b * dp) if b * dp > 0 else 0.0

    # ----- Flexural capacity -----
    fps = calc_fps(fpu, fpy, Eps, rho_p, f_c, beta1)
    Mn, phi_Mn, a = calc_moment_capacity(Aps, fps, dp, f_c, b, a_limit=ss.get("tf_top", 100))
    # Factored moment from loads
    Mu_max = ss.get("lb_Mu_max", 0) / 1e6   # kN·m
    DCR_M = Mu_max / phi_Mn if phi_Mn > 0 else 999.0

    # ----- Shear capacity -----
    # Dimensions
    bw = ss.get("bw_shear", ss["b_bottom"] - ss["n_core"] * ss["d_core"])
    # Prestress effects
    fpc = Pe * 1000 / ss["sp_An"]   # concrete compressive stress at centroid (MPa)
    # Shear demand along span
    x_arr = ss["lb_x_arr"]          # mm
    Vu_arr = ss["lb_Vu_arr"]        # kN
    Mu_arr = ss["lb_Mu_arr"] / 1e6  # kN·m
    # Mg (self-weight moment) – use service moment? For Vci, use factored? Let's simplify.
    # We'll compute Vci and Vcw at each point
    Vci_arr = np.zeros_like(Vu_arr)
    Vcw_arr = np.zeros_like(Vu_arr)
    phi_Vn_arr = np.zeros_like(Vu_arr)
    for i, x in enumerate(x_arr):
        # For Vci, use Vu and Mu at that point
        Vu = abs(Vu_arr[i])
        Mu = abs(Mu_arr[i])
        # Simplified Vci (lower bound)
        Vci = calc_Vci(f_c, bw, dp, fpc, Vu, Mu, 0.0)
        Vcw = calc_Vcw(f_c, bw, dp, fpc)
        Vn = min(Vci, Vcw)
        phi_V = 0.75
        phi_Vn_arr[i] = phi_V * Vn
        Vci_arr[i] = Vci
        Vcw_arr[i] = Vcw
    # Minimum shear capacity along span
    phi_Vn_min = np.min(phi_Vn_arr) if len(phi_Vn_arr) > 0 else 0.0
    Vu_max = ss.get("lb_Vu_max", 0)
    DCR_V = Vu_max / phi_Vn_min if phi_Vn_min > 0 else 999.0

    # Check ACI/PCI requirement: if h > 317mm and no topping and Vu > 0.5*phi*Vcw
    h = ss["h"]
    has_topping = ss.get("has_topping", False)
    needs_Av_min = False
    if h > 317 and not has_topping:
        # Check at critical section (typically at distance d from support)
        # For simplicity, check maximum Vu location
        idx_max = np.argmax(np.abs(Vu_arr))
        if phi_Vn_arr[idx_max] > 0:
            if abs(Vu_arr[idx_max]) > 0.5 * phi_Vn_arr[idx_max]:
                needs_Av_min = True

    return {
        "cap_fps": fps,
        "cap_Mn": Mn,
        "cap_phi_Mn": phi_Mn,
        "cap_a": a,
        "cap_DCR_M": DCR_M,
        "cap_Vci_arr": Vci_arr,
        "cap_Vcw_arr": Vcw_arr,
        "cap_phi_Vn_arr": phi_Vn_arr,
        "cap_phi_Vn_min": phi_Vn_min,
        "cap_DCR_V": DCR_V,
        "cap_needs_Av_min": needs_Av_min,
    }
