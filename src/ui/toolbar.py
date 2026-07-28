"""
Drawing Toolbar - Tool and Layer selection panel
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup, QLabel, QComboBox
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon

class DrawingToolbar(QWidget):
    """Vertical toolbar for selecting active drawing tool, CAD layer, and active view mode"""
    
    tool_selected = pyqtSignal(str)
    layer_changed = pyqtSignal(str)
    view_mode_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(124)
        self._init_ui()
        
    def _init_ui(self):
        """Initialize UI layout"""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(8)
        
        # Stylesheet for toolbar container
        self.setStyleSheet("""
            DrawingToolbar {
                background-color: #20252b;
                border-right: 1px solid #3a4149;
            }
            QLabel {
                color: #D4D4D4;
                font-weight: bold;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        
        # Title Label
        title = QLabel("TOOLS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Tool Button Group
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.tool_buttons = {}
        
        tools = [
            ('Select', 'select'),
            ('Region', 'region'),
            ('Line', 'line'),
            ('Rectangle', 'rectangle'),
            ('Circle', 'circle'),
            ('Polygon', 'polygon'),
        ]
        
        for label, tool_id in tools:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(46)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #293038;
                    color: #CCCCCC;
                    border: 1px solid #3a4149;
                    border-radius: 3px;
                    font-size: 10px;
                font-weight: 600;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #3C3C3C;
                    color: white;
                }
                QPushButton:checked {
                    background-color: #1769aa;
                    color: white;
                    border-color: #2d8bd0;
                }
            """)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
            self.button_group.addButton(btn)
            self.tool_buttons[tool_id] = btn
            layout.addWidget(btn)
            
        # Select first button ('Select') by default
        self.tool_buttons['select'].setChecked(True)
        
        # Separator Line
        layout.addSpacing(10)
        
        # View Mode Selection Title
        view_title = QLabel("ACTIVE VIEW")
        view_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(view_title)
        
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Auto (Centroid)", "Front View", "Top View", "LHS View", "RHS View"])
        self.view_combo.setStyleSheet("""
            QComboBox {
                background-color: #293038;
                color: #00FFFF;
                border: 1px solid #3a4149;
                border-radius: 3px;
                padding: 4px;
                font-size: 10px;
                font-weight: 600;
                font-weight: bold;
            }
            QComboBox:hover {
                background-color: #3C3C3C;
            }
            QComboBox QAbstractItemView {
                background-color: #293038;
                color: #CCCCCC;
                selection-background-color: #1769aa;
            }
        """)
        self.view_combo.currentTextChanged.connect(self._on_view_mode_changed)
        layout.addWidget(self.view_combo)

        # Separator Line
        layout.addSpacing(10)

        # Layer Selection Title
        layer_title = QLabel("ACTIVE LAYER")
        layer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(layer_title)
        
        # Layer Dropdown ComboBox
        self.layer_combo = QComboBox()
        self.layer_combo.addItems(["Visible", "Hidden", "Centerline", "Construction"])
        self.layer_combo.setStyleSheet("""
            QComboBox {
                background-color: #293038;
                color: #CCCCCC;
                border: 1px solid #3a4149;
                border-radius: 3px;
                padding: 4px;
                font-size: 10px;
                font-weight: 600;
            }
            QComboBox:hover {
                background-color: #3C3C3C;
            }
            QComboBox QAbstractItemView {
                background-color: #293038;
                color: #CCCCCC;
                selection-background-color: #1769aa;
            }
        """)
        self.layer_combo.currentTextChanged.connect(self.layer_changed.emit)
        layout.addWidget(self.layer_combo)
        
        layout.addStretch()
        
    def _on_tool_clicked(self, tool_id: str):
        """Emit signal on tool selection"""
        self.tool_selected.emit(tool_id)

    def _on_view_mode_changed(self, text: str):
        """Emit view mode change"""
        self.view_mode_changed.emit(text)
        
    def set_layer(self, layer_name: str):
        """Programmatically select active layer"""
        self.layer_combo.setCurrentText(layer_name)

    def set_active_tool(self, tool_id: str):
        """Programmatically select active tool button on the toolbar"""
        if tool_id in self.tool_buttons:
            self.tool_buttons[tool_id].setChecked(True)
