"""
HCS Design — Geometry Calculations
====================================
Reference : ACI/PCI CODE-319-25 Ch. 7 & 26
            PCI Design Handbook, 8th Edition Sec. 2.2
            ACI 318-19 Eq. 19.2.2.1 (elastic modulus)
Units     : SI only (mm, mm², MPa, kN/m³)

Functions
---------
calc_core_area      : Area of one core void (Circular / Capsule / Teardrop)
calc_h_core         : Total height of one core void
calc_modular_ratio  : Elastic moduli Ec_hcs, Ec_top and modular ratio n_mod
get_ps_props        : Prestressing steel property dict from lookup tables
"""

import math
from hcs.constants import WIRE_PROPS, STRAND_PROPS


def calc_core_area(core_shape: str, d_core: float,
                   h_straight: float, h_taper: float) -> float:
    """
    Calculate area of ONE core void.

    Shapes
    ------
    Circular : Full circle
               A = π/4 · d²
    Capsule  : Semicircle top + rectangle + semicircle bottom = full circle + rectangle
               A = π/4 · d² + d · h_straight
    Teardrop : Semicircle top + triangular taper
               Bottom tapers to ~0.30·d_core; avg width ≈ 0.65·d_core
               A = π/4 · d² + 0.65 · d · h_taper

    Ref: ACI/PCI 319-25 — section property calculation
    """
    if core_shape == "Circular":
        return (math.pi / 4) * d_core ** 2
    elif core_shape == "Capsule":
        return (math.pi / 4) * d_core ** 2 + d_core * h_straight
    else:  # Teardrop
        return (math.pi / 4) * d_core ** 2 + 0.65 * d_core * h_taper


def calc_h_core(core_shape: str, d_core: float,
                h_straight: float, h_taper: float) -> float:
    """
    Total height of one core void.

    Circular : h_core = d_core
    Capsule  : h_core = d_core + h_straight
    Teardrop : h_core = d_core + h_taper

    Ref: ACI/PCI 319-25 — section property calculation
    """
    if core_shape == "Circular":
        return d_core
    elif core_shape == "Capsule":
        return d_core + h_straight
    else:  # Teardrop
        return d_core + h_taper


def calc_modular_ratio(wc: float, f_c: float,
                       wc_top: float, f_c_top: float) -> tuple:
    """
    Elastic moduli for HCS and topping concrete, and their modular ratio.

    Formula
    -------
    ACI 318-19 Eq. 19.2.2.1:
        Ec [MPa] = 0.043 · wc^1.5 · √f'c
        where wc must be in kg/m³

    Conversion: wc [kN/m³] → wc [kg/m³] = wc × 1000 / 9.81

    Parameters
    ----------
    wc      : Unit weight of HCS concrete (kN/m³)
    f_c     : 28-day compressive strength of HCS concrete (MPa)
    wc_top  : Unit weight of topping concrete (kN/m³)
    f_c_top : 28-day compressive strength of topping (MPa)

    Returns
    -------
    (Ec_hcs, Ec_top, n_mod) : all floats, MPa / dimensionless
    """
    wc_kgm3     = wc     * 1000 / 9.81
    wc_top_kgm3 = wc_top * 1000 / 9.81
    Ec_hcs = 0.043 * (wc_kgm3 ** 1.5) * math.sqrt(f_c)
    Ec_top = 0.043 * (wc_top_kgm3 ** 1.5) * math.sqrt(f_c_top)
    n_mod  = Ec_top / Ec_hcs
    return Ec_hcs, Ec_top, n_mod


def get_ps_props(ps_type: str, wire_dia: float, strand_size: str) -> dict:
    """
    Return prestressing steel properties dict.

    Delegates to WIRE_PROPS (PC Wire) or STRAND_PROPS (7-wire strand)
    based on ps_type string.

    Ref: ASTM A416 / PCI Design Handbook Table 2.11.1 / Indonesian mfr data
    """
    if ps_type == "PC Wire (plain/indented)":
        return WIRE_PROPS[wire_dia]
    else:
        return STRAND_PROPS[strand_size]
