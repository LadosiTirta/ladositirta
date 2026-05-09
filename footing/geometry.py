"""
footing/geometry.py
Geometry and effective depth calculations for isolated spread footing.
"""
import numpy as np


def compute_effective_depth(t_mm: float, cover_mm: float,
                             bar_x_mm: float, bar_y_mm: float):
    """
    Compute effective depths dx and dy.
    X-bars placed lower (larger d), Y-bars on top.

    Returns:
        dx (mm), dy (mm)
    """
    dx = t_mm - cover_mm - 0.5 * bar_x_mm
    dy = t_mm - cover_mm - bar_x_mm - 0.5 * bar_y_mm
    return dx, dy


def compute_footing_weights(B: float, L: float, t: float,
                             h_soil: float, gamma_c: float, gamma_s: float,
                             sloof_in_footing: bool = False):
    """
    Compute self-weight of footing and soil overburden.

    Parameters:
        B, L      : footing dimensions (m)
        t         : total footing thickness (m)
        h_soil    : soil thickness above top of footing (m)
        gamma_c   : unit weight of concrete (kN/m³)
        gamma_s   : unit weight of soil (kN/m³)
        sloof_in_footing: if True, sloof is embedded → less soil overburden

    Returns:
        W_foot (kN), W_soil (kN), detail dict
    """
    A = B * L
    W_foot = gamma_c * A * t

    # If sloof embedded in footing, soil above is partially displaced
    h_soil_eff = h_soil if not sloof_in_footing else max(0.0, h_soil - 0.3)
    W_soil = gamma_s * A * h_soil_eff

    detail = {
        "A_m2": A,
        "W_foot_kN": W_foot,
        "W_soil_kN": W_soil,
        "h_soil_eff_m": h_soil_eff,
        "gamma_c": gamma_c,
        "gamma_s": gamma_s,
        "B": B, "L": L, "t": t, "h_soil": h_soil,
    }
    return W_foot, W_soil, detail


def compute_section_moduli(B: float, L: float):
    """
    Section moduli of footing base area.
    Wx = modulus about X-axis (resists Msx → pressure varies in Y)
    Wy = modulus about Y-axis (resists Msy → pressure varies in X)

    Returns: A (m²), Wx (m³), Wy (m³)
    """
    A = B * L
    Wx = L * B**2 / 6   # resists moment about Y-axis → eccentricity in X
    Wy = B * L**2 / 6   # resists moment about X-axis → eccentricity in Y
    return A, Wx, Wy


def compute_eccentricity(sum_N: float, sum_Mx: float, sum_My: float):
    """
    Compute eccentricities.
    ex = ΣMy / ΣN  (eccentricity in X direction)
    ey = ΣMx / ΣN  (eccentricity in Y direction)
    """
    if abs(sum_N) < 1e-6:
        return 0.0, 0.0
    ex = sum_My / sum_N
    ey = sum_Mx / sum_N
    return ex, ey


def corner_pressures(sum_N: float, sum_Mx: float, sum_My: float,
                     A: float, Wx: float, Wy: float):
    """
    Soil pressure at 4 corners of footing.
    q = N/A ± Mx/Wy ± My/Wx

    Convention:
      Corner 1: (+x, +y)
      Corner 2: (-x, +y)
      Corner 3: (-x, -y)
      Corner 4: (+x, -y)

    Returns: q1, q2, q3, q4 (kN/m²)
    """
    q0 = sum_N / A
    dqx = sum_My / Wx   # variation due to My (eccentricity in X)
    dqy = sum_Mx / Wy   # variation due to Mx (eccentricity in Y)

    q1 = q0 + dqx + dqy   # +x, +y
    q2 = q0 - dqx + dqy   # -x, +y
    q3 = q0 - dqx - dqy   # -x, -y
    q4 = q0 + dqx - dqy   # +x, -y
    return q1, q2, q3, q4


def punching_critical_perimeter(bc: float, hc: float, d: float,
                                 B: float, L: float):
    """
    Critical perimeter for punching shear at d/2 from column face.
    Clipped to footing boundary.

    Returns: bo (mm), b_crit (m), h_crit (m)
    """
    b_crit = min(bc + d / 1000, B)
    h_crit = min(hc + d / 1000, L)
    bo = 2 * (b_crit + h_crit) * 1000   # convert to mm
    return bo, b_crit, h_crit


def punching_area_outside(B: float, L: float,
                           b_crit: float, h_crit: float):
    """
    Area outside critical perimeter (loaded area causing punching shear).
    """
    A_total = B * L
    A_crit = b_crit * h_crit
    return A_total - A_crit


def one_way_shear_width_and_arm(B: float, L: float,
                                  bc: float, hc: float, d_mm: float,
                                  col_x: float, col_y: float):
    """
    Critical section width and shear arm for one-way shear.
    d_mm: effective depth in mm → convert to m for geometry.

    Returns dict with values for X and Y directions.
    """
    d_m = d_mm / 1000

    # X-direction: shear across full width B, arm from col face to d
    # Critical section at d from face of column (in X-direction)
    x_face_right = col_x + hc / 2   # col face in X-dir (using hc for X span)
    x_face_left  = col_x - hc / 2

    arm_x_right = (L / 2 - x_face_right - d_m)
    arm_x_left  = (L / 2 + x_face_left - d_m)
    arm_x = max(arm_x_right, arm_x_left, 0.0)

    # Y-direction: shear across full length L, arm in Y
    y_face_top    = col_y + bc / 2
    y_face_bottom = col_y - bc / 2

    arm_y_top    = (B / 2 - y_face_top - d_m)
    arm_y_bottom = (B / 2 + y_face_bottom - d_m)
    arm_y = max(arm_y_top, arm_y_bottom, 0.0)

    return {
        "arm_x_m": arm_x,
        "arm_y_m": arm_y,
        "width_x_m": B,    # shear width for X-direction check = B
        "width_y_m": L,    # shear width for Y-direction check = L
    }
