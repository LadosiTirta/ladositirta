# =============================================================================
# uditch/calc_engine.py  — PART 1: Load Analysis & Internal Forces
# =============================================================================
#
# PUBLIC API (this file):
#   run_load_analysis(inp: dict) -> ForceResult
#       Master dispatcher. Reads inp["condition"] and calls the correct
#       condition sub-function. Returns a ForceResult dataclass.
#
# INTERNAL sub-functions:
#   _loads_lateral(inp)          → LateralLoads   (earth + surcharge/point)
#   _loads_on_cu(inp)            → CULoads         (CU dead + live loads)
#   _cond1_forces(inp)           → ForceResult     (cantilever ± strut)
#   _cond2_forces(inp)           → ForceResult     (column: N + M)
#   _cond3_forces(inp)           → ForceResult     (pure cantilever)
#
# PART 2 (next step — section capacity):
#   calc_capacity_flexure(...)
#   calc_capacity_shear(...)
#   calc_pm_interaction(...)
#
# =============================================================================
# STRUCTURAL ASSUMPTIONS & CODE REFERENCES
# =============================================================================
# • SNI 2847:2019  — Tata Cara Perancangan Beton Struktural
# • SNI 1727:2020  — Beban Minimum untuk Perancangan Bangunan Gedung
# • AASHTO LRFD 9th Ed. (2020) — Bridge Design Specifications
# • Rankine lateral earth pressure:
#     Ka = tan²(45° - φ/2)                         [Rankine 1857]
#     σh  = Ka · γs · z  − 2c · √Ka               [active pressure]
# • Boussinesq point-load lateral pressure:
#     σh  = (3·P·z³) / (2π·R⁵)   where R = √(x²+z²)
#   For strip/line load (width L_seg along trench):
#     integrated over segment length.
# • Equivalent surcharge height (AASHTO 3.11.6.4):
#     heq = f(wall height H) from Table 3.11.6.4-2
# • Wheel load dispersal through fill (2:1 method):
#     A_contact = (B_w + H_fill)(L_seg + H_fill)   [vertical stress at CU top]
#     q_CU = P / A_contact
# • Condition 1 gap-closing: if δ_cantilever ≥ gap → boundary changes
#     Simple cantilever EI deflection:
#     δ = (q·H⁴)/(8EI) + (P_lat·H³)/(3EI)
#     After gap closes: wall = propped cantilever (CU = spring/strut at top)
# • Condition 2: CU treated as simply-supported beam → reaction R = P/2 on each wall
#     Wall = short column with N = R + W_wall and M = N·e + V_CU·arm
# • Condition 3: pure cantilever, wall fixed at base
#
# All forces in kN, moments in kN·m, lengths in m, stresses in kPa/MPa.
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

# ── Unit convenience ──────────────────────────────────────────────────────────
def _mm(val_mm: float) -> float:
    """Convert mm → m."""
    return val_mm / 1000.0


def _compat(inp: dict) -> dict:
    """
    Compatibility shim: maps new field names (Tahap A) to internal calc names.
    Called at the top of every load/force function.
    Returns a NEW dict — does not mutate inp.
    """
    d = dict(inp)

    # ── Wall geometry ──────────────────────────────────────────────────────────
    # New: ud_wall_thick_top (ta), ud_wall_thick_bot (tb), ud_slab_thick (ts)
    # Old functions used: ud_wall_thickness, ud_base_thickness
    if "ud_wall_thick_top" in d and "ud_wall_thickness" not in d:
        # Use ta (top) as the critical wall thickness for section checks
        d["ud_wall_thickness"] = d["ud_wall_thick_top"]
    if "ud_slab_thick" in d and "ud_base_thickness" not in d:
        d["ud_base_thickness"] = d["ud_slab_thick"]

    # ── Vehicle → wheel ───────────────────────────────────────────────────────
    # New: axle_load_G, wheel_dist_x1, wheel_spacing_x2
    # Old: wheel_load (kN, one wheel), wheel_dist (m, wheel CL from outer wall)
    if "axle_load_G" in d and "wheel_load" not in d:
        d["wheel_load"] = d["axle_load_G"] / 2.0   # P1 = G/2
    # ── cover_load_type_idx default (Kondisi 2 default = vehicle, not pedestrian) ─
    if "cover_load_type_idx" not in d:
        d["cover_load_type_idx"] = 1   # default = vehicle

    if "wheel_dist_x1" in d and "wheel_dist" not in d:
        # x_centre_from_wall = x1 (edge-to-edge) + 0 (we use x1 as centre distance
        # because for Boussinesq, x is measured from wall face to wheel CL)
        # Conservative: use x1 as the distance (closest wheel edge is the most critical)
        # x_centre = x1 + wheel contact half-width (0.125m) — but keep simple: use x1
        d["wheel_dist"] = max(d["wheel_dist_x1"], 0.05)

    # ── Soil fill / surcharge beside UD ──────────────────────────────────────
    # New: soil_fill_beside (m), fill_type_idx
    # Old: udl_beside (kPa, uniform)
    if "soil_fill_beside" in d and "udl_beside" not in d:
        Hf        = d.get("soil_fill_beside", 0.0)
        gamma_s   = d.get("gamma_s", 18.0)
        fill_type = d.get("fill_type_idx", 0)
        # Convert fill height to equivalent uniform surcharge pressure:
        # Soil: q = gamma_s * Hf
        # Asphalt + soil: use composite gamma = 22 kN/m³ for asphalt layer (0.05m) + soil
        # Concrete rigid: treat as surcharge q = 24 * Hf
        if fill_type == 0:
            q_fill = gamma_s * Hf
        elif fill_type == 1:
            gamma_asphalt = 22.0   # kN/m³
            q_fill = gamma_asphalt * Hf
        else:  # concrete
            q_fill = 24.0 * Hf
        d["udl_beside"] = q_fill

    # ── CU gap ────────────────────────────────────────────────────────────────
    # New: cu_gap (mm)
    # Old: gap_cu_ud (mm)
    if "cu_gap" in d and "gap_cu_ud" not in d:
        d["gap_cu_ud"] = d["cu_gap"]

    # ── CU geometry for CU load calc ─────────────────────────────────────────
    # New: cu_thick_centre (tcu mm)
    # Old: cu_thickness (mm)
    if "cu_thick_centre" in d and "cu_thickness" not in d:
        d["cu_thickness"] = d["cu_thick_centre"]

    # ── Fill above CU (crossing) ──────────────────────────────────────────────
    # New: soil_fill_above_cu (m)
    # Old: soil_fill_h (m)
    if "soil_fill_h" not in d:
        d["soil_fill_h"] = d.get("soil_fill_above_cu", 0.0)

    # ── Pedestrian load ───────────────────────────────────────────────────────
    # New: pedestrian_kpa
    # Old: pedestrian_load
    if "pedestrian_kpa" in d and "pedestrian_load" not in d:
        d["pedestrian_load"] = d.get("pedestrian_kpa", 5.0)

    # ── Phi factors ───────────────────────────────────────────────────────────
    # New: phi_shear_f, phi_axial_f
    # Old: phi_shear_factor, phi_axial
    if "phi_shear_f" in d and "phi_shear_factor" not in d:
        d["phi_shear_factor"] = d["phi_shear_f"]
    if "phi_axial_f" in d and "phi_axial" not in d:
        d["phi_axial"] = d["phi_axial_f"]

    # ── Connection mechanism ──────────────────────────────────────────────────
    # New: conn_mechanism (0=none,1=notch,2=dowel)
    # Old: conn_type / conn_type_idx (0=notch,1=dowel)
    if "conn_mechanism" in d and "conn_type_idx" not in d:
        cm = d["conn_mechanism"]
        d["conn_type_idx"] = max(0, cm - 1)   # 0→0(none=bearing), 1→0, 2→1(dowel)
        d["conn_type"]     = d["conn_type_idx"]

    # ── Rebar field names ────────────────────────────────────────────────────
    # New: rebar_tension_dia/spc (outer wall, tarik)
    # Old: rebar_outer_dia/spc
    if "rebar_tension_dia" in d and "rebar_outer_dia" not in d:
        d["rebar_outer_dia"] = d["rebar_tension_dia"]
        d["rebar_outer_spc"] = d.get("rebar_tension_spc", 150)
    if "rebar_comp_dia" in d and "rebar_inner_dia" not in d:
        # Old code had separate inner_tension; now inner = comp face
        d["rebar_inner_dia"] = d["rebar_comp_dia"]
        d["rebar_inner_spc"] = d.get("rebar_comp_spc", 200)

    # Slab rebar
    if "rebar_slab_bot_dia" in d and "cu_rebar_bot_dia" not in d:
        d["cu_rebar_bot_dia"] = d["rebar_slab_bot_dia"]
        d["cu_rebar_bot_spc"] = d.get("rebar_slab_bot_spc", 150)
        d["cu_rebar_top_dia"] = d.get("rebar_slab_top_dia", 10)
        d["cu_rebar_top_spc"] = d.get("rebar_slab_top_spc", 200)

    # ── Effective depths ─────────────────────────────────────────────────────
    # New names: d_eff_tension, d_eff_comp, d_eff_slab
    # Old names: d_eff_outer, d_eff_inner, d_eff_cu
    if "d_eff_tension" in d and "d_eff_outer" not in d:
        d["d_eff_outer"] = d["d_eff_tension"]
        d["d_eff_inner"] = d.get("d_eff_comp", d["d_eff_tension"])
        d["d_eff_cu"]    = d.get("d_eff_slab", d["d_eff_tension"])

    # ── CU overlap (used in _cond2_forces for eccentricity) ──────────────────
    # New geometry: te-cu = ta + gap; no "overlap" concept.
    # Old code used cu_overlap for eccentricity of CU bearing on wall.
    # Map: cu_overlap ≈ te-cu = ta + gap (how far CU extends below UD wall top)
    if "cu_overlap" not in d:
        ta_mm  = d.get("ud_wall_thick_top", d.get("ud_wall_thickness", 80))
        gap_mm = d.get("cu_gap", d.get("gap_cu_ud", 20))
        d["cu_overlap"] = ta_mm + gap_mm   # te-cu in mm

    return d



# =============================================================================
# DATA CLASSES  — carry both results AND the full calculation trace
# =============================================================================

@dataclass
class CalcStep:
    """
    One row in the step-by-step calculation table.
    Format for ui_output: Symbol | Formula | Substitution | Result | Unit | Code Ref
    """
    symbol:       str          # e.g. "Ka"
    description:  str          # human-readable name (bilingual label key OR raw string)
    formula:      str          # LaTeX string, e.g. r"tan^2(45° - \phi/2)"
    substitution: str          # numeric substitution string
    result:       float        # numeric value
    unit:         str          # e.g. "—", "kN/m²", "kN·m/m"
    code_ref:     str          # e.g. "AASHTO LRFD 3.11.5.1"


@dataclass
class LateralLoads:
    """Lateral earth pressure + surcharge acting on one UD wall (per metre run)."""
    Ka:               float         # Rankine active pressure coefficient
    sigma_h_base:     float         # Total horizontal stress at wall base (kPa)
    sigma_h_top:      float         # Total horizontal stress at wall top (kPa)
    F_earth:          float         # Resultant earth force (kN/m run)
    F_surcharge:      float         # Resultant surcharge force (kN/m run)
    F_total:          float         # F_earth + F_surcharge (kN/m run)
    arm_earth:        float         # Height of F_earth from wall base (m)
    arm_surcharge:    float         # Height of F_surcharge from wall base (m)
    method:           str           # "surcharge" | "point_line"
    steps:            list[CalcStep] = field(default_factory=list)


@dataclass
class CULoads:
    """Loads transferred to the CU (per metre width)."""
    w_dead:        float         # CU self-weight (kN/m²)
    w_soil:        float         # Soil fill on CU (kN/m²)
    w_live:        float         # Live load on CU (kN/m²)
    q_total_unfactored: float    # Total unfactored (kN/m²)
    q_total_factored:   float    # Total factored Wu (kN/m²)
    # Reactions on each UD wall from CU (simple beam model)
    R_cu_unfactored: float       # kN/m width per wall
    R_cu_factored:   float       # kN/m width per wall
    steps:           list[CalcStep] = field(default_factory=list)


@dataclass
class SectionForces:
    """
    Factored internal forces at the critical section of a member.
    All per-unit-length (metre along segment) unless noted.
    """
    Mu: float    # Factored bending moment (kN·m/m)
    Vu: float    # Factored shear force (kN/m)
    Nu: float    # Factored axial force (kN/m)  +ve = compression


@dataclass
class ForceResult:
    """
    Top-level output of run_load_analysis().
    Contains forces for every critical section plus the full trace.
    """
    condition:      str                    # "Kondisi 1" | "Kondisi 2" | "Kondisi 3"

    # ── Critical section forces (factored) ────────────────────────────────────
    wall_base:      SectionForces = None   # UD wall base (fixed end)
    wall_top:       SectionForces = None   # UD wall top (at CU contact) — Cond 1 strut
    cu_midspan:     SectionForces = None   # CU midspan — Cond 2
    cu_support:     SectionForces = None   # CU at support (shear) — Cond 2
    base_slab:      SectionForces = None   # UD base slab midspan — all conditions

    # ── Sub-results ──────────────────────────────────────────────────────────
    lateral:        LateralLoads  = None
    cu_loads:       CULoads       = None

    # ── Condition-1 gap analysis ──────────────────────────────────────────────
    gap_mm:         float = 0.0            # User-input gap (mm)
    delta_cant_mm:  float = 0.0            # Cantilever deflection at top (mm)
    gap_closed:     bool  = False          # True → propped cantilever governs

    # ── Calculation trace (all steps, in order) ───────────────────────────────
    steps:          list[CalcStep] = field(default_factory=list)

    # ── Input echo (for report header) ───────────────────────────────────────
    inp_echo:       dict = field(default_factory=dict)


# =============================================================================
# HELPER: Rankine Ka
# =============================================================================

def _rankine_Ka(phi_deg: float) -> float:
    """Active earth pressure coefficient (Rankine)."""
    phi_r = math.radians(phi_deg)
    return math.tan(math.radians(45.0) - phi_r / 2.0) ** 2


# =============================================================================
# HELPER: AASHTO equivalent surcharge height
# AASHTO LRFD 9th Ed. Table 3.11.6.4-2
# heq (m) as function of wall height H (m)
# =============================================================================

_AASHTO_HEQ_TABLE = [
    # (H_wall_m, heq_m)
    (0.0,  1.80),
    (1.5,  1.35),
    (3.0,  0.90),
    (6.0,  0.60),
]

def _aashto_heq(H_wall_m: float) -> float:
    """
    Interpolate equivalent surcharge height from AASHTO Table 3.11.6.4-2.
    AASHTO LRFD 9th Ed. §3.11.6.4
    """
    table = _AASHTO_HEQ_TABLE
    if H_wall_m <= table[0][0]:
        return table[0][1]
    if H_wall_m >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        h0, heq0 = table[i]
        h1, heq1 = table[i + 1]
        if h0 <= H_wall_m <= h1:
            t = (H_wall_m - h0) / (h1 - h0)
            return heq0 + t * (heq1 - heq0)
    return table[-1][1]


# =============================================================================
# HELPER: Boussinesq lateral pressure from point load
# For a point load P (kN) at distance x (m) from wall, integrated over
# segment length L_seg (m), at depth z (m) below surface.
# Returns lateral stress σh (kPa) at depth z.
#
# Ref: Poulos & Davis (1974); NAVFAC DM7.02 Fig. 3
# For STRIP load (integrated Boussinesq):
#   σh = (P / π·L) · [α - sin(α)·cos(α + 2δ)]
#   where α and δ are angles from the load to the wall point.
# We use the simpler point-load version integrated numerically over L_seg.
# =============================================================================

def _boussinesq_point_lateral(P_kN: float, x_m: float, z_m: float,
                               L_seg: float, n_pts: int = 40) -> float:
    """
    Lateral stress (kPa) on vertical wall at depth z due to point load P.
    Integrates numerically along segment length L_seg.

    σh = (3·P·x²·z³) / (2π·R⁵)   [Boussinesq 3D point load]
    where R = √(x² + y² + z²), integrated over y ∈ [-L/2, L/2].

    Returns: σh in kPa (force per unit area on wall face).
    """
    if z_m <= 0 or x_m <= 0:
        return 0.0
    dy = L_seg / n_pts
    sigma_total = 0.0
    for i in range(n_pts):
        y = -L_seg / 2 + (i + 0.5) * dy
        R = math.sqrt(x_m**2 + y**2 + z_m**2)
        if R < 1e-9:
            continue
        sigma_total += (3 * P_kN * x_m**2 * z_m**3) / (2 * math.pi * R**5) * dy
    return sigma_total   # kN/m² = kPa at unit wall-width slice


def _boussinesq_resultant(P_kN: float, x_m: float, H_wall_m: float,
                           L_seg: float, n_depth: int = 60) -> tuple[float, float]:
    """
    Integrate Boussinesq lateral stress over wall height.
    Returns (F_kN_per_m, arm_from_base_m) acting on 1 m width strip.
    """
    dz = H_wall_m / n_depth
    F = 0.0
    M_base = 0.0
    for i in range(n_depth):
        z = (i + 0.5) * dz
        sigma = _boussinesq_point_lateral(P_kN, x_m, z, L_seg)
        contrib = sigma * dz          # kN/m  (per m width)
        F += contrib
        M_base += contrib * (H_wall_m - z)   # moment about base
    arm = M_base / F if F > 1e-9 else H_wall_m / 3
    return F, arm


# =============================================================================
# LATERAL LOADS
# =============================================================================

def _loads_lateral(inp: dict) -> LateralLoads:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    """
    Calculate lateral earth pressure + lateral live load on one UD wall.
    Handles:
      • Surcharge method (AASHTO Table 3.11.6.4-2)
      • Point/Line load method (Boussinesq 3D, integrated over segment)

    All pressures are SERVICE (unfactored). Factoring done in _condX_forces.
    """
    steps: list[CalcStep] = []

    # ── Geometry (m) ──────────────────────────────────────────────────────────
    H_wall    = _mm(inp["ud_inner_height"])   # m  — free height of wall
    x_wheel   = inp["wheel_dist"]             # m  — wheel CL from outer wall face
    L_seg     = inp["ud_length"]              # m  — segment length
    gamma_s   = inp["gamma_s"]                # kN/m³
    phi_deg   = inp["phi_soil"]
    c_soil    = inp["cohesion"]               # kPa
    method    = inp["lat_method_idx"]         # 0=surcharge, 1=point/line
    P_wheel   = inp["wheel_load"]             # kN (one wheel)
    q_beside  = inp["udl_beside"]             # kPa uniform beside UD

    # ── Ka ────────────────────────────────────────────────────────────────────
    Ka = _rankine_Ka(phi_deg)
    steps.append(CalcStep(
        symbol      = "Ka",
        description = "Koefisien tekanan tanah aktif Rankine / Rankine active Ka",
        formula     = r"K_a = \tan^2\!\left(45° - \dfrac{\phi}{2}\right)",
        substitution= f"tan²(45° − {phi_deg}/2)",
        result      = Ka,
        unit        = "—",
        code_ref    = "Rankine (1857); SNI 8460:2017 §C.6.4",
    ))

    # ── Earth pressure distribution ───────────────────────────────────────────
    # σh(z) = Ka·γs·z − 2c·√Ka   (active, with cohesion intercept, min 0)
    def _sigma_earth(z_m: float) -> float:
        s = Ka * gamma_s * z_m - 2 * c_soil * math.sqrt(Ka)
        return max(s, 0.0)

    sigma_top  = _sigma_earth(0.0)       # always 0 for cohesionless (or cohesive with c)
    sigma_base = _sigma_earth(H_wall)

    steps.append(CalcStep(
        symbol      = "σh,base",
        description = "Tekanan tanah horizontal di dasar dinding / Earth pressure at wall base",
        formula     = r"\sigma_{h,base} = K_a \cdot \gamma_s \cdot H - 2c\sqrt{K_a}",
        substitution= f"{Ka:.3f} × {gamma_s} × {H_wall:.3f} − 2×{c_soil}×√{Ka:.3f}",
        result      = sigma_base,
        unit        = "kPa",
        code_ref    = "SNI 8460:2017 §6.4.1; AASHTO LRFD §3.11.5.1",
    ))

    # Resultant earth force (triangular: area of triangle)
    F_earth   = 0.5 * (sigma_top + sigma_base) * H_wall   # kN/m run
    # Arm from base: centroid of trapezoid
    if (sigma_top + sigma_base) > 1e-9:
        arm_earth = H_wall / 3 * (sigma_base + 2 * sigma_top) / (sigma_base + sigma_top)
    else:
        arm_earth = H_wall / 3

    steps.append(CalcStep(
        symbol      = "F_earth",
        description = "Resultan gaya tanah aktif / Resultant active earth force",
        formula     = r"F_{earth} = \tfrac{1}{2}(\sigma_{top}+\sigma_{base}) \cdot H",
        substitution= f"½×({sigma_top:.2f}+{sigma_base:.2f})×{H_wall:.3f}",
        result      = F_earth,
        unit        = "kN/m",
        code_ref    = "AASHTO LRFD §3.11.5.1",
    ))
    steps.append(CalcStep(
        symbol      = "y_earth",
        description = "Lengan momen F_earth dari dasar / Moment arm of earth force from base",
        formula     = r"y_{earth} = \dfrac{H}{3}\cdot\dfrac{\sigma_{base}+2\sigma_{top}}{\sigma_{base}+\sigma_{top}}",
        substitution= f"({H_wall:.3f}/3)×({sigma_base:.2f}+2×{sigma_top:.2f})/({sigma_base:.2f}+{sigma_top:.2f})",
        result      = arm_earth,
        unit        = "m",
        code_ref    = "Statics — centroid of trapezoid",
    ))

    # ── Live load lateral (surcharge OR Boussinesq) ───────────────────────────
    if method == 0:
        # ── Surcharge equivalent (AASHTO Table 3.11.6.4-2) ───────────────────
        heq = _aashto_heq(H_wall)
        sigma_surcharge = Ka * gamma_s * heq          # kPa, uniform over height
        # Add uniform surcharge from q_beside
        sigma_q_beside  = Ka * q_beside               # kPa, uniform

        sigma_live_total = sigma_surcharge + sigma_q_beside
        F_surcharge      = sigma_live_total * H_wall   # kN/m
        arm_surcharge    = H_wall / 2                  # uniform → midheight

        steps.append(CalcStep(
            symbol      = "heq",
            description = "Tinggi surcharge ekivalen roda / AASHTO equivalent surcharge height",
            formula     = r"h_{eq} = f(H_{wall})",
            substitution= f"f({H_wall:.2f} m) dari Tabel 3.11.6.4-2",
            result      = heq,
            unit        = "m",
            code_ref    = "AASHTO LRFD 9th Ed. Table 3.11.6.4-2",
        ))
        steps.append(CalcStep(
            symbol      = "σ_surcharge",
            description = "Tekanan lateral surcharge / Surcharge lateral pressure",
            formula     = r"\sigma_{sur} = K_a \cdot \gamma_s \cdot h_{eq} + K_a \cdot q_{beside}",
            substitution= f"{Ka:.3f}×{gamma_s}×{heq:.2f} + {Ka:.3f}×{q_beside}",
            result      = sigma_live_total,
            unit        = "kPa",
            code_ref    = "AASHTO LRFD §3.11.6.4",
        ))
        steps.append(CalcStep(
            symbol      = "F_surcharge",
            description = "Resultan gaya surcharge lateral / Surcharge resultant",
            formula     = r"F_{sur} = \sigma_{sur} \cdot H_{wall}",
            substitution= f"{sigma_live_total:.3f} × {H_wall:.3f}",
            result      = F_surcharge,
            unit        = "kN/m",
            code_ref    = "AASHTO LRFD §3.11.6.4",
        ))

    else:
        # ── Point/Line load (Boussinesq) ──────────────────────────────────────
        # Wheel distance from WALL FACE (outer face of wall):
        # x_wheel is measured from outer face, so x = x_wheel (m)
        x_m = x_wheel if x_wheel > 0.05 else 0.05   # avoid singularity

        # Note: P_wheel is one wheel. Distribute as point load.
        # Additional uniform surcharge from q_beside:
        sigma_q_uniform  = Ka * q_beside              # kPa (surcharge from uniform)
        F_q_beside       = sigma_q_uniform * H_wall   # kN/m

        F_boussinesq, arm_boussinesq = _boussinesq_resultant(
            P_kN    = P_wheel,
            x_m     = x_m,
            H_wall_m= H_wall,
            L_seg   = L_seg,
        )
        # F_boussinesq is already in kN per L_seg width, convert to kN/m
        F_boussinesq_per_m = F_boussinesq / L_seg

        F_surcharge  = F_boussinesq_per_m + F_q_beside
        arm_surcharge= (F_boussinesq_per_m * arm_boussinesq + F_q_beside * (H_wall / 2)) / max(F_surcharge, 1e-9)

        steps.append(CalcStep(
            symbol      = "F_Boussi",
            description = "Gaya lateral Boussinesq dari beban roda / Boussinesq lateral from wheel",
            formula     = r"F = \int_0^H \frac{3Px^2z^3}{2\pi R^5}\,dz \text{ (integrasi numerik)}",
            substitution= f"P={P_wheel}kN, x={x_m:.2f}m, H={H_wall:.2f}m, L={L_seg}m",
            result      = F_boussinesq_per_m,
            unit        = "kN/m",
            code_ref    = "Boussinesq (1885); NAVFAC DM7.02 Fig.3; SNI 8460 C.6",
        ))
        steps.append(CalcStep(
            symbol      = "y_Boussi",
            description = "Lengan momen Boussinesq dari dasar / Moment arm of Boussinesq force",
            formula     = r"y = M_{base} / F",
            substitution= f"numerik",
            result      = arm_boussinesq,
            unit        = "m",
            code_ref    = "Numerical integration",
        ))
        steps.append(CalcStep(
            symbol      = "F_q_beside",
            description = "Gaya lateral akibat q di samping UD / Lateral from q beside",
            formula     = r"F_q = K_a \cdot q \cdot H",
            substitution= f"{Ka:.3f}×{q_beside}×{H_wall:.3f}",
            result      = F_q_beside,
            unit        = "kN/m",
            code_ref    = "Rankine; AASHTO §3.11.5.1",
        ))
        steps.append(CalcStep(
            symbol      = "F_surcharge",
            description = "Total gaya lateral hidup / Total live lateral force",
            formula     = r"F_{sur} = F_{Boussi}/m + F_{q_{beside}}",
            substitution= f"{F_boussinesq_per_m:.3f} + {F_q_beside:.3f}",
            result      = F_surcharge,
            unit        = "kN/m",
            code_ref    = "—",
        ))

    F_total = F_earth + F_surcharge
    steps.append(CalcStep(
        symbol      = "F_lat,total",
        description = "Total gaya lateral (tanah + beban hidup) / Total lateral force",
        formula     = r"F_{total} = F_{earth} + F_{sur}",
        substitution= f"{F_earth:.3f} + {F_surcharge:.3f}",
        result      = F_total,
        unit        = "kN/m",
        code_ref    = "—",
    ))

    return LateralLoads(
        Ka            = Ka,
        sigma_h_base  = sigma_base,
        sigma_h_top   = sigma_top,
        F_earth       = F_earth,
        F_surcharge   = F_surcharge,
        F_total       = F_total,
        arm_earth     = arm_earth,
        arm_surcharge = arm_surcharge,
        method        = "surcharge" if method == 0 else "point_line",
        steps         = steps,
    )


# =============================================================================
# CU LOADS
# =============================================================================

def _loads_on_cu(inp: dict) -> CULoads:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    """
    Compute loads on the Cover (CU) and the resulting reactions on UD walls.
    CU modelled as simply-supported beam spanning B_o (outer width of UD).
    """
    steps: list[CalcStep] = []

    # ── Geometry ──────────────────────────────────────────────────────────────
    B_i     = _mm(inp["ud_inner_width"])      # m
    t_w     = _mm(inp["ud_wall_thickness"])   # m
    B_o     = B_i + 2 * t_w                  # m  span of CU
    t_cu    = _mm(inp["cu_thickness"])        # m
    L_seg   = inp["ud_length"]               # m
    gamma_c = inp["gamma_c"]                 # kN/m³
    gamma_s = inp["gamma_s"]                 # kN/m³
    H_fill  = inp["soil_fill_h"]             # m  soil above CU
    P_wheel = inp["wheel_load"]              # kN
    clt_idx = inp.get("cover_load_type_idx", 0)   # 0=pedestrian,1=vehicle,2=soil+wheel
    q_ped   = inp.get("pedestrian_load", 5.0)     # kPa
    gamma_DL = inp["gamma_DL"]
    gamma_LL = inp["gamma_LL"]

    # ── CU self-weight ────────────────────────────────────────────────────────
    w_dead = gamma_c * t_cu    # kN/m²
    steps.append(CalcStep(
        symbol      = "w_CU",
        description = "Berat sendiri CU / CU self-weight",
        formula     = r"w_{CU} = \gamma_c \cdot t_{CU}",
        substitution= f"{gamma_c} × {t_cu:.3f}",
        result      = w_dead,
        unit        = "kN/m²",
        code_ref    = "SNI 1727:2020 §3.1",
    ))

    # ── Soil fill on CU ───────────────────────────────────────────────────────
    w_soil = gamma_s * H_fill   # kN/m²
    steps.append(CalcStep(
        symbol      = "w_soil",
        description = "Beban tanah timbunan di atas CU / Soil fill load on CU",
        formula     = r"w_{soil} = \gamma_s \cdot H_{fill}",
        substitution= f"{gamma_s} × {H_fill}",
        result      = w_soil,
        unit        = "kN/m²",
        code_ref    = "SNI 1727:2020 §3.3",
    ))

    # ── Live load on CU ───────────────────────────────────────────────────────
    if clt_idx == 0:
        # Pedestrian
        w_live = q_ped
        steps.append(CalcStep(
            symbol      = "w_LL",
            description = "Beban pejalan kaki / Pedestrian load",
            formula     = r"w_{LL} = q_{ped}",
            substitution= f"{q_ped}",
            result      = w_live,
            unit        = "kPa",
            code_ref    = "SNI 1727:2020 Tabel 4-1",
        ))

    elif clt_idx == 1:
        # Vehicle wheel directly on CU (no fill)
        # Distribute wheel over contact patch + CU thickness (45° dispersion)
        B_wheel   = 0.25    # m  standard wheel contact width (AASHTO 3.6.1.2.5)
        L_wheel   = 0.50    # m  standard wheel contact length
        B_eff     = B_wheel + 2 * t_cu   # dispersion through CU slab (45°)
        L_eff     = min(L_wheel + 2 * t_cu, L_seg)
        A_eff     = B_eff * L_eff
        w_live    = P_wheel / A_eff   # kN/m²

        steps.append(CalcStep(
            symbol      = "B_eff",
            description = "Lebar efektif distribusi beban roda melalui CU / Effective wheel load width",
            formula     = r"B_{eff} = B_{wheel} + 2t_{CU}",
            substitution= f"{B_wheel} + 2×{t_cu:.3f}",
            result      = B_eff,
            unit        = "m",
            code_ref    = "AASHTO LRFD §3.6.1.2.5; SNI 1725:2016 §6.6",
        ))
        steps.append(CalcStep(
            symbol      = "w_LL",
            description = "Beban roda terdistribusi ke CU / Distributed wheel load on CU",
            formula     = r"w_{LL} = \dfrac{P_{wheel}}{B_{eff} \cdot L_{eff}}",
            substitution= f"{P_wheel} / ({B_eff:.3f}×{L_eff:.3f})",
            result      = w_live,
            unit        = "kN/m²",
            code_ref    = "AASHTO LRFD §3.6.1.2.5",
        ))

    else:
        # Soil fill + wheel (2:1 dispersion method through fill)
        B_wheel = 0.25    # m
        L_wheel = 0.50    # m
        A_21    = (B_wheel + H_fill) * (L_wheel + H_fill)   # 2:1 method
        w_wheel_fill = P_wheel / A_21 if A_21 > 0 else 0.0
        w_live  = w_wheel_fill   # soil fill already in w_soil

        steps.append(CalcStep(
            symbol      = "w_LL",
            description = "Distribusi beban roda melalui timbunan (metode 2:1) / 2:1 wheel dispersion through fill",
            formula     = r"w_{LL} = \dfrac{P}{(B_w + H_f)(L_w + H_f)}",
            substitution= f"{P_wheel}/({B_wheel}+{H_fill})×({L_wheel}+{H_fill})",
            result      = w_live,
            unit        = "kN/m²",
            code_ref    = "AASHTO LRFD §3.6.1.2.6b; NAVFAC DM7.02 §7.1",
        ))

    # ── Total loads ───────────────────────────────────────────────────────────
    q_unfactored = w_dead + w_soil + w_live
    q_factored   = gamma_DL * (w_dead + w_soil) + gamma_LL * w_live

    steps.append(CalcStep(
        symbol      = "wu,CU",
        description = "Beban terfaktor total di CU / Total factored load on CU",
        formula     = r"w_u = \gamma_{DL}(w_{CU}+w_{soil}) + \gamma_{LL} \cdot w_{LL}",
        substitution= f"{gamma_DL}×({w_dead:.3f}+{w_soil:.3f}) + {gamma_LL}×{w_live:.3f}",
        result      = q_factored,
        unit        = "kN/m²",
        code_ref    = "SNI 2847:2019 Ps.5.3.1 (U=1.2D+1.6L)",
    ))

    # ── CU reactions on UD walls ──────────────────────────────────────────────
    # Simple beam: R = w·B_o/2  (per metre CU width)
    R_unfactored = q_unfactored * B_o / 2
    R_factored   = q_factored   * B_o / 2

    steps.append(CalcStep(
        symbol      = "R_CU",
        description = "Reaksi CU ke dinding UD (per dinding) / CU reaction on each UD wall",
        formula     = r"R_{CU} = \dfrac{w_u \cdot B_o}{2}",
        substitution= f"{q_factored:.3f} × {B_o:.3f} / 2",
        result      = R_factored,
        unit        = "kN/m",
        code_ref    = "Statics — simply supported beam",
    ))

    return CULoads(
        w_dead           = w_dead,
        w_soil           = w_soil,
        w_live           = w_live,
        q_total_unfactored = q_unfactored,
        q_total_factored   = q_factored,
        R_cu_unfactored  = R_unfactored,
        R_cu_factored    = R_factored,
        steps            = steps,
    )


# =============================================================================
# CONDITION 1 — Approaching Wheel Load (UD + CU, Wheel Beside UD)
# =============================================================================
#
#  Phase A — CANTILEVER CHECK (before gap closes)
#  -----------------------------------------------
#  UD wall = vertical cantilever, fixed at base.
#  Lateral load = earth + surcharge (from _loads_lateral).
#  Earth: triangular distribution.
#  Surcharge: uniform OR Boussinesq.
#
#  At wall base (critical section):
#    Mu_cant = M_earth + M_surcharge
#    Vu_cant = F_earth + F_surcharge
#    Nu_cant = W_wall + R_CU_vertical    (compression)
#
#  Deflection at wall top (cantilever under combined loads):
#    δ_earth    = Ka·γs·H⁴ / (30·E·I)   [triangular load on cantilever]
#    δ_surcharge= (w_sur·H⁴)/(8·E·I)    [uniform load] OR numerical for Boussinesq
#    δ_total    = δ_earth + δ_surcharge  (in mm)
#
#  Phase B — PROPPED CANTILEVER (after gap closes, δ ≥ gap)
#  ----------------------------------------------------------
#  CU acts as horizontal strut at top → wall = propped cantilever.
#  Prop force H_strut found by compatibility (unit-load method).
#
#  Propped cantilever under UDL w (with prop at top):
#    H_strut = (3·w·H) / 8   for uniform w
#  For triangular (max at base):
#    H_strut = (w_base·H) / 10
#  For combined (superposition):
#    H_strut,total = H_strut,earth + H_strut,sur
#
#  Internal forces with prop:
#    At base: Mu = Mu_cant − H_strut · H
#             Vu = F_total − H_strut
#    At top (prop):  Vu_top = H_strut
#
#  GOVERNING: max(Mu_cantilever, Mu_propped) → reported separately.
# =============================================================================

def _cond1_forces(inp: dict, lateral: LateralLoads, cu_loads: CULoads) -> ForceResult:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    steps: list[CalcStep] = []

    # ── Geometry & material ───────────────────────────────────────────────────
    H_wall  = _mm(inp["ud_inner_height"])    # m   free height of wall
    t_w     = _mm(inp["ud_wall_thickness"])  # m
    L_seg   = inp["ud_length"]               # m
    gamma_c = inp["gamma_c"]                 # kN/m³
    fc      = inp["fc_prime"]                # MPa
    gap_mm  = inp["gap_cu_ud"]               # mm

    gamma_DL = inp["gamma_DL"]
    gamma_LL = inp["gamma_LL"]

    # ── Wall self-weight (per metre width) ────────────────────────────────────
    W_wall = gamma_c * H_wall * t_w          # kN/m²  → kN/m run of wall

    steps.append(CalcStep(
        symbol      = "W_wall",
        description = "Berat sendiri dinding UD / UD wall self-weight",
        formula     = r"W_{wall} = \gamma_c \cdot H_{wall} \cdot t_w",
        substitution= f"{gamma_c} × {H_wall:.3f} × {t_w:.3f}",
        result      = W_wall,
        unit        = "kN/m",
        code_ref    = "SNI 1727:2020 §3.1",
    ))

    # Factored axial (from CU reaction + wall self-weight) at wall base
    Nu_base = gamma_DL * (W_wall + cu_loads.R_cu_unfactored)

    steps.append(CalcStep(
        symbol      = "Nu,base",
        description = "Gaya aksial terfaktor di dasar dinding / Factored axial at wall base",
        formula     = r"N_u = \gamma_{DL}(W_{wall} + R_{CU})",
        substitution= f"{gamma_DL}×({W_wall:.3f}+{cu_loads.R_cu_unfactored:.3f})",
        result      = Nu_base,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Phase A: CANTILEVER moments at base ───────────────────────────────────
    # Moment from earth pressure (triangular, max at base):
    # M_earth = F_earth × arm_earth
    Mu_earth_serv = lateral.F_earth * lateral.arm_earth
    Mu_sur_serv   = lateral.F_surcharge * lateral.arm_surcharge

    Mu_cant_serv  = Mu_earth_serv + Mu_sur_serv
    Vu_cant_serv  = lateral.F_total

    # Factored
    Mu_cant = gamma_DL * Mu_earth_serv + gamma_LL * Mu_sur_serv
    Vu_cant = gamma_DL * lateral.F_earth + gamma_LL * lateral.F_surcharge

    steps.append(CalcStep(
        symbol      = "Mu,cant",
        description = "Momen terfaktor kantilever di dasar dinding (Phase A) / Factored cantilever moment at base",
        formula     = r"M_u = \gamma_{DL} M_{earth} + \gamma_{LL} M_{sur}",
        substitution= f"{gamma_DL}×{Mu_earth_serv:.3f} + {gamma_LL}×{Mu_sur_serv:.3f}",
        result      = Mu_cant,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1; AASHTO LRFD §3.4.1",
    ))
    steps.append(CalcStep(
        symbol      = "Vu,cant",
        description = "Geser terfaktor kantilever di dasar (Phase A) / Factored shear at base",
        formula     = r"V_u = \gamma_{DL} F_{earth} + \gamma_{LL} F_{sur}",
        substitution= f"{gamma_DL}×{lateral.F_earth:.3f} + {gamma_LL}×{lateral.F_surcharge:.3f}",
        result      = Vu_cant,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Deflection at wall top (cantilever, service loads) ────────────────────
    # Ec = 4700√fc (MPa) → (kN/m²) = Ec_MPa × 1000
    Ec_MPa = 4700 * math.sqrt(fc)           # MPa
    Ec     = Ec_MPa * 1e3                   # kN/m²
    I_wall = (t_w ** 3) / 12               # m⁴/m (per m width)

    steps.append(CalcStep(
        symbol      = "Ec",
        description = "Modulus elastisitas beton / Concrete elastic modulus",
        formula     = r"E_c = 4700\sqrt{f'_c}",
        substitution= f"4700×√{fc}",
        result      = Ec_MPa,
        unit        = "MPa",
        code_ref    = "SNI 2847:2019 Ps.19.2.2.1",
    ))
    steps.append(CalcStep(
        symbol      = "I_wall",
        description = "Momen inersia dinding (per m lebar) / Wall moment of inertia per m width",
        formula     = r"I = \dfrac{t_w^3}{12}",
        substitution= f"({t_w:.3f})³/12",
        result      = I_wall,
        unit        = "m⁴/m",
        code_ref    = "Statics",
    ))

    EI = Ec * I_wall    # kN·m²/m

    # Cantilever tip deflection:
    # Triangular load (max w_base at base → 0 at top):
    #   δ_tri = w_base · H⁴ / (30 · EI)   [cantilever, load max at fixed end]
    # Uniform surcharge:
    #   δ_uni = w_sur · H⁴ / (8 · EI)
    Ka      = lateral.Ka
    gamma_s = inp["gamma_s"]
    c_soil  = inp["cohesion"]
    w_base  = max(Ka * gamma_s * H_wall - 2 * c_soil * math.sqrt(Ka), 0.0)

    delta_earth_m = w_base * (H_wall ** 4) / (30 * EI)

    # Surcharge: if method=0 → uniform; if method=1 → approx uniform using sigma average
    if lateral.method == "surcharge":
        sigma_sur_uniform = lateral.F_surcharge / H_wall   # average intensity kPa
        delta_sur_m       = sigma_sur_uniform * (H_wall ** 4) / (8 * EI)
    else:
        # Boussinesq: treat as uniform equivalent for deflection estimate
        sigma_sur_equiv = lateral.F_surcharge / H_wall
        delta_sur_m     = sigma_sur_equiv * (H_wall ** 4) / (8 * EI)

    delta_total_m  = delta_earth_m + delta_sur_m
    delta_total_mm = delta_total_m * 1000

    steps.append(CalcStep(
        symbol      = "δ_earth",
        description = "Defleksi kantilever akibat tekanan tanah (beban segitiga) / Cantilever deflection from earth pressure",
        formula     = r"\delta_{earth} = \dfrac{w_{base} \cdot H^4}{30 \cdot EI}",
        substitution= f"{w_base:.3f}×{H_wall:.3f}⁴ / (30×{EI:.1f})",
        result      = delta_earth_m * 1000,
        unit        = "mm",
        code_ref    = "Timoshenko — Strength of Materials §6; cantilever triangular load",
    ))
    steps.append(CalcStep(
        symbol      = "δ_sur",
        description = "Defleksi kantilever akibat surcharge / Cantilever deflection from surcharge",
        formula     = r"\delta_{sur} = \dfrac{w_{sur} \cdot H^4}{8 \cdot EI}",
        substitution= f"{lateral.F_surcharge/H_wall:.3f}×{H_wall:.3f}⁴ / (8×{EI:.1f})",
        result      = delta_sur_m * 1000,
        unit        = "mm",
        code_ref    = "Timoshenko — cantilever uniform load",
    ))
    steps.append(CalcStep(
        symbol      = "δ_total",
        description = "Total defleksi puncak dinding / Total wall tip deflection",
        formula     = r"\delta_{total} = \delta_{earth} + \delta_{sur}",
        substitution= f"{delta_earth_m*1000:.2f} + {delta_sur_m*1000:.2f}",
        result      = delta_total_mm,
        unit        = "mm",
        code_ref    = "Superposition",
    ))

    gap_closed = delta_total_mm >= gap_mm
    steps.append(CalcStep(
        symbol      = "gap_check",
        description = "Cek apakah defleksi menutup celah / Gap closure check",
        formula     = r"\delta_{total} \geq \Delta_{gap}?",
        substitution= f"{delta_total_mm:.2f} mm ≥ {gap_mm} mm → {'YA (strut aktif)' if gap_closed else 'TIDAK (kantilever murni)'}",
        result      = 1.0 if gap_closed else 0.0,
        unit        = "—",
        code_ref    = "Engineering judgment; Condition 1 mechanism",
    ))

    # ── Phase B: PROPPED CANTILEVER (if gap closed) ───────────────────────────
    if gap_closed:
        # Prop force (CU strut reaction) by compatibility:
        # For triangular load (max w_base at fixed bottom → 0 at free top):
        #   H_strut,tri  = w_base · H / 10   (Roark's 7th Ed. Table 8.1 Case 7)
        # For uniform surcharge:
        #   H_strut,uni  = w_sur · H / 8     (Roark's — propped cantilever uniform)
        w_sur_uniform = lateral.F_surcharge / H_wall

        H_strut_earth = w_base       * H_wall / 10.0
        H_strut_sur   = w_sur_uniform * H_wall / 8.0
        H_strut_total = gamma_DL * H_strut_earth + gamma_LL * H_strut_sur

        steps.append(CalcStep(
            symbol      = "H_strut",
            description = "Gaya tumpuan strut CU (gaya horisontal di puncak dinding) / CU strut prop force at wall top",
            formula     = r"H_{strut} = \gamma_{DL}\frac{w_{base}H}{10} + \gamma_{LL}\frac{w_{sur}H}{8}",
            substitution= f"{gamma_DL}×{w_base:.3f}×{H_wall:.3f}/10 + {gamma_LL}×{w_sur_uniform:.3f}×{H_wall:.3f}/8",
            result      = H_strut_total,
            unit        = "kN/m",
            code_ref    = "Roark's Formulas 7th Ed. Table 8.1; propped cantilever",
        ))

        # Moments with prop:
        # At base: Mu_prop = Mu_cant − H_strut · H
        Mu_prop_base = Mu_cant - H_strut_total * H_wall
        # Point of zero shear (max moment in span):
        # V(x) from base (upward x): V = F_total - w_base·x - w_sur·x + H_strut [at top]
        # Simplified: location of max moment ≈ solve shear = 0
        # For triangular + uniform on propped cantilever, numerically find xmax
        Vu_prop_base = Vu_cant - H_strut_total
        Vu_prop_top  = H_strut_total   # = strut force

        # Moment at top (at prop): M_top = 0 (pin prop) → for notch/bearing, treat as pin
        Mu_prop_top = 0.0

        steps.append(CalcStep(
            symbol      = "Mu,prop,base",
            description = "Momen terfaktor di dasar dinding (Phase B, propped) / Factored moment at base — propped",
            formula     = r"M_{u,base}^{prop} = M_{u,cant} - H_{strut} \cdot H",
            substitution= f"{Mu_cant:.3f} − {H_strut_total:.3f}×{H_wall:.3f}",
            result      = Mu_prop_base,
            unit        = "kN·m/m",
            code_ref    = "Statics — propped cantilever",
        ))
        steps.append(CalcStep(
            symbol      = "Vu,prop,base",
            description = "Geser terfaktor di dasar (Phase B) / Factored shear at base — propped",
            formula     = r"V_{u,base}^{prop} = V_{u,cant} - H_{strut}",
            substitution= f"{Vu_cant:.3f} − {H_strut_total:.3f}",
            result      = Vu_prop_base,
            unit        = "kN/m",
            code_ref    = "Statics",
        ))

        # ── Governing forces at base ─────────────────────────────────────────
        # Design uses Phase B (propped) forces since that is the actual state.
        # Phase A forces are retained for reference.
        Mu_design_base = Mu_prop_base
        Vu_design_base = Vu_prop_base
        Mu_design_top  = Mu_prop_top
        Vu_design_top  = Vu_prop_top
        H_strut_design = H_strut_total

    else:
        # Pure cantilever governs
        Mu_design_base = Mu_cant
        Vu_design_base = Vu_cant
        Mu_design_top  = 0.0
        Vu_design_top  = 0.0
        H_strut_design = 0.0

    # ── Base slab forces ──────────────────────────────────────────────────────
    # UD base slab: two-way/one-way slab with:
    #   - Uplift from soil (zero if above ground) or hydrostatic = 0 (conservative ignore)
    #   - Self-weight of base slab (downward)
    #   - Reaction from walls (UD walls push down on slab edges)
    t_b     = _mm(inp["ud_base_thickness"])  # m
    B_i     = _mm(inp["ud_inner_width"])
    w_base_slab_DL = gamma_c * t_b         # kN/m² slab self-weight
    # Net downward load on base slab (conservative: no uplift modelled here)
    # Reactions from walls: P_wall = Nu_base (axial in wall) transferred to slab edge
    # Model base slab as cantilever from each wall face → moment at wall face
    #   Mu_base_slab = w_base_slab·(B_i/2)²/2   (one-way slab at midspan)
    w_u_slab = gamma_DL * w_base_slab_DL
    Mu_base_slab = w_u_slab * (B_i / 2) ** 2 / 2   # simplified: midspan of one-way
    Vu_base_slab = w_u_slab * B_i / 2

    steps.append(CalcStep(
        symbol      = "Mu,slab",
        description = "Momen terfaktor dasar UD (tengah bentang) / Factored moment at UD base slab midspan",
        formula     = r"M_{u,slab} = \dfrac{w_u \cdot (B_i/2)^2}{2}",
        substitution= f"{w_u_slab:.3f}×({B_i:.3f}/2)² / 2",
        result      = Mu_base_slab,
        unit        = "kN·m/m",
        code_ref    = "Statics — one-way slab at midspan",
    ))

    return ForceResult(
        condition   = "Kondisi 1",
        wall_base   = SectionForces(
            Mu = Mu_design_base,
            Vu = Vu_design_base,
            Nu = Nu_base,
        ),
        wall_top    = SectionForces(
            Mu = Mu_design_top,
            Vu = Vu_design_top,
            Nu = 0.0,             # no axial at top (prop = lateral only)
        ),
        base_slab   = SectionForces(
            Mu = Mu_base_slab,
            Vu = Vu_base_slab,
            Nu = 0.0,
        ),
        lateral     = lateral,
        cu_loads    = cu_loads,
        gap_mm      = gap_mm,
        delta_cant_mm = delta_total_mm,
        gap_closed  = gap_closed,
        steps       = steps,
        inp_echo    = inp,
    )


# =============================================================================
# CONDITION 2 — Wheel on Cover (CU acts as beam → walls = short columns)
# =============================================================================
#
#  Loading on CU:
#    w_u (kN/m²) from _loads_on_cu (includes wheel at midspan or distributed)
#    Wheel at midspan → CU = simply supported beam → R_wall = P/2 + w_dead·L/2
#
#  UD wall acts as SHORT COLUMN:
#    N = R_CU (vertical reaction) + W_wall (self-weight)
#    V = lateral earth + surcharge (same as Cond.1 Phase A, but lateral is still
#        present even with wheel on cover)
#    M at base = V·H − N·e   where e = eccentricity of N from wall centroid
#
#  Eccentricity: CU rests on top of wall with some eccentricity depending on
#  notch geometry. Conservative: e = t_w/6 (R acts at inner-third of wall).
#  Alternatively, user may specify; here we use t_w/4 (common for precast).
#
#  For asymmetric reinforcement (outer ≠ inner), P-M interaction needed.
#  This file produces N, M, V at critical sections for Part 2 (capacity).
# =============================================================================

def _cond2_forces(inp: dict, lateral: LateralLoads, cu_loads: CULoads) -> ForceResult:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    steps: list[CalcStep] = []

    # ── Geometry ──────────────────────────────────────────────────────────────
    H_wall  = _mm(inp["ud_inner_height"])
    t_w     = _mm(inp["ud_wall_thickness"])
    B_i     = _mm(inp["ud_inner_width"])
    B_o     = B_i + 2 * t_w
    t_b     = _mm(inp["ud_base_thickness"])
    t_cu    = _mm(inp["cu_thickness"])
    lap_m   = _mm(inp["cu_overlap"])         # m  overlap of CU below UD top
    gamma_c = inp["gamma_c"]
    gamma_DL = inp["gamma_DL"]
    gamma_LL = inp["gamma_LL"]
    L_seg    = inp["ud_length"]
    P_wheel  = inp["wheel_load"]

    # ── Wall self-weight ──────────────────────────────────────────────────────
    W_wall = gamma_c * H_wall * t_w   # kN/m

    steps.append(CalcStep(
        symbol      = "W_wall",
        description = "Berat sendiri dinding / Wall self-weight",
        formula     = r"W_{wall} = \gamma_c \cdot H_{wall} \cdot t_w",
        substitution= f"{gamma_c}×{H_wall:.3f}×{t_w:.3f}",
        result      = W_wall,
        unit        = "kN/m",
        code_ref    = "SNI 1727:2020 §3.1",
    ))

    # ── Wheel load on CU: concentrated + distributed ──────────────────────────
    # CU midspan: P_wheel (one wheel) at centre.
    # Simple beam reaction from concentrated load at centre:
    R_wheel_unfact = P_wheel / 2      # per wall, per metre width of CU
    # Distributed dead: already in cu_loads.R_cu_unfactored
    # Separate to apply different load factors:
    R_dead_unfact  = (cu_loads.w_dead + cu_loads.w_soil) * B_o / 2
    R_live_unfact  = cu_loads.w_live * B_o / 2 + R_wheel_unfact

    R_factored = gamma_DL * R_dead_unfact + gamma_LL * R_live_unfact

    steps.append(CalcStep(
        symbol      = "R_wall",
        description = "Reaksi dinding dari beban di CU (terfaktor) / Factored wall reaction from CU loads",
        formula     = r"R_u = \gamma_{DL} \cdot R_{DL} + \gamma_{LL} \cdot R_{LL}",
        substitution= f"{gamma_DL}×{R_dead_unfact:.3f} + {gamma_LL}×{R_live_unfact:.3f}",
        result      = R_factored,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Eccentricity of axial load ─────────────────────────────────────────────
    # CU notch rests at inner face → reaction acts at inner-quarter of wall:
    # e = t_w/4 from wall centroid (conservative)
    e_axial = t_w / 4     # m (positive = toward interior)

    steps.append(CalcStep(
        symbol      = "e_N",
        description = "Eksentrisitas beban aksial dari CU terhadap sumbu dinding / Axial load eccentricity from CU",
        formula     = r"e_N = t_w / 4",
        substitution= f"{t_w:.3f} / 4",
        result      = e_axial,
        unit        = "m",
        code_ref    = "Engineering assumption — precast notch bearing; ACI 318-19 §22.8",
    ))

    # ── Factored axial at wall base ───────────────────────────────────────────
    Nu_base = R_factored + gamma_DL * W_wall

    steps.append(CalcStep(
        symbol      = "Nu,base",
        description = "Gaya aksial terfaktor di dasar dinding (kolom) / Factored axial at wall base",
        formula     = r"N_u = R_u + \gamma_{DL} \cdot W_{wall}",
        substitution= f"{R_factored:.3f} + {gamma_DL}×{W_wall:.3f}",
        result      = Nu_base,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Lateral load on wall (earth + surcharge — same as Cond 1 Phase A) ─────
    Mu_lat   = gamma_DL * lateral.F_earth * lateral.arm_earth + \
               gamma_LL * lateral.F_surcharge * lateral.arm_surcharge
    Vu_lat   = gamma_DL * lateral.F_earth + gamma_LL * lateral.F_surcharge

    steps.append(CalcStep(
        symbol      = "Mu,lat",
        description = "Momen lateral terfaktor di dasar (akibat tanah+surcharge) / Factored lateral moment at base",
        formula     = r"M_{u,lat} = \gamma_{DL} F_{earth} y_{earth} + \gamma_{LL} F_{sur} y_{sur}",
        substitution= f"{gamma_DL}×{lateral.F_earth:.3f}×{lateral.arm_earth:.3f} + {gamma_LL}×{lateral.F_surcharge:.3f}×{lateral.arm_surcharge:.3f}",
        result      = Mu_lat,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Total moment at wall base ─────────────────────────────────────────────
    # M_axial_eccentricity = Nu · e  (moment from off-centre axial)
    Mu_eccentric = R_factored * e_axial    # kN·m/m  (from CU reaction only)
    Mu_total_base = Mu_lat + Mu_eccentric

    steps.append(CalcStep(
        symbol      = "Mu,ecc",
        description = "Momen eksentrisitas aksial di dasar / Eccentric axial moment at base",
        formula     = r"M_{u,ecc} = R_u \cdot e_N",
        substitution= f"{R_factored:.3f} × {e_axial:.3f}",
        result      = Mu_eccentric,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.22.4; eccentricity from off-centre reaction",
    ))
    steps.append(CalcStep(
        symbol      = "Mu,base",
        description = "Momen total terfaktor di dasar dinding (Kondisi 2) / Total factored moment at wall base",
        formula     = r"M_{u,base} = M_{u,lat} + M_{u,ecc}",
        substitution= f"{Mu_lat:.3f} + {Mu_eccentric:.3f}",
        result      = Mu_total_base,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── CU: midspan and support forces ────────────────────────────────────────
    # CU = simply-supported beam, span = B_o
    # Total factored load wu per metre width on CU:
    wu_cu = cu_loads.q_total_factored     # kN/m²
    # Concentrated factored wheel at midspan (already included in wu via clt_idx):
    # For Condition 2, wheel IS at midspan:
    Pu_wheel = gamma_LL * P_wheel         # factored concentrated wheel load (kN)

    # CU midspan moment:
    # From distributed load: Mu_CU_dist = wu·B_o²/8
    # From concentrated load at midspan: Mu_CU_conc = Pu·B_o/4
    Mu_CU_dist = wu_cu * B_o ** 2 / 8
    Mu_CU_conc = Pu_wheel * B_o / 4
    Mu_CU_mid  = Mu_CU_dist + Mu_CU_conc

    # CU support shear:
    Vu_CU_dist = wu_cu * B_o / 2
    Vu_CU_conc = Pu_wheel / 2
    Vu_CU_sup  = Vu_CU_dist + Vu_CU_conc

    steps.append(CalcStep(
        symbol      = "Mu,CU",
        description = "Momen terfaktor tengah bentang CU / Factored midspan moment of CU",
        formula     = r"M_{u,CU} = \frac{w_u B_o^2}{8} + \frac{P_u B_o}{4}",
        substitution= f"{wu_cu:.3f}×{B_o:.3f}²/8 + {Pu_wheel:.3f}×{B_o:.3f}/4",
        result      = Mu_CU_mid,
        unit        = "kN·m/m",
        code_ref    = "Statics — simply supported beam",
    ))
    steps.append(CalcStep(
        symbol      = "Vu,CU",
        description = "Geser terfaktor di tumpuan CU / Factored shear at CU support",
        formula     = r"V_{u,CU} = \frac{w_u B_o}{2} + \frac{P_u}{2}",
        substitution= f"{wu_cu:.3f}×{B_o:.3f}/2 + {Pu_wheel:.3f}/2",
        result      = Vu_CU_sup,
        unit        = "kN/m",
        code_ref    = "Statics — simply supported beam",
    ))

    # ── Base slab ─────────────────────────────────────────────────────────────
    t_b = _mm(inp["ud_base_thickness"])
    w_u_slab = gamma_DL * gamma_c * t_b
    Mu_base_slab = w_u_slab * (B_i / 2) ** 2 / 2
    Vu_base_slab = w_u_slab * B_i / 2

    steps.append(CalcStep(
        symbol      = "Mu,slab",
        description = "Momen terfaktor dasar UD (Kondisi 2) / Factored moment at UD base slab midspan",
        formula     = r"M_{u,slab} = \frac{w_u (B_i/2)^2}{2}",
        substitution= f"{w_u_slab:.3f}×({B_i:.3f}/2)²/2",
        result      = Mu_base_slab,
        unit        = "kN·m/m",
        code_ref    = "Statics — one-way slab",
    ))

    return ForceResult(
        condition   = "Kondisi 2",
        wall_base   = SectionForces(
            Mu = Mu_total_base,
            Vu = Vu_lat,
            Nu = Nu_base,
        ),
        cu_midspan  = SectionForces(
            Mu = Mu_CU_mid,
            Vu = 0.0,
            Nu = 0.0,
        ),
        cu_support  = SectionForces(
            Mu = 0.0,
            Vu = Vu_CU_sup,
            Nu = 0.0,
        ),
        base_slab   = SectionForces(
            Mu = Mu_base_slab,
            Vu = Vu_base_slab,
            Nu = 0.0,
        ),
        lateral     = lateral,
        cu_loads    = cu_loads,
        gap_mm      = inp["gap_cu_ud"],
        delta_cant_mm = 0.0,      # not checked in Cond. 2
        gap_closed  = True,       # CU always engaged in Cond. 2
        steps       = steps,
        inp_echo    = inp,
    )


# =============================================================================
# CONDITION 3 — Open UD (No CU), Wheel Load at Distance
# =============================================================================
#
#  Wall = pure cantilever, fixed at base.
#  Only lateral earth + surcharge/Boussinesq. No CU.
#  Forces at wall base = maximum demand.
#  No gap check needed (no CU to close against).
# =============================================================================

def _cond3_forces(inp: dict, lateral: LateralLoads) -> ForceResult:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    steps: list[CalcStep] = []

    # ── Geometry ──────────────────────────────────────────────────────────────
    H_wall   = _mm(inp["ud_inner_height"])
    t_w      = _mm(inp["ud_wall_thickness"])
    B_i      = _mm(inp["ud_inner_width"])
    t_b      = _mm(inp["ud_base_thickness"])
    gamma_c  = inp["gamma_c"]
    gamma_DL = inp["gamma_DL"]
    gamma_LL = inp["gamma_LL"]

    # ── Wall self-weight ──────────────────────────────────────────────────────
    W_wall = gamma_c * H_wall * t_w

    steps.append(CalcStep(
        symbol      = "W_wall",
        description = "Berat sendiri dinding (Kondisi 3) / Wall self-weight",
        formula     = r"W_{wall} = \gamma_c \cdot H_{wall} \cdot t_w",
        substitution= f"{gamma_c}×{H_wall:.3f}×{t_w:.3f}",
        result      = W_wall,
        unit        = "kN/m",
        code_ref    = "SNI 1727:2020 §3.1",
    ))

    # Axial at base (no CU → only self-weight contributes)
    Nu_base = gamma_DL * W_wall

    steps.append(CalcStep(
        symbol      = "Nu,base",
        description = "Gaya aksial terfaktor di dasar (hanya berat dinding, tanpa CU) / Factored axial — wall DL only",
        formula     = r"N_u = \gamma_{DL} \cdot W_{wall}",
        substitution= f"{gamma_DL}×{W_wall:.3f}",
        result      = Nu_base,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Cantilever moments at base (pure cantilever) ──────────────────────────
    Mu_earth_serv = lateral.F_earth * lateral.arm_earth
    Mu_sur_serv   = lateral.F_surcharge * lateral.arm_surcharge

    Mu_base = gamma_DL * Mu_earth_serv + gamma_LL * Mu_sur_serv
    Vu_base = gamma_DL * lateral.F_earth + gamma_LL * lateral.F_surcharge

    steps.append(CalcStep(
        symbol      = "Mu,base",
        description = "Momen terfaktor di dasar kantilever murni / Factored cantilever moment at base",
        formula     = r"M_u = \gamma_{DL} M_{earth} + \gamma_{LL} M_{sur}",
        substitution= f"{gamma_DL}×{Mu_earth_serv:.3f} + {gamma_LL}×{Mu_sur_serv:.3f}",
        result      = Mu_base,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))
    steps.append(CalcStep(
        symbol      = "Vu,base",
        description = "Geser terfaktor di dasar kantilever / Factored shear at base",
        formula     = r"V_u = \gamma_{DL} F_{earth} + \gamma_{LL} F_{sur}",
        substitution= f"{gamma_DL}×{lateral.F_earth:.3f} + {gamma_LL}×{lateral.F_surcharge:.3f}",
        result      = Vu_base,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.5.3.1",
    ))

    # ── Base slab ─────────────────────────────────────────────────────────────
    w_u_slab = gamma_DL * gamma_c * t_b
    Mu_base_slab = w_u_slab * (B_i / 2) ** 2 / 2
    Vu_base_slab = w_u_slab * B_i / 2

    steps.append(CalcStep(
        symbol      = "Mu,slab",
        description = "Momen terfaktor dasar UD (Kondisi 3) / Factored UD base slab moment",
        formula     = r"M_{u,slab} = \frac{w_u(B_i/2)^2}{2}",
        substitution= f"{w_u_slab:.3f}×({B_i:.3f}/2)²/2",
        result      = Mu_base_slab,
        unit        = "kN·m/m",
        code_ref    = "Statics — one-way slab",
    ))

    return ForceResult(
        condition   = "Kondisi 3",
        wall_base   = SectionForces(
            Mu = Mu_base,
            Vu = Vu_base,
            Nu = Nu_base,
        ),
        # No CU sections in Condition 3
        cu_midspan  = None,
        cu_support  = None,
        base_slab   = SectionForces(
            Mu = Mu_base_slab,
            Vu = Vu_base_slab,
            Nu = 0.0,
        ),
        lateral     = lateral,
        cu_loads    = None,
        gap_mm      = 0.0,
        delta_cant_mm = 0.0,
        gap_closed  = False,
        steps       = steps,
        inp_echo    = inp,
    )


# =============================================================================
# PUBLIC ENTRY POINT
# =============================================================================

def run_load_analysis(inp: dict) -> ForceResult:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    """
    Master dispatcher.
    Reads inp["condition"], computes shared sub-results, calls the correct
    condition function, and returns a fully populated ForceResult.

    Usage (from 11_UDitch_CU.py tab_calc):
        from uditch.calc_engine import run_load_analysis
        result = run_load_analysis(st.session_state["input_data"])
        st.session_state["calc_results"] = result
    """
    condition = inp.get("condition", "Kondisi 1")

    # ── Lateral loads: common to all conditions ────────────────────────────────
    lateral = _loads_lateral(inp)

    # ── CU loads: only relevant for Cond. 1 & 2 ──────────────────────────────
    if condition in ("Kondisi 1", "Kondisi 2"):
        cu_loads = _loads_on_cu(inp)
    else:
        # Dummy zero CU loads for Cond. 3
        cu_loads = CULoads(
            w_dead=0, w_soil=0, w_live=0,
            q_total_unfactored=0, q_total_factored=0,
            R_cu_unfactored=0, R_cu_factored=0,
            steps=[],
        )

    # ── Dispatch to condition ──────────────────────────────────────────────────
    if condition == "Kondisi 1":
        result = _cond1_forces(inp, lateral, cu_loads)
    elif condition == "Kondisi 2":
        result = _cond2_forces(inp, lateral, cu_loads)
    else:
        result = _cond3_forces(inp, lateral)

    # ── Merge all steps in order: lateral → CU → condition ────────────────────
    all_steps = lateral.steps + cu_loads.steps + result.steps
    result.steps   = all_steps
    result.lateral = lateral
    if condition != "Kondisi 3":
        result.cu_loads = cu_loads

    return result


# =============================================================================
# QUICK SELF-TEST  (run: python -m uditch.calc_engine)
# =============================================================================
if __name__ == "__main__":
    import json

    _test_inp = {
        # Dimensions (mm)
        "ud_inner_width":    600,
        "ud_inner_height":   600,
        "ud_wall_thickness": 100,
        "ud_base_thickness": 120,
        "ud_length":         1.2,
        "cu_thickness":      100,
        "cu_overlap":         40,
        # Material
        "fc_prime":          30.0,
        "fy_main":          420.0,
        "gamma_c":           24.0,
        "cover_clear":        30,
        # Soil
        "gamma_s":           18.0,
        "phi_soil":          30.0,
        "cohesion":           0.0,
        "soil_fill_h":        0.0,
        "lat_method_idx":       0,   # surcharge
        # Loading
        "wheel_load":        50.0,
        "wheel_dist":         0.5,
        "udl_beside":        10.0,
        "pedestrian_load":    5.0,
        "cover_load_type_idx": 0,    # pedestrian
        "gamma_DL":           1.2,
        "gamma_LL":           1.6,
        "phi_flex":           0.90,
        "phi_shear_factor":   0.75,
        "phi_axial":          0.65,
        # Connection
        "gap_cu_ud":          20,
        "conn_type":           0,
        "conn_type_idx":       0,
        "dowel_dia":          12,
        "dowel_spacing":     200,
        "dowel_embed":       150,
        "dowel_mechanism_idx": 0,
        # Rebar
        "rebar_outer_dia":    13,
        "rebar_outer_spc":   150,
        "rebar_inner_dia":    13,
        "rebar_inner_spc":   150,
        "rebar_comp_dia":     10,
        "rebar_comp_spc":    200,
        "cu_rebar_bot_dia":   13,
        "cu_rebar_bot_spc":  150,
        "cu_rebar_top_dia":   10,
        "cu_rebar_top_spc":  200,
        "d_eff_outer":        55.0,
        "d_eff_inner":        55.0,
        "d_eff_cu":           55.0,
        "ud_outer_width":    800,
        "ud_outer_height":   720,
    }

    print("=" * 60)
    for cond in ("Kondisi 1", "Kondisi 2", "Kondisi 3"):
        _test_inp["condition"] = cond
        res = run_load_analysis(_test_inp)
        print(f"\n{'='*60}")
        print(f"  {cond}")
        print(f"{'='*60}")
        print(f"  Wall Base   Mu={res.wall_base.Mu:.3f} kN·m/m  "
              f"Vu={res.wall_base.Vu:.3f} kN/m  Nu={res.wall_base.Nu:.3f} kN/m")
        if res.cu_midspan:
            print(f"  CU Midspan  Mu={res.cu_midspan.Mu:.3f} kN·m/m  "
                  f"Vu={res.cu_midspan.Vu:.3f} kN/m")
        if res.cu_support:
            print(f"  CU Support  Vu={res.cu_support.Vu:.3f} kN/m")
        print(f"  Base Slab   Mu={res.base_slab.Mu:.3f} kN·m/m  "
              f"Vu={res.base_slab.Vu:.3f} kN/m")
        if cond == "Kondisi 1":
            print(f"  Gap: {res.gap_mm}mm | δ_cant: {res.delta_cant_mm:.2f}mm | "
                  f"Closed: {res.gap_closed}")
        print(f"  Calc steps: {len(res.steps)}")


# =============================================================================
# =============================================================================
#  PART 2 — SECTION CAPACITY & REINFORCEMENT DESIGN
# =============================================================================
# =============================================================================
#
# THEORY BASIS
# ─────────────────────────────────────────────────────────────────────────────
# All capacity calculations follow SNI 2847:2019 (equivalent to ACI 318-19).
#
# FLEXURE (SNI 2847:2019 Ps. 22.3 / ACI 318-19 §22.3)
# ── Single reinforcement ──────────────────────────────────────────────────────
#   Mn  = As·fy·(d − a/2)
#   a   = As·fy / (0.85·fc'·b)          [Whitney stress block depth]
#   φMn ≥ Mu
#
# ── Double reinforcement (tension As + compression As') ──────────────────────
#   c   = (As·fy − As'·fs') / (0.85·fc'·b1·b)   [neutral axis, iterate]
#   fs' = εs'·Es  (compression steel strain: εs' = εu·(c−d')/c)
#   fs' ≤ fy  (cap at yield)
#   Mn  = As·fy·(d − a/2) − As'·(fs'−0.85·fc')·(d−d')
#         [compression block already counted → subtract 0.85fc'·As']
#
# SHEAR  (SNI 2847:2019 Ps. 22.5 / ACI 318-19 §22.5)
# ── Concrete shear capacity ───────────────────────────────────────────────────
#   Vc  = [0.17λ√fc' + Nu/(6Ag)]·b·d     [Detailed method, Tabel 22.5.5.1]
#   (simplified: Vc = 0.17√fc'·b·d for beams; column form includes Nu)
# ── Steel shear capacity ──────────────────────────────────────────────────────
#   Vs  = Av·fyt·d / s
#   φ(Vc+Vs) ≥ Vu
#
# P-M INTERACTION  (SNI 2847:2019 Ps. 22.4 / ACI 318-19 §22.4)
# ── Four control points ───────────────────────────────────────────────────────
#   Pt. 0: Pure compression   Pn,max = 0.80·[0.85fc'(Ag−Ast)+Ast·fy]
#   Pt. 1: Balance point      cb = εu·d / (εu+εy);  ab = b1·cb
#   Pt. 2: Zero axial         Pn = 0,  Mn = φMn (pure flexure)
#   Pt. 3: Pure tension       Pn = −Ast·fy
#   Intermediate: sweep c from 0 → section depth
#
# ASYMMETRIC REINFORCEMENT (UD wall Condition 2)
# ── Outer face As,out; inner face As,in ──────────────────────────────────────
#   Both sets enter P-M calculation. Strain compatibility at each neutral
#   axis depth c:
#     εs,out = εu·(c−d,out)/c  (compression if positive)
#     εs,in  = εu·(d,in−c)/c   (tension if positive)
#   fs = min(|ε|·Es, fy)  with sign from strain direction.
#   Pn(c) = 0.85fc'·a·b + As,out·fs,out + As,in·fs,in  (sign = +comp,−ten)
#   Mn(c) = each force × distance to plastic centroid
#
# UNITS: N, mm, MPa throughout capacity functions.
# Conversion from kN·m/m  →  N·mm/mm:  × 1e6
# Conversion from kN/m    →  N/mm:     × 1e3
# =============================================================================

import math
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# NEW DATA CLASSES (Part 2)
# =============================================================================

@dataclass
class RebarLayout:
    """
    Reinforcement in ONE face of a rectangular section.
    All dimensions in mm.
    """
    dia:       float    # bar diameter (mm)
    spacing:   float    # bar spacing (mm)
    d_eff:     float    # effective depth from compression face (mm)
    As_per_m:  float    # steel area per metre width (mm²/m)  — derived


@dataclass
class SectionGeom:
    """
    Geometry of one rectangular section being checked.
    All in mm; b = 1000 mm (per-metre-width strip).
    """
    b:         float    # width (mm), typically 1000
    h:         float    # total depth (mm)
    d:         float    # effective depth to tension steel (mm)
    d_prime:   float    # cover to compression steel (mm)
    fc:        float    # f'c (MPa)
    fy:        float    # fy (MPa)
    fyt:       float    # fyt stirrup (MPa)
    beta1:     float    # Whitney b1
    label:     str      # "UD Wall" | "CU" | "Base Slab"


@dataclass
class CapacityResult:
    """
    Output of a single section capacity check.
    """
    label:         str
    # ── Applied ──────────────────────────────────────────────────────────────
    Mu_kNmm:       float    # factored moment (kN·m/m)
    Vu_kNm:        float    # factored shear  (kN/m)
    Nu_kNm:        float    # factored axial  (kN/m) compression +ve
    # ── Flexure ──────────────────────────────────────────────────────────────
    As_req_mm2:    float    # required tension steel (mm²/m)
    As_min_mm2:    float    # minimum steel (mm²/m)   SNI 2847:2019 Ps.9.6.1
    As_prov_mm2:   float    # provided (user rebar)
    phi_Mn_kNm:    float    # φMn  (kN·m/m)
    flexure_ok:    bool
    # ── Shear ────────────────────────────────────────────────────────────────
    phi_Vc_kNm:    float    # φVc  (kN/m)
    Vs_req_kNm:    float    # required Vs = Vu/φ − Vc
    Av_req_mm2:    float    # required Av/s (mm²/mm) — 0 if Vc sufficient
    stirrup_needed:bool
    phi_Vn_kNm:   float     # φ(Vc+Vs) with provided stirrups
    shear_ok:      bool
    # ── Calculation trace ────────────────────────────────────────────────────
    steps:         list      # list[CalcStep]


@dataclass
class PMPoint:
    """One point on the P-M interaction diagram."""
    Pn:   float    # kN/m   (nominal axial)
    Mn:   float    # kN·m/m (nominal moment)
    phi_Pn: float
    phi_Mn: float
    label:  str    # e.g. "Pure compression", "Balanced", "Pure flexure"


@dataclass
class PMCurve:
    """
    Full P-M interaction diagram for the UD wall acting as a column.
    Includes both nominal and design (φ-reduced) points.
    """
    points:        list[PMPoint]
    # Control points for quick reference
    Pn_max:        float
    Pb:            float
    Mb:            float
    Mn_pure:       float
    Pn_tension:    float
    # Applied demand point
    Nu_demand:     float
    Mu_demand:     float
    inside_curve:  bool     # True if demand is inside (safe)
    steps:         list     # list[CalcStep]


@dataclass
class DesignResult:
    """
    Top-level output of run_section_design().
    One CapacityResult per critical section + PM curve for Condition 2.
    """
    condition:      str
    wall_base_cap:  Optional[CapacityResult] = None
    wall_base_dbl:  Optional[CapacityResult] = None   # double-rebar check
    cu_midspan_cap: Optional[CapacityResult] = None
    cu_support_cap: Optional[CapacityResult] = None
    base_slab_cap:  Optional[CapacityResult] = None
    pm_curve:          Optional[PMCurve]        = None
    pm_curve_reversed: Optional[PMCurve]        = None   # momen berbalik (CU aktif)
    all_steps:         list = field(default_factory=list)

# =============================================================================
# PART 2 HELPERS
# =============================================================================

_Es   = 200_000.0   # MPa  steel elastic modulus
_εu   = 0.003       # SNI 2847:2019 Ps.22.2.2.1 — max concrete strain
_λ    = 1.0         # normal-weight concrete factor


def _beta1(fc_MPa: float) -> float:
    """Whitney stress-block factor b1. SNI 2847:2019 Ps.22.2.2.4.3."""
    return max(0.65, min(0.85, 0.85 - 0.05 * (fc_MPa - 28.0) / 7.0))


def _As_per_m(dia_mm: float, spacing_mm: float) -> float:
    """Steel area per metre width (mm²/m)."""
    return (math.pi / 4.0 * dia_mm ** 2) / spacing_mm * 1000.0


def _cover_to_centroid(cover_clear_mm: float, stirrup_dia: float,
                       main_dia: float) -> float:
    """Distance from face to bar centroid (mm)."""
    return cover_clear_mm + stirrup_dia + main_dia / 2.0


def _phi_flexure(εt: float) -> float:
    """
    Strength reduction factor φ for flexure/combined loading.
    SNI 2847:2019 Tabel 21.2.2 (linear transition).
    εt = net tensile strain at extreme tension steel.
    """
    if εt >= 0.005:
        return 0.90          # tension-controlled
    elif εt >= _εu:          # transition zone (εu=0.003 to 0.005)
        return 0.65 + (εt - _εu) / (0.005 - _εu) * 0.25
    else:
        return 0.65          # compression-controlled


def _Asmin_beam(fc_MPa: float, fy_MPa: float, b: float, d: float) -> float:
    """
    Minimum flexural steel for beams. SNI 2847:2019 Ps.9.6.1.2.
    As,min = max(0.25√fc'/fy, 1.4/fy) × b × d   [mm²]
    """
    rho_min = max(0.25 * math.sqrt(fc_MPa) / fy_MPa, 1.4 / fy_MPa)
    return rho_min * b * d


def _Asmin_wall(fc_MPa: float, fy_MPa: float, h_mm: float) -> float:
    """
    Minimum vertical reinforcement ratio for walls.
    SNI 2847:2019 Ps.11.6.1 — ρl,min = 0.0012 for deformed bar fy≥420 MPa.
    As,min = 0.0012 × b × h   (b=1000 mm)
    """
    rho_min = 0.0012 if fy_MPa >= 420 else 0.0015
    return rho_min * 1000.0 * h_mm


# =============================================================================
# SECTION GEOMETRY BUILDERS  (mm-based, b=1000/m-strip)
# =============================================================================

def _make_wall_section(inp: dict) -> SectionGeom:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    fc  = inp["fc_prime"]
    fy  = inp["fy_main"]
    fyt = inp["fy_shear"]
    t_w = inp["ud_wall_thickness"]          # mm
    cov = inp["cover_clear"]               # mm
    d   = inp["d_eff_outer"]              # mm  (tension at outer face)
    d_p = _cover_to_centroid(cov, 8, inp["rebar_comp_dia"])   # comp face centroid
    return SectionGeom(
        b=1000, h=t_w, d=d, d_prime=d_p,
        fc=fc, fy=fy, fyt=fyt,
        beta1=_beta1(fc), label="UD Wall",
    )


def _make_cu_section(inp: dict) -> SectionGeom:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    fc  = inp["fc_prime"]
    fy  = inp["fy_main"]
    fyt = inp["fy_shear"]
    t   = inp["cu_thickness"]              # mm
    d   = inp["d_eff_cu"]                 # mm
    d_p = _cover_to_centroid(inp["cover_clear"], 8, inp["cu_rebar_top_dia"])
    return SectionGeom(
        b=1000, h=t, d=d, d_prime=d_p,
        fc=fc, fy=fy, fyt=fyt,
        beta1=_beta1(fc), label="Cover CU",
    )


def _make_slab_section(inp: dict) -> SectionGeom:

    inp = _compat(inp)  # Tahap B: map new field names to legacy internals
    fc  = inp["fc_prime"]
    fy  = inp["fy_main"]
    fyt = inp["fy_shear"]
    t   = inp["ud_base_thickness"]         # mm
    cov = inp["cover_clear"]
    d   = t - _cover_to_centroid(cov, 8, inp["rebar_outer_dia"])
    d_p = _cover_to_centroid(cov, 8, inp["rebar_comp_dia"])
    return SectionGeom(
        b=1000, h=t, d=d, d_prime=d_p,
        fc=fc, fy=fy, fyt=fyt,
        beta1=_beta1(fc), label="UD Base Slab",
    )


# =============================================================================
# FLEXURAL CAPACITY  (single reinforcement → finds As,req)
# =============================================================================

def calc_capacity_flexure(
    sec:     SectionGeom,
    Mu_kNm:  float,          # factored moment  kN·m/m
    Nu_kNm:  float,          # factored axial   kN/m (+ve compression)
    As_prov: float,          # provided As      mm²/m  (user-defined, or 0)
    phi:     float,          # strength reduction factor φ
    member:  str = "wall",   # "wall" | "beam" | "slab"
) -> CapacityResult:
    """
    SNI 2847:2019 Ps.22.3 — Flexural capacity check.
    Handles:
      • As,required from Mu  (iterative Whitney block)
      • As,minimum
      • φMn with provided As
      • Tension-controlled check (εt ≥ 0.004 per SNI 2847 Ps.21.2.2)
    Returns CapacityResult (shear fields = 0; filled by calc_capacity_shear).
    """
    steps: list = []

    # Convert to N, mm  (consistent units for capacity)
    Mu_Nmm  = Mu_kNm * 1e6           # N·mm/m
    Nu_N    = Nu_kNm * 1e3           # N/m  (compression +ve)

    fc  = sec.fc
    fy  = sec.fy
    b   = sec.b     # 1000 mm
    d   = sec.d
    b1  = sec.beta1

    # ── b1 ────────────────────────────────────────────────────────────────────
    steps.append(CalcStep(
        symbol      = "b1",
        description = "Faktor blok tegangan Whitney / Whitney stress-block factor",
        formula     = r"\beta_1 = \max\!\left(0.65,\; 0.85 - 0.05\frac{f'_c-28}{7}\right)",
        substitution= f"max(0.65, 0.85−0.05×({fc}−28)/7)",
        result      = b1,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.22.2.2.4.3",
    ))

    # ── Minimum steel ─────────────────────────────────────────────────────────
    if member == "wall":
        As_min = _Asmin_wall(fc, fy, sec.h)
        asmin_ref = "SNI 2847:2019 Ps.11.6.1 (dinding, ρ_l,min=0.0012)"
        asmin_formula = r"A_{s,min} = 0.0012 \cdot b \cdot h"
        asmin_sub     = f"0.0012 × 1000 × {sec.h:.0f}"
    else:
        As_min = _Asmin_beam(fc, fy, b, d)
        asmin_ref = "SNI 2847:2019 Ps.9.6.1.2"
        asmin_formula = r"A_{s,min} = \max\!\left(\frac{0.25\sqrt{f'_c}}{f_y},\frac{1.4}{f_y}\right)\!b\,d"
        asmin_sub     = f"max(0.25√{fc}/{fy}, 1.4/{fy})×1000×{d:.1f}"

    steps.append(CalcStep(
        symbol      = "As,min",
        description = "Tulangan minimum / Minimum reinforcement",
        formula     = asmin_formula,
        substitution= asmin_sub,
        result      = As_min,
        unit        = "mm²/m",
        code_ref    = asmin_ref,
    ))

    # ── Required As from Mu ────────────────────────────────────────────────────
    # For combined N+M: shift effective Mu:
    # Treat axial as reducing/increasing moment arm. Simplified:
    # M_eff = Mu − Nu·(h/2−d')  [reduces tension demand for compression]
    # Then solve: Mu_eff = φ·As·fy·(d − a/2)  with a = As·fy/(0.85fc'b)  → quadratic
    e_shift = Nu_N * (sec.h / 2.0 - sec.d_prime) if Nu_kNm > 0 else 0.0
    Mu_eff  = max(Mu_Nmm - e_shift, 0.0)   # N·mm

    if Mu_eff > 0:
        # Quadratic: 0.85fc'b·a²/2 − As·fy·d + Mu_eff/φ = 0  [solve for a]
        # As·fy·(d − a/2) = Mu_eff/φ  → a²·(0.85fc'b/2)/(fy) − a·(d) + Mu_eff/(φ·fy/1) hmm
        # Direct quadratic in As:
        # Mu_eff = φ·As·fy·d − φ·(As·fy)²/(2·0.85·fc'·b)
        # Let x = As·fy: x²·φ/(2·0.85·fc'·b) − x·φ·d + Mu_eff = 0
        A_coef = phi / (2.0 * 0.85 * fc * b)
        B_coef = -phi * d
        C_coef = Mu_eff
        discriminant = B_coef**2 - 4*A_coef*C_coef
        if discriminant < 0:
            As_req = float("inf")   # section over-stressed
        else:
            x = (-B_coef - math.sqrt(discriminant)) / (2*A_coef)
            As_req = x / fy
    else:
        As_req = 0.0

    As_req = max(As_req, As_min)

    steps.append(CalcStep(
        symbol      = "As,req",
        description = "Tulangan tarik perlu dari Mu / Required tension steel from Mu",
        formula     = r"A_{s,req}: \; \phi A_s f_y \!\left(d - \frac{A_s f_y}{2 \cdot 0.85 f'_c b}\right) = M_u",
        substitution= f"φ={phi}, d={d:.1f}mm, fc'={fc}MPa, Mu_eff={Mu_eff/1e6:.3f}kN·m",
        result      = As_req,
        unit        = "mm²/m",
        code_ref    = "SNI 2847:2019 Ps.22.3.2; Whitney stress block",
    ))

    # ── φMn with PROVIDED As ─────────────────────────────────────────────────
    As_use = max(As_prov if As_prov > 0 else As_req, As_min)
    a      = As_use * fy / (0.85 * fc * b)
    c      = a / b1
    εt     = _εu * (d - c) / c
    phi_act = _phi_flexure(εt)   # actual φ from strain

    Mn_Nmm  = As_use * fy * (d - a / 2.0)         # N·mm/m
    phi_Mn  = phi_act * Mn_Nmm / 1e6              # kN·m/m

    steps.append(CalcStep(
        symbol      = "a",
        description = "Kedalaman blok tegangan ekivalen / Equivalent stress-block depth",
        formula     = r"a = \frac{A_s f_y}{0.85 f'_c b}",
        substitution= f"{As_use:.1f}×{fy} / (0.85×{fc}×{b})",
        result      = a,
        unit        = "mm",
        code_ref    = "SNI 2847:2019 Ps.22.2.2.4.1",
    ))
    steps.append(CalcStep(
        symbol      = "c",
        description = "Kedalaman sumbu netral / Neutral axis depth",
        formula     = r"c = a / \beta_1",
        substitution= f"{a:.3f} / {b1:.3f}",
        result      = c,
        unit        = "mm",
        code_ref    = "SNI 2847:2019 Ps.22.2.2.4.2",
    ))
    steps.append(CalcStep(
        symbol      = "εt",
        description = "Regangan tarik netto / Net tensile strain at tension steel",
        formula     = r"\varepsilon_t = \varepsilon_u \cdot \frac{d - c}{c}",
        substitution= f"0.003×({d:.1f}−{c:.3f})/{c:.3f}",
        result      = εt,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.21.2.2; Tabel 21.2.2",
    ))
    steps.append(CalcStep(
        symbol      = "φ (act)",
        description = "Faktor reduksi aktual dari regangan / Actual φ from strain",
        formula     = r"\phi = 0.65 + (\varepsilon_t - 0.003) \cdot \frac{0.25}{0.002} \; [\text{transition}]",
        substitution= f"εt = {εt:.4f}",
        result      = phi_act,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Tabel 21.2.2",
    ))
    steps.append(CalcStep(
        symbol      = "Mn",
        description = "Kuat lentur nominal / Nominal flexural strength",
        formula     = r"M_n = A_s f_y \!\left(d - \frac{a}{2}\right)",
        substitution= f"{As_use:.1f}×{fy}×({d:.1f}−{a/2:.2f})",
        result      = Mn_Nmm / 1e6,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.22.3.2",
    ))
    steps.append(CalcStep(
        symbol      = "φMn",
        description = "Kuat lentur rencana / Design flexural strength",
        formula     = r"\phi M_n = \phi \cdot M_n",
        substitution= f"{phi_act:.2f} × {Mn_Nmm/1e6:.3f}",
        result      = phi_Mn,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.21.2.1",
    ))

    flexure_ok = phi_Mn >= Mu_kNm

    steps.append(CalcStep(
        symbol      = "Cek Lentur",
        description = "Kontrol kapasitas lentur / Flexure adequacy check",
        formula     = r"\phi M_n \geq M_u \;?",
        substitution= f"{phi_Mn:.3f} ≥ {Mu_kNm:.3f} → {'✅ OK' if flexure_ok else '❌ NG'}",
        result      = 1.0 if flexure_ok else 0.0,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.9.5.1",
    ))

    return CapacityResult(
        label        = sec.label,
        Mu_kNmm      = Mu_kNm,
        Vu_kNm       = 0.0,
        Nu_kNm       = Nu_kNm,
        As_req_mm2   = As_req,
        As_min_mm2   = As_min,
        As_prov_mm2  = As_prov,
        phi_Mn_kNm   = phi_Mn,
        flexure_ok   = flexure_ok,
        phi_Vc_kNm   = 0.0,
        Vs_req_kNm   = 0.0,
        Av_req_mm2   = 0.0,
        stirrup_needed = False,
        phi_Vn_kNm   = 0.0,
        shear_ok     = True,
        steps        = steps,
    )


# =============================================================================
# SHEAR CAPACITY
# =============================================================================

def calc_capacity_shear(
    sec:         SectionGeom,
    Vu_kNm:      float,           # factored shear kN/m
    Nu_kNm:      float,           # axial kN/m (+ve compression)
    cap_flex:    CapacityResult,  # flexure result (used to retrieve As_use, a)
    phi_s:       float = 0.75,    # φ shear
    stirrup_dia: float = 8.0,     # mm  (assumed minimum)
    stirrup_spc: float = 200.0,   # mm  (initial spacing, user-defined later)
) -> CapacityResult:
    """
    SNI 2847:2019 Ps.22.5 — Shear capacity check.

    Vc  = [0.17λ√fc' + Nu/(6·Ag)] · b · d        [Table 22.5.5.1 eq.(a)]
    Vs  = Av · fyt · d / s
    φ(Vc + Vs) ≥ Vu
    """
    steps: list = []

    fc   = sec.fc
    fyt  = sec.fyt
    b    = sec.b      # 1000 mm
    d    = sec.d
    Ag   = b * sec.h  # gross area mm²/m

    # Convert Vu to N/mm (per mm width, same as N/m / 1000 × 1)
    Vu_N   = Vu_kNm * 1e3        # N/m
    Nu_N   = Nu_kNm * 1e3        # N/m  compression +ve

    # ── Vc (detailed method, SNI 2847:2019 Ps.22.5.5.1) ─────────────────────
    # Term 1: 0.17λ√fc'  [MPa]
    # Term 2: Nu/(6·Ag)  [MPa]
    # Vc = (term1 + term2) · b · d   [N/m  when b=1000 mm]
    term1 = 0.17 * _λ * math.sqrt(fc)
    term2 = Nu_N / (6.0 * Ag)         # N/m / mm² = MPa if N & mm consistent
    # Note: Nu_N is N/m, Ag is mm²/m → consistent as N·m⁻¹ / mm²·m⁻¹ = N/mm² = MPa ✓
    Vc_Npm = (term1 + term2) * b * d  # N/m

    steps.append(CalcStep(
        symbol      = "Vc",
        description = "Kuat geser beton / Concrete shear strength",
        formula     = r"V_c = \!\left(0.17\lambda\sqrt{f'_c} + \frac{N_u}{6A_g}\right)\!b\,d",
        substitution= f"(0.17×1.0×√{fc} + {Nu_N:.0f}/(6×{Ag:.0f}))×{b}×{d:.1f}",
        result      = Vc_Npm / 1e3,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Tabel 22.5.5.1 Pers.(a)",
    ))

    phi_Vc = phi_s * Vc_Npm / 1e3    # kN/m

    steps.append(CalcStep(
        symbol      = "φVc",
        description = "Kuat geser beton desain / Design concrete shear strength",
        formula     = r"\phi V_c = \phi \cdot V_c",
        substitution= f"{phi_s} × {Vc_Npm/1e3:.3f}",
        result      = phi_Vc,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.21.2.1",
    ))

    # ── Shear check & required Vs ─────────────────────────────────────────────
    stirrup_needed = Vu_N / 1e3 > phi_Vc

    if stirrup_needed:
        # Required Vs = Vu/φ − Vc
        Vs_req_Npm = Vu_N / phi_s - Vc_Npm    # N/m
        # Required Av/s = Vs / (fyt · d)
        Av_req_mm2 = Vs_req_Npm / (fyt * d)   # mm²/m per mm spacing = mm/m  hmm
        # Correct unit: Vs = Av/s · fyt · d  → Av/s = Vs/(fyt·d)  [mm²/mm = mm]
        # Per metre width strip: Av/s (mm²/mm) × (1000/spacing) gives bars/m
        # We report as mm²/m:  (Av/s) × 1000 mm = Av per 1000 mm
        Av_req_per_m = Av_req_mm2 * 1.0   # already consistent (N/m / MPa / mm = mm/m strip)
        # More explicitly: Av_req [mm²/m] = Vs[N/m] / (fyt[MPa] × d[mm])
        # = Vs[N/m] / (fyt[N/mm²] × d[mm]) = Vs·mm / (fyt·d·N) → mm²·N / (fyt·d·N) → mm²/m ✓
    else:
        Vs_req_Npm   = 0.0
        Av_req_per_m = 0.0

    steps.append(CalcStep(
        symbol      = "Cek Geser",
        description = "Apakah beton cukup menahan geser? / Is Vc sufficient?",
        formula     = r"\phi V_c \geq V_u \;?",
        substitution= f"{phi_Vc:.3f} ≥ {Vu_kNm:.3f} kN/m → {'Tidak perlu sengkang' if not stirrup_needed else 'PERLU sengkang'}",
        result      = 0.0 if stirrup_needed else 1.0,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.9.6.3.1",
    ))

    if stirrup_needed:
        steps.append(CalcStep(
            symbol      = "Vs,req",
            description = "Kuat geser tulangan perlu / Required steel shear strength",
            formula     = r"V_s = V_u/\phi - V_c",
            substitution= f"{Vu_kNm:.3f}/{phi_s} − {Vc_Npm/1e3:.3f}",
            result      = Vs_req_Npm / 1e3,
            unit        = "kN/m",
            code_ref    = "SNI 2847:2019 Ps.22.5.1.1",
        ))
        steps.append(CalcStep(
            symbol      = "Av,req/m",
            description = "Luas sengkang perlu per m lebar / Required stirrup area per m width",
            formula     = r"\frac{A_v}{s} = \frac{V_s}{f_{yt} \cdot d}  \;\Rightarrow\; A_v/m",
            substitution= f"{Vs_req_Npm:.0f} / ({fyt}×{d:.1f})",
            result      = Av_req_per_m,
            unit        = "mm²/m",
            code_ref    = "SNI 2847:2019 Ps.22.5.8.5.3",
        ))

        # ── Minimum stirrup check ──────────────────────────────────────────────
        # Av,min/s = max(0.062√fc'/fyt, 0.35/fyt) · b  per SNI 2847:2019 Ps.9.6.3.4
        avmin_per_mm = max(0.062 * math.sqrt(fc) / fyt, 0.35 / fyt) * b
        Av_min_per_m = avmin_per_mm * 1000   # mm²/m
        Av_req_per_m = max(Av_req_per_m, Av_min_per_m)

        steps.append(CalcStep(
            symbol      = "Av,min",
            description = "Sengkang minimum / Minimum stirrup area",
            formula     = r"A_{v,min}/s = \max\!\left(\frac{0.062\sqrt{f'_c}}{f_{yt}},\frac{0.35}{f_{yt}}\right)\!b",
            substitution= f"max(0.062√{fc}/{fyt}, 0.35/{fyt})×{b}",
            result      = Av_min_per_m,
            unit        = "mm²/m",
            code_ref    = "SNI 2847:2019 Ps.9.6.3.4",
        ))

    # ── φVn with provided stirrups ────────────────────────────────────────────
    # Use user-provided stirrups if any; otherwise use required
    Av_prov = _As_per_m(stirrup_dia, stirrup_spc)    # mm²/m
    Vs_prov = Av_prov * fyt * d / 1000.0              # kN/m  (Av[mm²/m]×fyt[MPa]×d[mm]/1e3)
    phi_Vn  = phi_s * (Vc_Npm / 1e3 + Vs_prov)

    steps.append(CalcStep(
        symbol      = "Av,prov",
        description = "Sengkang terpasang (awal ø8-200) / Provided stirrups",
        formula     = r"A_v = \frac{\pi d^2/4}{s} \times 1000",
        substitution= f"π×{stirrup_dia}²/4 / {stirrup_spc} × 1000",
        result      = Av_prov,
        unit        = "mm²/m",
        code_ref    = "—",
    ))
    steps.append(CalcStep(
        symbol      = "Vs,prov",
        description = "Kuat geser sengkang terpasang / Provided stirrup shear strength",
        formula     = r"V_s = \frac{A_v \cdot f_{yt} \cdot d}{1000}",
        substitution= f"{Av_prov:.1f}×{fyt}×{d:.1f}/1000",
        result      = Vs_prov,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.5.8.5.3",
    ))
    steps.append(CalcStep(
        symbol      = "φVn",
        description = "Kuat geser rencana / Design shear strength",
        formula     = r"\phi V_n = \phi(V_c + V_s)",
        substitution= f"{phi_s}×({Vc_Npm/1e3:.3f}+{Vs_prov:.3f})",
        result      = phi_Vn,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.5.1.1",
    ))

    shear_ok = phi_Vn >= Vu_kNm
    steps.append(CalcStep(
        symbol      = "Cek Geser Final",
        description = "Kontrol kapasitas geser akhir / Final shear check",
        formula     = r"\phi V_n \geq V_u \;?",
        substitution= f"{phi_Vn:.3f} ≥ {Vu_kNm:.3f} → {'✅ OK' if shear_ok else '❌ NG'}",
        result      = 1.0 if shear_ok else 0.0,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.9.5.1",
    ))

    # Merge shear steps into the flexure result and return combined
    combined         = cap_flex
    combined.Vu_kNm  = Vu_kNm
    combined.phi_Vc_kNm     = phi_Vc
    combined.Vs_req_kNm     = Vs_req_Npm / 1e3
    combined.Av_req_mm2     = Av_req_per_m
    combined.stirrup_needed = stirrup_needed
    combined.phi_Vn_kNm     = phi_Vn
    combined.shear_ok       = shear_ok
    combined.steps          = combined.steps + steps
    return combined


# =============================================================================
# DOUBLE REINFORCEMENT CAPACITY  (user-defined As + As')
# =============================================================================

def calc_double_rebar_capacity(
    sec:        SectionGeom,
    As_tension: float,      # mm²/m  — user-defined tension steel
    As_comp:    float,      # mm²/m  — user-defined compression steel
    Mu_kNm:     float,
    Nu_kNm:     float = 0.0,
    phi:        float = 0.90,
) -> CapacityResult:
    """
    SNI 2847:2019 Ps.22.3.3 — Doubly-reinforced section capacity.
    Iterates neutral axis depth c until force equilibrium.

    Compression steel stress:
        εs' = εu·(c − d')/c
        fs'  = min(εs'·Es, fy)   (capped at yield)

    Concrete compression:
        Cc  = 0.85·fc'·b1·c·b    [using a = b1·c]

    Force equilibrium (per m width):
        Cc + As'·(fs' − 0.85·fc') = As·fy    ← solve for c
    Moment about tension steel:
        Mn = Cc·(d − a/2) + As'·(fs'−0.85fc')·(d−d')
    """
    steps: list = []

    fc  = sec.fc
    fy  = sec.fy
    b   = sec.b
    d   = sec.d
    d_p = sec.d_prime
    b1  = sec.beta1

    steps.append(CalcStep(
        symbol      = "As (tarik)",
        description = "Tulangan tarik terpasang / Provided tension steel",
        formula     = r"A_s",
        substitution= f"dari input",
        result      = As_tension,
        unit        = "mm²/m",
        code_ref    = "—",
    ))
    steps.append(CalcStep(
        symbol      = "As' (tekan)",
        description = "Tulangan tekan terpasang / Provided compression steel",
        formula     = r"A'_s",
        substitution= f"dari input",
        result      = As_comp,
        unit        = "mm²/m",
        code_ref    = "—",
    ))

    # ── Iterative solve for c ─────────────────────────────────────────────────
    def _residual(c_try: float) -> float:
        a_try  = b1 * c_try
        eps_s  = _εu * (c_try - d_p) / c_try if c_try > 1e-6 else 0.0
        fs_p   = min(abs(eps_s) * _Es, fy) * (1 if eps_s >= 0 else -1)
        Cc     = 0.85 * fc * a_try * b
        Cs     = As_comp * (fs_p - 0.85 * fc)
        T      = As_tension * fy
        return Cc + Cs - T   # should = 0 at equilibrium

    # Bisect between c = 1 mm and c = sec.h
    c_lo, c_hi = 1.0, sec.h
    for _ in range(60):
        c_mid = (c_lo + c_hi) / 2.0
        if _residual(c_lo) * _residual(c_mid) < 0:
            c_hi = c_mid
        else:
            c_lo = c_mid
    c = (c_lo + c_hi) / 2.0

    a    = b1 * c
    εs_p = _εu * (c - d_p) / c
    fs_p = min(abs(εs_p) * _Es, fy) * (1 if εs_p >= 0 else -1)
    Cc   = 0.85 * fc * a * b                          # N/m
    Cs   = As_comp * (fs_p - 0.85 * fc)              # N/m
    T    = As_tension * fy                             # N/m
    εt   = _εu * (d - c) / c

    steps.append(CalcStep(
        symbol      = "c (iter)",
        description = "Kedalaman sumbu netral (iterasi kesetimbangan) / Neutral axis from equilibrium",
        formula     = r"0.85f'_c \beta_1 c \cdot b + A'_s(f'_s - 0.85f'_c) = A_s f_y",
        substitution= f"iterasi biseksi → c = {c:.3f} mm",
        result      = c,
        unit        = "mm",
        code_ref    = "SNI 2847:2019 Ps.22.3.3; ACI 318-19 §22.3.3",
    ))
    steps.append(CalcStep(
        symbol      = "a",
        description = "Kedalaman blok tekan / Compression block depth",
        formula     = r"a = \beta_1 \cdot c",
        substitution= f"{b1:.3f} × {c:.3f}",
        result      = a,
        unit        = "mm",
        code_ref    = "SNI 2847:2019 Ps.22.2.2.4",
    ))
    steps.append(CalcStep(
        symbol      = "εs'",
        description = "Regangan tulangan tekan / Compression steel strain",
        formula     = r"\varepsilon'_s = \varepsilon_u \cdot \frac{c - d'}{c}",
        substitution= f"0.003×({c:.3f}−{d_p:.1f})/{c:.3f}",
        result      = εs_p,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.22.2.1.2 (kompatibilitas regangan)",
    ))
    steps.append(CalcStep(
        symbol      = "fs'",
        description = "Tegangan tulangan tekan / Compression steel stress",
        formula     = r"f'_s = \min(\varepsilon'_s \cdot E_s,\; f_y)",
        substitution= f"min({abs(εs_p):.5f}×200000, {fy}) → {fs_p:.1f}",
        result      = fs_p,
        unit        = "MPa",
        code_ref    = "SNI 2847:2019 Ps.20.2.2.1",
    ))
    steps.append(CalcStep(
        symbol      = "Cc",
        description = "Gaya tekan blok beton / Concrete compression force",
        formula     = r"C_c = 0.85 f'_c \cdot a \cdot b",
        substitution= f"0.85×{fc}×{a:.3f}×{b}",
        result      = Cc / 1e3,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.2.2.4",
    ))
    steps.append(CalcStep(
        symbol      = "Cs",
        description = "Gaya tekan tulangan tekan (dikurangi beton) / Compression steel force (net)",
        formula     = r"C_s = A'_s (f'_s - 0.85 f'_c)",
        substitution= f"{As_comp:.1f}×({fs_p:.1f}−0.85×{fc})",
        result      = Cs / 1e3,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.3.3",
    ))

    # ── Moment about tension steel centroid ───────────────────────────────────
    Mn_Nmm = Cc * (d - a / 2.0) + Cs * (d - d_p)
    phi_act = _phi_flexure(εt)
    phi_Mn  = phi_act * Mn_Nmm / 1e6   # kN·m/m

    steps.append(CalcStep(
        symbol      = "εt",
        description = "Regangan tarik netto / Net tensile strain",
        formula     = r"\varepsilon_t = \varepsilon_u (d-c)/c",
        substitution= f"0.003×({d:.1f}−{c:.3f})/{c:.3f}",
        result      = εt,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.21.2.2",
    ))
    steps.append(CalcStep(
        symbol      = "Mn (double)",
        description = "Momen nominal tulangan rangkap / Nominal moment (doubly-reinforced)",
        formula     = r"M_n = C_c\!\left(d-\tfrac{a}{2}\right) + C_s(d-d')",
        substitution= f"({Cc/1e3:.2f}×({d:.1f}−{a/2:.2f}) + {Cs/1e3:.2f}×({d:.1f}−{d_p:.1f}))/1e6",
        result      = Mn_Nmm / 1e6,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.22.3.3",
    ))
    steps.append(CalcStep(
        symbol      = "φMn (double)",
        description = "Kuat lentur rencana tulangan rangkap / Design strength (doubly-reinforced)",
        formula     = r"\phi M_n",
        substitution= f"{phi_act:.2f}×{Mn_Nmm/1e6:.3f}",
        result      = phi_Mn,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.21.2.1",
    ))

    flexure_ok = phi_Mn >= Mu_kNm
    steps.append(CalcStep(
        symbol      = "Cek Lentur Rangkap",
        description = "Kontrol tulangan rangkap / Doubly-reinforced flexure check",
        formula     = r"\phi M_n \geq M_u",
        substitution= f"{phi_Mn:.3f} ≥ {Mu_kNm:.3f} → {'✅ OK' if flexure_ok else '❌ NG'}",
        result      = 1.0 if flexure_ok else 0.0,
        unit        = "—",
        code_ref    = "SNI 2847:2019 Ps.9.5.1",
    ))

    As_min = _Asmin_wall(fc, fy, sec.h)

    return CapacityResult(
        label        = sec.label + " (tulangan rangkap)",
        Mu_kNmm      = Mu_kNm,
        Vu_kNm       = 0.0,
        Nu_kNm       = Nu_kNm,
        As_req_mm2   = As_tension,    # user-defined; "req" not applicable here
        As_min_mm2   = As_min,
        As_prov_mm2  = As_tension,
        phi_Mn_kNm   = phi_Mn,
        flexure_ok   = flexure_ok,
        phi_Vc_kNm   = 0.0,
        Vs_req_kNm   = 0.0,
        Av_req_mm2   = 0.0,
        stirrup_needed = False,
        phi_Vn_kNm   = 0.0,
        shear_ok     = True,
        steps        = steps,
    )


# =============================================================================
# P-M INTERACTION DIAGRAM  — asymmetric reinforcement
# =============================================================================

def calc_pm_interaction(
    sec:          SectionGeom,
    As_out:       float,    # mm²/m  outer-face tension rebar  (Condition 2: outer = tension)
    As_in:        float,    # mm²/m  inner-face rebar
    d_out:        float,    # mm     effective depth to outer steel (from compression face)
    d_in:         float,    # mm     effective depth to inner steel (from compression face)
    d_prime_out:  float,    # mm     cover centroid — outer face (compression in +M zone)
    d_prime_in:   float,    # mm     cover centroid — inner face (compression in −M zone)
    phi_flex:     float = 0.90,
    phi_axial:    float = 0.65,
    n_sweep:      int   = 60,
) -> PMCurve:
    """
    Build the P-M interaction curve for the UD wall with ASYMMETRIC reinforcement.

    Sign convention (consistent with SNI 2847:2019 / ACI 318-19):
      Pn  > 0 → compression   Pn < 0 → tension
      Mn  always ≥ 0 (absolute value; direction shown by location of tension)

    The section is swept by varying neutral axis depth c from ≈0 → h.
    For each c, strain compatibility + Whitney block gives (Pn, Mn).

    Control points generated:
      P0:  Pure compression  (Pn,max)
      Pb:  Balanced  (εt = εy at outer tension steel)
      P2:  Zero axial  (pure flexure Mn)
      Pt:  Pure tension (Pn = −Ast·fy, Mn = 0)

    Phi-reduction:
      • Compression-controlled (εt ≤ 0.002):  φ = 0.65
      • Transition  (0.002 < εt < 0.005):     φ = linear 0.65 → 0.90
      • Tension-controlled (εt ≥ 0.005):      φ = 0.90
    """
    steps: list = []

    fc  = sec.fc
    fy  = sec.fy
    b   = sec.b    # 1000 mm
    h   = sec.h
    b1  = sec.beta1
    Ast = As_out + As_in   # total steel
    εy  = fy / _Es

    def _strain_and_stress(c_val: float, d_bar: float) -> tuple[float, float]:
        """Strain and stress in a bar at effective depth d_bar from compression face."""
        if c_val < 1e-9:
            return -_εu, -fy    # all tension
        eps = _εu * (c_val - d_bar) / c_val   # +ve = compression
        fs  = min(abs(eps) * _Es, fy) * (1 if eps >= 0 else -1)
        return eps, fs

    def _pn_mn(c_val: float) -> tuple[float, float, float]:
        """
        Given c (neutral axis from outer compression face),
        returns (Pn [N/m], Mn [N·mm/m], εt).
        Assumes outer face in compression for positive Pn (typical column).
        εt = strain at outer tension steel (= inner steel here since that is
        the tensile face when outer face is compressed).
        """
        a_val = min(b1 * c_val, h)

        # Outer steel (compression face side → compressive if c > d_prime_out)
        eps_out, fs_out = _strain_and_stress(c_val, d_prime_out)
        # Inner steel (tension face side)
        eps_in,  fs_in  = _strain_and_stress(c_val, d_in)

        # Concrete compression block
        Cc = 0.85 * fc * a_val * b   # N/m

        # Steel forces (+ve = compression)
        Fs_out = As_out * fs_out     # N/m
        Fs_in  = As_in  * fs_in     # N/m  (negative = tension)

        # Axial  (compression +ve)
        Pn = Cc + Fs_out + Fs_in

        # Reference point = plastic centroid (≈ geometric centre for symmetric)
        # For asymmetric: use section mid-height h/2 as reference
        y_ref = h / 2.0   # mm from compression face

        # Moment about plastic centroid
        Mn = (Cc * (y_ref - a_val / 2.0) +
              Fs_out * (y_ref - d_prime_out) +
              Fs_in  * (y_ref - d_in))      # N·mm/m  (can be negative)

        # εt at the tension-steel face (inner steel = tension in this sweep)
        εt_val = abs(_εu * (d_in - c_val) / c_val) if c_val > 1e-6 else _εu

        return Pn, Mn, εt_val

    def _phi_col(εt_val: float) -> float:
        """φ for combined axial+flexure."""
        return _phi_flexure(εt_val)

    # ── Sweep c ──────────────────────────────────────────────────────────────
    curve_points: list[PMPoint] = []
    c_values = [i * h / n_sweep for i in range(1, n_sweep + 1)]

    for c_val in c_values:
        Pn, Mn, εt = _pn_mn(c_val)
        phi = _phi_col(εt)
        # Cap Pn at Pn,max (SNI 2847:2019 Ps.22.4.2.1)
        Pn_max = 0.80 * (0.85 * fc * (b * h - Ast) + Ast * fy)   # compression
        Pn_cap = min(Pn, Pn_max)
        curve_points.append(PMPoint(
            Pn     = Pn_cap / 1e3,          # kN/m
            Mn     = abs(Mn) / 1e6,         # kN·m/m
            phi_Pn = phi * Pn_cap / 1e3,
            phi_Mn = phi * abs(Mn) / 1e6,
            label  = f"c={c_val:.1f}mm",
        ))

    # ── Control points ────────────────────────────────────────────────────────

    # Pt 0: Pure compression (c → ∞ → whole section in compression)
    Pn_max_val = 0.80 * (0.85 * fc * (b * h - Ast) + Ast * fy)   # N/m
    phi_Pmax   = phi_axial   # compression-controlled φ
    pt0 = PMPoint(
        Pn=Pn_max_val/1e3, Mn=0.0,
        phi_Pn=phi_Pmax*Pn_max_val/1e3, phi_Mn=0.0,
        label="Pure Compression (Pn,max)"
    )
    steps.append(CalcStep(
        symbol      = "Pn,max",
        description = "Kuat tekan aksial maksimum / Maximum axial compression strength",
        formula     = r"P_{n,max} = 0.80[0.85f'_c(A_g - A_{st}) + A_{st}f_y]",
        substitution= f"0.80×[0.85×{fc}×({b*h:.0f}−{Ast:.1f})+{Ast:.1f}×{fy}]",
        result      = Pn_max_val / 1e3,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.4.2.1",
    ))

    # Pt Balanced: εt = εy at inner (tension) steel
    # cb = εu·d_in / (εu + εy)
    cb = _εu * d_in / (_εu + εy)
    Pn_b, Mn_b, εt_b = _pn_mn(cb)
    phi_b  = _phi_col(εt_b)
    pt_bal = PMPoint(
        Pn=Pn_b/1e3, Mn=abs(Mn_b)/1e6,
        phi_Pn=phi_b*Pn_b/1e3, phi_Mn=phi_b*abs(Mn_b)/1e6,
        label="Balanced Point"
    )
    steps.append(CalcStep(
        symbol      = "cb",
        description = "Kedalaman sumbu netral saat kondisi seimbang / Balanced neutral axis",
        formula     = r"c_b = \frac{\varepsilon_u \cdot d_{in}}{\varepsilon_u + \varepsilon_y}",
        substitution= f"0.003×{d_in:.1f} / (0.003+{εy:.5f})",
        result      = cb,
        unit        = "mm",
        code_ref    = "SNI 2847:2019 Ps.22.3.4; ACI 318 R22.3.4",
    ))
    steps.append(CalcStep(
        symbol      = "Pb",
        description = "Gaya aksial saat kondisi seimbang / Balanced axial force",
        formula     = r"P_b = f(c_b)",
        substitution= f"c_b={cb:.2f}mm → Pn={Pn_b/1e3:.3f}kN/m",
        result      = Pn_b / 1e3,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.3.4",
    ))
    steps.append(CalcStep(
        symbol      = "Mb",
        description = "Momen saat kondisi seimbang / Balanced moment",
        formula     = r"M_b = f(c_b)",
        substitution= f"c_b={cb:.2f}mm → Mn={abs(Mn_b)/1e6:.3f}kN·m/m",
        result      = abs(Mn_b) / 1e6,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.22.3.4",
    ))

    # Pt 2: Pure flexure (Pn = 0) — bisect c
    def _pn_zero_residual(c_try):
        pn, _, _ = _pn_mn(c_try)
        return pn

    c_lo2, c_hi2 = 0.5, h
    for _ in range(60):
        c_m2 = (c_lo2 + c_hi2) / 2.0
        if _pn_zero_residual(c_lo2) * _pn_zero_residual(c_m2) < 0:
            c_hi2 = c_m2
        else:
            c_lo2 = c_m2
    c_pure = (c_lo2 + c_hi2) / 2.0
    _, Mn_pure_N, εt_pure = _pn_mn(c_pure)
    phi_pure = _phi_col(εt_pure)
    pt_pure_flex = PMPoint(
        Pn=0.0, Mn=abs(Mn_pure_N)/1e6,
        phi_Pn=0.0, phi_Mn=phi_pure*abs(Mn_pure_N)/1e6,
        label="Pure Flexure (Pn=0)"
    )
    steps.append(CalcStep(
        symbol      = "Mn,pure",
        description = "Momen lentur murni (Pn=0) / Pure flexural moment at zero axial",
        formula     = r"M_n \text{ saat } P_n=0 \text{ (iterasi)}",
        substitution= f"biseksi c → c={c_pure:.2f}mm → Mn={abs(Mn_pure_N)/1e6:.3f}kN·m/m",
        result      = abs(Mn_pure_N) / 1e6,
        unit        = "kN·m/m",
        code_ref    = "SNI 2847:2019 Ps.22.3",
    ))

    # Pt 3: Pure tension
    Pn_tension = -(As_out + As_in) * fy    # N/m
    phi_tension = phi_flex
    pt_tension = PMPoint(
        Pn=Pn_tension/1e3, Mn=0.0,
        phi_Pn=phi_tension*Pn_tension/1e3, phi_Mn=0.0,
        label="Pure Tension"
    )
    steps.append(CalcStep(
        symbol      = "Pn,tension",
        description = "Kuat tarik aksial / Pure tension capacity",
        formula     = r"P_{n,t} = -(A_{s,out}+A_{s,in}) \cdot f_y",
        substitution= f"−({As_out:.1f}+{As_in:.1f})×{fy}",
        result      = Pn_tension / 1e3,
        unit        = "kN/m",
        code_ref    = "SNI 2847:2019 Ps.22.4.3",
    ))

    # ── Assemble ordered curve: tension → zero N → balanced → Pn,max ─────────
    # Sort sweep by Pn ascending (most tension first)
    curve_points.sort(key=lambda p: p.Pn)
    # Insert control points in order
    all_pts = [pt_tension] + curve_points + [pt0]

    return PMCurve(
        points      = all_pts,
        Pn_max      = Pn_max_val / 1e3,
        Pb          = Pn_b / 1e3,
        Mb          = abs(Mn_b) / 1e6,
        Mn_pure     = abs(Mn_pure_N) / 1e6,
        Pn_tension  = Pn_tension / 1e3,
        # Demand set later by run_section_design
        Nu_demand   = 0.0,
        Mu_demand   = 0.0,
        inside_curve= True,
        steps       = steps,
    )


def _check_demand_on_pm(pm: PMCurve, Nu_kNm: float, Mu_kNm: float) -> PMCurve:
    """
    Mark the demand point on the P-M curve and determine if it is inside.
    Uses piecewise linear polygon check (ray-casting from Mn axis).
    """
    pm.Nu_demand = Nu_kNm
    pm.Mu_demand = Mu_kNm

    # Build φ-reduced polygon from sorted phi_Pn, phi_Mn
    pts = [(p.phi_Mn, p.phi_Pn) for p in pm.points]

    # Point-in-polygon (ray cast from (Mu, Nu) in x=Mn, y=Pn plane)
    n = len(pts)
    inside = False
    x, y = Mu_kNm, Nu_kNm
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    pm.inside_curve = inside
    return pm


# =============================================================================
# MASTER DESIGN RUNNER
# =============================================================================

def run_section_design(
    force_result: "ForceResult",
    inp:          dict,
) -> DesignResult:
    """
    Given ForceResult from run_load_analysis() and the raw inp dict,
    runs every required capacity check and returns a DesignResult.

    Condition 1 & 3: wall base (flexure + shear + double-rebar)
    Condition 2:     wall base + P-M curve + CU midspan + CU support
    All:             base slab
    """
    condition = force_result.condition
    all_steps: list = []
    inp = _compat(inp)   # Tahap B: map new field names

    # ── Convenience ──────────────────────────────────────────────────────────
    phi_f  = inp.get("phi_flex",         inp.get("phi_flexure", 0.90))
    phi_s  = inp.get("phi_shear_factor", inp.get("phi_shear_f", 0.75))
    phi_a  = inp.get("phi_axial",        inp.get("phi_axial_f", 0.65))

    # ── Build sections ────────────────────────────────────────────────────────
    wall_sec  = _make_wall_section(inp)
    cu_sec    = _make_cu_section(inp)
    slab_sec  = _make_slab_section(inp)

    # ── Rebar areas (provided) ────────────────────────────────────────────────
    As_outer  = _As_per_m(inp["rebar_outer_dia"], inp["rebar_outer_spc"])
    As_inner  = _As_per_m(inp["rebar_inner_dia"], inp["rebar_inner_spc"])
    As_comp   = _As_per_m(inp["rebar_comp_dia"],  inp["rebar_comp_spc"])
    As_cu_bot = _As_per_m(inp["cu_rebar_bot_dia"],inp["cu_rebar_bot_spc"])
    As_cu_top = _As_per_m(inp["cu_rebar_top_dia"],inp["cu_rebar_top_spc"])

    result = DesignResult(condition=condition)

    # ── Wall Base ─────────────────────────────────────────────────────────────
    wb = force_result.wall_base
    if wb is not None:
        # Flexure (single rebar — outer tension)
        cap_f = calc_capacity_flexure(
            sec     = wall_sec,
            Mu_kNm  = wb.Mu,
            Nu_kNm  = wb.Nu,
            As_prov = As_outer,
            phi     = phi_f,
            member  = "wall",
        )
        # Shear
        cap_fs = calc_capacity_shear(
            sec         = wall_sec,
            Vu_kNm      = wb.Vu,
            Nu_kNm      = wb.Nu,
            cap_flex    = cap_f,
            phi_s       = phi_s,
        )
        result.wall_base_cap = cap_fs
        all_steps += cap_fs.steps

        # Double reinforcement check (outer tension + comp rebar)
        cap_dbl = calc_double_rebar_capacity(
            sec        = wall_sec,
            As_tension = As_outer,
            As_comp    = As_comp,
            Mu_kNm     = wb.Mu,
            Nu_kNm     = wb.Nu,
            phi        = phi_f,
        )
        result.wall_base_dbl = cap_dbl
        all_steps += cap_dbl.steps

    # ── Condition 2: P-M curve + CU sections ─────────────────────────────────
    if condition == "Kondisi 2":
        d_out   = inp["d_eff_outer"]
        d_in    = inp["d_eff_inner"]
        cov     = inp["cover_clear"]

        d_prime_out = _cover_to_centroid(cov, 8, inp["rebar_comp_dia"])
        d_prime_in  = d_prime_out  # symmetric cover both faces

        pm = calc_pm_interaction(
            sec         = wall_sec,
            As_out      = As_outer,
            As_in       = As_inner,
            d_out       = d_out,
            d_in        = d_in,
            d_prime_out = d_prime_out,
            d_prime_in  = d_prime_in,
            phi_flex    = phi_f,
            phi_axial   = phi_a,
        )
        # Check demand
        if wb is not None:
            pm = _check_demand_on_pm(pm, Nu_kNm=wb.Nu, Mu_kNm=wb.Mu)
            pm.steps.append(CalcStep(
                symbol      = "Cek P-M",
                description = "Kontrol titik beban pada diagram interaksi / Demand vs P-M curve",
                formula     = r"(M_u, N_u) \in \phi P\text{-}M \;?",
                substitution= f"Nu={wb.Nu:.3f}kN/m, Mu={wb.Mu:.3f}kN·m/m → {'✅ Dalam kurva (OK)' if pm.inside_curve else '❌ Di luar kurva (NG)'}",
                result      = 1.0 if pm.inside_curve else 0.0,
                unit        = "—",
                code_ref    = "SNI 2847:2019 Ps.22.4; Diagram interaksi kolom",
            ))
        result.pm_curve = pm
        all_steps += pm.steps

        # P-M kurva kedua: momen berbalik (zona atas, CU aktif)
        pm_rev = calc_pm_interaction(
            sec         = wall_sec,
            As_out      = As_inner,     # ← DITUKAR
            As_in       = As_outer,     # ← DITUKAR
            d_out       = d_in,
            d_in        = d_out,
            d_prime_out = d_prime_in,
            d_prime_in  = d_prime_out,
            phi_flex    = phi_f,
            phi_axial   = phi_a,
        )
        wt = force_result.wall_top
        Mu_top = abs(wt.Mu) if (wt and wt.Mu != 0) else (wb.Mu if wb else 0.0)
        Nu_top = wt.Nu if wt else (wb.Nu if wb else 0.0)
        pm_rev = _check_demand_on_pm(pm_rev, Nu_kNm=Nu_top, Mu_kNm=Mu_top)
        result.pm_curve_reversed = pm_rev
        all_steps += pm_rev.steps

        # CU midspan
        cms = force_result.cu_midspan
        if cms is not None:
            cap_cu_f = calc_capacity_flexure(
                sec=cu_sec, Mu_kNm=cms.Mu, Nu_kNm=0.0,
                As_prov=As_cu_bot, phi=phi_f, member="beam",
            )
            cap_cu = calc_capacity_shear(
                sec=cu_sec, Vu_kNm=cms.Vu, Nu_kNm=0.0,
                cap_flex=cap_cu_f, phi_s=phi_s,
            )
            result.cu_midspan_cap = cap_cu
            all_steps += cap_cu.steps

        # CU support (shear only; Mu=0 at pin)
        css = force_result.cu_support
        if css is not None:
            # Dummy flexure (Mu≈0 at support)
            cap_cus_f = calc_capacity_flexure(
                sec=cu_sec, Mu_kNm=0.01, Nu_kNm=0.0,
                As_prov=As_cu_bot, phi=phi_f, member="beam",
            )
            cap_cus = calc_capacity_shear(
                sec=cu_sec, Vu_kNm=css.Vu, Nu_kNm=0.0,
                cap_flex=cap_cus_f, phi_s=phi_s,
            )
            result.cu_support_cap = cap_cus
            all_steps += cap_cus.steps

    # ── Base slab ─────────────────────────────────────────────────────────────
    bs = force_result.base_slab
    if bs is not None:
        cap_sl_f = calc_capacity_flexure(
            sec=slab_sec, Mu_kNm=bs.Mu, Nu_kNm=0.0,
            As_prov=As_outer, phi=phi_f, member="slab",
        )
        cap_sl = calc_capacity_shear(
            sec=slab_sec, Vu_kNm=bs.Vu, Nu_kNm=0.0,
            cap_flex=cap_sl_f, phi_s=phi_s,
        )
        result.base_slab_cap = cap_sl
        all_steps += cap_sl.steps

    result.all_steps = all_steps
    return result


# =============================================================================
# SELF-TEST PART 2  (append to existing __main__ block above)
# =============================================================================
def _self_test_part2() -> None:
    """Run Part 2 capacity checks on the standard test input."""
    _inp = {
        "ud_inner_width": 600, "ud_inner_height": 600,
        "ud_wall_thickness": 100, "ud_base_thickness": 120,
        "ud_length": 1.2, "cu_thickness": 100, "cu_overlap": 40,
        "fc_prime": 30.0, "fy_main": 420.0, "fy_shear": 240.0,
        "gamma_c": 24.0, "cover_clear": 30,
        "gamma_s": 18.0, "phi_soil": 30.0, "cohesion": 0.0,
        "soil_fill_h": 0.0, "lat_method_idx": 0,
        "wheel_load": 50.0, "wheel_dist": 0.5, "udl_beside": 10.0,
        "pedestrian_load": 5.0, "cover_load_type_idx": 0,
        "gamma_DL": 1.2, "gamma_LL": 1.6,
        "phi_flex": 0.90, "phi_shear_factor": 0.75, "phi_axial": 0.65,
        "gap_cu_ud": 20, "conn_type": 0, "conn_type_idx": 0,
        "dowel_dia": 12, "dowel_spacing": 200, "dowel_embed": 150,
        "dowel_mechanism_idx": 0,
        "rebar_outer_dia": 13, "rebar_outer_spc": 150,
        "rebar_inner_dia": 13, "rebar_inner_spc": 150,
        "rebar_comp_dia": 10,  "rebar_comp_spc": 200,
        "cu_rebar_bot_dia": 13, "cu_rebar_bot_spc": 150,
        "cu_rebar_top_dia": 10, "cu_rebar_top_spc": 200,
        "d_eff_outer": 55.0, "d_eff_inner": 55.0, "d_eff_cu": 55.0,
        "ud_outer_width": 800, "ud_outer_height": 720,
    }

    print("\n" + "=" * 60)
    print("  PART 2 — Section Capacity Self-Test")
    print("=" * 60)

    for cond in ("Kondisi 1", "Kondisi 2", "Kondisi 3"):
        _inp["condition"] = cond
        forces  = run_load_analysis(_inp)
        design  = run_section_design(forces, _inp)

        print(f"\n── {cond} ──────────────────────────────────────")
        wb = design.wall_base_cap
        if wb:
            print(f"  Wall Base  φMn={wb.phi_Mn_kNm:.3f} kN·m/m "
                  f"({'✅' if wb.flexure_ok else '❌'})  "
                  f"φVn={wb.phi_Vn_kNm:.3f} kN/m "
                  f"({'✅' if wb.shear_ok else '❌'})")
        wd = design.wall_base_dbl
        if wd:
            print(f"  Wall Dbl   φMn={wd.phi_Mn_kNm:.3f} kN·m/m "
                  f"({'✅' if wd.flexure_ok else '❌'})")
        if design.pm_curve:
            pm = design.pm_curve
            print(f"  PM Curve   Pn,max={pm.Pn_max:.1f} kN/m | "
                  f"Pb={pm.Pb:.1f} kN/m | Mb={pm.Mb:.2f} kN·m/m | "
                  f"Mn,pure={pm.Mn_pure:.2f} kN·m/m")
            print(f"  PM Check   Nu={pm.Nu_demand:.2f}, Mu={pm.Mu_demand:.2f} → "
                  f"{'✅ Inside' if pm.inside_curve else '❌ Outside'}")
        if design.cu_midspan_cap:
            cu = design.cu_midspan_cap
            print(f"  CU Midspan φMn={cu.phi_Mn_kNm:.3f} kN·m/m "
                  f"({'✅' if cu.flexure_ok else '❌'})")
        if design.cu_support_cap:
            cs = design.cu_support_cap
            print(f"  CU Support φVn={cs.phi_Vn_kNm:.3f} kN/m "
                  f"({'✅' if cs.shear_ok else '❌'})")
        sl = design.base_slab_cap
        if sl:
            print(f"  Base Slab  φMn={sl.phi_Mn_kNm:.3f} kN·m/m "
                  f"({'✅' if sl.flexure_ok else '❌'})  "
                  f"φVn={sl.phi_Vn_kNm:.3f} kN/m "
                  f"({'✅' if sl.shear_ok else '❌'})")
        total_steps = len(design.all_steps)
        print(f"  Total calc steps: {total_steps}")
