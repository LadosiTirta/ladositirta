"""
footing/settlement.py
Settlement estimation for isolated spread footing.

References:
  - SNI 8460:2017 Pasal 9 (Allowable Settlement)
  - Bowles (1996) — Elastic (immediate) settlement
  - Terzaghi & Peck (1967) — Consolidation settlement
  - ACI 336.2R — Bearing and Settlement
"""
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# IMMEDIATE / ELASTIC SETTLEMENT
# ─────────────────────────────────────────────────────────────────────────────

def immediate_settlement(q_net_kPa: float, B_m: float, L_m: float,
                          Es_kPa: float, nu: float = 0.3,
                          Df_m: float = 1.0, embedment_factor: bool = True):
    """
    Immediate (elastic) settlement — Bowles (1996) / SNI 8460:2017 Lampiran D.

    δi = q_net × B × (1 - ν²) / Es × Iw × If

    Influence factor Iw (Steinbrenner approximation):
      For L/B = 1 (square): Iw ≈ 0.82
      For L/B = 2:          Iw ≈ 1.20
      For L/B → ∞:          Iw ≈ 1.52
      Interpolate: Iw = 0.82 + 0.29 × ln(L/B)

    Embedment factor If (Fox 1948):
      If = 1 - (1/(3.5 × e^(Df/B) × (L/B)^0.4))

    Parameters:
        q_net_kPa : net foundation pressure (service) = q_gross - γ_s × Df
        B_m       : footing width (m)
        L_m       : footing length (m) [L ≥ B]
        Es_kPa    : elastic modulus of soil (kPa)
        nu        : Poisson's ratio (0.3 sand, 0.4 clay)
        Df_m      : embedment depth (m)
        embedment_factor: apply Fox embedment correction

    Returns: δi (mm), detail dict
    """
    L_B = L_m / B_m
    Iw = 0.82 + 0.29 * np.log(L_B) if L_B > 1 else 0.82

    if embedment_factor:
        If = 1 - (1 / (3.5 * np.exp(Df_m / B_m) * L_B**0.4))
        If = max(If, 0.5)
    else:
        If = 1.0

    delta_m = q_net_kPa * B_m * (1 - nu**2) / Es_kPa * Iw * If
    delta_mm = delta_m * 1000

    detail = {
        "method": "Elastic (Immediate) Settlement — Bowles (1996)",
        "code_ref": "SNI 8460:2017 Lampiran D; Bowles (1996); ACI 336.2R",
        "formula": "δi = q_net × B × (1-ν²) / Es × Iw × If",
        "q_net_kPa": q_net_kPa,
        "B_m": B_m,
        "L_m": L_m,
        "L_B": L_B,
        "nu": nu,
        "Es_kPa": Es_kPa,
        "Iw": Iw,
        "If": If,
        "substitution": (
            f"δi = {q_net_kPa:.2f} × {B_m:.2f} × (1 - {nu}²) / {Es_kPa:.0f} × {Iw:.3f} × {If:.3f}"
        ),
        "delta_m": delta_m,
        "delta_mm": delta_mm,
    }
    return delta_mm, detail


# ─────────────────────────────────────────────────────────────────────────────
# CONSOLIDATION SETTLEMENT (CLAY)
# ─────────────────────────────────────────────────────────────────────────────

def consolidation_settlement(Cc: float, Cs: float, e0: float,
                              Hc_m: float, sigma_v0_kPa: float,
                              Pc_kPa: float, delta_sigma_kPa: float):
    """
    Primary consolidation settlement (Terzaghi).
    SNI 8460:2017 Pasal 9; Terzaghi & Peck (1967).

    Three cases:
      (a) NC Clay  (σ'v0 = Pc):
          Sc = Cc/(1+e0) × H × log10((σ'v0 + Δσ)/σ'v0)

      (b) OC Clay, stress stays below Pc (σ'v0 + Δσ ≤ Pc):
          Sc = Cs/(1+e0) × H × log10((σ'v0 + Δσ)/σ'v0)

      (c) OC Clay, stress exceeds Pc:
          Sc = Cs/(1+e0) × H × log10(Pc/σ'v0)
             + Cc/(1+e0) × H × log10((σ'v0+Δσ)/Pc)

    Parameters:
        Cc          : compression index
        Cs          : swelling/recompression index (≈ Cc/5 to Cc/10)
        e0          : initial void ratio
        Hc_m        : thickness of clay layer (m)
        sigma_v0_kPa: effective overburden stress at mid-layer (kPa)
        Pc_kPa      : preconsolidation pressure (kPa)
        delta_sigma_kPa: stress increase at mid-layer (kPa) — from Boussinesq

    Returns: Sc_mm, detail dict
    """
    OCR = Pc_kPa / sigma_v0_kPa if sigma_v0_kPa > 0 else 1.0
    sigma_f = sigma_v0_kPa + delta_sigma_kPa

    if OCR <= 1.0 or abs(OCR - 1.0) < 0.05:
        # NC Clay
        case = "NC Clay (OCR ≈ 1.0) — Normally Consolidated"
        Sc = Cc / (1 + e0) * Hc_m * np.log10(sigma_f / sigma_v0_kPa)
        formula = "Sc = Cc/(1+e₀) × H × log₁₀((σ'v0 + Δσ)/σ'v0)"
        sub = (f"   = {Cc}/{(1+e0):.3f} × {Hc_m} × log₁₀({sigma_f:.1f}/{sigma_v0_kPa:.1f})"
               f"\n   = {Sc:.4f} m")
    elif sigma_f <= Pc_kPa:
        # OC, stays OC
        case = "OC Clay — stress stays below Pc (lightly preconsolidated)"
        Sc = Cs / (1 + e0) * Hc_m * np.log10(sigma_f / sigma_v0_kPa)
        formula = "Sc = Cs/(1+e₀) × H × log₁₀((σ'v0 + Δσ)/σ'v0)"
        sub = (f"   = {Cs}/{(1+e0):.3f} × {Hc_m} × log₁₀({sigma_f:.1f}/{sigma_v0_kPa:.1f})"
               f"\n   = {Sc:.4f} m")
    else:
        # OC, exceeds Pc
        case = "OC Clay — stress exceeds Pc (crosses yield stress)"
        Sc1 = Cs / (1 + e0) * Hc_m * np.log10(Pc_kPa / sigma_v0_kPa)
        Sc2 = Cc / (1 + e0) * Hc_m * np.log10(sigma_f / Pc_kPa)
        Sc = Sc1 + Sc2
        formula = ("Sc = Cs/(1+e₀)×H×log₁₀(Pc/σ'v0) + Cc/(1+e₀)×H×log₁₀((σ'v0+Δσ)/Pc)")
        sub = (f"   = {Cs:.3f}/{(1+e0):.3f}×{Hc_m}×log₁₀({Pc_kPa:.1f}/{sigma_v0_kPa:.1f})"
               f" + {Cc:.3f}/{(1+e0):.3f}×{Hc_m}×log₁₀({sigma_f:.1f}/{Pc_kPa:.1f})"
               f"\n   = {Sc1:.4f} + {Sc2:.4f} = {Sc:.4f} m")

    Sc_mm = Sc * 1000

    detail = {
        "method": "Primary Consolidation Settlement — Terzaghi",
        "code_ref": "SNI 8460:2017 Pasal 9.3; Terzaghi & Peck (1967)",
        "case": case,
        "OCR": OCR,
        "Cc": Cc, "Cs": Cs, "e0": e0,
        "Hc_m": Hc_m,
        "sigma_v0_kPa": sigma_v0_kPa,
        "Pc_kPa": Pc_kPa,
        "delta_sigma_kPa": delta_sigma_kPa,
        "sigma_f_kPa": sigma_f,
        "formula": formula,
        "substitution": sub,
        "Sc_m": Sc,
        "Sc_mm": Sc_mm,
    }
    return Sc_mm, detail


def stress_increase_boussinesq(q_kPa: float, B_m: float, L_m: float, z_m: float):
    """
    Stress increase Δσ at depth z below center of rectangular load.
    Newmark (1935) / Boussinesq solution.

    Uses influence factor m = L/B, n = z/B.
    Formula: Δσ = q × Iσ

    Iσ = 1/(2π) × [2mn√(m²+n²+1)/(m²+n²+1+m²n²) × (m²+n²+2)/(m²+n²+1)
                  + arcsin(2mn√(m²+n²+1)/(m²+n²+1+m²n²))]

    Reference: Bowles (1996) Eq. 5-49
    """
    m = L_m / B_m
    n = z_m / B_m

    A = 2 * m * n * np.sqrt(m**2 + n**2 + 1) / (m**2 + n**2 + 1 + m**2 * n**2)
    B_val = (m**2 + n**2 + 2) / (m**2 + n**2 + 1)
    Isigma = (1 / (2 * np.pi)) * (A * B_val + np.arctan(A))
    delta_sigma = q_kPa * 4 * Isigma   # × 4 for full rectangle (quarter method)
    return delta_sigma, Isigma


# ─────────────────────────────────────────────────────────────────────────────
# SETTLEMENT CHECK SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

# SNI 8460:2017 Pasal 9.3 allowable settlements
ALLOW_SETTLEMENT = {
    "isolated_total_mm": 25,
    "isolated_differential_fraction": 1 / 500,
    "raft_total_mm": 50,
    "note": "SNI 8460:2017 Pasal 9.3.1 — Isolated footing: total ≤ 25mm, differential ≤ L/500",
}


def check_settlement(delta_i_mm: float, delta_c_mm: float,
                     span_m: float = None):
    """
    Check total and differential settlement.

    Returns: check dict
    """
    delta_total_mm = delta_i_mm + delta_c_mm
    allow_total = ALLOW_SETTLEMENT["isolated_total_mm"]

    ok_total = delta_total_mm <= allow_total

    result = {
        "delta_i_mm": delta_i_mm,
        "delta_c_mm": delta_c_mm,
        "delta_total_mm": delta_total_mm,
        "allow_total_mm": allow_total,
        "ok_total": ok_total,
        "code_ref": ALLOW_SETTLEMENT["note"],
    }

    if span_m:
        allow_diff = span_m * 1000 / 500  # mm
        result["allow_differential_mm"] = allow_diff
        result["span_m"] = span_m
        result["note_diff"] = (
            f"Differential settlement limit = L/500 = {span_m:.1f}×1000/500 = {allow_diff:.1f} mm"
        )

    result["recommendation"] = (
        "" if ok_total else
        f"TOTAL SETTLEMENT {delta_total_mm:.1f} mm EXCEEDS {allow_total} mm. "
        "Consider: larger footing (reduce q_net), soil improvement, or deep foundation."
    )
    return result
