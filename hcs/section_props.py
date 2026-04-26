"""
HCS Design — Section Properties (Phase 2)
==========================================
Reference : ACI/PCI CODE-319-25 Cl. 26.12
            PCI Design Handbook, 8th Edition Sec. 2.2 & 4.2.3
Units     : SI only (mm, mm², mm³, mm⁴)

Functions
---------
calc_section_properties : Gross / Net HCS / Composite section properties

Coordinate System
-----------------
y measured upward from the BOTTOM face of HCS (excluding topping).

Simplification (per PCI practice, >97% accuracy)
-------------------------------------------------
Section modelled as rectangular b_top × h.
Voids subtracted at centroid y_void_c = tf_bot + h_core/2.
Transformed steel uses (n−1)·Aps method.
"""

import math


def calc_section_properties(
        # Geometry
        b_top: float, b_bottom: float, h: float,
        tf_top: float, tf_bot: float,
        hcs_type: str,
        # Voids
        core_shape: str, d_core: float, n_core: int,
        h_straight: float, h_taper: float,
        A_core_1: float, A_voids_total: float, h_core: float,
        # Topping
        has_topping: bool, t_topping: float, b_nominal: float,
        n_mod: float,
        # Prestress
        Aps_bot: float, Aps_top: float,
        dp_bot: float, dp_top: float,
        n_ps: float,          # modular ratio Eps / Ec_hcs
) -> dict:
    """
    Calculate HCS section properties for three conditions:

    1. Gross HCS section   — rectangular b_top × h, no voids, no steel
       Ref: ACI/PCI 319-25 Cl. 26.12.1

    2. Net HCS section     — voids subtracted + transformed prestress steel
       Step A: A_net_conc = b_top×h − A_voids_total
               y_void_c   = tf_bot + h_core/2   (void zone centroid)
       Step B: Add (n_ps−1)·Aps at dp_bot / dp_top via parallel-axis
               (n−1 method: concrete at steel location already in gross)
       Step C: Moments of inertia via parallel-axis theorem
       Ref: PCI Design Handbook 8th Ed. Sec. 2.2.1

    3. Composite section   — net HCS + transformed topping
       Topping CG above HCS top: y_top_c = h + t_topping/2
       Transformed width: b_top_tr = b_nominal / n_mod
       Ref: PCI Design Handbook 8th Ed. Sec. 4.2.3

    Parameters
    ----------
    All lengths in mm, areas in mm², modular ratios dimensionless.

    Returns
    -------
    dict — see keys listed in return statement below.
    """
    # ─────────────────────────────────────────────────────────────────────────
    # 1. GROSS SECTION (rectangular b_top × h, ignore voids & steel)
    #    Ref: ACI/PCI 319-25 Cl. 26.12.1
    # ─────────────────────────────────────────────────────────────────────────
    A_gross   = b_top * h                              # mm²
    yb_gross  = h / 2.0                                # mm — CG from bottom
    yt_gross  = h - yb_gross                           # mm — CG from top
    I_gross   = b_top * h ** 3 / 12.0                 # mm⁴
    Sb_gross  = I_gross / yb_gross                     # mm³ — section modulus bottom
    St_gross  = I_gross / yt_gross                     # mm³ — section modulus top

    # ─────────────────────────────────────────────────────────────────────────
    # 2. NET HCS SECTION (subtract voids, add transformed steel)
    #    Ref: PCI Design Handbook 8th Ed. Sec. 2.2.1
    # ─────────────────────────────────────────────────────────────────────────

    # Void centroid (from bottom of HCS)
    y_void_c = tf_bot + h_core / 2.0                  # mm

    # Concrete-only net area and centroid
    A_net_conc  = b_top * h - A_voids_total            # mm²
    yb_net_conc = (b_top * h * (h / 2.0) - A_voids_total * y_void_c) / A_net_conc  # mm

    # Transformed steel additions (n-1)*Aps — parallel axis
    dA_bot = (n_ps - 1.0) * Aps_bot                   # mm²
    dA_top = (n_ps - 1.0) * Aps_top                   # mm²

    A_net = A_net_conc + dA_bot + dA_top               # mm²
    yb_net = (A_net_conc * yb_net_conc
              + dA_bot   * dp_bot
              + dA_top   * dp_top) / A_net             # mm from bottom
    yt_net = h - yb_net                                # mm from top

    # Moment of inertia — net section
    I_rect  = b_top * h ** 3 / 12.0
    d_rect  = (h / 2.0) - yb_net
    I_hcs_shifted = I_rect + b_top * h * d_rect ** 2

    # Subtract voids (parallel-axis theorem for each void shape)
    if core_shape == "Circular":
        I_void_own = math.pi / 64.0 * d_core ** 4
    elif core_shape == "Capsule":
        I_circ  = math.pi / 64.0 * d_core ** 4
        I_rect_ = d_core * h_straight ** 3 / 12.0
        I_void_own = I_circ + I_rect_
    else:  # Teardrop — semicircle top + triangle
        I_circ = math.pi / 128.0 * d_core ** 4        # semicircle about own NA
        I_tri  = d_core * h_taper ** 3 / 36.0
        I_void_own = I_circ + I_tri

    d_void = y_void_c - yb_net                        # distance void CG to section NA
    I_voids_total = n_core * (I_void_own + A_core_1 * d_void ** 2)

    # Steel contribution to I
    I_steel_bot = (n_ps - 1.0) * Aps_bot * (dp_bot - yb_net) ** 2
    I_steel_top = (n_ps - 1.0) * Aps_top * (dp_top - yb_net) ** 2

    I_net  = I_hcs_shifted - I_voids_total + I_steel_bot + I_steel_top
    Sb_net = I_net / yb_net                            # mm³
    St_net = I_net / yt_net                            # mm³
    r2_net = I_net / A_net                             # radius of gyration squared (mm²)
    e_bot  = dp_bot - yb_net                           # eccentricity bottom tendons (mm)
    e_top  = dp_top - yb_net if Aps_top > 0 else 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # 3. COMPOSITE SECTION (net HCS + transformed topping)
    #    Topping CG above HCS top → y_top_c = h + t_topping/2 from HCS bottom
    #    Transformed topping width = b_nominal / n_mod
    #    Ref: PCI Design Handbook 8th Ed. Sec. 4.2.3
    # ─────────────────────────────────────────────────────────────────────────
    if has_topping and t_topping > 0:
        b_top_tr   = b_nominal / n_mod                 # transformed topping width (mm)
        A_top_tr   = b_top_tr * t_topping              # mm²
        y_top_c    = h + t_topping / 2.0               # mm from bottom of HCS

        A_comp     = A_net + A_top_tr                  # mm²
        yb_comp    = (A_net * yb_net + A_top_tr * y_top_c) / A_comp   # mm from bottom HCS
        yt_comp    = h + t_topping - yb_comp           # mm from top of topping to NA

        # I composite — parallel-axis
        d_net_comp = yb_net - yb_comp
        d_top_comp = y_top_c - yb_comp
        I_top_own  = b_top_tr * t_topping ** 3 / 12.0
        I_comp     = (I_net + A_net * d_net_comp ** 2
                      + I_top_own + A_top_tr * d_top_comp ** 2)

        Sbc_comp   = I_comp / yb_comp                  # mm³ — bottom HCS
        Stc_comp   = I_comp / yt_comp                  # mm³ — top of topping
        yt_hcs_comp = h - yb_comp                      # +ve means NA is below HCS top
        Stc_hcs    = I_comp / abs(yt_hcs_comp) if abs(yt_hcs_comp) > 1e-3 else 0.0

        h_total    = h + t_topping                     # mm
    else:
        # No topping — composite = net section
        A_comp     = A_net
        yb_comp    = yb_net
        yt_comp    = yt_net
        I_comp     = I_net
        Sbc_comp   = Sb_net
        Stc_comp   = St_net
        Stc_hcs    = St_net
        h_total    = h
        A_top_tr   = 0.0
        b_top_tr   = 0.0

    return {
        # Gross
        "A_gross"   : A_gross,
        "yb_gross"  : yb_gross,
        "yt_gross"  : yt_gross,
        "I_gross"   : I_gross,
        "Sb_gross"  : Sb_gross,
        "St_gross"  : St_gross,
        # Net HCS
        "A_net"     : A_net,
        "yb_net"    : yb_net,
        "yt_net"    : yt_net,
        "I_net"     : I_net,
        "Sb_net"    : Sb_net,
        "St_net"    : St_net,
        "r2_net"    : r2_net,
        "e_bot"     : e_bot,
        "e_top"     : e_top,
        "y_void_c"  : y_void_c,
        # Composite
        "A_comp"    : A_comp,
        "yb_comp"   : yb_comp,
        "yt_comp"   : yt_comp,
        "I_comp"    : I_comp,
        "Sbc_comp"  : Sbc_comp,
        "Stc_comp"  : Stc_comp,
        "Stc_hcs"   : Stc_hcs,
        "h_total"   : h_total,
        # Helpers
        "A_net_conc": A_net_conc,
        "A_top_tr"  : A_top_tr,
        "b_top_tr"  : b_top_tr,
    }
