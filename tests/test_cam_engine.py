"""
Unit Test Suite for Module 3.6: CAM Toolpath Generator & CNC G-Code Engine.
Validates Speeds & Feeds physics, 2.5D spiral pocketing with MultiPolygon handling,
canned drilling/tapping cycles, ISO 6983 G-code post-processing, and CAD Doctor safety rules.
"""

import math
import pytest
from shapely.geometry import Polygon, box

from src.engine.cam_engine import (
    ToolType, ToolDefinition, OperationType, ToolpathSegment, MachiningOperation,
    calculate_speeds_and_feeds, get_default_tool_library
)
from src.engine.toolpath_planner import ToolpathPlanner, Z_CLEARANCE, Z_RETRACT
from src.export.gcode_post import GCodePostProcessor
from src.engine.rules_engine import RulesEngine, DiagnosticSeverity


def test_speeds_and_feeds_aluminum_6061():
    """
    Test Case 1 (PRD Section 7.1): Spindle Speed & Feed Calculations.
    - Material: 6061-T6 Aluminum (Vc = 250.0 m/min).
    - Endmill: D = 6.0 mm, Z_t = 3 flutes, f_z = 0.04 mm/tooth.
    - Spindle RPM: N = (1000 * 250) / (pi * 6.0) = 13262.91 RPM.
    - Feed XY: 13262.91 * 0.04 * 3 = 1591.55 mm/min.
    - Plunge Z: 0.30 * 1591.55 = 477.46 mm/min.
    """
    tool = ToolDefinition(
        tool_no=2,
        name="Ø6mm Flat Endmill",
        tool_type=ToolType.FLAT_ENDMILL,
        diameter=6.0,
        flutes=3,
        max_rpm=15000.0
    )

    rpm, f_xy, f_z = calculate_speeds_and_feeds(
        material="6061-T6 Aluminum",
        tool=tool,
        op_type=OperationType.POCKET_ROUGH,
        custom_fz=0.04
    )

    expected_rpm = (1000.0 * 250.0) / (math.pi * 6.0)
    expected_f_xy = expected_rpm * 0.04 * 3
    expected_f_z = 0.30 * expected_f_xy

    assert abs(rpm - expected_rpm) / expected_rpm < 0.005 # within 0.5%
    assert abs(f_xy - expected_f_xy) / expected_f_xy < 0.005
    assert abs(f_z - expected_f_z) / expected_f_z < 0.005


def test_inward_pocket_clearing_offset_loops():
    """
    Test Case 2 (PRD Section 7.2): Inward Pocket Clearing Offset Loops.
    - Pocket: 80 x 50 mm rectangle.
    - Tool: D = 10.0 mm (R = 5.0 mm).
    - Stepover: 60% of tool diameter = 6.0 mm.
    - Safe inset boundary: 70 x 40 mm.
    - Concentric loops: ceil((min(70, 40) / 2.0) / 6.0) = ceil(20 / 6) = 4 rings.
    """
    pocket_poly = box(-40.0, -25.0, 40.0, 25.0) # 80 x 50 mm
    tool = ToolDefinition(
        tool_no=1,
        name="Ø10mm Endmill",
        tool_type=ToolType.FLAT_ENDMILL,
        diameter=10.0,
        flutes=3
    )

    rings: list = []
    r_tool = tool.diameter / 2.0
    stepover_dist = 0.60 * tool.diameter
    safe_boundary = pocket_poly.buffer(-r_tool)

    ToolpathPlanner._generate_inward_rings_recursive(safe_boundary, stepover_dist, rings)

    assert len(rings) == 4

    # Generate full toolpath segments for single pass
    segments = ToolpathPlanner.plan_pocket_clearing(
        pocket_poly=pocket_poly,
        tool=tool,
        depth=5.0,
        stepover_ratio=0.60,
        max_stepdown=5.0
    )
    assert len(segments) > 10

    # Verify Guardrail #1: Retracts occur at Z_retract (+2.0 mm)
    z_rapid_levels = [seg.end_pt[2] for seg in segments if seg.is_rapid and seg.g_code == "G00"]
    assert all(z >= Z_RETRACT for z in z_rapid_levels)


def test_peck_drilling_and_rigid_tapping_gcode():
    """
    Test Case 3 (PRD Section 7.3): Peck Drilling & Rigid Tapping G-Code Generation.
    - M10 x 1.5 blind tapped hole:
      - Drill depth L_drill = 30.0 mm (> 3 * 8.5 mm -> G83 peck drill, Q = 4.25 mm).
      - Tap depth L_thread = 22.0 mm (G84 rigid tap, F = 400 RPM * 1.5 = 600.0 mm/min).
    """
    drill_tool = ToolDefinition(tool_no=3, name="Ø8.5mm Drill", tool_type=ToolType.DRILL, diameter=8.5, flutes=2)
    tap_tool = ToolDefinition(tool_no=4, name="M10x1.5 Tap", tool_type=ToolType.TAP, diameter=10.0, flutes=3, pitch=1.5)

    # 1. Plan Drilling
    drill_segs = ToolpathPlanner.plan_drilling_cycle(
        center_xy=(50.0, 50.0),
        hole_diameter=8.5,
        depth=30.0,
        tool=drill_tool,
        feed_z=225.0
    )
    op_drill = MachiningOperation(
        op_id="op_drill_01",
        name="Peck Drill M10",
        op_type=OperationType.PECK,
        tool=drill_tool,
        target_depth=30.0,
        spindle_rpm=4500.0,
        feed_xy=225.0,
        feed_z=225.0,
        segments=drill_segs
    )

    # 2. Plan Tapping
    tap_segs = ToolpathPlanner.plan_tapping_cycle(
        center_xy=(50.0, 50.0),
        thread_depth=22.0,
        tool=tap_tool,
        pitch=1.5,
        spindle_rpm=400.0
    )
    op_tap = MachiningOperation(
        op_id="op_tap_01",
        name="Rigid Tap M10x1.5",
        op_type=OperationType.TAP,
        tool=tap_tool,
        target_depth=22.0,
        spindle_rpm=400.0,
        feed_xy=600.0,
        feed_z=600.0,
        segments=tap_segs
    )

    # Post-Process to G-Code
    gcode = GCodePostProcessor.format_gcode([op_drill, op_tap], dialect="HAAS_VF")

    # Assertions
    assert "G83 X50.000 Y50.000 Z-30.000 R2.000 Q4.250 F225.0" in gcode
    assert "G84 X50.000 Y50.000 Z-22.000 R2.000 F600.0" in gcode
    assert "G80" in gcode # Canned cycle cancel


def test_rule_cam_02_rapid_collision_detection():
    """
    Test Case 4 (PRD Section 7.4): Rule CAM_02 Rapid Collision Detection.
    - G00 move plunging into stock: G00 X50.0 Y50.0 Z-5.0.
    - Stock footprint: [0, 0, 100, 100].
    - Assert: check_cam_rules() flags CAM_02 as CRITICAL / ERROR.
    """
    rules_engine = RulesEngine()
    tool = ToolDefinition(tool_no=1, name="Ø10mm Endmill", tool_type=ToolType.FLAT_ENDMILL, diameter=10.0)

    crash_segment = ToolpathSegment(
        g_code="G00",
        start_pt=(50.0, 50.0, 10.0),
        end_pt=(50.0, 50.0, -5.0), # Rapid through solid stock!
        is_rapid=True
    )
    op = MachiningOperation(
        op_id="op_crash",
        name="Rough Pocket",
        op_type=OperationType.POCKET_ROUGH,
        tool=tool,
        target_depth=5.0,
        segments=[crash_segment]
    )

    stock_bounds = (0.0, 0.0, 100.0, 100.0)
    diags = rules_engine.check_cam_rules([op], stock_bounds=stock_bounds)

    cam02_diags = [d for d in diags if d.rule_id == "CAM_02"]
    assert len(cam02_diags) == 1
    assert "Fatal Crash Hazard" in cam02_diags[0].title


def test_multipolygon_pocket_decomposition_guardrail_2():
    """
    Verify Guardrail #2: Dumbbell/H-shaped pocket splitting into MultiPolygon handles cleanly without exceptions.
    """
    # Create dumbbell / H-shaped polygon that pinches in the middle
    h_poly = Polygon([
        (-40, -30), (40, -30), (40, -10), (5, -10), (5, 10), (40, 10), (40, 30),
        (-40, 30), (-40, 10), (-5, 10), (-5, -10), (-40, -10)
    ])

    tool = ToolDefinition(tool_no=2, name="Ø6mm Endmill", tool_type=ToolType.FLAT_ENDMILL, diameter=6.0)

    segments = ToolpathPlanner.plan_pocket_clearing(
        pocket_poly=h_poly,
        tool=tool,
        depth=10.0,
        stepover_ratio=0.60
    )

    assert len(segments) > 0
    # Verify no Z crashes below 0.0 in rapid moves
    for seg in segments:
        if seg.is_rapid and seg.g_code == "G00":
            assert seg.end_pt[2] >= Z_RETRACT
