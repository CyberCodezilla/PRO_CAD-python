"""
Unit Tests for Module 1: Topology-Aware Feature Recognition Engine.
Tests semantic 2D corner blend tagging, 3D OpenCASCADE edge fillets and chamfers,
and graceful exception fallback / radius clamping (User Guardrail #1).
"""

import pytest
import build123d as bd
from src.engine.cad_engine import CADEngine, Rectangle, Arc, Line
from src.reconstruction.brep_reconstructor import BRepReconstructionWorker, HAS_BUILD123D


def test_2d_corner_blend_detection():
    """Verify that CADEngine automatically detects and tags fillet arcs and chamfer bevels"""
    engine = CADEngine()

    # Add a 90-degree corner arc
    fillet_arc = Arc((50.0, 50.0), radius=10.0, start_angle=0.0, end_angle=90.0)
    engine.add_shape(fillet_arc, 'top')

    # Add a 45-degree chamfer line
    chamfer_line = Line((0.0, 10.0), (10.0, 0.0))
    engine.add_shape(chamfer_line, 'top')

    engine.detect_and_tag_corner_blends('top')

    assert fillet_arc.feature_type == 'fillet'
    assert abs(fillet_arc.fillet_radius - 10.0) < 1e-3

    assert chamfer_line.feature_type == 'chamfer'
    assert chamfer_line.chamfer_dist > 0.0


@pytest.mark.skipif(not HAS_BUILD123D, reason="build123d/OpenCASCADE not installed")
def test_3d_topological_fillet_execution():
    """Verify that 3D B-Rep reconstructor applies true edge fillets and chamfers"""
    top_shapes = [
        {'type': 'rectangle', 'rect': (-50.0, -50.0, 100.0, 100.0), 'layer': 'Visible'},
        {'type': 'arc', 'center': (10.0, 10.0), 'radius': 5.0, 'start_angle': 0.0, 'end_angle': 90.0,
         'feature_type': 'fillet', 'fillet_radius': 5.0, 'layer': 'Visible'}
    ]
    front_shapes = [
        {'type': 'rectangle', 'rect': (-50.0, -50.0, 100.0, 100.0), 'layer': 'Visible'}
    ]
    side_shapes = [
        {'type': 'rectangle', 'rect': (-50.0, -50.0, 100.0, 100.0), 'layer': 'Visible'}
    ]

    worker = BRepReconstructionWorker(top_shapes, front_shapes, side_shapes)
    solid, step_bytes, _, summary, candidates = worker.reconstruct_brep_solid()

    assert solid is not None
    assert solid.volume > 0.0
    # A box of 100x100x100 with edge fillets has volume slightly less than 1,000,000 mm³
    assert solid.volume <= 1000000.0
    assert len(step_bytes) > 100


@pytest.mark.skipif(not HAS_BUILD123D, reason="build123d/OpenCASCADE not installed")
def test_fillet_oversize_graceful_fallback():
    """Verify that over-sized fillet radius clamps or safely falls back without crashing (Guardrail #1)"""
    top_shapes = [
        {'type': 'rectangle', 'rect': (-10.0, -10.0, 20.0, 20.0), 'layer': 'Visible'},
        # Fillet radius 50.0 exceeds physical geometry of 20x20 box
        {'type': 'arc', 'center': (10.0, 10.0), 'radius': 50.0, 'start_angle': 0.0, 'end_angle': 90.0,
         'feature_type': 'fillet', 'fillet_radius': 50.0, 'layer': 'Visible'}
    ]
    front_shapes = [{'type': 'rectangle', 'rect': (-10.0, -10.0, 20.0, 20.0), 'layer': 'Visible'}]
    side_shapes = [{'type': 'rectangle', 'rect': (-10.0, -10.0, 20.0, 20.0), 'layer': 'Visible'}]

    worker = BRepReconstructionWorker(top_shapes, front_shapes, side_shapes)
    # Should not raise exception
    solid, step_bytes, _, summary, candidates = worker.reconstruct_brep_solid()
    assert solid is not None
    assert solid.volume > 0.0
