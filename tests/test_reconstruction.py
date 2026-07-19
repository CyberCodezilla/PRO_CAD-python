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
