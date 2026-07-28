"""
Drawing Canvas - Vector drafting interface utilizing QGraphicsView and QGraphicsScene.
Features infinite pan/zoom, grid/axes drawing, snapping, ortho-constrain, and projection guides.
"""
import numpy as np
import shapely.geometry as sg
import shapely.ops as so
from typing import List, Optional
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsItem, QGraphicsPathItem, QWidget, QHBoxLayout, QLineEdit, QInputDialog
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF, QMouseEvent, QWheelEvent, QCursor, QPainterPath
from ..engine.cad_engine import Shape, Line, Rectangle, Circle, Polygon, Arc, Dimension

class DrawingCanvas(QGraphicsView):
    """QGraphicsView widget for precision vector CAD drawing"""
    
    # Signals for UI synchronization
    mouse_coords_changed = pyqtSignal(float, float, float, float)  # x, y, length, angle
    cursor_moved_in_scene = pyqtSignal(str, QPointF)  # view_name, scene_pos
    shape_drawn = pyqtSignal()
    
    def __init__(self, cad_engine, view_name: str, parent=None):
        scene = QGraphicsScene()
        # Large scene rect for virtual infinite workspace
        scene.setSceneRect(-50000, -50000, 100000, 100000)
        super().__init__(scene, parent)
        
        self.cad_engine = cad_engine
        self.view_name = view_name  # 'top', 'front', 'side'
        
        # Interactive modes
        self.current_tool = 'select'
        self.grid_size = 10
        self.major_grid_multiplier = 5
        self.snap_to_grid = True
        self.snap_to_object = True
        self.ortho_mode = False  # Locked to horizontal/vertical
        
        # State variables
        self.is_drawing = False
        self.start_point: Optional[QPointF] = None
        self.temp_item: Optional[QGraphicsItem] = None
        self.polygon_points: List[QPointF] = []
        self.temp_polygon_lines: List[QGraphicsLineItem] = []
        
        # Snapping state
        self.active_snap_point: Optional[QPointF] = None
        
        # Projection guides from other canvases
        self.guide_x: Optional[float] = None
        self.guide_y: Optional[float] = None
        
        # Pan state
        self._is_panning = False
        self._pan_start_pos = QPoint()
        
        # Dynamic HUD Cursor Input
        self.hud = QWidget(self.viewport())
        self.hud.setObjectName("DrawingHUD")
        self.hud.setStyleSheet("background-color: #2D2D2D; border: 1px solid #3C3C3C; border-radius: 2px;")
        self.hud_layout = QHBoxLayout(self.hud)
        self.hud_layout.setContentsMargins(4, 2, 4, 2)
        self.hud_layout.setSpacing(4)
        
        self.hud_len = QLineEdit(self.hud)
        self.hud_len.setPlaceholderText("Len")
        self.hud_len.setFixedWidth(55)
        self.hud_len.setStyleSheet("background-color: #1E1E1E; color: #00FFFF; border: 1px solid #3C3C3C; font-family: Consolas; font-size: 10px; padding: 2px;")
        self.hud_layout.addWidget(self.hud_len)
        
        self.hud_angle = QLineEdit(self.hud)
        self.hud_angle.setPlaceholderText("Ang")
        self.hud_angle.setFixedWidth(45)
        self.hud_angle.setStyleSheet("background-color: #1E1E1E; color: #00FFFF; border: 1px solid #3C3C3C; font-family: Consolas; font-size: 10px; padding: 2px;")
        self.hud_layout.addWidget(self.hud_angle)
        
        self.hud.setLayout(self.hud_layout)
        self.hud.hide()
        
        self.hud_len.returnPressed.connect(self._on_hud_entered)
        self.hud_angle.returnPressed.connect(self._on_hud_entered)
        
        self._init_settings()
        self.rebuild_scene()
        
    def _init_settings(self):
        """Configure viewport rendering settings"""
        self.setBackgroundBrush(QBrush(QColor('#1E1E1E')))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Reset zoom
        self.resetTransform()
        
    def set_tool(self, tool_name: str):
        """Set current drafting tool"""
        self.current_tool = tool_name
        self.cancel_current_operation()
        
    def set_grid_snap(self, enabled: bool):
        """Toggle grid snapping"""
        self.snap_to_grid = enabled
        
    def set_object_snap(self, enabled: bool):
        """Toggle object snapping"""
        self.snap_to_object = enabled
        
    def set_ortho(self, enabled: bool):
        """Toggle ortho mode"""
        self.ortho_mode = enabled

    def set_show_miter_line(self, enabled: bool):
        """Toggle 45 degree Miter Line guide visibility"""
        self.show_miter_line = enabled
        self.rebuild_scene()
        
    def cancel_current_operation(self):
        """Reset current active drawing state"""
        self.is_drawing = False
        self.start_point = None
        if self.temp_item:
            self.scene().removeItem(self.temp_item)
            self.temp_item = None
            
        for line in self.temp_polygon_lines:
            self.scene().removeItem(line)
        self.temp_polygon_lines.clear()
        self.polygon_points.clear()
        self._first_dim_point = None
        self._second_dim_point = None
        
        # Reset HUD
        self.hud.hide()
        self.hud_len.clear()
        self.hud_angle.clear()
        
        self.scene().update()
        
    def update_projection_guide(self, source_view: str, scene_pos: QPointF):
        """Receive cursor position from another view and compute guide line coordinates"""
        if source_view == self.view_name:
            return
            
        self.guide_x = None
        self.guide_y = None
        
        # Align projections according to coordinate mapping rules:
        # Top: X, -Z
        # Front: X, -Y
        # Side: Z, -Y
        if self.view_name == 'top':
            if source_view == 'front':
                # Shared coordinate: X (horizontal)
                self.guide_x = scene_pos.x()
            elif source_view == 'side':
                # Shared coordinate: Z (which is Side X and Top Y, wait, Top vert is -Z)
                # Side horiz = Z_3D. Top vert = -Z_3D.
                # So Z = scene_pos.x() (Side). On Top canvas, v = -Z, so scene_y = -Z = -scene_pos.x().
                self.guide_y = -scene_pos.x()
                
        elif self.view_name == 'front':
            if source_view == 'top':
                # Shared coordinate: X (horizontal)
                self.guide_x = scene_pos.x()
            elif source_view == 'side':
                # Shared coordinate: Y (which is Side Y and Front Y, vert axes on both are -Y)
                # Front vert = -Y. Side vert = -Y.
                # So they match directly!
                self.guide_y = scene_pos.y()
                
        elif self.view_name == 'side':
            if source_view == 'top':
                # Shared coordinate: Z (Top vert is -Z, Side horiz is Z)
                # Top vert = scene_pos.y() = -Z. So Z = -scene_pos.y().
                # Side horiz = Z, so scene_x = Z = -scene_pos.y().
                self.guide_x = -scene_pos.y()
            elif source_view == 'front':
                # Shared coordinate: Y (Front vert is -Y, Side vert is -Y)
                self.guide_y = scene_pos.y()
                
        self.scene().update()
        
    def clear_projection_guides(self):
        """Remove faint projection guide lines"""
        self.guide_x = None
        self.guide_y = None
        self.scene().update()

    def rebuild_scene(self):
        """Sync scene display with the CADEngine shapes database & view regions"""
        from ..engine.cad_engine import ViewRegion
        self.scene().clear()
        self.temp_item = None
        self.temp_polygon_lines.clear()
        
        # 1. Render View Regions
        active_mode = self.cad_engine.active_view_mode
        for key, region in self.cad_engine.view_regions.items():
            if region.min_x <= -10000.0 or region.max_x >= 10000.0:
                if region.view_type == 'top':
                    rx, ry, rw, rh = (-2000.0, -2000.0, 2000.0, 2000.0)
                    tx, ty = (-390.0, -390.0)
                elif region.view_type == 'front':
                    rx, ry, rw, rh = (-2000.0, 0.0, 2000.0, 2000.0)
                    tx, ty = (-390.0, 10.0)
                else:
                    rx, ry, rw, rh = (0.0, 0.0, 2000.0, 2000.0)
                    tx, ty = (10.0, 10.0)
            else:
                rx, ry, rw, rh = (region.min_x, region.min_y, region.width, region.height)
                tx, ty = (region.min_x + 10, region.min_y + 6)

            rect_item = QGraphicsRectItem(rx, ry, rw, rh)
            
            if region.view_type == 'top':
                color = QColor(40, 167, 69)      # Green for Top View
                plane_name = "XZ Plane"
            elif region.view_type == 'front':
                color = QColor(0, 122, 204)      # Blue for Front View
                plane_name = "XY Plane"
            elif region.view_type == 'right_side':
                color = QColor(230, 81, 0)       # Deep Orange for RHS View
                plane_name = "ZY Plane (RHS)"
            else:
                color = QColor(255, 193, 7)      # Amber/Yellow for LHS View
                plane_name = "ZY Plane (LHS)"
                
            is_active = (active_mode == region.view_type or (active_mode in ['left_side', 'right_side'] and key == 'side'))
            
            fill_alpha = 45 if is_active else 20
            rect_item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), fill_alpha)))
            
            border_width = 2.5 if is_active else 1.5
            pen_style = Qt.PenStyle.SolidLine if is_active else Qt.PenStyle.DashLine
            pen = QPen(color, border_width, pen_style)
            if not is_active:
                pen.setDashPattern([6, 4])
            rect_item.setPen(pen)
            self.scene().addItem(rect_item)
            
            # Label header badge in quadrant corner
            display_name = "LHS View" if region.view_type == 'left_side' else ("RHS View" if region.view_type == 'right_side' else f"{region.view_type.capitalize()} View")
            active_tag = " [ACTIVE MODE]" if is_active else ""
            
            text_item = self.scene().addText(f"{display_name} ({plane_name}){active_tag}")
            text_item.setDefaultTextColor(color)
            font = text_item.font()
            font.setBold(True)
            font.setPointSize(11)
            text_item.setFont(font)
            text_item.setPos(tx, ty)

        # 2. Render Projection Guides & 45° Miter Line
        self._draw_unified_projection_lines()

        # 3. Render Shapes (Assigned and Unassigned)
        all_shapes_keys = list(self.cad_engine.shapes.keys())
        for vk in all_shapes_keys:
            is_unassigned = (vk == 'unassigned')
            for shape in self.cad_engine.shapes[vk]:
                self._add_shape_to_scene(shape, is_unassigned=is_unassigned)
            
        self.scene().update()

    def _draw_unified_projection_lines(self):
        """Draw orthographic projection alignment guidelines & 45° Miter Line"""
        top = self.cad_engine.view_regions.get('top')
        front = self.cad_engine.view_regions.get('front')
        side = self.cad_engine.view_regions.get('side')

        guide_pen = QPen(QColor('#666666'), 1, Qt.PenStyle.DashLine)
        guide_pen.setDashPattern([4, 4])

        # Top to Front alignment lines (Width projection)
        if top and front:
            l1 = QGraphicsLineItem(top.min_x, top.max_y, front.min_x, front.min_y)
            l1.setPen(guide_pen)
            self.scene().addItem(l1)
            l2 = QGraphicsLineItem(top.max_x, top.max_y, front.max_x, front.min_y)
            l2.setPen(guide_pen)
            self.scene().addItem(l2)

        # Front to Side alignment lines (Height projection)
        if front and side:
            l1 = QGraphicsLineItem(front.max_x, front.min_y, side.min_x, side.min_y)
            l1.setPen(guide_pen)
            self.scene().addItem(l1)
            l2 = QGraphicsLineItem(front.max_x, front.max_y, side.min_x, side.max_y)
            l2.setPen(guide_pen)
            self.scene().addItem(l2)

        # 45° Miter Line projection (Top to Side Depth projection)
        if getattr(self, 'show_miter_line', True) and top and side:
            # Junction point at top right edge / origin
            miter_x = top.max_x
            miter_y = top.max_y
            
            miter_pen = QPen(QColor('#FF8C00'), 1.5, Qt.PenStyle.DashLine)
            miter_pen.setDashPattern([6, 3])
            
            miter_len = max(top.height, side.width) + 80.0
            # Extends at 45 degrees UP and RIGHT into the empty Top-Right Quadrant
            miter_line = QGraphicsLineItem(miter_x, miter_y, miter_x + miter_len, miter_y - miter_len)
            miter_line.setPen(miter_pen)
            self.scene().addItem(miter_line)
            
            label = self.scene().addText("45° Miter Line")
            label.setDefaultTextColor(QColor('#FF8C00'))
            font = label.font()
            font.setBold(True)
            font.setPointSize(9)
            label.setFont(font)
            label.setPos(miter_x + 15, miter_y - 35)
        
    def _add_shape_to_scene(self, shape: Shape, is_unassigned: bool = False):
        """Construct QGraphicsItem for a Shape data model and style it based on layer"""
        if is_unassigned:
            pen = QPen(QColor('#FF3333'), 2, Qt.PenStyle.DashLine)
        else:
            pen = self._get_pen_for_layer(shape.layer, getattr(shape, 'id', None))

        
        if isinstance(shape, Line):
            p1 = QPointF(shape.start[0], shape.start[1])
            p2 = QPointF(shape.end[0], shape.end[1])
            item = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            item.setPen(pen)
            self.scene().addItem(item)
            
        elif isinstance(shape, Rectangle):
            x, y, w, h = shape.rect
            item = QGraphicsRectItem(x, y, w, h)
            item.setPen(pen)
            self.scene().addItem(item)
            
        elif isinstance(shape, Circle):
            cx, cy = shape.center
            r = shape.radius
            item = QGraphicsEllipseItem(cx - r, cy - r, 2 * r, 2 * r)
            item.setPen(pen)
            self.scene().addItem(item)
            
        elif isinstance(shape, Polygon):
            qpoly = QPolygonF()
            for p in shape.points:
                qpoly.append(QPointF(p[0], p[1]))
            item = QGraphicsPolygonItem(qpoly)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.scene().addItem(item)
            
        elif isinstance(shape, Arc):
            cx, cy = shape.center
            r = shape.radius
            path = QPainterPath()
            sweep = shape.end_angle - shape.start_angle
            if sweep < 0:
                sweep += 360
            # QPainterPath's arcMoveTo and arcTo take positive counter-clockwise angles starting from 3 o'clock.
            # Mirror Y coordinate in angle calculations because scene Y goes down.
            path.arcMoveTo(cx - r, cy - r, 2 * r, 2 * r, -shape.start_angle)
            path.arcTo(cx - r, cy - r, 2 * r, 2 * r, -shape.start_angle, -sweep)
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            self.scene().addItem(item)
            
        elif isinstance(shape, Dimension):
            self._draw_dimension(shape)
            
    def _draw_dimension(self, dim: Dimension):
        """Draw an associative dimension segment with arrowheads and text labels"""
        pen = QPen(QColor('#FFFF00'), 1, Qt.PenStyle.SolidLine)
        p1 = QPointF(dim.start_pt[0], dim.start_pt[1])
        p2 = QPointF(dim.end_pt[0], dim.end_pt[1])
        lp = QPointF(dim.label_pt[0], dim.label_pt[1])
        
        v = p2 - p1
        length = np.sqrt(v.x()*v.x() + v.y()*v.y())
        if length < 0.1:
            return
        u = v / length
        n = QPointF(-u.y(), u.x())
        
        # Perpendicular offset from the line p1-p2 to lp
        proj_dist = (lp.x() - p1.x()) * n.x() + (lp.y() - p1.y()) * n.y()
        
        d1 = p1 + n * proj_dist
        d2 = p2 + n * proj_dist
        
        # Extension lines
        item1 = QGraphicsLineItem(p1.x(), p1.y(), d1.x(), d1.y())
        item1.setPen(pen)
        self.scene().addItem(item1)
        
        item2 = QGraphicsLineItem(p2.x(), p2.y(), d2.x(), d2.y())
        item2.setPen(pen)
        self.scene().addItem(item2)
        
        # Dimension line
        item_dim = QGraphicsLineItem(d1.x(), d1.y(), d2.x(), d2.y())
        item_dim.setPen(pen)
        self.scene().addItem(item_dim)
        
        # Scaled Arrowheads (in scene units, scaling inversely with zoom to maintain constant pixel size)
        arrow_len = 8.0 / self.transform().m11()
        
        # Arrowhead 1
        a1_1 = d1 + u * arrow_len + n * (arrow_len * 0.4)
        a1_2 = d1 + u * arrow_len - n * (arrow_len * 0.4)
        item_a1_1 = QGraphicsLineItem(d1.x(), d1.y(), a1_1.x(), a1_1.y())
        item_a1_1.setPen(pen)
        self.scene().addItem(item_a1_1)
        item_a1_2 = QGraphicsLineItem(d1.x(), d1.y(), a1_2.x(), a1_2.y())
        item_a1_2.setPen(pen)
        self.scene().addItem(item_a1_2)
        
        # Arrowhead 2
        a2_1 = d2 - u * arrow_len + n * (arrow_len * 0.4)
        a2_2 = d2 - u * arrow_len - n * (arrow_len * 0.4)
        item_a2_1 = QGraphicsLineItem(d2.x(), d2.y(), a2_1.x(), a2_1.y())
        item_a2_1.setPen(pen)
        self.scene().addItem(item_a2_1)
        item_a2_2 = QGraphicsLineItem(d2.x(), d2.y(), a2_2.x(), a2_2.y())
        item_a2_2.setPen(pen)
        self.scene().addItem(item_a2_2)
        
        # Dimension text
        mid = (d1 + d2) / 2
        text_item = self.scene().addText(dim.text)
        text_item.setDefaultTextColor(QColor('#FFFF00'))
        font = text_item.font()
        font.setPointSize(9)
        text_item.setFont(font)
        # Position text centered slightly above
        rect = text_item.boundingRect()
        text_item.setPos(mid.x() - rect.width() / 2, mid.y() - rect.height() - 2)
            
    def _get_pen_for_layer(self, layer: str, shape_id: str = None) -> QPen:
        """Get pen color and style for drawing depending on layer and diagnostic highlight state"""
        if hasattr(self, 'highlighted_shape_ids') and shape_id in self.highlighted_shape_ids:
            return QPen(QColor('#FF0033'), 3, Qt.PenStyle.SolidLine)

        if layer == 'Visible':
            return QPen(QColor('#00FFFF'), 2, Qt.PenStyle.SolidLine)
        elif layer == 'Hidden':
            # Dashed lines for interior cuts or pockets
            pen = QPen(QColor('#00FFFF'), 2, Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 2])
            return pen
        elif layer == 'Centerline':
            # Magenta Dash-Dot lines for symmetry axes
            pen = QPen(QColor('#FF00FF'), 1.5, Qt.PenStyle.DashDotLine)
            return pen
        elif layer == 'Construction':
            return QPen(QColor('#555555'), 1, Qt.PenStyle.SolidLine)
        return QPen(QColor('#FFFFFF'), 1, Qt.PenStyle.SolidLine)

    def highlight_shapes(self, shape_ids: List[str]):
        """Visually highlight specific shape IDs on the 2D scene in bright red"""
        self.highlighted_shape_ids = set(shape_ids)
        self.rebuild_scene()

    def clear_highlights(self):
        """Clear shape highlights"""
        self.highlighted_shape_ids = set()
        self.rebuild_scene()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Render drafting background grid and axes efficiently inside the exposed viewport rect"""
        painter.fillRect(rect, QColor('#1E1E1E'))
        
        # Grid settings
        grid_width = self.grid_size
        major_width = grid_width * self.major_grid_multiplier
        
        # Align iterations to the nearest grid step
        left = int(rect.left() // major_width) * major_width - major_width
        right = int(rect.right() // major_width) * major_width + major_width
        top = int(rect.top() // major_width) * major_width - major_width
        bottom = int(rect.bottom() // major_width) * major_width + major_width
        
        minor_pen = QPen(QColor('#2D2D2D'), 0.5, Qt.PenStyle.SolidLine)
        major_pen = QPen(QColor('#3D3D3D'), 1, Qt.PenStyle.SolidLine)
        
        # Draw vertical lines
        for x in range(left, right, grid_width):
            if x % major_width == 0:
                painter.setPen(major_pen)
            else:
                painter.setPen(minor_pen)
            painter.drawLine(x, top, x, bottom)
            
        # Draw horizontal lines
        for y in range(top, bottom, grid_width):
            if y % major_width == 0:
                painter.setPen(major_pen)
            else:
                painter.setPen(minor_pen)
            painter.drawLine(left, y, right, y)
            
        # Draw Red X-axis and Green Y-axis at origin
        painter.setPen(QPen(QColor('#FF0000'), 1.5))  # X Axis
        painter.drawLine(left, 0, right, 0)
        
        painter.setPen(QPen(QColor('#00FF00'), 1.5))  # Y Axis
        painter.drawLine(0, top, 0, bottom)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Draw snapping indicators and alignment projection guidelines"""
        # Draw cross-view alignment guide lines (dashed gray)
        guide_pen = QPen(QColor('#555555'), 1, Qt.PenStyle.DashLine)
        guide_pen.setDashPattern([6, 4])
        painter.setPen(guide_pen)
        
        if self.guide_x is not None:
            painter.drawLine(QPointF(self.guide_x, rect.top()), QPointF(self.guide_x, rect.bottom()))
            
        if self.guide_y is not None:
            painter.drawLine(QPointF(rect.left(), self.guide_y), QPointF(rect.right(), self.guide_y))
            
        # Draw yellow square snapping cursor
        if self.active_snap_point is not None:
            # Maintain constant size in pixels regardless of zoom
            size_px = 10
            size_scene = size_px / self.transform().m11()
            
            painter.setPen(QPen(QColor('#FFFF00'), 2))  # Yellow snap box
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(
                self.active_snap_point.x() - size_scene / 2,
                self.active_snap_point.y() - size_scene / 2,
                size_scene,
                size_scene
            ))
            
        # Draw Profile Closure Validation dangles (open endpoints) in bright red circles
        dangles = self._update_profile_closure()
        if dangles:
            painter.setPen(QPen(QColor('#FF3333'), 2))
            painter.setBrush(QBrush(QColor(255, 51, 51, 80)))
            size_scene = 8.0 / self.transform().m11()
            for pt in dangles:
                painter.drawEllipse(pt, size_scene, size_scene)

    def get_snap_point(self, scene_pos: QPointF) -> QPointF:
        """Find best snapping coordinate matching OSNAP or Grid Snapping"""
        self.active_snap_point = None
        
        # 1. Object Snapping (OSNAP)
        if self.snap_to_object:
            candidate = self._find_osnap_point(scene_pos)
            if candidate is not None:
                self.active_snap_point = candidate
                return candidate
                
        # 2. Grid Snapping
        if self.snap_to_grid:
            # Round to nearest grid size
            grid_x = round(scene_pos.x() / self.grid_size) * self.grid_size
            grid_y = round(scene_pos.y() / self.grid_size) * self.grid_size
            
            # Snap box triggers only within a threshold (e.g. 8px in screen coords)
            snap_pos = QPointF(grid_x, grid_y)
            dist_px = self._get_distance_in_pixels(scene_pos, snap_pos)
            if dist_px < 10:
                self.active_snap_point = snap_pos
                return snap_pos
                
        return scene_pos
        
    def _find_osnap_point(self, scene_pos: QPointF) -> Optional[QPointF]:
        """Scan scene shapes for endpoints, midpoints, and centers near coordinates"""
        best_point = None
        best_dist_px = 15.0  # Search threshold in screen pixels
        
        shapes = self.cad_engine.get_shapes(self.view_name)
        for shape in shapes:
            points_to_check = []
            
            if isinstance(shape, Line):
                p1 = QPointF(shape.start[0], shape.start[1])
                p2 = QPointF(shape.end[0], shape.end[1])
                mid = (p1 + p2) / 2
                points_to_check.extend([p1, p2, mid])
                
            elif isinstance(shape, Rectangle):
                x, y, w, h = shape.rect
                c1 = QPointF(x, y)
                c2 = QPointF(x + w, y)
                c3 = QPointF(x + w, y + h)
                c4 = QPointF(x, y + h)
                points_to_check.extend([
                    c1, c2, c3, c4,
                    (c1 + c2) / 2, (c2 + c3) / 2, (c3 + c4) / 2, (c4 + c1) / 2
                ])
                
            elif isinstance(shape, Circle):
                center = QPointF(shape.center[0], shape.center[1])
                r = shape.radius
                points_to_check.extend([
                    center,
                    QPointF(center.x() + r, center.y()),
                    QPointF(center.x() - r, center.y()),
                    QPointF(center.x(), center.y() + r),
                    QPointF(center.x(), center.y() - r)
                ])
                
            elif isinstance(shape, Polygon):
                for p in shape.points:
                    points_to_check.append(QPointF(p[0], p[1]))
                # Midpoints
                for i in range(len(shape.points)):
                    p1 = QPointF(shape.points[i][0], shape.points[i][1])
                    p2 = QPointF(shape.points[(i+1)%len(shape.points)][0], shape.points[(i+1)%len(shape.points)][1])
                    points_to_check.append((p1 + p2) / 2)
                    
            # Check distances
            for pt in points_to_check:
                d_px = self._get_distance_in_pixels(scene_pos, pt)
                if d_px < best_dist_px:
                    best_dist_px = d_px
                    best_point = pt
                    
        return best_point
        
    def _get_distance_in_pixels(self, p1: QPointF, p2: QPointF) -> float:
        """Compute pixel distance on screen between two scene points"""
        screen_p1 = self.mapFromScene(p1)
        screen_p2 = self.mapFromScene(p2)
        dx = screen_p1.x() - screen_p2.x()
        dy = screen_p1.y() - screen_p2.y()
        return np.sqrt(dx*dx + dy*dy)

    def apply_ortho_constrain(self, start: QPointF, end: QPointF) -> QPointF:
        """Constrain line angle strictly to 90-degree axis directions"""
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        
        if abs(dx) > abs(dy):
            return QPointF(end.x(), start.y())  # Horizontal lock
        else:
            return QPointF(start.x(), end.y())  # Vertical lock

    def command_input_point(self, dx: float, dy: float, is_absolute: bool = False):
        """Construct geometric point from bottom command console parametric input"""
        if self.current_tool == 'select':
            return
            
        current_cursor = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        reference = self.start_point if self.start_point else current_cursor
        
        if is_absolute:
            target = QPointF(dx, dy)
        else:
            # Relative delta entry (dx, dy)
            target = QPointF(reference.x() + dx, reference.y() + dy)
            
        # Treat this point as mouse click input
        self._input_drawing_point(target)

    def _input_drawing_point(self, pos: QPointF):
        """Handle drawing state progression when a coordinate is selected"""
        if self.current_tool == 'select':
            return
            
        if self.current_tool == 'dimension':
            if not self.is_drawing:
                # 1st point (start of measurement)
                self.is_drawing = True
                self.start_point = pos
                self._first_dim_point = pos
                self._second_dim_point = None
                self._create_temp_preview(pos, pos)
            elif self._second_dim_point is None:
                # 2nd point (end of measurement)
                self._second_dim_point = pos
                # Re-create temp preview from end point to cursor for text placement
                if self.temp_item:
                    self.scene().removeItem(self.temp_item)
                self._create_temp_preview(pos, pos)
            else:
                # 3rd point (label position)
                self.is_drawing = False
                
                # Check for snaps
                s1 = self._find_shape_at_point(self._first_dim_point)
                s2 = self._find_shape_at_point(self._second_dim_point)
                targets = []
                if s1: targets.append(s1.id)
                if s2: targets.append(s2.id)
                targets = list(set(targets))
                
                dx = self._second_dim_point.x() - self._first_dim_point.x()
                dy = self._second_dim_point.y() - self._first_dim_point.y()
                dist = np.sqrt(dx*dx + dy*dy)
                
                dim = Dimension(
                    'aligned',
                    (self._first_dim_point.x(), self._first_dim_point.y()),
                    (self._second_dim_point.x(), self._second_dim_point.y()),
                    (pos.x(), pos.y()),
                    f"{dist:.1f}",
                    target_shape_ids=targets
                )
                self.cad_engine.add_shape(dim, self.view_name)
                self.start_point = None
                self._first_dim_point = None
                self._second_dim_point = None
                if self.temp_item:
                    self.scene().removeItem(self.temp_item)
                    self.temp_item = None
                self.shape_drawn.emit()
                self.rebuild_scene()
            return
            
        if self.current_tool == 'polygon':
            self.polygon_points.append(pos)
            # Create a permanent line in the scene representing the segment
            if len(self.polygon_points) > 1:
                p1 = self.polygon_points[-2]
                p2 = self.polygon_points[-1]
                line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
                line.setPen(self._get_pen_for_layer(self.cad_engine.active_layer))
                self.scene().addItem(line)
                self.temp_polygon_lines.append(line)
            self.scene().update()
            return
            
        if not self.is_drawing:
            # First point selected
            self.is_drawing = True
            self.start_point = pos
            # Create dynamic temporary preview shape
            self._create_temp_preview(pos, pos)
        else:
            # Second point selected - finalize shape creation
            self.is_drawing = False
            self._finalize_drawn_shape(pos)
            self.start_point = None
            if self.temp_item:
                self.scene().removeItem(self.temp_item)
                self.temp_item = None
            self.shape_drawn.emit()
            
    def _create_temp_preview(self, start: QPointF, end: QPointF):
        """Add active temporary item to scene to show visual feedback while drawing"""
        pen = QPen(QColor('#00FFFF'), 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 2])
        
        if self.current_tool in ('line', 'dimension'):
            self.temp_item = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
        elif self.current_tool in ('rectangle', 'region'):
            x = min(start.x(), end.x())
            y = min(start.y(), end.y())
            w = abs(end.x() - start.x())
            h = abs(end.y() - start.y())
            self.temp_item = QGraphicsRectItem(x, y, w, h)
            if self.current_tool == 'region':
                pen = QPen(QColor('#FFC107'), 2, Qt.PenStyle.DashLine)
                pen.setDashPattern([6, 3])
        elif self.current_tool == 'circle':
            # Center and edge radius representation
            self.temp_item = QGraphicsEllipseItem(start.x(), start.y(), 0, 0)
            
        if self.temp_item:
            self.temp_item.setPen(pen)
            self.scene().addItem(self.temp_item)
            
    def _update_temp_preview(self, end: QPointF):
        """Update active geometry of temporary shape while cursor is moving"""
        if not self.temp_item or not self.start_point:
            return
            
        start = self.start_point
        
        if self.current_tool in ('line', 'dimension'):
            self.temp_item.setLine(start.x(), start.y(), end.x(), end.y())
        elif self.current_tool in ('rectangle', 'region'):
            x = min(start.x(), end.x())
            y = min(start.y(), end.y())
            w = abs(end.x() - start.x())
            h = abs(end.y() - start.y())
            self.temp_item.setRect(x, y, w, h)
        elif self.current_tool == 'circle':
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            r = np.sqrt(dx*dx + dy*dy)
            self.temp_item.setRect(start.x() - r, start.y() - r, 2 * r, 2 * r)

    def _add_shape_from_unified_sheet(self, shape: Shape):
        """Store a drawn shape in the visible sheet region under its centroid.

        The unified sheet is spatially authoritative: drawing in the LHS quadrant
        must create a Side shape even if the toolbar target was left on Front View.
        Explicit target mode is retained only as a fallback outside a known region.
        """
        target_view = self.cad_engine.assign_shape_to_region(shape)
        if target_view == 'unassigned' and self.cad_engine.active_view_mode != 'auto':
            target_view = ('side' if self.cad_engine.active_view_mode in ('left_side', 'right_side')
                           else self.cad_engine.active_view_mode)
        self.cad_engine.add_shape(shape, target_view if target_view in ('top', 'front', 'side') else None)
    def _finalize_drawn_shape(self, end: QPointF):
        """Generate CADEngine model shape or ViewRegion and add it to project database"""
        from ..engine.cad_engine import ViewRegion
        start = self.start_point
        layer = self.cad_engine.active_layer
        
        if self.current_tool == 'region':
            x = min(start.x(), end.x())
            y = min(start.y(), end.y())
            w = abs(end.x() - start.x())
            h = abs(end.y() - start.y())
            if w > 20 and h > 20:
                item, ok = QInputDialog.getItem(
                    self,
                    "Define View Region",
                    "Select View Region Label:",
                    ["Top View", "Front View", "Left Side View", "Right Side View"],
                    0,
                    False
                )
                if ok and item:
                    region = ViewRegion(item, (x, y, x + w, y + h))
                    self.cad_engine.add_view_region(region)

        elif self.current_tool == 'line':
            shape = Line((start.x(), start.y()), (end.x(), end.y()), layer)
            self._add_shape_from_unified_sheet(shape)
            
        elif self.current_tool == 'rectangle':
            x = min(start.x(), end.x())
            y = min(start.y(), end.y())
            w = abs(end.x() - start.x())
            h = abs(end.y() - start.y())
            if w > 0.1 and h > 0.1:
                shape = Rectangle((x, y, w, h), layer)
                self._add_shape_from_unified_sheet(shape)
                
        elif self.current_tool == 'circle':
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            r = np.sqrt(dx*dx + dy*dy)
            if r > 0.1:
                shape = Circle((start.x(), start.y()), r, layer)
                self._add_shape_from_unified_sheet(shape)
                
        self.rebuild_scene()

    def _finalize_polygon(self):
        """Close current active polygon and add it to shapes list"""
        if len(self.polygon_points) >= 3:
            pts = [(p.x(), p.y()) for p in self.polygon_points]
            shape = Polygon(pts, self.cad_engine.active_layer)
            self._add_shape_from_unified_sheet(shape)
            self.shape_drawn.emit()
            
        self.cancel_current_operation()
        self.rebuild_scene()

    def _on_hud_entered(self):
        """Parse dimensions typed in the floating HUD overlay and finish drawing segment"""
        if not self.is_drawing or not self.start_point:
            return
        try:
            length = float(self.hud_len.text())
            angle = float(self.hud_angle.text())
            
            # Resolve delta relative coordinates (inverted Y for canvas)
            rad = np.radians(angle)
            dx = length * np.cos(rad)
            dy = -length * np.sin(rad)
            
            target = QPointF(self.start_point.x() + dx, self.start_point.y() + dy)
            self._input_drawing_point(target)
            
            self.hud.hide()
            self.setFocus()
        except Exception as e:
            self.statusBar_msg(f"HUD Input Error: {str(e)}")

    def _handle_modification_tool_click(self, scene_pos: QPointF):
        """Process click events for editing tools like Trim, Extend, Fillet, Chamfer, and Offset"""
        win = self.window()
        
        if self.current_tool == 'trim':
            clicked_line = self._find_closest_line(scene_pos)
            if clicked_line:
                self._execute_trim(clicked_line, scene_pos)
                
        elif self.current_tool == 'extend':
            clicked_line = self._find_closest_line(scene_pos)
            if clicked_line:
                self._execute_extend(clicked_line, scene_pos)
                
        elif self.current_tool == 'fillet':
            clicked_line = self._find_closest_line(scene_pos)
            if clicked_line:
                if not hasattr(self, '_first_fillet_line') or self._first_fillet_line is None:
                    self._first_fillet_line = clicked_line
                    self.statusBar_msg("Fillet: Selected first line. Click second line.")
                else:
                    line1 = self._first_fillet_line
                    line2 = clicked_line
                    self._first_fillet_line = None
                    if line1.id == line2.id:
                        self.statusBar_msg("Error: Cannot fillet a line with itself.")
                        return
                    r, ok = QInputDialog.getDouble(self, "Fillet Radius", "Enter corner radius (mm):", 10.0, 0.1, 1000.0, 1)
                    if ok:
                        self._execute_fillet(line1, line2, r)
                        
        elif self.current_tool == 'chamfer':
            clicked_line = self._find_closest_line(scene_pos)
            if clicked_line:
                if not hasattr(self, '_first_chamfer_line') or self._first_chamfer_line is None:
                    self._first_chamfer_line = clicked_line
                    self.statusBar_msg("Chamfer: Selected first line. Click second line.")
                else:
                    line1 = self._first_chamfer_line
                    line2 = clicked_line
                    self._first_chamfer_line = None
                    if line1.id == line2.id:
                        self.statusBar_msg("Error: Cannot chamfer a line with itself.")
                        return
                    d1, ok1 = QInputDialog.getDouble(self, "Chamfer Distance 1", "Enter first line offset (mm):", 10.0, 0.1, 1000.0, 1)
                    if ok1:
                        d2, ok2 = QInputDialog.getDouble(self, "Chamfer Distance 2", "Enter second line offset (mm):", d1, 0.1, 1000.0, 1)
                        if ok2:
                            self._execute_chamfer(line1, line2, d1, d2)
                            
        elif self.current_tool == 'offset':
            clicked_shape = self._find_closest_shape(scene_pos)
            if clicked_shape:
                dist, ok = QInputDialog.getDouble(self, "Offset Distance", "Enter offset distance (mm):", 10.0, 0.1, 1000.0, 1)
                if ok:
                    self._execute_offset(clicked_shape, dist, scene_pos)

    def _find_closest_line(self, pos: QPointF, max_dist_px: float = 30.0) -> Optional[Line]:
        """Find the closest Line shape near coordinates within pixel threshold"""
        best_line = None
        best_dist_px = max_dist_px
        shapes = self.cad_engine.get_shapes(self.view_name)
        for shape in shapes:
            if isinstance(shape, Line):
                p1 = np.array(shape.start)
                p2 = np.array(shape.end)
                p = np.array([pos.x(), pos.y()])
                v = p2 - p1
                l2 = np.sum(v*v)
                if l2 < 0.1:
                    dist = np.linalg.norm(p - p1)
                else:
                    t = max(0.0, min(1.0, np.dot(p - p1, v) / l2))
                    proj = p1 + t * v
                    dist = np.linalg.norm(p - proj)
                dist_px = dist * self.transform().m11()
                if dist_px < best_dist_px:
                    best_dist_px = dist_px
                    best_line = shape
        return best_line

    def _find_closest_shape(self, pos: QPointF, max_dist_px: float = 40.0) -> Optional[Shape]:
        """Find closest shape of any type near scene coordinates"""
        best_shape = None
        best_dist_px = max_dist_px
        shapes = self.cad_engine.get_shapes(self.view_name)
        for s in shapes:
            if s.type == 'dimension':
                continue
            pts = self.cad_engine.shape_to_points(s)
            if len(pts) == 0:
                continue
            dists = np.linalg.norm(pts - np.array([pos.x(), pos.y()]), axis=1)
            min_dist = np.min(dists)
            dist_px = min_dist * self.transform().m11()
            if dist_px < best_dist_px:
                best_dist_px = dist_px
                best_shape = s
        return best_shape

    def _find_shape_at_point(self, pos: QPointF, max_dist_px: float = 20.0) -> Optional[Shape]:
        """Find shape endpoint/center at exactly snapped position"""
        shapes = self.cad_engine.get_shapes(self.view_name)
        best_shape = None
        best_dist_px = max_dist_px
        for s in shapes:
            if s.type == 'dimension':
                continue
            pts = []
            if s.type == 'line':
                pts = [s.start, s.end]
            elif s.type in ('circle', 'arc'):
                pts = [s.center]
            elif s.type == 'rectangle':
                x, y, w, h = s.rect
                pts = [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
            elif s.type == 'polygon':
                pts = s.points
            for p in pts:
                d_px = self._get_distance_in_pixels(pos, QPointF(p[0], p[1]))
                if d_px < best_dist_px:
                    best_dist_px = d_px
                    best_shape = s
        return best_shape

    def _shape_to_shapely_geom(self, shape: Shape) -> Optional[sg.base.BaseGeometry]:
        """Convert CAD shape to Shapely geometry for Boolean/intersection ops"""
        if isinstance(shape, Line):
            return sg.LineString([shape.start, shape.end])
        elif isinstance(shape, Rectangle):
            x, y, w, h = shape.rect
            return sg.box(x, y, x + w, y + h)
        elif isinstance(shape, Circle):
            return sg.Point(shape.center).buffer(shape.radius)
        elif isinstance(shape, Polygon):
            if len(shape.points) >= 3:
                return sg.Polygon(shape.points)
            elif len(shape.points) == 2:
                return sg.LineString(shape.points)
        elif isinstance(shape, Arc):
            pts = self.cad_engine.shape_to_points(shape)
            if len(pts) >= 2:
                return sg.LineString(pts)
        return None

    def _execute_trim(self, clicked_line: Line, click_pos: QPointF):
        """Trim line segment at intersections, deleting clicked section"""
        l_start = clicked_line.start
        l_end = clicked_line.end
        line_geom = sg.LineString([l_start, l_end])
        
        intersections = []
        shapes = self.cad_engine.get_shapes(self.view_name)
        for s in shapes:
            if s.id == clicked_line.id or s.type == 'dimension':
                continue
            geom = self._shape_to_shapely_geom(s)
            if geom is not None:
                boundary = geom.boundary if hasattr(geom, 'boundary') else geom
                inter = line_geom.intersection(boundary)
                if not inter.is_empty:
                    if inter.geom_type == 'Point':
                        intersections.append((inter.x, inter.y))
                    elif inter.geom_type == 'MultiPoint':
                        for pt in inter.geoms:
                            intersections.append((pt.x, pt.y))
                            
        S = np.array(l_start)
        E = np.array(l_end)
        v = E - S
        v_len2 = np.sum(v*v)
        if v_len2 < 0.1:
            return
            
        t_vals = [0.0, 1.0]
        for p in intersections:
            pt = np.array(p)
            t = np.dot(pt - S, v) / v_len2
            if 0.001 < t < 0.999:
                t_vals.append(t)
                
        t_vals = sorted(list(set(t_vals)))
        
        P_click = np.array([click_pos.x(), click_pos.y()])
        t_click = np.dot(P_click - S, v) / v_len2
        
        self.cad_engine.remove_shape(clicked_line.id, self.view_name)
        
        layer = clicked_line.layer
        for i in range(len(t_vals) - 1):
            t1, t2 = t_vals[i], t_vals[i+1]
            if t1 <= t_click <= t2:
                continue
            pt1 = S + t1 * v
            pt2 = S + t2 * v
            new_line = Line((pt1[0], pt1[1]), (pt2[0], pt2[1]), layer)
            self.cad_engine.add_shape(new_line, self.view_name)
            
        self.rebuild_scene()
        self.shape_drawn.emit()
        self.statusBar_msg("Trimmed line segment.")

    def _execute_extend(self, clicked_line: Line, click_pos: QPointF):
        """Extend line endpoint to nearest intersecting profile boundary"""
        S = np.array(clicked_line.start)
        E = np.array(clicked_line.end)
        C = np.array([click_pos.x(), click_pos.y()])
        
        dist_s = np.linalg.norm(C - S)
        dist_e = np.linalg.norm(C - E)
        extend_start = dist_s < dist_e
        
        if extend_start:
            origin = E
            direction = S - E
        else:
            origin = S
            direction = E - S
            
        dir_len = np.linalg.norm(direction)
        if dir_len < 0.1:
            return
        dir_unit = direction / dir_len
        
        ray = sg.LineString([origin, origin + dir_unit * 10000.0])
        
        closest_intersection = None
        closest_dist = 10000.0
        
        shapes = self.cad_engine.get_shapes(self.view_name)
        for s in shapes:
            if s.id == clicked_line.id or s.type == 'dimension':
                continue
            geom = self._shape_to_shapely_geom(s)
            if geom is not None:
                boundary = geom.boundary if hasattr(geom, 'boundary') else geom
                inter = ray.intersection(boundary)
                if not inter.is_empty:
                    pts = []
                    if inter.geom_type == 'Point':
                        pts.append((inter.x, inter.y))
                    elif inter.geom_type == 'MultiPoint':
                        for pt in inter.geoms:
                            pts.append((pt.x, pt.y))
                            
                    for pt in pts:
                        p_arr = np.array(pt)
                        ref_pt = S if extend_start else E
                        v_from_ref = p_arr - ref_pt
                        if np.dot(v_from_ref, dir_unit) > 0.1:
                            d = np.linalg.norm(p_arr - ref_pt)
                            if d < closest_dist:
                                closest_dist = d
                                closest_intersection = pt
                                
        if closest_intersection is not None:
            self.cad_engine.remove_shape(clicked_line.id, self.view_name)
            if extend_start:
                new_line = Line(closest_intersection, clicked_line.end, clicked_line.layer, clicked_line.id)
            else:
                new_line = Line(clicked_line.start, closest_intersection, clicked_line.layer, clicked_line.id)
            self.cad_engine.add_shape(new_line, self.view_name)
            self.rebuild_scene()
            self.shape_drawn.emit()
            self.statusBar_msg("Extended line segment.")
        else:
            self.statusBar_msg("No boundary found to extend to.")

    def _execute_fillet(self, line1: Line, line2: Line, R: float):
        """Atomic corner fillet operation generating tangent trimmed lines and Arc"""
        P1 = np.array(line1.start)
        P2 = np.array(line1.end)
        Q1 = np.array(line2.start)
        Q2 = np.array(line2.end)
        
        v1 = P2 - P1
        v2 = Q2 - Q1
        
        denom = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(denom) < 1e-4:
            self.statusBar_msg("Error: Lines are parallel.")
            return
            
        rhs = Q1 - P1
        t = (rhs[0] * (-v2[1]) - rhs[1] * (-v2[0])) / denom
        P_inter = P1 + t * v1
        
        d_start1 = np.linalg.norm(P1 - P_inter)
        d_end1 = np.linalg.norm(P2 - P_inter)
        O1 = P1 if d_start1 > d_end1 else P2
        u1 = (O1 - P_inter) / (d_start1 if d_start1 > d_end1 else d_end1)
        
        d_start2 = np.linalg.norm(Q1 - P_inter)
        d_end2 = np.linalg.norm(Q2 - P_inter)
        O2 = Q1 if d_start2 > d_end2 else Q2
        u2 = (O2 - P_inter) / (d_start2 if d_start2 > d_end2 else d_end2)
        
        theta = np.arccos(np.clip(np.dot(u1, u2), -1.0, 1.0))
        d_tangent = R / np.tan(theta / 2.0)
        
        if np.linalg.norm(O1 - P_inter) < d_tangent or np.linalg.norm(O2 - P_inter) < d_tangent:
            self.statusBar_msg("Error: Fillet radius too large for these lines.")
            return
            
        T1 = P_inter + d_tangent * u1
        T2 = P_inter + d_tangent * u2
        
        # Bisector
        bisect = u1 + u2
        bisect_len = np.linalg.norm(bisect)
        if bisect_len < 1e-4:
            return
        bisect_unit = bisect / bisect_len
        C = P_inter + (R / np.sin(theta / 2.0)) * bisect_unit
        
        # Angles relative to center C
        w1 = T1 - C
        w2 = T2 - C
        start_ang = np.degrees(np.arctan2(-w1[1], w1[0])) % 360
        end_ang = np.degrees(np.arctan2(-w2[1], w2[0])) % 360
        sweep = (end_ang - start_ang) % 360
        if sweep > 180:
            start_ang, end_ang = end_ang, start_ang
            
        # Atomic database edit
        self.cad_engine.remove_shape(line1.id, self.view_name)
        self.cad_engine.remove_shape(line2.id, self.view_name)
        
        # Add trimmed lines and connecting arc
        self.cad_engine.add_shape(Line((O1[0], O1[1]), (T1[0], T1[1]), line1.layer, line1.id), self.view_name)
        self.cad_engine.add_shape(Line((O2[0], O2[1]), (T2[0], T2[1]), line2.layer, line2.id), self.view_name)
        
        fillet_arc = Arc((C[0], C[1]), R, start_ang, end_ang, line1.layer)
        self.cad_engine.add_shape(fillet_arc, self.view_name)
        
        # Save state once (single transaction)
        self.cad_engine._save_state(f"Fillet Corners (R={R:.1f})")
        self.rebuild_scene()
        self.shape_drawn.emit()
        self.statusBar_msg(f"Fillet corner added (R={R:.1f}).")

    def _execute_chamfer(self, line1: Line, line2: Line, d1: float, d2: float):
        """Atomic corner chamfer operation generating tangent trimmed lines and bevel Line"""
        P1 = np.array(line1.start)
        P2 = np.array(line1.end)
        Q1 = np.array(line2.start)
        Q2 = np.array(line2.end)
        
        v1 = P2 - P1
        v2 = Q2 - Q1
        
        denom = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(denom) < 1e-4:
            self.statusBar_msg("Error: Lines are parallel.")
            return
            
        rhs = Q1 - P1
        t = (rhs[0] * (-v2[1]) - rhs[1] * (-v2[0])) / denom
        P_inter = P1 + t * v1
        
        d_start1 = np.linalg.norm(P1 - P_inter)
        d_end1 = np.linalg.norm(P2 - P_inter)
        O1 = P1 if d_start1 > d_end1 else P2
        u1 = (O1 - P_inter) / (d_start1 if d_start1 > d_end1 else d_end1)
        
        d_start2 = np.linalg.norm(Q1 - P_inter)
        d_end2 = np.linalg.norm(Q2 - P_inter)
        O2 = Q1 if d_start2 > d_end2 else Q2
        u2 = (O2 - P_inter) / (d_start2 if d_start2 > d_end2 else d_end2)
        
        if np.linalg.norm(O1 - P_inter) < d1 or np.linalg.norm(O2 - P_inter) < d2:
            self.statusBar_msg("Error: Chamfer distances too large for these lines.")
            return
            
        T1 = P_inter + d1 * u1
        T2 = P_inter + d2 * u2
        
        # Atomic database edit
        self.cad_engine.remove_shape(line1.id, self.view_name)
        self.cad_engine.remove_shape(line2.id, self.view_name)
        
        self.cad_engine.add_shape(Line((O1[0], O1[1]), (T1[0], T1[1]), line1.layer, line1.id), self.view_name)
        self.cad_engine.add_shape(Line((O2[0], O2[1]), (T2[0], T2[1]), line2.layer, line2.id), self.view_name)
        
        chamfer_line = Line((T1[0], T1[1]), (T2[0], T2[1]), line1.layer)
        self.cad_engine.add_shape(chamfer_line, self.view_name)
        
        # Save state once
        self.cad_engine._save_state(f"Chamfer Corners (d1={d1:.1f}, d2={d2:.1f})")
        self.rebuild_scene()
        self.shape_drawn.emit()
        self.statusBar_msg(f"Chamfer bevel added (d1={d1:.1f}, d2={d2:.1f}).")

    def _execute_offset(self, shape: Shape, dist: float, click_pos: QPointF):
        """Construct a parallel offset geometry shape based on side clicked, normalizing CCW winding"""
        geom = self._shape_to_shapely_geom(shape)
        if geom is None:
            return
            
        new_shape = None
        layer = shape.layer
        
        if isinstance(shape, Line):
            left_geom = geom.parallel_offset(dist, side='left')
            right_geom = geom.parallel_offset(dist, side='right')
            C_pt = sg.Point(click_pos.x(), click_pos.y())
            offset_geom = left_geom if left_geom.distance(C_pt) < right_geom.distance(C_pt) else right_geom
            if not offset_geom.is_empty:
                coords = list(offset_geom.coords)
                new_shape = Line(coords[0], coords[1], layer)
                
        elif isinstance(shape, Circle):
            C_pt = sg.Point(shape.center[0], shape.center[1])
            click_pt = sg.Point(click_pos.x(), click_pos.y())
            outside = click_pt.distance(C_pt) > shape.radius
            new_r = shape.radius + dist if outside else shape.radius - dist
            if new_r > 0.1:
                new_shape = Circle(shape.center, new_r, layer)
                
        elif isinstance(shape, (Rectangle, Polygon)):
            C_pt = sg.Point(click_pos.x(), click_pos.y())
            # Check if clicked inside
            inside = geom.contains(C_pt)
            offset_geom = geom.buffer(-dist if inside else dist)
            if not offset_geom.is_empty and offset_geom.geom_type == 'Polygon':
                # Normalize CCW winding
                coords = list(offset_geom.exterior.coords)[:-1]
                if not offset_geom.exterior.is_ccw:
                    coords = coords[::-1]
                new_shape = Polygon(coords, layer)
                
        if new_shape:
            self.cad_engine.add_shape(new_shape, self.view_name)
            self.rebuild_scene()
            self.shape_drawn.emit()
            self.statusBar_msg(f"Offset shape created (dist={dist:.1f}).")
        else:
            self.statusBar_msg("Error: Invalid offset geometry.")

    def _update_profile_closure(self) -> List[QPointF]:
        """Scan canvas visible/hidden line endpoints and return open dangles"""
        shapes = self.cad_engine.get_shapes(self.view_name)
        lines = []
        for s in shapes:
            if s.type == 'line' and s.layer in ('Visible', 'Hidden'):
                lines.append(s)
                
        if not lines:
            return []
            
        endpoint_counts = {}
        for line in lines:
            for pt in (line.start, line.end):
                key = (round(pt[0], 2), round(pt[1], 2))
                if key not in endpoint_counts:
                    endpoint_counts[key] = []
                endpoint_counts[key].append(pt)
                
        dangles = []
        for key, pts in endpoint_counts.items():
            if len(pts) == 1:
                dangles.append(QPointF(pts[0][0], pts[0][1]))
                
        return dangles

    def has_open_profile(self) -> bool:
        """Return True if the profile on the active layer is not watertight (has open endpoints)"""
        return len(self._update_profile_closure()) > 0

    def statusBar_msg(self, msg: str):
        """Output status feedback on MainWindow status bar"""
        win = self.window()
        if win and hasattr(win, 'statusBar'):
            win.statusBar().showMessage(msg)

    # View Controls & Mouse Events
    def mousePressEvent(self, event: QMouseEvent):
        """Handle drafting, edit click routing, and view pan selections"""
        scene_pos = self.mapToScene(event.pos())
        
        # Pan triggers via Middle Mouse Button
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            if self.current_tool in ('trim', 'extend', 'fillet', 'chamfer', 'offset'):
                self._handle_modification_tool_click(scene_pos)
                event.accept()
                return
            elif self.current_tool != 'select':
                # Determine snap target
                snapped = self.get_snap_point(scene_pos)
                
                # Check for Ortho constrain
                if self.ortho_mode and self.start_point:
                    snapped = self.apply_ortho_constrain(self.start_point, snapped)
                    
                self._input_drawing_point(snapped)
                event.accept()
                return
                
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event: QMouseEvent):
        """Update coordinates, previews, projection guides, active snapping, and HUD overlay positioning"""
        scene_pos = self.mapToScene(event.pos())
        
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
            
        snapped = self.get_snap_point(scene_pos)
        if self.ortho_mode and self.start_point:
            snapped = self.apply_ortho_constrain(self.start_point, snapped)
            
        # Calculate dynamic status coordinate displays: absolute, and relative polar
        dx = snapped.x()
        dy = snapped.y()
        length = 0.0
        angle = 0.0
        
        if self.start_point:
            lx = snapped.x() - self.start_point.x()
            ly = snapped.y() - self.start_point.y()
            length = np.sqrt(lx*lx + ly*ly)
            angle = np.degrees(np.arctan2(-ly, lx))
            if angle < 0:
                angle += 360.0
                
        if self.is_drawing:
            self._update_temp_preview(snapped)
            
            # Position and update HUD overlay
            if self.current_tool == 'line' or (self.current_tool == 'dimension' and self.start_point):
                self.hud.show()
                hud_pos = event.pos() + QPoint(15, 15)
                self.hud.move(hud_pos)
                self.hud_len.setText(f"{length:.1f}")
                self.hud_angle.setText(f"{angle:.1f}")
        else:
            self.hud.hide()
            
        self.cursor_moved_in_scene.emit(self.view_name, snapped)
        
        self.mouse_coords_changed.emit(dx, dy, length, angle)
        self.scene().update()
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Release panning cursor"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double click closes polygon shape drafting"""
        if event.button() == Qt.MouseButton.LeftButton and self.current_tool == 'polygon':
            self._finalize_polygon()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """Precision zoom centered around the cursor"""
        zoom_factor = 1.15
        if event.angleDelta().y() < 0:
            zoom_factor = 1.0 / zoom_factor
            
        old_scene_pos = self.mapToScene(event.position().toPoint())
        self.scale(zoom_factor, zoom_factor)
        
        # Readjust scene to keep mouse position aligned under zoom
        new_scene_pos = self.mapToScene(event.position().toPoint())
        delta = new_scene_pos - old_scene_pos
        self.translate(delta.x(), delta.y())
        
        event.accept()
        
    def leaveEvent(self, event):
        """Clear guide lines when cursor exits view window"""
        self.active_snap_point = None
        self.clear_projection_guides()
        self.hud.hide()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        """Handle key presses like Shift for Ortho and Tab for cursor HUD focus"""
        if event.key() == Qt.Key.Key_Tab and self.is_drawing and self.hud.isVisible():
            self.hud_len.setFocus()
            self.hud_len.selectAll()
            event.accept()
            return
            
        if event.key() == Qt.Key.Key_Shift:
            self.ortho_mode = True
            # Update coordinate preview with ortho lock active
            cursor_pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
            self.mouseMoveEvent(QMouseEvent(
                QMouseEvent.Type.MouseMove,
                QPointF(self.mapFromScene(cursor_pos)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ShiftModifier
            ))
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Handle key releases like Shift for Ortho mode"""
        if event.key() == Qt.Key.Key_Shift:
            self.ortho_mode = False
            cursor_pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
            self.mouseMoveEvent(QMouseEvent(
                QMouseEvent.Type.MouseMove,
                QPointF(self.mapFromScene(cursor_pos)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier
            ))
        super().keyReleaseEvent(event)
