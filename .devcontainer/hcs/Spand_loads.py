"""
HCS Design — Span Validation, Transfer Length & Load Diagrams
==============================================================
Reference : ACI/PCI CODE-319-25 Cl. 7.7.2, 16.2.6.2, 25.8.6, 25.8.7
            ACI 318-19 §25.8.6.1 & §25.8.7.1
            PCI Design Handbook, 8th Ed. Sec. 4.2.3 & Fig. 4.10.1.1
            ASCE 7 / ACI 318-19 Table 5.3.1 (load combinations)
Units     : SI only (mm, kN, MPa)

Functions
---------
calc_transfer_development_length  : l_t and l_d for wire/strand
check_prestress_development       : Compare L_an to l_d → FULL / PARTIAL / NON-PS
calc_factored_loads_and_diagrams  : Factored & service SFD/BMD for simply-supported HCS
"""

import numpy as np


def calc_transfer_development_length(
        ps_type: str,
        d_ps: float,
        fpu: float,
        fpi: float,
        fpy: float,
        assumed_loss_pct: float = 20.0
) -> dict:
    """
    Transfer length and development length for pretensioned wire/strand.

    Transfer Length (l_t)
    ---------------------
    Wire   : l_t = 50 × d_ps
             Ref: PCI Design Handbook 8th Ed., Sec. 4.2.3
    Strand : l_t = max(60 × d_ps,  fse/20.7 × d_ps)
             Ref: ACI 318-19 Eq. 25.8.6.1 (SI unit approx.; 20.7 ≈ 3000 psi / 145)
             Conservative: take the larger of the two values.

    Development Length (l_d)
    ------------------------
    ACI 318-19 Eq. 25.8.7.1 in SI:
        l_d = l_t + (fps - fse) × d_ps / 20.7
    where:
        fse  = effective prestress after losses (MPa)  → estimated as fpi × (1 - loss%)
        fps  = stress at nominal flexural strength (MPa) → conservative: min(fpu, fpy+70)
               (full ACI fps formula computed in Phase 5)
        20.7 = unit-conversion factor (ksi·in → MPa·mm / 25.4)

    Parameters
    ----------
    ps_type           : "PC Wire (plain/indented)" or "7-Wire Strand (low relax)"
    d_ps              : Nominal diameter of wire/strand (mm)
    fpu               : Ultimate tensile strength (MPa)
    fpi               : Initial prestress at jacking (MPa)
    fpy               : Yield strength of PS steel (MPa)
    assumed_loss_pct  : Assumed total prestress loss (%) — placeholder for Phase 3

    Returns
    -------
    dict with keys: l_t, l_d, fse_est, fps_est, method_lt, loss_note
    """
    fse_est = fpi * (1.0 - assumed_loss_pct / 100.0)    # MPa — estimated after losses
    fps_est = min(fpu, fpy + 70.0)                       # MPa — conservative estimate

    if ps_type == "PC Wire (plain/indented)":
        l_t    = 50.0 * d_ps           # PCI Sec. 4.2.3
        method = "Wire: 50 × d_ps (PCI Sec. 4.2.3)"
    else:
        l_t_60  = 60.0 * d_ps
        l_t_aci = (fse_est / 20.7) * d_ps   # ACI 318-19 §25.8.6.1 SI approx.
        l_t     = max(l_t_60, l_t_aci)
        method  = (f"Strand: max(60d = {l_t_60:.0f}, ACI 25.8.6 = {l_t_aci:.0f}) mm")

    # ACI 318-19 Eq. 25.8.7.1 — development length in SI
    l_d = l_t + (fps_est - fse_est) * d_ps / 20.7

    return {
        "l_t"       : l_t,
        "l_d"       : l_d,
        "fse_est"   : fse_est,
        "fps_est"   : fps_est,
        "method_lt" : method,
        "loss_note" : f"Assumed loss = {assumed_loss_pct}% (placeholder — Phase 3 will update)",
    }


def check_prestress_development(L_an: float, l_d: float) -> dict:
    """
    Compare analysis span against development length.

    Rules (ACI 318-19 Sec. 25.8.7 / PCI Design Handbook Sec. 4.2.3)
    -----------------------------------------------------------------
    L_an ≥ 1.5 × l_d  → FULL  prestress development assumed
    l_d ≤ L_an < 1.5×l_d → PARTIAL  (caution — reduced stress at midspan)
    L_an < l_d         → NON-PRESTRESSED (critical — section behaves as RC)

    Parameters
    ----------
    L_an : Analysis span (mm)
    l_d  : Development length (mm)

    Returns
    -------
    dict with keys: status, is_prestressed, message
    """
    if L_an >= 1.5 * l_d:
        return {
            "status"         : "FULL",
            "is_prestressed" : True,
            "message"        : "Full prestress development assumed. OK.",
        }
    elif L_an >= l_d:
        frac = L_an / l_d
        return {
            "status"         : "PARTIAL",
            "is_prestressed" : "partial",
            "message"        : (f"Caution: L_an / l_d = {frac:.2f}. "
                                f"Prestress only partially developed at midspan. "
                                f"Stress checks near midspan may be reduced."),
        }
    else:
        frac = L_an / l_d
        return {
            "status"         : "NON-PRESTRESSED",
            "is_prestressed" : False,
            "message"        : (f"CRITICAL: L_an / l_d = {frac:.2f} < 1.0. "
                                f"Prestress CANNOT fully develop. "
                                f"Section behaves as non-prestressed (RC). "
                                f"Verify with structural engineer or increase span."),
        }


def calc_factored_loads_and_diagrams(
        L_an, b_bottom, t_topping,
        wc, wc_top, has_topping,
        SW_HCS, SW_topping,
        SDL, LL,
        has_point_load,
        P1_DL, P1_LL, x_P1,
        P2_DL, P2_LL, x_P2,
        slab_position,
        N: int = 200
) -> dict:
    """
    Compute factored and service load diagrams for a simply-supported HCS.

    Load Combinations — ASCE 7 / ACI 318-19 Table 5.3.1
    -----------------------------------------------------
    wu_area = 1.2×(SW_HCS + SW_topping + SDL) + 1.6×LL   [kN/m²]  factored
    ws_area = 1.0×(SW_HCS + SW_topping + SDL + LL)         [kN/m²]  service

    Area → panel line loads [kN/mm]:
    w_line = w_area × b_bottom / 1e6

    Point Load Factoring
    --------------------
    Pu1 = 1.2×P1_DL + 1.6×P1_LL   [kN]
    Pu2 = 1.2×P2_DL + 1.6×P2_LL   [kN]
    Ps1 = P1_DL + P1_LL             [kN]  service
    Ps2 = P2_DL + P2_LL             [kN]  service

    Effective Width Reduction — PCI Fig. 4.10.1.1
    -----------------------------------------------
    Interior slab : eff_w = 0.50 × L_an
    Edge slab     : eff_w = 0.25 × L_an
    Reduction factor rf = b_bottom / eff_w  (capped at 1.0)

    Diagrams computed at N equally-spaced points along the span.

    Parameters
    ----------
    All lengths in mm, loads in kN or kN/m².

    Returns
    -------
    dict with numpy arrays (x_arr, Vu_arr, Mu_arr, Vs_arr, Ms_arr)
    and scalar maxima (Ra_u, Rb_u, wu_area, ws_area, Vu_max, Mu_max, etc.)
    """
    # ── Area loads → line loads (kN/mm) ──────────────────────────────────────
    wu_area = 1.2 * (SW_HCS + SW_topping + SDL) + 1.6 * LL   # kN/m²
    ws_area = SW_HCS + SW_topping + SDL + LL                   # kN/m² service
    wu_line = wu_area * b_bottom / 1e6    # kN/mm
    ws_line = ws_area * b_bottom / 1e6    # kN/mm

    # ── Point loads ───────────────────────────────────────────────────────────
    eff_w = 0.50 * L_an if slab_position == "Interior slab" else 0.25 * L_an
    rf    = min(b_bottom / max(eff_w, 1.0), 1.0)   # reduction factor ≤ 1.0

    if has_point_load:
        Pu1      = (1.2 * P1_DL + 1.6 * P1_LL) * rf
        Ps1      = (P1_DL + P1_LL)              * rf
        P2_active = (P2_DL + P2_LL) > 0
        Pu2      = (1.2 * P2_DL + 1.6 * P2_LL) * rf if P2_active else 0.0
        Ps2      = (P2_DL + P2_LL)              * rf if P2_active else 0.0
        x_P1_use = float(x_P1)
        x_P2_use = float(x_P2) if P2_active else L_an * 2  # push out of range
    else:
        Pu1 = Ps1 = Pu2 = Ps2 = 0.0
        x_P1_use = L_an * 2   # push out of range
        x_P2_use = L_an * 2

    # ── Reactions ─────────────────────────────────────────────────────────────
    x_P1_use = min(x_P1_use, L_an)
    x_P2_use = min(x_P2_use, L_an)

    Ra_u = (wu_line * L_an / 2
            + Pu1 * (L_an - x_P1_use) / L_an
            + Pu2 * (L_an - x_P2_use) / L_an)
    Rb_u = (wu_line * L_an / 2
            + Pu1 * x_P1_use / L_an
            + Pu2 * x_P2_use / L_an)
    Ra_s = (ws_line * L_an / 2
            + Ps1 * (L_an - x_P1_use) / L_an
            + Ps2 * (L_an - x_P2_use) / L_an)

    # ── Diagrams at N points ──────────────────────────────────────────────────
    x = np.linspace(0.0, L_an, N)

    step1u = np.where(x > x_P1_use, Pu1, 0.0)
    step2u = np.where(x > x_P2_use, Pu2, 0.0)
    step1s = np.where(x > x_P1_use, Ps1, 0.0)
    step2s = np.where(x > x_P2_use, Ps2, 0.0)

    # kN and kN·mm
    Vu = Ra_u - wu_line * x - step1u - step2u
    Mu = (Ra_u * x
          - wu_line * x ** 2 / 2.0
          - step1u * np.maximum(x - x_P1_use, 0.0)
          - step2u * np.maximum(x - x_P2_use, 0.0))

    Vs = Ra_s - ws_line * x - step1s - step2s
    Ms = (Ra_s * x
          - ws_line * x ** 2 / 2.0
          - step1s * np.maximum(x - x_P1_use, 0.0)
          - step2s * np.maximum(x - x_P2_use, 0.0))

    Mu_max_val = float(np.max(Mu))
    Mu_max_x   = float(x[np.argmax(Mu)])
    Vu_max_val = float(np.max(np.abs(Vu)))

    return {
        "x_arr"   : x,
        "Vu_arr"  : Vu,
        "Mu_arr"  : Mu,
        "Vs_arr"  : Vs,
        "Ms_arr"  : Ms,
        "Ra_u"    : float(Ra_u),
        "Rb_u"    : float(Rb_u),
        "wu_area" : wu_area,
        "ws_area" : ws_area,
        "Vu_max"  : Vu_max_val,
        "Mu_max"  : Mu_max_val,
        "Mu_max_x": Mu_max_x,
        "Pu1_red" : Pu1,
        "Pu2_red" : Pu2,
        "x_P1_use": x_P1_use,
        "x_P2_use": x_P2_use,
    }
