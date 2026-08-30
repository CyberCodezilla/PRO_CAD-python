"""
ASME Y14.5-2018 GD&T Authoring Modal Dialog.
Provides Feature Control Frame (FCF) placement, Datum Feature tagging,
and 1D/2D Worst-Case & Root-Sum-Square (RSS) Tolerance Stack-Up calculation.
"""

import uuid
from typing import Optional, List, Dict
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, 
    QFormLayout, QLabel, QComboBox, QCheckBox, QDoubleSpinBox, 
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from ..engine.gdt_engine import (
    GDTSymbol, MaterialModifier, DatumFeature, FeatureControlFrame, 
    DimensionStackItem, GDTEngine, GDT_UNICODE_MAP, GDT_LABEL_MAP, MODIFIER_SYMBOL_MAP
)


class GDTDialog(QDialog):
    """Interactive GD&T Modal Dialog for drafting sheet annotations and metrology stack-up analysis"""

    def __init__(self, cad_engine, parent=None, active_view: str = "front"):
        super().__init__(parent)
        self.cad_engine = cad_engine
        self.active_view = active_view

        self.setWindowTitle("ASME Y14.5-2018 GD&T & Tolerance Analysis")
        self.resize(620, 520)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Tab widget
        self.tabs = QTabWidget(self)
        self.tab_fcf = QWidget()
        self.tab_datum = QWidget()
        self.tab_stack = QWidget()

        self._setup_fcf_tab()
        self._setup_datum_tab()
        self._setup_stack_tab()

        self.tabs.addTab(self.tab_fcf, "Feature Control Frame (FCF)")
        self.tabs.addTab(self.tab_datum, "Datum Identifier")
        self.tabs.addTab(self.tab_stack, "Tolerance Stack-Up Analyzer")

        main_layout.addWidget(self.tabs)

        # Apply dark theme styling
        self.setStyleSheet("""
            QDialog { background-color: #1a1f24; color: #d7dde3; }
            QTabWidget::pane { border: 1px solid #3a4149; background-color: #20262c; }
            QTabBar::tab { background-color: #15191d; color: #8995a0; padding: 8px 14px; border: 1px solid #303840; }
            QTabBar::tab:selected { background-color: #20262c; color: #00E5FF; border-bottom: 2px solid #00E5FF; font-weight: bold; }
            QLabel { color: #d7dde3; }
            QGroupBox { border: 1px solid #3a4149; border-radius: 4px; margin-top: 10px; padding-top: 10px; font-weight: bold; color: #00E5FF; }
            QComboBox, QLineEdit, QDoubleSpinBox { background-color: #171c21; color: #d7dde3; border: 1px solid #3a4149; border-radius: 3px; padding: 4px; }
            QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus { border-color: #00E5FF; }
            QPushButton { background-color: #263b4d; color: #ffffff; border: 1px solid #3c9bdd; border-radius: 3px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #2887c8; }
            QTableWidget { background-color: #171c21; color: #d7dde3; gridline-color: #303840; border: 1px solid #3a4149; }
            QHeaderView::section { background-color: #15191d; color: #8995a0; padding: 4px; border: 1px solid #303840; }
        """)

    # -------------------------------------------------------------------------
    # TAB 1: FEATURE CONTROL FRAME BUILDER
    # -------------------------------------------------------------------------
    def _setup_fcf_tab(self):
        layout = QVBoxLayout(self.tab_fcf)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # 1. View selector
        self.fcf_view_combo = QComboBox()
        self.fcf_view_combo.addItems(["front", "top", "side"])
        self.fcf_view_combo.setCurrentText(self.active_view if self.active_view in ["front", "top", "side"] else "front")
        form.addRow("Target View:", self.fcf_view_combo)

        # 2. Geometric Characteristic Symbol
        self.fcf_symbol_combo = QComboBox()
        for sym in GDTSymbol:
            glyph = GDT_UNICODE_MAP.get(sym, "")
            label = GDT_LABEL_MAP.get(sym, sym.value)
            self.fcf_symbol_combo.addItem(f"{glyph}  {label}", sym.value)
        self.fcf_symbol_combo.currentIndexChanged.connect(self._update_fcf_preview)
        form.addRow("Characteristic:", self.fcf_symbol_combo)

        # 3. Diameter zone checkbox
        self.fcf_dia_check = QCheckBox("Prepend Diameter (Ø) zone")
        self.fcf_dia_check.setChecked(True)
        self.fcf_dia_check.stateChanged.connect(self._update_fcf_preview)
        form.addRow("Zone Shape:", self.fcf_dia_check)

        # 4. Tolerance SpinBox
        self.fcf_tol_spin = QDoubleSpinBox()
        self.fcf_tol_spin.setRange(0.001, 100.0)
        self.fcf_tol_spin.setDecimals(3)
        self.fcf_tol_spin.setValue(0.100)
        self.fcf_tol_spin.setSingleStep(0.01)
        self.fcf_tol_spin.valueChanged.connect(self._update_fcf_preview)
        form.addRow("Tolerance (mm):", self.fcf_tol_spin)

        # 5. Material Modifier
        self.fcf_mod_combo = QComboBox()
        self.fcf_mod_combo.addItem("None (RFS - Regardless of Feature Size)", MaterialModifier.NONE.value)
        self.fcf_mod_combo.addItem("Ⓜ MMC (Maximum Material Condition)", MaterialModifier.MMC.value)
        self.fcf_mod_combo.addItem("Ⓛ LMC (Least Material Condition)", MaterialModifier.LMC.value)
        self.fcf_mod_combo.currentIndexChanged.connect(self._update_fcf_preview)
        form.addRow("Material Modifier:", self.fcf_mod_combo)

        # 6. Datum Selectors
        active_datum_labels = ["(None)"] + [d.label for d in self.cad_engine.get_datums()]
        
        self.fcf_prim_combo = QComboBox()
        self.fcf_prim_combo.addItems(active_datum_labels if len(active_datum_labels) > 1 else ["(None)", "A", "B", "C"])
        self.fcf_prim_combo.currentIndexChanged.connect(self._update_fcf_preview)
        form.addRow("Primary Datum [-A-]:", self.fcf_prim_combo)

        self.fcf_sec_combo = QComboBox()
        self.fcf_sec_combo.addItems(active_datum_labels if len(active_datum_labels) > 1 else ["(None)", "A", "B", "C"])
        self.fcf_sec_combo.currentIndexChanged.connect(self._update_fcf_preview)
        form.addRow("Secondary Datum [-B-]:", self.fcf_sec_combo)

        self.fcf_tert_combo = QComboBox()
        self.fcf_tert_combo.addItems(active_datum_labels if len(active_datum_labels) > 1 else ["(None)", "A", "B", "C"])
        self.fcf_tert_combo.currentIndexChanged.connect(self._update_fcf_preview)
        form.addRow("Tertiary Datum [-C-]:", self.fcf_tert_combo)

        layout.addLayout(form)

        # Live Preview Box
        preview_group = QGroupBox("ASME Y14.5 Feature Control Frame Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.fcf_preview_label = QLabel("[ ⌖ | Ø 0.100 | A | B ]")
        self.fcf_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fcf_preview_label.setStyleSheet("""
            background-color: #171D22;
            color: #00E5FF;
            border: 2px solid #00E5FF;
            border-radius: 4px;
            padding: 10px;
            font-family: 'Consolas', 'Segoe UI Symbol';
            font-size: 16px;
            font-weight: bold;
        """)
        preview_layout.addWidget(self.fcf_preview_label)
        layout.addWidget(preview_group)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        place_btn = QPushButton("Place Feature Control Frame")
        place_btn.clicked.connect(self._on_place_fcf)
        btn_layout.addWidget(place_btn)

        close_btn = QPushButton("Cancel")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self._update_fcf_preview()

    def _update_fcf_preview(self):
        sym_val = self.fcf_symbol_combo.currentData() or "position"
        try:
            sym = GDTSymbol(sym_val)
        except ValueError:
            sym = GDTSymbol.POSITION
        glyph = GDT_UNICODE_MAP.get(sym, sym.value[:3].upper())

        dia = "Ø " if self.fcf_dia_check.isChecked() else ""
        tol = f"{self.fcf_tol_spin.value():.3f}"
        
        mod_val = self.fcf_mod_combo.currentData() or "RFS"
        mod_sym = ""
        if mod_val == MaterialModifier.MMC.value:
            mod_sym = " Ⓜ"
        elif mod_val == MaterialModifier.LMC.value:
            mod_sym = " Ⓛ"

        prim = self.fcf_prim_combo.currentText()
        sec = self.fcf_sec_combo.currentText()
        tert = self.fcf_tert_combo.currentText()

        cells = [glyph, f"{dia}{tol}{mod_sym}"]
        if prim and prim != "(None)":
            cells.append(prim.strip("-"))
        if sec and sec != "(None)":
            cells.append(sec.strip("-"))
        if tert and tert != "(None)":
            cells.append(tert.strip("-"))

        preview_str = "[ " + " | ".join(cells) + " ]"
        self.fcf_preview_label.setText(preview_str)

    def _on_place_fcf(self):
        sym_val = self.fcf_symbol_combo.currentData() or "position"
        try:
            sym = GDTSymbol(sym_val)
        except ValueError:
            sym = GDTSymbol.POSITION

        mod_val = self.fcf_mod_combo.currentData() or "RFS"
        try:
            mod = MaterialModifier(mod_val)
        except ValueError:
            mod = MaterialModifier.NONE

        prim = self.fcf_prim_combo.currentText()
        sec = self.fcf_sec_combo.currentText()
        tert = self.fcf_tert_combo.currentText()

        view = self.fcf_view_combo.currentText()

        # Default placement offset in viewport
        fcf = FeatureControlFrame(
            id=str(uuid.uuid4()),
            view=view,
            symbol=sym,
            is_diameter=self.fcf_dia_check.isChecked(),
            tolerance=self.fcf_tol_spin.value(),
            modifier=mod,
            primary_datum=prim if prim != "(None)" else None,
            secondary_datum=sec if sec != "(None)" else None,
            tertiary_datum=tert if tert != "(None)" else None,
            leader_anchor=(-100.0, -100.0) if view == "front" else (100.0, -100.0),
            leader_target=(-50.0, -50.0)
        )

        self.cad_engine.add_feature_control_frame(fcf)
        self.accept()

    # -------------------------------------------------------------------------
    # TAB 2: DATUM IDENTIFIER TAGGER
    # -------------------------------------------------------------------------
    def _setup_datum_tab(self):
        layout = QVBoxLayout(self.tab_datum)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.datum_label_edit = QLineEdit("A")
        self.datum_label_edit.setMaxLength(3)
        form.addRow("Datum Label:", self.datum_label_edit)

        self.datum_view_combo = QComboBox()
        self.datum_view_combo.addItems(["front", "top", "side"])
        self.datum_view_combo.setCurrentText(self.active_view if self.active_view in ["front", "top", "side"] else "front")
        form.addRow("Target View:", self.datum_view_combo)

        self.datum_order_combo = QComboBox()
        self.datum_order_combo.addItem("Primary Datum (3 Contact Points)", 1)
        self.datum_order_combo.addItem("Secondary Datum (2 Contact Points)", 2)
        self.datum_order_combo.addItem("Tertiary Datum (1 Contact Point)", 3)
        form.addRow("Kinematic Order (3-2-1):", self.datum_order_combo)

        layout.addLayout(form)

        # Existing Datums list
        list_group = QGroupBox("Active Sheet Datums")
        list_layout = QVBoxLayout(list_group)
        self.datums_table = QTableWidget()
        self.datums_table.setColumnCount(3)
        self.datums_table.setHorizontalHeaderLabels(["Label", "View", "Kinematic Order"])
        self.datums_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._refresh_datums_table()
        list_layout.addWidget(self.datums_table)
        layout.addWidget(list_group)

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        add_datum_btn = QPushButton("Add Datum Identifier")
        add_datum_btn.clicked.connect(self._on_add_datum)
        btn_layout.addWidget(add_datum_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _refresh_datums_table(self):
        datums = self.cad_engine.get_datums()
        self.datums_table.setRowCount(len(datums))
        for r, d in enumerate(datums):
            self.datums_table.setItem(r, 0, QTableWidgetItem(f"[-{d.label}-]"))
            self.datums_table.setItem(r, 1, QTableWidgetItem(d.view.capitalize()))
            self.datums_table.setItem(r, 2, QTableWidgetItem(f"{d.order} ({d.contact_points} pts)"))

    def _on_add_datum(self):
        label = self.datum_label_edit.text().strip().upper().strip("-")
        if not label:
            QMessageBox.warning(self, "Invalid Label", "Please specify a datum label letter (e.g., A, B, C).")
            return

        view = self.datum_view_combo.currentText()
        order = self.datum_order_combo.currentData() or 1
        contact_pts = 4 - order  # 3 for 1, 2 for 2, 1 for 3

        datum = DatumFeature(
            id=str(uuid.uuid4()),
            label=label,
            view=view,
            origin=(0.0, 0.0),
            direction=(0.0, 1.0),
            order=order,
            contact_points=contact_pts
        )
        self.cad_engine.add_datum_feature(datum)
        self._refresh_datums_table()

        # Increment default label for next placement
        next_char = chr(ord(label[0]) + 1) if label and 'A' <= label[0] < 'Z' else "A"
        self.datum_label_edit.setText(next_char)

    # -------------------------------------------------------------------------
    # TAB 3: 1D/2D TOLERANCE STACK-UP ANALYZER
    # -------------------------------------------------------------------------
    def _setup_stack_tab(self):
        layout = QVBoxLayout(self.tab_stack)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel("Evaluate 1D/2D assembly clearance using Worst-Case & Root-Sum-Square (RSS 3-Sigma) methods:")
        info.setStyleSheet("color: #8995a0; font-size: 11px;")
        layout.addWidget(info)

        # Dimension stack table
        self.stack_table = QTableWidget()
        self.stack_table.setColumnCount(4)
        self.stack_table.setHorizontalHeaderLabels(["Feature Label", "Nominal (mm)", "Tolerance (±mm)", "Direction (+1 / -1)"])
        self.stack_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.stack_table)

        # Table buttons
        tbl_btn_layout = QHBoxLayout()
        add_row_btn = QPushButton("+ Add Dimension")
        add_row_btn.clicked.connect(self._add_stack_row)
        tbl_btn_layout.addWidget(add_row_btn)

        remove_row_btn = QPushButton("- Remove Selected")
        remove_row_btn.clicked.connect(self._remove_stack_row)
        tbl_btn_layout.addWidget(remove_row_btn)

        load_sample_btn = QPushButton("Load ASME Sample Stack")
        load_sample_btn.clicked.connect(self._load_sample_stack)
        tbl_btn_layout.addWidget(load_sample_btn)

        tbl_btn_layout.addStretch()
        layout.addLayout(tbl_btn_layout)

        # Results Group
        results_group = QGroupBox("Tolerance Stack-Up Analysis Report")
        results_layout = QVBoxLayout(results_group)

        self.stack_results_label = QLabel("Click 'Calculate Assembly Tolerance Stack' to analyze.")
        self.stack_results_label.setStyleSheet("""
            background-color: #171c21;
            color: #d7dde3;
            border: 1px solid #3a4149;
            border-radius: 4px;
            padding: 10px;
            font-family: 'Consolas';
            font-size: 11px;
        """)
        results_layout.addWidget(self.stack_results_label)
        layout.addWidget(results_group)

        # Calc button
        calc_btn = QPushButton("Calculate Assembly Tolerance Stack")
        calc_btn.setStyleSheet("background-color: #1f75b5; color: #ffffff; padding: 8px; font-weight: bold;")
        calc_btn.clicked.connect(self._calculate_stack)
        layout.addWidget(calc_btn)

        # Load default sample
        self._load_sample_stack()

    def _add_stack_row(self, label="Dim", nominal="10.00", tol="0.05", direction="+1.0"):
        r = self.stack_table.rowCount()
        self.stack_table.insertRow(r)
        self.stack_table.setItem(r, 0, QTableWidgetItem(label))
        self.stack_table.setItem(r, 1, QTableWidgetItem(str(nominal)))
        self.stack_table.setItem(r, 2, QTableWidgetItem(str(tol)))
        self.stack_table.setItem(r, 3, QTableWidgetItem(str(direction)))

    def _remove_stack_row(self):
        curr_row = self.stack_table.currentRow()
        if curr_row >= 0:
            self.stack_table.removeRow(curr_row)

    def _load_sample_stack(self):
        """Load standard 5-part bearing stack from PRD Section 7.3"""
        self.stack_table.setRowCount(0)
        self._add_stack_row("Bore Housing Depth", "52.40", "0.20", "+1.0")
        self._add_stack_row("Bearing 1 Width", "15.00", "0.05", "-1.0")
        self._add_stack_row("Spacer Bushing Length", "20.00", "0.10", "-1.0")
        self._add_stack_row("Bearing 2 Width", "15.00", "0.05", "-1.0")
        self._add_stack_row("Retaining Ring", "2.00", "0.05", "-1.0")
        self._calculate_stack()

    def _calculate_stack(self):
        items: List[DimensionStackItem] = []
        for r in range(self.stack_table.rowCount()):
            lbl_item = self.stack_table.item(r, 0)
            nom_item = self.stack_table.item(r, 1)
            tol_item = self.stack_table.item(r, 2)
            dir_item = self.stack_table.item(r, 3)

            if not nom_item or not tol_item or not dir_item:
                continue

            lbl = lbl_item.text() if lbl_item else f"D{r+1}"
            try:
                nom = float(nom_item.text())
                tol = float(tol_item.text())
                d_val = float(dir_item.text().replace("+", ""))
            except ValueError:
                continue

            items.append(DimensionStackItem(label=lbl, dimension=nom, tolerance=tol, direction=d_val))

        if not items:
            self.stack_results_label.setText("No valid dimensions in stack.")
            return

        res = GDTEngine.evaluate_tolerance_stack(items)

        wc_status = "<b style='color:#00E676;'>PASS</b>" if res.wc_pass else "<b style='color:#FF9100;'>WARNING (Interference Possible)</b>"
        rss_status = "<b style='color:#00E676;'>PASS (99.73% 3-Sigma Yield)</b>" if res.rss_pass else "<b style='color:#FF1744;'>FAIL (Statistical Interference)</b>"

        html = f"""
        <b>Nominal Assembly Gap:</b> <span style='color:#00E5FF;'>{res.nominal_gap:.4f} mm</span><br/>
        <hr style='border: 0.5px solid #3a4149;'/>
        <b>Worst-Case (Deterministic) Analysis:</b><br/>
        &nbsp;&bull; Total Tolerance: ±{res.wc_tolerance:.4f} mm<br/>
        &nbsp;&bull; Clearance Range: [{res.wc_min:.4f} mm, {res.wc_max:.4f} mm]<br/>
        &nbsp;&bull; Status: {wc_status}<br/>
        <hr style='border: 0.5px solid #3a4149;'/>
        <b>Root-Sum-Square (RSS 3-Sigma Statistical) Analysis:</b><br/>
        &nbsp;&bull; Total Statistical Tolerance: ±{res.rss_tolerance:.4f} mm<br/>
        &nbsp;&bull; Clearance Range: [{res.rss_min:.4f} mm, {res.rss_max:.4f} mm]<br/>
        &nbsp;&bull; Status: {rss_status}
        """
        self.stack_results_label.setText(html)
