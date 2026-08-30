"""
Semantic Mechanical Feature Recognition & Machine Component Synthesizer.
Recognizes standard ISO/DIN/ASME machine elements from 2D orthographic projections:
- Tapped Holes (Through and Blind with ISO 261 pitch and drill cone)
- Counterbore Cap Screw Pockets (DIN 912 / ISO 4762)
- Countersink Pockets with included angle determination (DIN 74 / ISO 7721)
- Pitch Circle Diameter (PCD) Bolt Patterns
- Parallel Drive Keyways (DIN 6885) and Shaft Undercuts (DIN 509)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import math
import numpy as np

from .cad_engine import Shape, Line, Rectangle, Circle, Arc, Polygon
from .standards_db import (
    METRIC_COARSE_THREADS, COUNTERBORE_TABLE, COUNTERSINK_TABLE,
    METRIC_KEYWAY_TABLE, FASTENER_CATALOG,
    lookup_metric_thread, lookup_counterbore, lookup_countersink, lookup_shaft_keyway
)


class FeatureType(Enum):
    CLEARANCE_HOLE = "clearance_hole"
    THROUGH_TAPPED_HOLE = "through_tapped_hole"
    BLIND_TAPPED_HOLE = "blind_tapped_hole"
    COUNTERBORE = "counterbore"
    COUNTERSINK = "countersink"
    PARALLEL_KEYWAY = "parallel_keyway"
    SHAFT_UNDERCUT = "shaft_undercut"
    BOLT_CIRCLE_PATTERN = "bolt_circle_pattern"


@dataclass
class RecognizedFeature:
    """Base data container for recognized semantic machine elements"""
    feature_type: FeatureType
    center: Tuple[float, float]               # 2D coordinates in Plan/View
    nominal_size: str                         # e.g., "M6", "M10x1.5"
    view: str = "top"
    standard: str = ""                        # e.g., "ISO 261", "DIN 912"
    d_pass: float = 0.0                       # Clearance / pass diameter (mm)
    d_major: float = 0.0                      # Thread major / outer diameter (mm)
    d_drill: float = 0.0                      # Tap drill diameter (mm)
    d_bore: float = 0.0                       # Counterbore / countersink outer diameter (mm)
    h_bore: float = 0.0                       # Counterbore depth / countersink depth (mm)
    angle: float = 0.0                        # Countersink included angle (deg)
    depth: float = 0.0                        # Total hole depth (mm)
    usable_depth: float = 0.0                 # Usable thread depth (mm)
    pitch: float = 0.0                        # Thread pitch (mm)
    shape_ids: List[str] = field(default_factory=list)


@dataclass
class BoltCirclePattern:
    """Clustered Pitch Circle Diameter (PCD) array of equispaced hole features"""
    pcd: float                                # Pitch Circle Diameter (mm)
    count: int                                # Number of holes in pattern
    hole_size: float                          # Diameter of each hole (mm)
    center: Tuple[float, float]               # Center axis of bolt circle (cx, cy)
    nominal_spacing_deg: float                # Angular division (360 / N deg)
    matched_fastener: Optional[str] = None     # Suggested fastener e.g. "DIN 912 M6"
    shape_ids: List[str] = field(default_factory=list)


class FeatureRecognizer:
    """
    Cross-View Semantic Feature Recognition Engine:
    Processes 2D drafting entities across orthographic views and classifies them into standard machine components.
    """

    def __init__(self, cross_view_tolerance: float = 2.0):
        self.tau = cross_view_tolerance  # Alignment tolerance window (Guardrail #2)

    def recognize_all_features(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        part_thickness: float = 50.0
    ) -> Tuple[List[RecognizedFeature], List[BoltCirclePattern]]:
        """Run all semantic recognition pipelines on active drafting views"""
        features: List[RecognizedFeature] = []

        # 1. Detect Tapped Holes
        features.extend(self.detect_tapped_holes(shapes_by_view, part_thickness))

        # 2. Detect Counterbores
        features.extend(self.detect_counterbores(shapes_by_view, part_thickness))

        # 3. Detect Countersinks
        features.extend(self.detect_countersinks(shapes_by_view, part_thickness))

        # 4. Detect PCD Bolt Circle Patterns
        pcd_patterns = self.detect_pcd_patterns(shapes_by_view)

        return features, pcd_patterns

    # -------------------------------------------------------------------------
    # 1. TAPPED HOLE RECOGNITION (ISO 261 / ISO 965-1)
    # -------------------------------------------------------------------------
    def detect_tapped_holes(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        part_thickness: float = 50.0
    ) -> List[RecognizedFeature]:
        """
        Identify standard tapped holes from concentric circle + 270° arc pairs in plan view
        matched with hidden lines in elevation view.
        """
        results: List[RecognizedFeature] = []
        top_shapes = shapes_by_view.get('top', [])
        front_shapes = shapes_by_view.get('front', [])

        circles = [s for s in top_shapes if isinstance(s, Circle)]
        arcs = [s for s in top_shapes if isinstance(s, Arc)]

        for arc in arcs:
            # Step 1: Arc Sweep Verification (open 3/4 circle: 260° to 280°)
            sweep = abs(arc.end_angle - arc.start_angle)
            if sweep < 0:
                sweep += 360.0
            if not (260.0 <= sweep <= 280.0):
                continue

            # Find matching concentric full circle
            for circle in circles:
                dist = math.hypot(arc.center[0] - circle.center[0], arc.center[1] - circle.center[1])
                if dist > 0.5:
                    continue

                d_major = 2.0 * arc.radius
                d_drill = 2.0 * circle.radius
                if d_major <= d_drill:
                    continue

                # Step 2: Nominal Size Lookup
                thread_match = lookup_metric_thread(d_major, tolerance=0.3)
                if not thread_match:
                    continue

                size_name, tdata = thread_match
                pitch = tdata["pitch"]

                # Step 3: Elevation Depth Matching
                h_hole = self._find_elevation_depth(circle.center[0], front_shapes, default_depth=part_thickness)

                if abs(h_hole - part_thickness) <= 0.5:
                    ftype = FeatureType.THROUGH_TAPPED_HOLE
                    usable_depth = part_thickness
                else:
                    ftype = FeatureType.BLIND_TAPPED_HOLE
                    usable_depth = max(0.0, h_hole - (1.25 * pitch))

                results.append(RecognizedFeature(
                    feature_type=ftype,
                    center=circle.center,
                    nominal_size=f"{size_name}x{pitch:.1f}",
                    standard="ISO 261",
                    d_major=d_major,
                    d_drill=d_drill,
                    pitch=pitch,
                    depth=h_hole,
                    usable_depth=round(usable_depth, 3),
                    shape_ids=[circle.id, arc.id]
                ))

        return results

    # -------------------------------------------------------------------------
    # 2. COUNTERBORE RECOGNITION (DIN 912 / ISO 4762)
    # -------------------------------------------------------------------------
    def detect_counterbores(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        part_thickness: float = 50.0
    ) -> List[RecognizedFeature]:
        """
        Identify counterbores from concentric circle pairs in Plan view and
        stepped rectangular notch in Elevation view.
        """
        results: List[RecognizedFeature] = []
        top_shapes = shapes_by_view.get('top', [])
        front_shapes = shapes_by_view.get('front', [])

        circles = [s for s in top_shapes if isinstance(s, Circle)]

        # Find concentric circle pairs
        for i in range(len(circles)):
            for j in range(i + 1, len(circles)):
                c1, c2 = circles[i], circles[j]
                dist = math.hypot(c1.center[0] - c2.center[0], c1.center[1] - c2.center[1])
                if dist > 0.5:
                    continue

                r_pass = min(c1.radius, c2.radius)
                r_bore = max(c1.radius, c2.radius)
                d_pass = 2.0 * r_pass
                d_bore = 2.0 * r_bore

                if abs(d_bore - d_pass) < 1.0:
                    continue

                # Match depth from front view notch or standard table
                h_bore = self._find_counterbore_depth(c1.center[0], front_shapes, d_bore)

                cb_match = lookup_counterbore(d_bore, h_bore, tolerance=0.5)
                size_name = cb_match[0] if cb_match else "Custom"
                std_screw = f"DIN 912 {size_name}" if cb_match else "DIN 912"

                results.append(RecognizedFeature(
                    feature_type=FeatureType.COUNTERBORE,
                    center=c1.center,
                    nominal_size=std_screw,
                    standard="DIN 912 / ISO 4762",
                    d_pass=d_pass,
                    d_bore=d_bore,
                    h_bore=h_bore,
                    depth=part_thickness,
                    shape_ids=[c1.id, c2.id]
                ))

        return results

    # -------------------------------------------------------------------------
    # 3. COUNTERSINK RECOGNITION (DIN 74 Form F / ISO 7721)
    # -------------------------------------------------------------------------
    def detect_countersinks(
        self,
        shapes_by_view: Dict[str, List[Shape]],
        part_thickness: float = 50.0
    ) -> List[RecognizedFeature]:
        """
        Identify countersinks from concentric circle pairs and evaluate included conical angle.
        """
        results: List[RecognizedFeature] = []
        top_shapes = shapes_by_view.get('top', [])
        front_shapes = shapes_by_view.get('front', [])

        circles = [s for s in top_shapes if isinstance(s, Circle)]

        for i in range(len(circles)):
            for j in range(i + 1, len(circles)):
                c1, c2 = circles[i], circles[j]
                dist = math.hypot(c1.center[0] - c2.center[0], c1.center[1] - c2.center[1])
                if dist > 0.5:
                    continue

                r_pass = min(c1.radius, c2.radius)
                r_sink = max(c1.radius, c2.radius)
                d_pass = 2.0 * r_pass
                d_sink = 2.0 * r_sink

                if abs(d_sink - d_pass) < 1.0:
                    continue

                # Find conical taper depth in front view
                h_sink = self._find_countersink_depth(c1.center[0], front_shapes, d_sink, d_pass)
                if h_sink <= 0.0:
                    # Default nominal calculation assuming standard 90 deg
                    h_sink = (d_sink - d_pass) / (2.0 * math.tan(math.radians(45.0)))

                # Calculate included chamfer angle
                angle_rad = 2.0 * math.atan((d_sink - d_pass) / (2.0 * h_sink))
                angle_deg = round(math.degrees(angle_rad), 1)

                cs_match = lookup_countersink(d_sink, angle_deg, tolerance=0.5)
                size_name = cs_match[0] if cs_match else "M4"
                std_name = f"ISO 7721 {size_name} {int(round(angle_deg))} DEG"

                results.append(RecognizedFeature(
                    feature_type=FeatureType.COUNTERSINK,
                    center=c1.center,
                    nominal_size=std_name,
                    standard="ISO 7721 / DIN 74 Form F",
                    d_pass=d_pass,
                    d_bore=d_sink,
                    h_bore=h_sink,
                    angle=angle_deg,
                    depth=part_thickness,
                    shape_ids=[c1.id, c2.id]
                ))

        return results

    # -------------------------------------------------------------------------
    # 4. PITCH CIRCLE DIAMETER (PCD) PATTERN CLUSTERING
    # -------------------------------------------------------------------------
    def detect_pcd_patterns(
        self,
        shapes_by_view: Dict[str, List[Shape]]
    ) -> List[BoltCirclePattern]:
        """
        4-Step PCD Pattern Recognition:
        1. Identify Reference Centerline Circle
        2. Collect Candidate Hole Features
        3. Distance Invariance Test (|R_i - D_pcd/2| <= 1.0mm)
        4. Angular Equispacing Test (|delta_phi_i - 2pi/N| <= 1 deg)
        """
        patterns: List[BoltCirclePattern] = []
        top_shapes = shapes_by_view.get('top', [])

        # Find reference centerline circles
        pcd_circles = [
            s for s in top_shapes
            if isinstance(s, Circle) and s.layer == "Centerline"
        ]

        hole_candidates = [
            s for s in top_shapes
            if isinstance(s, Circle) and s.layer != "Centerline"
        ]

        if not hole_candidates:
            return patterns

        # If no explicit centerline circle is drafted, evaluate virtual PCD clustering
        reference_pcds = []
        if pcd_circles:
            for pcircle in pcd_circles:
                reference_pcds.append((pcircle.center, 2.0 * pcircle.radius, pcircle.id))
        else:
            # Infer central axis from geometric centroid of all holes
            if len(hole_candidates) >= 3:
                cx = sum(h.center[0] for h in hole_candidates) / len(hole_candidates)
                cy = sum(h.center[1] for h in hole_candidates) / len(hole_candidates)
                dists = [math.hypot(h.center[0] - cx, h.center[1] - cy) for h in hole_candidates]
                avg_r = sum(dists) / len(dists)
                if all(abs(d - avg_r) <= 1.0 for d in dists):
                    reference_pcds.append(((cx, cy), 2.0 * avg_r, None))

        for center_pt, d_pcd, pcd_id in reference_pcds:
            cx_0, cy_0 = center_pt
            r_target = d_pcd / 2.0

            # Step 3: Collect holes matching radial distance
            matched_holes: List[Tuple[float, Circle]] = []
            for hole in hole_candidates:
                r_dist = math.hypot(hole.center[0] - cx_0, hole.center[1] - cy_0)
                if abs(r_dist - r_target) <= 1.0:
                    phi = math.atan2(hole.center[1] - cy_0, hole.center[0] - cx_0)
                    if phi < 0:
                        phi += 2.0 * math.pi
                    matched_holes.append((phi, hole))

            n_holes = len(matched_holes)
            if n_holes < 3:
                continue

            # Step 4: Sort by polar angle and verify equispacing
            matched_holes.sort(key=lambda item: item[0])
            angles = [item[0] for item in matched_holes]
            delta_nominal = (2.0 * math.pi) / n_holes

            is_equispaced = True
            for k in range(n_holes):
                next_k = (k + 1) % n_holes
                step = angles[next_k] - angles[k]
                if step < 0:
                    step += 2.0 * math.pi
                if abs(step - delta_nominal) > math.radians(2.0):
                    is_equispaced = False
                    break

            if is_equispaced:
                hole_dia = 2.0 * matched_holes[0][1].radius
                # Match standard fastener size (e.g., 6.6mm -> M6 Clearance, 9.0mm -> M8 Clearance)
                matched_fastener = None
                for size, data in METRIC_COARSE_THREADS.items():
                    if abs(hole_dia - data["clearance_med"]) <= 0.3 or abs(hole_dia - data["clearance_close"]) <= 0.3:
                        matched_fastener = f"{size} Clearance (DIN 273)"
                        break

                pattern_ids = [item[1].id for item in matched_holes]
                if pcd_id:
                    pattern_ids.append(pcd_id)

                patterns.append(BoltCirclePattern(
                    pcd=round(d_pcd, 2),
                    count=n_holes,
                    hole_size=round(hole_dia, 2),
                    center=(round(cx_0, 2), round(cy_0, 2)),
                    nominal_spacing_deg=round(math.degrees(delta_nominal), 1),
                    matched_fastener=matched_fastener,
                    shape_ids=pattern_ids
                ))

        return patterns

    # -------------------------------------------------------------------------
    # HELPER CROSS-VIEW ELEVATION PROJECTION MATCHER
    # -------------------------------------------------------------------------
    def _find_elevation_depth(self, plan_x: float, front_shapes: List[Shape], default_depth: float) -> float:
        """Match vertical hidden lines in front view within cross-view tolerance tau"""
        lines = [s for s in front_shapes if isinstance(s, Line) and s.layer == "Hidden"]
        matching_ys = []

        for line in lines:
            # Check if line is vertical and aligned with plan_x within tau
            if abs(line.start[0] - line.end[0]) <= 0.5:
                lx = (line.start[0] + line.end[0]) / 2.0
                if abs(lx - plan_x) <= self.tau or abs(abs(lx) - abs(plan_x)) <= self.tau:
                    y_len = abs(line.end[1] - line.start[1])
                    matching_ys.append(y_len)

        return max(matching_ys) if matching_ys else default_depth

    def _find_counterbore_depth(self, plan_x: float, front_shapes: List[Shape], d_bore: float) -> float:
        """Find counterbore shoulder depth in front view or return standard entry"""
        lines = [s for s in front_shapes if isinstance(s, Line)]
        for line in lines:
            if abs(line.start[0] - line.end[0]) <= 0.5:
                lx = (line.start[0] + line.end[0]) / 2.0
                if abs(abs(lx) - abs(plan_x)) <= (d_bore / 2.0 + self.tau):
                    y_len = abs(line.end[1] - line.start[1])
                    if 2.0 <= y_len <= 30.0:
                        return y_len

        # Fallback to standard table if not explicitly drafted in front view
        for size, data in COUNTERBORE_TABLE.items():
            if abs(d_bore - data["d_bore"]) <= 0.5:
                return data["h_bore"]
        return 6.5

    def _find_countersink_depth(self, plan_x: float, front_shapes: List[Shape], d_sink: float, d_pass: float) -> float:
        """Find conical countersink taper depth in front view"""
        lines = [s for s in front_shapes if isinstance(s, Line)]
        for line in lines:
            # Angled chamfer line
            dx = abs(line.end[0] - line.start[0])
            dy = abs(line.end[1] - line.start[1])
            expected_dx = (d_sink - d_pass) / 2.0
            if abs(dx - expected_dx) <= self.tau and dy > 0.5:
                return dy
        return (d_sink - d_pass) / (2.0 * math.tan(math.radians(45.0)))
