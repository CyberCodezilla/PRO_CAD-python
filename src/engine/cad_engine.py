"""
CAD Engine - Core data model and shape management with history stack & unified orthographic regions.
"""
import uuid
import numpy as np
from typing import List, Dict, Tuple, Any, Optional

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
            return Line(tuple(d['start']), tuple(d['end']), layer, shape_id)
        elif shape_type == 'rectangle':
            return Rectangle(tuple(d['rect']), layer, shape_id)
        elif shape_type == 'circle':
            return Circle(tuple(d['center']), float(d['radius']), layer, shape_id)
        elif shape_type == 'polygon':
            points = [tuple(p) for p in d['points']]
            return Polygon(points, layer, shape_id)
        elif shape_type == 'arc':
            return Arc(tuple(d['center']), float(d['radius']), float(d['start_angle']), float(d['end_angle']), layer, shape_id)
        elif shape_type == 'dimension':
            return Dimension(d['dim_type'], tuple(d['start_pt']), tuple(d['end_pt']), tuple(d['label_pt']), d['text'], d.get('target_shape_ids', []), layer, shape_id)
        
        raise ValueError(f"Unknown shape type: {shape_type}")


class Line(Shape):
    """Line segment primitive"""
    
    def __init__(self, start: Tuple[float, float], end: Tuple[float, float], layer: str = "Visible", shape_id: str = None):
        super().__init__('line', layer, shape_id)
        self.start = start  # (x, y)
        self.end = end      # (x, y)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'start': self.start,
            'end': self.end
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
    
    def __init__(self, center: Tuple[float, float], radius: float, start_angle: float, end_angle: float, layer: str = "Visible", shape_id: str = None):
        super().__init__('arc', layer, shape_id)
        self.center = center          # (x, y)
        self.radius = radius
        self.start_angle = start_angle # in degrees (0-360)
        self.end_angle = end_angle     # in degrees (0-360)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'layer': self.layer,
            'center': self.center,
            'radius': self.radius,
            'start_angle': self.start_angle,
            'end_angle': self.end_angle
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
        """Initialize standard 4-quadrant orthographic drafting sheet layout (infinite quadrant bounds)"""
        # Top-Left Quadrant: Top View
        self.view_regions['top'] = ViewRegion('top', (-50000.0, -50000.0, 0.0, 0.0))
        # Bottom-Left Quadrant: Front View
        self.view_regions['front'] = ViewRegion('front', (-50000.0, 0.0, 0.0, 50000.0))
        # Bottom-Right Quadrant: Left Side / LHS View
        self.view_regions['side'] = ViewRegion('left_side', (0.0, 0.0, 50000.0, 50000.0))

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
        
        if action == 'auto_scale_top_width':
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
        Guardrail 3: Assign a shape to a ViewRegion based on its centroid.
        Returns the region key ('top', 'front', 'side', or 'unassigned').
        """
        centroid = get_shape_centroid(shape)
        for key, region in self.view_regions.items():
            if region.contains_point(centroid):
                return key
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
        """Remove a shape by ID"""
        views_to_search = [view] if view and view in self.shapes else list(self.shapes.keys())
        
        for v in views_to_search:
            initial_len = len(self.shapes[v])
            self.shapes[v] = [s for s in self.shapes[v] if s.id != shape_id]
            if len(self.shapes[v]) < initial_len:
                self._save_state(f"Remove Shape from {v.capitalize()} View")
                return True
        return False
        
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
        self.init_default_quadrant_regions()
        self.history = []
        self.history_index = -1
        self._save_state("Clear All")
        
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
            
    def _save_state(self, description: str = "State Change"):
        """Save current state for undo/redo"""
        for view in self.shapes.keys():
            self.update_associative_dimensions(view)
            
        self.history = self.history[:self.history_index + 1]
        
        state = {
            'shapes': {v: [s.to_dict() for s in self.shapes[v]] for v in self.shapes},
            'regions': {k: r.to_dict() for k, r in self.view_regions.items()}
        }
        
        self.history.append((description, state))
        self.history_index += 1
        
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_index -= 1
            
    def _load_state_from_history(self):
        """Restore shapes and regions from history state"""
        description, state = self.history[self.history_index]
        if 'shapes' in state:
            self.shapes = {v: [Shape.from_dict(s) for s in state['shapes'][v]] for v in state['shapes']}
            self.view_regions = {k: ViewRegion.from_dict(r) for k, r in state.get('regions', {}).items()}
        else:
            # Legacy fallback
            self.shapes = {
                'top': [Shape.from_dict(s) for s in state.get('top', [])],
                'front': [Shape.from_dict(s) for s in state.get('front', [])],
                'side': [Shape.from_dict(s) for s in state.get('side', [])],
                'unassigned': []
            }
            
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
        Guardrails 1 & 4: Extract shapes converted to local coordinates.
        - Bottom-left origin (x0, y0)
        - Y-inversion: local_y = y0 - abs_y
        - Right-side view mirroring: local_x = x0 - abs_x for right_side view
        """
        shapes = self.shapes.get(view_key, [])
        region = self.view_regions.get(view_key)
        
        # Default origin fallback if region not explicitly defined
        if region:
            x0, y0 = region.origin
            is_right_side = (region.view_type == 'right_side')
        else:
            # Fallback bounds of shapes in view
            all_bounds = [self.get_shape_bounds(s) for s in shapes if self.get_shape_bounds(s) is not None]
            if all_bounds:
                min_xs = [b[0] for b in all_bounds]
                max_ys = [b[3] for b in all_bounds]
                x0 = min(min_xs)
                y0 = max(max_ys)
            else:
                x0, y0 = (0.0, 0.0)
            is_right_side = False

        local_shapes = []
        for shape in shapes:
            d = shape.to_dict()
            t = d.get('type')
            
            # Helper to map absolute point (px, py) -> (lx, ly)
            def map_pt(px: float, py: float) -> Tuple[float, float]:
                lx = (x0 - px) if is_right_side else (px - x0)
                ly = y0 - py  # Y-inversion: canvas Y grows down, local 3D Y grows up
                return (lx, ly)
                
            if t == 'line':
                d['start'] = map_pt(d['start'][0], d['start'][1])
                d['end'] = map_pt(d['end'][0], d['end'][1])
            elif t == 'rectangle':
                x, y, w, h = d['rect']
                lx1, ly1 = map_pt(x, y + h)  # bottom-left
                lx2, ly2 = map_pt(x + w, y)  # top-right
                lx_min = min(lx1, lx2)
                ly_min = min(ly1, ly2)
                d['rect'] = (lx_min, ly_min, abs(w), abs(h))
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
