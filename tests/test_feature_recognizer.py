"""
Unit Test Suite for Module 3.1: Standard Mechanical Feature & Component Recognizer.
Validates metric threads, counterbores, countersinks, PCD patterns, and CAD Doctor diagnostic auto-fix.
"""

import math
import pytest
from src.engine.cad_engine import CADEngine, Circle, Arc, Line
from src.engine.standards_db import (
    METRIC_COARSE_THREADS, COUNTERBORE_TABLE, COUNTERSINK_TABLE,
    lookup_metric_thread, lookup_counterbore, lookup_countersink
)
from src.engine.feature_recognizer import (
    FeatureRecognizer, FeatureType, RecognizedFeature, BoltCirclePattern
)
from src.engine.rules_engine import RulesEngine, DiagnosticSeverity


def test_metric_thread_recognition():
    """
    Test Case 1 (PRD Section 7.1): Metric Thread Recognition.
    - Top View: Circle at (-50, -50) with radius 4.25 mm (D_drill = 8.5 mm),
      paired with 270° Arc at (-50, -50) with radius 5.0 mm (D_major = 10.0 mm).
    - Front View: Hidden vertical line pair extending down 30.0 mm. Part thickness = 50.0 mm.
    - Expected: BLIND_TAPPED_HOLE, nominal_size = "M10x1.5", usable_depth = 30.0 - 1.25*1.5 = 28.125 mm.
    """
    recognizer = FeatureRecognizer()

    drill_circle = Circle(center=(-50.0, -50.0), radius=4.25, layer="Visible")
    thread_arc = Arc(center=(-50.0, -50.0), radius=5.0, start_angle=0.0, end_angle=270.0, layer="Visible")

    # Front view vertical hidden line at X = -50.0 extending from 0 to -30.0
    front_hidden_line = Line(start=(-50.0, 0.0), end=(-50.0, -30.0), layer="Hidden")

    shapes_by_view = {
        'top': [drill_circle, thread_arc],
        'front': [front_hidden_line]
    }

    features = recognizer.detect_tapped_holes(shapes_by_view, part_thickness=50.0)

    assert len(features) == 1
    f = features[0]
    assert f.feature_type == FeatureType.BLIND_TAPPED_HOLE
    assert f.nominal_size == "M10x1.5"
    assert abs(f.d_major - 10.0) < 1e-3
    assert abs(f.d_drill - 8.5) < 1e-3
    assert abs(f.pitch - 1.5) < 1e-3
    assert abs(f.usable_depth - 28.125) < 1e-3


def test_counterbore_recognition():
    """
    Test Case 2 (PRD Section 7.2): Counterbore Cap Screw Pocket Recognition.
    - Top View: Concentric circles at (-80, -40) with radius 3.3 mm (D_pass = 6.6 mm)
      and radius 5.5 mm (D_bore = 11.0 mm).
    - Front View: Hidden vertical line of depth 6.5 mm.
    - Expected: COUNTERBORE, nominal_size = "DIN 912 M6", d_pass = 6.6, d_bore = 11.0, h_bore = 6.5.
    """
    recognizer = FeatureRecognizer()

    pass_circle = Circle(center=(-80.0, -40.0), radius=3.3, layer="Visible")
    bore_circle = Circle(center=(-80.0, -40.0), radius=5.5, layer="Visible")

    front_notch_line = Line(start=(-80.0, 0.0), end=(-80.0, -6.5), layer="Hidden")

    shapes_by_view = {
        'top': [pass_circle, bore_circle],
        'front': [front_notch_line]
    }

    features = recognizer.detect_counterbores(shapes_by_view, part_thickness=50.0)

    assert len(features) == 1
    f = features[0]
    assert f.feature_type == FeatureType.COUNTERBORE
    assert f.nominal_size == "DIN 912 M6"
    assert abs(f.d_pass - 6.6) < 1e-3
    assert abs(f.d_bore - 11.0) < 1e-3
    assert abs(f.h_bore - 6.5) < 1e-3


def test_countersink_angle_determination():
    """
    Test Case 3 (PRD Section 7.3): Countersink Angle Determination.
    - Top View: Concentric circles with D_pass = 4.5 mm (radius 2.25) and D_sink = 8.3 mm (radius 4.15).
    - Front View: Conical taper with depth H_sink = 1.9 mm.
    - Angle = 2.0 * atan((8.3 - 4.5) / (2.0 * 1.9)) * 180 / pi = 90.0 degrees.
    - Expected: COUNTERSINK, standard = "ISO 7721 M4 90 DEG".
    """
    recognizer = FeatureRecognizer()

    pass_circle = Circle(center=(20.0, 30.0), radius=2.25, layer="Visible")
    sink_circle = Circle(center=(20.0, 30.0), radius=4.15, layer="Visible")

    # Front view chamfer line with dx = (8.3 - 4.5)/2 = 1.9, dy = 1.9
    front_chamfer = Line(start=(20.0, 0.0), end=(21.9, -1.9), layer="Visible")

    shapes_by_view = {
        'top': [pass_circle, sink_circle],
        'front': [front_chamfer]
    }

    features = recognizer.detect_countersinks(shapes_by_view, part_thickness=30.0)

    assert len(features) == 1
    f = features[0]
    assert f.feature_type == FeatureType.COUNTERSINK
    assert abs(f.angle - 90.0) < 1e-2
    assert "ISO 7721" in f.standard
    assert "M4" in f.nominal_size


def test_pcd_pattern_clustering():
    """
    Test Case 4 (PRD Section 7.4): Pitch Circle Diameter (PCD) Pattern Clustering.
    - Reference Centerline Circle with diameter 120.0 mm (radius 60.0 mm).
    - 4 clearance holes of diameter 9.0 mm (radius 4.5 mm) at:
      (60.0, 0.0), (0.0, 60.0), (-60.0, 0.0), (0.0, -60.0).
    - Expected: PCD = 120.0 mm, Count = 4, Spacing = 90.0°, Matched = "M8 Clearance (DIN 273)".
    """
    recognizer = FeatureRecognizer()

    pcd_circle = Circle(center=(0.0, 0.0), radius=60.0, layer="Centerline")
    h1 = Circle(center=(60.0, 0.0), radius=4.5, layer="Visible")
    h2 = Circle(center=(0.0, 60.0), radius=4.5, layer="Visible")
    h3 = Circle(center=(-60.0, 0.0), radius=4.5, layer="Visible")
    h4 = Circle(center=(0.0, -60.0), radius=4.5, layer="Visible")

    shapes_by_view = {
        'top': [pcd_circle, h1, h2, h3, h4],
        'front': []
    }

    patterns = recognizer.detect_pcd_patterns(shapes_by_view)

    assert len(patterns) == 1
    p = patterns[0]
    assert abs(p.pcd - 120.0) < 1e-3
    assert p.count == 4
    assert abs(p.hole_size - 9.0) < 1e-3
    assert abs(p.nominal_spacing_deg - 90.0) < 1e-3
    assert p.matched_fastener == "M8 Clearance (DIN 273)"


def test_mech_01_tap_drill_verification_and_autofix():
    """
    Verify Rule MECH_01 in RulesEngine:
    - Drawn tapped hole has outer diameter M10 (radius 5.0 mm) and incorrect tap drill 7.0 mm (radius 3.5 mm).
    - RulesEngine emits MECH_01 ERROR.
    - CADEngine apply_autofix fixes radius to standard 4.25 mm (8.50 mm diameter).
    """
    engine = CADEngine()
    rules_engine = RulesEngine()

    wrong_drill = Circle(center=(0.0, 0.0), radius=3.5, layer="Visible")  # 7.0 mm diameter
    thread_arc = Arc(center=(0.0, 0.0), radius=5.0, start_angle=0.0, end_angle=270.0, layer="Visible")

    engine.add_shape(wrong_drill, 'top')
    engine.add_shape(thread_arc, 'top')

    diags = rules_engine.evaluate_all(engine.shapes, engine.view_regions)
    mech01_errors = [d for d in diags if d.rule_id == "MECH_01"]

    assert len(mech01_errors) == 1
    err = mech01_errors[0]
    assert err.severity == DiagnosticSeverity.ERROR
    assert "8.50" in err.description

    # Test 1-click Auto-Fix
    success = engine.apply_autofix(err)
    assert success is True

    # Verify drill circle radius updated to 4.25 mm
    fixed_circle = [s for s in engine.get_shapes('top') if s.id == wrong_drill.id][0]
    assert abs(fixed_circle.radius - 4.25) < 1e-3
