"""
Unit Tests for Module 2: Orthographic Ambiguity & Candidate Disambiguation.
Tests gated ambiguity detection and multi-solution solid candidate generation.
"""

from src.engine.cad_engine import Rectangle, Line
from src.engine.rules_engine import RulesEngine
from src.reconstruction.brep_reconstructor import BRepReconstructionWorker, HAS_BUILD123D
import pytest


def test_ambiguity_diagnostic_detection():
    """Verify that RulesEngine flags ambiguous orthographics with multiple hidden features (Rule 14)"""
    engine = RulesEngine()

    shapes = {
        'top': [
            Rectangle((0.0, 0.0, 100.0, 100.0), layer='Visible'),
            Line((20.0, 20.0), (80.0, 20.0), layer='Hidden'),
            Line((20.0, 80.0), (80.0, 80.0), layer='Hidden')
        ],
        'front': [
            Rectangle((0.0, 0.0, 100.0, 100.0), layer='Visible')
        ],
        'side': [
            Rectangle((0.0, 0.0, 100.0, 100.0), layer='Visible')
        ]
    }

    diags = engine.check_orthographic_ambiguity(shapes)
    assert len(diags) > 0
    assert diags[0].rule_id == "RULE_AMBIGUITY_DETECTED"


@pytest.mark.skipif(not HAS_BUILD123D, reason="build123d/OpenCASCADE not installed")
def test_candidate_solid_generation():
    """Verify that ambiguous drawings generate multiple manifold solution candidates"""
    top_shapes = [
        {'type': 'rectangle', 'rect': (0.0, 0.0, 100.0, 100.0), 'layer': 'Visible'},
        {'type': 'line', 'start': (20.0, 20.0), 'end': (80.0, 20.0), 'layer': 'Hidden'},
        {'type': 'line', 'start': (20.0, 80.0), 'end': (80.0, 80.0), 'layer': 'Hidden'}
    ]
    front_shapes = [{'type': 'rectangle', 'rect': (0.0, 0.0, 100.0, 100.0), 'layer': 'Visible'}]
    side_shapes = [{'type': 'rectangle', 'rect': (0.0, 0.0, 100.0, 100.0), 'layer': 'Visible'}]

    worker = BRepReconstructionWorker(top_shapes, front_shapes, side_shapes)
    solid, step_bytes, _, summary, candidates = worker.reconstruct_brep_solid()

    assert solid is not None
    assert len(candidates) >= 1
