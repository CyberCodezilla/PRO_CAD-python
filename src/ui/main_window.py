"""
Main Window - Primary PyQt6 layout and controller coordinating MVC data flow.
Integrates 2D vector graphic scenes, 3D OpenGL viewport, bottom command console, and reconstruction threads.
"""
import json
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QTabWidget, QLineEdit, QLabel, QStatusBar,
    QMessageBox, QFileDialog, QDockWidget, QTreeWidget, 
    QTreeWidgetItem, QPushButton, QCheckBox, QComboBox, 
    QSlider, QDoubleSpinBox, QFormLayout, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QAction, QKeySequence, QCursor

from .canvas import DrawingCanvas
from .toolbar import DrawingToolbar
from .viewport_3d import OpenGLViewport
from ..engine.cad_engine import CADEngine, Shape, Line, Rectangle, Circle, Polygon, Arc, Dimension
from ..reconstruction.reconstructor import Reconstructor3D

class MainWindow(QMainWindow):
    """Main application window container"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python CAD Pro - Precision 2D to 3D CAD")
        self.setGeometry(100, 100, 1400, 900)
        
        # Core Models & Engines
        self.cad_engine = CADEngine()
        self.reconstructor = Reconstructor3D()
        
        self._init_ui()
        self._create_menus()
        self._apply_theme()
        
        # Initial status message
        self.statusBar().showMessage("Ready - Select a drawing tool and start drafting")
        
    def _init_ui(self):
        """Build layout panels"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Horizontal Split Panel: Left (Tools + 2D), Right (3D Viewport)
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Panel layout: Vertical Toolbar + 2D Drafting Tabs
        left_panel_widget = QWidget()
        left_panel_layout = QHBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(0)
        
        # 1. Left Vertical Toolbar
        self.toolbar = DrawingToolbar(self)
        self.toolbar.tool_selected.connect(self._on_tool_selected)
        self.toolbar.layer_changed.connect(self._on_layer_changed)
        self.toolbar.view_mode_changed.connect(self._on_view_mode_changed)
        left_panel_layout.addWidget(self.toolbar)
        
        # 2. 2D Drafting Unified Orthographic Sheet Workspace
        self.canvas = DrawingCanvas(self.cad_engine, 'unified', self)
        self.canvas.mouse_coords_changed.connect(self._on_mouse_coords_changed)
        self.canvas.shape_drawn.connect(self._trigger_reconstruction)
        
        left_panel_layout.addWidget(self.canvas)
        content_splitter.addWidget(left_panel_widget)
        
        # 3. Right Panel: 3D OpenGL Viewport
        self.viewport_3d = OpenGLViewport(self)
        content_splitter.addWidget(self.viewport_3d)
        
        # Set splitter layout size ratio (60% 2D canvas, 40% 3D viewport)
        content_splitter.setSizes([850, 550])
        content_splitter.setCollapsible(0, False)
        content_splitter.setCollapsible(1, False)
        
        main_layout.addWidget(content_splitter, stretch=1)
        
        # 4. Bottom Command Console Layout
        console_widget = QWidget()
        console_widget.setObjectName("ConsoleWidget")
        console_layout = QHBoxLayout(console_widget)
        console_layout.setContentsMargins(10, 5, 10, 5)
        console_layout.setSpacing(5)
        
        console_label = QLabel("Command:")
        console_label.setStyleSheet("color: #00FFFF; font-weight: bold; font-family: Consolas;")
        console_layout.addWidget(console_label)
        
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Enter coordinate offset (e.g. '100,50' or relative distance '100') or absolute coordinate ('#x,y')")
        self.command_input.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3C3C3C;
                border-radius: 3px;
                padding: 4px;
                font-family: Consolas;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #007ACC;
            }
        """)
        self.command_input.returnPressed.connect(self._on_command_entered)
        console_layout.addWidget(self.command_input)
        
        main_layout.addWidget(console_widget)
        
        # 5. Status Bar
        self.setStatusBar(QStatusBar())
        
        # 6. Initialize properties and view control docks
        self._init_docks()
        
    def _create_menus(self):
        """Create menu items"""
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("&File")
        
        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)
        
        open_action = QAction("&Open Project...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)
        
        save_action = QAction("&Save Project...", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        import_dxf_action = QAction("Import DXF...", self)
        import_dxf_action.triggered.connect(self._import_dxf)
        file_menu.addAction(import_dxf_action)
        
        export_dxf_action = QAction("Export DXF...", self)
        export_dxf_action.triggered.connect(self._export_dxf)
        file_menu.addAction(export_dxf_action)
        
        file_menu.addSeparator()
        
        export_stl_action = QAction("Export STL...", self)
        export_stl_action.triggered.connect(lambda: self._export_mesh('stl'))
        file_menu.addAction(export_stl_action)
        
        export_obj_action = QAction("Export OBJ...", self)
        export_obj_action.triggered.connect(lambda: self._export_mesh('obj'))
        file_menu.addAction(export_obj_action)
        
        export_3mf_action = QAction("Export 3MF...", self)
        export_3mf_action.triggered.connect(lambda: self._export_mesh('3mf'))
        file_menu.addAction(export_3mf_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)
        
        # View Menu
        view_menu = menubar.addMenu("&View")
        
        # Grid Snap toggle
        self.grid_snap_action = QAction("Enable Grid Snap", self, checkable=True)
        self.grid_snap_action.setChecked(True)
        self.grid_snap_action.triggered.connect(self._toggle_grid_snap)
        view_menu.addAction(self.grid_snap_action)
        
        # Object Snap toggle
        self.obj_snap_action = QAction("Enable Object Snap (OSNAP)", self, checkable=True)
        self.obj_snap_action.setChecked(True)
        self.obj_snap_action.triggered.connect(self._toggle_obj_snap)
        view_menu.addAction(self.obj_snap_action)
        
        # Ortho Mode toggle
        self.ortho_action = QAction("Enable Ortho Mode", self, checkable=True)
        self.ortho_action.setShortcut(QKeySequence("F8"))
        self.ortho_action.setChecked(False)
        self.ortho_action.triggered.connect(self._toggle_ortho_mode)
        view_menu.addAction(self.ortho_action)

        # 45° Miter Line toggle
        self.miter_action = QAction("Show 45° Miter Guide Line", self, checkable=True)
        self.miter_action.setChecked(True)
        self.miter_action.triggered.connect(self._toggle_miter_line)
        view_menu.addAction(self.miter_action)
        
        view_menu.addSeparator()
        
        layer_mgr_action = QAction("Layer Manager...", self)
        layer_mgr_action.triggered.connect(self._open_layer_manager)
        view_menu.addAction(layer_mgr_action)
        
        # Reconstruction Menu
        reconstruct_menu = menubar.addMenu("&Reconstruct")
        
        reconstruct_action = QAction("Generate 3D Model", self)
        reconstruct_action.setShortcut(QKeySequence("Ctrl+R"))
        reconstruct_action.triggered.connect(self._trigger_reconstruction)
        reconstruct_menu.addAction(reconstruct_action)
        
        # Help Menu
        help_menu = menubar.addMenu("&Help")
        
        guide_action = QAction("&User Guide", self)
        guide_action.setShortcut(QKeySequence("F1"))
        guide_action.triggered.connect(self._show_help_dialog)
        help_menu.addAction(guide_action)
        
    def _apply_theme(self):
        """Apply modern dark CAD interface styling"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E1E;
            }
            QMenuBar {
                background-color: #2D2D2D;
                color: #D4D4D4;
                border-bottom: 1px solid #3C3C3C;
            }
            QMenuBar::item:selected {
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
            QStatusBar {
                background-color: #007ACC;
                color: #FFFFFF;
                font-family: Consolas;
                font-size: 11px;
            }
            QTabWidget::pane {
                border: 1px solid #3C3C3C;
                background-color: #1E1E1E;
            }
            QTabBar::tab {
                background-color: #2D2D2D;
                color: #8C8C8C;
                padding: 6px 12px;
                border: 1px solid #3C3C3C;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background-color: #1E1E1E;
                color: #00FFFF;
                font-weight: bold;
                border-bottom: 1px solid #1E1E1E;
            }
            QSplitter::handle {
                background-color: #2D2D2D;
                width: 3px;
            }
            #ConsoleWidget {
                background-color: #252526;
                border-top: 1px solid #3C3C3C;
            }
        """)

    def _on_tool_selected(self, tool_name: str):
        """Sync active tool with 2D unified canvas"""
        self.cad_engine.set_active_tool(tool_name)
        self.canvas.set_tool(tool_name)
        self.statusBar().showMessage(f"Tool selected: {tool_name.upper()}")
        
    def _on_layer_changed(self, layer_name: str):
        """Sync active layer in cad engine"""
        self.cad_engine.set_active_layer(layer_name)
        self.statusBar().showMessage(f"Active Layer: {layer_name.upper()}")

    def _on_view_mode_changed(self, view_mode_text: str):
        """Update active view mode in CAD engine and refresh canvas indicators"""
        self.cad_engine.set_active_view_mode(view_mode_text)
        self.canvas.rebuild_scene()
        self.statusBar().showMessage(f"Active View Mode set to: {view_mode_text}")

    def _on_mouse_coords_changed(self, x: float, y: float, length: float, angle: float):
        """Update status bar coordinate feedback"""
        # Format coordinate text
        coord_txt = f"X: {x:8.1f} | Y: {-y:8.1f}"  # Invert Y to show projection coords
        
        # Format snap properties
        snap_mode = []
        if self.grid_snap_action.isChecked():
            snap_mode.append("GRID")
        if self.obj_snap_action.isChecked():
            snap_mode.append("OSNAP")
        snap_status = "+".join(snap_mode) if snap_mode else "FREE"
        
        ortho_status = "ORTHO" if self.ortho_action.isChecked() else "POLAR"
        
        status_msg = f" {coord_txt}  |  Mode: {ortho_status}  |  Snap: {snap_status}"
        
        # Add relative dimension details when drawing
        if length > 0.01:
            dim_txt = f"  [ Length: {length:.1f} < {angle:.1f}° ]"
            status_msg += dim_txt
            
        self.statusBar().showMessage(status_msg)

    def _sync_projection_guides(self, source_view: str, scene_pos: QPointF):
        """Synchronize projection guidelines across 2D views"""
        for name, canvas in self.canvases.items():
            if name != source_view:
                canvas.update_projection_guide(source_view, scene_pos)

    def _on_command_entered(self):
        """Parse parametric input coordinate string and forward to active view canvas"""
        text = self.command_input.text().strip()
        if not text:
            return
            
        # Command word shortcuts (AutoCAD style shortcuts for human friendliness)
        lower_text = text.lower()
        if lower_text == 'undo':
            self._undo()
            self.command_input.clear()
            return
        elif lower_text == 'redo':
            self._redo()
            self.command_input.clear()
            return
        elif lower_text in ('clear', 'cls'):
            self.cad_engine.clear_all()
            self.canvas.rebuild_scene()
            self._trigger_reconstruction()
            self.statusBar().showMessage("Cleared All Views")
            self.command_input.clear()
            return
        elif lower_text in ('help', '?', 'h'):
            self._show_help_dialog()
            self.command_input.clear()
            return
        elif lower_text in ('region', 'r'):
            self.toolbar.set_active_tool('region')
            self._on_tool_selected('region')
            self.command_input.clear()
            self.statusBar().showMessage("Active Tool: DEFINE REGION")
            return
        elif lower_text in ('circle', 'c'):
            self.toolbar.set_active_tool('circle')
            self._on_tool_selected('circle')
            self.command_input.clear()
            self.statusBar().showMessage("Active Tool: CIRCLE")
            return
        elif lower_text in ('line', 'l'):
            self.toolbar.set_active_tool('line')
            self._on_tool_selected('line')
            self.command_input.clear()
            self.statusBar().showMessage("Active Tool: LINE")
            return
        elif lower_text in ('rect', 'rectangle', 'rec'):
            self.toolbar.set_active_tool('rectangle')
            self._on_tool_selected('rectangle')
            self.command_input.clear()
            self.statusBar().showMessage("Active Tool: RECTANGLE")
            return
        elif lower_text in ('select', 'sel', 's'):
            self.toolbar.set_active_tool('select')
            self._on_tool_selected('select')
            self.command_input.clear()
            self.statusBar().showMessage("Active Tool: SELECT")
            return
        elif lower_text in ('polygon', 'poly', 'p'):
            self.toolbar.set_active_tool('polygon')
            self._on_tool_selected('polygon')
            self.command_input.clear()
            self.statusBar().showMessage("Active Tool: POLYGON")
            return
            
        is_absolute = False
        if text.startswith('#'):
            is_absolute = True
            text = text[1:].strip()
            
        # Parse inputs
        try:
            parts = text.replace(',', ' ').split()
            active_canvas = self.canvas
            
            if not active_canvas:
                return
                
            if len(parts) == 2:
                # Coordinate offset (dx, dy)
                val1 = float(parts[0])
                val2 = float(parts[1])
                # Reconstruct Y representation since canvas is inverted
                canvas_val2 = -val2
                active_canvas.command_input_point(val1, canvas_val2, is_absolute=is_absolute)
                self.command_input.clear()
                self.statusBar().showMessage(f"Parametric point entered: {val1}, {val2} ({'absolute' if is_absolute else 'relative'})")
                
            elif len(parts) == 1:
                # Length constraint/radius entry
                val = float(parts[0])
                if active_canvas.is_drawing and active_canvas.start_point:
                    # Resolve vector delta from start point to cursor
                    cursor_pos = active_canvas.mapToScene(active_canvas.mapFromGlobal(QCursor.pos()))
                    dx = cursor_pos.x() - active_canvas.start_point.x()
                    dy = cursor_pos.y() - active_canvas.start_point.y()
                    length = np.sqrt(dx*dx + dy*dy)
                    
                    if length < 0.01:
                        # Fallback direction: project along positive X-axis
                        dx = 1.0
                        dy = 0.0
                        length = 1.0
                        
                    scale = val / length
                    active_canvas.command_input_point(dx * scale, dy * scale, is_absolute=False)
                    self.command_input.clear()
                    self.statusBar().showMessage(f"Length/radius input entered: {val}")
                else:
                    self.statusBar().showMessage("Length entry requires active drawing segment.")
            else:
                self.statusBar().showMessage("Invalid command. Format: 'dx,dy' (relative), '#x,y' (absolute) or 'length'")
        except Exception as e:
            self.statusBar().showMessage(f"Error parsing coordinate: {str(e)}")

    def _trigger_reconstruction(self):
        """Asynchronously trigger the 3D CSG reconstruction process with validation and diagnostics"""
        # 1. Alignment Validation (Guardrail 2)
        valid, msg = self.cad_engine.validate_alignment(tolerance=5.0)
        if not valid:
            self.statusBar().showMessage(f"⚠ Alignment Warning: {msg}")
            QMessageBox.warning(self, "Orthographic Alignment Error", msg)
            return

        self.statusBar().showMessage("⚙️ Generating watertight 3D model...")
            
        # 2. Extract local shape profiles (Guardrails 1, 3, 4)
        tol = self.tolerance_spin.value() if hasattr(self, 'tolerance_spin') else 10.0
        top_shapes = self.cad_engine.get_local_shapes_for_view('top')
        front_shapes = self.cad_engine.get_local_shapes_for_view('front')
        side_shapes = self.cad_engine.get_local_shapes_for_view('side')

        self.reconstructor.run_reconstruction(
            top_shapes,
            front_shapes,
            side_shapes,
            callback_finished=self._on_reconstruction_finished,
            callback_error=self._on_reconstruction_error,
            angular_tolerance=tol
        )

    def _on_reconstruction_finished(self, mesh):
        """Receive the reconstructed mesh safely on the GUI Thread and update OpenGLViewport"""
        if mesh is not None and len(mesh.vertices) > 0:
            self.viewport_3d.set_mesh(mesh)
            self.statusBar().showMessage("✓ 3D Model updated successfully!")
        else:
            self.viewport_3d.set_mesh(None)
            self.statusBar().showMessage("⚠ Reconstruction returned an empty mesh. Draw profiles in views first.")
            
        # Update right-side properties panel tree view
        self._update_properties_panel()

    def _on_reconstruction_error(self, error_trace: str):
        """Handle error from background thread"""
        self.statusBar().showMessage("❌ Reconstruction Error! Click Help or check console log.")
        QMessageBox.critical(
            self,
            "Reconstruction Error",
            f"An error occurred during computational geometry operations:\n\n{error_trace}"
        )

    def _undo(self):
        """Undo last CAD operation"""
        success, description = self.cad_engine.undo()
        if success:
            self._sync_all_views()
            self._trigger_reconstruction()
            self.statusBar().showMessage(f"Undo: {description}")
        else:
            self.statusBar().showMessage("Nothing to undo")
            
    def _redo(self):
        """Redo last CAD operation"""
        success, description = self.cad_engine.redo()
        if success:
            self._sync_all_views()
            self._trigger_reconstruction()
            self.statusBar().showMessage(f"Redo: {description}")
        else:
            self.statusBar().showMessage("Nothing to redo")
            
    def _show_help_dialog(self):
        """Display an interactive, beautifully formatted CAD User Guide"""
        help_text = (
            "<h3>📘 Python CAD Pro - Engineering Graphics User Guide</h3>"
            "<p>Welcome to <b>Python CAD Pro</b>, a professional desktop CAD editor. "
            "Draft on the 2D orthographic canvases and reconstruct watertight 3D models instantly.</p>"
            
            "<h4>📌 1. Line Types (Engineering Graphics Convention)</h4>"
            "<ul>"
            "<li><b>Visible Layer (Solid Cyan):</b> Used to draft the outer solid boundaries of your part.</li>"
            "<li><b>Hidden Layer (Dashed Cyan):</b> Used to draft internal holes, pockets, or cuts. Hidden profiles are subtracted from visible profiles during 3D CSG reconstruction.</li>"
            "<li><b>Construction Layer (Faint Grey):</b> Alignment/layout lines. Ignored in 3D reconstruction.</li>"
            "</ul>"
            
            "<h4>📌 2. Drafting Tools & Snapping</h4>"
            "<ul>"
            "<li><b>Select Tool:</b> Select shapes on the active tab canvas. Press <b>Delete</b> key to remove selected shapes.</li>"
            "<li><b>Line, Rectangle, Circle, Polygon:</b> Select a shape drawing tool from the vertical toolbar. Click on the canvas to place points.</li>"
            "<li><b>Shift Key (Ortho Mode):</b> Hold the <b>Shift</b> key while drawing lines to snap/constrain segments to horizontal or vertical axes.</li>"
            "<li><b>OSNAP (Object Snapping):</b> Snaps to endpoints, midpoints, circle centers, and polygon vertices within 15px (indicated by yellow square).</li>"
            "<li><b>Grid Snapping:</b> Snaps coordinate placements to the nearest 10px grid intersection.</li>"
            "</ul>"
            
            "<h4>📌 3. Command Console Instructions</h4>"
            "Type parametric commands in the bottom bar and press <b>Enter</b>:"
            "<ul>"
            "<li><b>Relative Offset:</b> Type <code>dx,dy</code> (e.g. <code>100,50</code>) to place the next point relative to the last point.</li>"
            "<li><b>Absolute Coordinate:</b> Type <code>#x,y</code> (e.g. <code>#0,-100</code>) to place a point at exact coordinates.</li>"
            "<li><b>Strict Length:</b> Type a number (e.g. <code>250</code>) during active drawing to lock the line segment to that length along the cursor direction.</li>"
            "<li><b>Command shortcuts:</b> Type <code>undo</code>, <code>redo</code>, <code>clear</code>, or <code>help</code> in the console.</li>"
            "</ul>"
            
            "<h4>📌 4. 3D Viewport Navigation</h4>"
            "<ul>"
            "<li><b>Rotate Camera:</b> Left-Click and drag inside the 3D viewport.</li>"
            "<li><b>Pan Viewport:</b> Right-Click and drag inside the 3D viewport.</li>"
            "<li><b>Zoom In/Out:</b> Scroll your mouse wheel.</li>"
            "</ul>"
        )
        QMessageBox.information(self, "Python CAD Pro User Guide", help_text)
            
    def _sync_all_views(self):
        """Rebuild unified canvas view"""
        self.canvas.rebuild_scene()

    def _toggle_grid_snap(self, checked: bool):
        """Toggle grid snap state"""
        self.canvas.set_grid_snap(checked)
            
    def _toggle_obj_snap(self, checked: bool):
        """Toggle object snap state"""
        self.canvas.set_object_snap(checked)
            
    def _toggle_ortho_mode(self, checked: bool):
        """Toggle ortho mode"""
        self.ortho_action.setChecked(checked)
        self.canvas.set_ortho(checked)

    def _toggle_miter_line(self, checked: bool):
        """Toggle 45 degree miter line visibility"""
        self.miter_action.setChecked(checked)
        self.canvas.set_show_miter_line(checked)

    def _new_project(self):
        """Clear project workspace"""
        confirm = QMessageBox.question(
            self,
            "New Project",
            "Clear all active views and restart?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.cad_engine.clear_all()
            self._sync_all_views()
            self.viewport_3d.set_mesh(None)
            self.command_input.clear()
            self.statusBar().showMessage("New project initialized")

    def _export_mesh(self, format_ext: str):
        """Export the constructed mesh to file"""
        mesh = self.viewport_3d.mesh
        if mesh is None or len(mesh.vertices) == 0:
            QMessageBox.warning(self, "No 3D Model", "Please draw profiles and generate a 3D model first.")
            return
            
        file_filter = f"{format_ext.upper()} Files (*.{format_ext})"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export 3D Model as {format_ext.upper()}",
            "",
            file_filter
        )
        
        if filename:
            try:
                self.reconstructor.export(mesh, filename)
                QMessageBox.information(self, "Export Success", f"Mesh exported successfully to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not export file:\n{str(e)}")

    def closeEvent(self, event):
        """Safely terminate GL viewport and worker threads on window close"""
        self.viewport_3d.cleanup()
        if self.reconstructor.worker and self.reconstructor.worker.isRunning():
            self.reconstructor.worker.terminate()
            self.reconstructor.worker.wait()
        super().closeEvent(event)

    def _init_docks(self):
        """Create and place Right Panel Docks for Properties Tree and View Control parameters"""
        # 1. Properties Tree Dock
        self.properties_dock = QDockWidget("Properties Panel", self)
        self.properties_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.properties_tree = QTreeWidget()
        self.properties_tree.setHeaderLabels(["Entity", "Details"])
        self.properties_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                font-family: Consolas;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #FFFFFF;
                border: 1px solid #3C3C3C;
                padding: 4px;
            }
        """)
        self.properties_dock.setWidget(self.properties_tree)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.properties_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        
        # 2. 3D View Settings Dock
        self.controls_dock = QDockWidget("3D View Settings", self)
        self.controls_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        controls_widget = QWidget()
        controls_widget.setStyleSheet("background-color: #252526; color: #D4D4D4; font-size: 11px;")
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(8)
        
        # Snaps layout
        snaps_label = QLabel("Camera Snaps:")
        snaps_label.setStyleSheet("font-weight: bold; color: #00FFFF;")
        controls_layout.addWidget(snaps_label)
        
        snaps_btn_layout = QHBoxLayout()
        btn_front = QPushButton("Front")
        btn_side = QPushButton("Side")
        btn_top = QPushButton("Top")
        btn_iso = QPushButton("Isometric")
        
        btn_style = """
            QPushButton {
                background-color: #3C3C3C;
                color: #FFFFFF;
                border: 1px solid #555555;
                padding: 4px 6px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #007ACC;
            }
        """
        for btn in (btn_front, btn_side, btn_top, btn_iso):
            btn.setStyleSheet(btn_style)
            snaps_btn_layout.addWidget(btn)
            
        btn_front.clicked.connect(self.viewport_3d.snap_front)
        btn_side.clicked.connect(self.viewport_3d.snap_side)
        btn_top.clicked.connect(self.viewport_3d.snap_top)
        btn_iso.clicked.connect(self.viewport_3d.snap_iso)
        controls_layout.addLayout(snaps_btn_layout)
        
        controls_layout.addSpacing(5)
        
        # Section View Clipping
        clip_label = QLabel("Section View Cutting Plane:")
        clip_label.setStyleSheet("font-weight: bold; color: #00FFFF;")
        controls_layout.addWidget(clip_label)
        
        self.clip_chk = QCheckBox("Enable Section View")
        self.clip_chk.setStyleSheet("color: #FFFFFF;")
        self.clip_chk.stateChanged.connect(self._on_clip_toggled)
        controls_layout.addWidget(self.clip_chk)
        
        axis_layout = QHBoxLayout()
        axis_layout.addWidget(QLabel("Cut Axis:"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X", "Y", "Z"])
        self.axis_combo.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF; border: 1px solid #3C3C3C;")
        self.axis_combo.currentTextChanged.connect(self._on_clip_axis_changed)
        axis_layout.addWidget(self.axis_combo)
        controls_layout.addLayout(axis_layout)
        
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position:"))
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(-300, 300)
        self.pos_slider.setValue(0)
        self.pos_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #3C3C3C;
                height: 4px;
                background: #1E1E1E;
            }
            QSlider::handle:horizontal {
                background: #007ACC;
                width: 12px;
                margin: -4px 0;
                border-radius: 2px;
            }
        """)
        self.pos_slider.valueChanged.connect(self._on_clip_pos_changed)
        pos_layout.addWidget(self.pos_slider)
        controls_layout.addLayout(pos_layout)
        
        controls_layout.addSpacing(5)
        
        # Angular Tolerance Spinbox
        tol_label = QLabel("Tessellation Quality:")
        tol_label.setStyleSheet("font-weight: bold; color: #00FFFF;")
        controls_layout.addWidget(tol_label)
        
        tol_layout = QHBoxLayout()
        tol_layout.addWidget(QLabel("Angular Tol:"))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(1.0, 45.0)
        self.tolerance_spin.setValue(10.0)
        self.tolerance_spin.setDecimals(1)
        self.tolerance_spin.setSuffix("°")
        self.tolerance_spin.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF; border: 1px solid #3C3C3C;")
        self.tolerance_spin.valueChanged.connect(lambda: self._trigger_reconstruction())
        tol_layout.addWidget(self.tolerance_spin)
        controls_layout.addLayout(tol_layout)
        
        controls_layout.addStretch()
        self.controls_dock.setWidget(controls_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.controls_dock)

    def _on_clip_toggled(self, state):
        """Toggle OpenGL clipping planes status"""
        self.viewport_3d.section_enabled = (state == Qt.CheckState.Checked.value or state == True)
        self.viewport_3d.update()
        
    def _on_clip_axis_changed(self, text):
        """Update clipping axis orientation"""
        self.viewport_3d.section_axis = text
        self.viewport_3d.update()
        
    def _on_clip_pos_changed(self, value):
        """Update cutting plane offset location"""
        self.viewport_3d.section_pos = float(value)
        self.viewport_3d.update()

    def _update_properties_panel(self):
        """Sync Properties Tree View nodes with current CADEngine drawing shapes"""
        self.properties_tree.clear()
        for view_name in ('top', 'front', 'side'):
            view_item = QTreeWidgetItem(self.properties_tree, [f"{view_name.capitalize()} View", ""])
            shapes = self.cad_engine.get_shapes(view_name)
            for shape in shapes:
                if shape.type == 'line':
                    desc = f"Line ({shape.start[0]:.1f}, {shape.start[1]:.1f}) to ({shape.end[0]:.1f}, {shape.end[1]:.1f})"
                elif shape.type == 'rectangle':
                    x, y, w, h = shape.rect
                    desc = f"Rect ({x:.1f}, {y:.1f}) W:{w:.1f} H:{h:.1f}"
                elif shape.type == 'circle':
                    desc = f"Circle C:({shape.center[0]:.1f}, {shape.center[1]:.1f}) R:{shape.radius:.1f}"
                elif shape.type == 'arc':
                    desc = f"Arc C:({shape.center[0]:.1f}, {shape.center[1]:.1f}) R:{shape.radius:.1f} ({shape.start_angle:.1f}°-{shape.end_angle:.1f}°)"
                elif shape.type == 'polygon':
                    desc = f"Polygon ({len(shape.points)} pts)"
                elif shape.type == 'dimension':
                    desc = f"Dimension ({shape.text})"
                else:
                    desc = f"Shape: {shape.type}"
                    
                child_item = QTreeWidgetItem(view_item, [f"{shape.type.capitalize()} [{shape.layer}]", desc])
                child_item.setData(0, Qt.ItemDataRole.UserRole, (view_name, shape.id))
        self.properties_tree.expandAll()

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Open parameters dialog to edit shape properties numerically on double-click"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        view_name, shape_id = data
        shapes = self.cad_engine.get_shapes(view_name)
        shape = next((s for s in shapes if s.id == shape_id), None)
        if not shape:
            return
            
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Modify {shape.type.capitalize()}")
        layout = QFormLayout(dialog)
        
        # Layer Selection
        layer_combo = QComboBox()
        layer_combo.addItems(["Visible", "Hidden", "Construction"])
        layer_combo.setCurrentText(shape.layer)
        layout.addRow("Layer:", layer_combo)
        
        spinboxes = {}
        
        if shape.type == 'line':
            for label, val in [("Start X", shape.start[0]), ("Start Y", shape.start[1]), ("End X", shape.end[0]), ("End Y", shape.end[1])]:
                sb = QDoubleSpinBox()
                sb.setRange(-10000.0, 10000.0)
                sb.setValue(val)
                layout.addRow(f"{label}:", sb)
                spinboxes[label] = sb
        elif shape.type == 'rectangle':
            x, y, w, h = shape.rect
            for label, val in [("X", x), ("Y", y), ("Width", w), ("Height", h)]:
                sb = QDoubleSpinBox()
                sb.setRange(-10000.0, 10000.0)
                if label in ("Width", "Height"):
                    sb.setRange(0.1, 10000.0)
                sb.setValue(val)
                layout.addRow(f"{label}:", sb)
                spinboxes[label] = sb
        elif shape.type == 'circle':
            cx, cy = shape.center
            for label, val in [("Center X", cx), ("Center Y", cy), ("Radius", shape.radius)]:
                sb = QDoubleSpinBox()
                sb.setRange(-10000.0, 10000.0)
                if label == "Radius":
                    sb.setRange(0.1, 10000.0)
                sb.setValue(val)
                layout.addRow(f"{label}:", sb)
                spinboxes[label] = sb
        elif shape.type == 'arc':
            cx, cy = shape.center
            for label, val in [("Center X", cx), ("Center Y", cy), ("Radius", shape.radius), ("Start Angle", shape.start_angle), ("End Angle", shape.end_angle)]:
                sb = QDoubleSpinBox()
                sb.setRange(-10000.0, 10000.0)
                if label == "Radius":
                    sb.setRange(0.1, 10000.0)
                elif label in ("Start Angle", "End Angle"):
                    sb.setRange(-360.0, 360.0)
                sb.setValue(val)
                layout.addRow(f"{label}:", sb)
                spinboxes[label] = sb
        elif shape.type == 'dimension':
            txt_edit = QLineEdit(shape.text)
            layout.addRow("Text Override:", txt_edit)
            spinboxes["text"] = txt_edit
            
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            shape.layer = layer_combo.currentText()
            
            if shape.type == 'line':
                shape.start = (spinboxes["Start X"].value(), spinboxes["Start Y"].value())
                shape.end = (spinboxes["End X"].value(), spinboxes["End Y"].value())
            elif shape.type == 'rectangle':
                shape.rect = (spinboxes["X"].value(), spinboxes["Y"].value(), spinboxes["Width"].value(), spinboxes["Height"].value())
            elif shape.type == 'circle':
                shape.center = (spinboxes["Center X"].value(), spinboxes["Center Y"].value())
                shape.radius = spinboxes["Radius"].value()
            elif shape.type == 'arc':
                shape.center = (spinboxes["Center X"].value(), spinboxes["Center Y"].value())
                shape.radius = spinboxes["Radius"].value()
                shape.start_angle = spinboxes["Start Angle"].value()
                shape.end_angle = spinboxes["End Angle"].value()
            elif shape.type == 'dimension':
                shape.text = spinboxes["text"].text()
                
            self.cad_engine._save_state(f"Modify {shape.type.capitalize()}")
            self._sync_all_views()
            self._trigger_reconstruction()

    def _save_project(self):
        """Save native CAD project to .pcad JSON file"""
        filename, _ = QFileDialog.getSaveFileName(self, "Save CAD Project", "", "PCAD Project Files (*.pcad)")
        if filename:
            try:
                state = {
                    'top': [s.to_dict() for s in self.cad_engine.shapes['top']],
                    'front': [s.to_dict() for s in self.cad_engine.shapes['front']],
                    'side': [s.to_dict() for s in self.cad_engine.shapes['side']],
                }
                with open(filename, 'w') as f:
                    json.dump(state, f, indent=2)
                self.statusBar().showMessage(f"💾 Project saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Save Failed", f"Could not save project state:\n{str(e)}")

    def _open_project(self):
        """Load native CAD project from .pcad JSON file"""
        filename, _ = QFileDialog.getOpenFileName(self, "Load CAD Project", "", "PCAD Project Files (*.pcad)")
        if filename:
            try:
                with open(filename, 'r') as f:
                    state = json.load(f)
                self.cad_engine.clear_all()
                self.cad_engine.shapes = {
                    'top': [Shape.from_dict(s) for s in state.get('top', [])],
                    'front': [Shape.from_dict(s) for s in state.get('front', [])],
                    'side': [Shape.from_dict(s) for s in state.get('side', [])],
                }
                self.cad_engine._save_state("Load Project")
                self._sync_all_views()
                self._trigger_reconstruction()
                self.statusBar().showMessage(f"📂 Project loaded successfully from {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Load Failed", f"Could not load project file:\n{str(e)}")

    def _import_dxf(self):
        """Import DXF wireframe entities into the active view canvas, handling LWPOLYLINE bulges and scaling"""
        active_canvas = self.tab_widget.currentWidget()
        if not active_canvas:
            return
            
        filename, _ = QFileDialog.getOpenFileName(self, "Import 2D DXF", "", "DXF Files (*.dxf)")
        if filename:
            try:
                import ezdxf
                doc = ezdxf.readfile(filename)
                msp = doc.modelspace()
                
                # Retrieve units header
                insunits = doc.header.get('$INSUNITS', 4)
                scale = 1.0
                if insunits == 1:    # Inches -> mm
                    scale = 25.4
                elif insunits == 2:  # Feet -> mm
                    scale = 304.8
                elif insunits == 5:  # cm -> mm
                    scale = 10.0
                elif insunits == 6:  # m -> mm
                    scale = 1000.0
                    
                view_name = active_canvas.view_name
                layer = self.cad_engine.active_layer
                added_count = 0
                
                for entity in msp:
                    dxftype = entity.dxftype()
                    if dxftype == 'LINE':
                        start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
                        end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
                        self.cad_engine.add_shape(Line(start, end, layer), view_name)
                        added_count += 1
                    elif dxftype == 'CIRCLE':
                        center = (entity.dxf.center.x * scale, entity.dxf.center.y * scale)
                        radius = entity.dxf.radius * scale
                        self.cad_engine.add_shape(Circle(center, radius, layer), view_name)
                        added_count += 1
                    elif dxftype == 'ARC':
                        center = (entity.dxf.center.x * scale, entity.dxf.center.y * scale)
                        radius = entity.dxf.radius * scale
                        start_ang = entity.dxf.start_angle
                        end_ang = entity.dxf.end_angle
                        self.cad_engine.add_shape(Arc(center, radius, start_ang, end_ang, layer), view_name)
                        added_count += 1
                    elif dxftype == 'LWPOLYLINE':
                        points = entity.get_points()
                        for i in range(len(points) - (0 if entity.closed else 1)):
                            pt1 = points[i]
                            pt2 = points[(i + 1) % len(points)]
                            
                            bulge = pt1[4]
                            p1 = (pt1[0] * scale, pt1[1] * scale)
                            p2 = (pt2[0] * scale, pt2[1] * scale)
                            
                            if abs(bulge) < 1e-4:
                                self.cad_engine.add_shape(Line(p1, p2, layer), view_name)
                            else:
                                L = np.linalg.norm(np.array(p2) - np.array(p1))
                                if L > 0.01:
                                    s = bulge * L / 2.0
                                    R = abs(s / 2.0 + L * L / (8.0 * s))
                                    v_chord = np.array(p2) - np.array(p1)
                                    chord_mid = (np.array(p1) + np.array(p2)) / 2.0
                                    n = np.array([-v_chord[1], v_chord[0]]) / L
                                    C = chord_mid + n * (R - abs(s)) * (-1 if bulge < 0 else 1)
                                    w1 = np.array(p1) - C
                                    w2 = np.array(p2) - C
                                    start_ang = np.degrees(np.arctan2(w1[1], w1[0])) % 360
                                    end_ang = np.degrees(np.arctan2(w2[1], w2[0])) % 360
                                    if bulge < 0:
                                        start_ang, end_ang = end_ang, start_ang
                                    self.cad_engine.add_shape(Arc((C[0], C[1]), R, start_ang, end_ang, layer), view_name)
                            added_count += 1
                            
                self.cad_engine._save_state(f"Import DXF ({added_count} shapes)")
                self._sync_all_views()
                self._trigger_reconstruction()
                QMessageBox.information(self, "Import Success", f"Successfully imported {added_count} entities from DXF (scaled by {scale:.3f}).")
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", f"Could not read DXF drawing:\n{str(e)}")

    def _export_dxf(self):
        """Export current 2D vector shapes into a multi-layered DXF drawing file"""
        filename, _ = QFileDialog.getSaveFileName(self, "Export 2D DXF", "", "DXF Files (*.dxf)")
        if filename:
            try:
                import ezdxf
                doc = ezdxf.new('R2010')
                doc.header['$INSUNITS'] = 4  # Standard Millimeters
                msp = doc.modelspace()
                
                for view_name in ('top', 'front', 'side'):
                    shapes = self.cad_engine.get_shapes(view_name)
                    for s in shapes:
                        layer_name = f"{view_name.upper()}_{s.layer.upper()}"
                        if not doc.layers.has_entry(layer_name):
                            color = 4 if s.layer == 'Hidden' else (8 if s.layer == 'Construction' else 3)
                            doc.layers.new(name=layer_name, dxfattribs={'color': color})
                            
                        if s.type == 'line':
                            msp.add_line(s.start, s.end, dxfattribs={'layer': layer_name})
                        elif s.type == 'rectangle':
                            x, y, w, h = s.rect
                            msp.add_lwpolyline([(x, y), (x+w, y), (x+w, y+h), (x, y+h)], dxfattribs={'layer': layer_name, 'flags': 1})
                        elif s.type == 'circle':
                            msp.add_circle(s.center, s.radius, dxfattribs={'layer': layer_name})
                        elif s.type == 'arc':
                            msp.add_arc(s.center, s.radius, s.start_angle, s.end_angle, dxfattribs={'layer': layer_name})
                        elif s.type == 'polygon':
                            msp.add_lwpolyline(s.points, dxfattribs={'layer': layer_name, 'flags': 1})
                            
                doc.saveas(filename)
                QMessageBox.information(self, "Export Success", f"Successfully exported 2D layers to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not write DXF drawing:\n{str(e)}")

    def _open_layer_manager(self):
        """Show Layer Manager dialog displaying configurations forVisible, Hidden, and Construction layouts"""
        QMessageBox.information(
            self,
            "Layer Manager Settings",
            "<h3>Drafting Layers Configuration</h3>"
            "<p>Standard drafting properties applied in Python CAD Pro:</p>"
            "<hr/>"
            "<p>🔴 <b>Visible Layer:</b> Solid Cyan, width 2.0px. Defines primary solid structures.</p>"
            "<p>🟡 <b>Hidden Layer:</b> Dashed Cyan, width 2.0px. Defines subtractive interior features (holes/cuts).</p>"
            "<p>⚪ <b>Construction Layer:</b> Solid Grey, width 1.0px. Auxiliary guides (ignored in 3D).</p>"
        )

    def _run_alignment_diagnostics(self) -> Tuple[bool, List[str]]:
        """Perform X/Y/Z bounding overlap diagnostic checks across Top, Front, and Side projections"""
        if not self.cad_engine.get_shapes('top') or not self.cad_engine.get_shapes('front') or not self.cad_engine.get_shapes('side'):
            # Ignore diagnostics checks if any projection is empty
            return True, []
            
        top_limits = self.reconstructor._get_view_bounds_3d([s.to_dict() for s in self.cad_engine.get_shapes('top')], 'top')
        front_limits = self.reconstructor._get_view_bounds_3d([s.to_dict() for s in self.cad_engine.get_shapes('front')], 'front')
        side_limits = self.reconstructor._get_view_bounds_3d([s.to_dict() for s in self.cad_engine.get_shapes('side')], 'side')
        
        warnings = []
        # Horizontal X bounds check (Top vs Front)
        x_top_min, x_top_max = top_limits[0], top_limits[1]
        x_front_min, x_front_max = front_limits[0], front_limits[1]
        if abs(x_top_min - x_front_min) > 25.0 or abs(x_top_max - x_front_max) > 25.0:
            warnings.append("X horizontal coordinate mismatch between Top and Front views (sketches misaligned).")
            
        # Vertical Y bounds check (Front vs Side)
        y_front_min, y_front_max = front_limits[2], front_limits[3]
        y_side_min, y_side_max = side_limits[2], side_limits[3]
        if abs(y_front_min - y_side_min) > 25.0 or abs(y_front_max - y_side_max) > 25.0:
            warnings.append("Y vertical coordinate mismatch between Front and Side views (sketches misaligned).")
            
        # Depth Z bounds check (Top vs Side)
        z_top_min, z_top_max = top_limits[2], top_limits[3]
        z_side_min, z_side_max = side_limits[0], side_limits[1]
        if abs(z_top_min - z_side_min) > 25.0 or abs(z_top_max - z_side_max) > 25.0:
            warnings.append("Z depth coordinate mismatch between Top and Side views (sketches misaligned).")
            
        return len(warnings) == 0, warnings
