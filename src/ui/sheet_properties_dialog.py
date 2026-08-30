"""
Sheet Properties & ISO 7200 Title Block Configuration Dialog.
Allows customizing sheet size, drawing metadata, and projection symbology.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QPushButton, QGroupBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from ..engine.sheet_layout_engine import SheetFormat, TitleBlockData


class SheetPropertiesDialog(QDialog):
    """Modal dialog for setting drawing sheet template and ISO 7200 title block fields"""

    def __init__(self, current_format: SheetFormat = SheetFormat.ISO_A3, current_tb: TitleBlockData = None, parent=None):
        super().__init__(parent)
        self.sheet_format = current_format
        self.title_block = current_tb or TitleBlockData()

        self.setWindowTitle("ISO 5457 / ISO 7200 Sheet & Title Block Setup")
        self.setMinimumWidth(460)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Sheet Size Setup
        sheet_group = QGroupBox("Drawing Sheet Format (ISO 5457)")
        form1 = QFormLayout(sheet_group)

        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "ISO A3 (420 x 297 mm) — Standard",
            "ISO A4 (297 x 210 mm)",
            "ISO A2 (594 x 420 mm)",
            "ANSI B (11 x 17 in)",
            "ANSI C (17 x 22 in)"
        ])
        # Set current selection
        idx_map = {
            SheetFormat.ISO_A3: 0,
            SheetFormat.ISO_A4: 1,
            SheetFormat.ISO_A2: 2,
            SheetFormat.ANSI_B: 3,
            SheetFormat.ANSI_C: 4,
        }
        self.format_combo.setCurrentIndex(idx_map.get(self.sheet_format, 0))
        form1.addRow("Sheet Size:", self.format_combo)

        layout.addWidget(sheet_group)

        # 2. ISO 7200 Title Block Metadata
        tb_group = QGroupBox("Title Block Information (ISO 7200)")
        form2 = QFormLayout(tb_group)

        self.title_edit = QLineEdit(self.title_block.title)
        form2.addRow("Drawing Title:", self.title_edit)

        self.dwg_no_edit = QLineEdit(self.title_block.dwg_no)
        form2.addRow("Drawing Number:", self.dwg_no_edit)

        self.rev_edit = QLineEdit(self.title_block.rev)
        self.rev_edit.setMaxLength(4)
        form2.addRow("Revision:", self.rev_edit)

        self.material_edit = QLineEdit(self.title_block.material)
        form2.addRow("Material:", self.material_edit)

        self.drafter_edit = QLineEdit(self.title_block.drafter)
        form2.addRow("Drawn By:", self.drafter_edit)

        self.scale_edit = QLineEdit(self.title_block.scale)
        form2.addRow("Scale:", self.scale_edit)

        self.proj_combo = QComboBox()
        self.proj_combo.addItems(["Third-Angle Projection (USA / ASME)", "First-Angle Projection (ISO / European)"])
        self.proj_combo.setCurrentIndex(0 if self.title_block.projection == "3rd_angle" else 1)
        form2.addRow("Projection Symbol:", self.proj_combo)

        layout.addWidget(tb_group)

        # 3. Action Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        # Update sheet format
        idx = self.format_combo.currentIndex()
        fmt_map = [SheetFormat.ISO_A3, SheetFormat.ISO_A4, SheetFormat.ISO_A2, SheetFormat.ANSI_B, SheetFormat.ANSI_C]
        self.sheet_format = fmt_map[idx]

        # Update TitleBlockData
        self.title_block.title = self.title_edit.text().strip() or "PART DRAWING"
        self.title_block.dwg_no = self.dwg_no_edit.text().strip() or "PCAD-3501"
        self.title_block.rev = self.rev_edit.text().strip() or "A"
        self.title_block.material = self.material_edit.text().strip() or "EN-GJL-250"
        self.title_block.drafter = self.drafter_edit.text().strip() or "Sahil Rane"
        self.title_block.scale = self.scale_edit.text().strip() or "1:1"
        self.title_block.projection = "3rd_angle" if self.proj_combo.currentIndex() == 0 else "1st_angle"

        self.accept()
