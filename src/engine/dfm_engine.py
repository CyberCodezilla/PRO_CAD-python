"""
Design for Manufacturing (DFM) Advisory & Linter Engine.
Conforming to ASME Y14.8, DIN 8580, and ISO 2768:
- CNC Milling Feasibility (interior concave sharp corners & deep pocket aspect ratios)
- Injection Molding & Die Casting Draw Geometry (draft angles & rib sink mark risk)
- Sheet Metal Limits (minimum inside bend radii & hole-to-bend tear-out clearances)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Any
import math
import numpy as np
import shapely.geometry as sg
from shapely.geometry import Polygon, MultiPolygon, Point, LineString

from .cad_engine import Shape, Line, Rectangle, Circle, Polygon as CADPolygon, Arc


class ManufacturingProcess(Enum):
    CNC_MILLING = "cnc_milling"
    INJECTION_MOLDING = "injection_molding"
    DIE_CASTING = "die_casting"
    SHEET_METAL = "sheet_metal"


class DFMDiagnosticSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class DFMViolation:
    """Detailed Design for Manufacturing diagnostic item"""
    rule_id: str                              # e.g., "DFM_CNC_01", "DFM_MOLD_01"
    severity: DFMDiagnosticSeverity
    process: ManufacturingProcess
    title: str
    description: str
    suggestion: str
    location_2d: Tuple[float, float]          # Coordinates on drafting canvas
    target_shape_id: Optional[str] = None
    face_id_3d: Optional[int] = None
    recommended_value: Optional[float] = None
    autofix_payload: Optional[Dict[str, Any]] = None


class DFMEngine:
    """
    Automated DFM analyzer evaluating 2D drafting entities and 3D B-Rep models.
    """

    def __init__(self, default_process: ManufacturingProcess = ManufacturingProcess.CNC_MILLING):
        self.process = default_process

    def evaluate_all_rules(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        process: Optional[ManufacturingProcess] = None,
        brep_solid: Optional[Any] = None
    ) -> List[DFMViolation]:
        """Run DFM rules for the selected manufacturing process"""
        active_proc = process or self.process
        violations: List[DFMViolation] = []

        if active_proc == ManufacturingProcess.CNC_MILLING:
            violations.extend(self.check_cnc_sharp_corners(shapes_by_view.get('top', [])))
            violations.extend(self.check_cnc_pocket_aspect_ratio(shapes_by_view))

        elif active_proc in (ManufacturingProcess.INJECTION_MOLDING, ManufacturingProcess.DIE_CASTING):
            violations.extend(self.check_molding_draft_angles(brep_solid, shapes_by_view))
            violations.extend(self.check_molding_wall_thickness(shapes_by_view))

        elif active_proc == ManufacturingProcess.SHEET_METAL:
            violations.extend(self.check_sheet_metal_bend_radii(shapes_by_view))
            violations.extend(self.check_sheet_metal_hole_proximity(shapes_by_view))

        return violations

    # -------------------------------------------------------------------------
    # 1. CNC MILLING RULES (DFM_CNC_01, DFM_CNC_02)
    # -------------------------------------------------------------------------
    def check_cnc_sharp_corners(
        self,
        top_shapes: List[Shape],
        tool_radius: float = 1.5
    ) -> List[DFMViolation]:
        """
        Rule DFM_CNC_01: Internal Sharp Corner Inaccessibility.
        Distinguishes outer stock boundaries from internal pocket cutouts using Shapely containment (Guardrail #1).
        Flags interior pocket corners with radius < tool_radius.
        """
        violations: List[DFMViolation] = []
        if not top_shapes:
            return violations

        # Group polygons and rectangles
        poly_candidates: List[Tuple[Shape, List[Tuple[float, float]], bool]] = []

        for s in top_shapes:
            if isinstance(s, Rectangle):
                rx, ry, rw, rh = s.rect
                pts = [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)]
                poly_candidates.append((s, pts, s.layer == "Hidden"))
            elif isinstance(s, CADPolygon):
                pts = s.points
                if len(pts) >= 3:
                    poly_candidates.append((s, pts, s.layer == "Hidden"))

        if not poly_candidates:
            return violations

        # Determine outer boundaries vs interior cutouts
        shapely_polys = []
        for s, pts, is_hidden in poly_candidates:
            try:
                p = Polygon(pts)
                if p.is_valid and not p.is_empty:
                    shapely_polys.append((s, pts, p, is_hidden))
            except Exception:
                pass

        for s, pts, poly, is_hidden in shapely_polys:
            # Check if this polygon is an interior pocket (either explicitly Hidden or enclosed inside another outer polygon)
            is_interior_pocket = is_hidden
            if not is_interior_pocket:
                for other_s, other_pts, other_poly, _ in shapely_polys:
                    if other_s.id != s.id and other_poly.contains(poly.centroid) and other_poly.area > poly.area * 1.2:
                        is_interior_pocket = True
                        break

            if not is_interior_pocket:
                continue

            # Check all corners of the interior pocket
            n = len(pts)
            for i in range(n):
                p_prev = pts[(i - 1) % n]
                p_curr = pts[i]
                p_next = pts[(i + 1) % n]

                v1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
                v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])

                # 2D Cross Product
                cross_z = (v1[0] * v2[1]) - (v1[1] * v2[0])

                # For interior pocket vertices, a 90° or sharp corner creates a zero-radius inaccessible corner for an endmill
                # If corner is not filleted (corner radius = 0.0 < tool_radius)
                rec_radius = round(tool_radius + 0.1, 2)
                violations.append(DFMViolation(
                    rule_id="DFM_CNC_01",
                    severity=DFMDiagnosticSeverity.ERROR,
                    process=ManufacturingProcess.CNC_MILLING,
                    title="Internal Sharp Corner Inaccessible to CNC Endmill",
                    description=(
                        f"Zero-radius interior corner at ({p_curr[0]:.1f}, {p_curr[1]:.1f}) cannot be machined "
                        f"with a standard Ø{2.0 * tool_radius:.1f} mm endmill."
                    ),
                    suggestion=f"Add a corner fillet of radius >= {rec_radius:.1f} mm (e.g. {rec_radius:.1f} mm).",
                    location_2d=(p_curr[0], p_curr[1]),
                    target_shape_id=s.id,
                    recommended_value=rec_radius,
                    autofix_payload={
                        "action": "CNC_ADD_CORNER_FILLET",
                        "shape_id": s.id,
                        "vertex_index": i,
                        "recommended_radius": rec_radius
                    }
                ))

        return violations

    def check_cnc_pocket_aspect_ratio(
        self,
        shapes_by_view: Dict[str, List[Shape]]
    ) -> List[DFMViolation]:
        """
        Rule DFM_CNC_02: Deep Pocket Aspect Ratio (Tool Deflection & Chatter).
        Aspect_Ratio = Pocket_Depth / Minimum_Wall_Span.
        <= 4.0: PASS, 4.0 < AR <= 6.0: WARNING, > 6.0: ERROR.
        """
        violations: List[DFMViolation] = []
        top_shapes = shapes_by_view.get('top', [])
        front_shapes = shapes_by_view.get('front', [])

        # Find pocket widths in top view
        pockets = [s for s in top_shapes if (isinstance(s, Rectangle) and s.layer == "Hidden")]

        for p in pockets:
            w, h = p.rect[2], p.rect[3]
            min_span = min(w, h)
            if min_span <= 0.0:
                continue

            # Estimate depth from front view hidden lines or assume part height
            depth = 70.0  # Default test depth or match from front view
            front_hidden_lines = [s for s in front_shapes if isinstance(s, Line) and s.layer == "Hidden"]
            if front_hidden_lines:
                depth = max(abs(l.end[1] - l.start[1]) for l in front_hidden_lines)

            aspect_ratio = depth / min_span

            if aspect_ratio > 6.0:
                violations.append(DFMViolation(
                    rule_id="DFM_CNC_02",
                    severity=DFMDiagnosticSeverity.ERROR,
                    process=ManufacturingProcess.CNC_MILLING,
                    title="Excessive Pocket Depth-to-Width Ratio (Tool Deflection / Chatter)",
                    description=(
                        f"Pocket depth ({depth:.1f} mm) to minimum span ({min_span:.1f} mm) aspect ratio is {aspect_ratio:.1f}:1 "
                        f"(exceeds maximum 6.0:1 threshold)."
                    ),
                    suggestion="Widen pocket span, reduce depth, or specify EDM/pocket split to prevent tool breakage.",
                    location_2d=(p.rect[0] + w / 2.0, p.rect[1] + h / 2.0),
                    target_shape_id=p.id,
                    recommended_value=4.0
                ))
            elif aspect_ratio > 4.0:
                violations.append(DFMViolation(
                    rule_id="DFM_CNC_02",
                    severity=DFMDiagnosticSeverity.WARNING,
                    process=ManufacturingProcess.CNC_MILLING,
                    title="Deep Pocket: High Tool Deflection Warning",
                    description=f"Pocket aspect ratio is {aspect_ratio:.1f}:1 (> 4.0:1). Requires reduced feeds and custom long-reach endmills.",
                    suggestion="Consider widening pocket if possible to standard 4:1 aspect ratio.",
                    location_2d=(p.rect[0] + w / 2.0, p.rect[1] + h / 2.0),
                    target_shape_id=p.id,
                    recommended_value=4.0
                ))

        return violations

    # -------------------------------------------------------------------------
    # 2. INJECTION MOLDING & DIE CASTING RULES (DFM_MOLD_01, DFM_MOLD_02)
    # -------------------------------------------------------------------------
    def check_molding_draft_angles(
        self,
        brep_solid: Optional[Any] = None,
        shapes_by_view: Optional[Dict[str, List[Shape]]] = None,
        pull_vector: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    ) -> List[DFMViolation]:
        """
        Rule DFM_MOLD_01: Missing Draft Angle on Vertical Walls.
        Evaluates 3D face normals when brep_solid is present, with 2D sidewall elevation fallback (Guardrail #2).
        """
        violations: List[DFMViolation] = []

        # 3D B-Rep Mode
        if brep_solid is not None:
            faces_attr = getattr(brep_solid, 'faces', [])
            faces_list = faces_attr() if callable(faces_attr) else (faces_attr or [])

            for idx, face in enumerate(faces_list):
                f_norm = getattr(face, 'normal_at', None)
                if not f_norm:
                    continue
                try:
                    norm = f_norm((0, 0))
                    nx = getattr(norm, 'X', 0.0)
                    ny = getattr(norm, 'Y', 0.0)
                    nz = getattr(norm, 'Z', 0.0)

                    mag = math.hypot(nx, math.hypot(ny, nz))
                    if mag < 1e-4:
                        continue
                    nx, ny, nz = nx / mag, ny / mag, nz / mag

                    # Dot product with pull vector
                    dot = nx * pull_vector[0] + ny * pull_vector[1] + nz * pull_vector[2]
                    dot = max(-1.0, min(1.0, dot))
                    angle_to_pull = math.degrees(math.acos(abs(dot)))
                    draft_angle = abs(90.0 - angle_to_pull)

                    # If side face (perpendicular to pull direction) has zero or near-zero draft
                    if abs(nz) < 0.2: # Sidewall face
                        if draft_angle < 0.5:
                            violations.append(DFMViolation(
                                rule_id="DFM_MOLD_01",
                                severity=DFMDiagnosticSeverity.ERROR,
                                process=ManufacturingProcess.INJECTION_MOLDING,
                                title="Zero Draft on Mold Wall",
                                description=f"Face {idx} has {draft_angle:.1f}° draft angle along draw vector (minimum 1.0° required).",
                                suggestion="Apply at least 1.5° draft angle to allow clean part ejection without scuffing.",
                                location_2d=(0.0, 0.0),
                                face_id_3d=idx,
                                recommended_value=1.5,
                                autofix_payload={"action": "MOLD_APPLY_DRAFT", "face_index": idx, "draft_angle": 1.5}
                            ))
                        elif draft_angle < 1.0:
                            violations.append(DFMViolation(
                                rule_id="DFM_MOLD_01",
                                severity=DFMDiagnosticSeverity.WARNING,
                                process=ManufacturingProcess.INJECTION_MOLDING,
                                title="Marginal Draft Angle on Mold Wall",
                                description=f"Face {idx} draft angle is {draft_angle:.1f}° (< 1.0° standard).",
                                suggestion="Increase draft angle to 1.5° for improved tooling life.",
                                location_2d=(0.0, 0.0),
                                face_id_3d=idx,
                                recommended_value=1.5
                            ))
                except Exception:
                    pass

        # 2D Fallback Mode (Guardrail #2)
        elif shapes_by_view:
            front_shapes = shapes_by_view.get('front', [])
            for s in front_shapes:
                if isinstance(s, Line) and s.layer == "Visible":
                    # Pure vertical line in elevation view has 0.0° draft
                    if abs(s.start[0] - s.end[0]) < 1e-4 and abs(s.start[1] - s.end[1]) > 10.0:
                        mid_x = (s.start[0] + s.end[0]) / 2.0
                        mid_y = (s.start[1] + s.end[1]) / 2.0
                        violations.append(DFMViolation(
                            rule_id="DFM_MOLD_01",
                            severity=DFMDiagnosticSeverity.ERROR,
                            process=ManufacturingProcess.INJECTION_MOLDING,
                            title="Zero Draft on Vertical Wall (2D Elevation)",
                            description="Vertical sidewall has 0.0° draft angle relative to vertical mold pull vector.",
                            suggestion="Add 1.5° taper to sidewall to ensure mold release.",
                            location_2d=(mid_x, mid_y),
                            target_shape_id=s.id,
                            recommended_value=1.5
                        ))

        return violations

    def check_molding_wall_thickness(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        nominal_wall: float = 3.0
    ) -> List[DFMViolation]:
        """
        Rule DFM_MOLD_02: Wall Thickness Ratio & Sink Mark Risk.
        Rib_Wall_Ratio = Rib_Thickness / Nominal_Wall. If > 0.60: WARNING.
        """
        violations: List[DFMViolation] = []
        front_shapes = shapes_by_view.get('front', [])

        for s in front_shapes:
            if isinstance(s, Rectangle):
                w, h = s.rect[2], s.rect[3]
                rib_t = min(w, h)
                ratio = rib_t / nominal_wall
                if ratio > 0.60 and max(w, h) > rib_t * 2.0:
                    rec_t = round(0.55 * nominal_wall, 2)
                    violations.append(DFMViolation(
                        rule_id="DFM_MOLD_02",
                        severity=DFMDiagnosticSeverity.WARNING,
                        process=ManufacturingProcess.INJECTION_MOLDING,
                        title="Sink Mark Risk on Opposite Class-A Surface",
                        description=(
                            f"Rib thickness ({rib_t:.1f} mm) is {ratio*100:.0f}% of nominal wall ({nominal_wall:.1f} mm), "
                            f"exceeding standard 60% rule."
                        ),
                        suggestion=f"Reduce rib thickness to {rec_t:.1f} mm (55% nominal wall) to prevent surface sinks.",
                        location_2d=(s.rect[0] + w / 2.0, s.rect[1] + h / 2.0),
                        target_shape_id=s.id,
                        recommended_value=rec_t
                    ))

        return violations

    # -------------------------------------------------------------------------
    # 3. SHEET METAL FORMING RULES (DFM_SHEET_01, DFM_SHEET_02)
    # -------------------------------------------------------------------------
    def check_sheet_metal_bend_radii(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        thickness: float = 2.0,
        k_mat: float = 1.0
    ) -> List[DFMViolation]:
        """
        Rule DFM_SHEET_01: Minimum Inside Bend Radius.
        R_min_allowed = k_mat * Sheet_Thickness.
        """
        violations: List[DFMViolation] = []
        r_min = k_mat * thickness

        for vname, shapes in shapes_by_view.items():
            for s in shapes:
                if isinstance(s, Arc):
                    if s.radius < r_min:
                        violations.append(DFMViolation(
                            rule_id="DFM_SHEET_01",
                            severity=DFMDiagnosticSeverity.ERROR,
                            process=ManufacturingProcess.SHEET_METAL,
                            title="Inside Bend Radius Too Sharp (Sheet Metal Cracking Risk)",
                            description=(
                                f"Drawn inside bend radius ({s.radius:.1f} mm) is less than minimum allowed "
                                f"{r_min:.1f} mm for {thickness:.1f} mm sheet."
                            ),
                            suggestion=f"Increase inside bend radius to at least {r_min:.1f} mm.",
                            location_2d=s.center,
                            target_shape_id=s.id,
                            recommended_value=r_min,
                            autofix_payload={"action": "SHEET_EXPAND_BEND_RADIUS", "shape_id": s.id, "target_radius": r_min}
                        ))

        return violations

    def check_sheet_metal_hole_proximity(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        thickness: float = 2.0,
        drawn_bend_radius: float = 2.0
    ) -> List[DFMViolation]:
        """
        Rule DFM_SHEET_02: Hole Proximity to Sheet Metal Bend Line.
        Hole_Edge_Distance = Center_To_Bend_Distance - (D_hole / 2.0).
        Safe_Clearance = (2.0 * Sheet_Thickness) + Drawn_Bend_Radius.
        """
        violations: List[DFMViolation] = []
        safe_clearance = (2.0 * thickness) + drawn_bend_radius

        for vname, shapes in shapes_by_view.items():
            circles = [s for s in shapes if isinstance(s, Circle)]
            lines = [s for s in shapes if isinstance(s, Line) and s.layer == "Centerline"]

            for c in circles:
                d_hole = 2.0 * c.radius
                # Check distance to nearest bend centerline
                for bend_line in lines:
                    # Calculate perpendicular distance from circle center to bend line segment
                    p1 = np.array(bend_line.start)
                    p2 = np.array(bend_line.end)
                    p = np.array(c.center)

                    l_vec = p2 - p1
                    l_len = np.linalg.norm(l_vec)
                    if l_len > 1e-4:
                        u = np.dot(p - p1, l_vec) / (l_len ** 2)
                        u = max(0.0, min(1.0, u))
                        proj = p1 + u * l_vec
                        center_dist = float(np.linalg.norm(p - proj))
                        hole_edge_dist = center_dist - c.radius

                        if hole_edge_dist < safe_clearance:
                            violations.append(DFMViolation(
                                rule_id="DFM_SHEET_02",
                                severity=DFMDiagnosticSeverity.WARNING,
                                process=ManufacturingProcess.SHEET_METAL,
                                title="Hole Inside Bend Deformation Zone (Oval Distortion Risk)",
                                description=(
                                    f"Hole edge distance ({hole_edge_dist:.1f} mm) is less than required safe clearance "
                                    f"({safe_clearance:.1f} mm) from the bend line."
                                ),
                                suggestion=f"Move hole center at least {safe_clearance + c.radius:.1f} mm from the bend line.",
                                location_2d=c.center,
                                target_shape_id=c.id,
                                recommended_value=safe_clearance
                            ))

        return violations
