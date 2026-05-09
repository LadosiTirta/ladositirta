"""
footing_strip/geometry.py
Strip footing geometry helpers.
"""

def strip_section_moduli(B: float):
    """
    Section properties for a 1 m wide strip.
    Returns A (m²/m), Wx (m³/m) — modulus about X‑axis (resists moment about X).
    """
    A = B * 1.0      # per meter length
    Wx = 1.0 * B**2 / 6
    return A, Wx

def strip_corner_pressures(N_per_m: float, Mx_per_m: float, A: float, Wx: float):
    """
    Soil pressure at two edges of a strip footing (uniform across length).
    q = N/A ± Mx/Wx
    Returns: q_left, q_right (kN/m²)
    """
    q_avg = N_per_m / A
    delta = Mx_per_m / Wx
    q_left = q_avg - delta
    q_right = q_avg + delta
    return q_left, q_right
