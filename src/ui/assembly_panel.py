"""
Multi-Part Assembly, ISO 286 Limits & Fits, and Bill of Materials (BOM) Panel.
Features:
- ISO 7200 Bill of Materials (BOM) Table with synchronized 3D selection
- Kinematic Mating Joint List & ISO 286 Fit Status
- Dynamic Exploded View Slider (0% to 100%)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QSlider, QLabel, QPushButton, QGroupBox, QHeaderView, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..engine.assembly_engine import Assembly, Part, AssemblyMate, AssemblyEngine, BOMEntry
from ..engine.fits_db import evaluate_iso_fit


class AssemblyPanel(QWidget):
    """Dock panel managing multi-body assembly BOM, kinematic mates, and exploded views"""
    explode_changed = pyqtSignal(float)      # Emits slider factor [0.0, 1.0]
    part_selected = pyqtSignal(str)          # Emits selected part_id for 3D highlight

    def __init__(self, cad_engine, parent=None):
        super().__init__(parent)
        self.cad_engine = cad_engine
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # 1. Exploded View Slider Control
        explode_group = QGroupBox("Exploded Assembly View")
        explode_layout = QVBoxLayout(explode_group)

        slider_row = QHBoxLayout()
        self.explode_label = QLabel("Separation: 0%")
        self.explode_slider = QSlider(Qt.Orientation.Horizontal)
        self.explode_slider.setRange(0, 100)
        self.explode_slider.setValue(0)
        self.explode_slider.valueChanged.connect(self._on_slider_changed)

        slider_row.addWidget(self.explode_slider)
        slider_row.addWidget(self.explode_label)
        explode_layout.addLayout(slider_row)

        layout.addWidget(explode_group)

        # 2. Splitter for BOM and Mates
        splitter = QSplitter(Qt.Orientation.Vertical)

        # BOM Table (ISO 7200)
        bom_group = QGroupBox("Bill of Materials (BOM — ISO 7200)")
        bom_layout = QVBoxLayout(bom_group)

        self.bom_table = QTableWidget()
        self.bom_table.setColumnCount(5)
        self.bom_table.setHorizontalHeaderLabels(["#", "Part Name", "Material", "Qty", "Dimensions"])
        self.bom_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.bom_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.bom_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bom_table.itemSelectionChanged.connect(self._on_bom_selection_changed)
        bom_layout.addWidget(self.bom_table)

        splitter.addWidget(bom_group)

        # Mates Table
        mates_group = QGroupBox("Kinematic Mates & ISO 286 Fits")
        mates_layout = QVBoxLayout(mates_group)

        self.mates_table = QTableWidget()
        self.mates_table.setColumnCount(5)
        self.mates_table.setHorizontalHeaderLabels(["Mate", "Type", "Part A", "Part B", "ISO Fit"])
        self.mates_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.mates_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        mates_layout.addWidget(self.mates_table)

        splitter.addWidget(mates_group)
        layout.addWidget(splitter)

        # 3. Actions
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Assembly / BOM")
        self.refresh_btn.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 5px;")
        self.refresh_btn.clicked.connect(self.refresh_ui)
        btn_row.addWidget(self.refresh_btn)

        layout.addLayout(btn_row)

    def _on_slider_changed(self, val: int):
        factor = val / 100.0
        self.explode_label.setText(f"Separation: {val}%")
        self.explode_changed.emit(factor)

    def _on_bom_selection_changed(self):
        """Synchronize BOM table selection with 3D viewport highlight (Guardrail #3)"""
        selected_rows = self.bom_table.selectedItems()
        if not selected_rows:
            self.part_selected.emit("")
            return
        row = selected_rows[0].row()
        pid_item = self.bom_table.item(row, 1)
        if pid_item:
            part_id = pid_item.data(Qt.ItemDataRole.UserRole)
            if part_id:
                self.part_selected.emit(part_id)

    def refresh_ui(self):
        """Re-populate BOM table and Mating joint definitions"""
        assy = self.cad_engine.get_assembly()
        bom_entries = AssemblyEngine.compile_bill_of_materials(assy, self.cad_engine.shapes)

        # Populate BOM
        self.bom_table.setRowCount(len(bom_entries))
        for r, entry in enumerate(bom_entries):
            item_no = QTableWidgetItem(str(entry.item_no))
            item_no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bom_table.setItem(r, 0, item_no)

            name_item = QTableWidgetItem(f"{entry.name} {'(Anchor)' if entry.is_anchor else ''}")
            name_item.setData(Qt.ItemDataRole.UserRole, entry.part_id)
            self.bom_table.setItem(r, 1, name_item)

            self.bom_table.setItem(r, 2, QTableWidgetItem(entry.material))

            qty_item = QTableWidgetItem(str(entry.qty))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bom_table.setItem(r, 3, qty_item)

            self.bom_table.setItem(r, 4, QTableWidgetItem(entry.dimensions))

        # Populate Mates
        self.mates_table.setRowCount(len(assy.mates))
        for r, m in enumerate(assy.mates):
            p_a = assy.parts.get(m.part_a_id)
            p_b = assy.parts.get(m.part_b_id)
            name_a = p_a.name if p_a else m.part_a_id
            name_b = p_b.name if p_b else m.part_b_id

            self.mates_table.setItem(r, 0, QTableWidgetItem(m.mate_id))
            self.mates_table.setItem(r, 1, QTableWidgetItem(m.type))
            self.mates_table.setItem(r, 2, QTableWidgetItem(name_a))
            self.mates_table.setItem(r, 3, QTableWidgetItem(name_b))

            fit_text = m.fit_code or "None"
            if m.fit_code:
                try:
                    res = evaluate_iso_fit(m.nominal_d, m.fit_code)
                    fit_text = f"{m.fit_code} ({res.category})"
                except Exception:
                    pass
            self.mates_table.setItem(r, 4, QTableWidgetItem(fit_text))
