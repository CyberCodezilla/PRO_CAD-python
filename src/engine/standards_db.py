"""
Engineering Standards Database for Mechanical Machine Elements.
Contains standardized lookup specifications for:
- Metric Coarse Pitch Screw Threads (ISO 261 / ISO 965-1)
- Hex Socket Head Cap Screw Counterbores (DIN 912 / ISO 4762 / DIN 74 Form H)
- 90-Degree & 82-Degree Countersink Screw Pockets (DIN 74 Form F / ISO 7721 / ASME B18.3)
- Parallel Drive Shaft Keyways (DIN 6885-1 Form A)
- Shaft Relief Grinding Undercuts (DIN 509 Type E)
- Standard Fastener Catalog for automated CAD Doctor assembly suggestions
"""

from typing import Dict, List, Any, Optional, Tuple

# Metric Coarse Pitch Screw Threads (ISO 261 / ISO 965-1)
METRIC_COARSE_THREADS: Dict[str, Dict[str, float]] = {
    "M3":  {"nominal_d": 3.0,  "pitch": 0.50, "tap_drill": 2.50, "clearance_close": 3.2, "clearance_med": 3.4},
    "M4":  {"nominal_d": 4.0,  "pitch": 0.70, "tap_drill": 3.30, "clearance_close": 4.3, "clearance_med": 4.5},
    "M5":  {"nominal_d": 5.0,  "pitch": 0.80, "tap_drill": 4.20, "clearance_close": 5.3, "clearance_med": 5.5},
    "M6":  {"nominal_d": 6.0,  "pitch": 1.00, "tap_drill": 5.00, "clearance_close": 6.4, "clearance_med": 6.6},
    "M8":  {"nominal_d": 8.0,  "pitch": 1.25, "tap_drill": 6.80, "clearance_close": 8.4, "clearance_med": 9.0},
    "M10": {"nominal_d": 10.0, "pitch": 1.50, "tap_drill": 8.50, "clearance_close": 10.5, "clearance_med": 11.0},
    "M12": {"nominal_d": 12.0, "pitch": 1.75, "tap_drill": 10.20, "clearance_close": 13.0, "clearance_med": 13.5},
    "M16": {"nominal_d": 16.0, "pitch": 2.00, "tap_drill": 14.00, "clearance_close": 17.0, "clearance_med": 17.5},
    "M20": {"nominal_d": 20.0, "pitch": 2.50, "tap_drill": 17.50, "clearance_close": 21.0, "clearance_med": 22.0},
}

# Hexagon Socket Head Cap Screw Counterbores (DIN 912 / ISO 4762 / DIN 74 Form H)
COUNTERBORE_TABLE: Dict[str, Dict[str, float]] = {
    "M3":  {"d_bore": 6.0,  "h_bore": 3.4, "d_pass": 3.4},
    "M4":  {"d_bore": 7.5,  "h_bore": 4.4, "d_pass": 4.5},
    "M5":  {"d_bore": 9.0,  "h_bore": 5.4, "d_pass": 5.5},
    "M6":  {"d_bore": 11.0, "h_bore": 6.5, "d_pass": 6.6},
    "M8":  {"d_bore": 14.0, "h_bore": 8.6, "d_pass": 9.0},
    "M10": {"d_bore": 17.5, "h_bore": 10.6, "d_pass": 11.0},
    "M12": {"d_bore": 20.0, "h_bore": 12.6, "d_pass": 13.5},
    "M16": {"d_bore": 26.0, "h_bore": 16.6, "d_pass": 17.5},
    "M20": {"d_bore": 33.0, "h_bore": 20.6, "d_pass": 22.0},
}

# 90-Degree & 82-Degree Countersunk Screw Pockets (DIN 74 Form F / ISO 7721 / ASME B18.3)
COUNTERSINK_TABLE: Dict[str, Dict[str, float]] = {
    "M3":  {"d_sink": 6.3,  "angle": 90.0, "d_pass": 3.4},
    "M4":  {"d_sink": 8.3,  "angle": 90.0, "d_pass": 4.5},
    "M5":  {"d_sink": 10.4, "angle": 90.0, "d_pass": 5.5},
    "M6":  {"d_sink": 12.4, "angle": 90.0, "d_pass": 6.6},
    "M8":  {"d_sink": 16.5, "angle": 90.0, "d_pass": 9.0},
    "M10": {"d_sink": 20.5, "angle": 90.0, "d_pass": 11.0},
}

# Parallel Drive Keyways for Metric Shafts (DIN 6885-1 Form A)
METRIC_KEYWAY_TABLE: List[Dict[str, float]] = [
    {"d_min": 6.0,  "d_max": 8.0,  "b": 2.0, "h": 2.0, "t1": 1.2, "t2": 1.0},
    {"d_min": 8.0,  "d_max": 10.0, "b": 3.0, "h": 3.0, "t1": 1.8, "t2": 1.4},
    {"d_min": 10.0, "d_max": 12.0, "b": 4.0, "h": 4.0, "t1": 2.5, "t2": 1.8},
    {"d_min": 12.0, "d_max": 17.0, "b": 5.0, "h": 5.0, "t1": 3.0, "t2": 2.3},
    {"d_min": 17.0, "d_max": 22.0, "b": 6.0, "h": 6.0, "t1": 3.5, "t2": 2.8},
    {"d_min": 22.0, "d_max": 30.0, "b": 8.0, "h": 7.0, "t1": 4.0, "t2": 3.3},
    {"d_min": 30.0, "d_max": 38.0, "b": 10.0, "h": 8.0, "t1": 5.0, "t2": 3.3},
    {"d_min": 38.0, "d_max": 44.0, "b": 12.0, "h": 8.0, "t1": 5.0, "t2": 3.3},
    {"d_min": 44.0, "d_max": 50.0, "b": 14.0, "h": 9.0, "t1": 5.5, "t2": 3.8},
]

# Shaft Relief Undercuts (DIN 509 Type E)
SHAFT_UNDERCUT_TABLE: List[Dict[str, float]] = [
    {"d_min": 1.6,  "d_max": 3.0,  "r": 0.2, "t1": 0.1},
    {"d_min": 3.0,  "d_max": 18.0, "r": 0.4, "t1": 0.2},
    {"d_min": 18.0, "d_max": 80.0, "r": 0.8, "t1": 0.3},
]

# Fastener Catalog
FASTENER_CATALOG: Dict[str, Dict[str, Any]] = {
    "DIN 912": {
        "name": "Hexagon Socket Head Cap Screw",
        "standard": "DIN 912 / ISO 4762",
        "head_type": "counterbore",
        "available_sizes": ["M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"]
    },
    "ISO 7721": {
        "name": "Countersunk Flat Head Screw",
        "standard": "ISO 7721 / DIN 7991",
        "head_type": "countersink",
        "available_sizes": ["M3", "M4", "M5", "M6", "M8", "M10"]
    },
    "ISO 4014": {
        "name": "Hexagon Head Bolt",
        "standard": "ISO 4014 / DIN 931",
        "head_type": "hex",
        "available_sizes": ["M6", "M8", "M10", "M12", "M16", "M20"]
    }
}


def lookup_metric_thread(major_d: float, tolerance: float = 0.25) -> Optional[Tuple[str, Dict[str, float]]]:
    """Find closest standard ISO 261 metric thread entry within tolerance"""
    for size_name, data in METRIC_COARSE_THREADS.items():
        if abs(major_d - data["nominal_d"]) <= tolerance:
            return size_name, data
    return None


def lookup_counterbore(d_bore: float, h_bore: float, tolerance: float = 0.4) -> Optional[Tuple[str, Dict[str, float]]]:
    """Find closest standard DIN 912 / ISO 4762 counterbore entry within tolerance"""
    for size_name, data in COUNTERBORE_TABLE.items():
        if abs(d_bore - data["d_bore"]) <= tolerance and abs(h_bore - data["h_bore"]) <= tolerance:
            return size_name, data
    return None


def lookup_countersink(d_sink: float, angle: float, tolerance: float = 0.4) -> Optional[Tuple[str, Dict[str, float]]]:
    """Find closest standard DIN 74 Form F / ISO 7721 countersink entry within tolerance"""
    for size_name, data in COUNTERSINK_TABLE.items():
        if abs(d_sink - data["d_sink"]) <= tolerance and abs(angle - data["angle"]) <= 3.0:
            return size_name, data
    return None


def lookup_shaft_keyway(d_shaft: float) -> Optional[Dict[str, float]]:
    """Find standard DIN 6885-1 Form A keyway dimensions for shaft diameter"""
    for entry in METRIC_KEYWAY_TABLE:
        if entry["d_min"] <= d_shaft <= entry["d_max"]:
            return entry
    return None
