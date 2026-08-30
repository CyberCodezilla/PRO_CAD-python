"""
CAD Engine - Core data model and shape management with history stack & unified orthographic regions.
"""
import uuid
import numpy as np
from typing import List, Dict, Tuple, Any, Optional
from .constraint_solver import Constraint, ConstraintType, ConstraintSolver2D
from .gdt_engine import DatumFeature, FeatureControlFrame, GDTSymbol, MaterialModifier
from .section_engine import CuttingPlane, SectionView, SectionType

class Shape:
    """Base class for all drawing shapes"""
    
    def __init__(self, shape_type: str, layer: str = "Visible", shape_id: str = None):
        self.id = shape_id if shape_id else str(uuid.uuid4())
        self.type = shape_type
        self.layer = layer  # "Visible" (solid), "Hidden" (dashed), "Construction" (faint)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize shape to dictionary"""
        raise NotImplementedError("Subclasses must implement to_dict")

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'Shape':
        """Deserialize shape from dictionary"""
        shape_type = d.get('type')
        layer = d.get('layer', 'Visible')
        shape_id = d.get('id')
        
        if shape_type == 'line':
            return Line(tuple(d['start']), tuple(d['end']), layer, shape_id,
                        d.get('feature_type', 'default'), float(d.get('chamfer_dist', 0.0)), float(d.get('chamfer_angle', 45.0)))
        elif shape_type == 'rectangle':
            return Rectangle(tuple(d['rect']), layer, shape_id)
        elif shape_type == 'circle':
            return Circle(tuple(d['center']), float(d['radius']), layer, shape_id)
        elif shape_type == 'polygon':
            points = [tuple(p) for p in d['points']]
            return Polygon(points, layer, shape_id)
        elif shape_type == 'arc':
            return Arc(tuple(d['center']), float(d['radius']), float(d['start_angle']), float(d['end_angle']), layer, shape_id,
                       d.get('feature_type', 'default'), float(d.get('fillet_radius', float(d['radius']))))
        elif shape_type == 'dimension':
            return Dimension(d['dim_type'], tuple(d['start_pt']), tuple(d['end_pt']), tuple(d['label_pt']), d['text'], d.get('target_shape_ids', []), layer, shape_id)
        
        raise ValueError(f"Unknown shape type: {shape_type}")


class Line(Shape):
    """Line segment primitive"""
    
    def __init__(self, start: Tuple[float, float], end: Tuple[float, float], layer: str = "Visible", shape_id: str = None,
                 feature_type: str = "default", chamfer_dist: float = 0.0, chamfer_angle: float = 45.0):
        super().__init__('line', layer, shape_id)
        self.start = start  # (x, y)
        self.end = end      # (x, y)
        self.feature_type = feature_type      # 'default', 'chamfer'
        self.chamfer_dist = chamfer_dist
        self.chamfer_angle = chamfer_angle

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'start': self.start,
            'end': self.end,
            'feature_type': self.feature_type,
            'chamfer_dist': self.chamfer_dist,
            'chamfer_angle': self.chamfer_angle
        }


class Rectangle(Shape):
    """Rectangle primitive"""
    
    def __init__(self, rect: Tuple[float, float, float, float], layer: str = "Visible", shape_id: str = None):
        super().__init__('rectangle', layer, shape_id)
        self.rect = rect    # (x, y, w, h)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'rect': self.rect
        }


class Circle(Shape):
    """Circle primitive"""
    
    def __init__(self, center: Tuple[float, float], radius: float, layer: str = "Visible", shape_id: str = None):
        super().__init__('circle', layer, shape_id)
        self.center = center    # (x, y)
        self.radius = radius

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'center': self.center,
            'radius': self.radius
        }


class Polygon(Shape):
    """Closed polygon primitive"""
    
    def __init__(self, points: List[Tuple[float, float]], layer: str = "Visible", shape_id: str = None):
        super().__init__('polygon', layer, shape_id)
        self.points = points    # list of (x, y)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'points': self.points
        }


class Arc(Shape):
    """Circular arc primitive"""
    
    def __init__(self, center: Tuple[float, float], radius: float, start_angle: float, end_angle: float, layer: str = "Visible", shape_id: str = None,
                 feature_type: str = "default", fillet_radius: float = 0.0):
        super().__init__('arc', layer, shape_id)
        self.center = center          # (x, y)
        self.radius = radius
        self.start_angle = start_angle # in degrees (0-360)
        self.end_angle = end_angle     # in degrees (0-360)
        self.feature_type = feature_type      # 'default', 'fillet'
        self.fillet_radius = fillet_radius if fillet_radius > 0.0 else radius

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'center': self.center,
            'radius': self.radius,
            'start_angle': self.start_angle,
            'end_angle': self.end_angle,
            'feature_type': self.feature_type,
            'fillet_radius': self.fillet_radius
        }


class Dimension(Shape):
    """Associative dimension primitive"""
    
    def __init__(self, dim_type: str, start_pt: Tuple[float, float], end_pt: Tuple[float, float], label_pt: Tuple[float, float], text: str, target_shape_ids: List[str] = None, layer: str = "Construction", shape_id: str = None):
        super().__init__('dimension', layer, shape_id)
        self.dim_type = dim_type              # 'linear', 'aligned', 'angular', 'radial'
        self.start_pt = start_pt              # (x, y)
        self.end_pt = end_pt                  # (x, y)
        self.label_pt = label_pt              # (x, y)
        self.text = text                      # Label string
        self.target_shape_ids = target_shape_ids if target_shape_ids else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'dim_type': self.dim_type,
            'start_pt': self.start_pt,
            'end_pt': self.end_pt,
            'label_pt': self.label_pt,
            'text': self.text,
            'target_shape_ids': self.target_shape_ids
        }


class ViewRegion:
    """Defined region on the unified orthographic drafting sheet"""
    
    def __init__(self, view_type: str, bounds: Tuple[float, float, float, float], region_id: str = None):
        """
        view_type: 'top', 'front', 'side', 'left_side', 'right_side', 'lhs', 'rhs'
        bounds: (min_x, min_y, max_x, max_y)
        """
        self.id = region_id if region_id else str(uuid.uuid4())
        self.view_type = view_type.lower()
        
        # Standardize view_type names
        if self.view_type in ['top view', 'top']:
            self.view_type = 'top'
        elif self.view_type in ['front view', 'front']:
            self.view_type = 'front'
        elif self.view_type in ['left side view', 'left side', 'left_side', 'lhs view', 'lhs', 'side', 'side view']:
            self.view_type = 'left_side'
        elif self.view_type in ['right side view', 'right side', 'right_side', 'rhs view', 'rhs']:
            self.view_type = 'right_side'
            
        x1, y1, x2, y2 = bounds
        self.min_x = float(min(x1, x2))
        self.min_y = float(min(y1, y2))
        self.max_x = float(max(x1, x2))
        self.max_y = float(max(y1, y2))
        
        # Guardrail 1: Origin defined as Bottom-Left corner (0,0 if infinite quadrant)
        if self.min_x <= -10000.0 or self.max_x >= 10000.0:
            self.origin = (0.0, 0.0)
        else:
            self.origin = (self.min_x, self.max_y)

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def contains_point(self, pt: Tuple[float, float]) -> bool:
        """Check if 2D canvas point lies inside region bounds"""
        x, y = pt
        return (self.min_x <= x <= self.max_x) and (self.min_y <= y <= self.max_y)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'view_type': self.view_type,
            'bounds': (self.min_x, self.min_y, self.max_x, self.max_y),
            'origin': self.origin
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'ViewRegion':
        return ViewRegion(d['view_type'], tuple(d['bounds']), d.get('id'))


def get_shape_centroid(shape: Shape) -> Tuple[float, float]:
    """Guardrail 3: Calculate 2D centroid of a shape"""
    if isinstance(shape, Line):
        return ((shape.start[0] + shape.end[0]) / 2.0, (shape.start[1] + shape.end[1]) / 2.0)
    elif isinstance(shape, Rectangle):
        x, y, w, h = shape.rect
        return (x + w / 2.0, y + h / 2.0)
    elif isinstance(shape, Circle) or isinstance(shape, Arc):
        return shape.center
    elif isinstance(shape, Polygon):
        if not shape.points:
            return (0.0, 0.0)
        xs = [p[0] for p in shape.points]
        ys = [p[1] for p in shape.points]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    elif isinstance(shape, Dimension):
        return ((shape.start_pt[0] + shape.end_pt[0]) / 2.0, (shape.start_pt[1] + shape.end_pt[1]) / 2.0)
    return (0.0, 0.0)


class CADEngine:
    """Core CAD engine for managing shapes, view regions, and drawing operations with undo/redo"""
    
    def __init__(self):
        self.shapes: Dict[str, List[Shape]] = {
            'top': [],
            'front': [],
            'side': [],
            'unassigned': []
        }
        self.view_regions: Dict[str, ViewRegion] = {}
        self.constraints: List[Constraint] = []
        self.constraint_solver = ConstraintSolver2D()
        self.datums: Dict[str, DatumFeature] = {}
        self.feature_control_frames: Dict[str, FeatureControlFrame] = {}
        self.cutting_planes: Dict[str, CuttingPlane] = {}
        self.section_views: Dict[str, SectionView] = {}
        self.active_tool: str = 'select'
        self.active_layer: str = 'Visible'  # 'Visible', 'Hidden', 'Construction'
        self.active_view_mode: str = 'auto'  # 'auto', 'top', 'front', 'left_side', 'right_side'
        
        # Pre-initialize standard orthographic quadrant view regions on sheet
        self.init_default_quadrant_regions()

        self.history: List[Tuple[str, Dict[str, Any]]] = []
        self.history_index: int = -1
        self.max_history: int = 100
        
        # Save baseline empty state
        self._save_state("Initial State")
        
    def init_default_quadrant_regions(self):
        """Initialize standard 4-quadrant orthographic drafting sheet layout (First-Angle / European standard)"""
        # Quadrant II (Top-Left): Front View (XY Elevation)
        self.view_regions['front'] = ViewRegion('front', (-50000.0, -50000.0, 0.0, 0.0))
        # Quadrant I (Top-Right): Side View (ZY Profile / Elevation)
        self.view_regions['side'] = ViewRegion('left_side', (0.0, -50000.0, 50000.0, 0.0))
        # Quadrant III (Bottom-Left): Top View (XZ Plan)
        self.view_regions['top'] = ViewRegion('top', (-50000.0, 0.0, 0.0, 50000.0))

    def set_active_tool(self, tool_name: str):
        """Set active drawing tool"""
        self.active_tool = tool_name
        
    def set_active_layer(self, layer_name: str):
        """Set active drawing layer ('Visible', 'Hidden', 'Construction', 'Centerline')"""
        self.active_layer = layer_name

    def apply_autofix(self, diagnostic) -> bool:
        """Apply mathematical auto-fix for a specific diagnostic suggestion"""
        if not diagnostic or not getattr(diagnostic, 'fix_action', None):
            return False
            
        action = diagnostic.fix_action
        data = diagnostic.fix_data or {}

        if action == 'auto_fix_tap_drill':
            target_r = data.get('target_radius')
            shape_id = data.get('shape_id')
            if target_r and shape_id:
                for v in self.shapes.values():
                    for s in v:
                        if s.id == shape_id and isinstance(s, Circle):
                            s.radius = float(target_r)
                            self._save_state(f"Auto-Fix: Correct Tap Drill Radius to {target_r:.2f}mm")
                            return True

        elif action in ('CNC_ADD_CORNER_FILLET', 'auto_add_corner_fillet'):
            shape_id = data.get('shape_id')
            rec_r = data.get('recommended_radius', 1.6)
            if shape_id:
                for vname, slist in self.shapes.items():
                    for idx, s in enumerate(slist):
                        if s.id == shape_id:
                            if isinstance(s, Rectangle):
                                rx, ry, rw, rh = s.rect
                                pts = [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)]
                                new_poly = Polygon(pts, layer=s.layer)
                                new_poly.id = s.id
                                setattr(new_poly, 'corner_fillet_radius', rec_r)
                                slist[idx] = new_poly
                            elif isinstance(s, Polygon):
                                setattr(s, 'corner_fillet_radius', rec_r)
                            self._save_state(f"Auto-Fix: Add CNC Corner Fillet R{rec_r:.1f}mm")
                            return True

        elif action in ('SHEET_EXPAND_BEND_RADIUS', 'auto_expand_bend_radius'):
            shape_id = data.get('shape_id')
            target_r = data.get('target_radius')
            if shape_id and target_r:
                for vname, slist in self.shapes.items():
                    for s in slist:
                        if s.id == shape_id and isinstance(s, Arc):
                            s.radius = float(target_r)
                            self._save_state(f"Auto-Fix: Expand Bend Radius to {target_r:.1f}mm")
                            return True

        elif action == 'auto_scale_top_width':
            target_w = data.get('target_width')
            curr_w = data.get('current_width')
            if target_w and curr_w and curr_w > 0:
                scale_x = target_w / curr_w
                top_shapes = self.shapes.get('top', [])
                if top_shapes:
                    min_x = min([s.rect[0] if isinstance(s, Rectangle) else (s.center[0] - s.radius if isinstance(s, Circle) else s.start[0]) for s in top_shapes])
                    for s in top_shapes:
                        if isinstance(s, Line):
                            s.start = (min_x + (s.start[0] - min_x) * scale_x, s.start[1])
                            s.end = (min_x + (s.end[0] - min_x) * scale_x, s.end[1])
                        elif isinstance(s, Rectangle):
                            x, y, w, h = s.rect
                            s.rect = (min_x + (x - min_x) * scale_x, y, w * scale_x, h)
                        elif isinstance(s, Circle):
                            cx, cy = s.center
                            s.center = (min_x + (cx - min_x) * scale_x, cy)
                            s.radius = s.radius * scale_x
                    self._save_state("Auto-Fix: Scale Top View Width")
                    return True
                    
        elif action == 'auto_scale_side_height':
            target_h = data.get('target_height')
            curr_h = data.get('current_height')
            if target_h and curr_h and curr_h > 0:
                scale_y = target_h / curr_h
                side_shapes = self.shapes.get('side', [])
                if side_shapes:
                    min_y = min([s.rect[1] if isinstance(s, Rectangle) else (s.center[1] - s.radius if isinstance(s, Circle) else s.start[1]) for s in side_shapes])
                    for s in side_shapes:
                        if isinstance(s, Line):
                            s.start = (s.start[0], min_y + (s.start[1] - min_y) * scale_y)
                            s.end = (s.end[0], min_y + (s.end[1] - min_y) * scale_y)
                        elif isinstance(s, Rectangle):
                            x, y, w, h = s.rect
                            s.rect = (x, min_y + (y - min_y) * scale_y, w, h * scale_y)
                        elif isinstance(s, Circle):
                            cx, cy = s.center
                            s.center = (cx, min_y + (cy - min_y) * scale_y)
                            s.radius = s.radius * scale_y
                    self._save_state("Auto-Fix: Scale Side View Height")
                    return True

        elif action == 'auto_scale_side_depth':
            target_d = data.get('target_depth')
            curr_d = data.get('current_depth')
            if target_d and curr_d and curr_d > 0:
                scale_x = target_d / curr_d
                side_shapes = self.shapes.get('side', [])
                if side_shapes:
                    min_x = min([s.rect[0] if isinstance(s, Rectangle) else (s.center[0] - s.radius if isinstance(s, Circle) else s.start[0]) for s in side_shapes])
                    for s in side_shapes:
                        if isinstance(s, Line):
                            s.start = (min_x + (s.start[0] - min_x) * scale_x, s.start[1])
                            s.end = (min_x + (s.end[0] - min_x) * scale_x, s.end[1])
                        elif isinstance(s, Rectangle):
                            x, y, w, h = s.rect
                            s.rect = (min_x + (x - min_x) * scale_x, y, w * scale_x, h)
                        elif isinstance(s, Circle):
                            cx, cy = s.center
                            s.center = (min_x + (cx - min_x) * scale_x, cy)
                            s.radius = s.radius * scale_x
                    self._save_state("Auto-Fix: Scale Side View Depth")
                    return True

        return False

    def set_active_view_mode(self, view_mode: str):
        """Set active view mode ('auto', 'top', 'front', 'left_side', 'right_side', 'side')"""
        mode = view_mode.lower()
        if mode in ['lhs', 'lhs view', 'left side view', 'left_side']:
            self.active_view_mode = 'left_side'
        elif mode in ['rhs', 'rhs view', 'right side view', 'right_side']:
            self.active_view_mode = 'right_side'
        elif mode in ['top', 'top view']:
            self.active_view_mode = 'top'
        elif mode in ['front', 'front view']:
            self.active_view_mode = 'front'
        else:
            self.active_view_mode = 'auto'

    def add_view_region(self, region: ViewRegion):
        """Add or update a ViewRegion and re-assign existing shapes"""
        key = 'side' if region.view_type in ['left_side', 'right_side'] else region.view_type
        self.view_regions[key] = region
        self.reassign_all_shapes()
        self._save_state(f"Add {region.view_type.replace('_', ' ').title()} Region")

    def remove_view_region(self, view_key: str):
        """Remove a ViewRegion"""
        if view_key in self.view_regions:
            del self.view_regions[view_key]
            self.reassign_all_shapes()
            self._save_state(f"Remove {view_key.capitalize()} Region")

    def assign_shape_to_region(self, shape: Shape) -> str:
        """
        Assign a shape to a ViewRegion based on its centroid:
        - Checks explicit user-defined ViewRegions first if present and finite
        - Falls back to First-Angle standard quadrants:
          * Cx <= 0 and Cy <= 0 -> 'front' (Quadrant II)
          * Cx >= 0 and Cy <= 0 -> 'side' (Quadrant I)
          * Cx <= 0 and Cy >= 0 -> 'top' (Quadrant III)
        """
        centroid = get_shape_centroid(shape)
        # Check custom/finite regions first
        for key, region in self.view_regions.items():
            if region.min_x > -10000.0 and region.max_x < 10000.0:
                if region.contains_point(centroid):
                    return key
        cx, cy = centroid
        if cx <= 0.0 and cy <= 0.0:
            return 'front'
        elif cx >= 0.0 and cy <= 0.0:
            return 'side'
        elif cx <= 0.0 and cy >= 0.0:
            return 'top'
        return 'unassigned'
        
    def add_shape(self, shape: Shape, view: Optional[str] = None):
        """Add a shape to the specified view, active view mode, or auto-assign via centroid"""
        target_view = view
        if not target_view:
            if self.active_view_mode != 'auto':
                target_view = 'side' if self.active_view_mode in ['left_side', 'right_side'] else self.active_view_mode
                # Ensure region matches view mode if user explicitly selected LHS/RHS
                if self.active_view_mode in ['left_side', 'right_side'] and 'side' in self.view_regions:
                    self.view_regions['side'].view_type = self.active_view_mode
            else:
                target_view = self.assign_shape_to_region(shape)
            
        if target_view not in self.shapes:
            self.shapes[target_view] = []
            
        self.shapes[target_view].append(shape)
        self._save_state(f"Draw {shape.type.capitalize()} on {self.active_layer} in {target_view.capitalize()} View")

    def reassign_all_shapes(self):
        """Re-evaluate region assignment for all existing shapes based on centroid"""
        all_existing_shapes = []
        for key in list(self.shapes.keys()):
            all_existing_shapes.extend(self.shapes[key])
            self.shapes[key] = []
            
        self.shapes['unassigned'] = []
        
        for shape in all_existing_shapes:
            target_view = self.assign_shape_to_region(shape)
            if target_view not in self.shapes:
                self.shapes[target_view] = []
            self.shapes[target_view].append(shape)
            
    def remove_shape(self, shape_id: str, view: Optional[str] = None) -> bool:
        """Remove a shape by ID with cascade cleanup for attached Datums and FCFs (Guardrail #2)"""
        views_to_search = [view] if view and view in self.shapes else list(self.shapes.keys())
        removed = False
        
        for v in views_to_search:
            initial_len = len(self.shapes[v])
            self.shapes[v] = [s for s in self.shapes[v] if s.id != shape_id]
            if len(self.shapes[v]) < initial_len:
                removed = True

        if removed:
            self._cleanup_orphaned_gdt_references(shape_id)
            self._save_state(f"Remove Shape {shape_id}")
            return True
        return False

    def _cleanup_orphaned_gdt_references(self, deleted_shape_id: str):
        """Clean up or unlink any DatumFeature or FeatureControlFrame attached to a deleted shape (Guardrail #2)"""
        for d in self.datums.values():
            if d.target_shape_id == deleted_shape_id:
                d.target_shape_id = None

        for fcf in self.feature_control_frames.values():
            if fcf.target_shape_id == deleted_shape_id:
                fcf.target_shape_id = None
        
    def get_shapes(self, view: str) -> List[Shape]:
        """Get all shapes for a view"""
        return self.shapes.get(view, [])

    def get_unassigned_shapes(self) -> List[Shape]:
        """Get shapes not inside any ViewRegion"""
        return self.shapes.get('unassigned', [])
        
    def clear_view(self, view: str):
        """Clear all shapes from a view"""
        if view in self.shapes:
            self.shapes[view] = []
            self._save_state(f"Clear {view.capitalize()} View")
            
    def clear_all(self):
        """Clear all shapes and re-init default regions"""
        self.shapes = {
            'top': [],
            'front': [],
            'side': [],
            'unassigned': []
        }
        self.view_regions = {}
        self.datums = {}
        self.feature_control_frames = {}
        self.init_default_quadrant_regions()
        self.history = []
        self.history_index = -1
        self._save_state("Clear All")

    def add_datum_feature(self, datum: DatumFeature):
        """Register a datum feature on the drafting sheet"""
        self.datums[datum.id] = datum
        self._save_state(f"Add Datum [-{datum.label}-]")

    def remove_datum_feature(self, datum_id: str) -> bool:
        """Remove a datum feature by ID"""
        if datum_id in self.datums:
            d = self.datums.pop(datum_id)
            self._save_state(f"Remove Datum [-{d.label}-]")
            return True
        return False

    def get_datums(self, view: Optional[str] = None) -> List[DatumFeature]:
        """Get all datums or filtered by view"""
        if view:
            return [d for d in self.datums.values() if d.view == view]
        return list(self.datums.values())

    def add_feature_control_frame(self, fcf: FeatureControlFrame):
        """Register a feature control frame annotation"""
        self.feature_control_frames[fcf.id] = fcf
        self._save_state(f"Add FCF [{fcf.symbol.value}]")

    def remove_feature_control_frame(self, fcf_id: str) -> bool:
        """Remove a feature control frame by ID"""
        if fcf_id in self.feature_control_frames:
            fcf = self.feature_control_frames.pop(fcf_id)
            self._save_state(f"Remove FCF [{fcf.symbol.value}]")
            return True
        return False

    def get_feature_control_frames(self, view: Optional[str] = None) -> List[FeatureControlFrame]:
        """Get all FCFs or filtered by view"""
        if view:
            return [f for f in self.feature_control_frames.values() if f.view == view]
        return list(self.feature_control_frames.values())

    def add_cutting_plane(self, cp: CuttingPlane):
        """Register a cutting plane annotation on drafting view"""
        self.cutting_planes[cp.id] = cp
        self._save_state(f"Add Cutting Plane {cp.label}—{cp.label}")

    def remove_cutting_plane(self, cp_id: str) -> bool:
        """Remove cutting plane by ID"""
        if cp_id in self.cutting_planes:
            cp = self.cutting_planes.pop(cp_id)
            # Cascade remove associated section views
            self.section_views = {k: sv for k, sv in self.section_views.items() if sv.cutting_plane_id != cp_id}
            self._save_state(f"Remove Cutting Plane {cp.label}—{cp.label}")
            return True
        return False

    def get_cutting_planes(self, view: Optional[str] = None) -> List[CuttingPlane]:
        """Get all cutting planes or filtered by view"""
        if view:
            return [cp for cp in self.cutting_planes.values() if cp.view == view]
        return list(self.cutting_planes.values())

    def add_section_view(self, sv: SectionView):
        """Register a section view"""
        self.section_views[sv.id] = sv
        self._save_state(f"Add Section View {sv.id}")

    def remove_section_view(self, sv_id: str) -> bool:
        """Remove section view by ID"""
        if sv_id in self.section_views:
            self.section_views.pop(sv_id)
            self._save_state(f"Remove Section View {sv_id}")
            return True
        return False

    def get_section_views(self) -> List[SectionView]:
        """Get all registered section views"""
        return list(self.section_views.values())
        
    def undo(self) -> Tuple[bool, str]:
        """Undo last action"""
        if self.history_index > 0:
            undone_desc = self.history[self.history_index][0]
            self.history_index -= 1
            self._load_state_from_history()
            return True, undone_desc
        return False, ""
            
    def redo(self) -> Tuple[bool, str]:
        """Redo last undone action"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self._load_state_from_history()
            redone_desc = self.history[self.history_index][0]
            return True, redone_desc
        return False, ""
            
    def add_constraint(self, constraint: Constraint):
        """Add a geometric constraint and solve immediately"""
        self.constraints = [c for c in self.constraints if c.id != constraint.id]
        self.constraints.append(constraint)
        self.solve_constraints()
        self._save_state(f"Add {constraint.constraint_type.value.capitalize()} Constraint")

    def remove_constraint(self, constraint_id: str) -> bool:
        """Remove a constraint by ID"""
        initial_len = len(self.constraints)
        self.constraints = [c for c in self.constraints if c.id != constraint_id]
        if len(self.constraints) < initial_len:
            self._save_state("Remove Constraint")
            return True
        return False

    def get_constraints_for_shape(self, shape_id: str) -> List[Constraint]:
        """Retrieve all constraints affecting a specific shape"""
        return [c for c in self.constraints if shape_id in c.shape_ids]

    def detect_and_tag_corner_blends(self, view: str):
        """Automatically identify 2D corner blend arcs and chamfer bevels and tag them semantically"""
        if view not in self.shapes:
            return
        for s in self.shapes[view]:
            if isinstance(s, Arc):
                sweep = abs(s.end_angle - s.start_angle)
                if 70.0 <= sweep <= 110.0 or 250.0 <= sweep <= 290.0:
                    s.feature_type = 'fillet'
                    s.fillet_radius = s.radius
            elif isinstance(s, Line):
                dx = abs(s.end[0] - s.start[0])
                dy = abs(s.end[1] - s.start[1])
                length = (dx*dx + dy*dy)**0.5
                if dx > 1.0 and dy > 1.0 and abs(dx - dy) / max(dx, dy) < 0.15 and length < 60.0:
                    s.feature_type = 'chamfer'
                    s.chamfer_dist = length / 1.4142
                    s.chamfer_angle = 45.0

    def solve_constraints(self) -> Tuple[bool, str]:
        """Execute 2D parametric constraint solver across all shapes"""
        if not self.constraints:
            return True, "No constraints to solve."
        all_shapes = []
        for v in self.shapes.values():
            all_shapes.extend(v)
        success, updated, msg = self.constraint_solver.solve(all_shapes, self.constraints)
        return success, msg

    def _save_state(self, description: str = "State Change"):
        """Save current state for undo/redo"""
        for view in self.shapes.keys():
            self.update_associative_dimensions(view)
            
        self.history = self.history[:self.history_index + 1]
        
        serialized_constraints = []
        for c in self.constraints:
            serialized_constraints.append({
                'id': c.id,
                'constraint_type': c.constraint_type.value,
                'shape_ids': c.shape_ids,
                'value': c.value,
                'point_indices': c.point_indices,
                'view_name': c.view_name,
                'is_active': c.is_active
            })
            
        state = {
            'shapes': {v: [s.to_dict() for s in self.shapes[v]] for v in self.shapes},
            'regions': {k: r.to_dict() for k, r in self.view_regions.items()},
            'constraints': serialized_constraints,
            'datums': {k: d.to_dict() for k, d in self.datums.items()},
            'feature_control_frames': {k: f.to_dict() for k, f in self.feature_control_frames.items()},
            'cutting_planes': {k: {
                'id': cp.id,
                'label': cp.label,
                'view': cp.view,
                'points': cp.points,
                'normal': list(cp.normal),
                'arrow_size': cp.arrow_size,
                'line_style': cp.line_style
            } for k, cp in self.cutting_planes.items()},
            'section_views': {k: {
                'id': sv.id,
                'cutting_plane_id': sv.cutting_plane_id,
                'target_view': sv.target_view,
                'section_type': sv.section_type.value if hasattr(sv.section_type, 'value') else str(sv.section_type),
                'hatch_angle': sv.hatch_angle,
                'hatch_pitch': sv.hatch_pitch,
                'rib_exclusion_ids': sv.rib_exclusion_ids
            } for k, sv in self.section_views.items()}
        }
        
        self.history.append((description, state))
        self.history_index += 1
        
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_index -= 1
            
    def _load_state_from_history(self):
        """Restore shapes, regions, constraints, datums, FCFs, and section planes from history state"""
        description, state = self.history[self.history_index]
        if 'shapes' in state:
            self.shapes = {v: [Shape.from_dict(s) for s in state['shapes'][v]] for v in state['shapes']}
            self.view_regions = {k: ViewRegion.from_dict(r) for k, r in state.get('regions', {}).items()}
            self.datums = {k: DatumFeature.from_dict(d) for k, d in state.get('datums', {}).items()}
            self.feature_control_frames = {k: FeatureControlFrame.from_dict(f) for k, f in state.get('feature_control_frames', {}).items()}
            
            # Load cutting planes
            self.cutting_planes = {}
            for k, cpd in state.get('cutting_planes', {}).items():
                self.cutting_planes[k] = CuttingPlane(
                    id=cpd['id'],
                    label=cpd.get('label', 'A'),
                    view=cpd.get('view', 'top'),
                    points=[tuple(p) for p in cpd.get('points', [])],
                    normal=tuple(cpd.get('normal', (0.0, -1.0))),
                    arrow_size=cpd.get('arrow_size', 8.0),
                    line_style=cpd.get('line_style', 'dash_dot')
                )
                
            # Load section views
            self.section_views = {}
            for k, svd in state.get('section_views', {}).items():
                stype_val = svd.get('section_type', 'full')
                try:
                    stype = SectionType(stype_val)
                except Exception:
                    stype = SectionType.FULL
                self.section_views[k] = SectionView(
                    id=svd['id'],
                    cutting_plane_id=svd['cutting_plane_id'],
                    target_view=svd.get('target_view', 'front'),
                    section_type=stype,
                    hatch_angle=svd.get('hatch_angle', 45.0),
                    hatch_pitch=svd.get('hatch_pitch', 3.0),
                    rib_exclusion_ids=svd.get('rib_exclusion_ids', [])
                )

            self.constraints = []
            for cd in state.get('constraints', []):
                try:
                    ctype = ConstraintType(cd['constraint_type'])
                    self.constraints.append(Constraint(
                        id=cd['id'],
                        constraint_type=ctype,
                        shape_ids=cd['shape_ids'],
                        value=cd.get('value'),
                        point_indices=cd.get('point_indices'),
                        view_name=cd.get('view_name', 'unified'),
                        is_active=cd.get('is_active', True)
                    ))
                except Exception:
                    pass
        else:
            # Legacy fallback
            self.shapes = {
                'top': [Shape.from_dict(s) for s in state.get('top', [])],
                'front': [Shape.from_dict(s) for s in state.get('front', [])],
                'side': [Shape.from_dict(s) for s in state.get('side', [])],
                'unassigned': []
            }
            self.datums = {}
            self.feature_control_frames = {}
            self.constraints = []
            
    def update_associative_dimensions(self, view: str):
        """Update dimension text linked to target shapes"""
        if view not in self.shapes:
            return
            
        shape_dict = {s.id: s for s in self.shapes[view]}
        
        for shape in self.shapes[view]:
            if shape.type == 'dimension':
                dim = shape
                if not dim.target_shape_ids:
                    continue
                    
                target_ids = dim.target_shape_ids
                if len(target_ids) == 1:
                    target = shape_dict.get(target_ids[0])
                    if target:
                        if target.type == 'line':
                            dim.start_pt = target.start
                            dim.end_pt = target.end
                            dx = target.end[0] - target.start[0]
                            dy = target.end[1] - target.start[1]
                            dist = np.sqrt(dx*dx + dy*dy)
                            dim.text = f"{dist:.1f}"
                        elif target.type in ['circle', 'arc']:
                            dim.start_pt = target.center
                            dim.end_pt = (target.center[0] + target.radius, target.center[1])
                            dim.text = f"R{target.radius:.1f}"
                elif len(target_ids) == 2:
                    target1 = shape_dict.get(target_ids[0])
                    target2 = shape_dict.get(target_ids[1])
                    if target1 and target2:
                        pt1 = target1.start if target1.type == 'line' else getattr(target1, 'center', (0.0, 0.0))
                        pt2 = target2.start if target2.type == 'line' else getattr(target2, 'center', (0.0, 0.0))
                        dim.start_pt = pt1
                        dim.end_pt = pt2
                        dx = pt2[0] - pt1[0]
                        dy = pt2[1] - pt1[1]
                        dist = np.sqrt(dx*dx + dy*dy)
                        dim.text = f"{dist:.1f}"

    def get_shape_bounds(self, shape: Shape) -> Optional[Tuple[float, float, float, float]]:
        """Get bounding box of a shape as (min_x, min_y, max_x, max_y)"""
        if isinstance(shape, Line):
            x1, y1 = shape.start
            x2, y2 = shape.end
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            
        elif isinstance(shape, Rectangle):
            x, y, w, h = shape.rect
            return (x, y, x + w, y + h)
            
        elif isinstance(shape, Circle):
            cx, cy = shape.center
            r = shape.radius
            return (cx - r, cy - r, cx + r, cy + r)
            
        elif isinstance(shape, Polygon):
            if not shape.points:
                return None
            xs = [p[0] for p in shape.points]
            ys = [p[1] for p in shape.points]
            return (min(xs), min(ys), max(xs), max(ys))
            
        elif isinstance(shape, Arc):
            cx, cy = shape.center
            r = shape.radius
            return (cx - r, cy - r, cx + r, cy + r)
            
        elif isinstance(shape, Dimension):
            x1, y1 = shape.start_pt
            x2, y2 = shape.end_pt
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            
        return None

    def get_local_shapes_for_view(self, view_key: str) -> List[Dict[str, Any]]:
        """
        Extract shapes converted to local coordinates:
        - If custom finite ViewRegion defined: maps relative to region origin (x0, y0) with Y-inversion
        - Else (default infinite quadrants):
          * Front View (Q2: X <= 0, Y <= 0): u = px, v = -py (positive 3D Y points up)
          * Side View (Q1: X >= 0, Y <= 0): u = px (depth), v = -py (height)
          * Top View (Q3: X <= 0, Y >= 0): u = px (width), w = py (depth away from front)
        """
        shapes = self.shapes.get(view_key, [])
        region = self.view_regions.get(view_key)
        is_custom_finite = region and (region.min_x > -10000.0 and region.max_x < 10000.0)
        
        if is_custom_finite:
            x0, y0 = region.origin
            is_right_side = (region.view_type == 'right_side')
        else:
            x0, y0 = (0.0, 0.0)
            is_right_side = False

        local_shapes = []
        for shape in shapes:
            d = shape.to_dict()
            t = d.get('type')
            
            def map_pt(px: float, py: float) -> Tuple[float, float]:
                if is_custom_finite:
                    lx = (x0 - px) if is_right_side else (px - x0)
                    ly = y0 - py
                    return (lx, ly)
                if view_key in ('front', 'side'):
                    return (px, -py)
                else:  # 'top'
                    return (px, py)
                
            if t == 'line':
                d['start'] = map_pt(d['start'][0], d['start'][1])
                d['end'] = map_pt(d['end'][0], d['end'][1])
            elif t == 'rectangle':
                x, y, w, h = d['rect']
                corners = [map_pt(x, y), map_pt(x + w, y), map_pt(x + w, y + h), map_pt(x, y + h)]
                min_x = min(c[0] for c in corners)
                min_y = min(c[1] for c in corners)
                d['rect'] = (min_x, min_y, abs(w), abs(h))
            elif t in ['circle', 'arc']:
                d['center'] = map_pt(d['center'][0], d['center'][1])
            elif t == 'polygon':
                d['points'] = [map_pt(p[0], p[1]) for p in d['points']]
            elif t == 'dimension':
                d['start_pt'] = map_pt(d['start_pt'][0], d['start_pt'][1])
                d['end_pt'] = map_pt(d['end_pt'][0], d['end_pt'][1])
                d['label_pt'] = map_pt(d['label_pt'][0], d['label_pt'][1])
                
            local_shapes.append(d)
            
        return local_shapes

    def validate_alignment(self, tolerance: float = 5.0) -> Tuple[bool, str]:
        """
        Guardrail 2: Verify standard orthographic alignment across Top, Front, and Side views.
        - Top Width (max_x - min_x) == Front Width (max_x - min_x)
        - Front Height (max_y - min_y) == Side Height (max_y - min_y)
        - Top View Depth (Top Region Height) == Side View Depth (Side Region Width)
        """
        def get_view_span(view_key: str) -> Optional[Tuple[float, float, float, float]]:
            shapes = self.shapes.get(view_key, [])
            all_bounds = [self.get_shape_bounds(s) for s in shapes if self.get_shape_bounds(s) is not None]
            if not all_bounds:
                return None
            min_x = min(b[0] for b in all_bounds)
            min_y = min(b[1] for b in all_bounds)
            max_x = max(b[2] for b in all_bounds)
            max_y = max(b[3] for b in all_bounds)
            return (min_x, min_y, max_x, max_y)

        top_span = get_view_span('top')
        front_span = get_view_span('front')
        side_span = get_view_span('side')

        # Check Top vs Front Width
        if top_span and front_span:
            top_width = top_span[2] - top_span[0]
            front_width = front_span[2] - front_span[0]
            if abs(top_width - front_width) > tolerance:
                return False, f"Alignment Error: Front View width is {front_width:.1f}mm, but Top View width is {top_width:.1f}mm."

        # Check Front vs Side Height
        if front_span and side_span:
            front_height = front_span[3] - front_span[1]
            side_height = side_span[3] - side_span[1]
            if abs(front_height - side_height) > tolerance:
                return False, f"Alignment Error: Front View height is {front_height:.1f}mm, but Side View height is {side_height:.1f}mm."

        # Guardrail 2: Check Top Depth vs Side Depth
        if top_span and side_span:
            top_depth = top_span[3] - top_span[1]
            side_depth = side_span[2] - side_span[0]
            if abs(top_depth - side_depth) > tolerance:
                return False, f"Alignment Error: Top View depth is {top_depth:.1f}mm, but Side View depth is {side_depth:.1f}mm."

        return True, "Orthographic alignment validated successfully."
