"""
Unit Test Suite for Module 3.3: Design for Manufacturing (DFM) Advisory Engine.
Validates CNC sharp corner inaccessibility, deep pocket aspect ratios, injection molding draft angles, and sheet metal bend clearances.
"""

import math
import pytest
from src.engine.cad_engine import CADEngine, Rectangle, Line, Circle
from src.engine.dfm_engine import (
    DFMEngine, ManufacturingProcess, DFMDiagnosticSeverity, DFMViolation
)


def test_cnc_sharp_interior_corner_detection():
    """
    Test Case 1 (PRD Section 5.1): CNC Sharp Interior Corner Detection.
    - Outer plate: 200 x 150 mm (Visible).
    - Interior pocket: 100 x 60 mm (Hidden) inside outer plate. Corners have radius = 0.0 mm.
    - Tool radius: R_tool = 1.5 mm (Ø3.0 mm endmill).
    - Assert: check_cnc_sharp_corners() returns 4 violations for DFM_CNC_01 with recommended radius = 1.6 mm.
    """
    dfm = DFMEngine()

    outer_plate = Rectangle(rect=(-100.0, -75.0, 200.0, 150.0), layer="Visible")
    inner_pocket = Rectangle(rect=(-50.0, -30.0, 100.0, 60.0), layer="Hidden")

    top_shapes = [outer_plate, inner_pocket]

    violations = dfm.check_cnc_sharp_corners(top_shapes, tool_radius=1.5)

    assert len(violations) == 4
    for v in violations:
        assert v.rule_id == "DFM_CNC_01"
        assert v.severity == DFMDiagnosticSeverity.ERROR
        assert abs(v.recommended_value - 1.6) < 1e-3
        assert "Ø3.0 mm" in v.description


def test_boundary_loop_disambiguation_guardrail_1():
    """
    Verify Guardrail #1: Exterior stock perimeter corners must NOT be flagged as unmachinable CNC corners.
    """
    dfm = DFMEngine()
    outer_plate = Rectangle(rect=(-100.0, -75.0, 200.0, 150.0), layer="Visible")

    # Only outer boundary present
    violations = dfm.check_cnc_sharp_corners([outer_plate], tool_radius=1.5)
    assert len(violations) == 0


def test_deep_pocket_aspect_ratio():
    """
    Test Case 2 (PRD Section 5.2): Deep Narrow Pocket Aspect Ratio.
    - Pocket: Width W = 10.0 mm, Depth H = 70.0 mm.
    - Aspect Ratio: 70.0 / 10.0 = 7.0 (exceeds maximum threshold 6.0).
    - Assert: check_cnc_pocket_aspect_ratio() flags DFM_CNC_02 with severity = ERROR.
    """
    dfm = DFMEngine()

    pocket = Rectangle(rect=(-5.0, -5.0, 10.0, 20.0), layer="Hidden")
    front_depth_line = Line(start=(-5.0, 0.0), end=(-5.0, -70.0), layer="Hidden")

    shapes_by_view = {
        'top': [pocket],
        'front': [front_depth_line]
    }

    violations = dfm.check_cnc_pocket_aspect_ratio(shapes_by_view)

    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "DFM_CNC_02"
    assert v.severity == DFMDiagnosticSeverity.ERROR
    assert "7.0:1" in v.description


def test_injection_molding_draft_angle_evaluation():
    """
    Test Case 3 (PRD Section 5.3): Injection Molding Draft Angle Evaluation.
    - B-Rep box with planar vertical sidewalls (Normal = (1, 0, 0)), pull vector = (0, 0, 1).
    - Calculated draft angle = 0.0 degrees.
    - Assert: check_molding_draft_angles() flags DFM_MOLD_01 with severity = ERROR, recommending 1.5 degrees.
    """
    bd = pytest.importorskip("build123d")
    from build123d import Box

    dfm = DFMEngine()
    cube = Box(50.0, 50.0, 50.0)

    violations = dfm.check_molding_draft_angles(brep_solid=cube, pull_vector=(0.0, 0.0, 1.0))

    assert len(violations) >= 1
    v = violations[0]
    assert v.rule_id == "DFM_MOLD_01"
    assert v.severity == DFMDiagnosticSeverity.ERROR
    assert abs(v.recommended_value - 1.5) < 1e-3


def test_sheet_metal_hole_proximity_to_bend():
    """
    Test Case 4 (PRD Section 5.4): Sheet Metal Hole Proximity to Bend Line.
    - Sheet thickness t = 2.0 mm, drawn bend radius R = 2.0 mm, hole diameter D = 6.0 mm (radius = 3.0 mm).
    - Bend line at X = 0.0 (from Y=-50 to Y=50). Hole center at (5.0, 0.0).
    - Hole Edge Distance = 5.0 - 3.0 = 2.0 mm.
    - Required Safe Clearance = (2.0 * 2.0) + 2.0 = 6.0 mm.
    - Assert: check_sheet_metal_hole_proximity() flags DFM_SHEET_02 with severity = WARNING.
    """
    dfm = DFMEngine()

    bend_line = Line(start=(0.0, -50.0), end=(0.0, 50.0), layer="Centerline")
    hole = Circle(center=(5.0, 0.0), radius=3.0, layer="Visible")

    shapes_by_view = {
        'top': [bend_line, hole],
        'front': []
    }

    violations = dfm.check_sheet_metal_hole_proximity(shapes_by_view, thickness=2.0, drawn_bend_radius=2.0)

    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "DFM_SHEET_02"
    assert v.severity == DFMDiagnosticSeverity.WARNING
    assert "2.0 mm" in v.description
    assert "6.0 mm" in v.description
