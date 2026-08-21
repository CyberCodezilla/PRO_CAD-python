"""
Constraint Solver Unit Tests — Validates 2D parametric geometric constraint solving.
Tests Coincidence, Horizontal, Vertical, Distance, Radius, and Tangency solving.
"""

import pytest
import math
import numpy as np
from src.engine.cad_engine import Line, Circle, Rectangle
from src.engine.constraint_solver import ConstraintSolver2D, Constraint, ConstraintType


def test_horizontal_constraint():
    """Verify that a slanted line is solved to be strictly horizontal"""
    line = Line((10.0, 20.0), (100.0, 50.0))
    c = Constraint(
        id="c_horiz",
        constraint_type=ConstraintType.HORIZONTAL,
        shape_ids=[line.id]
    )
    solver = ConstraintSolver2D(tolerance=1e-4)
    success, shapes, msg = solver.solve([line], [c])

    assert success, f"Solver failed: {msg}"
    assert abs(line.start[1] - line.end[1]) < 1e-3, f"Line is not horizontal: y1={line.start[1]}, y2={line.end[1]}"


def test_vertical_constraint():
    """Verify that a slanted line is solved to be strictly vertical"""
    line = Line((30.0, 10.0), (45.0, 120.0))
    c = Constraint(
        id="c_vert",
        constraint_type=ConstraintType.VERTICAL,
        shape_ids=[line.id]
    )
    solver = ConstraintSolver2D(tolerance=1e-4)
    success, shapes, msg = solver.solve([line], [c])

    assert success, f"Solver failed: {msg}"
    assert abs(line.start[0] - line.end[0]) < 1e-3, f"Line is not vertical: x1={line.start[0]}, x2={line.end[0]}"


def test_distance_constraint():
    """Verify that line length adjusts to exact parametric distance value"""
    line = Line((0.0, 0.0), (30.0, 40.0))  # initial length = 50
    c = Constraint(
        id="c_dist",
        constraint_type=ConstraintType.DISTANCE,
        shape_ids=[line.id],
        value=100.0  # target length = 100
    )
    solver = ConstraintSolver2D(tolerance=1e-4)
    success, shapes, msg = solver.solve([line], [c])

    assert success, f"Solver failed: {msg}"
    dx = line.end[0] - line.start[0]
    dy = line.end[1] - line.start[1]
    solved_length = math.sqrt(dx * dx + dy * dy)
    assert abs(solved_length - 100.0) < 1e-2, f"Length {solved_length} != 100.0"


def test_radius_constraint():
    """Verify that circle radius adjusts to exact parametric radius"""
    circle = Circle((50.0, 50.0), radius=20.0)
    c = Constraint(
        id="c_rad",
        constraint_type=ConstraintType.RADIUS,
        shape_ids=[circle.id],
        value=45.0
    )
    solver = ConstraintSolver2D(tolerance=1e-4)
    success, shapes, msg = solver.solve([circle], [c])

    assert success, f"Solver failed: {msg}"
    assert abs(circle.radius - 45.0) < 1e-3, f"Radius {circle.radius} != 45.0"


def test_coincident_constraint():
    """Verify that two endpoints converge to identical coordinates"""
    l1 = Line((0.0, 0.0), (50.0, 50.0))
    l2 = Line((52.0, 48.0), (100.0, 100.0))
    c = Constraint(
        id="c_coin",
        constraint_type=ConstraintType.COINCIDENT,
        shape_ids=[l1.id, l2.id],
        point_indices=[1, 0]  # l1 end -> l2 start
    )
    solver = ConstraintSolver2D(tolerance=1e-4)
    success, shapes, msg = solver.solve([l1, l2], [c])

    assert success, f"Solver failed: {msg}"
    dist = math.sqrt((l1.end[0] - l2.start[0])**2 + (l1.end[1] - l2.start[1])**2)
    assert dist < 1e-3, f"Endpoints not coincident: dist={dist}"


def test_tangent_constraint():
    """Verify that a line segment adjusts to become tangent to a circle"""
    circle = Circle((50.0, 50.0), radius=25.0)
    # Line passing near top edge of circle
    line = Line((0.0, 80.0), (100.0, 80.0))
    c = Constraint(
        id="c_tangent",
        constraint_type=ConstraintType.TANGENT,
        shape_ids=[line.id, circle.id]
    )
    solver = ConstraintSolver2D(tolerance=1e-4)
    success, shapes, msg = solver.solve([line, circle], [c])

    assert success, f"Solver failed: {msg}"
    # Distance from center (50, 50) to line should equal radius (25)
    lx1, ly1, lx2, ly2 = line.start[0], line.start[1], line.end[0], line.end[1]
    cx, cy = circle.center
    num = abs((ly2 - ly1) * cx - (lx2 - lx1) * cy + lx2 * ly1 - ly2 * lx1)
    den = math.sqrt((ly2 - ly1)**2 + (lx2 - lx1)**2)
    dist = num / den
    assert abs(dist - circle.radius) < 1e-2, f"Line not tangent: dist={dist}, r={circle.radius}"
