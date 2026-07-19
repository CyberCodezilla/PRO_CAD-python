"""
View Selector - Orthographic view selection panel
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

class ViewSelector(QWidget):
    """View selection widget for orthographic views"""
    
    view_changed = pyqtSignal(str)
    save_requested = pyqtSignal()
    generate_3d_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_view = 'top'
        self.saved_views_status = {'top': False, 'front': False, 'side': False}
        self._init_ui()
        
    def _init_ui(self):
        """Initialize UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Framed background
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border-bottom: 2px solid #333;
            }
        """)
        
        # Title
        title = QLabel("📐 Orthographic Views")
        title.setStyleSheet("font-weight: bold; font-size: 16px; color: white; padding: 5px;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # View buttons
        views = [
            ('Top View', 'top'),
            ('Front View', 'front'),
            ('Side View', 'side')
        ]
        
        self.view_buttons = {}
        for label, view_id in views:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedSize(120, 40)
            btn.clicked.connect(lambda checked, v=view_id: self._on_view_clicked(v))
            self.view_buttons[view_id] = btn
            layout.addWidget(btn)
            
        # Set top view as default
        self.view_buttons['top'].setChecked(True)
        
        layout.addStretch()
        
        # Save view button
        self.save_btn = QPushButton("💾 Save View")
        self.save_btn.setFixedSize(120, 40)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.save_btn.clicked.connect(self.save_requested.emit)
        layout.addWidget(self.save_btn)
        
        # Generate 3D button
        self.generate_btn = QPushButton("🎯 Generate 3D Model")
        self.generate_btn.setFixedSize(160, 40)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.generate_btn.clicked.connect(self.generate_3d_requested.emit)
        layout.addWidget(self.generate_btn)
        
        self._update_button_styles()
        
    def _on_view_clicked(self, view_id):
        """Handle view button click"""
        self.current_view = view_id
        
        # Update button states
        for vid, btn in self.view_buttons.items():
            btn.setChecked(vid == view_id)
            
        self._update_button_styles()
        self.view_changed.emit(view_id)
        
    def _update_button_styles(self):
        """Update button styles based on state"""
        for view_id, btn in self.view_buttons.items():
            is_active = view_id == self.current_view
            is_saved = self.saved_views_status[view_id]
            
            if is_active:
                if is_saved:
                    style = """
                        QPushButton {
                            background-color: #27ae60;
                            color: white;
                            border: 2px solid #229954;
                            border-radius: 5px;
                            font-weight: bold;
                        }
                    """
                else:
                    style = """
                        QPushButton {
                            background-color: #0078d4;
                            color: white;
                            border: 2px solid #005a9e;
                            border-radius: 5px;
                            font-weight: bold;
                        }
                    """
            else:
                if is_saved:
                    style = """
                        QPushButton {
                            background-color: #3a3a3a;
                            color: #27ae60;
                            border: 2px solid #27ae60;
                            border-radius: 5px;
                        }
                        QPushButton:hover {
                            background-color: #4a4a4a;
                        }
                    """
                else:
                    style = """
                        QPushButton {
                            background-color: #3a3a3a;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 5px;
                        }
                        QPushButton:hover {
                            background-color: #4a4a4a;
                        }
                    """
                    
            btn.setStyleSheet(style)
            
            # Update text with checkmark if saved
            view_name = view_id.capitalize()
            if is_saved:
                btn.setText(f"{view_name} View ✓")
            else:
                btn.setText(f"{view_name} View")
                
    def mark_view_saved(self, view_id):
        """Mark a view as saved"""
        self.saved_views_status[view_id] = True
        self._update_button_styles()
        
    def reset_views(self):
        """Reset all views to unsaved"""
        self.saved_views_status = {'top': False, 'front': False, 'side': False}
        self._update_button_styles()
        
    def set_view(self, view_id):
        """Programmatically set view"""
        self._on_view_clicked(view_id)
