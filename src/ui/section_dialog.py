"""
Section Views & Cutting-Plane Authoring Modal Dialog.
Allows interactive creation and configuration of:
- Full Sections, Offset/Stepped Sections, and Half Sections
- Cutting Plane Labels and Viewing Sight Arrows
- Material-Specific Cross-Hatch Angle and Pitch
"""

import uuid
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QDoubleSpinBox, QPushButton, QLabel, QGroupBox,
    QDialogButtonBox
)
from PyQt6.QtCore import Qt
from ..engine.section_engine import CuttingPlane, SectionView, SectionType


class SectionDialog(QDialog):
    """Modal dialog for defining and editing ISO 128-40 cutting planes and section views"""

    def __init__(self, cad_engine, parent=None, active_view: str = "top"):
        super().__init__(parent)
        self.cad_engine = cad_engine
        self.active_view = active_view

        self.setWindowTitle("ISO 128-40 / ASME Y14.3 Section View & Cutting-Plane Builder")
        self.setMinimumWidth(480)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Section Header & Label
        header_group = QGroupBox("Cutting-Plane Identification (ISO 128-40)")
        form1 = QFormLayout(header_group)

        self.label_edit = QLineEdit("A")
        self.label_edit.setMaxLength(2)
        form1.addRow("Section Label:", self.label_edit)

        self.source_view_combo = QComboBox()
        self.source_view_combo.addItems(["top", "front", "side"])
        self.source_view_combo.setCurrentText(self.active_view)
        form1.addRow("Cutting Plane View:", self.source_view_combo)

        self.target_view_combo = QComboBox()
        self.target_view_combo.addItems(["front", "side", "top"])
        self.target_view_combo.setCurrentText("front" if self.active_view == "top" else "side")
        form1.addRow("Projected Section View:", self.target_view_combo)

        self.section_type_combo = QComboBox()
        self.section_type_combo.addItems(["Full Section", "Offset (Stepped) Section", "Half Section", "Revolved Section"])
        form1.addRow("Section Type:", self.section_type_combo)

        layout.addWidget(header_group)

        # 2. Cutting Path Coordinates
        coords_group = QGroupBox("Cutting Path Coordinates (mm)")
        form2 = QFormLayout(coords_group)

        coord_row1 = QHBoxLayout()
        self.start_x = QDoubleSpinBox()
        self.start_x.setRange(-5000, 5000)
        self.start_x.setValue(-100.0)
        self.start_y = QDoubleSpinBox()
        self.start_y.setRange(-5000, 5000)
        self.start_y.setValue(20.0)
        coord_row1.addWidget(QLabel("X:"))
        coord_row1.addWidget(self.start_x)
        coord_row1.addWidget(QLabel("Y:"))
        coord_row1.addWidget(self.start_y)
        form2.addRow("Start Point (P1):", coord_row1)

        coord_row2 = QHBoxLayout()
        self.end_x = QDoubleSpinBox()
        self.end_x.setRange(-5000, 5000)
        self.end_x.setValue(0.0)
        self.end_y = QDoubleSpinBox()
        self.end_y.setRange(-5000, 5000)
        self.end_y.setValue(20.0)
        coord_row2.addWidget(QLabel("X:"))
        coord_row2.addWidget(self.end_x)
        coord_row2.addWidget(QLabel("Y:"))
        coord_row2.addWidget(self.end_y)
        form2.addRow("End Point (P2):", coord_row2)

        self.arrow_dir_combo = QComboBox()
        self.arrow_dir_combo.addItems(["Downward / Front (-Y)", "Upward / Back (+Y)", "Rightward (+X)", "Leftward (-X)"])
        form2.addRow("Sight Arrow Direction:", self.arrow_dir_combo)

        layout.addWidget(coords_group)

        # 3. Cross-Hatch Settings (ISO 128-50)
        hatch_group = QGroupBox("Material Cross-Hatch Shading (ISO 128-50 / DIN 201)")
        form3 = QFormLayout(hatch_group)

        self.hatch_angle = QDoubleSpinBox()
        self.hatch_angle.setRange(0, 180)
        self.hatch_angle.setValue(45.0)
        self.hatch_angle.setSuffix(" °")
        form3.addRow("Hatch Angle:", self.hatch_angle)

        self.hatch_pitch = QDoubleSpinBox()
        self.hatch_pitch.setRange(1.0, 20.0)
        self.hatch_pitch.setValue(3.0)
        self.hatch_pitch.setSingleStep(0.5)
        self.hatch_pitch.setSuffix(" mm")
        form3.addRow("Hatch Pitch / Spacing:", self.hatch_pitch)

        layout.addWidget(hatch_group)

        # 4. Action Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        """Build and register CuttingPlane and SectionView into CADEngine"""
        label = self.label_edit.text().strip().upper() or "A"
        src_view = self.source_view_combo.currentText()
        tgt_view = self.target_view_combo.currentText()

        p1 = (self.start_x.value(), self.start_y.value())
        p2 = (self.end_x.value(), self.end_y.value())

        # Determine viewing normal
        dir_idx = self.arrow_dir_combo.currentIndex()
        if dir_idx == 0:
            normal = (0.0, -1.0)
        elif dir_idx == 1:
            normal = (0.0, 1.0)
        elif dir_idx == 2:
            normal = (1.0, 0.0)
        else:
            normal = (-1.0, 0.0)

        type_map = {
            "Full Section": SectionType.FULL,
            "Offset (Stepped) Section": SectionType.OFFSET,
            "Half Section": SectionType.HALF,
            "Revolved Section": SectionType.REVOLVED
        }
        stype = type_map.get(self.section_type_combo.currentText(), SectionType.FULL)

        cp_id = f"cp_{uuid.uuid4().hex[:6]}"
        cutting_plane = CuttingPlane(
            id=cp_id,
            label=label,
            view=src_view,
            points=[p1, p2],
            normal=normal,
            arrow_size=8.0
        )

        sv_id = f"sec_{label}_{uuid.uuid4().hex[:4]}"
        section_view = SectionView(
            id=sv_id,
            cutting_plane_id=cp_id,
            target_view=tgt_view,
            section_type=stype,
            hatch_angle=self.hatch_angle.value(),
            hatch_pitch=self.hatch_pitch.value()
        )

        self.cad_engine.add_cutting_plane(cutting_plane)
        self.cad_engine.add_section_view(section_view)
        self.accept()
