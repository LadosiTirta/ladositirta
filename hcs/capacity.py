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
    Stress in prestressing steel at nominal moment capacity.
    ACI 318-19 Eq. 20.3.2.4.1 (approximate):
        fps = fpu * (1 - gamma_p/beta1 * rho_p * fpu / f_c)
    For HCS without mild steel.
    gamma_p = 0.28 for low-relaxation strand/wire
    beta1 = 0.85 for f_c <= 28 MPa, reduces by 0.05 per 7 MPa above 28, min 0.65
    """
    if beta1 <= 0:
        beta1 = 0.85
    fps = fpu * (1 - gamma_p / beta1 * rho_p * fpu / f_c)
    # Upper bound: fpu, lower bound: fpy
    return max(min(fps, fpu), fpy)


def calc_moment_capacity(Aps, fps, dp, f_c, b, beta1, a_limit=None):
    """
    Nominal moment capacity Mn (kN·mm) and phi*Mn.
    ACI 318-19 §22.3:
        a = Aps * fps / (0.85 * f_c * b)
        Mn = Aps * fps * (dp - a/2)   [N·mm]
    Returns dict with Mn_Nmm, Mn_kNm, phi_Mn_kNm, a, status_flange
    """
    Aps_mm2 = Aps
    fps_MPa = fps
    dp_mm = dp
    f_c_MPa = f_c
    b_mm = b
    # Neutral axis depth
    a_mm = Aps_mm2 * fps_MPa / (0.85 * f_c_MPa * b_mm)
    # Check if a exceeds flange thickness (if limit given)
    flange_ok = True
    if a_limit is not None:
        if a_mm > a_limit:
            flange_ok = False
            # Simplified: T-section behavior, but for HCS with topping we assume within flange
            # For accuracy, we would need more complex calc, but for now warn.
            pass
    Mn_Nmm = Aps_mm2 * fps_MPa * (dp_mm - a_mm/2)
    phi = 0.9  # tension-controlled
    phi_Mn_Nmm = phi * Mn_Nmm
    return {
        "a": a_mm,
        "Mn_Nmm": Mn_Nmm,
        "Mn_kNm": Mn_Nmm / 1e6,
        "phi_Mn_kNm": phi_Mn_Nmm / 1e6,
        "flange_ok": flange_ok
    }


def calc_Vci(f_c, bw, dp, fpe, Vd, Vi, Mcre, Mmax):
    """
    Flexure-shear cracking strength (N).
    ACI 318-19 Eq. 22.5.8.3.1:
        Vci = 0.05*lambda*sqrt(f_c)*bw*dp + Vd + Vi*Mcre/Mmax
    lambda = 1.0 for normal weight concrete.
    fpe = effective prestress stress at centroid of steel = Pe/Aps (MPa)
    Vd = shear due to unfactored dead load
    Vi = factored shear due to superimposed loads
    Mcre = cracking moment (N·mm)
    Mmax = factored moment at section
    """
    lam = 1.0
    sqrt_fc = math.sqrt(f_c)
    term1 = 0.05 * lam * sqrt_fc * bw * dp   # N
    # Vd, Vi in N, Mcre, Mmax in N·mm
    Vci = term1 + Vd + Vi * Mcre / max(Mmax, 1.0)
    return Vci


def calc_Vcw(f_c, bw, dp, fpc, Vp=0):
    """
    Web-shear cracking strength (N).
    ACI 318-19 Eq. 22.5.8.3.2:
        Vcw = (0.29*lambda*sqrt(f_c) + 0.3*fpc)*bw*dp + Vp
    fpc = compressive stress at centroid of section due to effective prestress (MPa)
    Vp = vertical component of prestress (0 for straight tendons)
    """
    lam = 1.0
    sqrt_fc = math.sqrt(f_c)
    term1 = 0.29 * lam * sqrt_fc + 0.3 * fpc
    Vcw = term1 * bw * dp + Vp
    return Vcw


def get_capacity_results(ss):
    """
    Master function for Phase 5.
    Reads session_state, computes flexural and shear capacity.
    Returns dict with keys:
        cap_fps, cap_Mn_kNm, cap_phi_Mn_kNm, cap_a, cap_flange_ok,
        cap_Vci_max, cap_Vcw_max, cap_phi_Vn_min, cap_DCR_M, cap_DCR_V,
        cap_needs_Av_min (bool)
    """
    # --- Flexural capacity ---
    # Properties
    Aps_bot = ss.get("Aps_bot", 0.0)
    dp_bot = ss.get("dp_bot", 0.0)
    f_c = ss.get("f_c", 50.0)
    b_eff = ss.get("b_top", ss.get("b_bottom", 1200))   # effective flange width
    fpu = ss.get("fpu", 1860)
    fpy = ss.get("fpy", 1675)
    Eps = ss.get("Eps", 196500)
    # Reinforcement ratio rho_p
    b_web = ss.get("b_bottom", b_eff)  # approximate, but for rho_p use effective width
    # For simplicity, use b_eff for rho_p
    rho_p = Aps_bot / (b_eff * dp_bot) if dp_bot>0 else 0
    # Beta1
    if f_c <= 28:
        beta1 = 0.85
    else:
        beta1 = 0.85 - 0.05 * (f_c - 28)/7
        beta1 = max(beta1, 0.65)
    gamma_p = 0.28  # low-relaxation
    fps = calc_fps(fpu, fpy, Eps, rho_p, f_c, beta1, gamma_p)
    # Flange limit: if topping exists, a_limit = topping thickness? Actually for HCS, if a > topping thickness, need T-section calc.
    # We'll set a_limit = ss.get("t_topping", 1e6) (large if no topping)
    t_topping = ss.get("t_topping", 0)
    a_limit = t_topping if t_topping>0 else None
    Mn_result = calc_moment_capacity(Aps_bot, fps, dp_bot, f_c, b_eff, beta1, a_limit)
    # --- Shear capacity ---
    # Section properties
    bw = ss.get("bw_shear", ss.get("b_bottom", 1200))  # web width
    dp = dp_bot   # effective depth
    f_ci = ss.get("f_ci", 35.0)  # for cracking? Use f_c for service
    # Effective prestress after losses
    Pe = ss.get("pl_Pe", 0.0)  # kN
    Aps_total = Aps_bot + ss.get("Aps_top", 0.0)
    if Aps_total > 0:
        fpe = (Pe * 1000) / Aps_total   # MPa
    else:
        fpe = 0.0
    # Compressive stress at centroid due to prestress (fpc)
    # fpc = Pe / An (converted to MPa)
    An = ss.get("sp_An", 1e6)
    fpc = (Pe * 1000) / An if An>0 else 0.0
    # Shear forces from load diagrams (factored)
    # We need Vu along span, but for simplified check use max Vu
    Vu_max = ss.get("lb_Vu_max", 0.0)  # kN
    # For Vci, need Vd (unfactored dead load shear) and Vi (factored superimposed shear)
    # Approximations: use w_sw and w_sdl+topping for Vd, and w_ll+point for Vi
    L_an = ss.get("L_an", 6000)
    w_sw = ss.get("SW_HCS", 0) * ss.get("b_bottom", 1200) / 1e6  # kN/mm
    Vd = w_sw * L_an / 2 * 1000  # N
    w_sdl = ss.get("SW_topping",0) + ss.get("SDL",0)
    w_sdl_line = w_sdl * ss.get("b_bottom",1200)/1e6
    w_ll_line = ss.get("LL",0) * ss.get("b_bottom",1200)/1e6
    # Factored superimposed: 1.2*(SDL+SW_topping) + 1.6*LL
    w_sup_factor = 1.2*(ss.get("SDL",0)+ss.get("SW_topping",0)) + 1.6*ss.get("LL",0)
    w_sup_line = w_sup_factor * ss.get("b_bottom",1200)/1e6
    Vi = w_sup_line * L_an / 2 * 1000   # N
    # Cracking moment Mcre (approx) = 0.5*sqrt(f_c)*Sb_net (N·mm)
    Sb_net = ss.get("sp_Sb_net", 1e6)
    Mcre = 0.5 * math.sqrt(f_c) * Sb_net   # N·mm
    # Max factored moment (N·mm)
    Mmax = ss.get("lb_Mu_max", 1e6) * 1000  # kN·m -> N·mm
    # Compute Vci at critical section (simplified at support)
    Vci = calc_Vci(f_c, bw, dp, fpe, Vd, Vi, Mcre, Mmax)
    Vcw = calc_Vcw(f_c, bw, dp, fpc)
    Vn = min(Vci, Vcw)
    phi_v = 0.75
    phi_Vn = phi_v * Vn / 1000   # kN
    # Demand-capacity ratios
    Mn_kNm = Mn_result["Mn_kNm"]
    phi_Mn_kNm = Mn_result["phi_Mn_kNm"]
    # Use max moment from load combo
    Mu_max = ss.get("lb_Mu_max", 1e6) / 1e6  # kN·m
    DCR_M = Mu_max / phi_Mn_kNm if phi_Mn_kNm>0 else 99
    DCR_V = Vu_max / phi_Vn if phi_Vn>0 else 99
    # ACI/PCI 319-25 special requirement: if h > 317mm and no topping, need Av_min if Vu > 0.5*phi*Vcw
    h_hcs = ss.get("h", 200)
    need_Av_min = False
    if h_hcs > 317 and not ss.get("has_topping", False):
        if Vu_max > 0.5 * phi_v * (Vcw/1000):
            need_Av_min = True
    return {
        "cap_fps": fps,
        "cap_Mn_kNm": Mn_kNm,
        "cap_phi_Mn_kNm": phi_Mn_kNm,
        "cap_a": Mn_result["a"],
        "cap_flange_ok": Mn_result["flange_ok"],
        "cap_Vci_kN": Vci/1000,
        "cap_Vcw_kN": Vcw/1000,
        "cap_phi_Vn_kN": phi_Vn,
        "cap_DCR_M": DCR_M,
        "cap_DCR_V": DCR_V,
        "cap_needs_Av_min": need_Av_min,
    }
