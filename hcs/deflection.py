"""
HCS Design — Deflection & Camber (Phase 6)
============================================
Reference : ACI/PCI CODE-319-25 Cl. 24.2
            PCI Design Handbook, 8th Edition Sec. 4.8 & Table 4.8.3
Units     : SI only (mm, kN, MPa)
"""

import math


def camber_prestress(Pe, e, L, Ec, I):
    """
    Upward camber due to prestress at transfer (mm).
    For straight tendons (HCS):
    delta_ps = Pe * e * L^2 / (8 * Ec * I)
    Pe : effective prestress force (kN)
    e  : eccentricity (mm)
    L  : span (mm)
    Ec : concrete modulus (MPa)
    I  : moment of inertia (mm^4)
    Returns positive upward camber (mm).
    """
    Pe_N = Pe * 1000   # N
    delta = Pe_N * e * L * L / (8 * Ec * I)
    return delta   # mm, upward (+)


def deflection_selfweight(w_sw, L, Ec, I):
    """
    Downward deflection due to self-weight (mm).
    w_sw : self weight per unit length (kN/mm)
    L    : span (mm)
    Ec   : concrete modulus (MPa)
    I    : moment of inertia (mm^4)
    """
    w_Nmm = w_sw * 1000   # N/mm
    delta = (5 * w_Nmm * L**4) / (384 * Ec * I)
    return -delta   # negative = downward


def deflection_uniform_load(w, L, Ec, I):
    """
    Deflection due to uniform load (kN/mm) over full span (mm).
    Returns deflection in mm (negative downward).
    """
    w_Nmm = w * 1000
    delta = (5 * w_Nmm * L**4) / (384 * Ec * I)
    return -delta


def deflection_point_load(P, a, L, Ec, I):
    """
    Deflection at center due to point load P (kN) at distance a from left support.
    P : point load (kN)
    a : distance from left support (mm)
    L : span (mm)
    Returns deflection at center (mm). If load is at midspan, a = L/2.
    Simplified for max deflection location.
    """
    if P == 0:
        return 0.0
    P_N = P * 1000
    # For maximum deflection, use formula for load at location a
    # For simplicity, compute at midspan (conservative)
    # More accurate: compute at load location, but for envelope use midspan approx.
    # Use standard formula: delta = P*a*(3*L^2 - 4*a^2)/(48*E*I) for a<=L/2
    a = min(a, L - a)
    delta = P_N * a * (3*L*L - 4*a*a) / (48 * Ec * I)
    return -delta   # downward negative


def deflection_total(initial_camber, sw_deflection, sdl_deflection, ll_deflection, multipliers):
    """
    Combine deflections with long-term multipliers per PCI Table 4.8.3.
    multipliers dict: {'camber':1.85, 'sw':1.85, 'sdl':3.0, 'll':1.0}
    Returns dict with final values.
    """
    final_camber = initial_camber * multipliers.get('camber', 1.85)
    final_sw = sw_deflection * multipliers.get('sw', 1.85)
    final_sdl = sdl_deflection * multipliers.get('sdl', 3.0)
    final_ll = ll_deflection * multipliers.get('ll', 1.0)
    net_deflection = final_camber + final_sw + final_sdl + final_ll
    return {
        'final_camber': final_camber,
        'final_sw': final_sw,
        'final_sdl': final_sdl,
        'final_ll': final_ll,
        'net_deflection': net_deflection,
    }


def get_long_term_multipliers(has_topping, time_erection=30, time_final=365):
    """
    PCI Design Handbook Table 4.8.3 (for normal weight concrete).
    Returns multipliers dictionary for erection and final stages.
    Without topping: higher multipliers.
    With topping: reduced (topping added later).
    """
    if has_topping:
        # Topping placed after initial camber & self-weight deflection
        # Typical values from PCI Handbook
        multipliers = {
            'camber': 1.45,   # at erection
            'sw': 1.45,
            'sdl': 2.0,       # long-term for superimposed dead after topping
            'll': 1.0,
            'final_camber': 2.0,
            'final_sw': 2.0,
            'final_sdl': 2.5,
        }
    else:
        # Untopped
        multipliers = {
            'camber': 1.85,
            'sw': 1.85,
            'sdl': 3.0,
            'll': 1.0,
            'final_camber': 2.7,
            'final_sw': 2.4,
            'final_sdl': 3.0,
        }
    return multipliers


def check_deflection_limits(net_deflection, span_mm):
    """
    Check ACI 318-19 Table 24.2.2 deflection limits.
    Returns dict with status for LL and total deflection.
    """
    L = span_mm
    limit_ll = L / 360   # live load only
    limit_total = L / 240  # total deflection affecting non-structural elements
    ok_ll = abs(net_deflection) <= limit_ll
    ok_total = abs(net_deflection) <= limit_total
    return {
        'limit_ll_mm': limit_ll,
        'limit_total_mm': limit_total,
        'deflection_mm': net_deflection,
        'status_ll': 'OK' if ok_ll else 'NG',
        'status_total': 'OK' if ok_total else 'NG',
    }


def get_deflection_results(ss):
    """
    Master function. Reads session_state and returns dict with prefix 'def_'.
    """
    # Extract inputs
    L = ss["L_an"]                     # mm
    Pe = ss.get("pl_Pe", ss["Pi"])    # kN (effective force after losses)
    e = ss.get("sp_e_net", 0.0)       # mm (eccentricity)
    Ec = ss.get("Ec_hcs", 33000.0)    # MPa (modulus at 28 days)
    I_net = ss.get("sp_In", 1e12)     # mm^4 (non-composite)
    I_comp = ss.get("sp_I_comp", I_net) # mm^4 (composite, if topping exists)
    has_topping = ss.get("has_topping", False)
    # Loads (line loads in kN/mm)
    b = ss["b_bottom"]
    w_sw = ss["SW_HCS"] * b / 1e6          # kN/mm
    w_topping = ss.get("SW_topping", 0.0) * b / 1e6 if has_topping else 0.0
    w_sdl = ss["SDL"] * b / 1e6            # kN/mm
    w_ll = ss["LL"] * b / 1e6              # kN/mm

    # Point loads (if any) - simplified: use max moment location, but for deflection we use midspan approx.
    # We'll handle point loads in a simplified way: add deflection at midspan due to each point load.
    P1 = (ss.get("P1_DL", 0) + ss.get("P1_LL", 0)) if ss.get("has_point_load", False) else 0
    P2 = (ss.get("P2_DL", 0) + ss.get("P2_LL", 0)) if ss.get("has_point_load", False) else 0
    x1 = ss.get("x_P1", L/2)
    x2 = ss.get("x_P2", L/2)

    # Prestress camber (initial, at transfer)
    delta_ps_initial = camber_prestress(Pe, e, L, Ec, I_net)   # positive upward

    # Self-weight deflection (downward)
    delta_sw = deflection_selfweight(w_sw, L, Ec, I_net)       # negative

    # Deflection due to topping (applied after initial, on non-composite)
    delta_topping = deflection_uniform_load(w_topping, L, Ec, I_net) if has_topping else 0.0

    # Superimposed dead load deflection (on composite section)
    delta_sdl = deflection_uniform_load(w_sdl, L, Ec, I_comp)   # negative

    # Live load deflection (on composite section)
    delta_ll = deflection_uniform_load(w_ll, L, Ec, I_comp)     # negative

    # Point load contributions (simplified: add to live load deflection)
    if P1 > 0:
        delta_ll += deflection_point_load(P1, x1, L, Ec, I_comp)
    if P2 > 0:
        delta_ll += deflection_point_load(P2, x2, L, Ec, I_comp)

    # Short-term net at release: camber + self-weight (topping not yet applied)
    net_release = delta_ps_initial + delta_sw

    # Long-term multipliers (PCI Handbook)
    mult = get_long_term_multipliers(has_topping)
    # For erection: camber and self-weight multiplied by erection factor (before topping)
    # But if topping exists, erection may occur after topping? Assume topping placed before erection? 
    # Simplified: use final multipliers for service stage.
    final_camber = delta_ps_initial * mult.get('final_camber', 2.0)
    final_sw = delta_sw * mult.get('final_sw', 2.0)
    final_sdl = delta_sdl * mult.get('final_sdl', 2.5)
    final_ll = delta_ll   # live load not multiplied for long-term (transient)

    total_deflection = final_camber + final_sw + final_sdl + final_ll

    # Check limits
    limit_check = check_deflection_limits(total_deflection, L)

    return {
        'def_delta_ps_initial': delta_ps_initial,
        'def_delta_sw': delta_sw,
        'def_delta_topping': delta_topping,
        'def_delta_sdl': delta_sdl,
        'def_delta_ll': delta_ll,
        'def_net_release': net_release,
        'def_total_longterm': total_deflection,
        'def_limit_ll_mm': limit_check['limit_ll_mm'],
        'def_limit_total_mm': limit_check['limit_total_mm'],
        'def_status_ll': limit_check['status_ll'],
        'def_status_total': limit_check['status_total'],
    }
