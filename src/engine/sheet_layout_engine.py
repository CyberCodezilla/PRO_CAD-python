"""
ISO 5457 / ISO 7200 Technical Drawing Sheet Layout Engine.
Provides standard sheet dimensions, coordinate grid reference zones,
working area boundaries, and ISO 7200 title block positioning.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, List, Dict, Optional, Any
import math


class SheetFormat(Enum):
    ISO_A4 = "ISO_A4"  # 210 x 297 mm
    ISO_A3 = "ISO_A3"  # 420 x 297 mm
    ISO_A2 = "ISO_A2"  # 594 x 420 mm
    ANSI_B = "ANSI_B"  # 11 x 17 in (279.4 x 431.8 mm)
    ANSI_C = "ANSI_C"  # 17 x 22 in (431.8 x 558.8 mm)


@dataclass
class TitleBlockData:
    """ISO 7200 Title Block Metadata Fields"""
    title: str = "PART DRAWING"
    dwg_no: str = "PCAD-3501"
    rev: str = "A"
    material: str = "EN-GJL-250 CAST IRON"
    drafter: str = "Sahil Rane"
    date: str = "2026-08"
    scale: str = "1:1"
    projection: str = "3rd_angle"        # "1st_angle" or "3rd_angle"
    legal_owner: str = "VCET MECHANICAL LABS"
    tolerances: str = "ISO 2768-m"
    units: str = "mm"
    sheet_info: str = "1 / 1 (A3)"


@dataclass
class SheetTemplate:
    """ISO 5457 Sheet Boundary Geometry & Grid Definitions"""
    sheet_format: SheetFormat
    width_mm: float
    height_mm: float
    margin_left: float = 20.0            # 20mm filing margin
    margin_other: float = 10.0           # 10mm standard border margins
    zone_size: float = 50.0              # 50mm reference grid intervals
    title_block_w: float = 180.0
    title_block_h: float = 63.0

    @property
    def working_width(self) -> float:
        return self.width_mm - (self.margin_left + self.margin_other)

    @property
    def working_height(self) -> float:
        return self.height_mm - (2.0 * self.margin_other)

    @property
    def working_origin(self) -> Tuple[float, float]:
        """(X, Y) of top-left corner of the working area inside margins"""
        return (self.margin_left, self.margin_other)

    @property
    def title_block_origin(self) -> Tuple[float, float]:
        """(X, Y) top-left anchor for the bottom-right title block"""
        x = self.width_mm - self.margin_other - self.title_block_w
        y = self.height_mm - self.margin_other - self.title_block_h
        return (x, y)

    @property
    def zones_x(self) -> int:
        """Horizontal zone count (columns 1, 2, 3...)"""
        return max(1, int(self.working_width // self.zone_size))

    @property
    def zones_y(self) -> int:
        """Vertical zone count (rows A, B, C...)"""
        return max(1, int(self.working_height // self.zone_size))


def get_sheet_template(sheet_format: SheetFormat = SheetFormat.ISO_A3) -> SheetTemplate:
    """Retrieve standard ISO 5457 / ASME Y14.1 template"""
    dims = {
        SheetFormat.ISO_A4: (297.0, 210.0), # Landscape
        SheetFormat.ISO_A3: (420.0, 297.0),
        SheetFormat.ISO_A2: (594.0, 420.0),
        SheetFormat.ANSI_B: (431.8, 279.4),
        SheetFormat.ANSI_C: (558.8, 431.8),
    }
    w, h = dims.get(sheet_format, (420.0, 297.0))
    return SheetTemplate(sheet_format=sheet_format, width_mm=w, height_mm=h)


class SheetLayoutEngine:
    """
    Computes coordinate transformations from 4-quadrant canvas space to ISO paper space.
    """

    @staticmethod
    def map_canvas_to_paper(
        x_canvas: float,
        y_canvas: float,
        template: SheetTemplate,
        scale: float = 1.0
    ) -> Tuple[float, float]:
        """
        Transforms centered 4-quadrant canvas coordinates into sheet paper coordinates (Guardrail #2).
        Shifts canvas origin (0, 0) into the center of the available working area.
        """
        # Working area center (leaving space for title block)
        cx = template.margin_left + (template.working_width * 0.42)
        cy = template.margin_other + (template.working_height * 0.50)

        # Scale and map (inverting canvas Y so +Y is up)
        x_paper = cx + (x_canvas * scale)
        y_paper = cy + (y_canvas * scale)

        return (round(x_paper, 4), round(y_paper, 4))
