"""
B-Rep & STEP/IGES Pipeline Unit Tests — Validates OpenCASCADE analytical solid modeling
and ISO 10303-21 STEP / IGES manufacturing export.
"""

import pytest
import numpy as np
from src.reconstruction.brep_reconstructor import BRepReconstructionWorker, HAS_BUILD123D
from src.utils.step_exporter import StepExporter


def test_brep_box_reconstruction():
    """Verify exact analytical B-Rep reconstruction of a 100x100x100 cube solid"""
    bd = pytest.importorskip("build123d", reason="build123d / OpenCASCADE not installed")
    if not HAS_BUILD123D:
        pytest.skip("build123d / OpenCASCADE not available")

    top_shapes = [{
        'type': 'rectangle',
        'rect': (-50.0, -50.0, 100.0, 100.0),
        'layer': 'Visible'
    }]
    front_shapes = [{
        'type': 'rectangle',
        'rect': (-50.0, -50.0, 100.0, 100.0),
        'layer': 'Visible'
    }]
    side_shapes = [{
        'type': 'rectangle',
        'rect': (-50.0, -50.0, 100.0, 100.0),
        'layer': 'Visible'
    }]

    worker = BRepReconstructionWorker(top_shapes, front_shapes, side_shapes)
    solid, step_bytes, iges_bytes, summary, *candidates = worker.reconstruct_brep_solid()

    assert solid is not None, "B-Rep solid is None"
    assert len(step_bytes) > 0, "STEP export bytes are empty"
    assert step_bytes.startswith(b"ISO-10303-21;"), "Invalid STEP header"

    # Verify analytical volume is within 1% of 1,000,000 mm³
    volume = getattr(solid, 'volume', 0.0)
    assert abs(volume - 1_000_000.0) / 1_000_000.0 < 0.01, f"Volume error: {volume} mm³"


def test_faceted_step_exporter_fallback():
    """Verify fallback ISO-10303-21 STEP physical file generation on a triangular mesh"""
    # Simple tetrahedron mesh
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [100.0, 0.0, 0.0],
        [50.0, 86.6, 0.0],
        [50.0, 28.8, 81.6]
    ])
    faces = np.array([
        [0, 2, 1],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3]
    ])

    step_text = StepExporter.export_mesh_to_step(vertices, faces, part_name="TEST_TETRAHEDRON")

    assert step_text.startswith("ISO-10303-21;"), "Missing ISO-10303-21 header"
    assert "MANIFOLD_SOLID_BREP" in step_text, "Missing MANIFOLD_SOLID_BREP entity"
    assert "ADVANCED_FACE" in step_text, "Missing ADVANCED_FACE entities"
    assert "END-ISO-10303-21;" in step_text, "Missing END-ISO-10303-21 trailer"
