"""
CAD Engine - Core data model and shape management with history stack
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


class CADEngine:
    """Core CAD engine for managing shapes and drawing operations with undo/redo"""
    
    def __init__(self):
        self.shapes: Dict[str, List[Shape]] = {
            'top': [],
            'front': [],
            'side': []
        }
        self.active_tool: str = 'select'
        self.active_layer: str = 'Visible'  # 'Visible', 'Hidden', 'Construction'
        
        self.history: List[Tuple[str, Dict[str, List[Dict[str, Any]]]]] = []
        self.history_index: int = -1
        self.max_history: int = 100
        
        # Save baseline empty state
        self._save_state("Initial State")
        
    def set_active_tool(self, tool_name: str):
        """Set active drawing tool"""
        self.active_tool = tool_name
        
    def set_active_layer(self, layer_name: str):
        """Set active drawing layer"""
        self.active_layer = layer_name
        
    def add_shape(self, shape: Shape, view: str):
        """Add a shape to the specified view"""
        if view not in self.shapes:
            return
            
        self.shapes[view].append(shape)
        self._save_state(f"Draw {shape.type.capitalize()} on {self.active_layer} in {view.capitalize()} View")
        
    def remove_shape(self, shape_id: str, view: str) -> bool:
        """Remove a shape by ID from the specified view"""
        if view not in self.shapes:
            return False
            
        initial_len = len(self.shapes[view])
        # Find shape type for descriptive undo
        shape_type = "Shape"
        for s in self.shapes[view]:
            if s.id == shape_id:
                shape_type = s.type.capitalize()
                break
        self.shapes[view] = [s for s in self.shapes[view] if s.id != shape_id]
        
        if len(self.shapes[view]) < initial_len:
            self._save_state(f"Remove {shape_type} in {view.capitalize()} View")
            return True
        return False
        
    def get_shapes(self, view: str) -> List[Shape]:
        """Get all shapes for a view"""
        return self.shapes.get(view, [])
        
    def clear_view(self, view: str):
        """Clear all shapes from a view"""
        if view in self.shapes:
            self.shapes[view] = []
            self._save_state(f"Clear {view.capitalize()} View")
            
    def clear_all(self):
        """Clear all shapes from all views"""
        self.shapes = {
            'top': [],
            'front': [],
            'side': []
        }
        self.history = []
        self.history_index = -1
        self._save_state("Clear All")
        
    def undo(self) -> Tuple[bool, str]:
        """Undo last action, returns (success, description)"""
        if self.history_index > 0:
            undone_desc = self.history[self.history_index][0]
            self.history_index -= 1
            self._load_state_from_history()
            return True, undone_desc
        return False, ""
            
    def redo(self) -> Tuple[bool, str]:
        """Redo last undone action, returns (success, description)"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self._load_state_from_history()
            redone_desc = self.history[self.history_index][0]
            return True, redone_desc
        return False, ""
            
    def _save_state(self, description: str = "State Change"):
        """Save current state for undo/redo via serialization"""
        # Automatically update associative dimensions for all views
        for view in ['top', 'front', 'side']:
            self.update_associative_dimensions(view)
            
        # Trim history after current index
        self.history = self.history[:self.history_index + 1]
        
        # Save serialized representation of shapes
        state = {
            'top': [s.to_dict() for s in self.shapes['top']],
            'front': [s.to_dict() for s in self.shapes['front']],
            'side': [s.to_dict() for s in self.shapes['side']]
        }
        
        self.history.append((description, state))
        self.history_index += 1
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_index -= 1
            
    def _load_state_from_history(self):
        """Restore shapes from serialized history state"""
        description, state = self.history[self.history_index]
        self.shapes = {
            'top': [Shape.from_dict(s) for s in state['top']],
            'front': [Shape.from_dict(s) for s in state['front']],
            'side': [Shape.from_dict(s) for s in state['side']]
        }
        
    def update_associative_dimensions(self, view: str):
        """Update any dimension coordinates linked to modified shapes in a view"""
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
                        elif target.type == 'circle':
                            dim.start_pt = target.center
                            dim.end_pt = (target.center[0] + target.radius, target.center[1])
                            dim.text = f"R{target.radius:.1f}"
                        elif target.type == 'arc':
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
        
    def shape_to_points(self, shape: Shape, num_points: int = 100) -> np.ndarray:
        """Convert shape boundary to array of points for CV processing"""
        if isinstance(shape, Line):
            x1, y1 = shape.start
            x2, y2 = shape.end
            t = np.linspace(0, 1, num_points)
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            return np.column_stack([x, y])
            
        elif isinstance(shape, Circle):
            cx, cy = shape.center
            r = shape.radius
            theta = np.linspace(0, 2 * np.pi, num_points)
            x = cx + r * np.cos(theta)
            y = cy + r * np.sin(theta)
            return np.column_stack([x, y])
            
        elif isinstance(shape, Rectangle):
            x, y, w, h = shape.rect
            pts_per_side = num_points // 4
            top = np.column_stack([np.linspace(x, x + w, pts_per_side), np.full(pts_per_side, y)])
            right = np.column_stack([np.full(pts_per_side, x + w), np.linspace(y, y + h, pts_per_side)])
            bottom = np.column_stack([np.linspace(x + w, x, pts_per_side), np.full(pts_per_side, y + h)])
            left = np.column_stack([np.full(pts_per_side, x), np.linspace(y + h, y, pts_per_side)])
            return np.vstack([top, right, bottom, left])
            
        elif isinstance(shape, Polygon):
            return np.array(shape.points)
            
        elif isinstance(shape, Arc):
            cx, cy = shape.center
            r = shape.radius
            theta1 = np.radians(shape.start_angle)
            theta2 = np.radians(shape.end_angle)
            if theta2 < theta1:
                theta2 += 2 * np.pi
            theta = np.linspace(theta1, theta2, num_points)
            x = cx + r * np.cos(theta)
            y = cy + r * np.sin(theta)
            return np.column_stack([x, y])
            
        elif isinstance(shape, Dimension):
            return np.array([])
            
        return np.array([])
