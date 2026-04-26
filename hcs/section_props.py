"""
HCS Design — Section Properties
=================================
Reference : ACI/PCI CODE-319-25 Cl. 26.12
            PCI Design Handbook, 8th Edition Sec. 2.2 & 2.2.3 & 4.2.3
Units     : SI only (mm, mm², mm³, mm⁴)

Coordinate System
-----------------
y measured upward from the BOTTOM face of HCS (excluding topping).

Simplification (per PCI practice, accuracy >97%)
--------------------------------------------------
HCS modelled as rectangular b_top × h.
Voids subtracted at their geometric centroids via the parallel-axis theorem.
Composite topping is transformed to equivalent HCS concrete.

Functions
---------
calc_net_section       : Gross + Net HCS section (no topping, no transformed steel)
calc_composite_section : Composite section (HCS + transformed topping)
calc_ps_eccentricity   : Eccentricity of prestressing force from centroid
get_all_section_props  : Master function — reads session_state dict, returns
                         combined dict ready to store with prefix 'sp_'
"""

import math


# ─────────────────────────────────────────────────────────────────────────────
# Internal helper: moment of inertia of one void about its OWN centroid
# ─────────────────────────────────────────────────────────────────────────────
def _I_void_own(core_shape: str, d_core: float,
                h_straight: float, h_taper: float) -> float:
    """
    Moment of inertia of ONE core void about its own centroidal axis.

    Circular  : I = π·d⁴/64
                Full circle about its own CG.

    Capsule   : I = π·d⁴/64  +  d·h_str³/12
                Circle part (π·d⁴/64) + rectangular mid-segment (d·h_str³/12).
                Both sub-parts share the same void CG for a symmetric layout;
                the parallel-axis shift to the section NA is applied in
                calc_net_section via d_void.

    Teardrop  : I = π·d⁴/128  +  d·h_tap³/36
                Semicircle top (π·d⁴/128 about semicircle's own NA) +
                Triangle taper (bh³/36 for a triangle, b=d, h=h_taper,
                about the triangle's own CG).

    Ref: PCI Design Handbook 8th Ed. Sec. 2.2  |  standard geometric formulas
    """
    if core_shape == "Circular":
        return math.pi / 64.0 * d_core ** 4

    elif core_shape == "Capsule":
        I_circle = math.pi / 64.0 * d_core ** 4
        I_rect   = d_core * h_straight ** 3 / 12.0
        return I_circle + I_rect

    else:  # Teardrop
        I_semicircle = math.pi / 128.0 * d_core ** 4   # semicircle about own NA
        I_triangle   = d_core * h_taper ** 3 / 36.0    # bh³/36
        return I_semicircle + I_triangle


# =============================================================================
# 1. GROSS + NET SECTION
# =============================================================================
def calc_net_section(
        b_top        : float,
        h            : float,
        tf_bot       : float,
        core_shape   : str,
        d_core       : float,
        n_core       : int,
        h_straight   : float,
        h_taper      : float,
        A_core_1     : float,
        A_voids_total: float,
        h_core       : float,
) -> dict:
    """
    Net section properties of HCS alone (no topping, no transformed steel).
    Ref: PCI Design Handbook 8th Ed. Sec. 2.2

    Method: rectangular simplification using b_top
    ------------------------------------------------
    Gross
        Ag   = b_top × h
        yb_g = h / 2   (symmetric rectangle)
        Ig   = b_top × h³ / 12

    Net (subtract voids)
        y_void_c = tf_bot + h_core / 2       (void zone centroid from bottom)
        An  = Ag − A_voids_total
        yb  = (Ag × h/2  −  A_voids_total × y_void_c) / An
              (composite-area method; for perfectly symmetric cores this gives
               yb ≈ h/2, but asymmetric flanges shift it slightly — full formula
               is always used for correctness)

        I_gross_shifted = Ig + Ag × (h/2 − yb)²      about new NA
        I_void_1 = _I_void_own()                       about void's own CG
        d_void   = y_void_c − yb                       parallel-axis distance
        I_voids  = n_core × (I_void_1 + A_core_1 × d_void²)
        In  = I_gross_shifted − I_voids

    Section moduli
        Sb = In / yb          bottom fibre
        St = In / (h − yb)    top fibre

    Kern points  (ACI/PCI 319-25 Cl. 24.5.2 / PCI Handbook Sec. 2.2)
        kb = In / (An × yb)      lower kern from bottom
        kt = In / (An × yt)      upper kern from top

    r² = In / An              radius of gyration squared

    Parameters
    ----------
    b_top, h, tf_bot      : geometry (mm)
    core_shape            : "Circular" | "Capsule" | "Teardrop"
    d_core, h_straight, h_taper : core dimensions (mm)
    n_core                : number of cores
    A_core_1              : area of one core (mm²)
    A_voids_total         : n_core × A_core_1 (mm²)
    h_core                : total height of one core (mm)

    Returns
    -------
    dict — keys: Ag, yb_g, yt_g, Ig, Sb_g, St_g  (gross)
                 An, yb, yt, In, Sb, St, kb, kt, r2 (net)
                 y_void_c                             (helper for Phase 3/4)
    """
    # ── Gross section ──────────────────────────────────────────────────────────
    Ag   = b_top * h
    yb_g = h / 2.0
    yt_g = h - yb_g
    Ig   = b_top * h ** 3 / 12.0
    Sb_g = Ig / yb_g
    St_g = Ig / yt_g

    # ── Void centroid from bottom ──────────────────────────────────────────────
    y_void_c = tf_bot + h_core / 2.0

    # ── Net area and centroid ─────────────────────────────────────────────────
    An  = Ag - A_voids_total
    yb  = (Ag * (h / 2.0) - A_voids_total * y_void_c) / An
    yt  = h - yb

    # ── Net inertia ───────────────────────────────────────────────────────────
    I_gross_shifted = Ig + Ag * (h / 2.0 - yb) ** 2
    I_v1    = _I_void_own(core_shape, d_core, h_straight, h_taper)
    d_void  = y_void_c - yb
    I_voids = n_core * (I_v1 + A_core_1 * d_void ** 2)
    In      = I_gross_shifted - I_voids

    # ── Section moduli ────────────────────────────────────────────────────────
    Sb = In / yb
    St = In / yt

    # ── Kern points ───────────────────────────────────────────────────────────
    kb = In / (An * yb)
    kt = In / (An * yt)

    # ── Radius of gyration squared ────────────────────────────────────────────
    r2 = In / An

    return {
        # Gross
        "Ag"      : Ag,
        "yb_g"    : yb_g,
        "yt_g"    : yt_g,
        "Ig"      : Ig,
        "Sb_g"    : Sb_g,
        "St_g"    : St_g,
        # Net
        "An"      : An,
        "yb"      : yb,
        "yt"      : yt,
        "In"      : In,
        "Sb"      : Sb,
        "St"      : St,
        "kb"      : kb,
        "kt"      : kt,
        "r2"      : r2,
        # Helper
        "y_void_c": y_void_c,
    }


# =============================================================================
# 2. COMPOSITE SECTION  (HCS + topping)
# =============================================================================
def calc_composite_section(
        net_props : dict,
        b_top     : float,
        h         : float,
        t_topping : float,
        n_mod     : float,
        hcs_type  : str,
) -> dict:
    """
    Composite section properties: HCS + structural topping.
    Ref: PCI Design Handbook 8th Ed. Sec. 2.2.3

    Case A — No topping (t_topping = 0)
        All _comp keys mirror the net section values.

    Case B — Half Slab + topping  (hcs_type == "Half Slab (Open Top)")
        Topping fills open cores → solid rectangular composite:
            A_comp  = b_top × (h + t_topping)
            yb_comp = (h + t_topping) / 2
            I_comp  = b_top × (h + t_topping)³ / 12

    Case C — Full HCS + topping
        Transform topping to HCS-concrete equivalent using n_mod = Ec_top/Ec_hcs:
            b_top_tr = b_top × n_mod
            A_top_tr = b_top_tr × t_topping
            y_top_c  = h + t_topping / 2          (topping CG from HCS bottom)

            A_comp   = An + A_top_tr
            yb_comp  = (An×yb + A_top_tr×y_top_c) / A_comp

        Parallel-axis inertia:
            d_net    = yb_comp − yb
            d_top    = y_top_c − yb_comp
            I_top_tr = b_top_tr × t_topping³ / 12
            I_comp   = In + An×d_net² + I_top_tr + A_top_tr×d_top²

        Section moduli (in HCS-concrete stress units):
            Sb_comp   = I_comp / yb_comp
            St_comp   = I_comp / (h + t_top − yb_comp)    top of topping
            St_hcs    = I_comp / |h − yb_comp|             top of HCS (interface)
            St_top_tr = St_comp × n_mod   → stress in topping concrete (Phase 4)

    Parameters
    ----------
    net_props : output dict of calc_net_section()
    b_top     : HCS top flange width (mm)
    h         : HCS total depth (mm)
    t_topping : topping thickness (mm)
    n_mod     : modular ratio Ec_top / Ec_hcs
    hcs_type  : "Full HCS (Hollow Core)" | "Half Slab (Open Top)"

    Returns
    -------
    dict — all net_props keys plus:
        A_comp, yb_comp, yt_comp, I_comp,
        Sb_comp, St_comp, St_hcs, St_top_tr,
        h_total, A_top_tr, b_top_tr
    """
    An = net_props["An"]
    yb = net_props["yb"]
    In = net_props["In"]

    # ── Case A: no topping ────────────────────────────────────────────────────
    if t_topping <= 0:
        comp = dict(net_props)
        comp.update({
            "A_comp"   : An,
            "yb_comp"  : yb,
            "yt_comp"  : net_props["yt"],
            "I_comp"   : In,
            "Sb_comp"  : net_props["Sb"],
            "St_comp"  : net_props["St"],
            "St_hcs"   : net_props["St"],
            "St_top_tr": net_props["St"],
            "h_total"  : h,
            "A_top_tr" : 0.0,
            "b_top_tr" : 0.0,
        })
        return comp

    # ── Case B: Half Slab + topping → fully solid ─────────────────────────────
    if hcs_type == "Half Slab (Open Top)":
        h_total = h + t_topping
        A_comp  = b_top * h_total
        yb_comp = h_total / 2.0
        yt_comp = h_total - yb_comp
        I_comp  = b_top * h_total ** 3 / 12.0
        Sb_comp = I_comp / yb_comp
        St_comp = I_comp / yt_comp
        yt_hcs  = abs(h - yb_comp) if abs(h - yb_comp) > 1e-3 else 1e-3
        St_hcs  = I_comp / yt_hcs
        St_top_tr = St_comp * n_mod
        comp = dict(net_props)
        comp.update({
            "A_comp"   : A_comp,
            "yb_comp"  : yb_comp,
            "yt_comp"  : yt_comp,
            "I_comp"   : I_comp,
            "Sb_comp"  : Sb_comp,
            "St_comp"  : St_comp,
            "St_hcs"   : St_hcs,
            "St_top_tr": St_top_tr,
            "h_total"  : h_total,
            "A_top_tr" : b_top * t_topping,
            "b_top_tr" : b_top,
        })
        return comp

    # ── Case C: Full HCS + transformed topping ────────────────────────────────
    b_top_tr = b_top * n_mod
    A_top_tr = b_top_tr * t_topping
    y_top_c  = h + t_topping / 2.0

    A_comp   = An + A_top_tr
    yb_comp  = (An * yb + A_top_tr * y_top_c) / A_comp
    yt_comp  = h + t_topping - yb_comp

    d_net    = yb_comp - yb
    d_top    = y_top_c - yb_comp
    I_top_tr = b_top_tr * t_topping ** 3 / 12.0
    I_comp   = In + An * d_net ** 2 + I_top_tr + A_top_tr * d_top ** 2

    Sb_comp   = I_comp / yb_comp
    St_comp   = I_comp / yt_comp
    yt_hcs    = abs(h - yb_comp) if abs(h - yb_comp) > 1e-3 else 1e-3
    St_hcs    = I_comp / yt_hcs
    St_top_tr = St_comp * n_mod

    h_total  = h + t_topping

    comp = dict(net_props)
    comp.update({
        "A_comp"   : A_comp,
        "yb_comp"  : yb_comp,
        "yt_comp"  : yt_comp,
        "I_comp"   : I_comp,
        "Sb_comp"  : Sb_comp,
        "St_comp"  : St_comp,
        "St_hcs"   : St_hcs,
        "St_top_tr": St_top_tr,
        "h_total"  : h_total,
        "A_top_tr" : A_top_tr,
        "b_top_tr" : b_top_tr,
    })
    return comp


# =============================================================================
# 3. PRESTRESS ECCENTRICITY
# =============================================================================
def calc_ps_eccentricity(
        yb     : float,
        dp_bot : float,
        dp_top : float,
        n_top  : int,
        Aps_bot: float,
        Aps_top: float,
) -> dict:
    """
    Eccentricity of prestressing force from section centroid (net section).
    Ref: PCI Design Handbook 8th Ed. Sec. 2.2  |  ACI/PCI 319-25 Cl. 26.10

    Sign convention (PCI standard for simply-supported prestressed beams):
        e_bot  = dp_bot − yb   (+ve when bottom steel is BELOW centroid → favourable)
        e_top  = dp_top − yb   (−ve when top steel is ABOVE centroid)

    Net eccentricity (resultant of all PS steel):
        e_net = (Aps_bot×e_bot + Aps_top×e_top) / (Aps_bot + Aps_top)

    Parameters
    ----------
    yb      : centroid from bottom of net section (mm)
    dp_bot  : distance from bottom fibre to bottom steel CG (mm)
    dp_top  : distance from bottom fibre to top steel CG (mm)
    n_top   : number of top tendons (0 = none present)
    Aps_bot : total bottom PS area (mm²)
    Aps_top : total top PS area (mm²)

    Returns
    -------
    dict — keys: e_bot, e_top, e_net  (all in mm)
    """
    e_bot = dp_bot - yb
    e_top = dp_top - yb if n_top > 0 else 0.0

    Aps_total = Aps_bot + Aps_top
    e_net     = (Aps_bot * e_bot + Aps_top * e_top) / Aps_total if Aps_total > 0 else 0.0

    return {
        "e_bot": e_bot,
        "e_top": e_top,
        "e_net": e_net,
    }


# =============================================================================
# 4. MASTER FUNCTION
# =============================================================================
def get_all_section_props(ss: dict) -> dict:
    """
    Master function — reads session_state dict, calls all three calculation
    functions above, and returns a combined dict with ALL section properties
    ready to be stored in session_state with prefix 'sp_'.

    Reads from ss
    -------------
    Geometry  : b_top, h, tf_bot, hcs_type
    Voids     : core_shape, d_core, n_core, h_straight, h_taper,
                A_core_1, A_voids_total, h_core
    Topping   : has_topping, t_topping, n_mod
    Prestress : n_bot, n_top, cover_bot, cover_top, ps_area,
                Aps_bot, Aps_top, dp_bot, dp_top

    Returns
    -------
    dict — superset of calc_net_section() + calc_composite_section() keys
           plus eccentricity keys: e_bot, e_top, e_net
    """
    # ── Geometry ──────────────────────────────────────────────────────────────
    b_top         = ss["b_top"]
    h             = ss["h"]
    tf_bot        = ss["tf_bot"]
    hcs_type      = ss["hcs_type"]
    core_shape    = ss["core_shape"]
    d_core        = float(ss["d_core"])
    n_core        = int(ss["n_core"])
    h_straight    = float(ss["h_straight"])
    h_taper       = float(ss["h_taper"])
    A_core_1      = ss["A_core_1"]
    A_voids_total = ss["A_voids_total"]
    h_core        = ss["h_core"]
    t_topping     = float(ss["t_topping"]) if ss.get("has_topping") else 0.0
    n_mod         = ss.get("n_mod", 1.0)

    # ── Prestress layout ──────────────────────────────────────────────────────
    ps_area  = ss.get("ps_area", 19.6)
    n_bot    = int(ss.get("n_bot", 0))
    n_top    = int(ss.get("n_top", 0))
    cover_bot= float(ss.get("cover_bot", 35))
    cover_top= float(ss.get("cover_top", 30))
    Aps_bot  = ss.get("Aps_bot",  n_bot * ps_area)
    Aps_top  = ss.get("Aps_top",  n_top * ps_area)
    dp_bot   = ss.get("dp_bot",   h - cover_bot)
    dp_top   = ss.get("dp_top",   cover_top)

    # ── 1. Net section ────────────────────────────────────────────────────────
    net = calc_net_section(
        b_top         = b_top,
        h             = h,
        tf_bot        = tf_bot,
        core_shape    = core_shape,
        d_core        = d_core,
        n_core        = n_core,
        h_straight    = h_straight,
        h_taper       = h_taper,
        A_core_1      = A_core_1,
        A_voids_total = A_voids_total,
        h_core        = h_core,
    )

    # ── 2. Composite section ──────────────────────────────────────────────────
    comp = calc_composite_section(
        net_props = net,
        b_top     = b_top,
        h         = h,
        t_topping = t_topping,
        n_mod     = n_mod,
        hcs_type  = hcs_type,
    )

    # ── 3. Eccentricity ───────────────────────────────────────────────────────
    ecc = calc_ps_eccentricity(
        yb      = net["yb"],
        dp_bot  = dp_bot,
        dp_top  = dp_top,
        n_top   = n_top,
        Aps_bot = Aps_bot,
        Aps_top = Aps_top,
    )

    # ── Merge: comp already contains all net keys ─────────────────────────────
    result = dict(comp)
    result.update(ecc)
    return result
