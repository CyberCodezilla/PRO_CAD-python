"""
CAM Toolpath Generator & CNC Physics Engine.
Implements Feature-Based Machining (FBM), Tool Definitions,
and Speeds & Feeds Physics formulations conforming to ISO 6983-1.
"""

import math
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any


class ToolType(Enum):
    FLAT_ENDMILL = "FLAT_ENDMILL"
    BALL_ENDMILL = "BALL_ENDMILL"
    DRILL = "DRILL"
    TAP = "TAP"
    CHAMFER_MILL = "CHAMFER_MILL"
    FACE_MILL = "FACE_MILL"


class OperationType(Enum):
    FACING = "FACING"
    POCKET_ROUGH = "POCKET_ROUGH"
    POCKET_FINISH = "POCKET_FINISH"
    CONTOUR = "CONTOUR"
    DRILL = "DRILL"
    PECK = "PECK"
    TAP = "TAP"


@dataclass
class ToolDefinition:
    """CNC Tool Geometry and Parameters"""
    tool_no: int
    name: str
    tool_type: ToolType
    diameter: float                      # mm
    flute_length: float = 30.0           # mm
    overall_length: float = 75.0         # mm
    flutes: int = 3                      # Flute count Z_t
    max_rpm: float = 15000.0             # Spindle limit
    pitch: Optional[float] = None        # mm/rev (for taps)


@dataclass
class ToolpathSegment:
    """Individual CNC Motion Vector Segment"""
    g_code: str                          # "G00", "G01", "G02", "G03", "G81", "G83", "G84"
    start_pt: Tuple[float, float, float] # (X, Y, Z)
    end_pt: Tuple[float, float, float]   # (X, Y, Z)
    feed_rate: float = 0.0               # mm/min
    is_rapid: bool = False
    center_pt: Optional[Tuple[float, float, float]] = None # I, J, K or arc center
    q_peck: Optional[float] = None       # mm (for G83)
    r_plane: Optional[float] = None      # mm (for canned cycles)


@dataclass
class MachiningOperation:
    """Structured Machining Operation Sequence"""
    op_id: str
    name: str
    op_type: OperationType
    tool: ToolDefinition
    target_depth: float                  # mm
    stepover: float = 0.60               # Ratio of tool diameter (0.60 = 60%)
    stepdown: float = 3.0                # mm (axial depth of cut a_p)
    segments: List[ToolpathSegment] = field(default_factory=list)
    total_time_sec: float = 0.0
    spindle_rpm: float = 8000.0
    feed_xy: float = 1000.0
    feed_z: float = 300.0


# Standard Material Surface Speeds (Vc in m/min) for Carbide Tooling
MATERIAL_SURFACE_SPEEDS: Dict[str, float] = {
    "6061-T6 Aluminum": 250.0,
    "5052 Aluminum": 250.0,
    "Mild Steel (S235 / 1018)": 120.0,
    "Alloy Steel (4140 / 42CrMo4)": 80.0,
    "Cast Iron (EN-GJL-250)": 90.0,
    "Brass / Bronze (CuSn8)": 150.0,
}

# Standard Feed per Tooth (fz in mm/tooth)
STANDARD_CHIP_LOADS: Dict[OperationType, float] = {
    OperationType.FACING: 0.08,
    OperationType.POCKET_ROUGH: 0.04,
    OperationType.POCKET_FINISH: 0.025,
    OperationType.CONTOUR: 0.035,
    OperationType.DRILL: 0.05,
    OperationType.PECK: 0.04,
    OperationType.TAP: 1.0,              # Pitch-driven
}


def calculate_speeds_and_feeds(
    material: str,
    tool: ToolDefinition,
    op_type: OperationType = OperationType.POCKET_ROUGH,
    custom_fz: Optional[float] = None
) -> Tuple[float, float, float]:
    """
    Computes theoretical CNC machining parameters:
    - Spindle RPM: N = (1000.0 * V_c) / (pi * D_tool)
    - XY Cutting Feed: Feed_XY = N * f_z * Z_t
    - Z Plunge Feed: Feed_Z = 0.30 * Feed_XY
    - Rigid Tapping Feed: Feed_Tap = N * P
    """
    v_c = MATERIAL_SURFACE_SPEEDS.get(material, 150.0)

    # 1. Spindle RPM
    if tool.diameter > 0.0:
        spindle_rpm = (1000.0 * v_c) / (math.pi * tool.diameter)
    else:
        spindle_rpm = 1000.0

    # Clamp to machine/tool limits
    spindle_rpm = max(100.0, min(tool.max_rpm, spindle_rpm))

    # 2. Feed Rates
    if op_type == OperationType.TAP and tool.pitch:
        # Rigid Tapping: F = N * P (spindle is geared down for tapping)
        tap_rpm = min(400.0, spindle_rpm)
        feed_xy = tap_rpm * tool.pitch
        feed_z = feed_xy
        return (round(tap_rpm, 2), round(feed_xy, 2), round(feed_z, 2))

    fz = custom_fz if custom_fz is not None else STANDARD_CHIP_LOADS.get(op_type, 0.04)
    feed_xy = spindle_rpm * fz * max(1, tool.flutes)
    feed_z = 0.30 * feed_xy

    return (round(spindle_rpm, 2), round(feed_xy, 2), round(feed_z, 2))


def get_default_tool_library() -> Dict[int, ToolDefinition]:
    """Standard starter tool catalog for CNC machining centers"""
    return {
        1: ToolDefinition(tool_no=1, name="Ø10mm Flat Endmill (3F Rougher)", tool_type=ToolType.FLAT_ENDMILL, diameter=10.0, flutes=3),
        2: ToolDefinition(tool_no=2, name="Ø6mm Flat Endmill (3F Finisher)", tool_type=ToolType.FLAT_ENDMILL, diameter=6.0, flutes=3),
        3: ToolDefinition(tool_no=3, name="Ø8.5mm Jobber Drill (M10 Tap Drill)", tool_type=ToolType.DRILL, diameter=8.5, flutes=2),
        4: ToolDefinition(tool_no=4, name="M10x1.5 Spiral Flute Tap", tool_type=ToolType.TAP, diameter=10.0, flutes=3, pitch=1.5),
        5: ToolDefinition(tool_no=5, name="Ø12mm 90° Chamfer Mill", tool_type=ToolType.CHAMFER_MILL, diameter=12.0, flutes=4),
    }
