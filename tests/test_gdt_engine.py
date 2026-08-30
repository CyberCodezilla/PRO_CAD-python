"""
Unit Test Suite for ASME Y14.5-2018 GD&T and Metrology Intelligence Engine.
Tests True Position, MMC/LMC bonus tolerances, Virtual Condition boundaries,
1D/2D Worst-Case & RSS Tolerance Stack-Up Analysis, and RulesEngine DRF validation.
"""

import math
import pytest
from src.engine.gdt_engine import (
    GDTSymbol, MaterialModifier, DatumFeature, FeatureControlFrame, 
    DimensionStackItem, GDTEngine
)
from src.engine.cad_engine import CADEngine, Circle, Line
from src.engine.rules_engine import RulesEngine, DiagnosticSeverity


def test_true_position_rfs():
    """
    Test Case 1 (PRD Section 7.1): True Position calculation at RFS.
    - Nominal: X=50.0, Y=50.0; Actual: X=50.05, Y=50.08
    - dX = 0.05, dY = 0.08
    - Expected TP: 2.0 * sqrt(0.05^2 + 0.08^2) = 0.18868 mm
    """
    dx = 0.05
    dy = 0.08
    tp = GDTEngine.calculate_true_position(dx, dy)
    expected_tp = 2.0 * math.sqrt(0.05**2 + 0.08**2)

    assert abs(tp - expected_tp) < 1e-6
    assert abs(tp - 0.1887) < 1e-4


def test_mmc_bonus_tolerance_internal_hole():
    """
    Test Case 2 (PRD Section 7.2): MMC Bonus Tolerance calculation for internal hole.
    - Specified Tolerance: 0.10 mm (M)
    - Hole Nominal Size: 10.0 mm (+0.2 mm / -0.0 mm)
    - MMC Size: 10.0 mm; Actual Size: 10.15 mm
    - Expected Bonus: 0.15 mm; Total Allowed TP: 0.25 mm
    - Measured dX = 0.08, dY = 0.06 -> Measured TP = 0.20 mm <= 0.25 mm (PASS)
    """
    nominal_size = 10.0
    lower_tol = 0.0
    upper_tol = 0.2
    actual_size = 10.15
    specified_tol = 0.10

    bonus = GDTEngine.compute_bonus_tolerance(
        nominal_size=nominal_size,
        actual_size=actual_size,
        lower_tol=lower_tol,
        upper_tol=upper_tol,
        is_internal=True,
        modifier=MaterialModifier.MMC
    )

    assert abs(bonus - 0.15) < 1e-5
    total_allowed_tp = specified_tol + bonus
    assert abs(total_allowed_tp - 0.25) < 1e-5

    measured_tp = GDTEngine.calculate_true_position(0.08, 0.06)
    assert abs(measured_tp - 0.20) < 1e-5
    assert measured_tp <= total_allowed_tp


def test_mmc_bonus_tolerance_external_pin():
    """
    Verify MMC Bonus Tolerance for external shaft/pin.
    - Nominal Pin Size: 20.0 mm (+0.0 / -0.2 mm)
    - MMC Size: 20.0 mm; Actual Size: 19.85 mm
    - Expected Bonus: 20.0 - 19.85 = 0.15 mm
    """
    bonus = GDTEngine.compute_bonus_tolerance(
        nominal_size=20.0,
        actual_size=19.85,
        lower_tol=0.2,
        upper_tol=0.0,
        is_internal=False,
        modifier=MaterialModifier.MMC
    )
    assert abs(bonus - 0.15) < 1e-5


def test_virtual_condition_boundary():
    """Verify Virtual Condition assembly clearance boundary calculation"""
    # Internal hole: VC = MMC_Size - Specified_Tol = 10.0 - 0.10 = 9.90 mm
    vc_hole = GDTEngine.calculate_virtual_condition(
        nominal_size=10.0,
        lower_tol=0.0,
        upper_tol=0.2,
        specified_gdt_tol=0.10,
        is_internal=True
    )
    assert abs(vc_hole - 9.90) < 1e-5

    # External pin: VC = MMC_Size + Specified_Tol = 20.0 + 0.10 = 20.10 mm
    vc_pin = GDTEngine.calculate_virtual_condition(
        nominal_size=20.0,
        lower_tol=0.2,
        upper_tol=0.0,
        specified_gdt_tol=0.10,
        is_internal=False
    )
    assert abs(vc_pin - 20.10) < 1e-5


def test_1d_tolerance_stackup_worst_case_and_rss():
    """
    Test Case 3 (PRD Section 7.3): 1D Tolerance Stack-Up Calculation.
    - Bore Depth: 52.40 ± 0.20 mm (+1.0)
    - Bearing 1: 15.00 ± 0.05 mm (-1.0)
    - Spacer: 20.00 ± 0.10 mm (-1.0)
    - Bearing 2: 15.00 ± 0.05 mm (-1.0)
    - Retaining Ring: 2.00 ± 0.05 mm (-1.0)
    - Expected Nominal Gap: 0.40 mm
    - Expected Worst-Case: Total Tol = 0.45 mm, Min Gap = -0.05 mm (WARNING)
    - Expected RSS: Total Tol = 0.2398 mm, Min Gap = +0.1602 mm (PASS)
    """
    stack = [
        DimensionStackItem(label="Bore Depth", dimension=52.40, tolerance=0.20, direction=1.0),
        DimensionStackItem(label="Bearing 1", dimension=15.00, tolerance=0.05, direction=-1.0),
        DimensionStackItem(label="Spacer", dimension=20.00, tolerance=0.10, direction=-1.0),
        DimensionStackItem(label="Bearing 2", dimension=15.00, tolerance=0.05, direction=-1.0),
        DimensionStackItem(label="Retaining Ring", dimension=2.00, tolerance=0.05, direction=-1.0),
    ]

    res = GDTEngine.evaluate_tolerance_stack(stack)

    assert abs(res.nominal_gap - 0.40) < 1e-4
    assert abs(res.wc_tolerance - 0.45) < 1e-4
    assert abs(res.wc_min - (-0.05)) < 1e-4
    assert res.wc_pass is False
    assert res.warning_msg is not None

    assert abs(res.rss_tolerance - 0.2398) < 1e-3
    assert abs(res.rss_min - 0.1602) < 1e-3
    assert res.rss_pass is True
    assert res.error_msg is None


def test_invalid_datum_reference_rule():
    """
    Test Case 4 (PRD Section 7.4): Invalid Datum Reference in RulesEngine (Rule GD_01).
    - FCF specifies: [Pos] | Ø 0.1 | -A- | -B-
    - Datum A exists; Datum B does not exist.
    - RulesEngine emits ERROR for GD_01.
    """
    rules_engine = RulesEngine()

    datums = [
        DatumFeature(id="d_01", label="A", view="front", origin=(0.0, 0.0), direction=(0.0, 1.0))
    ]

    fcfs = [
        FeatureControlFrame(
            id="fcf_01",
            view="front",
            symbol=GDTSymbol.POSITION,
            is_diameter=True,
            tolerance=0.1,
            primary_datum="A",
            secondary_datum="B"
        )
    ]

    diags = rules_engine.check_gdt_rules(datums, fcfs, {'front': []})
    gd01_errors = [d for d in diags if d.rule_id == "GD_01"]

    assert len(gd01_errors) == 1
    assert gd01_errors[0].severity == DiagnosticSeverity.ERROR
    assert "[-B-]" in gd01_errors[0].description


def test_duplicate_datum_reference_rule_gd04():
    """Verify Rule GD_04: Duplicate datum in same DRF emits ERROR"""
    rules_engine = RulesEngine()

    datums = [
        DatumFeature(id="d_01", label="A", view="front", origin=(0.0, 0.0), direction=(0.0, 1.0))
    ]

    fcfs = [
        FeatureControlFrame(
            id="fcf_01",
            view="front",
            symbol=GDTSymbol.POSITION,
            tolerance=0.1,
            primary_datum="A",
            secondary_datum="A"
        )
    ]

    diags = rules_engine.check_gdt_rules(datums, fcfs, {'front': []})
    gd04_errors = [d for d in diags if d.rule_id == "GD_04"]

    assert len(gd04_errors) == 1
    assert gd04_errors[0].severity == DiagnosticSeverity.ERROR


def test_cascade_deletion_and_orphan_cleanup():
    """
    Verify Guardrail #2: Deleting a geometric shape automatically cleans up / unlinks
    attached Datums and Feature Control Frames without crashing.
    """
    engine = CADEngine()
    hole = Circle(center=(50.0, 50.0), radius=10.0, layer="Hidden")
    engine.add_shape(hole, 'front')

    datum = DatumFeature(id="d_hole", label="A", target_shape_id=hole.id, view="front")
    fcf = FeatureControlFrame(id="fcf_hole", target_shape_id=hole.id, view="front", symbol=GDTSymbol.POSITION)

    engine.add_datum_feature(datum)
    engine.add_feature_control_frame(fcf)

    assert engine.datums["d_hole"].target_shape_id == hole.id
    assert engine.feature_control_frames["fcf_hole"].target_shape_id == hole.id

    # Remove the shape
    success = engine.remove_shape(hole.id, 'front')
    assert success is True

    # Check unlinking
    assert engine.datums["d_hole"].target_shape_id is None
    assert engine.feature_control_frames["fcf_hole"].target_shape_id is None

    # Verify state persistence through undo and redo
    engine.undo()
    assert len(engine.get_shapes('front')) == 1
    engine.redo()
    assert len(engine.get_shapes('front')) == 0
