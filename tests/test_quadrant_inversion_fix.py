import pytest
from src.engine.cad_engine import CADEngine, Rectangle, Circle
from src.reconstruction.reconstructor import Reconstructor3D

def test_front_view_bottom_wheels_orientation():
    engine = CADEngine()

    # 1. Add Main Body to Front View (Q2: X in [-100, -20], Y in [-100, -40])
    # Local Height: v in [40, 100]
    body = Rectangle(rect=(-100.0, -100.0, 80.0, 60.0), layer="Visible")
    engine.add_shape(body, view="front")

    # 2. Add Wheels to Bottom of Front View (Q2: Y in [-40, -20])
    # Local Height: v in [20, 40] -> Strictly below the body
    wheel_left = Circle(center=(-80.0, -30.0), radius=10.0, layer="Visible")
    wheel_right = Circle(center=(-40.0, -30.0), radius=10.0, layer="Visible")
    engine.add_shape(wheel_left, view="front")
    engine.add_shape(wheel_right, view="front")

    # 3. Add Side View Depth Extrusion (Q1: X in [20, 40], Y in [-100, -20])
    side_body = Rectangle(rect=(20.0, -100.0, 20.0, 80.0), layer="Visible")
    engine.add_shape(side_body, view="side")

    # 4. Reconstruct 3D CSG Solid
    reconstructor = Reconstructor3D()
    mesh = reconstructor.reconstruct(engine.shapes)

    # 5. Assert Vertical Coordinates in 3D Space
    # Body Y bounds must be strictly higher than Wheel center Y coordinates
    wheel_left_3d_y = -(-30.0) # Expected 3D Y = 30.0
    body_top_3d_y = -(-100.0) # Expected 3D Y = 100.0

    assert mesh is not None
    assert mesh.bounds[1][1] > mesh.bounds[0][1] # Valid height
    assert mesh.bounds[0][1] <= 20.0 + 1e-3 # Lowest point is bottom of wheels
    assert mesh.bounds[1][1] >= 100.0 - 1e-3 # Highest point is top of body
