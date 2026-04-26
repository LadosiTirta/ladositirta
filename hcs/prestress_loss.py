"""
HCS Design — Prestress Losses (Phase 3)
========================================
Reference : ACI/PCI CODE-319-25 Cl. 26.10
            PCI Design Handbook, 8th Edition Sec. 4.7
            ACI 318-19
Units     : SI only (mm, kN, MPa)

Functions
---------
loss_elastic_shortening  : ES loss (PCI Eq. 4.7.2)
loss_creep               : CR loss (PCI Eq. 4.7.3)
loss_shrinkage           : SH loss (PCI Eq. 4.7.4)
loss_relaxation          : RE loss (PCI Eq. 4.7.5)
get_prestress_losses     : Master function, reads session_state
"""

import math


def loss_elastic_shortening(f_ci, Ec_ci, Eps, Pi, e, An, In, Mg_sw):
    """
    Elastic shortening loss (ES) in MPa.
    
    PCI Design Handbook 8th Ed. Eq. 4.7.2:
        ES = (Eps / Ec_ci) * fcgp
    where
        fcgp = stress in concrete at centroid of PS steel at transfer
        fcgp = Pi/An + Pi*e^2/In - Mg_sw*e/In
    Pi    : initial prestress force (kN)
    e     : eccentricity of PS steel (mm)
    An    : net area (mm²)
    In    : net moment of inertia (mm⁴)
    Mg_sw : moment due to self-weight at midspan (kN·mm)
    Ec_ci : concrete modulus at transfer (MPa)
    Eps   : steel modulus (MPa)

    Note: Mg_sw should be the midspan moment. For simply supported,
    Mg_sw = w_sw * L^2 / 8, with w_sw in kN/mm, L in mm.
    This function does not compute Mg_sw; it is passed.
    """
    # Convert Pi from kN to N (to keep consistent MPa units: N/mm²)
    Pi_N = Pi * 1000  # N
    Mg_sw_Nmm = Mg_sw * 1e6  # kN·mm → N·mm (since 1 kN·m = 1e6 N·mm)
    # But careful: Pi in kN, e in mm, An in mm² → Pi*1000 / An = N/mm² (MPa)
    fcgp = (Pi_N / An) + (Pi_N * e * e / In) - (Mg_sw_Nmm * e / In)
    ES = (Eps / Ec_ci) * fcgp
    return max(ES, 0.0)   # loss cannot be negative


def loss_creep(fcgp, fcdp, Eps, Ec, Kcr=2.0):
    """
    Creep loss (CR) in MPa.
    
    PCI Design Handbook 8th Ed. Eq. 4.7.3:
        CR = Kcr * (Eps / Ec) * (fcgp - fcdp)
    where:
        Kcr = 2.0 for normal weight concrete
        fcdp = concrete stress at PS centroid due to sustained dead load
               (superimposed dead load, but not live load)
    fcgp : stress at PS centroid at transfer (MPa)
    fcdp : stress at PS centroid due to SDL (MPa)
    Eps  : steel modulus (MPa)
    Ec   : concrete modulus at 28 days (MPa)
    """
    CR = Kcr * (Eps / Ec) * (fcgp - fcdp)
    return max(CR, 0.0)


def loss_shrinkage(Eps, RH=75.0, V_S=38.0, Ksh=1.0):
    """
    Shrinkage loss (SH) in MPa.
    
    PCI Design Handbook 8th Ed. Eq. 4.7.4:
        SH = 8.2e-6 * Ksh * Eps * (1 - 0.06 * V_S) * (100 - RH)
    where
        RH = relative humidity (%)
        V_S = volume to surface ratio (mm) (typical 38 mm for HCS)
        Ksh = 1.0 for moist cured
        Eps = steel modulus (MPa)
    """
    SH = 8.2e-6 * Ksh * Eps * (1 - 0.06 * V_S) * (100 - RH)
    return max(SH, 0.0)


def loss_relaxation(fpi, fpy, fpu, ps_type="7-Wire Strand (low relax)", time_days=10000.0):
    """
    Steel relaxation loss (RE) in MPa.
    
    PCI Design Handbook 8th Ed. Eq. 4.7.5:
        For low-relaxation strand:
            RE = [Kre - J*(SH+CR+ES)] * C
        where:
            Kre = 34.5 MPa (5000 psi)
            J   = 0.04
            C   = relaxation factor from PCI Table 4.7.3.2
                approx: C = 1.45 - 0.3*(fpi/fpu)  for LR strand
        For stress-relieved wire:
            Kre = 34.5 MPa
            J   = 0.04
            C   = 1.0  (conservative)
    
    This function returns RE alone (not using other losses yet),
    but the full formula needs SH+CR+ES. In master function,
    we compute RE after other losses.
    """
    if "Wire" in ps_type:
        C = 1.0
    else:  # low-relax strand
        ratio = fpi / fpu
        C = 1.45 - 0.3 * ratio
        C = max(C, 0.5)   # reasonable bound
    Kre = 34.5  # MPa
    J = 0.04
    # We'll compute RE after we have SH+CR+ES; so just return base expression
    # Actually we need to return coefficient (Kre - J*sum_other) * C
    # But we'll compute it in master.
    # For simplicity, we provide a function that returns RE given sum_other.
    def calc_RE(sum_other):
        val = (Kre - J * sum_other) * C
        return max(val, 0.0)
    return calc_RE


def get_prestress_losses(ss):
    """
    Master function to compute all prestress losses.
    
    Reads session_state dict (ss) for required keys.
    Returns dict with keys prefixed 'pl_':
        pl_ES, pl_CR, pl_SH, pl_RE      (each in MPa)
        pl_total_MPa, pl_total_pct
        pl_fse, pl_Pe, pl_fse_MPa (effective stress)
        pl_Pe_bot, pl_Pe_top (per layer, kN)
    
    Required keys in ss:
        f_ci, f_c, Ec_hcs, Eps
        Aps_bot, Aps_top, Pi, e_bot, e_top
        An, In, yb_net, h
        L_an, SW_HCS, has_topping, wc, wc_top
        RH (optional, default 75), V_S (optional, default 38)
        pl_use_detailed (optional, bool) reserved for future
    """
    # Default values for RH and V_S
    RH = ss.get("RH", 75.0)
    V_S = ss.get("V_S", 38.0)
    
    # Material moduli
    Eps = ss["Eps"]
    Ec_ci = 0.043 * (ss["wc"] * 1000 / 9.81) ** 1.5 * math.sqrt(ss["f_ci"])
    Ec = ss.get("Ec_hcs", 33000.0)  # use stored if available
    
    # Prestress details
    Pi = ss["Pi"]  # kN
    Aps_bot = ss["Aps_bot"]
    Aps_top = ss.get("Aps_top", 0.0)
    Aps_total = Aps_bot + Aps_top
    
    # Eccentricities (already computed in section_props)
    e_bot = ss.get("sp_e_bot", 0.0)
    e_top = ss.get("sp_e_top", 0.0)
    # Weighted average eccentricity for force location
    if Aps_total > 0:
        e_net = (Aps_bot * e_bot - Aps_top * e_top) / Aps_total
    else:
        e_net = 0.0
    
    # Net section properties (for non-composite)
    An = ss["sp_A_net"]
    In = ss["sp_I_net"]
    yb = ss["sp_yb_net"]
    h_hcs = ss["h"]
    
    # Midspan moment due to self-weight (HCS only, no topping)
    L = ss["L_an"]  # mm
    w_sw = ss["SW_HCS"] * ss["b_bottom"] / 1e6  # kN/mm (line load)
    Mg_sw = (w_sw * L * L) / 8.0  # kN·mm
    # Convert to N·mm for stress calculation: factor 1000? Actually Mg_sw in kN·mm,
    # to get N·mm multiply by 1000. But formula uses consistent units:
    # Pi in N, e in mm, In in mm⁴, Mg_sw in N·mm.
    # So pass Mg_sw_Nmm = Mg_sw * 1000.
    Mg_sw_Nmm = Mg_sw * 1000.0
    
    # Elastic shortening
    ES = loss_elastic_shortening(ss["f_ci"], Ec_ci, Eps, Pi, e_net, An, In, Mg_sw_Nmm)
    
    # Stress at PS centroid after transfer (for creep)
    Pi_N = Pi * 1000
    fcgp = (Pi_N / An) + (Pi_N * e_net * e_net / In) - (Mg_sw_Nmm * e_net / In)
    
    # For fcdp: stress due to superimposed dead load (SDL only, not LL)
    # Use composite section for SDL? Actually sustained loads after topping are on composite.
    # But creep loss formula uses stress at PS centroid due to sustained loads.
    # We need a simplified approach: assume fcdp = (M_SDL / I_comp) * e_net (or similar)
    # For now, if topping exists, we compute approximate fcdp.
    # We'll read M_SDL from load diagram max moment for SDL only.
    # Calculate M_SDL from loads: SW_topping + SDL (both in kN/m²)
    # Since we don't have distribution of SDL moment along span, use max midspan moment.
    if ss.get("has_topping", False):
        w_sdl_area = ss["SW_topping"] + ss["SDL"]  # kN/m²
        w_sdl_line = w_sdl_area * ss["b_bottom"] / 1e6  # kN/mm
        M_sdl = (w_sdl_line * L * L) / 8.0  # kN·mm
        # Use composite section properties
        I_comp = ss.get("sp_I_comp", In)
        # Distance from centroid to PS steel (approx e_net relative to composite centroid)
        # For simplicity, assume same e_net relative to composite NA? Not accurate.
        # Better: use stress at PS location f = (M_sdl * y_ps) / I_comp
        # where y_ps = distance from composite NA to steel. But we don't have that.
        # We'll approximate fcdp = (M_sdl * e_net) / I_comp (small error)
        fcdp = (M_sdl * 1000.0 * e_net) / I_comp if I_comp > 0 else 0.0
    else:
        fcdp = 0.0
    
    CR = loss_creep(fcgp, fcdp, Eps, Ec, Kcr=2.0)
    
    # Shrinkage
    SH = loss_shrinkage(Eps, RH, V_S)
    
    # Relaxation: need sum of other losses for iteration, but standard approach uses SH+CR+ES
    sum_other = ES + CR + SH
    relax_func = loss_relaxation(ss["fpi"], ss["fpy"], ss["fpu"], ss["ps_type"])
    RE = relax_func(sum_other)
    
    total_loss_MPa = ES + CR + SH + RE
    fpi = ss["fpi"]
    total_loss_pct = (total_loss_MPa / fpi) * 100.0 if fpi > 0 else 0.0
    fse = fpi - total_loss_MPa   # effective prestress (MPa)
    Pe = fse * Aps_total / 1000.0  # kN (effective force)
    # Per layer forces:
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
