"""
3D Reconstructor - CSG-based reconstruction pipeline from 2D orthographic views.
Runs in a background QThread to prevent UI blocking.
"""
import traceback
import numpy as np
import shapely.geometry as sg
import shapely.ops as so
import shapely.affinity
import trimesh
from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Dict, Tuple, Any, Optional
from ..engine.cad_engine import Shape

class ReconstructionWorker(QThread):
    """Background worker thread to perform CPU-intensive CSG reconstruction"""
    
    # Signals for communicating back to the GUI Thread
    finished_reconstruction = pyqtSignal(object)  # Emits trimesh.Trimesh
    error_occurred = pyqtSignal(str)              # Emits traceback string
    
    def __init__(self, top_shapes: List[Dict[str, Any]], front_shapes: List[Dict[str, Any]], side_shapes: List[Dict[str, Any]], angular_tolerance: float = 10.0, projection_type: str = '3rd_angle'):
        super().__init__()
        self.top_shapes = top_shapes
        self.front_shapes = front_shapes
        self.side_shapes = side_shapes
        self.angular_tolerance = angular_tolerance
        self.projection_type = projection_type

    def run_reconstruction(self, top_shapes: List[Shape], front_shapes: List[Shape], side_shapes: List[Shape], callback_finished, callback_error=None, angular_tolerance: float = 10.0, projection_type: str = '3rd_angle'):
        """Spawn ReconstructionWorker in a background thread to generate 3D mesh"""
        # Cancel any active running workers
        if self.worker is not None and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            
        # Serialize shapes list to dictionary before handoff (thread-safe copies)
        top_dicts = [s if isinstance(s, dict) else s.to_dict() for s in top_shapes]
        front_dicts = [s if isinstance(s, dict) else s.to_dict() for s in front_shapes]
        side_dicts = [s if isinstance(s, dict) else s.to_dict() for s in side_shapes]
        
        self.worker = ReconstructionWorker(top_dicts, front_dicts, side_dicts, angular_tolerance, projection_type)
        self.worker.finished_reconstruction.connect(callback_finished)
        if callback_error:
            self.worker.error_occurred.connect(callback_error)
            
        self.worker.start()
        
    def run(self):
        """Execute reconstruction pipeline"""
        try:
            print("CSG Reconstruction background thread started...")
            
            # 1. Compute 3D coordinate bounding limits for extrusions
            top_limits = self._get_view_bounds_3d(self.top_shapes, 'top', self.projection_type)
            front_limits = self._get_view_bounds_3d(self.front_shapes, 'front')
            side_limits = self._get_view_bounds_3d(self.side_shapes, 'side')
            
            # Extract bounds
            x_min_top, x_max_top, z_min_top, z_max_top = top_limits
            x_min_front, x_max_front, y_min_front, y_max_front = front_limits
            z_min_side, z_max_side, y_min_side, y_max_side = side_limits
            
            # Align boundaries globally
            x_min = min(x_min_top, x_min_front)
            x_max = max(x_max_top, x_max_front)
            y_min = min(y_min_front, y_min_side)
            y_max = max(y_max_front, y_max_side)
            z_min = min(z_min_top, z_min_side)
            z_max = max(z_max_top, z_max_side)
            
            # 2. Extract 2D profiles using Shapely (outer boundaries and subtractive holes)
            poly_top = self._extract_view_profile(self.top_shapes)
            poly_front = self._extract_view_profile(self.front_shapes)
            poly_side = self._extract_view_profile(self.side_shapes)
            
            extruded_meshes = []
            
            # 3. Perform extrusions and coordinate mappings using strict 4x4 matrices
            
            # Top view extrusion (along Y axis)
            if poly_top is not None and not poly_top.is_empty:
                h_y = y_max - y_min
                if h_y > 0.1:
                    # Mirror vertical coordinate input to preserve CCW winding order under reflection
                    poly_top_mirrored = shapely.affinity.scale(poly_top, yfact=-1.0, origin=(0, 0))
                    mesh_top = self._extrude_profile(poly_top_mirrored, h_y)
                    if mesh_top is not None:
                        # 4x4 matrix: local (u, v, w, 1) -> 3D (X, Y, Z, 1)
                        # X = u, Y = w + y_min, Z = -v (since we mirrored, -v restores correct Z)
                        # In third-angle layout the Top View is above the datum
                        # and the LHS view is to the right, so both represent
                        # positive physical depth. The previous fixed -Z mapping
                        # placed these profiles on opposite sides of the solid.
                        top_depth_sign = 1.0 if self.projection_type == '3rd_angle' else -1.0
                        M_top = np.array([
                            [1.0,  0.0, 0.0, 0.0],
                            [0.0,  0.0, 1.0, y_min],
                            [0.0, top_depth_sign, 0.0, 0.0],
                            [0.0,  0.0, 0.0, 1.0]
                        ])
                        v_local = mesh_top.vertices
                        v_hom = np.column_stack([v_local, np.ones(len(v_local))])
                        v_3d = (M_top @ v_hom.T).T[:, :3]
                        mesh_top.vertices = v_3d
                        mesh_top = self._prepare_mesh(mesh_top)
                        extruded_meshes.append(('top', mesh_top))
                    
            # Front view extrusion (along Z axis)
            if poly_front is not None and not poly_front.is_empty:
                h_z = z_max - z_min
                if h_z > 0.1:
                    # Front view projection is naturally right-handed, no mirror needed
                    mesh_front = self._extrude_profile(poly_front, h_z)
                    if mesh_front is not None:
                        # 4x4 matrix: local (u, v, w, 1) -> 3D (X, Y, Z, 1)
                        # X = u, Y = v, Z = w + z_min
                        M_front = np.array([
                            [1.0, 0.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0, 0.0],
                            [0.0, 0.0, 1.0, z_min],
                            [0.0, 0.0, 0.0, 1.0]
                        ])
                        v_local = mesh_front.vertices
                        v_hom = np.column_stack([v_local, np.ones(len(v_local))])
                        v_3d = (M_front @ v_hom.T).T[:, :3]
                        mesh_front.vertices = v_3d
                        mesh_front = self._prepare_mesh(mesh_front)
                        extruded_meshes.append(('front', mesh_front))
                    
            # Side view extrusion (along X axis)
            if poly_side is not None and not poly_side.is_empty:
                h_x = x_max - x_min
                if h_x > 0.1:
                    # Mirror vertical coordinate to preserve CCW handedness under X-Z swap
                    poly_side_mirrored = shapely.affinity.scale(poly_side, yfact=-1.0, origin=(0, 0))
                    mesh_side = self._extrude_profile(poly_side_mirrored, h_x)
                    if mesh_side is not None:
                        # 4x4 matrix: local (u, v, w, 1) -> 3D (X, Y, Z, 1)
                        # X = w + x_min, Y = -v, Z = u
                        M_side = np.array([
                            [0.0,  0.0, 1.0, x_min],
                            [0.0, -1.0, 0.0, 0.0],
                            [1.0,  0.0, 0.0, 0.0],
                            [0.0,  0.0, 0.0, 1.0]
                        ])
                        v_local = mesh_side.vertices
                        v_hom = np.column_stack([v_local, np.ones(len(v_local))])
                        v_3d = (M_side @ v_hom.T).T[:, :3]
                        mesh_side.vertices = v_3d
                        mesh_side = self._prepare_mesh(mesh_side)
                        extruded_meshes.append(('side', mesh_side))
                    
            # 4. Perform CSG Boolean Intersection
            if not extruded_meshes:
                self.finished_reconstruction.emit(None)
                return
                
            meshes_only = [m for name, m in extruded_meshes]
            
            if len(meshes_only) == 1:
                final_mesh = meshes_only[0]
            else:
                print(f"Intersecting {len(meshes_only)} extruded views...")
                final_mesh = self._boolean_intersection(meshes_only)
                
            # 5. Watertight repair and validation
            if final_mesh is not None and hasattr(final_mesh, 'faces') and len(final_mesh.faces) > 0 and getattr(final_mesh.faces, 'ndim', 0) == 2:
                print("Repairing reconstructed solid mesh...")
                try:
                    trimesh.repair.fill_holes(final_mesh)
                    trimesh.repair.fix_normals(final_mesh)
                    final_mesh.fill_holes()
                    final_mesh.fix_normals()
                    print(f"Watertight check: {getattr(final_mesh, 'is_watertight', False)}")
                except Exception as e:
                    print(f"Warning during final mesh repair: {e}")
                
            self.finished_reconstruction.emit(final_mesh)
            
        except Exception as e:
            tb = traceback.format_exc()
            print(f"Error during reconstruction: {e}\n{tb}")
            self.error_occurred.emit(tb)
 
    def _boolean_intersection(self, meshes: List[trimesh.Trimesh]) -> Optional[trimesh.Trimesh]:
        """Run a validated intersection with an engine fallback for backend variance."""
        if not meshes:
            return None
        for engine in ("manifold", None):
            try:
                result = (trimesh.boolean.intersection(meshes, engine=engine)
                          if engine else trimesh.boolean.intersection(meshes))
                if result is not None and hasattr(result, "faces") and len(result.faces) > 0:
                    return self._prepare_mesh(result)
            except Exception as exc:
                print(f"Boolean intersection failed with {engine or 'default'} backend: {exc}")
        try:
            result = meshes[0]
            for mesh in meshes[1:]:
                result = trimesh.boolean.intersection([result, mesh], engine="manifold")
                if result is None or len(result.faces) == 0:
                    return None
            return self._prepare_mesh(result)
        except Exception as exc:
            print(f"Pairwise boolean intersection failed: {exc}")
            return None

    @staticmethod
    def _normalize_polygonal(geometry):
        """Repair Shapely polygonal input and discard non-area geometry."""
        if geometry is None or geometry.is_empty:
            return None
        try:
            if not geometry.is_valid:
                geometry = geometry.buffer(0)
            if geometry.is_empty:
                return None
            if geometry.geom_type == "GeometryCollection":
                polygons = [g for g in geometry.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
                geometry = so.unary_union(polygons) if polygons else None
            if geometry is None or geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                return None
            return geometry if geometry.area > 1e-6 else None
        except Exception as exc:
            print(f"2D profile normalization failed: {exc}")
            return None
    def _prepare_mesh(self, mesh: trimesh.Trimesh) -> Optional[trimesh.Trimesh]:
        """Ensure mesh is watertight and has outward-pointing face normals (positive volume)"""
        if mesh is None or not hasattr(mesh, 'faces') or len(mesh.faces) == 0 or getattr(mesh.faces, 'ndim', 0) != 2:
            return None
        try:
            trimesh.repair.fill_holes(mesh)
            trimesh.repair.fix_normals(mesh)
            mesh.fill_holes()
            mesh.fix_normals()
            # Fallback orientation check
            if hasattr(mesh, 'volume') and mesh.volume < 0:
                mesh.invert()
                trimesh.repair.fix_normals(mesh)
                mesh.fix_normals()
        except Exception as e:
            print(f"Warning during mesh repair: {e}")
        return mesh

    def _extrude_profile(self, poly: sg.base.BaseGeometry, height: float) -> Optional[trimesh.Trimesh]:
        """Extrude a Shapely Polygon or MultiPolygon along local Z-axis by height"""
        if poly is None or poly.is_empty or getattr(poly, 'area', 0) <= 1e-6:
            return None
            
        if isinstance(poly, sg.Polygon):
            try:
                mesh = trimesh.creation.extrude_polygon(poly, height)
                if mesh is not None and hasattr(mesh, 'faces') and len(mesh.faces) > 0 and getattr(mesh.faces, 'ndim', 0) == 2:
                    return mesh
            except Exception as e:
                print(f"Error extruding single Polygon: {e}")
                return None
                
        elif isinstance(poly, sg.MultiPolygon):
            meshes = []
            for p in poly.geoms:
                if p is not None and not p.is_empty and getattr(p, 'area', 0) > 1e-6:
                    try:
                        m = trimesh.creation.extrude_polygon(p, height)
                        if m is not None and hasattr(m, 'faces') and len(m.faces) > 0 and getattr(m.faces, 'ndim', 0) == 2:
                            meshes.append(m)
                    except Exception as e:
                        print(f"Error extruding sub-polygon of MultiPolygon: {e}")
            if meshes:
                return trimesh.util.concatenate(meshes)
                
        return None

    def _get_view_bounds_3d(self, shapes: List[Dict[str, Any]], view_name: str, projection_type: str = '3rd_angle') -> Tuple[float, float, float, float]:
        """Compute bounds in the same coordinate system used by each extrusion."""
        if not shapes:
            return (-50.0, 50.0, -50.0, 50.0)

        horiz_vals = []
        vert_vals = []
        top_uses_positive_depth = view_name == 'top' and projection_type == '3rd_angle'

        for s in shapes:
            t = s.get('type')
            if t == 'rectangle':
                x, y, w, h = s['rect']
                horiz_vals.extend([x, x + w])
                vert_vals.extend([y, y + h] if top_uses_positive_depth else [-(y + h), -y])
            elif t == 'circle':
                cx, cy = s['center']
                r = s['radius']
                horiz_vals.extend([cx - r, cx + r])
                vert_vals.extend([cy - r, cy + r] if top_uses_positive_depth else [-cy - r, -cy + r])
            elif t == 'polygon':
                for p in s['points']:
                    horiz_vals.append(p[0])
                    vert_vals.append(p[1] if top_uses_positive_depth else -p[1])
            elif t == 'line':
                start, end = s['start'], s['end']
                horiz_vals.extend([start[0], end[0]])
                vert_vals.extend(([start[1], end[1]]) if top_uses_positive_depth else ([-start[1], -end[1]]))
            elif t == 'arc':
                cx, cy, r = s['center'][0], s['center'][1], s['radius']
                horiz_vals.extend([cx - r, cx + r])
                vert_vals.extend([cy - r, cy + r] if top_uses_positive_depth else [-cy - r, -cy + r])

        if not horiz_vals or not vert_vals:
            return (-50.0, 50.0, -50.0, 50.0)
        return (min(horiz_vals), max(horiz_vals), min(vert_vals), max(vert_vals))
    def _extract_view_profile(self, shapes: List[Dict[str, Any]]) -> Optional[sg.Polygon]:
        """Assemble outer silhouettes and nested subtractive loops into a single Shapely Polygon"""
        if not shapes:
            return None
            
        visible_polys = []
        hidden_polys = []
        visible_lines = []
        hidden_lines = []
        
        # 1. Convert drawing primitives to Shapely geometries
        for s in shapes:
            t = s.get('type')
            layer = s.get('layer', 'Visible')
            
            # Construction lines are drafting layout guides and are ignored in 3D reconstruction
            if layer == 'Construction':
                continue
                
            # Project canvas Y coordinates correctly to 3D projection space (multiply Y by -1)
            if t == 'rectangle':
                x, y, w, h = s['rect']
                poly = sg.box(x, -(y+h), x+w, -y)
                if layer == 'Hidden':
                    hidden_polys.append(poly)
                else:
                    visible_polys.append(poly)
                    
            elif t == 'circle':
                cx, cy = s['center']
                r = s['radius']
                q_segs = max(8, int(np.ceil(90.0 / self.angular_tolerance)))
                poly = sg.Point(cx, -cy).buffer(r, quad_segs=q_segs)
                if layer == 'Hidden':
                    hidden_polys.append(poly)
                else:
                    visible_polys.append(poly)
                    
            elif t == 'arc':
                cx, cy = s['center']
                r = s['radius']
                start_angle = s['start_angle']
                end_angle = s['end_angle']
                sweep = end_angle - start_angle
                if sweep < 0:
                    sweep += 360
                
                num_segs = max(4, int(np.ceil(sweep / self.angular_tolerance)))
                angles = np.radians(np.linspace(start_angle, start_angle + sweep, num_segs + 1))
                pts = [(cx + r * np.cos(a), -cy + r * np.sin(a)) for a in angles]
                arc_geom = sg.LineString(pts)
                if layer == 'Hidden':
                    hidden_lines.append(arc_geom)
                else:
                    visible_lines.append(arc_geom)
                    
            elif t == 'polygon':
                pts = [(p[0], -p[1]) for p in s['points']]
                if len(pts) >= 3:
                    poly = sg.Polygon(pts)
                    if layer == 'Hidden':
                        hidden_polys.append(poly)
                    else:
                        visible_polys.append(poly)
                        
            elif t == 'line':
                start = s['start']
                end = s['end']
                line_geom = sg.LineString([(start[0], -start[1]), (end[0], -end[1])])
                if layer == 'Hidden':
                    hidden_lines.append(line_geom)
                else:
                    visible_lines.append(line_geom)
                
        # 2. Support line polygonization for vector wireframe loops
        if visible_lines:
            visible_polys.extend(so.polygonize(so.unary_union(visible_lines)))
        if hidden_lines:
            hidden_polys.extend(so.polygonize(so.unary_union(hidden_lines)))

        visible_polys = [p for p in (self._normalize_polygonal(g) for g in visible_polys) if p is not None]
        hidden_polys = [p for p in (self._normalize_polygonal(g) for g in hidden_polys) if p is not None]
        if not visible_polys:
            return None

        # 3. Containment analysis for nested profiles (through-holes / inner loops)
        visible_polys.sort(key=lambda p: p.area, reverse=True)
        final_visible_list = []
        processed_indices = set()
        for i, outer_poly in enumerate(visible_polys):
            if i in processed_indices:
                continue
            temp_outer = outer_poly
            for j in range(i + 1, len(visible_polys)):
                if j in processed_indices:
                    continue
                inner_candidate = visible_polys[j]
                if temp_outer.contains(inner_candidate):
                    temp_outer = self._normalize_polygonal(temp_outer.difference(inner_candidate))
                    processed_indices.add(j)
            if temp_outer is not None and not temp_outer.is_empty:
                final_visible_list.append(temp_outer)
            processed_indices.add(i)

        # 4. Subtract explicitly hidden layer elements (pocket/hole profiles)
        final_profiles = []
        for vis_poly in final_visible_list:
            temp_poly = vis_poly
            for hid_poly in hidden_polys:
                if temp_poly.intersects(hid_poly):
                    temp_poly = self._normalize_polygonal(temp_poly.difference(hid_poly))
                    if temp_poly is None:
                        break
            if temp_poly is not None and not temp_poly.is_empty:
                final_profiles.append(temp_poly)
        if not final_profiles:
            return None

        # 5. Union all separate visible islands, then normalize once more so
        # extrusion never receives self-intersecting rings or zero-area fragments.
        return self._normalize_polygonal(so.unary_union(final_profiles))

class Reconstructor3D:
    """CSG reconstruction pipeline coordinator"""
    
    def __init__(self):
        self.current_mesh: Optional[trimesh.Trimesh] = None
        self.worker: Optional[ReconstructionWorker] = None
        
    def _get_view_bounds_3d(self, shapes: List[Dict[str, Any]], view_name: str) -> Tuple[float, float, float, float]:
        """Compute projection-space coordinates of a view's bounding limits"""
        if not shapes:
            return (-50.0, 50.0, -50.0, 50.0)
            
        horiz_vals = []
        vert_vals = []
        
        for s in shapes:
            t = s.get('type')
            if t == 'rectangle':
                x, y, w, h = s['rect']
                horiz_vals.extend([x, x + w])
                vert_vals.extend([-(y + h), -y])
            elif t == 'circle':
                cx, cy = s['center']
                r = s['radius']
                horiz_vals.extend([cx - r, cx + r])
                vert_vals.extend([-cy - r, -cy + r])
            elif t == 'polygon':
                for p in s['points']:
                    horiz_vals.append(p[0])
                    vert_vals.append(-p[1])
            elif t == 'line':
                start = s['start']
                end = s['end']
                horiz_vals.extend([start[0], end[0]])
                vert_vals.extend([-start[1], -end[1]])
                
        if not horiz_vals or not vert_vals:
            return (-50.0, 50.0, -50.0, 50.0)
            
        return (min(horiz_vals), max(horiz_vals), min(vert_vals), max(vert_vals))
        
    def run_reconstruction(self, top_shapes: List[Shape], front_shapes: List[Shape], side_shapes: List[Shape], callback_finished, callback_error=None, angular_tolerance: float = 10.0, projection_type: str = '3rd_angle'):
        """Spawn ReconstructionWorker in a background thread to generate 3D mesh"""
        # Cancel any active running workers
        if self.worker is not None and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            
        # Serialize shapes list to dictionary before handoff (thread-safe copies)
        top_dicts = [s if isinstance(s, dict) else s.to_dict() for s in top_shapes]
        front_dicts = [s if isinstance(s, dict) else s.to_dict() for s in front_shapes]
        side_dicts = [s if isinstance(s, dict) else s.to_dict() for s in side_shapes]
        
        self.worker = ReconstructionWorker(top_dicts, front_dicts, side_dicts, angular_tolerance, projection_type)
        self.worker.finished_reconstruction.connect(callback_finished)
        if callback_error:
            self.worker.error_occurred.connect(callback_error)
            
        self.worker.start()
        
    def export(self, mesh: trimesh.Trimesh, filename: str):
        """Export mesh to file (STL, OBJ, etc.)"""
        if mesh is None:
            raise ValueError("No mesh available for export")
        mesh.export(filename)
        print(f"Successfully exported 3D model to {filename}")
