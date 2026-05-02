"""
HCS Design — Deflection & Camber (Phase 6)
============================================
Reference : ACI/PCI CODE-319-25 Cl. 24.2
            PCI Design Handbook, 8th Edition Sec. 4.8 & Table 4.8.3
            AISC Design Guide 11 (Vibration of Steel-Framed Structural Systems)
            ISO 10137:2007 (Bases for design of structures — Serviceability)
Units     : SI only (mm, kN, MPa)

CHANGE LOG (FIX-4)
------------------
- get_deflection_results(): now reads user-editable PCI multipliers from ss
  (mult_camber_final, mult_dw_final, mult_sdl_final, mult_ll_final)
- get_deflection_results(): now reads custom limit fractions
  (limit_LL_fraction, limit_total_fraction)
- New function: calc_thermal_camber()  — temperature differential
- New function: calc_vibration()       — natural frequency + acceleration check
- All existing return keys preserved exactly
- New return keys added with prefix 'def_vib_' and 'def_therm_'
"""

import math


# =============================================================================
# ELASTIC DEFLECTION FORMULAS  (unchanged from original)
# =============================================================================

def camber_prestress(Pe, e, L, Ec, I):
    """
    Upward camber due to prestress at transfer (mm).
    Straight tendon (HCS): delta_ps = Pe * e * L^2 / (8 * Ec * I)
    Pe [kN], e [mm], L [mm], Ec [MPa], I [mm^4]
    Returns positive upward camber (mm).
    """
    Pe_N = Pe * 1000   # N
    if Ec <= 0 or I <= 0:
        return 0.0
    delta = Pe_N * e * L * L / (8.0 * Ec * I)
    return delta   # mm, upward (+)


def deflection_selfweight(w_sw, L, Ec, I):
    """
    Downward deflection due to self-weight.
    w_sw [kN/mm], L [mm], Ec [MPa], I [mm^4]
    Returns negative (downward) deflection in mm.
    """
    w_Nmm = w_sw * 1000   # N/mm
    if Ec <= 0 or I <= 0:
        return 0.0
    delta = (5.0 * w_Nmm * L**4) / (384.0 * Ec * I)
    return -delta


def deflection_uniform_load(w, L, Ec, I):
    """
    Deflection due to uniform load (kN/mm) over full span.
    Returns negative (downward) deflection in mm.
    """
    w_Nmm = w * 1000
    if Ec <= 0 or I <= 0:
        return 0.0
    delta = (5.0 * w_Nmm * L**4) / (384.0 * Ec * I)
    return -delta


def deflection_point_load(P, a, L, Ec, I):
    """
    Midspan deflection due to point load P (kN) at distance a from left support.
    Uses standard formula: delta = P*a*(3L^2 - 4a^2) / (48*E*I) for a <= L/2
    Returns negative (downward) in mm.
    """
    if P == 0 or Ec <= 0 or I <= 0:
        return 0.0
    P_N = P * 1000
    a = min(a, L - a)
    delta = P_N * a * (3.0 * L * L - 4.0 * a * a) / (48.0 * Ec * I)
    return -delta


def deflection_total(initial_camber, sw_deflection, sdl_deflection,
                     ll_deflection, multipliers):
    """
    Combine deflections with long-term multipliers per PCI Table 4.8.3.
    multipliers dict: {'camber':1.85, 'sw':1.85, 'sdl':3.0, 'll':1.0}
    """
    final_camber = initial_camber    * multipliers.get('camber', 1.85)
    final_sw     = sw_deflection     * multipliers.get('sw',     1.85)
    final_sdl    = sdl_deflection    * multipliers.get('sdl',    3.0)
    final_ll     = ll_deflection     * multipliers.get('ll',     1.0)
    net_deflection = final_camber + final_sw + final_sdl + final_ll
    return {
        'final_camber':    final_camber,
        'final_sw':        final_sw,
        'final_sdl':       final_sdl,
        'final_ll':        final_ll,
        'net_deflection':  net_deflection,
    }


# =============================================================================
# PCI MULTIPLIERS  (FIX-4: now accepts user overrides from session_state)
# =============================================================================

def get_pci_multiplier_defaults(has_topping: bool) -> dict:
    """
    PCI Design Handbook 8th Ed. Table 4.8.3 default multipliers.
    Returns a dict of defaults that the UI can display and let the user edit.
    Keys match session_state variable names used in get_deflection_results().
    """
    if has_topping:
        return {
            "mult_camber_erection": 1.85,
            "mult_dw_erection":     1.85,
            "mult_camber_final":    2.40,
            "mult_dw_final":        2.30,
            "mult_sdl_final":       3.00,
            "mult_ll_final":        1.00,
        }
    else:
        return {
            "mult_camber_erection": 1.85,
            "mult_dw_erection":     1.85,
            "mult_camber_final":    2.70,
            "mult_dw_final":        2.40,
            "mult_sdl_final":       3.00,
            "mult_ll_final":        1.00,
        }


def get_long_term_multipliers(has_topping, ss=None):
    """
    Return multiplier dict for use in deflection calculation.
    If ss is provided, reads user-editable values from session_state.
    Falls back to PCI defaults if keys not present.
    """
    defaults = get_pci_multiplier_defaults(has_topping)

    if ss is not None:
        return {
            'camber':       ss.get("mult_camber_erection", defaults["mult_camber_erection"]),
            'sw':           ss.get("mult_dw_erection",     defaults["mult_dw_erection"]),
            'final_camber': ss.get("mult_camber_final",    defaults["mult_camber_final"]),
            'final_sw':     ss.get("mult_dw_final",        defaults["mult_dw_final"]),
            'sdl':          ss.get("mult_sdl_final",       defaults["mult_sdl_final"]),
            'final_sdl':    ss.get("mult_sdl_final",       defaults["mult_sdl_final"]),
            'll':           ss.get("mult_ll_final",        defaults["mult_ll_final"]),
        }

    # Legacy path — no ss provided (backward compat)
    if has_topping:
        return {
            'camber': 1.45, 'sw': 1.45, 'sdl': 2.0, 'll': 1.0,
            'final_camber': 2.0, 'final_sw': 2.0, 'final_sdl': 2.5,
        }
    else:
        return {
            'camber': 1.85, 'sw': 1.85, 'sdl': 3.0, 'll': 1.0,
            'final_camber': 2.7, 'final_sw': 2.4, 'final_sdl': 3.0,
        }


# =============================================================================
# DEFLECTION LIMITS  (FIX-4: custom fractions)
# =============================================================================

def check_deflection_limits(net_deflection, span_mm,
                             limit_ll_fraction=360,
                             limit_total_fraction=240):
    """
    Check deflection limits.
    limit_ll_fraction    : denominator for LL limit    (default L/360)
    limit_total_fraction : denominator for total limit (default L/240)
    """
    L = span_mm
    limit_ll    = L / max(limit_ll_fraction,    1)
    limit_total = L / max(limit_total_fraction, 1)
    ok_ll    = abs(net_deflection) <= limit_ll
    ok_total = abs(net_deflection) <= limit_total
    return {
        'limit_ll_mm':    limit_ll,
        'limit_total_mm': limit_total,
        'deflection_mm':  net_deflection,
        'status_ll':      'OK' if ok_ll    else 'NG',
        'status_total':   'OK' if ok_total else 'NG',
    }


# =============================================================================
# FIX-4 ADDITION 2 — Thermal camber
# =============================================================================

def calc_thermal_camber(alpha_T, delta_T, L_an, h):
    """
    Upward camber due to temperature differential (simply-supported beam).

    delta_thermal = alpha_T * delta_T * L^2 / (8 * h)

    Parameters
    ----------
    alpha_T  : Thermal expansion coefficient [/°C]. Normal concrete: 10e-6.
    delta_T  : Temperature differential top-to-bottom [°C].
               Positive = top warmer = hogging = upward camber.
    L_an     : Analysis span [mm].
    h        : Total HCS thickness [mm].

    Returns
    -------
    delta_thermal [mm]. Positive = upward.

    Reference: Timoshenko & Goodier, Theory of Elasticity.
    For simply-supported beam: delta = alpha_T * delta_T * L^2 / (8 * h)
    """
    if h <= 0:
        return 0.0
    return alpha_T * delta_T * L_an**2 / (8.0 * h)


# =============================================================================
# FIX-4 ADDITION 4 — Natural frequency & vibration check
# =============================================================================

def calc_vibration(SW_HCS, SW_topping, SDL, LL,
                   b_bottom, L_an, Ec_hcs, I_comp,
                   damping_ratio=3.0,
                   vibration_mode="Walking / Occupancy"):
    """
    Fundamental natural frequency and peak acceleration ratio for HCS floor.

    Natural Frequency (simply-supported beam):
    ------------------------------------------
    f_n = (pi^2 / (2 * L^2)) * sqrt(EI / m_per_length)

    where:
        m_per_length = total mass per unit length [kg/mm]
                     = (SW_HCS + SW_topping + SDL + 0.1*LL) * b_bottom [kN/m²→N/mm / g]
        EI           = Ec_hcs [MPa] * I_comp [mm^4]  = N.mm^2

    Peak Acceleration (AISC DG11 simplified):
    -----------------------------------------
    a/g = P0 * exp(-2*pi*beta) / W_eff

    where:
        P0    = 0.29 kN (walking excitation force, AISC DG11 Table 4.2)
        beta  = damping ratio (fraction, not %)
        W_eff = effective panel weight [kN]

    Parameters
    ----------
    SW_HCS, SW_topping, SDL, LL : area loads [kN/m²]
    b_bottom  : panel width [mm]
    L_an      : analysis span [mm]
    Ec_hcs    : concrete modulus at 28 days [MPa = N/mm²]
    I_comp    : composite moment of inertia [mm^4]
    damping_ratio : percentage (e.g. 3.0 for 3%)
    vibration_mode: "Walking / Occupancy", "Machine / Equipment",
                    "Sensitive (Lab/Hospital)"

    Returns
    -------
    dict with vibration results
    """
    # Limits per AISC Design Guide 11 / ISO 10137
    _fn_limits = {
        "Walking / Occupancy":       8.0,   # Hz  AISC DG11 Table 4.1
        "Machine / Equipment":       4.0,   # Hz
        "Sensitive (Lab/Hospital)": 12.0,   # Hz
    }
    _ag_limits = {
        "Walking / Occupancy":      0.005,  # 0.5 % g  AISC DG11
        "Machine / Equipment":      0.015,  # 1.5 % g
        "Sensitive (Lab/Hospital)": 0.004,  # 0.4 % g
    }
    fn_limit = _fn_limits.get(vibration_mode, 8.0)
    ag_limit = _ag_limits.get(vibration_mode, 0.005)

    # Guard against degenerate inputs
    if Ec_hcs <= 0 or I_comp <= 0 or L_an <= 0 or b_bottom <= 0:
        return {
            "vib_fn":        0.0,
            "vib_fn_limit":  fn_limit,
            "vib_fn_ok":     False,
            "vib_ag":        0.0,
            "vib_ag_limit":  ag_limit,
            "vib_ag_ok":     False,
            "vib_mode":      vibration_mode,
            "vib_beta":      damping_ratio,
            "vib_W_eff":     0.0,
            "vib_error":     "Invalid inputs (Ec, I_comp, L_an or b_bottom = 0)",
        }

    # Effective mass per unit length [kg/mm]
    # Use 10% of LL as sustained mass per AISC DG11
    g_mm_s2 = 9810.0   # mm/s^2
    w_total_kNm2 = SW_HCS + SW_topping + SDL + 0.1 * LL   # kN/m²
    # Convert: kN/m² * b_bottom[mm] / 1e6 [mm²→m²] * 1000 [kN→N] / g [mm/s²]
    m_per_mm = (w_total_kNm2 * b_bottom / 1e6 * 1000.0) / g_mm_s2   # kg/mm

    if m_per_mm <= 0:
        m_per_mm = 1e-6   # avoid zero division

    # EI [N.mm²]
    EI = Ec_hcs * I_comp   # MPa * mm^4 = N/mm² * mm^4 = N.mm²

    # Natural frequency [Hz]
    # f_n = (pi^2 / (2*L^2)) * sqrt(EI / m_per_mm)
    # Units check: sqrt(N.mm² / (kg/mm)) = sqrt(N.mm³/kg) = sqrt(kg.mm/s².mm³/kg)
    #            = sqrt(mm²/s²) = mm/s  → need extra sqrt(1/mm²) → divide by L
    # Correct formula for simply-supported beam:
    # omega_n = pi^2 / L^2 * sqrt(EI / m_per_length_SI)
    # m_per_length_SI [kg/m] = m_per_mm * 1000
    m_per_m = m_per_mm * 1000.0   # kg/m
    EI_SI   = EI * 1e-6           # N.m² (from N.mm² / 1e6)
    L_m     = L_an / 1000.0       # m

    fn = (math.pi**2 / (2.0 * L_m**2)) * math.sqrt(EI_SI / m_per_m)   # Hz

    fn_ok = fn >= fn_limit

    # Effective weight for acceleration check [kN]
    # W_eff = effective tributary mass × g
    W_eff_kN = w_total_kNm2 * (b_bottom / 1000.0) * L_m   # kN (area × span)
    if W_eff_kN <= 0:
        W_eff_kN = 1e-3

    # Peak acceleration ratio (AISC DG11 Eq. 4.2)
    P0   = 0.29   # kN — walking excitation force
    beta = damping_ratio / 100.0   # fraction
    ag   = P0 * math.exp(-2.0 * math.pi * beta) / W_eff_kN

    ag_ok = ag <= ag_limit

    return {
        "vib_fn":        fn,
        "vib_fn_limit":  fn_limit,
        "vib_fn_ok":     fn_ok,
        "vib_ag":        ag,
        "vib_ag_limit":  ag_limit,
        "vib_ag_ok":     ag_ok,
        "vib_mode":      vibration_mode,
        "vib_beta":      damping_ratio,
        "vib_W_eff":     W_eff_kN,
        "vib_m_per_m":   m_per_m,
        "vib_EI_SI":     EI_SI,
        "vib_L_m":       L_m,
        "vib_error":     None,
    }


# =============================================================================
# MASTER FUNCTION  (updated for FIX-4)
# =============================================================================

def get_deflection_results(ss):
    """
    Master function. Reads session_state and returns dict with prefix 'def_'.

    FIX-4 additions:
    - Reads user-editable PCI multipliers from ss
    - Reads custom deflection limit fractions
    - Computes thermal camber (if has_thermal in ss)
    - Computes vibration (always)
    - All original keys preserved exactly
    """
    # ── Basic inputs ─────────────────────────────────────────────────────────
    L          = float(ss["L_an"])
    Pe         = float(ss.get("pl_Pe",  ss["Pi"]))
    e          = float(ss.get("sp_e_net",  ss.get("sp_e_bot", 0.0)))
    Ec         = float(ss.get("Ec_hcs",  33000.0))
    I_net      = float(ss.get("sp_In",   1e9))
    has_topping = bool(ss.get("has_topping", False))
    I_comp     = float(ss.get("sp_I_comp", I_net))
    b          = float(ss["b_bottom"])
    h          = float(ss["h"])

    # ── Loads (line loads in kN/mm) ───────────────────────────────────────────
    w_sw      = float(ss["SW_HCS"])      * b / 1e6
    w_topping = float(ss.get("SW_topping", 0.0)) * b / 1e6 if has_topping else 0.0
    w_sdl     = float(ss["SDL"])         * b / 1e6
    w_ll      = float(ss["LL"])          * b / 1e6

    # ── Point loads ───────────────────────────────────────────────────────────
    _has_pl = bool(ss.get("has_point_load", False))
    P1 = float(ss.get("P1_DL", 0) + ss.get("P1_LL", 0)) if _has_pl else 0.0
    P2 = float(ss.get("P2_DL", 0) + ss.get("P2_LL", 0)) if _has_pl else 0.0
    x1 = float(ss.get("x_P1", L / 2))
    x2 = float(ss.get("x_P2", L / 2))

    # ── Instantaneous deflections ─────────────────────────────────────────────
    delta_ps_initial = camber_prestress(Pe, e, L, Ec, I_net)
    delta_sw         = deflection_selfweight(w_sw, L, Ec, I_net)
    delta_topping    = deflection_uniform_load(w_topping, L, Ec, I_net) if has_topping else 0.0
    delta_sdl        = deflection_uniform_load(w_sdl, L, Ec, I_comp)
    delta_ll         = deflection_uniform_load(w_ll,  L, Ec, I_comp)

    if P1 > 0:
        delta_ll += deflection_point_load(P1, x1, L, Ec, I_comp)
    if P2 > 0:
        delta_ll += deflection_point_load(P2, x2, L, Ec, I_comp)

    # ── Net at release ────────────────────────────────────────────────────────
    net_release = delta_ps_initial + delta_sw

    # ── PCI multipliers — FIX-4: read user-editable values from ss ───────────
    mult = get_long_term_multipliers(has_topping, ss=ss)

    final_camber = delta_ps_initial * mult.get("final_camber", 2.0)
    final_sw     = delta_sw         * mult.get("final_sw",     2.0)
    final_sdl    = delta_sdl        * mult.get("final_sdl",    2.5)
    final_ll     = delta_ll   # LL not long-term multiplied (transient)

    total_deflection = final_camber + final_sw + final_sdl + final_ll

    # ── Custom deflection limits — FIX-4 ─────────────────────────────────────
    lim_ll_frac    = float(ss.get("limit_LL_fraction",    360))
    lim_total_frac = float(ss.get("limit_total_fraction", 240))
    limit_check = check_deflection_limits(
        total_deflection, L,
        limit_ll_fraction=lim_ll_frac,
        limit_total_fraction=lim_total_frac
    )

    # ── Thermal camber — FIX-4 Addition 2 ────────────────────────────────────
    _has_therm   = bool(ss.get("has_thermal", False))
    _alpha_T     = float(ss.get("alpha_T", 10e-6))
    _delta_T     = float(ss.get("delta_T",  0.0))
    delta_thermal = (calc_thermal_camber(_alpha_T, _delta_T, L, h)
                     if _has_therm else 0.0)

    # ── Vibration — FIX-4 Addition 4 ─────────────────────────────────────────
    _vib_mode    = ss.get("vibration_mode",  "Walking / Occupancy")
    _damp        = float(ss.get("damping_ratio", 3.0))
    _SW_HCS_vib  = float(ss["SW_HCS"])
    _SW_top_vib  = float(ss.get("SW_topping", 0.0))
    vib = calc_vibration(
        SW_HCS=_SW_HCS_vib, SW_topping=_SW_top_vib,
        SDL=float(ss["SDL"]), LL=float(ss["LL"]),
        b_bottom=b, L_an=L,
        Ec_hcs=Ec, I_comp=I_comp,
        damping_ratio=_damp,
        vibration_mode=_vib_mode,
    )

    # ── Build return dict (all original keys + new keys) ─────────────────────
    result = {
        # ── Original keys (all preserved) ────────────────────────────────────
        "def_delta_ps_initial": delta_ps_initial,
        "def_delta_sw":         delta_sw,
        "def_delta_topping":    delta_topping,
        "def_delta_sdl":        delta_sdl,
        "def_delta_ll":         delta_ll,
        "def_net_release":      net_release,
        "def_total_longterm":   total_deflection,
        "def_limit_ll_mm":      limit_check["limit_ll_mm"],
        "def_limit_total_mm":   limit_check["limit_total_mm"],
        "def_status_ll":        limit_check["status_ll"],
        "def_status_total":     limit_check["status_total"],
        # ── FIX-4 new keys — long-term components (for detail display) ───────
        "def_final_camber":     final_camber,
        "def_final_sw":         final_sw,
        "def_final_sdl":        final_sdl,
        "def_final_ll":         final_ll,
        # ── FIX-4 thermal ────────────────────────────────────────────────────
        "def_delta_thermal":    delta_thermal,
        # ── FIX-4 vibration (prefix def_vib_) ────────────────────────────────
        "def_vib_fn":           vib["vib_fn"],
        "def_vib_fn_limit":     vib["vib_fn_limit"],
        "def_vib_fn_ok":        vib["vib_fn_ok"],
        "def_vib_ag":           vib["vib_ag"],
        "def_vib_ag_limit":     vib["vib_ag_limit"],
        "def_vib_ag_ok":        vib["vib_ag_ok"],
        "def_vib_W_eff":        vib["vib_W_eff"],
        "def_vib_mode":         vib["vib_mode"],
        "def_vib_beta":         vib["vib_beta"],
    }
    return result
