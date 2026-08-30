"""
Section Views & Cutting-Plane Semantics Engine (ISO 128-40 / ISO 128-50 / ASME Y14.3).
Provides:
- Cutting plane line representation and 2D-to-3D infinite slicing plane conversion.
- Material-specific 45-degree cross-hatch synthesis via Shapely polygon slicing.
- Stepped and offset section path decomposition.
- ASME Y14.3 / ISO 128-50 non-hatching exclusion for longitudinal ribs, webs, and shafts.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional, Any
import math
import numpy as np
import shapely.geometry as sg
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection


class SectionType(Enum):
    FULL = "full"
    OFFSET = "offset"
    HALF = "half"
    REVOLVED = "revolved"


@dataclass
class CuttingPlane:
    """Represents a 2D cutting-plane line on a drafting sheet"""
    id: str
    label: str = "A"                                   # e.g., "A" for Section A—A
    view: str = "top"                                  # Source view where plane is drawn
    points: List[Tuple[float, float]] = field(default_factory=list) # Ordered path vertices
    normal: Tuple[float, float] = (0.0, -1.0)          # 2D viewing sight normal (nx, ny)
    arrow_size: float = 8.0                            # Size of sight arrowheads in mm
    line_style: str = "dash_dot"                       # ISO 128-40 thick dash-dot line


@dataclass
class SectionView:
    """Represents the projected section view resulting from a cutting plane"""
    id: str
    cutting_plane_id: str
    target_view: str = "front"                         # Where the sectioned cut is projected
    section_type: SectionType = SectionType.FULL
    hatch_angle: float = 45.0                          # Angle in degrees relative to principal axis
    hatch_pitch: float = 3.0                           # Distance between parallel hatch lines in mm
    rib_exclusion_ids: List[str] = field(default_factory=list)  # Shapes excluded from hatching (Rule SECT_02)


class SectionEngine:
    """
    Mathematical and geometric operations for 2D cross-hatching and 3D B-Rep sectioning.
    """

    @staticmethod
    def compute_3d_cutting_plane_equation(
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        normal_2d: Tuple[float, float],
        view: str = "top"
    ) -> Tuple[float, float, float, float]:
        """
        Derives 3D plane equation Ax + By + Cz + D = 0 from a 2D cutting-plane segment (Guardrail #1).
        Maps 2D quadrant canvas coordinates into 3D Cartesian space:
        - Top View (Quadrant III, X-Z plane): canvas (x, y) -> 3D (x, 0, y)
        - Front View (Quadrant II, X-Y plane): canvas (x, y) -> 3D (x, -y, 0)
        """
        x1, y1 = p1
        x2, y2 = p2
        nx, ny = normal_2d

        # Normalize 2D viewing normal vector
        norm_len = math.hypot(nx, ny)
        if norm_len > 1e-6:
            nx, ny = nx / norm_len, ny / norm_len
        else:
            # Derive normal perpendicular to tangent if not provided
            dx = x2 - x1
            dy = y2 - y1
            l = math.hypot(dx, dy)
            if l > 1e-6:
                nx, ny = -dy / l, dx / l
            else:
                nx, ny = 0.0, -1.0

        if view == "top":
            # In Top View (X-Z plane):
            # Normal in 3D: N = (nx, 0.0, ny)
            # Point in 3D: P0 = (x1, 0.0, y1)
            A = float(nx)
            B = 0.0
            C = float(ny)
            D = float(-(A * x1 + C * y1))
        elif view == "front":
            # In Front View (X-Y plane):
            # Normal in 3D: N = (nx, -ny, 0.0)
            # Point in 3D: P0 = (x1, -y1, 0.0)
            A = float(nx)
            B = float(-ny)
            C = 0.0
            D = float(-(A * x1 + B * (-y1)))
        else: # side view (Y-Z plane)
            A = 0.0
            B = float(-ny)
            C = float(nx)
            D = float(-(B * (-y1) + C * x1))

        return (round(A, 6), round(B, 6), round(C, 6), round(D, 6))

    @staticmethod
    def compute_optimal_hatch_pitch(area: float) -> float:
        """
        ISO 128-50 dynamic pitch scaling based on cut surface area:
        S = max(1.5, min(5.0, sqrt(Area) / 20.0))
        """
        if area <= 0.0:
            return 3.0
        return max(1.5, min(5.0, math.sqrt(area) / 20.0))

    @staticmethod
    def generate_hatch_lines(
        outer_boundary: List[Tuple[float, float]],
        holes: Optional[List[List[Tuple[float, float]]]] = None,
        pitch: float = 3.0,
        angle_deg: float = 45.0
    ) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """
        Synthesize continuous thin parallel cross-hatch lines over a cut planar polygon (Guardrail #3).
        1. Rotate polygon by -theta.
        2. Generate horizontal test scanlines across [v_min, v_max].
        3. Intersect with Shapely polygon and safely unpack LineStrings.
        4. Rotate intersection segments back by +theta.
        """
        if len(outer_boundary) < 3:
            return []

        holes = holes or []
        poly = Polygon(shell=outer_boundary, holes=holes)
        if not poly.is_valid:
            poly = poly.buffer(0)
            if not poly.is_valid or poly.is_empty:
                return []

        theta_rad = math.radians(angle_deg)
        cos_t = math.cos(-theta_rad)
        sin_t = math.sin(-theta_rad)

        def rotate_pt(x: float, y: float, c: float, s: float) -> Tuple[float, float]:
            return (x * c - y * s, x * s + y * c)

        # Rotate outer shell and holes
        rot_shell = [rotate_pt(x, y, cos_t, sin_t) for x, y in outer_boundary]
        rot_holes = [[rotate_pt(x, y, cos_t, sin_t) for x, y in h] for h in holes]

        rot_poly = Polygon(shell=rot_shell, holes=rot_holes)
        if not rot_poly.is_valid:
            rot_poly = rot_poly.buffer(0)

        min_u, min_v, max_u, max_v = rot_poly.bounds

        hatch_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        cos_back = math.cos(theta_rad)
        sin_back = math.sin(theta_rad)

        v_curr = min_v + pitch
        while v_curr < max_v:
            scanline = LineString([(min_u - 10.0, v_curr), (max_u + 10.0, v_curr)])
            try:
                inter = rot_poly.intersection(scanline)
                # Guardrail 3: Cleanly unpack LineString, MultiLineString, or GeometryCollection
                extracted_lines: List[LineString] = []

                if isinstance(inter, LineString):
                    extracted_lines.append(inter)
                elif isinstance(inter, MultiLineString):
                    extracted_lines.extend(inter.geoms)
                elif isinstance(inter, GeometryCollection):
                    for g in inter.geoms:
                        if isinstance(g, LineString):
                            extracted_lines.append(g)

                for line in extracted_lines:
                    coords = list(line.coords)
                    if len(coords) >= 2:
                        for k in range(len(coords) - 1):
                            p_start = rotate_pt(coords[k][0], coords[k][1], cos_back, sin_back)
                            p_end = rotate_pt(coords[k + 1][0], coords[k + 1][1], cos_back, sin_back)
                            if math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1]) > 0.01:
                                hatch_segments.append((
                                    (round(p_start[0], 4), round(p_start[1], 4)),
                                    (round(p_end[0], 4), round(p_end[1], 4))
                                ))
            except Exception as e:
                print(f"Hatch line intersection warning: {e}")

            v_curr += pitch

        return hatch_segments

    @staticmethod
    def parse_offset_cutting_path(
        vertices: List[Tuple[float, float]]
    ) -> List[Tuple[Tuple[float, float], Tuple[float, float], bool]]:
        """
        Decomposes an offset/stepped cutting-plane line path into sub-segments,
        flagging transverse step jogs that must be hidden per ASME Y14.3.
        """
        segments = []
        if len(vertices) < 2:
            return segments

        # Main longitudinal axis is defined by vector from start to end
        total_dx = vertices[-1][0] - vertices[0][0]
        total_dy = vertices[-1][1] - vertices[0][1]
        is_horizontal_main = abs(total_dx) >= abs(total_dy)

        for i in range(len(vertices) - 1):
            p_a = vertices[i]
            p_b = vertices[i + 1]
            seg_dx = abs(p_b[0] - p_a[0])
            seg_dy = abs(p_b[1] - p_a[1])

            # A jog is transverse (perpendicular) to the main cut direction
            is_jog = seg_dy > seg_dx if is_horizontal_main else seg_dx > seg_dy
            segments.append((p_a, p_b, is_jog))

        return segments
