"""
Industrial Blueprint Benchmark & End-to-End Metrology Suite.
Executes complete industrial mechanisms through the full engineering stack:
- Benchmark 1: Split Plummer Block Pedestal Bearing Assembly (ISO fits, sectioning, BOM)
- Benchmark 2: Machine Vice Base & Lead-Screw (GD&T DRF, M16 tap drill, DFM, 1:1 PDF export)
"""

import os
import tempfile
import pytest
from src.engine.cad_engine import CADEngine, Rectangle, Circle, Line
from src.engine.sheet_layout_engine import (
    SheetFormat, TitleBlockData, SheetTemplate, get_sheet_template, SheetLayoutEngine
)
from src.engine.fits_db import evaluate_iso_fit
from src.engine.assembly_engine import Assembly, Part, AssemblyMate, AssemblyEngine
from src.engine.section_engine import CuttingPlane, SectionView, SectionEngine
from src.engine.standards_db import lookup_metric_thread
from src.engine.gdt_engine import DatumFeature, FeatureControlFrame, GDTSymbol, MaterialModifier, GDTEngine
from src.engine.dfm_engine import DFMEngine, ManufacturingProcess
from src.engine.rules_engine import RulesEngine
from src.export.drawing_exporter import DrawingExporter, POINTS_PER_MM
from PyQt6.QtWidgets import QApplication

_qapp = QApplication.instance()
if _qapp is None:
    _qapp = QApplication(["pytest-runner", "-platform", "offscreen"])


def test_sheet_layout_margins_and_zones_iso_a3():
    """
    Test Case 1 (PRD Section 6.1): Sheet Layout Margins & Zone Calculation (ISO A3).
    - SheetFormat.ISO_A3 (420.0 x 297.0 mm).
    - Working width = 420.0 - 30.0 = 390.0 mm.
    - Working height = 297.0 - 20.0 = 277.0 mm.
    - Title block origin at (230.0, 224.0) mm.
    """
    template = get_sheet_template(SheetFormat.ISO_A3)

    assert abs(template.width_mm - 420.0) < 1e-4
    assert abs(template.height_mm - 297.0) < 1e-4
    assert abs(template.working_width - 390.0) < 1e-4
    assert abs(template.working_height - 277.0) < 1e-4

    x_tb, y_tb = template.title_block_origin
    assert abs(x_tb - 230.0) < 1e-4
    assert abs(y_tb - 224.0) < 1e-4

    # Zone calculation
    assert template.zones_x >= 7
    assert template.zones_y >= 5


def test_pdf_exporter_1_to_1_metric_scaling():
    """
    Test Case 2 (PRD Section 6.2): PDF Exporter 1:1 Metric Coordinate Calibration.
    - 100.0 mm stroke maps to exactly 283.465 ± 0.01 pt (at 72 DPI PostScript scale).
    """
    length_mm = 100.0
    expected_pts = length_mm * (72.0 / 25.4)

    calculated_pts = length_mm * POINTS_PER_MM
    assert abs(calculated_pts - 283.464567) < 0.01
    assert abs(calculated_pts - expected_pts) < 1e-6


def test_benchmark_plummer_block_pedestal_assembly():
    """
    Test Case 3 (PRD Section 6.3): End-to-End Plummer Block Assembly Benchmark.
    - Base Housing (EN-GJL-250), Split Bronze Brasses (CuSn8), Journal Shaft (42CrMo4).
    - Longitudinal full section slicing along centerline.
    - Running clearance fit H7/g6 on Ø25.0 mm journal (C_min = +0.007 mm, C_max = +0.041 mm).
    - Exploded trajectory vertical disassembly along Z-axis.
    """
    cad_engine = CADEngine()

    # 1. Base Housing (Part 1)
    base_rect = Rectangle(rect=(-80.0, -22.5, 160.0, 45.0), layer="Visible", shape_id="p1_base")
    bolt1 = Circle(center=(-60.0, 0.0), radius=6.0, layer="Visible", shape_id="p1_bolt1")
    bolt2 = Circle(center=(60.0, 0.0), radius=6.0, layer="Visible", shape_id="p1_bolt2")
    seat = Circle(center=(0.0, 0.0), radius=19.0, layer="Visible", shape_id="p1_seat") # Ø38.0mm

    # 2. Split Bronze Brasses (Part 2)
    bushing_od = Circle(center=(0.0, 0.0), radius=19.0, layer="Visible", shape_id="p2_od")
    bushing_id = Circle(center=(0.0, 0.0), radius=12.5, layer="Visible", shape_id="p2_id") # Ø25.0mm

    # 3. Journal Shaft (Part 3)
    shaft = Circle(center=(0.0, 0.0), radius=12.5, layer="Visible", shape_id="p3_shaft") # Ø25.0mm

    cad_engine.shapes['top'] = [base_rect, bolt1, bolt2, seat, bushing_od, bushing_id, shaft]

    # Setup Assembly
    p1 = Part(part_id="p1", name="Plummer Block Housing", material="EN-GJL-250 CAST IRON", is_anchor=True, extent_3d=(160.0, 45.0, 75.0))
    p2 = Part(part_id="p2", name="Split Bronze Brasses", material="Bronze CuSn8", extent_3d=(38.0, 38.0, 40.0))
    p3 = Part(part_id="p3", name="Journal Shaft", material="Alloy Steel 42CrMo4", extent_3d=(25.0, 25.0, 100.0))

    assy = cad_engine.get_assembly()
    assy.parts["p1"] = p1
    assy.parts["p2"] = p2
    assy.parts["p3"] = p3

    m1 = AssemblyMate(mate_id="m1", type="COAXIAL", part_a_id="p1", part_b_id="p2", nominal_d=38.0, fit_code="H7/p6")
    m2 = AssemblyMate(mate_id="m2", type="COAXIAL", part_a_id="p2", part_b_id="p3", nominal_d=25.0, fit_code="H7/g6")
    assy.mates.extend([m1, m2])

    # Section Cut A—A
    cp = CuttingPlane(id="cp_aa", label="A", view="top", points=[(-90.0, 0.0), (90.0, 0.0)], normal=(0.0, -1.0))
    sv = SectionView(id="sec_aa", cutting_plane_id="cp_aa", target_view="front")
    cad_engine.add_cutting_plane(cp)
    cad_engine.add_section_view(sv)

    # 1. Verify ISO Fit calculation
    fit_res = evaluate_iso_fit(25.0, "H7/g6")
    assert fit_res.category == "CLEARANCE"
    assert abs(fit_res.min_clearance - 0.007) < 1e-4
    assert abs(fit_res.max_clearance - 0.041) < 1e-4

    # 2. Verify Hatch line generation for cut housing face
    outer_box = [(-80.0, -37.5), (80.0, -37.5), (80.0, 37.5), (-80.0, 37.5)]
    hatch_lines = SectionEngine.generate_hatch_lines(outer_box, pitch=5.0, angle_deg=45.0)
    assert len(hatch_lines) > 0

    # 3. Verify Exploded View separation
    offsets = AssemblyEngine.compute_exploded_trajectories(assy, t_factor=1.0)
    assert offsets["p1"] == (0.0, 0.0, 0.0)
    assert offsets["p2"][2] > 50.0
    assert offsets["p3"][2] > offsets["p2"][2]

    # 4. Verify BOM compilation
    bom = AssemblyEngine.compile_bill_of_materials(assy, cad_engine.shapes)
    assert len(bom) == 3
    assert bom[0].name == "Plummer Block Housing"


def test_benchmark_machine_vice_base_and_leadscrew():
    """
    Test Case 4 (PRD Section 6.4): End-to-End Machine Vice Base Benchmark.
    - Base Dimensions: 220 x 100 x 80 mm.
    - Guideway Slot: 50 x 15 mm.
    - Blind tapped lead-screw bore: M16 x 2.0.
    - GD&T callouts: Datum [-A-], Parallelism to [-A-], True Position Ø0.15 (M).
    - Full PDF export pipeline test.
    """
    cad_engine = CADEngine()

    base = Rectangle(rect=(-110.0, -50.0, 220.0, 100.0), layer="Visible", shape_id="vice_base")
    guideway = Rectangle(rect=(-25.0, -7.5, 50.0, 15.0), layer="Hidden", shape_id="guideway_slot")
    m16_tap = Circle(center=(0.0, 0.0), radius=7.0, layer="Visible", shape_id="m16_tap_hole") # Ø14.0mm tap drill

    # Front view slot depth representation (15mm depth)
    slot_depth_line = Line(start=(-25.0, 0.0), end=(-25.0, -15.0), layer="Hidden", shape_id="slot_depth_l1")

    cad_engine.shapes['top'] = [base, guideway, m16_tap]
    cad_engine.shapes['front'] = [slot_depth_line]

    # 1. Tap drill verification (M16 x 2.0 -> 14.0mm tap drill)
    m16_res = lookup_metric_thread(16.0)
    assert m16_res is not None
    size_name, data = m16_res
    assert size_name == "M16"
    assert abs(data["tap_drill"] - 14.0) < 1e-4

    # 2. DFM Pocket Aspect Ratio Check (15mm depth / 50mm width = 0.30 -> PASS)
    dfm = DFMEngine()
    violations = dfm.check_cnc_pocket_aspect_ratio(cad_engine.shapes)
    assert len(violations) == 0

    # 3. GD&T Engine Verification
    datum_a = DatumFeature(id="dat_a", label="A", origin=(-110.0, -50.0), view="top")
    fcf_parallel = FeatureControlFrame(
        id="fcf_p1", symbol=GDTSymbol.PARALLELISM, tolerance=0.05,
        primary_datum="A", leader_anchor=(-25.0, 20.0), view="top"
    )
    fcf_pos = FeatureControlFrame(
        id="fcf_pos1", symbol=GDTSymbol.POSITION, tolerance=0.15,
        modifier=MaterialModifier.MMC, primary_datum="A", leader_anchor=(0.0, 30.0), view="top"
    )
    cad_engine.datums["dat_a"] = datum_a
    cad_engine.feature_control_frames["fcf_p1"] = fcf_parallel
    cad_engine.feature_control_frames["fcf_pos1"] = fcf_pos

    rules_engine = RulesEngine()
    diags = rules_engine.check_gdt_rules([datum_a], [fcf_parallel, fcf_pos], cad_engine.shapes)
    error_diags = [d for d in diags if d.severity.value == "error"]
    assert len(error_diags) == 0

    # 4. PDF Exporter Execution
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_pdf = tmp.name

    try:
        tb_data = TitleBlockData(
            title="MACHINE VICE FIXED JAW BASE",
            dwg_no="PCAD-VICE-01",
            rev="B",
            material="EN-GJL-250 CAST IRON",
            drafter="Sahil Rane",
            scale="1:1",
            projection="3rd_angle"
        )
        success = DrawingExporter.export_to_pdf(
            cad_engine,
            tmp_pdf,
            sheet_format=SheetFormat.ISO_A3,
            title_block=tb_data
        )
        assert success
        assert os.path.exists(tmp_pdf)
        assert os.path.getsize(tmp_pdf) > 100 # Verify PDF file was generated
    finally:
        if os.path.exists(tmp_pdf):
            os.remove(tmp_pdf)
