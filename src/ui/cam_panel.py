"""
CAM & CNC G-Code Control Panel.
Manages Tool Library, Feature-Based Machining (FBM) Operations,
Toolpath Generation, and ISO 6983 G-Code Post-Processing.
"""

from typing import List, Dict, Optional, Tuple, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QLabel, QTextEdit, QGroupBox, QHeaderView, QSplitter,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from shapely.geometry import Polygon, box

from ..engine.cam_engine import (
    ToolType, ToolDefinition, OperationType, ToolpathSegment, MachiningOperation,
    MATERIAL_SURFACE_SPEEDS, calculate_speeds_and_feeds, get_default_tool_library
)
from ..engine.toolpath_planner import ToolpathPlanner
from ..export.gcode_post import GCodePostProcessor
from ..engine.cad_engine import Rectangle, Circle, Line


class CAMPanel(QWidget):
    """Dock panel managing CNC Toolpaths and ISO 6983 G-Code generation"""
    toolpaths_updated = pyqtSignal(list)   # Emits List[ToolpathSegment] for 3D Viewport

    def __init__(self, cad_engine, parent=None):
        super().__init__(parent)
        self.cad_engine = cad_engine
        self.tool_library = get_default_tool_library()
        self.operations: List[MachiningOperation] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # 1. Material & Post Settings
        settings_group = QGroupBox("Machining Setup & Material")
        form_layout = QFormLayout(settings_group)

        self.material_combo = QComboBox()
        self.material_combo.addItems(list(MATERIAL_SURFACE_SPEEDS.keys()))
        form_layout.addRow("Stock Material:", self.material_combo)

        self.dialect_combo = QComboBox()
        self.dialect_combo.addItems(["HAAS_VF", "FANUC_0I", "GRBL_OPENBUILD"])
        form_layout.addRow("Post Dialect:", self.dialect_combo)

        layout.addWidget(settings_group)

        # 2. Splitter for Operations and G-Code Preview
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Operations Table
        ops_group = QGroupBox("Machining Operations (FBM)")
        ops_layout = QVBoxLayout(ops_group)

        self.ops_table = QTableWidget()
        self.ops_table.setColumnCount(4)
        self.ops_table.setHorizontalHeaderLabels(["Operation", "Tool", "Depth", "RPM / Feed"])
        self.ops_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.ops_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ops_layout.addWidget(self.ops_table)

        btn_row1 = QHBoxLayout()
        self.auto_fbm_btn = QPushButton("Auto-Detect Operations")
        self.auto_fbm_btn.setStyleSheet("background-color: #2D2D2D; color: white; padding: 4px;")
        self.auto_fbm_btn.clicked.connect(self.auto_generate_operations)
        btn_row1.addWidget(self.auto_fbm_btn)

        self.gen_toolpath_btn = QPushButton("Generate Toolpaths")
        self.gen_toolpath_btn.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 4px;")
        self.gen_toolpath_btn.clicked.connect(self.generate_toolpaths)
        btn_row1.addWidget(self.gen_toolpath_btn)

        ops_layout.addLayout(btn_row1)
        splitter.addWidget(ops_group)

        # G-Code Preview Text Viewer
        gcode_group = QGroupBox("G-Code Program Viewer (ISO 6983)")
        gcode_layout = QVBoxLayout(gcode_group)

        self.gcode_text = QTextEdit()
        self.gcode_text.setReadOnly(True)
        self.gcode_text.setFontFamily("Consolas")
        self.gcode_text.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-size: 10px;")
        gcode_layout.addWidget(self.gcode_text)

        btn_row2 = QHBoxLayout()
        self.time_label = QLabel("Est. Machining Time: 0.0s")
        btn_row2.addWidget(self.time_label)

        self.post_btn = QPushButton("Post G-Code File...")
        self.post_btn.setStyleSheet("background-color: #0E639C; color: white; font-weight: bold; padding: 4px;")
        self.post_btn.clicked.connect(self.export_gcode_file)
        btn_row2.addWidget(self.post_btn)

        gcode_layout.addLayout(btn_row2)
        splitter.addWidget(gcode_group)

        layout.addWidget(splitter)

    def auto_generate_operations(self):
        """Analyze 2D orthographic canvas entities and automatically synthesize FBM operations"""
        self.operations.clear()
        mat = self.material_combo.currentText()
        top_shapes = self.cad_engine.shapes.get('top', [])

        # 1. Detect outer stock bounding box for Facing & Contouring
        rects = [s for s in top_shapes if isinstance(s, Rectangle)]
        outer_rect = next((r for r in rects if r.layer == "Visible"), None)

        if outer_rect:
            # Operation 1: Facing
            tool_10 = self.tool_library[1] # 10mm endmill
            rpm, f_xy, f_z = calculate_speeds_and_feeds(mat, tool_10, OperationType.FACING)
            op_facing = MachiningOperation(
                op_id="op_face_01",
                name="Top Face Flattening",
                op_type=OperationType.FACING,
                tool=tool_10,
                target_depth=1.0,
                spindle_rpm=rpm,
                feed_xy=f_xy,
                feed_z=f_z
            )
            self.operations.append(op_facing)

            # Operation 2: Outer Contour Roughing
            rpm_c, f_xy_c, f_z_c = calculate_speeds_and_feeds(mat, tool_10, OperationType.CONTOUR)
            op_contour = MachiningOperation(
                op_id="op_contour_01",
                name="Workpiece Outer Contouring",
                op_type=OperationType.CONTOUR,
                tool=tool_10,
                target_depth=15.0,
                spindle_rpm=rpm_c,
                feed_xy=f_xy_c,
                feed_z=f_z_c
            )
            self.operations.append(op_contour)

        # 2. Detect internal hidden pockets
        hidden_pockets = [r for r in rects if r.layer == "Hidden"]
        for idx, p in enumerate(hidden_pockets, start=1):
            tool_6 = self.tool_library[2] # 6mm endmill
            rpm_p, f_xy_p, f_z_p = calculate_speeds_and_feeds(mat, tool_6, OperationType.POCKET_ROUGH)
            op_pocket = MachiningOperation(
                op_id=f"op_pocket_{idx}",
                name=f"Pocket Clearing #{idx}",
                op_type=OperationType.POCKET_ROUGH,
                tool=tool_6,
                target_depth=10.0,
                spindle_rpm=rpm_p,
                feed_xy=f_xy_p,
                feed_z=f_z_p
            )
            self.operations.append(op_pocket)

        # 3. Detect circles (Holes & Taps)
        circles = [s for s in top_shapes if isinstance(s, Circle)]
        for idx, c in enumerate(circles, start=1):
            d = 2.0 * c.radius
            tool_drill = self.tool_library[3] # 8.5mm drill
            rpm_d, f_xy_d, f_z_d = calculate_speeds_and_feeds(mat, tool_drill, OperationType.PECK)

            op_drill = MachiningOperation(
                op_id=f"op_drill_{idx}",
                name=f"Peck Drill Hole Ø{d:.1f}mm",
                op_type=OperationType.PECK,
                tool=tool_drill,
                target_depth=25.0,
                spindle_rpm=rpm_d,
                feed_xy=f_xy_d,
                feed_z=f_z_d
            )
            self.operations.append(op_drill)

        self._refresh_operations_table()

    def _refresh_operations_table(self):
        """Update the operations table view"""
        self.ops_table.setRowCount(len(self.operations))
        for r, op in enumerate(self.operations):
            self.ops_table.setItem(r, 0, QTableWidgetItem(op.name))
            self.ops_table.setItem(r, 1, QTableWidgetItem(f"T{op.tool.tool_no} (Ø{op.tool.diameter:.1f}mm)"))
            self.ops_table.setItem(r, 2, QTableWidgetItem(f"{op.target_depth:.1f} mm"))
            self.ops_table.setItem(r, 3, QTableWidgetItem(f"{int(op.spindle_rpm)} RPM / {int(op.feed_xy)} mm/min"))

    def generate_toolpaths(self):
        """Compute toolpath segments for all operations and stream to G-code viewer & 3D viewport"""
        if not self.operations:
            self.auto_generate_operations()

        all_segments: List[ToolpathSegment] = []
        top_shapes = self.cad_engine.shapes.get('top', [])
        rects = [s for s in top_shapes if isinstance(s, Rectangle)]
        outer_rect = next((r for r in rects if r.layer == "Visible"), None)
        hidden_pockets = [r for r in rects if r.layer == "Hidden"]
        circles = [s for s in top_shapes if isinstance(s, Circle)]

        for op in self.operations:
            op.segments.clear()

            if op.op_type == OperationType.FACING and outer_rect:
                rx, ry, rw, rh = outer_rect.rect
                op.segments = ToolpathPlanner.plan_facing(
                    stock_rect=(rx, ry, rw, rh),
                    tool=op.tool,
                    depth=op.target_depth,
                    feed_xy=op.feed_xy,
                    feed_z=op.feed_z
                )

            elif op.op_type == OperationType.CONTOUR and outer_rect:
                rx, ry, rw, rh = outer_rect.rect
                stock_poly = box(rx, ry, rx + rw, ry + rh)
                op.segments = ToolpathPlanner.plan_contour(
                    stock_poly=stock_poly,
                    tool=op.tool,
                    depth=op.target_depth,
                    is_outer=True,
                    feed_xy=op.feed_xy,
                    feed_z=op.feed_z
                )

            elif op.op_type == OperationType.POCKET_ROUGH:
                p_rect = hidden_pockets[0] if hidden_pockets else (outer_rect or Rectangle(rect=(-20, -20, 40, 40)))
                rx, ry, rw, rh = p_rect.rect
                p_poly = box(rx, ry, rx + rw, ry + rh)
                op.segments = ToolpathPlanner.plan_pocket_clearing(
                    pocket_poly=p_poly,
                    tool=op.tool,
                    depth=op.target_depth,
                    stepover_ratio=op.stepover,
                    feed_xy=op.feed_xy,
                    feed_z=op.feed_z
                )

            elif op.op_type in (OperationType.DRILL, OperationType.PECK):
                c = circles[0] if circles else Circle(center=(0.0, 0.0), radius=5.0)
                op.segments = ToolpathPlanner.plan_drilling_cycle(
                    center_xy=c.center,
                    hole_diameter=2.0 * c.radius,
                    depth=op.target_depth,
                    tool=op.tool,
                    feed_z=op.feed_z
                )

            elif op.op_type == OperationType.TAP:
                c = circles[0] if circles else Circle(center=(0.0, 0.0), radius=5.0)
                op.segments = ToolpathPlanner.plan_tapping_cycle(
                    center_xy=c.center,
                    thread_depth=op.target_depth,
                    tool=op.tool,
                    pitch=op.tool.pitch or 1.5,
                    spindle_rpm=op.spindle_rpm
                )

            all_segments.extend(op.segments)

        # Update G-Code Viewer
        dialect = self.dialect_combo.currentText()
        mat = self.material_combo.currentText()
        gcode_str = GCodePostProcessor.format_gcode(self.operations, dialect=dialect, material=mat)
        self.gcode_text.setPlainText(gcode_str)

        # Update Estimated Machining Time
        total_time_sec = GCodePostProcessor.estimate_machining_time(self.operations)
        self.time_label.setText(f"Est. Machining Time: {total_time_sec:.1f}s ({total_time_sec/60.0:.1f} min)")

        # Emit to 3D Viewport
        self.toolpaths_updated.emit(all_segments)

    def export_gcode_file(self):
        """Export formatted G-code to a .nc / .gcode file"""
        if not self.gcode_text.toPlainText():
            self.generate_toolpaths()

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CNC G-Code Program", "program.nc", "G-Code Files (*.nc *.gcode *.tap);;All Files (*)"
        )
        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.gcode_text.toPlainText())
            QMessageBox.information(self, "G-Code Exported", f"Successfully exported G-code program to:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Could not write G-code file:\n{str(e)}")
