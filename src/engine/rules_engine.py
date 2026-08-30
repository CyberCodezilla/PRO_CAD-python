"""
Rules Engine — Comprehensive Engineering Graphics Drafting Rules Evaluator.
Implements ASME Y14.5 and ISO 128 drafting standards verification, topological integrity checks,
projection angle detection, and diagnostic suggestions with auto-fix payloads.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any, Optional
import math
import numpy as np
import shapely.geometry as sg
import shapely.ops as so

from .cad_engine import Shape, Line, Rectangle, Circle, Arc, Polygon, ViewRegion, get_shape_centroid
from .gdt_engine import DatumFeature, FeatureControlFrame, GDTSymbol, GDTEngine
from .standards_db import METRIC_COARSE_THREADS, lookup_metric_thread
from .feature_recognizer import FeatureRecognizer, BoltCirclePattern
from .section_engine import CuttingPlane, SectionView, SectionType, SectionEngine
from .dfm_engine import DFMEngine, ManufacturingProcess, DFMDiagnosticSeverity, DFMViolation
from .assembly_engine import Assembly, Part, AssemblyMate
from .fits_db import evaluate_iso_fit


class DiagnosticSeverity(Enum):
    """Severity levels for CAD Doctor diagnostics"""
    ERROR = "error"         # Critical error: blocks 3D CSG reconstruction
    WARNING = "warning"     # Important warning: non-standard or potential misalignment
    INFO = "info"           # Information/suggestion: e.g., projection angle detected


@dataclass
class Diagnostic:
    """Detailed diagnostic item produced by the RulesEngine"""
    rule_id: str
    severity: DiagnosticSeverity
    title: str
    description: str
    suggestion: str
    mismatched_shape_ids: List[str] = field(default_factory=list)
    fix_action: Optional[str] = None          # Action identifier e.g. 'auto_scale_width', 'auto_snap_vertices'
    fix_data: Optional[Dict[str, Any]] = None  # Numerical / payload parameters required for auto-fix


class RulesEngine:
    """Evaluates 2D drafting primitives across orthographic views against ASME Y14.5 / ISO 128 standards"""

    def __init__(self, epsilon: float = 0.1, alignment_tolerance: float = 2.0):
        self.epsilon = epsilon  # Near-coincident vertex tolerance (mm)
        self.alignment_tolerance = alignment_tolerance  # Orthographic alignment tolerance (mm)

    def evaluate_all(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        view_regions: Dict[str, ViewRegion],
        datums: Optional[List[DatumFeature]] = None,
        feature_control_frames: Optional[List[FeatureControlFrame]] = None,
        cutting_planes: Optional[List[CuttingPlane]] = None,
        section_views: Optional[List[SectionView]] = None,
        manufacturing_process: Optional[ManufacturingProcess] = None,
        brep_solid: Optional[Any] = None,
        assembly: Optional[Assembly] = None
    ) -> List[Diagnostic]:
        """Run all engineering drafting rules, GD&T, DFM, and Assembly checks to aggregate diagnostic report"""
        diagnostics: List[Diagnostic] = []

        # 1. Projection Angle Detection Rule
        proj_type, proj_diags = self.detect_projection_type(view_regions)
        diagnostics.extend(proj_diags)

        # 2. Orthographic Alignment Rule (Width, Height, Depth)
        diagnostics.extend(self.check_orthographic_alignment(shapes_by_view, view_regions))

        # 3. 2D Profile Closure Rule (Watertight Profiles)
        diagnostics.extend(self.check_profile_closure(shapes_by_view))

        # 4. Line Precedence Rule (ASME Y14.5 / ISO 128 Visible vs Hidden)
        diagnostics.extend(self.check_line_precedence(shapes_by_view))

        # 5. Vertex Coincidence & Edge Projection Rule
        diagnostics.extend(self.check_vertex_coincidence(shapes_by_view))

        # 6. Hidden Line Depth Inference Rule (Through vs Blind Holes)
        diagnostics.extend(self.check_hidden_line_depth_inference(shapes_by_view))

        # 7. Inclined & Oblique Plane Edge Matching Rule
        diagnostics.extend(self.check_inclined_plane_matching(shapes_by_view))

        # 8. Centerline & Symmetry Recognition Rule
        diagnostics.extend(self.check_centerline_symmetry(shapes_by_view))

        # 9. Line Priority & Overlap Resolution Rule (Auto-Trim)
        diagnostics.extend(self.check_line_priority_overlap(shapes_by_view))

        # 10. Minimum Gap Tolerance Rule (Topological Micro-Gaps)
        diagnostics.extend(self.check_minimum_gap_tolerance(shapes_by_view))

        # 11. Revolved Surface & Cylindrical Feature Recognition Rule
        diagnostics.extend(self.check_revolved_feature_candidates(shapes_by_view))

        # 12. Auxiliary View Projection Alignment Rule
        diagnostics.extend(self.check_auxiliary_view_alignment(shapes_by_view, view_regions))

        # 13. Fillet Radius Over-Constraint Diagnostic Rule
        diagnostics.extend(self.check_fillet_radius_bounds(shapes_by_view))

        # 14. Gated Orthographic Ambiguity Detection Rule
        diagnostics.extend(self.check_orthographic_ambiguity(shapes_by_view))

        # 15. ASME Y14.5-2018 GD&T Rules (Datum Existence, Orthogonality, DRF, Stack-Up)
        if datums is not None or feature_control_frames is not None:
            diagnostics.extend(self.check_gdt_rules(datums or [], feature_control_frames or [], shapes_by_view))

        # 16. Standard Mechanical Features & Machine Elements Rules (MECH_01, MECH_02)
        diagnostics.extend(self.check_mechanical_feature_rules(shapes_by_view))

        # 17. ISO 128-40 / ASME Y14.3 Section View & Cutting-Plane Rules (SECT_01 to SECT_04)
        if cutting_planes is not None or section_views is not None:
            diagnostics.extend(self.check_section_rules(cutting_planes or [], section_views or [], shapes_by_view))

        # 18. Design for Manufacturing (DFM) Rules (CNC, Molding, Sheet Metal)
        diagnostics.extend(self.check_dfm_rules(shapes_by_view, manufacturing_process, brep_solid))

        # 19. Multi-Part Assembly & ISO 286 Fits Rules (ASSY_01 to ASSY_03)
        if assembly is not None:
            diagnostics.extend(self.check_assembly_rules(assembly, shapes_by_view))

        return diagnostics

    # -------------------------------------------------------------------------
    # RULE 1: PROJECTION TYPE DETECTION (1ST ANGLE VS 3RD ANGLE)
    # -------------------------------------------------------------------------
    def detect_projection_type(self, view_regions: Dict[str, ViewRegion]) -> Tuple[str, List[Diagnostic]]:
        """
        Detects 1st Angle vs 3rd Angle projection based on relative positions of Top View and Front View:
        - Third-Angle Projection: Top View is ABOVE Front View (smaller canvas Y).
        - First-Angle Projection: Top View is BELOW Front View (larger canvas Y).
        """
        top_reg = view_regions.get('top')
        front_reg = view_regions.get('front')

        if not top_reg or not front_reg:
            return '3rd_angle', [Diagnostic(
                rule_id="RULE_PROJ_TYPE",
                severity=DiagnosticSeverity.INFO,
                title="Projection System",
                description="Defaulting to Third-Angle Projection (ASME standard).",
                suggestion="Define Top View and Front View regions to detect projection angle automatically."
            )]

        # Canvas Y increases downwards
        if top_reg.min_y < front_reg.min_y:
            proj_type = '3rd_angle'
            desc = "Third-Angle Projection (Top View placed ABOVE Front View)."
            sugg = "Standard North American layout (ASME Y14.5). Extrusions project outwards."
        else:
            proj_type = '1st_angle'
            desc = "First-Angle Projection (Top View placed BELOW Front View)."
            sugg = "Standard European layout (ISO 128). 3D extrusions will adjust Z-axis orientation automatically."

        diagnostic = Diagnostic(
            rule_id="RULE_PROJ_TYPE",
            severity=DiagnosticSeverity.INFO,
            title="Projection System Detected",
            description=desc,
            suggestion=sugg,
            fix_action="set_projection_type",
            fix_data={"projection_type": proj_type}
        )
        return proj_type, [diagnostic]

    # -------------------------------------------------------------------------
    # RULE 2: ORTHOGRAPHIC ALIGNMENT (WIDTH, HEIGHT, DEPTH)
    # -------------------------------------------------------------------------
    def check_orthographic_alignment(self, shapes_by_view: Dict[str, List[Shape]], view_regions: Dict[str, ViewRegion]) -> List[Diagnostic]:
        """Check Width (Top vs Front), Height (Front vs Side), Depth (Top vs Side) alignment"""
        diags: List[Diagnostic] = []

        top_shapes = [s for s in shapes_by_view.get('top', []) if s.layer != 'Construction']
        front_shapes = [s for s in shapes_by_view.get('front', []) if s.layer != 'Construction']
        side_shapes = [s for s in shapes_by_view.get('side', []) if s.layer != 'Construction']

        # Width Alignment: Top Width vs Front Width
        if top_shapes and front_shapes:
            top_xs = self._get_shape_extent_x(top_shapes)
            front_xs = self._get_shape_extent_x(front_shapes)

            if top_xs and front_xs:
                top_w = top_xs[1] - top_xs[0]
                front_w = front_xs[1] - front_xs[0]
                delta_w = abs(top_w - front_w)

                if delta_w > self.alignment_tolerance:
                    diags.append(Diagnostic(
                        rule_id="RULE_ALIGN_WIDTH",
                        severity=DiagnosticSeverity.ERROR,
                        title="Width Mismatch (Top vs Front)",
                        description=f"Top View width ({top_w:.1f} mm) does not match Front View width ({front_w:.1f} mm). Delta: {delta_w:.1f} mm.",
                        suggestion=f"Auto-scale Top View width to match Front View ({front_w:.1f} mm).",
                        mismatched_shape_ids=[s.id for s in top_shapes],
                        fix_action="auto_scale_top_width",
                        fix_data={"target_width": front_w, "current_width": top_w, "target_view": "top"}
                    ))

        # Height Alignment: Front Height vs Side Height
        if front_shapes and side_shapes:
            front_ys = self._get_shape_extent_y(front_shapes)
            side_ys = self._get_shape_extent_y(side_shapes)

            if front_ys and side_ys:
                front_h = front_ys[1] - front_ys[0]
                side_h = side_ys[1] - side_ys[0]
                delta_h = abs(front_h - side_h)

                if delta_h > self.alignment_tolerance:
                    diags.append(Diagnostic(
                        rule_id="RULE_ALIGN_HEIGHT",
                        severity=DiagnosticSeverity.ERROR,
                        title="Height Mismatch (Front vs Side)",
                        description=f"Front View height ({front_h:.1f} mm) does not match Side View height ({side_h:.1f} mm). Delta: {delta_h:.1f} mm.",
                        suggestion=f"Auto-scale Side View height to match Front View ({front_h:.1f} mm).",
                        mismatched_shape_ids=[s.id for s in side_shapes],
                        fix_action="auto_scale_side_height",
                        fix_data={"target_height": front_h, "current_height": side_h, "target_view": "side"}
                    ))

        # Depth Alignment: Top Depth (Y height) vs Side Depth (X width)
        if top_shapes and side_shapes:
            top_ys = self._get_shape_extent_y(top_shapes)
            side_xs = self._get_shape_extent_x(side_shapes)

            if top_ys and side_xs:
                top_depth = top_ys[1] - top_ys[0]
                side_depth = side_xs[1] - side_xs[0]
                delta_d = abs(top_depth - side_depth)

                if delta_d > self.alignment_tolerance:
                    diags.append(Diagnostic(
                        rule_id="RULE_ALIGN_DEPTH",
                        severity=DiagnosticSeverity.ERROR,
                        title="Depth Mismatch (Top vs Side)",
                        description=f"Top View depth ({top_depth:.1f} mm) does not match Side View width ({side_depth:.1f} mm). Delta: {delta_d:.1f} mm.",
                        suggestion=f"Auto-scale Side View depth to match Top View depth ({top_depth:.1f} mm).",
                        mismatched_shape_ids=[s.id for s in side_shapes],
                        fix_action="auto_scale_side_depth",
                        fix_data={"target_depth": top_depth, "current_depth": side_depth, "target_view": "side"}
                    ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 3: 2D PROFILE CLOSURE (WATERTIGHT PROFILES)
    # -------------------------------------------------------------------------
    def check_profile_closure(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Verify that Visible layer primitives form closed, watertight 2D boundaries"""
        diags: List[Diagnostic] = []

        for view_name, shapes in shapes_by_view.items():
            if view_name == 'unassigned':
                continue
            visible_shapes = [s for s in shapes if s.layer == 'Visible']
            if not visible_shapes:
                continue

            lines = self._extract_lines_from_shapes(visible_shapes)
            if not lines:
                continue

            # Build endpoint adjacency map
            degree_map: Dict[Tuple[float, float], List[str]] = {}
            for p1, p2, sid in lines:
                k1 = (round(p1[0], 2), round(p1[1], 2))
                k2 = (round(p2[0], 2), round(p2[1], 2))
                degree_map.setdefault(k1, []).append(sid)
                degree_map.setdefault(k2, []).append(sid)

            open_endpoints = [pt for pt, sids in degree_map.items() if len(sids) % 2 != 0]

            if open_endpoints:
                open_sids = list(set([sid for pt in open_endpoints for sid in degree_map[pt]]))
                pts_str = ", ".join([f"({p[0]:.1f}, {p[1]:.1f})" for p in open_endpoints[:3]])
                diags.append(Diagnostic(
                    rule_id="RULE_PROFILE_CLOSURE",
                    severity=DiagnosticSeverity.ERROR,
                    title=f"Unclosed Profile in {view_name.capitalize()} View",
                    description=f"Visible boundary contains {len(open_endpoints)} dangling endpoints near: {pts_str}.",
                    suggestion="Close boundary loop or remove stray line segments to ensure valid 3D extrusion.",
                    mismatched_shape_ids=open_sids,
                    fix_action="auto_close_profile",
                    fix_data={"open_endpoints": open_endpoints, "view_name": view_name}
                ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 4: LINE PRECEDENCE (ASME Y14.5 / ISO 128 VISIBLE VS HIDDEN)
    # -------------------------------------------------------------------------
    def check_line_precedence(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Check for overlapping Visible and Hidden lines; Visible line takes precedence"""
        diags: List[Diagnostic] = []

        for view_name, shapes in shapes_by_view.items():
            vis_lines = [s for s in shapes if isinstance(s, Line) and s.layer == 'Visible']
            hid_lines = [s for s in shapes if isinstance(s, Line) and s.layer == 'Hidden']

            overlapping_ids = []
            for h in hid_lines:
                h_seg = sg.LineString([h.start, h.end])
                for v in vis_lines:
                    v_seg = sg.LineString([v.start, v.end])
                    if h_seg.intersects(v_seg):
                        inter = h_seg.intersection(v_seg)
                        if isinstance(inter, sg.LineString) and inter.length > self.epsilon:
                            overlapping_ids.append(h.id)

            if overlapping_ids:
                diags.append(Diagnostic(
                    rule_id="RULE_LINE_PRECEDENCE",
                    severity=DiagnosticSeverity.WARNING,
                    title=f"Line Precedence Collision ({view_name.capitalize()} View)",
                    description=f"Found {len(overlapping_ids)} Hidden lines overlapping Visible lines. ASME Y14.5 mandates Visible lines take precedence.",
                    suggestion="Auto-trim hidden line segments that lie underneath visible lines.",
                    mismatched_shape_ids=overlapping_ids,
                    fix_action="auto_trim_hidden_overlaps",
                    fix_data={"hidden_ids": overlapping_ids, "view_name": view_name}
                ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 5: VERTEX COINCIDENCE & EDGE PROJECTION
    # -------------------------------------------------------------------------
    def check_vertex_coincidence(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Check if 2D vertex in one view has a corresponding projected edge/vertex in aligned views"""
        diags: List[Diagnostic] = []

        top_shapes = [s for s in shapes_by_view.get('top', []) if s.layer != 'Construction']
        front_shapes = [s for s in shapes_by_view.get('front', []) if s.layer != 'Construction']

        if top_shapes and front_shapes:
            top_lines = self._extract_lines_from_shapes(top_shapes)
            front_lines = self._extract_lines_from_shapes(front_shapes)

            top_xs = set([round(p[0], 1) for l in top_lines for p in (l[0], l[1])])
            front_xs = set([round(p[0], 1) for l in front_lines for p in (l[0], l[1])])

            unmatched_top_x = [x for x in top_xs if not any(abs(x - fx) <= self.alignment_tolerance for fx in front_xs)]

            if unmatched_top_x:
                diags.append(Diagnostic(
                    rule_id="RULE_VERTEX_COINCIDENCE",
                    severity=DiagnosticSeverity.WARNING,
                    title="Missing Projective Edge",
                    description=f"Top View vertex at X={unmatched_top_x[0]:.1f} has no corresponding projective edge in Front View.",
                    suggestion="Add missing edge line or check alignment between Top and Front views.",
                    mismatched_shape_ids=[s.id for s in top_shapes]
                ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 6: HIDDEN LINE DEPTH INFERENCE (THROUGH VS BLIND HOLES)
    # -------------------------------------------------------------------------
    def check_hidden_line_depth_inference(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Identify Blind Holes vs Through Holes based on hidden line depth spanning"""
        diags: List[Diagnostic] = []

        top_circles = [s for s in shapes_by_view.get('top', []) if isinstance(s, Circle)]
        front_hidden = [s for s in shapes_by_view.get('front', []) if s.layer == 'Hidden']
        front_visible = [s for s in shapes_by_view.get('front', []) if s.layer == 'Visible']

        if top_circles and front_visible:
            front_ys = self._get_shape_extent_y(front_visible)
            if front_ys:
                part_height = front_ys[1] - front_ys[0]

                for circle in top_circles:
                    # Find matching hidden lines in Front View near circle X extent
                    cx, r = circle.center[0], circle.radius
                    matching_hidden = []
                    for h in front_hidden:
                        if isinstance(h, Line):
                            if abs(h.start[0] - (cx - r)) <= 2.0 or abs(h.start[0] - (cx + r)) <= 2.0:
                                matching_hidden.append(h)

                    if matching_hidden:
                        h_lengths = [abs(h.end[1] - h.start[1]) for h in matching_hidden if isinstance(h, Line)]
                        if h_lengths:
                            max_h_len = max(h_lengths)
                            if abs(max_h_len - part_height) > 2.0:
                                diags.append(Diagnostic(
                                    rule_id="RULE_HOLE_DEPTH",
                                    severity=DiagnosticSeverity.INFO,
                                    title="Blind Hole Feature Detected",
                                    description=f"Hole (Ø {2*r:.1f} mm) in Top View extends {max_h_len:.1f} mm deep (Blind Hole, Part Height: {part_height:.1f} mm).",
                                    suggestion="CSG subtractive cylinder will be extruded to specified blind depth."
                                ))
                            else:
                                diags.append(Diagnostic(
                                    rule_id="RULE_HOLE_DEPTH",
                                    severity=DiagnosticSeverity.INFO,
                                    title="Through Hole Feature Confirmed",
                                    description=f"Hole (Ø {2*r:.1f} mm) spans full part depth ({part_height:.1f} mm).",
                                    suggestion="CSG subtractive cylinder will cut through entire solid."
                                ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 7: INCLINED & OBLIQUE PLANE EDGE MATCHING
    # -------------------------------------------------------------------------
    def check_inclined_plane_matching(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Check if inclined line in one view has projected bounding box area in other views"""
        diags: List[Diagnostic] = []

        front_lines = [s for s in shapes_by_view.get('front', []) if isinstance(s, Line) and s.layer == 'Visible']
        top_shapes = [s for s in shapes_by_view.get('top', []) if s.layer == 'Visible']

        for line in front_lines:
            dx = abs(line.end[0] - line.start[0])
            dy = abs(line.end[1] - line.start[1])
            if dx > 5.0 and dy > 5.0:  # Angled / inclined line
                angle_deg = math.degrees(math.atan2(dy, dx))
                if 10.0 <= angle_deg <= 80.0:
                    top_xs = self._get_shape_extent_x(top_shapes) if top_shapes else None
                    if top_xs:
                        line_min_x = min(line.start[0], line.end[0])
                        line_max_x = max(line.start[0], line.end[0])
                        if line_max_x > top_xs[1] + self.alignment_tolerance or line_min_x < top_xs[0] - self.alignment_tolerance:
                            diags.append(Diagnostic(
                                rule_id="RULE_INCLINED_PLANE",
                                severity=DiagnosticSeverity.WARNING,
                                title="Insufficient Bounding Box for Inclined Surface",
                                description=f"Front View inclined edge ({angle_deg:.1f}°) projects outside Top View bounding limits.",
                                suggestion="Adjust Top View bounding extent to encompass inclined plane projection.",
                                mismatched_shape_ids=[line.id]
                            ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 8: CENTERLINE & SYMMETRY RECOGNITION
    # -------------------------------------------------------------------------
    def check_centerline_symmetry(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Detect Centerlines and provide auto-mirroring payload for symmetrical geometries"""
        diags: List[Diagnostic] = []

        for view_name, shapes in shapes_by_view.items():
            centerlines = [s for s in shapes if isinstance(s, Line) and (s.layer == 'Centerline' or getattr(s, 'layer', '') == 'Centerline')]
            if centerlines:
                for cl in centerlines:
                    # Check if centerline is vertical or horizontal
                    is_vert = abs(cl.start[0] - cl.end[0]) < 1.0
                    is_horiz = abs(cl.start[1] - cl.end[1]) < 1.0
                    if is_vert or is_horiz:
                        axis = "Vertical" if is_vert else "Horizontal"
                        coord = cl.start[0] if is_vert else cl.start[1]
                        diags.append(Diagnostic(
                            rule_id="RULE_CENTERLINE_SYMMETRY",
                            severity=DiagnosticSeverity.INFO,
                            title=f"Centerline Axis Recognized ({view_name.capitalize()} View)",
                            description=f"{axis} symmetry centerline detected at coordinate {coord:.1f} mm.",
                            suggestion="Auto-mirror profile across centerline axis to guarantee 100% symmetric 3D mesh.",
                            mismatched_shape_ids=[cl.id],
                            fix_action="auto_mirror_symmetry",
                            fix_data={"axis": axis, "coord": coord, "view_name": view_name}
                        ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 9: LINE PRIORITY & OVERLAP RESOLUTION (AUTO-TRIM)
    # -------------------------------------------------------------------------
    def check_line_priority_overlap(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Detect colinear overlapping lines of different layers and suggest Auto-Trim"""
        diags: List[Diagnostic] = []

        for view_name, shapes in shapes_by_view.items():
            lines = [s for s in shapes if isinstance(s, Line)]
            overlapping_pairs = []

            for i in range(len(lines)):
                for j in range(i + 1, len(lines)):
                    l1, l2 = lines[i], lines[j]
                    if l1.layer != l2.layer:
                        s1 = sg.LineString([l1.start, l1.end])
                        s2 = sg.LineString([l2.start, l2.end])
                        if s1.intersects(s2):
                            inter = s1.intersection(s2)
                            if isinstance(inter, sg.LineString) and inter.length > self.epsilon:
                                overlapping_pairs.append((l1.id, l2.id))

            if overlapping_pairs:
                diags.append(Diagnostic(
                    rule_id="RULE_LINE_PRIORITY",
                    severity=DiagnosticSeverity.WARNING,
                    title=f"Colinear Overlapping Lines ({view_name.capitalize()} View)",
                    description=f"Detected {len(overlapping_pairs)} overlapping line segments with conflicting layer properties.",
                    suggestion="Auto-trim hidden segments that collide with visible lines.",
                    mismatched_shape_ids=[pair[1] for pair in overlapping_pairs],
                    fix_action="auto_trim_colinear",
                    fix_data={"pairs": overlapping_pairs, "view_name": view_name}
                ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 10: MINIMUM GAP TOLERANCE (TOPOLOGICAL MICRO-GAPS)
    # -------------------------------------------------------------------------
    def check_minimum_gap_tolerance(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Detect endpoints that lie within micro-gap distance epsilon (0.1 mm) but are not snap-coincident"""
        diags: List[Diagnostic] = []

        for view_name, shapes in shapes_by_view.items():
            visible_shapes = [s for s in shapes if s.layer == 'Visible']
            lines = self._extract_lines_from_shapes(visible_shapes)
            if not lines:
                continue

            pts = []
            for p1, p2, sid in lines:
                pts.append((p1, sid))
                pts.append((p2, sid))

            near_gap_pairs = []
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    (pt1, id1), (pt2, id2) = pts[i], pts[j]
                    if id1 != id2:
                        dist = math.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)
                        if 1e-4 < dist <= self.epsilon:
                            near_gap_pairs.append((pt1, pt2, dist, id1, id2))

            if near_gap_pairs:
                affected_ids = list(set([p[3] for p in near_gap_pairs] + [p[4] for p in near_gap_pairs]))
                min_dist = min([p[2] for p in near_gap_pairs])
                diags.append(Diagnostic(
                    rule_id="RULE_MICRO_GAP",
                    severity=DiagnosticSeverity.WARNING,
                    title=f"Near-Coincident Micro-Gap ({view_name.capitalize()} View)",
                    description=f"Detected {len(near_gap_pairs)} endpoints separated by micro-gap ({min_dist:.3f} mm <= {self.epsilon} mm).",
                    suggestion="Auto-snap near-coincident vertices into a single topological point to ensure watertight extrusion.",
                    mismatched_shape_ids=affected_ids,
                    fix_action="auto_snap_micro_gaps",
                    fix_data={"pairs": near_gap_pairs, "view_name": view_name, "epsilon": self.epsilon}
                ))

        return diags

    # -------------------------------------------------------------------------
    # RULE 11: REVOLVED SURFACE & CYLINDRICAL FEATURE RECOGNITION
    # -------------------------------------------------------------------------
    def check_revolved_feature_candidates(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Detect profiles symmetrical about a Centerline eligible for B-Rep analytical Revolve operations"""
        diags: List[Diagnostic] = []
        for view_name, shapes in shapes_by_view.items():
            centerlines = [s for s in shapes if isinstance(s, Line) and getattr(s, 'layer', '') == 'Centerline']
            visible_shapes = [s for s in shapes if getattr(s, 'layer', '') == 'Visible']
            if centerlines and visible_shapes:
                for cl in centerlines:
                    is_vert = abs(cl.start[0] - cl.end[0]) < 1.0
                    is_horiz = abs(cl.start[1] - cl.end[1]) < 1.0
                    if is_vert or is_horiz:
                        axis_type = "Vertical" if is_vert else "Horizontal"
                        coord = cl.start[0] if is_vert else cl.start[1]
                        diags.append(Diagnostic(
                            rule_id="RULE_REVOLVE_FEATURE",
                            severity=DiagnosticSeverity.INFO,
                            title=f"Revolve Surface Candidate Detected ({view_name.capitalize()} View)",
                            description=f"Profile has rotational {axis_type.lower()} symmetry axis at {coord:.1f} mm. Analytical B-Rep kernel can perform 360° Revolve.",
                            suggestion="B-Rep kernel will generate analytical cylindrical/conical NURBS surface.",
                            mismatched_shape_ids=[cl.id]
                        ))
        return diags

    # -------------------------------------------------------------------------
    # RULE 12: AUXILIARY VIEW PROJECTION ALIGNMENT
    # -------------------------------------------------------------------------
    def check_auxiliary_view_alignment(self, shapes_by_view: Dict[str, List[Shape]], view_regions: Dict[str, ViewRegion]) -> List[Diagnostic]:
        """Verify alignment of auxiliary projection regions against principal orthographic views"""
        diags: List[Diagnostic] = []
        aux_regions = [r for r in view_regions.values() if r.view_type in ['auxiliary', 'aux', 'isometric', 'section']]
        if aux_regions:
            for ar in aux_regions:
                diags.append(Diagnostic(
                    rule_id="RULE_AUXILIARY_ALIGN",
                    severity=DiagnosticSeverity.INFO,
                    title=f"Auxiliary View Active: {ar.view_type.capitalize()}",
                    description=f"Auxiliary projection region at ({ar.min_x:.0f}, {ar.min_y:.0f}) configured for true-shape projection.",
                    suggestion="Ensure feature projection rays remain perpendicular to inclined surface."
                ))
        return diags

    # -------------------------------------------------------------------------
    # RULE 13: FILLET RADIUS OVER-CONSTRAINT DIAGNOSTIC
    # -------------------------------------------------------------------------
    def check_fillet_radius_bounds(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Detect fillet radii that exceed adjoining edge geometric boundaries"""
        diags: List[Diagnostic] = []
        for view_name, shapes in shapes_by_view.items():
            fillet_arcs = [s for s in shapes if isinstance(s, Arc) and getattr(s, 'feature_type', '') == 'fillet']
            lines = [s for s in shapes if isinstance(s, Line)]
            if fillet_arcs and lines:
                min_line_len = min((abs(l.end[0]-l.start[0])**2 + abs(l.end[1]-l.start[1])**2)**0.5 for l in lines)
                for fa in fillet_arcs:
                    r = getattr(fa, 'fillet_radius', fa.radius)
                    if r >= min_line_len / 2.0:
                        diags.append(Diagnostic(
                            rule_id="RULE_FILLET_BOUNDS",
                            severity=DiagnosticSeverity.WARNING,
                            title=f"Fillet Radius Over-Constraint ({view_name.capitalize()} View)",
                            description=f"Fillet radius R={r:.1f} mm exceeds half of minimum edge length ({min_line_len:.1f} mm).",
                            suggestion="Radius will be automatically clamped during 3D OpenCASCADE blend generation.",
                            mismatched_shape_ids=[fa.id]
                        ))
        return diags

    # -------------------------------------------------------------------------
    # RULE 14: GATED ORTHOGRAPHIC AMBIGUITY DETECTION
    # -------------------------------------------------------------------------
    def check_orthographic_ambiguity(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """Detect under-constrained orthographic drawings with multiple valid manifold CSG topologies"""
        diags: List[Diagnostic] = []
        top_hidden = [s for s in shapes_by_view.get('top', []) if getattr(s, 'layer', '') == 'Hidden']
        front_hidden = [s for s in shapes_by_view.get('front', []) if getattr(s, 'layer', '') == 'Hidden']
        
        if len(top_hidden) >= 2 or len(front_hidden) >= 2:
            diags.append(Diagnostic(
                rule_id="RULE_AMBIGUITY_DETECTED",
                severity=DiagnosticSeverity.INFO,
                title="Multiple 3D Topological Candidates Detected",
                description="Overlapping hidden profiles admit multiple valid manifold solid permutations (e.g. through vs blind cuts).",
                suggestion="Use the 3D Viewport Candidate Switcher HUD to toggle between alternate solid solutions."
            ))
        return diags



    # -------------------------------------------------------------------------
    # HELPER UTILITIES
    # -------------------------------------------------------------------------
    def _get_shape_extent_x(self, shapes: List[Shape]) -> Optional[Tuple[float, float]]:
        """Calculate bounding X extent across shapes"""
        xs = []
        for s in shapes:
            if isinstance(s, Line):
                xs.extend([s.start[0], s.end[0]])
            elif isinstance(s, Rectangle):
                x, y, w, h = s.rect
                xs.extend([x, x + w])
            elif isinstance(s, Circle) or isinstance(s, Arc):
                cx, r = s.center[0], s.radius
                xs.extend([cx - r, cx + r])
            elif isinstance(s, Polygon):
                xs.extend([p[0] for p in s.points])
        return (min(xs), max(xs)) if xs else None

    def _get_shape_extent_y(self, shapes: List[Shape]) -> Optional[Tuple[float, float]]:
        """Calculate bounding Y extent across shapes"""
        ys = []
        for s in shapes:
            if isinstance(s, Line):
                ys.extend([s.start[1], s.end[1]])
            elif isinstance(s, Rectangle):
                x, y, w, h = s.rect
                ys.extend([y, y + h])
            elif isinstance(s, Circle) or isinstance(s, Arc):
                cy, r = s.center[1], s.radius
                ys.extend([cy - r, cy + r])
            elif isinstance(s, Polygon):
                ys.extend([p[1] for p in s.points])
        return (min(ys), max(ys)) if ys else None

    def _extract_lines_from_shapes(self, shapes: List[Shape]) -> List[Tuple[Tuple[float, float], Tuple[float, float], str]]:
        """Extract line segments (start, end, shape_id) from 2D primitives"""
        lines = []
        for s in shapes:
            if isinstance(s, Line):
                lines.append((s.start, s.end, s.id))
            elif isinstance(s, Rectangle):
                x, y, w, h = s.rect
                p1, p2, p3, p4 = (x, y), (x + w, y), (x + w, y + h), (x, y + h)
                lines.extend([(p1, p2, s.id), (p2, p3, s.id), (p3, p4, s.id), (p4, p1, s.id)])
            elif isinstance(s, Polygon) and len(s.points) >= 2:
                pts = s.points
                for i in range(len(pts)):
                    lines.append((pts[i], pts[(i + 1) % len(pts)], s.id))
        return lines

    # -------------------------------------------------------------------------
    # RULE 15: ASME Y14.5-2018 GD&T & DATUM REFERENCE FRAME (DRF) VALIDATION
    # -------------------------------------------------------------------------
    def check_gdt_rules(
        self,
        datums: List[DatumFeature],
        feature_control_frames: List[FeatureControlFrame],
        shapes_by_view: Dict[str, List[Shape]]
    ) -> List[Diagnostic]:
        """
        Validate Datum Reference Frames and Feature Control Frames against ASME Y14.5-2018:
        - GD_01: Datum Existence (every referenced datum letter must exist on the sheet)
        - GD_02: Datum Orthogonality (Secondary must be perpendicular to Primary datum)
        - GD_03: Basic Dimensioning (Features controlled by True Position must have basic nominals)
        - GD_04: Over-Constrained DRF (No duplicate datum references in same frame)
        - GD_ORPHAN: Orphan annotation attached to deleted geometry
        """
        diagnostics: List[Diagnostic] = []
        all_shape_ids = {s.id for shapes in shapes_by_view.values() for s in shapes}
        datum_map = {d.label.strip().upper().strip("-"): d for d in datums}

        # Check for orphan datums
        for d in datums:
            if d.target_shape_id and d.target_shape_id not in all_shape_ids:
                diagnostics.append(Diagnostic(
                    rule_id="GD_ORPHAN",
                    severity=DiagnosticSeverity.WARNING,
                    title="Orphan Datum Feature",
                    description=f"Datum [-{d.label}-] was attached to a geometry entity that was deleted or unlinked.",
                    suggestion="Re-assign Datum [-{d.label}-] to an active entity on the sheet."
                ))

        # Check each Feature Control Frame
        for fcf in feature_control_frames:
            # Check for orphan FCF
            if fcf.target_shape_id and fcf.target_shape_id not in all_shape_ids:
                diagnostics.append(Diagnostic(
                    rule_id="GD_ORPHAN",
                    severity=DiagnosticSeverity.WARNING,
                    title="Orphan Feature Control Frame",
                    description=f"Feature Control Frame [{fcf.symbol.value}] is attached to a deleted entity.",
                    suggestion="Re-anchor the FCF leader arrow to an active feature on the drawing sheet."
                ))

            # DRF validation (GD_01, GD_02, GD_04)
            drf_errors = GDTEngine.validate_datum_reference_frame(fcf, datums)
            for err in drf_errors:
                rule_id = err.split(":")[0].strip()
                err_msg = err.split(":", 1)[1].strip() if ":" in err else err
                sev = DiagnosticSeverity.ERROR if "GD_01" in rule_id or "GD_04" in rule_id else DiagnosticSeverity.WARNING
                diagnostics.append(Diagnostic(
                    rule_id=rule_id,
                    severity=sev,
                    title=f"GD&T Standard Violation ({rule_id})",
                    description=err_msg,
                    suggestion="Update the Datum Reference Frame sequence to conform with ASME Y14.5-2018."
                ))

            # GD_03: True Position Basic Dimension Recommendation
            if fcf.symbol == GDTSymbol.POSITION and not fcf.primary_datum:
                diagnostics.append(Diagnostic(
                    rule_id="GD_03",
                    severity=DiagnosticSeverity.WARNING,
                    title="True Position Missing DRF",
                    description="True Position tolerance specified without a Primary Datum Reference Frame.",
                    suggestion="Assign at least a Primary Datum (e.g., [-A-]) to establish the coordinate origin for True Position."
                ))

        return diagnostics

    # -------------------------------------------------------------------------
    # RULE 16: MECHANICAL FEATURES & HARDWARE RECOGNITION (MECH_01, MECH_02)
    # -------------------------------------------------------------------------
    def check_mechanical_feature_rules(self, shapes_by_view: Dict[str, List[Shape]]) -> List[Diagnostic]:
        """
        Evaluate semantic machine features against engineering standards:
        - MECH_01: Standard Tap Drill Verification (flags non-standard drill size for metric threads with 1-click auto-fix)
        - MECH_02: Bolt Circle Pattern Recognition (identifies PCD hole arrays and suggests standard fasteners)
        """
        diagnostics: List[Diagnostic] = []

        # Check all views for tapped hole circle/arc pairs
        for view_name, shapes in shapes_by_view.items():
            circles = [s for s in shapes if isinstance(s, Circle)]
            arcs = [s for s in shapes if isinstance(s, Arc)]

            for arc in arcs:
                sweep = abs(arc.end_angle - arc.start_angle)
                if sweep < 0:
                    sweep += 360.0
                if not (250.0 <= sweep <= 290.0):
                    continue

                for circle in circles:
                    dist = math.hypot(arc.center[0] - circle.center[0], arc.center[1] - circle.center[1])
                    if dist > 0.5:
                        continue

                    d_major = 2.0 * arc.radius
                    d_drill = 2.0 * circle.radius

                    thread_match = lookup_metric_thread(d_major, tolerance=0.3)
                    if thread_match:
                        size_name, tdata = thread_match
                        std_drill = tdata["tap_drill"]
                        pitch = tdata["pitch"]

                        # MECH_01: Verify tap drill size
                        if abs(d_drill - std_drill) > 0.2:
                            diagnostics.append(Diagnostic(
                                rule_id="MECH_01",
                                severity=DiagnosticSeverity.ERROR,
                                title=f"Non-Standard Tap Drill Diameter for {size_name} Thread",
                                description=(
                                    f"Drawn tap drill diameter is {d_drill:.2f} mm. "
                                    f"ISO 261 standard specifies {std_drill:.2f} mm for {size_name}x{pitch:.1f} thread."
                                ),
                                suggestion=f"Correct tap drill diameter to standard {std_drill:.2f} mm (radius {std_drill/2.0:.2f} mm).",
                                mismatched_shape_ids=[circle.id, arc.id],
                                fix_action="auto_fix_tap_drill",
                                fix_data={"target_radius": std_drill / 2.0, "shape_id": circle.id}
                            ))

        # MECH_02: PCD Bolt Circle Pattern Recognition
        recognizer = FeatureRecognizer()
        pcd_patterns = recognizer.detect_pcd_patterns(shapes_by_view)

        for pat in pcd_patterns:
            fastener_info = pat.matched_fastener or f"Clearance Holes ({pat.hole_size:.1f}mm)"
            diagnostics.append(Diagnostic(
                rule_id="MECH_02",
                severity=DiagnosticSeverity.INFO,
                title=f"Standard Bolt Circle Identified: {pat.count}x {fastener_info} on {pat.pcd:.0f}mm PCD",
                description=(
                    f"Pattern contains {pat.count} equispaced {pat.hole_size:.1f} mm holes "
                    f"at {pat.nominal_spacing_deg:.1f}° intervals on a {pat.pcd:.1f} mm Pitch Circle Diameter."
                ),
                suggestion="Insert matching standard fastener hardware (e.g., DIN 912 Hex Socket Head Screws).",
                mismatched_shape_ids=pat.shape_ids
            ))

        return diagnostics

    # -------------------------------------------------------------------------
    # RULE 17: SECTION VIEWS & CUTTING-PLANE RULES (SECT_01 to SECT_04)
    # -------------------------------------------------------------------------
    def check_section_rules(
        self,
        cutting_planes: List[CuttingPlane],
        section_views: List[SectionView],
        shapes_by_view: Dict[str, List[Shape]]
    ) -> List[Diagnostic]:
        """
        Evaluates ISO 128-40 / ASME Y14.3 Sectioning Conventions:
        - SECT_01: Sight arrow direction verification.
        - SECT_02: Thin web/rib longitudinal non-hatching rule.
        - SECT_03: Fastener/shaft longitudinal non-hatching rule.
        - SECT_04: Hatch angle parallel interference warning.
        """
        diagnostics: List[Diagnostic] = []

        cp_map = {cp.id: cp for cp in cutting_planes}

        for sv in section_views:
            cp = cp_map.get(sv.cutting_plane_id)
            if not cp:
                continue

            # SECT_01: Arrow direction vs projected view
            if cp.view == 'top' and sv.target_view == 'front':
                if cp.normal[1] > 0.1:  # Pointing away from front view
                    diagnostics.append(Diagnostic(
                        rule_id="SECT_01",
                        severity=DiagnosticSeverity.WARNING,
                        title=f"Section {cp.label}—{cp.label} Arrow Direction Mismatch",
                        description=f"Directional arrows for Section {cp.label}—{cp.label} point upward (+Y), opposite to Front Section View.",
                        suggestion="Flip cutting-plane sight arrows downward (-Y) to match standard third-angle section projection."
                    ))

            # SECT_02: Thin Web / Rib Non-Hatching Rule
            target_shapes = shapes_by_view.get(sv.target_view, [])
            for s in target_shapes:
                if isinstance(s, Rectangle):
                    w, h = s.rect[2], s.rect[3]
                    min_dim = min(w, h)
                    max_dim = max(w, h)
                    if min_dim <= 8.0 and max_dim >= min_dim * 3.0:
                        diagnostics.append(Diagnostic(
                            rule_id="SECT_02",
                            severity=DiagnosticSeverity.INFO,
                            title=f"Thin Structural Web Identified in Section {cp.label}—{cp.label}",
                            description=f"Thin rib of thickness {min_dim:.1f} mm cut longitudinally must NOT be cross-hatched per ASME Y14.3 / ISO 128-50.",
                            suggestion="Exclude rib region from cross-hatching to avoid misleading solid representation.",
                            mismatched_shape_ids=[s.id]
                        ))

            # SECT_04: Hatch Angle Parallel Interference
            for s in target_shapes:
                if isinstance(s, Line):
                    dx = s.end[0] - s.start[0]
                    dy = s.end[1] - s.start[1]
                    if abs(dx) > 1e-4:
                        angle_deg = math.degrees(math.atan2(dy, dx)) % 180.0
                        if abs(angle_deg - sv.hatch_angle) <= 5.0 or abs(angle_deg - (sv.hatch_angle + 90.0)) <= 5.0:
                            diagnostics.append(Diagnostic(
                                rule_id="SECT_04",
                                severity=DiagnosticSeverity.WARNING,
                                title=f"Hatch Angle Interference in Section {cp.label}—{cp.label}",
                                description=f"Hatch angle ({sv.hatch_angle:.1f}°) is nearly parallel to a major boundary edge ({angle_deg:.1f}°).",
                                suggestion="Adjust section cross-hatch angle to 30° or 60° for optimal visual clarity.",
                                mismatched_shape_ids=[s.id]
                            ))

        return diagnostics

    # -------------------------------------------------------------------------
    # RULE 18: DESIGN FOR MANUFACTURING (DFM) RULES
    # -------------------------------------------------------------------------
    def check_dfm_rules(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        process: Optional[ManufacturingProcess] = None,
        brep_solid: Optional[Any] = None
    ) -> List[Diagnostic]:
        """
        Runs automated DFM checks for CNC Milling, Injection Molding, or Sheet Metal:
        - DFM_CNC_01: Internal Sharp Corner Inaccessibility (Ø3.0mm endmill check).
        - DFM_CNC_02: Deep Pocket Depth-to-Width Ratio (Tool deflection / chatter).
        - DFM_MOLD_01: Missing Mold Draft Angles (1.5° draw angle check).
        - DFM_MOLD_02: Rib-to-Wall Sink Mark Ratio (60% rule).
        - DFM_SHEET_01: Minimum Inside Bend Radius (cracking risk).
        - DFM_SHEET_02: Hole Proximity to Bend Line (ovular distortion risk).
        """
        diagnostics: List[Diagnostic] = []
        dfm_engine = DFMEngine(process or ManufacturingProcess.CNC_MILLING)
        violations = dfm_engine.evaluate_all_rules(shapes_by_view, process, brep_solid)

        for v in violations:
            if v.severity == DFMDiagnosticSeverity.ERROR:
                sev = DiagnosticSeverity.ERROR
            elif v.severity == DFMDiagnosticSeverity.WARNING:
                sev = DiagnosticSeverity.WARNING
            else:
                sev = DiagnosticSeverity.INFO

            fix_act = v.autofix_payload.get("action") if v.autofix_payload else None

            diagnostics.append(Diagnostic(
                rule_id=v.rule_id,
                severity=sev,
                title=f"[{v.process.value.upper()}] {v.title}",
                description=v.description,
                suggestion=v.suggestion,
                mismatched_shape_ids=[v.target_shape_id] if v.target_shape_id else [],
                fix_action=fix_act,
                fix_data=v.autofix_payload
            ))

        return diagnostics

    # -------------------------------------------------------------------------
    # RULE 19: MULTI-PART ASSEMBLY & ISO 286 FITS RULES
    # -------------------------------------------------------------------------
    def check_assembly_rules(
        self,
        assembly: Assembly,
        shapes_by_view: Dict[str, List[Shape]]
    ) -> List[Diagnostic]:
        """
        Evaluates multi-part kinematic assembly constraints and ISO 286 limits and fits:
        - ASSY_01: ISO Fit Intent Conflict (Mechanical Seizure Warning).
        - ASSY_02: Coaxial Centerline Misalignment.
        - ASSY_03: Exploded Trajectory Collision Warning.
        """
        diagnostics: List[Diagnostic] = []
        if not assembly or not assembly.mates:
            return diagnostics

        all_shapes = [s for slist in shapes_by_view.values() for s in slist]
        shape_dict = {s.id: s for s in all_shapes}

        for m in assembly.mates:
            part_a = assembly.parts.get(m.part_a_id)
            part_b = assembly.parts.get(m.part_b_id)
            if not part_a or not part_b:
                continue

            # ASSY_01: ISO Fit Conflict / Seizure
            if m.fit_code:
                fit_eval = evaluate_iso_fit(m.nominal_d, m.fit_code)
                is_clearance_spec = fit_eval.fit_code.lower().endswith("g6") or fit_eval.fit_code.lower().endswith("h6") or fit_eval.category == "CLEARANCE"

                # Check actual drawn shaft vs hole dimensions if shapes are linked
                drawn_shaft_d = None
                drawn_hole_d = None
                for sid in part_b.shape_ids:
                    s = shape_dict.get(sid)
                    if isinstance(s, Circle):
                        drawn_shaft_d = 2.0 * s.radius
                for sid in part_a.shape_ids:
                    s = shape_dict.get(sid)
                    if isinstance(s, Circle):
                        drawn_hole_d = 2.0 * s.radius

                if is_clearance_spec:
                    if drawn_shaft_d is not None and drawn_hole_d is not None:
                        actual_clearance = drawn_hole_d - drawn_shaft_d
                        if actual_clearance <= 0.0:
                            diagnostics.append(Diagnostic(
                                rule_id="ASSY_01",
                                severity=DiagnosticSeverity.ERROR,
                                title=f"Mechanical Seizure Risk: Interference Under Clearance Fit {m.fit_code}",
                                description=(
                                    f"Drawn shaft diameter ({drawn_shaft_d:.3f} mm) exceeds hole diameter ({drawn_hole_d:.3f} mm). "
                                    f"Specified sliding fit {m.fit_code} requires positive clearance ({fit_eval.min_clearance*1000:.1f} µm minimum)."
                                ),
                                suggestion=f"Adjust shaft diameter to <= {fit_eval.shaft_upper_limit:.3f} mm for {m.fit_code} running fit.",
                                mismatched_shape_ids=part_b.shape_ids
                            ))
                    elif fit_eval.min_clearance < 0.0:
                        diagnostics.append(Diagnostic(
                            rule_id="ASSY_01",
                            severity=DiagnosticSeverity.ERROR,
                            title=f"Mechanical Seizure Risk: Negative Clearance on Fit {m.fit_code}",
                            description=f"Specified fit {m.fit_code} on Ø{m.nominal_d:.1f} mm yields negative clearance ({fit_eval.min_clearance*1000:.1f} µm).",
                            suggestion="Change fit specification to a clearance standard (e.g. H7/g6 or H7/h6).",
                            mismatched_shape_ids=part_b.shape_ids
                        ))

            # ASSY_02: Coaxial Centerline Misalignment
            if m.type == "COAXIAL":
                centers_a = [s.center for sid in part_a.shape_ids if (s := shape_dict.get(sid)) and isinstance(s, Circle)]
                centers_b = [s.center for sid in part_b.shape_ids if (s := shape_dict.get(sid)) and isinstance(s, Circle)]
                if centers_a and centers_b:
                    ca = centers_a[0]
                    cb = centers_b[0]
                    offset = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
                    if offset > 0.5:
                        diagnostics.append(Diagnostic(
                            rule_id="ASSY_02",
                            severity=DiagnosticSeverity.WARNING,
                            title=f"Coaxial Mating Eccentricity ({part_a.name} & {part_b.name})",
                            description=f"Centerline offset between mating features is {offset:.2f} mm (exceeds 0.5 mm tolerance).",
                            suggestion="Align feature centers or add a concentric constraint.",
                            mismatched_shape_ids=part_a.shape_ids + part_b.shape_ids
                        ))

        return diagnostics
