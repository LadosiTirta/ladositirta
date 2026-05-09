"""
footing/__init__.py
Isolated Spread Footing Design Package
"""
from .geometry import (
    compute_effective_depth, compute_footing_weights,
    compute_section_moduli, compute_eccentricity,
    corner_pressures, punching_critical_perimeter,
)
from .soil_pressure import (
    bearing_capacity_all_spt, bearing_capacity_sondir,
    check_soil_pressure, factored_pressure,
    METHOD_GUIDANCE, SELECTION_ADVICE,
)
from .punching_shear import check_punching_shear, check_one_way_shear
from .reinforcement import (
    flexure_design_full, compute_design_moment,
    reinforcement_schedule,
)
from .settlement import (
    immediate_settlement, consolidation_settlement,
    stress_increase_boussinesq, check_settlement,
    ALLOW_SETTLEMENT,
)
