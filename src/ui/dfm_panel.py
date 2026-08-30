"""
Design for Manufacturing (DFM) Advisory & Inspection Panel.
Provides live manufacturing feasibility score, process switching, and rule tolerances.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QGroupBox, QFormLayout, QDoubleSpinBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..engine.dfm_engine import ManufacturingProcess, DFMEngine


class DFMPanel(QWidget):
    """Interactive DFM manufacturing process selector and diagnostic control panel"""
    process_changed = pyqtSignal(str)
    run_analysis_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Process Selection
        proc_group = QGroupBox("Target Manufacturing Process")
        proc_layout = QVBoxLayout(proc_group)

        self.proc_combo = QComboBox()
        self.proc_combo.addItems([
            "CNC Milling (3-Axis)",
            "Injection Molding",
            "Die Casting",
            "Sheet Metal Forming"
        ])
        self.proc_combo.currentIndexChanged.connect(self._on_process_changed)
        proc_layout.addWidget(self.proc_combo)

        layout.addWidget(proc_group)

        # 2. Process Parameters
        self.param_group = QGroupBox("Process Parameters")
        self.form_layout = QFormLayout(self.param_group)

        self.tool_radius_spin = QDoubleSpinBox()
        self.tool_radius_spin.setRange(0.5, 20.0)
        self.tool_radius_spin.setValue(1.5)
        self.tool_radius_spin.setSuffix(" mm")
        self.form_layout.addRow("Min Tool Radius (R):", self.tool_radius_spin)

        self.sheet_thick_spin = QDoubleSpinBox()
        self.sheet_thick_spin.setRange(0.5, 10.0)
        self.sheet_thick_spin.setValue(2.0)
        self.sheet_thick_spin.setSuffix(" mm")
        self.form_layout.addRow("Sheet Thickness (t):", self.sheet_thick_spin)

        layout.addWidget(self.param_group)

        # 3. Action Controls
        self.analyze_btn = QPushButton("Run DFM Analysis")
        self.analyze_btn.setStyleSheet("background-color: #00ADB5; color: white; font-weight: bold; padding: 6px;")
        self.analyze_btn.clicked.connect(self.run_analysis_requested.emit)
        layout.addWidget(self.analyze_btn)

        layout.addStretch()

    def _on_process_changed(self, idx: int):
        proc_map = {
            0: "cnc_milling",
            1: "injection_molding",
            2: "die_casting",
            3: "sheet_metal"
        }
        self.process_changed.emit(proc_map.get(idx, "cnc_milling"))

    def get_selected_process(self) -> ManufacturingProcess:
        idx = self.proc_combo.currentIndex()
        if idx == 1:
            return ManufacturingProcess.INJECTION_MOLDING
        elif idx == 2:
            return ManufacturingProcess.DIE_CASTING
        elif idx == 3:
            return ManufacturingProcess.SHEET_METAL
        return ManufacturingProcess.CNC_MILLING
