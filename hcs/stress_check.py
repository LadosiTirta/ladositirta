"""
HCS Design — Stress Checks (Phase 4)
=====================================
Reference : ACI/PCI CODE-319-25 Cl. 24.5 & Table 24.5.3.1
            PCI Design Handbook, 8th Edition Sec. 4.2 & 5.3
Units     : SI only (mm, kN, MPa)

Functions:
- stress_at_transfer: stresses at release (top & bottom)
- stress_at_lifting: stresses just after lifting (using Pe_initial)
- stress_at_construction: stresses during topping placement (non-composite)
- stress_at_service: stresses under service loads (composite)
- get_all_stress_checks: master function
"""

import math


# Stress limits per ACI/PCI 319-25 Table 24.5.3.1 (SI units)
LIMIT_COMP_TRANSFER = 0.60      # × f_ci
LIMIT_TENS_TRANSFER = 0.25      # × sqrt(f_ci) in MPa

LIMIT_COMP_SUSTAINED = 0.45     # × f_c
LIMIT_COMP_TOTAL     = 0.60     # × f_c
LIMIT_TENS_CLASS_U   = 0.0      # uncracked (no tension)
LIMIT_TENS_CLASS_T   = 0.50     # × sqrt(f_c) MPa (transition)
LIMIT_TENS_CLASS_C   = 1.00     # × sqrt(f_c) MPa (cracked)


def stress_at_transfer(Pi, e_net, An, In, yb, h, Mg_sw, f_ci):
    """
    Stresses at transfer (release) at top and bottom fiber.
    Sign: compression negative, tension positive.
    Returns dict with f_top, f_bot, limit_comp, limit_tens, status.
    """
    # Pi in kN → N
    Pi_N = Pi * 1000
    yt = h - yb   # distance from CG to top fiber

    # Stresses: f = -P/A ± P*e*y/I - M*y/I
    f_bot = -Pi_N/An + Pi_N * e_net * yb / In - Mg_sw * 1000 * yb / In   # MPa (N/mm²)
    f_top = -Pi_N/An - Pi_N * e_net * yt / In + Mg_sw * 1000 * yt / In

    # Limits
    comp_limit = LIMIT_COMP_TRANSFER * f_ci
    tens_limit = LIMIT_TENS_TRANSFER * math.sqrt(f_ci)  # positive

    # Check status: compression OK if |stress| ≤ comp_limit; tension OK if stress ≤ tens_limit
    # For bottom fiber (compression):
    ok_bot_comp = (-f_bot <= comp_limit) if f_bot < 0 else True
    ok_bot_tens = (f_bot <= tens_limit) if f_bot > 0 else True
    ok_top_comp = (-f_top <= comp_limit) if f_top < 0 else True
    ok_top_tens = (f_top <= tens_limit) if f_top > 0 else True
    status = "OK" if (ok_bot_comp and ok_bot_tens and ok_top_comp and ok_top_tens) else "NG"

    return {
        "f_top": f_top,
        "f_bot": f_bot,
        "limit_comp": comp_limit,
        "limit_tens": tens_limit,
        "status": status,
    }


def stress_at_lifting(Pe, e_net, An, In, yb, h, Mg_sw, f_ci):
    """
    Stresses at lifting (immediately after transfer, with initial losses - elastic shortening).
    Typically Pe = Pi - ES_loss (kN). Use same formula as transfer.
    """
    Pe_N = Pe * 1000
    yt = h - yb
    f_bot = -Pe_N/An + Pe_N * e_net * yb / In - Mg_sw * 1000 * yb / In
    f_top = -Pe_N/An - Pe_N * e_net * yt / In + Mg_sw * 1000 * yt / In

    comp_limit = LIMIT_COMP_TRANSFER * f_ci
    tens_limit = LIMIT_TENS_TRANSFER * math.sqrt(f_ci)

    ok_bot_comp = (-f_bot <= comp_limit) if f_bot < 0 else True
    ok_bot_tens = (f_bot <= tens_limit) if f_bot > 0 else True
    ok_top_comp = (-f_top <= comp_limit) if f_top < 0 else True
    ok_top_tens = (f_top <= tens_limit) if f_top > 0 else True
    status = "OK" if (ok_bot_comp and ok_bot_tens and ok_top_comp and ok_top_tens) else "NG"

    return {
        "f_top": f_top,
        "f_bot": f_bot,
        "limit_comp": comp_limit,
        "limit_tens": tens_limit,
        "status": status,
    }


def stress_at_construction(Pe, e_net, An, In, yb, h, Mg_sw, Mg_sdl, Mg_topping, f_c):
    """
    Stresses during construction (topping placed, not yet composite).
    Moments: self-weight (Mg_sw) + topping weight (Mg_topping) + SDL (Mg_sdl) if applied early.
    All moments in kN·mm.
    Use non-composite section (An, In).
    """
    Pe_N = Pe * 1000
    yt = h - yb
    M_total = Mg_sw + Mg_sdl + Mg_topping
    M_total_Nmm = M_total * 1000
    f_bot = -Pe_N/An + Pe_N * e_net * yb / In - M_total_Nmm * yb / In
    f_top = -Pe_N/An - Pe_N * e_net * yt / In + M_total_Nmm * yt / In

    comp_limit = LIMIT_COMP_TOTAL * f_c    # at service, but construction temporary? Use total limit.
    tens_limit = LIMIT_TENS_CLASS_T * math.sqrt(f_c)   # transition class for construction
    # For construction, many codes allow higher tension; but use transition as conservative.
    ok_bot_comp = (-f_bot <= comp_limit) if f_bot < 0 else True
    ok_bot_tens = (f_bot <= tens_limit) if f_bot > 0 else True
    ok_top_comp = (-f_top <= comp_limit) if f_top < 0 else True
    ok_top_tens = (f_top <= tens_limit) if f_top > 0 else True
    status = "OK" if (ok_bot_comp and ok_bot_tens and ok_top_comp and ok_top_tens) else "NG"

    return {
        "f_top": f_top,
        "f_bot": f_bot,
        "limit_comp": comp_limit,
        "limit_tens": tens_limit,
        "status": status,
    }


def stress_at_service(Pe, e_net, An, In, yb, h,
                      sp_comp_dict,  # dict with I_comp, yb_comp, yt_comp, Sb_comp, St_comp
                      M_DL, M_SDL, M_LL, f_c, section_class="T"):
    """
    Service stresses after composite action.
    - M_DL: moment from HCS self-weight (kN·mm) – applied on non-composite section
    - M_SDL: superimposed dead load moment (kN·mm) – applied on composite section
    - M_LL: live load moment (kN·mm) – applied on composite section
    Class: 'U', 'T', or 'C' per ACI 318-19 §24.5.2
    """
    Pe_N = Pe * 1000
    yt = h - yb   # non-composite top fiber distance from CG
    yb_comp = sp_comp_dict["yb_comp"]
    yt_comp = sp_comp_dict["yt_comp"]   # from top of topping to composite NA
    I_comp = sp_comp_dict["I_comp"]
    Sb_comp = sp_comp_dict["Sb_comp"]   # bottom of HCS
    St_comp = sp_comp_dict["St_comp"]   # top of topping

    # Non-composite part (prestress + self-weight)
    # f_bot_non = -P/A - P*e*yb/I + M_DL*yb/I (but careful sign)
    # Actually: f_bot = -P/A - P*e*yb/I + M*yb/I (compression -)
    # For service, we compute final stresses in composite section:
    # Step1: stresses due to prestress and M_DL on non-composite section
    f_bot_nc = -Pe_N/An - Pe_N * e_net * yb / In + M_DL * 1000 * yb / In
    f_top_nc = -Pe_N/An + Pe_N * e_net * yt / In - M_DL * 1000 * yt / In

    # Step2: add stresses from M_SDL and M_LL on composite section (using transformed properties)
    M_super = (M_SDL + M_LL) * 1000   # N·mm
    f_bot_super = M_super * yb_comp / I_comp
    f_top_super = -M_super * yt_comp / I_comp   # tension positive? careful: compression at top

    f_bot = f_bot_nc + f_bot_super
    f_top = f_top_nc + f_top_super

    # Allowable limits based on class
    sqrt_fc = math.sqrt(f_c)
    if section_class.upper() == 'U':
        tens_limit = LIMIT_TENS_CLASS_U * sqrt_fc   # zero
    elif section_class.upper() == 'T':
        tens_limit = LIMIT_TENS_CLASS_T * sqrt_fc
    else:  # 'C'
        tens_limit = LIMIT_TENS_CLASS_C * sqrt_fc

    comp_limit = LIMIT_COMP_TOTAL * f_c

    # Ensure compression stress magnitude check (negative stress is compression)
    ok_bot_comp = (-f_bot <= comp_limit) if f_bot < 0 else True
    ok_bot_tens = (f_bot <= tens_limit) if f_bot > 0 else True
    ok_top_comp = (-f_top <= comp_limit) if f_top < 0 else True
    ok_top_tens = (f_top <= tens_limit) if f_top > 0 else True
    status = "OK" if (ok_bot_comp and ok_bot_tens and ok_top_comp and ok_top_tens) else "NG"

    return {
        "f_bot": f_bot,
        "f_top": f_top,
        "limit_comp": comp_limit,
        "limit_tens": tens_limit,
        "status": status,
    }


def get_all_stress_checks(ss):
    """
    Master function. Reads session_state and returns dict with all stress results.
    Keys: sc_transfer, sc_lifting, sc_construction, sc_service
    Each is a dict containing f_top, f_bot, limit_comp, limit_tens, status.
    Also sc_service_class (the class used).
    """
    # Extract needed values
    Pi = ss["Pi"]                  # kN initial
    Pe = ss.get("pl_Pe", Pi)       # effective after losses (kN)
    e_net = ss.get("sp_e_net", 0.0)
    An = ss["sp_An"]
    In = ss["sp_In"]
    yb = ss["sp_yb"]
    h = ss["h"]
    f_ci = ss["f_ci"]
    f_c = ss["f_c"]

    # Moments (kN·mm) – from load diagrams (max midspan)
    L = ss["L_an"]
    w_sw = ss["SW_HCS"] * ss["b_bottom"] / 1e6  # kN/mm
    Mg_sw = w_sw * L * L / 8.0   # kN·mm
    w_topping = ss.get("SW_topping", 0.0) * ss["b_bottom"] / 1e6
    Mg_top = w_topping * L * L / 8.0 if ss.get("has_topping") else 0.0
    w_sdl = ss["SDL"] * ss["b_bottom"] / 1e6
    M_sdl = w_sdl * L * L / 8.0
    w_ll = ss["LL"] * ss["b_bottom"] / 1e6
    M_ll = w_ll * L * L / 8.0

    # Transfer stress
    transfer = stress_at_transfer(Pi, e_net, An, In, yb, h, Mg_sw, f_ci)

    # Lifting stress (after elastic shortening only, but use Pe as approximation)
    lifting = stress_at_lifting(Pe, e_net, An, In, yb, h, Mg_sw, f_ci)

    # Construction stress (topping + SDL on non-composite)
    # For simplicity, assume topping and SDL applied before composite action
    construction = stress_at_construction(Pe, e_net, An, In, yb, h, Mg_sw, M_sdl, Mg_top, f_c)

    # Service stress (composite)
    # Build composite dict from session_state keys
    comp_dict = {
        "I_comp": ss.get("sp_I_comp", In),
        "yb_comp": ss.get("sp_yb_comp", yb),
        "yt_comp": ss.get("sp_yt_comp", h + ss.get("t_topping", 0) - yb),
        "Sb_comp": ss.get("sp_Sb_comp", 0.0),
        "St_comp": ss.get("sp_St_comp", 0.0),
    }
    section_class = "T"   # default Transition class (cracked but limited tension)
    service = stress_at_service(Pe, e_net, An, In, yb, h, comp_dict,
                                Mg_sw, M_sdl, M_ll, f_c, section_class)

    return {
        "sc_transfer": transfer,
        "sc_lifting": lifting,
        "sc_construction": construction,
        "sc_service": service,
        "sc_service_class": section_class,
    }
