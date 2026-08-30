"""
Unit Test Suite for Module 3.4: Multi-Part Assembly, ISO 286 Fits & Exploded Views.
Validates ISO 286 tolerance calculations, DAG disassembly trajectories, BOM generation, and CAD Doctor seizure checks.
"""

import math
import pytest
from src.engine.fits_db import evaluate_iso_fit, FitEvaluationResult
from src.engine.assembly_engine import (
    Assembly, Part, AssemblyMate, AssemblyEngine, BOMEntry
)
from src.engine.cad_engine import CADEngine, Circle, Rectangle
from src.engine.rules_engine import RulesEngine, DiagnosticSeverity


def test_iso_286_running_clearance_fit_h7_g6():
    """
    Test Case 1 (PRD Section 7.1): ISO 286 Precision Running Clearance Fit (H7/g6).
    - Nominal diameter D_nom = 20.0 mm, Fit = "H7/g6".
    - Hole H7: [20.000, 20.021] mm.
    - Shaft g6: [19.980, 19.993] mm.
    - Min_Clearance = +0.007 mm (+7.0 um).
    - Max_Clearance = +0.041 mm (+41.0 um).
    - Assert: category == "CLEARANCE", is_interference == False.
    """
    res = evaluate_iso_fit(20.0, "H7/g6")

    assert res.category == "CLEARANCE"
    assert not res.is_interference
    assert abs(res.hole_lower_limit - 20.000) < 1e-4
    assert abs(res.hole_upper_limit - 20.021) < 1e-4
    assert abs(res.shaft_lower_limit - 19.980) < 1e-4
    assert abs(res.shaft_upper_limit - 19.993) < 1e-4
    assert abs(res.min_clearance - 0.007) < 1e-4
    assert abs(res.max_clearance - 0.041) < 1e-4


def test_iso_286_heavy_press_fit_h7_p6():
    """
    Test Case 2 (PRD Section 7.2): ISO 286 Heavy Press Interference Fit (H7/p6).
    - Nominal diameter D_nom = 50.0 mm, Fit = "H7/p6".
    - Hole H7: [50.000, 50.025] mm.
    - Shaft p6: [50.026, 50.042] mm.
    - Min_Interference = +0.001 mm (+1.0 um).
    - Max_Interference = +0.042 mm (+42.0 um).
    - Assert: category == "INTERFERENCE", is_interference == True.
    """
    res = evaluate_iso_fit(50.0, "H7/p6")

    assert res.category == "INTERFERENCE"
    assert res.is_interference
    assert abs(res.hole_lower_limit - 50.000) < 1e-4
    assert abs(res.hole_upper_limit - 50.025) < 1e-4
    assert abs(res.shaft_lower_limit - 50.026) < 1e-4
    assert abs(res.shaft_upper_limit - 50.042) < 1e-4
    assert abs(res.min_interference - 0.001) < 1e-4
    assert abs(res.max_interference - 0.042) < 1e-4


def test_dynamic_exploded_position_vector_transformation():
    """
    Test Case 3 (PRD Section 7.3): Dynamic Exploded Position Vector Transformation.
    - Part 0 (Base): extent Z = 40.0 mm, is_anchor = True.
    - Part 1 (Shaft): extent Z = 30.0 mm, mating vector = (0, 0, 1), S_gap = 25.0 mm.
    - Total separation distance = 40.0 + 25.0 = 65.0 mm.
    - At t = 0.0: translation == (0.0, 0.0, 0.0).
    - At t = 1.0: translation == (0.0, 0.0, 65.0).
    """
    assy = Assembly(name="Gearbox Assembly")
    p0 = Part(part_id="p0", name="Base Housing", is_anchor=True, extent_3d=(60.0, 60.0, 40.0))
    p1 = Part(part_id="p1", name="Input Shaft", is_anchor=False, extent_3d=(20.0, 20.0, 30.0))
    assy.parts["p0"] = p0
    assy.parts["p1"] = p1

    m1 = AssemblyMate(
        mate_id="m1",
        type="COAXIAL",
        part_a_id="p0",
        part_b_id="p1",
        axis="Z",
        vector=(0.0, 0.0, 1.0),
        nominal_d=20.0,
        fit_code="H7/g6"
    )
    assy.mates.append(m1)

    t0_offsets = AssemblyEngine.compute_exploded_trajectories(assy, t_factor=0.0, s_gap=25.0)
    assert t0_offsets["p0"] == (0.0, 0.0, 0.0)
    assert t0_offsets["p1"] == (0.0, 0.0, 0.0)

    t1_offsets = AssemblyEngine.compute_exploded_trajectories(assy, t_factor=1.0, s_gap=25.0)
    assert t1_offsets["p0"] == (0.0, 0.0, 0.0)
    assert abs(t1_offsets["p1"][0] - 0.0) < 1e-4
    assert abs(t1_offsets["p1"][1] - 0.0) < 1e-4
    assert abs(t1_offsets["p1"][2] - 65.0) < 1e-4


def test_rule_assy_01_seizure_detection():
    """
    Test Case 4 (PRD Section 7.4): Rule ASSY_01 Seizure Detection.
    - Setup: Mating joint tagged with fit "H7/g6" on D_nom = 25.0 mm.
    - Drawn shaft circle radius = 12.505 mm (D = 25.010 mm), hole circle radius = 12.500 mm (D = 25.000 mm).
    - Assert: check_assembly_rules() flags ASSY_01 with severity = ERROR.
    """
    rules_engine = RulesEngine()

    hole_shape = Circle(center=(0.0, 0.0), radius=12.500, shape_id="hole_s1")
    shaft_shape = Circle(center=(0.0, 0.0), radius=12.505, shape_id="shaft_s1")

    p_hole = Part(part_id="part_hole", name="Housing", is_anchor=True, shape_ids=["hole_s1"])
    p_shaft = Part(part_id="part_shaft", name="Shaft", is_anchor=False, shape_ids=["shaft_s1"])

    assy = Assembly()
    assy.parts["part_hole"] = p_hole
    assy.parts["part_shaft"] = p_shaft

    m1 = AssemblyMate(
        mate_id="mate_01",
        type="COAXIAL",
        part_a_id="part_hole",
        part_b_id="part_shaft",
        nominal_d=25.0,
        fit_code="H7/g6"
    )
    assy.mates.append(m1)

    shapes_by_view = {
        'top': [hole_shape, shaft_shape]
    }

    diags = rules_engine.check_assembly_rules(assy, shapes_by_view)
    assy01_diags = [d for d in diags if d.rule_id == "ASSY_01"]

    assert len(assy01_diags) == 1
    assert assy01_diags[0].severity == DiagnosticSeverity.ERROR
    assert "Mechanical Seizure" in assy01_diags[0].title
    assert "25.010 mm" in assy01_diags[0].description


def test_assembly_graph_cycle_and_disconnected_guardrail_1():
    """
    Verify Guardrail #1: Mutual cyclical mates and disconnected parts must not cause infinite loops.
    """
    assy = Assembly()
    p0 = Part(part_id="p0", name="Base", is_anchor=True)
    p1 = Part(part_id="p1", name="Shaft", is_anchor=False)
    p2 = Part(part_id="p2", name="Floating Widget", is_anchor=False)
    assy.parts["p0"] = p0
    assy.parts["p1"] = p1
    assy.parts["p2"] = p2

    # Mutual cycle
    assy.mates.append(AssemblyMate("m1", "COAXIAL", "p0", "p1"))
    assy.mates.append(AssemblyMate("m2", "COAXIAL", "p1", "p0"))

    # Compute exploded trajectory
    offsets = AssemblyEngine.compute_exploded_trajectories(assy, t_factor=1.0)

    assert "p0" in offsets
    assert "p1" in offsets
    assert "p2" in offsets
    assert offsets["p0"] == (0.0, 0.0, 0.0)


def test_2d_bounding_fallback_guardrail_2():
    """
    Verify Guardrail #2: BOM and extent calculators fallback gracefully to 2D shapes when 3D B-Rep is absent.
    """
    rect = Rectangle(rect=(0.0, 0.0, 120.0, 80.0), shape_id="s_rect")
    p0 = Part(part_id="p0", name="Plate", shape_ids=["s_rect"], extent_3d=(0.0, 0.0, 0.0))

    assy = Assembly()
    assy.parts["p0"] = p0

    bom = AssemblyEngine.compile_bill_of_materials(assy, shapes_by_view={'top': [rect]})

    assert len(bom) == 1
    assert "120.0 x 80.0" in bom[0].dimensions
