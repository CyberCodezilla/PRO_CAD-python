"""
ISO 286-1 / ISO 286-2 System of Limits and Fits Database.
Provides fundamental deviation tables (in micrometers) and tolerance calculations
for standard engineering fits (e.g., H7/g6, H7/h6, H7/p6).
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional


# ISO 286-2 Hole Deviations in micrometers (um)
# Format: (d_min, d_max): {"EI": float, "ES": float}
ISO_HOLE_H7: Dict[Tuple[float, float], Dict[str, float]] = {
    (0.0, 3.0):    {"EI": 0.0, "ES": 10.0},
    (3.0, 6.0):    {"EI": 0.0, "ES": 12.0},
    (6.0, 10.0):   {"EI": 0.0, "ES": 15.0},
    (10.0, 18.0):  {"EI": 0.0, "ES": 18.0},
    (18.0, 30.0):  {"EI": 0.0, "ES": 21.0},
    (30.0, 50.0):  {"EI": 0.0, "ES": 25.0},
    (50.0, 80.0):  {"EI": 0.0, "ES": 30.0},
    (80.0, 120.0): {"EI": 0.0, "ES": 35.0},
    (120.0, 180.0): {"EI": 0.0, "ES": 40.0},
}

# ISO 286-2 Shaft Deviations in micrometers (um)
# g6: Precision sliding / running clearance fit
ISO_SHAFT_G6: Dict[Tuple[float, float], Dict[str, float]] = {
    (0.0, 3.0):    {"ei": -8.0,  "es": -2.0},
    (3.0, 6.0):    {"ei": -12.0, "es": -4.0},
    (6.0, 10.0):   {"ei": -14.0, "es": -5.0},
    (10.0, 18.0):  {"ei": -17.0, "es": -6.0},
    (18.0, 30.0):  {"ei": -20.0, "es": -7.0},
    (30.0, 50.0):  {"ei": -25.0, "es": -9.0},
    (50.0, 80.0):  {"ei": -29.0, "es": -10.0},
    (80.0, 120.0): {"ei": -34.0, "es": -12.0},
    (120.0, 180.0): {"ei": -39.0, "es": -14.0},
}

# h6: Exact location / key / close slide fit
ISO_SHAFT_H6: Dict[Tuple[float, float], Dict[str, float]] = {
    (0.0, 3.0):    {"ei": -6.0,  "es": 0.0},
    (3.0, 6.0):    {"ei": -8.0,  "es": 0.0},
    (6.0, 10.0):   {"ei": -9.0,  "es": 0.0},
    (10.0, 18.0):  {"ei": -11.0, "es": 0.0},
    (18.0, 30.0):  {"ei": -13.0, "es": 0.0},
    (30.0, 50.0):  {"ei": -16.0, "es": 0.0},
    (50.0, 80.0):  {"ei": -19.0, "es": 0.0},
    (80.0, 120.0): {"ei": -22.0, "es": 0.0},
    (120.0, 180.0): {"ei": -25.0, "es": 0.0},
}

# p6: Rigid press / permanent interference fit
ISO_SHAFT_P6: Dict[Tuple[float, float], Dict[str, float]] = {
    (0.0, 3.0):    {"ei": 6.0,   "es": 12.0},
    (3.0, 6.0):    {"ei": 12.0,  "es": 20.0},
    (6.0, 10.0):   {"ei": 15.0,  "es": 24.0},
    (10.0, 18.0):  {"ei": 18.0,  "es": 29.0},
    (18.0, 30.0):  {"ei": 22.0,  "es": 35.0},
    (30.0, 50.0):  {"ei": 26.0,  "es": 42.0},
    (50.0, 80.0):  {"ei": 32.0,  "es": 51.0},
    (80.0, 120.0): {"ei": 37.0,  "es": 59.0},
    (120.0, 180.0): {"ei": 43.0,  "es": 68.0},
}


@dataclass
class FitEvaluationResult:
    """Result of ISO 286 tolerance and fit calculation"""
    nominal_d: float
    fit_code: str
    hole_lower_limit: float
    hole_upper_limit: float
    shaft_lower_limit: float
    shaft_upper_limit: float
    min_clearance: float
    max_clearance: float
    min_interference: float
    max_interference: float
    category: str               # "CLEARANCE", "INTERFERENCE", "TRANSITION"
    is_interference: bool


def _lookup_table(table: Dict[Tuple[float, float], Dict[str, float]], d_nom: float) -> Optional[Dict[str, float]]:
    """Find deviation step containing nominal diameter d_nom"""
    for (d_min, d_max), devs in table.items():
        if d_min < d_nom <= d_max or (d_min == 0.0 and d_nom == 0.0):
            return devs
    return None


def evaluate_iso_fit(d_nom: float, fit_code: str = "H7/g6") -> FitEvaluationResult:
    """
    Evaluates ISO 286 limits and fits for a given nominal diameter and fit specification.
    Supports H7/g6, H7/h6, H7/p6.
    """
    parts = fit_code.strip().split('/')
    hole_code = parts[0].upper() if len(parts) > 0 else "H7"
    shaft_code = parts[1].lower() if len(parts) > 1 else "g6"

    # Hole lookup
    hole_devs = _lookup_table(ISO_HOLE_H7, d_nom) or {"EI": 0.0, "ES": 25.0}
    ei_hole_mm = hole_devs.get("EI", 0.0) / 1000.0
    es_hole_mm = hole_devs.get("ES", 25.0) / 1000.0

    hole_lower = d_nom + ei_hole_mm
    hole_upper = d_nom + es_hole_mm

    # Shaft lookup
    if shaft_code == "g6":
        shaft_devs = _lookup_table(ISO_SHAFT_G6, d_nom) or {"ei": -25.0, "es": -9.0}
    elif shaft_code == "h6":
        shaft_devs = _lookup_table(ISO_SHAFT_H6, d_nom) or {"ei": -16.0, "es": 0.0}
    elif shaft_code == "p6":
        shaft_devs = _lookup_table(ISO_SHAFT_P6, d_nom) or {"ei": 26.0, "es": 42.0}
    else:
        shaft_devs = _lookup_table(ISO_SHAFT_G6, d_nom) or {"ei": -25.0, "es": -9.0}

    ei_shaft_mm = shaft_devs.get("ei", 0.0) / 1000.0
    es_shaft_mm = shaft_devs.get("es", 0.0) / 1000.0

    shaft_lower = d_nom + ei_shaft_mm
    shaft_upper = d_nom + es_shaft_mm

    # Clearances and Interferences (in mm)
    max_clearance = round(hole_upper - shaft_lower, 6)
    min_clearance = round(hole_lower - shaft_upper, 6)
    max_interference = round(shaft_upper - hole_lower, 6)
    min_interference = round(shaft_lower - hole_upper, 6)

    if min_clearance > 0.0:
        category = "CLEARANCE"
        is_interference = False
    elif max_clearance < 0.0 or min_interference > 0.0:
        category = "INTERFERENCE"
        is_interference = True
    else:
        category = "TRANSITION"
        is_interference = False

    return FitEvaluationResult(
        nominal_d=d_nom,
        fit_code=fit_code,
        hole_lower_limit=round(hole_lower, 4),
        hole_upper_limit=round(hole_upper, 4),
        shaft_lower_limit=round(shaft_lower, 4),
        shaft_upper_limit=round(shaft_upper, 4),
        min_clearance=round(min_clearance, 4),
        max_clearance=round(max_clearance, 4),
        min_interference=round(max(0.0, min_interference), 4),
        max_interference=round(max(0.0, max_interference), 4),
        category=category,
        is_interference=is_interference
    )
