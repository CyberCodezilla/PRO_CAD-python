"""
AI Vectorizer Unit Tests — Validates collinear segment merging, endpoint micro-gap snapping,
and GNN missing edge inference for raster-to-CAD workflows.
"""

import math
import numpy as np
from src.cv.ai_vectorizer import RasterCADVectorizer, GNNInferenceBridge
from src.engine.cad_engine import Line, Rectangle


def test_collinear_segment_merging():
    """Verify that fragmented collinear segments on the same line are merged into one"""
    vectorizer = RasterCADVectorizer(snap_tolerance=0.5, collinear_angle_deg=5.0)

    # 3 fragmented line segments on y = 0
    fragments = [
        ((0.0, 0.0), (20.0, 0.0)),
        ((20.0, 0.0), (60.0, 0.0)),
        ((60.0, 0.0), (100.0, 0.0))
    ]

    merged = vectorizer._merge_collinear_segments(fragments)
    assert len(merged) == 1, f"Expected 1 merged segment, got {len(merged)}"

    p1, p2 = merged[0]
    # Check start and end
    assert abs(p1[0] - 0.0) < 1e-2 and abs(p1[1] - 0.0) < 1e-2
    assert abs(p2[0] - 100.0) < 1e-2 and abs(p2[1] - 0.0) < 1e-2


def test_endpoint_micro_gap_snapping():
    """Verify that near-coincident endpoints within epsilon = 0.1 mm snap to a single point"""
    vectorizer = RasterCADVectorizer(snap_tolerance=0.15)

    # Two segments with a 0.1 mm gap between (49.95, 0) and (50.05, 0)
    lines = [
        ((0.0, 0.0), (49.95, 0.0)),
        ((50.05, 0.0), (100.0, 0.0))
    ]

    snapped = vectorizer._snap_endpoints(lines)
    assert len(snapped) == 2

    # The junction point between line 1 end and line 2 start should be identical
    junc1 = snapped[0][1]
    junc2 = snapped[1][0]
    dist = math.sqrt((junc1[0] - junc2[0])**2 + (junc1[1] - junc2[1])**2)
    assert dist < 1e-4, f"Endpoints failed to snap: dist={dist}"
    assert abs(junc1[0] - 50.0) < 1e-3


def test_gnn_missing_edge_inference():
    """Verify GNN inference bridge detects unprojected orthogonal feature boundaries"""
    top_shapes = [
        Rectangle((0.0, 0.0, 100.0, 50.0)),
        Line((50.0, 0.0), (50.0, 50.0))  # Step feature at X = 50
    ]
    front_shapes = [
        Rectangle((0.0, 0.0, 100.0, 60.0))  # Front view missing feature line at X = 50
    ]
    side_shapes = []

    suggestions = GNNInferenceBridge.infer_missing_edges(top_shapes, front_shapes, side_shapes)

    assert len(suggestions) > 0, "No suggestions returned"
    suggested_x = suggestions[0]['suggested_x']
    assert abs(suggested_x - 50.0) < 1.0, f"Expected suggested X at 50, got {suggested_x}"
