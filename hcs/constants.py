"""
HCS Design — Constants & Lookup Tables
=======================================
Reference : ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
            ASTM A416 (7-wire strand) | Indonesian manufacturer data (PC wire)
Units     : SI only (mm, kN, MPa)

Contents
--------
WIRE_PROPS    : PC Wire properties (Indonesian manufacturer, converted from kg/cm²)
STRAND_PROPS  : 7-Wire Strand properties (ASTM A416 Grade 270, Low-Relaxation)
PRESET_TABLE  : Standard Indonesian precast HCS section geometry presets
"""

# ─── PC Wire properties (Indonesian manufacturer data) ───────────────────────
# Converted: 1 kg/cm² = 0.09807 MPa
WIRE_PROPS = {
    5.0: {
        "area_mm2": 19.6,
        "fpu_MPa":  1618,    # 16500 kg/cm² × 0.09807
        "fpy_MPa":  1432,    # 14600 kg/cm² × 0.09807
        "Eps_MPa":  199_050  # 2,029,888 kg/cm² × 0.09807
    },
    7.0: {
        "area_mm2": 38.5,
        "fpu_MPa":  1515,    # 15450 kg/cm² × 0.09807
        "fpy_MPa":  1324,    # 13500 kg/cm² × 0.09807
        "Eps_MPa":  199_990  # 2,039,541 kg/cm² × 0.09807
    }
}

# ─── 7-Wire Strand properties — ASTM A416 Grade 270, Low-Relaxation ──────────
# Source: PCI Design Handbook Table 2.11.1
STRAND_PROPS = {
    "3/8 in  (d=8.4mm)":  {"d_mm": 8.4,  "area_mm2": 54.9,  "fpu_MPa": 1862, "fpy_MPa": 1675, "Eps_MPa": 196_500},
    "7/16 in (d=9.7mm)":  {"d_mm": 9.7,  "area_mm2": 74.2,  "fpu_MPa": 1860, "fpy_MPa": 1674, "Eps_MPa": 196_500},
    "1/2 in  (d=11.2mm)": {"d_mm": 11.2, "area_mm2": 98.7,  "fpu_MPa": 1862, "fpy_MPa": 1675, "Eps_MPa": 196_500},
    "3/5 in  (d=13.4mm)": {"d_mm": 13.4, "area_mm2": 140.0, "fpu_MPa": 1860, "fpy_MPa": 1674, "Eps_MPa": 196_500},
}

# ─── HCS Presets — standard Indonesian precast section data ───────────────────
PRESET_TABLE = {
    "Custom (manual input)": None,
    "HCS 120mm — Circular core": {
        "h": 120, "b_bottom": 1197, "b_top": 1185,
        "tf_top": 40, "tf_bot": 30,
        "core_shape": "Circular",
        "d_core": 60, "n_core": 9,
        "gap_side": 64, "gap_between": 70,
        "h_straight": 40, "h_taper": 20,
    },
    "HCS 150mm — Teardrop core": {
        "h": 150, "b_bottom": 1197, "b_top": 1185,
        "tf_top": 40, "tf_bot": 40,
        "core_shape": "Teardrop",
        "d_core": 80, "h_taper": 10, "n_core": 9,
        "gap_side": 66, "gap_between": 53,
        "h_straight": 40,
    },
    "HCS 200mm — Teardrop core": {
        "h": 200, "b_bottom": 1199, "b_top": 1187,
        "tf_top": 52, "tf_bot": 50,
        "core_shape": "Teardrop",
        "d_core": 80, "h_taper": 40, "n_core": 9,
        "gap_side": 67, "gap_between": 52,
        "h_straight": 40,
    },
    "HCS 250mm — Capsule core": {
        "h": 250, "b_bottom": 1199, "b_top": 1187,
        "tf_top": 52, "tf_bot": 50,
        "core_shape": "Capsule",
        "d_core": 80, "h_straight": 100, "n_core": 9,
        "gap_side": 67, "gap_between": 52,
        "h_taper": 20,
    },
}
