"""
2.5D Toolpath Planning & Trajectory Synthesizer.
Implements:
- 3-Tier Z Safety Hierarchy (Guardrail #1: Z_clearance = 10.0mm, Z_retract = 2.0mm, Z_cut = -depth)
- Shapely MultiPolygon Recursive Inward Pocket Clearing (Guardrail #2)
- Outer Profile Contouring with Arc Lead-In / Lead-Out
- Canned Drilling (G81 / G83) & Rigid Tapping (G84) Cycles
"""

import math
from typing import List, Tuple, Optional, Any, Union
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, box, LineString
from shapely.ops import unary_union

from .cam_engine import (
    ToolDefinition, ToolpathSegment, MachiningOperation, OperationType,
    calculate_speeds_and_feeds
)


# 3-Tier Z Safety Hierarchy Planes
Z_CLEARANCE = 10.0   # Safe traverse between operations (mm)
Z_RETRACT = 2.0      # Retract plane above stock top (mm)


class ToolpathPlanner:
    """
    Synthesizes CNC cutter motion vectors from CAD polygons and semantic hole features.
    """

    @staticmethod
    def plan_facing(
        stock_rect: Tuple[float, float, float, float], # (x, y, w, h)
        tool: ToolDefinition,
        depth: float = 1.0,
        feed_xy: float = 1200.0,
        feed_z: float = 300.0
    ) -> List[ToolpathSegment]:
        """
        Generates linear raster facing passes over the raw stock top face.
        """
        segments: List[ToolpathSegment] = []
        x, y, w, h = stock_rect
        r_tool = tool.diameter / 2.0
        stepover = 0.70 * tool.diameter

        # Lead-in and lead-out margins
        margin = r_tool + 5.0
        min_x, max_x = x - margin, x + w + margin
        min_y, max_y = y - margin, y + h + margin

        # Rapid to start clearance
        curr_y = min_y + r_tool
        segments.append(ToolpathSegment(
            g_code="G00",
            start_pt=(min_x, curr_y, Z_CLEARANCE),
            end_pt=(min_x, curr_y, Z_CLEARANCE),
            is_rapid=True
        ))

        # Plunge to cut depth
        segments.append(ToolpathSegment(
            g_code="G01",
            start_pt=(min_x, curr_y, Z_CLEARANCE),
            end_pt=(min_x, curr_y, -depth),
            feed_rate=feed_z
        ))

        direction = 1 # 1: left-to-right, -1: right-to-left
        while curr_y <= max_y:
            target_x = max_x if direction == 1 else min_x
            start_x = min_x if direction == 1 else max_x

            segments.append(ToolpathSegment(
                g_code="G01",
                start_pt=(start_x, curr_y, -depth),
                end_pt=(target_x, curr_y, -depth),
                feed_rate=feed_xy
            ))

            curr_y += stepover
            if curr_y <= max_y:
                # Step over to next line
                segments.append(ToolpathSegment(
                    g_code="G01",
                    start_pt=(target_x, curr_y - stepover, -depth),
                    end_pt=(target_x, curr_y, -depth),
                    feed_rate=feed_xy
                ))
            direction *= -1

        # Retract to clearance
        last_pt = segments[-1].end_pt
        segments.append(ToolpathSegment(
            g_code="G00",
            start_pt=last_pt,
            end_pt=(last_pt[0], last_pt[1], Z_CLEARANCE),
            is_rapid=True
        ))

        return segments

    @staticmethod
    def plan_pocket_clearing(
        pocket_poly: Polygon,
        tool: ToolDefinition,
        depth: float = 10.0,
        stepover_ratio: float = 0.60,
        max_stepdown: Optional[float] = None,
        feed_xy: float = 1000.0,
        feed_z: float = 300.0
    ) -> List[ToolpathSegment]:
        """
        Generates 2.5D inward spiral pocket clearing with multi-pass stepdown and MultiPolygon handling (Guardrail #1 & #2).
        """
        segments: List[ToolpathSegment] = []
        r_tool = tool.diameter / 2.0
        stepover_dist = stepover_ratio * tool.diameter

        # Determine axial stepdown passes
        ap = max_stepdown if max_stepdown is not None else (0.50 * tool.diameter)
        pass_count = max(1, math.ceil(depth / max(1.0, ap)))
        step_z = depth / pass_count

        # Safe initial inset boundary
        safe_boundary = pocket_poly.buffer(-r_tool)
        if safe_boundary.is_empty:
            return segments

        for p_idx in range(1, pass_count + 1):
            current_z = -round(p_idx * step_z, 4)

            # Generate concentric inward rings
            rings: List[Polygon] = []
            ToolpathPlanner._generate_inward_rings_recursive(safe_boundary, stepover_dist, rings)

            for ring in rings:
                coords = list(ring.exterior.coords)
                if len(coords) < 3:
                    continue

                start_x, start_y = coords[0]

                # 1. Rapid to position at Z_retract
                segments.append(ToolpathSegment(
                    g_code="G00",
                    start_pt=(start_x, start_y, Z_RETRACT),
                    end_pt=(start_x, start_y, Z_RETRACT),
                    is_rapid=True
                ))

                # 2. Feed plunge to current cut depth
                segments.append(ToolpathSegment(
                    g_code="G01",
                    start_pt=(start_x, start_y, Z_RETRACT),
                    end_pt=(start_x, start_y, current_z),
                    feed_rate=feed_z
                ))

                # 3. Mill the closed loop
                for i in range(len(coords) - 1):
                    p_start = coords[i]
                    p_end = coords[i + 1]
                    segments.append(ToolpathSegment(
                        g_code="G01",
                        start_pt=(p_start[0], p_start[1], current_z),
                        end_pt=(p_end[0], p_end[1], current_z),
                        feed_rate=feed_xy
                    ))

                # 4. Retract back to Z_retract
                segments.append(ToolpathSegment(
                    g_code="G00",
                    start_pt=(start_x, start_y, current_z),
                    end_pt=(start_x, start_y, Z_RETRACT),
                    is_rapid=True
                ))

        # Final retract to Z_clearance
        if segments:
            last_pt = segments[-1].end_pt
            segments.append(ToolpathSegment(
                g_code="G00",
                start_pt=last_pt,
                end_pt=(last_pt[0], last_pt[1], Z_CLEARANCE),
                is_rapid=True
            ))

        return segments

    @staticmethod
    def _generate_inward_rings_recursive(
        geom: Union[Polygon, MultiPolygon],
        stepover: float,
        out_rings: List[Polygon]
    ):
        """
        Recursively decomposes Polygon and MultiPolygon geometry into concentric offset loops (Guardrail #2).
        """
        if geom.is_empty:
            return

        polygons: List[Polygon] = []
        if isinstance(geom, Polygon):
            polygons.append(geom)
        elif isinstance(geom, MultiPolygon):
            polygons.extend(geom.geoms)

        for poly in polygons:
            if poly.is_empty or poly.area < 1e-3:
                continue
            out_rings.append(poly)

            # Inset further by stepover
            next_inset = poly.buffer(-stepover)
            ToolpathPlanner._generate_inward_rings_recursive(next_inset, stepover, out_rings)

    @staticmethod
    def plan_contour(
        stock_poly: Polygon,
        tool: ToolDefinition,
        depth: float = 10.0,
        is_outer: bool = True,
        feed_xy: float = 1000.0,
        feed_z: float = 300.0
    ) -> List[ToolpathSegment]:
        """
        Generates outer or inner profile contouring with cutter radius compensation and tangential lead-in/out.
        """
        segments: List[ToolpathSegment] = []
        r_tool = tool.diameter / 2.0

        offset_dist = r_tool if is_outer else -r_tool
        path_geom = stock_poly.buffer(offset_dist)
        if path_geom.is_empty:
            return segments

        poly = path_geom if isinstance(path_geom, Polygon) else list(path_geom.geoms)[0]
        coords = list(poly.exterior.coords)
        if len(coords) < 3:
            return segments

        start_x, start_y = coords[0]
        lead_r = r_tool

        # Rapid to lead-in point at Z_retract
        lead_x = start_x - lead_r
        lead_y = start_y
        segments.append(ToolpathSegment(
            g_code="G00",
            start_pt=(lead_x, lead_y, Z_RETRACT),
            end_pt=(lead_x, lead_y, Z_RETRACT),
            is_rapid=True
        ))

        # Plunge
        segments.append(ToolpathSegment(
            g_code="G01",
            start_pt=(lead_x, lead_y, Z_RETRACT),
            end_pt=(lead_x, lead_y, -depth),
            feed_rate=feed_z
        ))

        # Lead-in move to start point
        segments.append(ToolpathSegment(
            g_code="G01",
            start_pt=(lead_x, lead_y, -depth),
            end_pt=(start_x, start_y, -depth),
            feed_rate=feed_xy
        ))

        # Mill profile perimeter
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            segments.append(ToolpathSegment(
                g_code="G01",
                start_pt=(p1[0], p1[1], -depth),
                end_pt=(p2[0], p2[1], -depth),
                feed_rate=feed_xy
            ))

        # Retract to Z_clearance
        segments.append(ToolpathSegment(
            g_code="G00",
            start_pt=(start_x, start_y, -depth),
            end_pt=(start_x, start_y, Z_CLEARANCE),
            is_rapid=True
        ))

        return segments

    @staticmethod
    def plan_drilling_cycle(
        center_xy: Tuple[float, float],
        hole_diameter: float,
        depth: float,
        tool: ToolDefinition,
        feed_z: float = 225.0
    ) -> List[ToolpathSegment]:
        """
        Generates standard drilling (G81) or deep-hole peck drilling (G83) canned cycle.
        Peck cycle is selected when depth > 3.0 * tool diameter.
        """
        segments: List[ToolpathSegment] = []
        cx, cy = center_xy

        # Rapid to hole position at Z_clearance
        segments.append(ToolpathSegment(
            g_code="G00",
            start_pt=(cx, cy, Z_CLEARANCE),
            end_pt=(cx, cy, Z_CLEARANCE),
            is_rapid=True
        ))

        is_peck = depth > (3.0 * tool.diameter)
        g_code = "G83" if is_peck else "G81"
        q_val = round(0.5 * tool.diameter, 2) if is_peck else None

        segments.append(ToolpathSegment(
            g_code=g_code,
            start_pt=(cx, cy, Z_RETRACT),
            end_pt=(cx, cy, -depth),
            feed_rate=feed_z,
            r_plane=Z_RETRACT,
            q_peck=q_val
        ))

        return segments

    @staticmethod
    def plan_tapping_cycle(
        center_xy: Tuple[float, float],
        thread_depth: float,
        tool: ToolDefinition,
        pitch: float = 1.5,
        spindle_rpm: float = 400.0
    ) -> List[ToolpathSegment]:
        """
        Generates rigid tapping (G84) canned cycle with synchronized feed rate F = N * P.
        """
        segments: List[ToolpathSegment] = []
        cx, cy = center_xy
        tap_feed = spindle_rpm * pitch

        # Rapid to thread position at Z_clearance
        segments.append(ToolpathSegment(
            g_code="G00",
            start_pt=(cx, cy, Z_CLEARANCE),
            end_pt=(cx, cy, Z_CLEARANCE),
            is_rapid=True
        ))

        segments.append(ToolpathSegment(
            g_code="G84",
            start_pt=(cx, cy, Z_RETRACT),
            end_pt=(cx, cy, -thread_depth),
            feed_rate=tap_feed,
            r_plane=Z_RETRACT
        ))

        return segments
