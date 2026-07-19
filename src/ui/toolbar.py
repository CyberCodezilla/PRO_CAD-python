"""
Drawing Toolbar - Tool and Layer selection panel
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup, QLabel, QComboBox
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon

class DrawingToolbar(QWidget):
    """Vertical toolbar for selecting active drawing tool and CAD layer"""
    
    tool_selected = pyqtSignal(str)
    layer_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(100)
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
                background-color: #252526;
                border-right: 1px solid #3c3c3c;
            }
            QLabel {
                color: #D4D4D4;
                font-weight: bold;
                font-size: 11px;
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
            ('Select', 'select', '🖱️'),
            ('Line', 'line', '📏'),
            ('Rectangle', 'rectangle', '▭'),
            ('Circle', 'circle', '⭕'),
            ('Polygon', 'polygon', '🔷'),
        ]
        
        for label, tool_id, icon in tools:
            btn = QPushButton(f"{icon}\n{label}")
            btn.setCheckable(True)
            btn.setFixedHeight(50)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2D2D2D;
                    color: #CCCCCC;
                    border: 1px solid #3C3C3C;
                    border-radius: 4px;
                    font-size: 10px;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #3C3C3C;
                    color: white;
                }
                QPushButton:checked {
                    background-color: #007ACC;
                    color: white;
                    border-color: #007ACC;
                }
            """)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
            self.button_group.addButton(btn)
            self.tool_buttons[tool_id] = btn
            layout.addWidget(btn)
            
        # Select first button ('Select') by default
        self.tool_buttons['select'].setChecked(True)
        
        # Separator Line
        layout.addSpacing(15)
        
        # Layer Selection Title
        layer_title = QLabel("ACTIVE LAYER")
        layer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(layer_title)
        
        # Layer Dropdown ComboBox
        self.layer_combo = QComboBox()
        self.layer_combo.addItems(["Visible", "Hidden", "Construction"])
        self.layer_combo.setStyleSheet("""
            QComboBox {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
            QComboBox:hover {
                background-color: #3C3C3C;
            }
            QComboBox QAbstractItemView {
                background-color: #2D2D2D;
                color: #CCCCCC;
                selection-background-color: #007ACC;
            }
        """)
        self.layer_combo.currentTextChanged.connect(self.layer_changed.emit)
        layout.addWidget(self.layer_combo)
        
        layout.addStretch()
        
    def _on_tool_clicked(self, tool_id: str):
        """Emit signal on tool selection"""
        self.tool_selected.emit(tool_id)
        
    def set_layer(self, layer_name: str):
        """Programmatically select active layer"""
        self.layer_combo.setCurrentText(layer_name)

    def set_active_tool(self, tool_id: str):
        """Programmatically select active tool button on the toolbar"""
        if tool_id in self.tool_buttons:
            self.tool_buttons[tool_id].setChecked(True)
