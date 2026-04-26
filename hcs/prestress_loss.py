"""
HCS Design — Prestress Losses (Phase 3)
========================================
Reference : ACI/PCI CODE-319-25 Cl. 26.10
            PCI Design Handbook, 8th Edition Sec. 4.7
            ACI 318-19
Units     : SI only (mm, kN, MPa)
"""

import math


def loss_elastic_shortening(f_ci, Ec_ci, Eps, Pi, e, An, In, Mg_sw):
    """
    Elastic shortening loss (ES) in MPa.
    PCI Design Handbook 8th Ed. Eq. 4.7.2:
        ES = (Eps / Ec_ci) * fcgp
    """
    Pi_N = Pi * 1000  # N
    Mg_sw_Nmm = Mg_sw * 1000.0
    fcgp = (Pi_N / An) + (Pi_N * e * e / In) - (Mg_sw_Nmm * e / In)
    ES = (Eps / Ec_ci) * fcgp
    return max(ES, 0.0)


def loss_creep(fcgp, fcdp, Eps, Ec, Kcr=2.0):
    """Creep loss (CR) in MPa."""
    CR = Kcr * (Eps / Ec) * (fcgp - fcdp)
    return max(CR, 0.0)


def loss_shrinkage(Eps, RH=75.0, V_S=38.0, Ksh=1.0):
    """Shrinkage loss (SH) in MPa."""
    SH = 8.2e-6 * Ksh * Eps * (1 - 0.06 * V_S) * (100 - RH)
    return max(SH, 0.0)


def loss_relaxation(ps_type, fpi, fpu, sum_other_losses):
    """Relaxation loss (RE) in MPa."""
    Kre = 34.5  # MPa
    J = 0.04
    if "Wire" in ps_type:
        C = 1.0
    else:
        ratio = fpi / fpu
        C = 1.45 - 0.3 * ratio
        C = max(C, 0.5)
    RE = (Kre - J * sum_other_losses) * C
    return max(RE, 0.0)


def get_prestress_losses(ss):
    """
    Master function to compute all prestress losses.
    Reads session_state dict (ss).
    Returns dict with keys prefixed 'pl_'.
    """
    RH = ss.get("RH", 75.0)
    V_S = ss.get("V_S", 38.0)

    # Materials
    wc = ss["wc"]
    f_ci = ss["f_ci"]
    Ec_ci = 0.043 * (wc * 1000 / 9.81) ** 1.5 * math.sqrt(f_ci)
    Ec = ss.get("Ec_hcs", 33000.0)
    Eps = ss["Eps"]

    # Prestress
    Pi = ss["Pi"]  # kN
    Aps_bot = ss["Aps_bot"]
    Aps_top = ss.get("Aps_top", 0.0)
    Aps_total = Aps_bot + Aps_top
    e_bot = ss.get("sp_e_bot", 0.0)
    e_top = ss.get("sp_e_top", 0.0)
    if Aps_total > 0:
        e_net = (Aps_bot * e_bot - Aps_top * e_top) / Aps_total
    else:
        e_net = 0.0

    # Net section properties (keys from get_all_section_props)
    An = ss["sp_An"]          # <-- perbaikan: sp_An
    In = ss["sp_In"]          # <-- perbaikan: sp_In
    yb = ss["sp_yb"]          # <-- perbaikan: sp_yb (tidak dipakai, tapi untuk referensi)
    L = ss["L_an"]  # mm
    w_sw = ss["SW_HCS"] * ss["b_bottom"] / 1e6  # kN/mm
    Mg_sw = (w_sw * L * L) / 8.0  # kN·mm

    # Elastic shortening
    ES = loss_elastic_shortening(f_ci, Ec_ci, Eps, Pi, e_net, An, In, Mg_sw)

    # Stress at PS centroid after transfer
    Pi_N = Pi * 1000
    Mg_sw_Nmm = Mg_sw * 1000
    fcgp = (Pi_N / An) + (Pi_N * e_net * e_net / In) - (Mg_sw_Nmm * e_net / In)

    # fcdp: stress due to SDL (simplified)
    if ss.get("has_topping", False):
        w_sdl_area = ss["SW_topping"] + ss["SDL"]  # kN/m²
        w_sdl_line = w_sdl_area * ss["b_bottom"] / 1e6  # kN/mm
        M_sdl = (w_sdl_line * L * L) / 8.0  # kN·mm
        I_comp = ss.get("sp_I_comp", In)
        fcdp = (M_sdl * 1000.0 * e_net) / I_comp if I_comp > 0 else 0.0
    else:
        fcdp = 0.0

    CR = loss_creep(fcgp, fcdp, Eps, Ec, Kcr=2.0)
    SH = loss_shrinkage(Eps, RH, V_S)
    sum_other = ES + CR + SH
    RE = loss_relaxation(ss["ps_type"], ss["fpi"], ss["fpu"], sum_other)

    total_loss_MPa = ES + CR + SH + RE
    fpi = ss["fpi"]
    total_loss_pct = (total_loss_MPa / fpi) * 100.0 if fpi > 0 else 0.0
    fse = fpi - total_loss_MPa
    Pe = fse * Aps_total / 1000.0
    if Aps_total > 0:
        Pe_bot = fse * Aps_bot / 1000.0
        Pe_top = fse * Aps_top / 1000.0
    else:
        Pe_bot = Pe_top = 0.0

    return {
        "pl_ES": ES,
        "pl_CR": CR,
        "pl_SH": SH,
        "pl_RE": RE,
        "pl_total_MPa": total_loss_MPa,
        "pl_total_pct": total_loss_pct,
        "pl_fse": fse,
        "pl_Pe": Pe,
        "pl_Pe_bot": Pe_bot,
        "pl_Pe_top": Pe_top,
        "pl_fse_MPa": fse,
        "pl_fpi_MPa": fpi,
    }
