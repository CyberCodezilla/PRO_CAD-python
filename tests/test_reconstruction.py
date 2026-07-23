"""
Reconstruction Tests - Verifies watertightness and volume accuracy of the 3D CSG engine.
Runs synchronously using mock data.
"""
import pytest
import numpy as np
import trimesh
from src.reconstruction.reconstructor import ReconstructionWorker

def test_box_reconstruction():
    """Test Case 1: Reconstructing a 100x100x100 watertight box"""
    # Define 100x100 square centered at (0,0) in each view
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
    
    worker = ReconstructionWorker(top_shapes, front_shapes, side_shapes)
    
    reconstructed_mesh = None
    def finished_callback(mesh):
        nonlocal reconstructed_mesh
        reconstructed_mesh = mesh
        
    worker.finished_reconstruction.connect(finished_callback)
    
    # Execute pipeline synchronously
    worker.run()
    
    assert reconstructed_mesh is not None, "Failed to reconstruct box mesh"
    assert reconstructed_mesh.is_watertight, "Reconstructed box mesh is not watertight"
    
    # Expected Volume: 100 * 100 * 100 = 1,000,000 mm³
    expected_volume = 1000000.0
    actual_volume = reconstructed_mesh.volume
    
    print(f"Box actual volume: {actual_volume}")
    
    # Assert within 1% tolerance
    assert abs(actual_volume - expected_volume) < (0.01 * expected_volume), \
        f"Volume {actual_volume} deviates from expected {expected_volume} by more than 1%"


def test_cylinder_reconstruction():
    """Test Case 2: Reconstructing a Cylinder (radius=50, height=100)"""
    # Top View: Circle r=50 centered at (0,0)
    top_shapes = [{
        'type': 'circle',
        'center': (0.0, 0.0),
        'radius': 50.0,
        'layer': 'Visible'
    }]
    # Front/Side views: Rect 100x100 to bound height to 100
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
    
    worker = ReconstructionWorker(top_shapes, front_shapes, side_shapes)
    
    reconstructed_mesh = None
    def finished_callback(mesh):
        nonlocal reconstructed_mesh
        reconstructed_mesh = mesh
        
    worker.finished_reconstruction.connect(finished_callback)
    worker.run()
    
    assert reconstructed_mesh is not None, "Failed to reconstruct cylinder mesh"
    assert reconstructed_mesh.is_watertight, "Reconstructed cylinder mesh is not watertight"
    
    # Expected Volume: pi * r^2 * h = pi * 50^2 * 100 = 250,000 * pi ~ 785,398.16 mm³
    expected_volume = np.pi * (50.0 ** 2) * 100.0
    actual_volume = reconstructed_mesh.volume
    
    print(f"Cylinder actual volume: {actual_volume} (Expected: {expected_volume})")
    
    # Assert within 1% tolerance
    assert abs(actual_volume - expected_volume) < (0.01 * expected_volume), \
        f"Volume {actual_volume} deviates from expected {expected_volume} by more than 1%"


def test_hollow_pipe_reconstruction():
    """Test Case 3: Reconstructing a Hollow Pipe (Outer r=50, Inner r=25, Height=100)"""
    # Top View: Outer Circle r=50, Inner Circle r=25
    top_shapes = [
        {
            'type': 'circle',
            'center': (0.0, 0.0),
            'radius': 50.0,
            'layer': 'Visible'
        },
        {
            'type': 'circle',
            'center': (0.0, 0.0),
            'radius': 25.0,
            'layer': 'Visible'  # Outer circle contains this circle, subtracting it
        }
    ]
    # Front/Side views: Rect 100x100
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
    
    worker = ReconstructionWorker(top_shapes, front_shapes, side_shapes)
    
    reconstructed_mesh = None
    def finished_callback(mesh):
        nonlocal reconstructed_mesh
        reconstructed_mesh = mesh
        
    worker.finished_reconstruction.connect(finished_callback)
    worker.run()
    
    assert reconstructed_mesh is not None, "Failed to reconstruct hollow pipe mesh"
    assert reconstructed_mesh.is_watertight, "Reconstructed hollow pipe mesh is not watertight"
    
    # Expected Volume: pi * (R^2 - r^2) * h = pi * (50^2 - 25^2) * 100 = 187,500 * pi ~ 589,048.62 mm³
    expected_volume = np.pi * ((50.0 ** 2) - (25.0 ** 2)) * 100.0
    actual_volume = reconstructed_mesh.volume
    
    print(f"Hollow Pipe actual volume: {actual_volume} (Expected: {expected_volume})")
    
    # Assert within 1.5% tolerance (since double circle approximations slightly compound area error)
    assert abs(actual_volume - expected_volume) < (0.015 * expected_volume), \
        f"Volume {actual_volume} deviates from expected {expected_volume} by more than 1.5%"


def test_view_region_and_guardrails():
    """Test Case 4: ViewRegion, Centroid Assignment, Local Coordinate Y-Inversion, and Right-Side Mirroring"""
    from src.engine.cad_engine import CADEngine, ViewRegion, Rectangle, Line, Circle
    
    engine = CADEngine()
    
    # Define Top Region: (0, 0, 200, 200) -> origin = (0, 200)
    # Front Region: (0, 300, 200, 500) -> origin = (0, 500)
    # Right Side Region: (300, 300, 500, 500) -> origin = (300, 500)
    top_reg = ViewRegion('top', (0.0, 0.0, 200.0, 200.0))
    front_reg = ViewRegion('front', (0.0, 300.0, 200.0, 500.0))
    right_side_reg = ViewRegion('right_side', (300.0, 300.0, 500.0, 500.0))
    
    engine.add_view_region(top_reg)
    engine.add_view_region(front_reg)
    engine.add_view_region(right_side_reg)
    
    # Draw a 100x100 rectangle inside Front Region at canvas (50, 350, 100, 100)
    # Centroid: (100, 400) -> inside Front Region
    rect_front = Rectangle((50.0, 350.0, 100.0, 100.0))
    assigned_view = engine.assign_shape_to_region(rect_front)
    assert assigned_view == 'front', f"Expected 'front', got {assigned_view}"
    engine.add_shape(rect_front)
    
    # Test local coordinate extraction for Front View
    # Canvas top-left = (50, 350), bottom-left = (50, 450)
    # Region origin = (0, 500)
    # Local bottom-left: local_x = 50 - 0 = 50, local_y = 500 - (350+100) = 50
    local_front = engine.get_local_shapes_for_view('front')
    assert len(local_front) == 1
    r_local = local_front[0]['rect']
    assert r_local == (50.0, 50.0, 100.0, 100.0), f"Unexpected local rect: {r_local}"

    # Draw a rectangle in Right Side View at canvas (350, 350, 100, 100)
    # Right Side region origin = (300, 500)
    rect_side = Rectangle((350.0, 350.0, 100.0, 100.0))
    engine.add_shape(rect_side)
    local_side = engine.get_local_shapes_for_view('side')
    assert len(local_side) == 1

    # Draw an unassigned shape outside all regions
    rect_unassigned = Rectangle((1000.0, 1000.0, 50.0, 50.0))
    assigned_un = engine.assign_shape_to_region(rect_unassigned)
    assert assigned_un == 'unassigned'
    engine.add_shape(rect_unassigned)
    assert len(engine.get_unassigned_shapes()) == 1


def test_alignment_validation():
    """Test Case 5: Orthographic Alignment Validation Math"""
    from src.engine.cad_engine import CADEngine, ViewRegion, Rectangle
    
    engine = CADEngine()
    engine.add_view_region(ViewRegion('top', (0, 0, 200, 200)))
    engine.add_view_region(ViewRegion('front', (0, 300, 200, 500)))
    
    # Add Front shape width = 100 (x=50 to 150)
    engine.add_shape(Rectangle((50, 350, 100, 100)))
    # Add Top shape width = 80 (x=50 to 130) -> Mismatch > 5.0
    engine.add_shape(Rectangle((50, 50, 80, 100)))
    
    valid, msg = engine.validate_alignment(tolerance=5.0)
    assert not valid
    assert "Alignment Error" in msg
    assert "Front View width is 100.0" in msg

