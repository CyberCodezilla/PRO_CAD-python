"""
1:1 Vector PDF & DXF Manufacturing Drawing Exporter.
Conforming to ISO 7200, ISO 5457, ISO 128-20, and ISO 128-30.
"""

import sys
import math
from typing import Optional, Dict, List, Tuple, Any

from PyQt6.QtCore import Qt, QPointF, QRectF, QMarginsF, QCoreApplication
from PyQt6.QtGui import QPainter, QPdfWriter, QPageSize, QPageLayout, QPen, QColor, QFont, QPainterPath
from PyQt6.QtWidgets import QApplication

from ..engine.sheet_layout_engine import (
    SheetFormat, TitleBlockData, SheetTemplate, get_sheet_template, SheetLayoutEngine
)
from ..engine.cad_engine import CADEngine, Line, Rectangle, Circle, Arc, Polygon, Dimension


# Scale factor: 72 PostScript points per inch (25.4 mm)
POINTS_PER_MM = 72.0 / 25.4  # ~2.83464567 pt/mm


def _ensure_qt_app() -> Optional[QApplication]:
    """Ensure a QApplication instance exists for headless offscreen rendering (Guardrail #1)"""
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication(["python-cad-pro", "-platform", "offscreen"])
        except Exception:
            try:
                app = QCoreApplication(["python-cad-pro"])
            except Exception:
                pass
    return app


class DrawingExporter:
    """
    High-precision technical drawing sheet exporter for 1:1 Vector PDF and DXF formats.
    """

    @staticmethod
    def export_to_pdf(
        cad_engine: CADEngine,
        filepath: str,
        sheet_format: SheetFormat = SheetFormat.ISO_A3,
        title_block: Optional[TitleBlockData] = None,
        scale: float = 1.0
    ) -> bool:
        """
        Exports drafting canvas entities and ISO 7200 sheet frame into a 1:1 vector PDF.
        """
        _ensure_qt_app()
        tb = title_block or TitleBlockData()
        template = get_sheet_template(sheet_format)

        try:
            pdf_writer = QPdfWriter(filepath)
            pdf_writer.setResolution(72)  # 72 DPI standard PostScript point scale

            # Set page dimensions (landscape)
            page_size = QPageSize(QPageSize.PageSizeId.A3 if sheet_format == SheetFormat.ISO_A3 else (
                QPageSize.PageSizeId.A4 if sheet_format == SheetFormat.ISO_A4 else QPageSize.PageSizeId.A2
            ))
            pdf_writer.setPageSize(page_size)
            pdf_writer.setPageOrientation(QPageLayout.Orientation.Landscape)
            pdf_writer.setPageMargins(QMarginsF(0.0, 0.0, 0.0, 0.0), QPageLayout.Unit.Millimeter)

            painter = QPainter(pdf_writer)
            if not painter.isActive():
                painter.begin(pdf_writer)

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Draw ISO 5457 Sheet Border & Reference Grid
            DrawingExporter._render_sheet_frame(painter, template)

            # Draw ISO 7200 Title Block & Projection Cone
            DrawingExporter._render_title_block(painter, template, tb)

            # Draw CAD Drawing Entities
            DrawingExporter._render_cad_entities(painter, cad_engine, template, scale)

            painter.end()
            return True

        except Exception as e:
            print(f"Error exporting PDF: {e}")
            return False

    @staticmethod
    def _render_sheet_frame(painter: QPainter, template: SheetTemplate):
        """Draw outer sheet border, filing margins, and reference coordinate zones (1..8, A..F)"""
        k = POINTS_PER_MM

        # Outer sheet edge (thin)
        outer_pen = QPen(QColor("#000000"), 0.25 * k, Qt.PenStyle.SolidLine)
        painter.setPen(outer_pen)
        painter.drawRect(QRectF(0, 0, template.width_mm * k, template.height_mm * k))

        # Inner working area border (thick 0.70mm line)
        border_pen = QPen(QColor("#000000"), 0.70 * k, Qt.PenStyle.SolidLine)
        painter.setPen(border_pen)
        rx = template.margin_left * k
        ry = template.margin_other * k
        rw = template.working_width * k
        rh = template.working_height * k
        painter.drawRect(QRectF(rx, ry, rw, rh))

        # Reference Zone Grid Marks & Labels
        font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font)
        zone_pen = QPen(QColor("#000000"), 0.35 * k, Qt.PenStyle.SolidLine)
        painter.setPen(zone_pen)

        # Horizontal zones (1, 2, 3...)
        num_x = template.zones_x
        step_x = (template.working_width / num_x) * k
        for i in range(num_x):
            zx = rx + i * step_x
            painter.drawLine(QPointF(zx, 0), QPointF(zx, template.margin_other * k))
            painter.drawLine(QPointF(zx, (template.height_mm - template.margin_other) * k), QPointF(zx, template.height_mm * k))
            painter.drawText(QRectF(zx, 2 * k, step_x, (template.margin_other - 2) * k), Qt.AlignmentFlag.AlignCenter, str(i + 1))
            painter.drawText(QRectF(zx, (template.height_mm - template.margin_other + 2) * k, step_x, (template.margin_other - 2) * k), Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # Vertical zones (A, B, C...)
        num_y = template.zones_y
        step_y = (template.working_height / num_y) * k
        for j in range(num_y):
            zy = ry + j * step_y
            letter = chr(ord('A') + j)
            painter.drawLine(QPointF(0, zy), QPointF(template.margin_left * k, zy))
            painter.drawLine(QPointF((template.width_mm - template.margin_other) * k, zy), QPointF(template.width_mm * k, zy))
            painter.drawText(QRectF(2 * k, zy, (template.margin_left - 4) * k, step_y), Qt.AlignmentFlag.AlignCenter, letter)
            painter.drawText(QRectF((template.width_mm - template.margin_other + 2) * k, zy, (template.margin_other - 4) * k, step_y), Qt.AlignmentFlag.AlignCenter, letter)

    @staticmethod
    def _render_title_block(painter: QPainter, template: SheetTemplate, tb: TitleBlockData):
        """Render ISO 7200 Title Block in bottom-right corner"""
        k = POINTS_PER_MM
        x0, y0 = template.title_block_origin
        x0_pt = x0 * k
        y0_pt = y0 * k
        w_pt = template.title_block_w * k
        h_pt = template.title_block_h * k

        # Title block outer border (0.70mm)
        thick_pen = QPen(QColor("#000000"), 0.70 * k, Qt.PenStyle.SolidLine)
        thin_pen = QPen(QColor("#000000"), 0.35 * k, Qt.PenStyle.SolidLine)

        painter.setPen(thick_pen)
        painter.drawRect(QRectF(x0_pt, y0_pt, w_pt, h_pt))

        # Internal compartment grid lines
        painter.setPen(thin_pen)
        row_h = (template.title_block_h / 4.0) * k

        for r in range(1, 4):
            painter.drawLine(QPointF(x0_pt, y0_pt + r * row_h), QPointF(x0_pt + w_pt, y0_pt + r * row_h))

        # Vertical dividing lines
        col_w = w_pt / 3.0
        painter.drawLine(QPointF(x0_pt + col_w, y0_pt + row_h), QPointF(x0_pt + col_w, y0_pt + h_pt))
        painter.drawLine(QPointF(x0_pt + 2.0 * col_w, y0_pt), QPointF(x0_pt + 2.0 * col_w, y0_pt + h_pt))

        # Text labels
        font_lbl = QFont("Segoe UI", 6)
        font_val = QFont("Segoe UI", 8, QFont.Weight.Bold)

        # Row 1: Legal Owner & Projection Symbol
        painter.setFont(font_lbl)
        painter.drawText(QRectF(x0_pt + 4 * k, y0_pt + 2 * k, col_w * 2.0, row_h), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, f"Legal Owner: {tb.legal_owner}")
        DrawingExporter._render_projection_symbol(painter, x0 + template.title_block_w - 30.0, y0 + 3.0, tb.projection)

        # Row 2: Title, Dwg No, Rev
        painter.setFont(font_val)
        painter.drawText(QRectF(x0_pt + 4 * k, y0_pt + row_h + 2 * k, col_w * 2.0, row_h), Qt.AlignmentFlag.AlignVCenter, f"Title: {tb.title}")
        painter.drawText(QRectF(x0_pt + 2.0 * col_w + 4 * k, y0_pt + row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Dwg: {tb.dwg_no} Rev: {tb.rev}")

        # Row 3: Material, Scale, Sheet
        painter.setFont(font_lbl)
        painter.drawText(QRectF(x0_pt + 4 * k, y0_pt + 2.0 * row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Material: {tb.material}")
        painter.drawText(QRectF(x0_pt + col_w + 4 * k, y0_pt + 2.0 * row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Scale: {tb.scale}")
        painter.drawText(QRectF(x0_pt + 2.0 * col_w + 4 * k, y0_pt + 2.0 * row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Sheet: {tb.sheet_info}")

        # Row 4: Drafter, Date, Tolerances
        painter.drawText(QRectF(x0_pt + 4 * k, y0_pt + 3.0 * row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Drawn: {tb.drafter}")
        painter.drawText(QRectF(x0_pt + col_w + 4 * k, y0_pt + 3.0 * row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Date: {tb.date}")
        painter.drawText(QRectF(x0_pt + 2.0 * col_w + 4 * k, y0_pt + 3.0 * row_h + 2 * k, col_w, row_h), Qt.AlignmentFlag.AlignVCenter, f"Tol: {tb.tolerances} Units: {tb.units}")

    @staticmethod
    def _render_projection_symbol(painter: QPainter, x_mm: float, y_mm: float, proj_type: str = "3rd_angle"):
        """Render ISO 128-30 First / Third Angle projection conical symbol"""
        k = POINTS_PER_MM
        px = x_mm * k
        py = y_mm * k

        pen = QPen(QColor("#000000"), 0.35 * k, Qt.PenStyle.SolidLine)
        painter.setPen(pen)

        if proj_type == "3rd_angle":
            # Concentric circles on left
            c_center = QPointF(px + 6 * k, py + 5 * k)
            painter.drawEllipse(c_center, 4 * k, 4 * k)
            painter.drawEllipse(c_center, 2 * k, 2 * k)

            # Truncated cone on right
            painter.drawLine(QPointF(px + 14 * k, py + 3 * k), QPointF(px + 22 * k, py + 1 * k))
            painter.drawLine(QPointF(px + 22 * k, py + 1 * k), QPointF(px + 22 * k, py + 9 * k))
            painter.drawLine(QPointF(px + 22 * k, py + 9 * k), QPointF(px + 14 * k, py + 7 * k))
            painter.drawLine(QPointF(px + 14 * k, py + 7 * k), QPointF(px + 14 * k, py + 3 * k))
        else:
            # 1st Angle: Cone on left, circles on right
            painter.drawLine(QPointF(px + 2 * k, py + 1 * k), QPointF(px + 10 * k, py + 3 * k))
            painter.drawLine(QPointF(px + 10 * k, py + 3 * k), QPointF(px + 10 * k, py + 7 * k))
            painter.drawLine(QPointF(px + 10 * k, py + 7 * k), QPointF(px + 2 * k, py + 9 * k))
            painter.drawLine(QPointF(px + 2 * k, py + 9 * k), QPointF(px + 2 * k, py + 1 * k))

            c_center = QPointF(px + 18 * k, py + 5 * k)
            painter.drawEllipse(c_center, 4 * k, 4 * k)
            painter.drawEllipse(c_center, 2 * k, 2 * k)

    @staticmethod
    def _render_cad_entities(
        painter: QPainter,
        cad_engine: CADEngine,
        template: SheetTemplate,
        scale: float = 1.0
    ):
        """Render all 2D shapes with ISO 128-20 line weights into paper space"""
        k = POINTS_PER_MM

        pen_visible = QPen(QColor("#000000"), 0.70 * k, Qt.PenStyle.SolidLine)
        pen_hidden = QPen(QColor("#404040"), 0.35 * k, Qt.PenStyle.DashLine)
        pen_center = QPen(QColor("#C00000"), 0.25 * k, Qt.PenStyle.DashDotLine)
        pen_dim = QPen(QColor("#003366"), 0.25 * k, Qt.PenStyle.SolidLine)

        for view_name, shapes in cad_engine.shapes.items():
            for s in shapes:
                # Select pen based on layer
                if s.layer == "Hidden":
                    painter.setPen(pen_hidden)
                elif s.layer == "Centerline":
                    painter.setPen(pen_center)
                elif isinstance(s, Dimension):
                    painter.setPen(pen_dim)
                else:
                    painter.setPen(pen_visible)

                if isinstance(s, Line):
                    x1, y1 = SheetLayoutEngine.map_canvas_to_paper(s.start[0], s.start[1], template, scale)
                    x2, y2 = SheetLayoutEngine.map_canvas_to_paper(s.end[0], s.end[1], template, scale)
                    painter.drawLine(QPointF(x1 * k, y1 * k), QPointF(x2 * k, y2 * k))

                elif isinstance(s, Rectangle):
                    rx, ry, rw, rh = s.rect
                    x1, y1 = SheetLayoutEngine.map_canvas_to_paper(rx, ry, template, scale)
                    x2, y2 = SheetLayoutEngine.map_canvas_to_paper(rx + rw, ry + rh, template, scale)
                    rect = QRectF(QPointF(x1 * k, y1 * k), QPointF(x2 * k, y2 * k)).normalized()
                    painter.drawRect(rect)

                elif isinstance(s, Circle):
                    cx, cy = SheetLayoutEngine.map_canvas_to_paper(s.center[0], s.center[1], template, scale)
                    r_pt = s.radius * scale * k
                    painter.drawEllipse(QPointF(cx * k, cy * k), r_pt, r_pt)

                elif isinstance(s, Arc):
                    cx, cy = SheetLayoutEngine.map_canvas_to_paper(s.center[0], s.center[1], template, scale)
                    r_pt = s.radius * scale * k
                    rect = QRectF(cx * k - r_pt, cy * k - r_pt, r_pt * 2, r_pt * 2)
                    start_angle_16th = int(s.start_angle * 16)
                    span_angle_16th = int((s.end_angle - s.start_angle) * 16)
                    painter.drawArc(rect, start_angle_16th, span_angle_16th)

    @staticmethod
    def export_to_dxf(
        cad_engine: CADEngine,
        filepath: str,
        sheet_format: SheetFormat = SheetFormat.ISO_A3
    ) -> bool:
        """
        Exports CAD drawing entities to standard 2D DXF with lazy ezdxf import (Guardrail #3).
        """
        try:
            import ezdxf
        except ImportError:
            print("Warning: ezdxf is not installed. DXF export skipped.")
            return False

        try:
            doc = ezdxf.new('R2010')
            msp = doc.modelspace()

            # Setup standard layers
            doc.layers.add('VISIBLE', color=7)     # White/Black (0.70mm)
            doc.layers.add('HIDDEN', color=8, linetype='DASHED')  # Gray (0.35mm)
            doc.layers.add('CENTER', color=1, linetype='DASHDOT') # Red (0.25mm)

            for view_name, shapes in cad_engine.shapes.items():
                for s in shapes:
                    layer_name = 'VISIBLE'
                    if s.layer == 'Hidden':
                        layer_name = 'HIDDEN'
                    elif s.layer == 'Centerline':
                        layer_name = 'CENTER'

                    if isinstance(s, Line):
                        msp.add_line(s.start, s.end, dxfattribs={'layer': layer_name})
                    elif isinstance(s, Rectangle):
                        rx, ry, rw, rh = s.rect
                        pts = [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh), (rx, ry)]
                        msp.add_lwpolyline(pts, dxfattribs={'layer': layer_name})
                    elif isinstance(s, Circle):
                        msp.add_circle(s.center, s.radius, dxfattribs={'layer': layer_name})

            doc.saveas(filepath)
            return True
        except Exception as e:
            print(f"Error exporting DXF: {e}")
            return False
