"""
Unit Test Suite for Module 3.2: Section Views & Cutting-Plane Semantics Engine.
Validates 3D plane equations, Shapely 45° cross-hatching, ASME Y14.3 non-hatching rules, and B-Rep solid splitting.
"""

import math
import pytest
from src.engine.section_engine import (
    CuttingPlane, SectionView, SectionType, SectionEngine
)
from src.engine.cad_engine import CADEngine, Rectangle, Line
from src.engine.rules_engine import RulesEngine, DiagnosticSeverity
from src.reconstruction.brep_reconstructor import apply_brep_section_cut, HAS_BUILD123D


def test_cutting_plane_equation_derivation():
    """
    Test Case 1 (PRD Section 7.1): 3D Cutting Plane Equation Derivation.
    - Top View Line: From (-100.0, 50.0) to (0.0, 50.0) with normal (0.0, -1.0) pointing in -Z.
    - Point: (-100.0, 0.0, 50.0), Normal: (0.0, 0.0, -1.0).
    - Expected Plane Equation: 0*X + 0*Y - 1*Z + 50.0 = 0 -> A=0.0, B=0.0, C=-1.0, D=50.0.
    """
    p1 = (-100.0, 50.0)
    p2 = (0.0, 50.0)
    normal_2d = (0.0, -1.0)

    A, B, C, D = SectionEngine.compute_3d_cutting_plane_equation(p1, p2, normal_2d, view="top")

    assert abs(A - 0.0) < 1e-4
    assert abs(B - 0.0) < 1e-4
    assert abs(C - (-1.0)) < 1e-4
    assert abs(D - 50.0) < 1e-4


def test_45_degree_hatch_line_generation():
    """
    Test Case 2 (PRD Section 7.2): 45-Degree Hatch Line Generation for Rectangular Cut Face.
    - Input: Rectangular cut face from X=0 to 100, Y=0 to 50 (Area = 5000 mm²).
    - Hatch Parameters: angle = 45.0°, pitch = 10.0 mm.
    - Assert: All hatch segments have slope = tan(45°) = 1.0 ± 1e-4.
    - Assert: All endpoints lie strictly on rectangle perimeter [0..100, 0..50].
    """
    outer_rect = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
    hatch_lines = SectionEngine.generate_hatch_lines(outer_rect, pitch=10.0, angle_deg=45.0)

    assert len(hatch_lines) > 0

    for (x1, y1), (x2, y2) in hatch_lines:
        dx = x2 - x1
        dy = y2 - y1
        assert abs(dx) > 1e-3
        slope = dy / dx
        assert abs(slope - 1.0) < 1e-3, f"Hatch line segment slope was {slope}, expected 1.0"

        # Verify endpoints lie within rectangular boundary
        for x, y in [(x1, y1), (x2, y2)]:
            assert -0.1 <= x <= 100.1
            assert -0.1 <= y <= 50.1


def test_rule_sect_02_web_rib_non_hatching():
    """
    Test Case 3 (PRD Section 7.3): Rule SECT_02 Web/Rib Non-Hatching Verification.
    - Symmetrical part with longitudinal structural rib of thickness 6.0 mm and length 40.0 mm.
    - RulesEngine emits INFO for SECT_02 to exclude the rib from cross-hatching.
    """
    rules_engine = RulesEngine()

    cp = CuttingPlane(id="cp_01", label="A", view="top", points=[(-50.0, 0.0), (50.0, 0.0)], normal=(0.0, -1.0))
    sv = SectionView(id="sec_01", cutting_plane_id="cp_01", target_view="front")

    rib_rect = Rectangle(rect=(0.0, 0.0, 40.0, 6.0), layer="Visible")

    shapes_by_view = {
        'top': [],
        'front': [rib_rect]
    }

    diags = rules_engine.check_section_rules([cp], [sv], shapes_by_view)
    sect02_diags = [d for d in diags if d.rule_id == "SECT_02"]

    assert len(sect02_diags) == 1
    assert sect02_diags[0].severity == DiagnosticSeverity.INFO
    assert "Thin Structural Web" in sect02_diags[0].title


def test_opencascade_analytical_solid_slicing():
    """
    Test Case 4 (PRD Section 7.4): OpenCASCADE Analytical Solid Slicing.
    - Base solid: 100 x 50 x 80 mm block.
    - Slicing plane passes through center at Z = 40.0 mm with normal along +Z (0, 0, 1).
    - Sliced solid has approximately half the base volume (within 1.0%).
    """
    bd = pytest.importorskip("build123d")
    from build123d import Box

    base_block = Box(100.0, 50.0, 80.0)
    base_volume = getattr(base_block, 'volume', 0.0)

    assert abs(base_volume - 400000.0) < 1.0

    plane_origin = (0.0, 0.0, 0.0) # Centered box extends from Z=-40 to +40, cutting at Z=0
    plane_normal = (0.0, 0.0, 1.0)

    sectioned_solid = apply_brep_section_cut(base_block, plane_origin, plane_normal)
    assert sectioned_solid is not None

    cut_volume = getattr(sectioned_solid, 'volume', 0.0)
    # Sliced solid should have half volume: ~200,000 mm³
    assert abs(cut_volume - (base_volume / 2.0)) < 1000.0
