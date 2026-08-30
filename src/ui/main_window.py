"""
Main Window - Primary PyQt6 layout and controller coordinating MVC data flow.
Integrates 2D vector graphic scenes, 3D OpenGL viewport, bottom command console, and reconstruction threads.
"""
import json
import urllib.request
import urllib.error
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QTabWidget, QLineEdit, QLabel, QStatusBar,
    QMessageBox, QFileDialog, QDockWidget, QTreeWidget, 
    QTreeWidgetItem, QPushButton, QCheckBox, QComboBox, 
    QSlider, QDoubleSpinBox, QFormLayout, QDialog, QDialogButtonBox, QFrame
)
from PyQt6.QtCore import Qt, QPointF, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QAction, QKeySequence, QCursor, QColor, QBrush, QDesktopServices

from .canvas import DrawingCanvas
from .toolbar import DrawingToolbar
from .viewport_3d import OpenGLViewport
from .gdt_dialog import GDTDialog
from .section_dialog import SectionDialog
from ..engine.cad_engine import CADEngine, Shape, Line, Rectangle, Circle, Polygon, Arc, Dimension
from ..engine.rules_engine import RulesEngine, Diagnostic, DiagnosticSeverity
from ..reconstruction.reconstructor import Reconstructor3D
from ..reconstruction.brep_reconstructor import BRepReconstructionWorker, HAS_BUILD123D
from ..utils.step_exporter import StepExporter
from ..cv.ai_vectorizer import RasterCADVectorizer, GNNInferenceBridge

APP_VERSION = "v2.1.0"
GITHUB_REPO = "CyberCodezilla/PRO_CAD-python"


class UpdateCheckWorker(QThread):
    """Background worker querying GitHub Releases API for new updates"""
    update_available = pyqtSignal(str, str, str)  # latest_tag, html_url, release_body
    up_to_date = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, current_version: str = APP_VERSION, repo: str = GITHUB_REPO, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.repo = repo

    def run(self):
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(url, headers={
            "User-Agent": "PythonCADPro-App",
            "Accept": "application/vnd.github.v3+json"
        })
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    tag_name = data.get("tag_name", "").strip()
                    html_url = data.get("html_url", f"https://github.com/{self.repo}/releases")
                    body = data.get("body", "")
                    
                    if tag_name and self._is_newer_version(tag_name, self.current_version):
                        self.update_available.emit(tag_name, html_url, body)
                    else:
                        self.up_to_date.emit()
                else:
                    self.up_to_date.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

    @staticmethod
    def _is_newer_version(latest_tag: str, current_tag: str) -> bool:
        """Compare semver strings e.g. v2.1.1 vs v2.1.0"""
        def parse_version(tag: str):
            clean = tag.lstrip("vV").split("-")[0]
            parts = []
            for p in clean.split("."):
                try:
                    parts.append(int(p))
                except ValueError:
                    parts.append(0)
            return tuple(parts)
        return parse_version(latest_tag) > parse_version(current_tag)

class MainWindow(QMainWindow):
    """Main application window container"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python CAD Pro - Precision 2D to 3D CAD")
        self.setGeometry(100, 100, 1400, 900)
        
        # Core Models & Engines
        self.cad_engine = CADEngine()
        self.rules_engine = RulesEngine()
        self.reconstructor = Reconstructor3D()
        self.current_diagnostics: List[Diagnostic] = []
        self.cached_brep_solid = None
        self.cached_step_bytes: bytes = b""
        self.cached_iges_bytes: bytes = b""
        self.brep_worker: Optional[BRepReconstructionWorker] = None
        self.update_worker: Optional[UpdateCheckWorker] = None
        
        self._init_ui()
        self._create_menus()
        self._apply_theme()
        
        # Initial status message
        self.statusBar().showMessage("Ready - Select a drawing tool and start drafting")

        # Asynchronously check for GitHub releases in the background after UI renders
        QTimer.singleShot(2500, lambda: self.check_for_updates(silent=True))
        
    def _init_ui(self):
        """Build layout panels"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Professional document header. This is presentation-only; all existing controls
        # and signals remain unchanged below it.
        header = QFrame()
        header.setObjectName("DocumentHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 10, 18, 10)
        header_layout.setSpacing(14)

        brand = QLabel("PYTHON CAD PRO")
        brand.setObjectName("BrandLabel")
        header_layout.addWidget(brand)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setObjectName("HeaderSeparator")
        header_layout.addWidget(separator)

        document_label = QLabel("UNTITLED PROJECT")
        document_label.setObjectName("DocumentLabel")
        header_layout.addWidget(document_label)
        header_layout.addStretch()

        mode_label = QLabel("2D DRAFT  /  3D PREVIEW")
        mode_label.setObjectName("ModeLabel")
        header_layout.addWidget(mode_label)
        self.rebuild_button = QPushButton("Generate 3D Model")
        self.rebuild_button.setObjectName("PrimaryAction")
        self.rebuild_button.setToolTip("Rebuild the 3D preview from the current drawing")
        self.rebuild_button.clicked.connect(self._trigger_reconstruction)
        header_layout.addWidget(self.rebuild_button)
        main_layout.addWidget(header)

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
        self.viewport_3d.candidate_switched.connect(self._on_candidate_switched)
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
        
        console_label = QLabel("COMMAND")
        console_label.setStyleSheet("color: #75b9e6; font-weight: 600; font-family: Consolas;")
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

        export_step_action = QAction("Export STEP (AP214 / ISO 10303)...", self)
        export_step_action.triggered.connect(self._export_step)
        file_menu.addAction(export_step_action)

        export_iges_action = QAction("Export IGES...", self)
        export_iges_action.triggered.connect(self._export_iges)
        file_menu.addAction(export_iges_action)
        
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

        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")
        
        vectorize_action = QAction("Vectorize Scanned Drawing...", self)
        vectorize_action.triggered.connect(self._vectorize_scanned_drawing)
        tools_menu.addAction(vectorize_action)

        solve_constraints_action = QAction("Solve Parametric Constraints", self)
        solve_constraints_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        solve_constraints_action.triggered.connect(self._solve_all_constraints)
        tools_menu.addAction(solve_constraints_action)

        ai_autocomplete_action = QAction("AI Sketch Autocomplete (GNN)...", self)
        ai_autocomplete_action.triggered.connect(self._run_ai_autocomplete)
        tools_menu.addAction(ai_autocomplete_action)
        
        # Annotations / GD&T Menu (ASME Y14.5-2018)
        gdt_menu = menubar.addMenu("&Annotations")

        fcf_action = QAction("Add &Feature Control Frame (FCF)...", self)
        fcf_action.setShortcut(QKeySequence("Shift+G"))
        fcf_action.triggered.connect(lambda: self._open_gdt_dialog(tab_index=0))
        gdt_menu.addAction(fcf_action)

        datum_action = QAction("Add &Datum Identifier...", self)
        datum_action.setShortcut(QKeySequence("Shift+D"))
        datum_action.triggered.connect(lambda: self._open_gdt_dialog(tab_index=1))
        gdt_menu.addAction(datum_action)

        gdt_menu.addSeparator()

        stack_action = QAction("&Tolerance Stack-Up Analyzer...", self)
        stack_action.setShortcut(QKeySequence("Shift+T"))
        stack_action.triggered.connect(lambda: self._open_gdt_dialog(tab_index=2))
        gdt_menu.addAction(stack_action)

        gdt_menu.addSeparator()

        section_action = QAction("Add &Cutting Plane (Section A—A)...", self)
        section_action.setShortcut(QKeySequence("Shift+S"))
        section_action.triggered.connect(self._open_section_dialog)
        gdt_menu.addAction(section_action)

        # Help Menu
        help_menu = menubar.addMenu("&Help")
        
        guide_action = QAction("&User Guide", self)
        guide_action.setShortcut(QKeySequence("F1"))
        guide_action.triggered.connect(self._show_help_dialog)
        help_menu.addAction(guide_action)

        help_menu.addSeparator()

        check_update_action = QAction("Check for &Updates...", self)
        check_update_action.triggered.connect(lambda: self.check_for_updates(silent=False))
        help_menu.addAction(check_update_action)

        help_menu.addSeparator()

        about_action = QAction(f"&About Python CAD Pro ({APP_VERSION})", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
        
    def _apply_theme(self):
        """Apply the neutral, high-contrast visual system used by the workspace."""
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1a1f24; color: #d7dde3; font-family: "Segoe UI"; font-size: 11px; }
            QMenuBar { background-color: #15191d; color: #b8c0c8; border-bottom: 1px solid #303840; padding: 2px 8px; }
            QMenuBar::item { padding: 6px 10px; }
            QMenuBar::item:selected, QMenu::item:selected { background-color: #263b4d; color: #ffffff; }
            QMenu { background-color: #20262c; color: #d7dde3; border: 1px solid #3a4149; }
            QStatusBar { background-color: #12344a; color: #d9eefb; border-top: 1px solid #245a7a; font-family: "Consolas"; font-size: 10px; padding-left: 8px; }
            #DocumentHeader { background-color: #20262c; border-bottom: 1px solid #3a4149; }
            #BrandLabel { color: #f0f4f7; font-size: 13px; font-weight: 700; letter-spacing: 1px; }
            #DocumentLabel { color: #8995a0; font-size: 10px; font-weight: 600; letter-spacing: 0.8px; }
            #ModeLabel { color: #75b9e6; font-size: 10px; font-weight: 600; letter-spacing: 0.7px; }
            #HeaderSeparator { color: #46515b; }
            #PrimaryAction { background-color: #1f75b5; color: #ffffff; border: 1px solid #3c9bdd; border-radius: 3px; padding: 7px 14px; font-weight: 600; }
            #PrimaryAction:hover { background-color: #2887c8; }
            QDockWidget { color: #d7dde3; font-weight: 600; }
            QDockWidget::title { background-color: #20262c; padding: 8px 10px; border-bottom: 1px solid #3a4149; }
            QSplitter::handle { background-color: #39434c; width: 4px; }
            QLineEdit, QComboBox, QDoubleSpinBox, QTreeWidget { background-color: #171c21; color: #d7dde3; border: 1px solid #3a4149; border-radius: 3px; selection-background-color: #245a7a; }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: #3c9bdd; }
            QCheckBox { spacing: 7px; }
            QTabWidget::pane { border: 1px solid #303840; background-color: #1a1f24; }
            QTabBar::tab { background-color: #20262c; color: #8995a0; padding: 7px 14px; border: 1px solid #303840; }
            QTabBar::tab:selected { background-color: #1a1f24; color: #75b9e6; border-top: 2px solid #3c9bdd; }
            #ConsoleWidget { background-color: #15191d; border-top: 1px solid #3a4149; }
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
        # 1. Evaluate CAD Doctor RulesEngine
        is_valid, proj_type = self._run_diagnostics_and_update_doctor()
        if not is_valid:
            self.statusBar().showMessage("Reconstruction blocked: CAD Doctor identified geometry errors. See panel below.")
            return

        self.statusBar().showMessage(f"Generating watertight 3D model ({proj_type.upper()})...")
            
        # 2. Extract local shape profiles (Guardrails 1, 3, 4)
        tol = self.tolerance_spin.value() if hasattr(self, 'tolerance_spin') else 10.0
        top_shapes = self.cad_engine.get_local_shapes_for_view('top')
        front_shapes = self.cad_engine.get_local_shapes_for_view('front')
        side_shapes = self.cad_engine.get_local_shapes_for_view('side')

        # Interactive CSG mesh worker (Fast sub-50ms viewport response)
        self.reconstructor.run_reconstruction(
            top_shapes,
            front_shapes,
            side_shapes,
            callback_finished=self._on_reconstruction_finished,
            callback_error=self._on_reconstruction_error,
            angular_tolerance=tol,
            projection_type=proj_type
        )

        # Background Master Analytical B-Rep Worker (OpenCASCADE STEP / IGES pipeline)
        if HAS_BUILD123D:
            if self.brep_worker and self.brep_worker.isRunning():
                self.brep_worker.quit()
                self.brep_worker.wait(100)
            self.brep_worker = BRepReconstructionWorker(
                top_shapes, front_shapes, side_shapes,
                view_regions=self.cad_engine.view_regions,
                projection_type=proj_type
            )
            self.brep_worker.finished_brep.connect(self._on_brep_finished)
            self.brep_worker.start()

    def _on_reconstruction_finished(self, mesh):
        """Receive the reconstructed mesh safely on the GUI Thread and update OpenGLViewport"""
        if mesh is not None and len(mesh.vertices) > 0:
            self.viewport_3d.set_mesh(mesh)
            self.statusBar().showMessage("3D model updated successfully.")
        else:
            self.viewport_3d.set_mesh(None)
            self.statusBar().showMessage("Reconstruction returned an empty mesh. Draw profiles in views first.")
            
        # Update right-side properties panel tree view
        self._update_properties_panel()

    def _on_brep_finished(self, solid, step_bytes: bytes, iges_bytes: bytes, summary: str, candidates: list = None):
        """Handle background completion of OpenCASCADE B-Rep solid model"""
        self.cached_brep_solid = solid
        self.cached_step_bytes = step_bytes
        self.cached_iges_bytes = iges_bytes
        self.candidate_solids = candidates or ([solid] if solid else [])
        self.viewport_3d.set_candidates(len(self.candidate_solids), 0)
        print(f"[B-Rep Kernel] {summary}")

    def _on_candidate_switched(self, idx: int):
        """Switch active solid solution candidate for export and preview"""
        if hasattr(self, 'candidate_solids') and 0 <= idx < len(self.candidate_solids):
            selected_solid = self.candidate_solids[idx]
            self.cached_brep_solid = selected_solid
            self.statusBar().showMessage(f"Active 3D Solution: Candidate {idx + 1} of {len(self.candidate_solids)}")

    def _export_mesh(self, fmt: str):
        """Export current 3D solid mesh to STL, OBJ, or 3MF format"""
        mesh = getattr(self.viewport_3d, 'mesh', None)
        if mesh is None or len(mesh.vertices) == 0:
            QMessageBox.warning(self, "Export Warning", "No 3D solid model available to export. Reconstruct a 3D model first.")
            return

        filter_map = {
            'stl': "Stereolithography Files (*.stl)",
            'obj': "Wavefront OBJ Files (*.obj)",
            '3mf': "3D Manufacturing Format Files (*.3mf)"
        }
        filename, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", "", filter_map.get(fmt, "All Files (*)"))
        if filename:
            try:
                mesh.export(filename, file_type=fmt)
                QMessageBox.information(self, "Export Success", f"Successfully exported 3D model to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Failed to export {fmt.upper()} mesh:\n{str(e)}")

    def _export_step(self):
        """Export exact OpenCASCADE B-Rep solid as ISO-10303 STEP AP214 file with fallback"""
        filename, _ = QFileDialog.getSaveFileName(self, "Export STEP Solid", "", "STEP Files (*.step *.stp)")
        if not filename:
            return

        try:
            if self.cached_step_bytes and len(self.cached_step_bytes) > 0:
                with open(filename, 'wb') as f:
                    f.write(self.cached_step_bytes)
                QMessageBox.information(self, "Export Success", f"Successfully exported analytical B-Rep STEP to:\n{filename}")
                return

            # Faceted STEP Fallback
            mesh = getattr(self.viewport_3d, 'mesh', None)
            if mesh is not None and len(mesh.vertices) > 0:
                step_str = StepExporter.export_mesh_to_step(mesh.vertices, mesh.faces, part_name="CAD_PRO_SOLID")
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(step_str)
                QMessageBox.information(self, "Export Success", f"Successfully exported faceted STEP (ISO-10303 AP214) to:\n{filename}")
            else:
                QMessageBox.warning(self, "Export Warning", "No 3D model available to export.")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export STEP file:\n{str(e)}")

    def _export_iges(self):
        """Export OpenCASCADE B-Rep solid as IGES file"""
        filename, _ = QFileDialog.getSaveFileName(self, "Export IGES", "", "IGES Files (*.iges *.igs)")
        if not filename:
            return

        try:
            if self.cached_iges_bytes and len(self.cached_iges_bytes) > 0:
                with open(filename, 'wb') as f:
                    f.write(self.cached_iges_bytes)
                QMessageBox.information(self, "Export Success", f"Successfully exported IGES solid to:\n{filename}")
            else:
                QMessageBox.warning(self, "Export Warning", "No analytical IGES solid available. Ensure valid watertight 2D profiles are drawn.")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export IGES file:\n{str(e)}")

    def _vectorize_scanned_drawing(self):
        """Load and vectorize a scanned raster blueprint image into editable CAD entities"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Scanned Technical Drawing", "",
            "Drawing Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tif);;All Files (*)"
        )
        if not filename:
            return

        try:
            self.statusBar().showMessage(f"Vectorizing scanned technical drawing from {filename}...")
            vectorizer = RasterCADVectorizer(snap_tolerance=0.15, collinear_angle_deg=5.0)
            shapes_by_quadrant = vectorizer.vectorize_image(filename)

            total_added = 0
            for view_key, shape_list in shapes_by_quadrant.items():
                if view_key in self.cad_engine.shapes:
                    self.cad_engine.shapes[view_key].extend(shape_list)
                    total_added += len(shape_list)

            self.cad_engine._save_state("Vectorize Scanned Drawing")
            self._sync_all_views()
            self._trigger_reconstruction()
            QMessageBox.information(
                self, "Vectorization Complete",
                f"Successfully extracted and merged {total_added} vector CAD primitives from scanned blueprint into orthographic views."
            )
        except Exception as e:
            QMessageBox.critical(self, "Vectorization Failed", f"Could not vectorize drawing:\n{str(e)}")

    def _solve_all_constraints(self):
        """Execute mathematical constraint solver across all active parametric constraints"""
        success, msg = self.cad_engine.solve_constraints()
        self._sync_all_views()
        self._trigger_reconstruction()
        self.statusBar().showMessage(f"Constraint Solver: {msg}")
        QMessageBox.information(self, "Constraint Solver", msg)

    def _run_ai_autocomplete(self):
        """Analyze orthographic alignment rays and suggest missing projected features"""
        top_shapes = self.cad_engine.get_shapes('top')
        front_shapes = self.cad_engine.get_shapes('front')
        side_shapes = self.cad_engine.get_shapes('side')

        suggestions = GNNInferenceBridge.infer_missing_edges(top_shapes, front_shapes, side_shapes)
        if not suggestions:
            QMessageBox.information(self, "AI Autocomplete", "All primary orthographic projection feature rays are consistent and fully aligned.")
            return

        msg_lines = ["<b>AI Suggested Sketch Completions:</b><ul>"]
        for s in suggestions:
            msg_lines.append(f"<li><b>{s['target_view'].upper()} View:</b> {s['reason']}</li>")
        msg_lines.append("</ul>")

        reply = QMessageBox.question(
            self, "AI Sketch Completion",
            "".join(msg_lines) + "<br/>Apply inferred feature alignment lines to your sketch?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            for s in suggestions:
                view = s['target_view']
                x_pos = s['suggested_x']
                # Create construction alignment line
                line = Line((x_pos, -200.0), (x_pos, 200.0), layer='Construction')
                self.cad_engine.add_shape(line, view)
            self._sync_all_views()
            self.statusBar().showMessage("AI suggested alignment features added.")



    def _on_reconstruction_error(self, error_trace: str):
        """Handle error from background thread"""
        self.statusBar().showMessage("Reconstruction error. Click Help or check the console log.")
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

    def _open_gdt_dialog(self, tab_index: int = 0):
        """Open the ASME Y14.5 GD&T authoring modal dialog"""
        active_view = self.cad_engine.active_view_mode if self.cad_engine.active_view_mode != 'auto' else 'front'
        dlg = GDTDialog(self.cad_engine, self, active_view=active_view)
        dlg.tabs.setCurrentIndex(tab_index)
        if dlg.exec():
            self._sync_all_views()
            self._trigger_reconstruction()
            self._run_diagnostics_and_update_doctor()
            self.statusBar().showMessage("GD&T Annotations updated successfully.")

    def _open_section_dialog(self):
        """Open the ISO 128-40 Section Views and Cutting-Plane authoring modal dialog"""
        active_view = self.cad_engine.active_view_mode if self.cad_engine.active_view_mode != 'auto' else 'top'
        dlg = SectionDialog(self.cad_engine, self, active_view=active_view)
        if dlg.exec():
            self._sync_all_views()
            self._trigger_reconstruction()
            self._run_diagnostics_and_update_doctor()
            self.statusBar().showMessage("Section Plane and Cross-Hatching updated successfully.")
            
    def _show_help_dialog(self):
        """Display an interactive, beautifully formatted CAD User Guide"""
        help_text = (
            "<h3>Python CAD Pro - Engineering Graphics User Guide</h3>"
            "<p>Welcome to <b>Python CAD Pro</b>, a professional desktop CAD editor. "
            "Draft on the 2D orthographic canvases and reconstruct watertight 3D models instantly.</p>"
            
            "<h4>1. Line Types (Engineering Graphics Convention)</h4>"
            "<ul>"
            "<li><b>Visible Layer (Solid Cyan):</b> Used to draft the outer solid boundaries of your part.</li>"
            "<li><b>Hidden Layer (Dashed Cyan):</b> Used to draft internal holes, pockets, or cuts. Hidden profiles are subtracted from visible profiles during 3D CSG reconstruction.</li>"
            "<li><b>Construction Layer (Faint Grey):</b> Alignment/layout lines. Ignored in 3D reconstruction.</li>"
            "</ul>"
            
            "<h4>2. Drafting Tools & Snapping</h4>"
            "<ul>"
            "<li><b>Select Tool:</b> Select shapes on the active tab canvas. Press <b>Delete</b> key to remove selected shapes.</li>"
            "<li><b>Line, Rectangle, Circle, Polygon:</b> Select a shape drawing tool from the vertical toolbar. Click on the canvas to place points.</li>"
            "<li><b>Shift Key (Ortho Mode):</b> Hold the <b>Shift</b> key while drawing lines to snap/constrain segments to horizontal or vertical axes.</li>"
            "<li><b>OSNAP (Object Snapping):</b> Snaps to endpoints, midpoints, circle centers, and polygon vertices within 15px (indicated by yellow square).</li>"
            "<li><b>Grid Snapping:</b> Snaps coordinate placements to the nearest 10px grid intersection.</li>"
            "</ul>"
            
            "<h4>3. Command Console Instructions</h4>"
            "Type parametric commands in the bottom bar and press <b>Enter</b>:"
            "<ul>"
            "<li><b>Relative Offset:</b> Type <code>dx,dy</code> (e.g. <code>100,50</code>) to place the next point relative to the last point.</li>"
            "<li><b>Absolute Coordinate:</b> Type <code>#x,y</code> (e.g. <code>#0,-100</code>) to place a point at exact coordinates.</li>"
            "<li><b>Strict Length:</b> Type a number (e.g. <code>250</code>) during active drawing to lock the line segment to that length along the cursor direction.</li>"
            "<li><b>Command shortcuts:</b> Type <code>undo</code>, <code>redo</code>, <code>clear</code>, or <code>help</code> in the console.</li>"
            "</ul>"
            
            "<h4>4. 3D Viewport Navigation</h4>"
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

        # 3. CAD Doctor Diagnostic Dock (Bottom Dockable Widget)
        self.doctor_dock = QDockWidget("CAD DOCTOR  /  Diagnostics & Suggestions", self)
        self.doctor_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        
        doctor_container = QWidget()
        doctor_container.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        doctor_layout = QVBoxLayout(doctor_container)
        doctor_layout.setContentsMargins(6, 6, 6, 6)
        doctor_layout.setSpacing(6)
        
        self.doctor_tree = QTreeWidget()
        self.doctor_tree.setHeaderLabels(["Severity", "Rule Title", "Description", "Suggestion"])
        self.doctor_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #00FFFF;
                font-weight: bold;
                border: 1px solid #3C3C3C;
                padding: 4px;
            }
        """)
        self.doctor_tree.setColumnWidth(0, 95)
        self.doctor_tree.setColumnWidth(1, 200)
        self.doctor_tree.setColumnWidth(2, 380)
        self.doctor_tree.itemSelectionChanged.connect(self._on_doctor_item_selected)
        doctor_layout.addWidget(self.doctor_tree)
        
        btn_bar = QHBoxLayout()
        self.autofix_btn = QPushButton("Apply Auto-Fix")
        self.autofix_btn.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: #FFFFFF;
                border: 1px solid #0099FF;
                padding: 5px 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #0099FF;
            }
            QPushButton:disabled {
                background-color: #3A3A3A;
                color: #777777;
                border-color: #444444;
            }
        """)
        self.autofix_btn.setEnabled(False)
        self.autofix_btn.clicked.connect(self._on_apply_autofix)
        btn_bar.addWidget(self.autofix_btn)
        btn_bar.addStretch()
        
        doctor_layout.addLayout(btn_bar)
        self.doctor_dock.setWidget(doctor_container)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.doctor_dock)

    def _run_diagnostics_and_update_doctor(self) -> Tuple[bool, str]:
        """Run RulesEngine and populate CAD Doctor dock list"""
        self.doctor_tree.clear()
        self.current_diagnostics = self.rules_engine.evaluate_all(
            self.cad_engine.shapes,
            self.cad_engine.view_regions,
            self.cad_engine.get_datums(),
            self.cad_engine.get_feature_control_frames(),
            self.cad_engine.get_cutting_planes(),
            self.cad_engine.get_section_views()
        )
        
        has_error = False
        proj_type = '3rd_angle'

        for diag in self.current_diagnostics:
            if diag.rule_id == "RULE_PROJ_TYPE" and diag.fix_data:
                proj_type = diag.fix_data.get('projection_type', '3rd_angle')

            if diag.severity == DiagnosticSeverity.ERROR:
                sev_str = "ERROR"
                color = "#FF3333"
                has_error = True
            elif diag.severity == DiagnosticSeverity.WARNING:
                sev_str = "WARNING"
                color = "#FF8C00"
            else:
                sev_str = "INFO"
                color = "#00FFFF"

            item = QTreeWidgetItem([sev_str, diag.title, diag.description, diag.suggestion])
            item.setForeground(0, QBrush(QColor(color)))
            item.setData(0, Qt.ItemDataRole.UserRole, diag)
            self.doctor_tree.addTopLevelItem(item)

        self.autofix_btn.setEnabled(len(self.current_diagnostics) > 0)
        return (not has_error), proj_type

    def _on_doctor_item_selected(self):
        """Highlight shapes associated with selected diagnostic item"""
        selected = self.doctor_tree.selectedItems()
        if not selected:
            self.canvas.clear_highlights()
            return
        
        diag: Diagnostic = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if diag and diag.mismatched_shape_ids:
            self.canvas.highlight_shapes(diag.mismatched_shape_ids)
            self.statusBar().showMessage(f"Highlighted {len(diag.mismatched_shape_ids)} shape(s) for: {diag.title}")
        else:
            self.canvas.clear_highlights()

    def _on_apply_autofix(self):
        """Apply auto-fix for selected diagnostic item"""
        selected = self.doctor_tree.selectedItems()
        if not selected:
            self.statusBar().showMessage("Please select a diagnostic item to auto-fix.")
            return

        diag: Diagnostic = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if diag and diag.fix_action:
            success = self.cad_engine.apply_autofix(diag)
            if success:
                self.canvas.clear_highlights()
                self.canvas.rebuild_scene()
                self._run_diagnostics_and_update_doctor()
                self.statusBar().showMessage(f"Applied Auto-Fix: {diag.title}")
            else:
                self.statusBar().showMessage("Auto-Fix action not supported for this item.")
        else:
            self.statusBar().showMessage("No Auto-Fix available for selected item.")

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
                self.statusBar().showMessage(f"Project saved to {filename}")
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
                self.statusBar().showMessage(f"Project loaded successfully from {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Load Failed", f"Could not load project file:\n{str(e)}")

    def _import_dxf(self):
        """Import DXF wireframe entities into the active view canvas, handling LWPOLYLINE bulges and scaling"""
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
                    
                view_name = self.cad_engine.active_view_mode if self.cad_engine.active_view_mode != 'auto' else None
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
            "<p><b>Visible Layer:</b> Solid Cyan, width 2.0px. Defines primary solid structures.</p>"
            "<p><b>Hidden Layer:</b> Dashed Cyan, width 2.0px. Defines subtractive interior features (holes/cuts).</p>"
            "<p><b>Construction Layer:</b> Solid Grey, width 1.0px. Auxiliary guides (ignored in 3D).</p>"
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

    def check_for_updates(self, silent: bool = False):
        """Asynchronously query GitHub Releases API to detect newer version"""
        if self.update_worker and self.update_worker.isRunning():
            return
            
        self.update_worker = UpdateCheckWorker(APP_VERSION, GITHUB_REPO, self)
        
        def on_update(latest_version: str, html_url: str, release_notes: str):
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Update Available — Python CAD Pro")
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setText(
                f"<h3>A newer version of Python CAD Pro is available!</h3>"
                f"<p>Installed version: <b>{APP_VERSION}</b><br>"
                f"Latest release: <b style='color:#00E5FF;'>{latest_version}</b></p>"
            )
            
            if release_notes:
                preview = release_notes[:400] + ("..." if len(release_notes) > 400 else "")
                msg_box.setInformativeText(f"<b>Release Notes:</b><br><pre>{preview}</pre>")
                
            download_btn = msg_box.addButton("Download Release", QMessageBox.ButtonRole.AcceptRole)
            remind_btn = msg_box.addButton("Remind Me Later", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(download_btn)
            
            msg_box.exec()
            if msg_box.clickedButton() == download_btn:
                QDesktopServices.openUrl(QUrl(html_url))

        def on_up_to_date():
            if not silent:
                QMessageBox.information(
                    self, 
                    "No Updates Found", 
                    f"You are running the latest version of Python CAD Pro ({APP_VERSION})."
                )

        def on_error(err_msg: str):
            if not silent:
                QMessageBox.warning(
                    self,
                    "Update Check",
                    f"Unable to check for updates at this time.\n\nDetails: {err_msg}"
                )

        self.update_worker.update_available.connect(on_update)
        self.update_worker.up_to_date.connect(on_up_to_date)
        self.update_worker.error_occurred.connect(on_error)
        self.update_worker.start()

    def _show_about_dialog(self):
        """Show About application modal"""
        QMessageBox.about(
            self,
            "About Python CAD Pro",
            f"<h2>Python CAD Pro {APP_VERSION}</h2>"
            f"<p>Industrial-Grade 2D Drafting & Orthographic 3D CSG / B-Rep Reconstruction Engine.</p>"
            f"<p>Built with PyQt6, PyOpenGL, Manifold3D, and OpenCASCADE Technology.</p>"
            f"<hr/>"
            f"<p>Developed with ❤️ by <b>Sahil Rane (CyberCodezilla)</b>.</p>"
            f"<p><a href='https://github.com/{GITHUB_REPO}'>GitHub Repository</a></p>"
        )
