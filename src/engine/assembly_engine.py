"""
Multi-Part Assembly, ISO 286 Limits & Fits, and Kinematic Exploded Views Engine.
Conforming to ISO 286-1/2, ISO 7200 (BOM), ASME Y14.41, and ISO 10303-21 (STEP AP214).
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any, Set
import numpy as np

from .fits_db import evaluate_iso_fit, FitEvaluationResult


@dataclass
class Part:
    """Discrete component definition within a multi-body assembly"""
    part_id: str
    name: str
    material: str = "Steel (Structural)"
    qty: int = 1
    color_rgba: Tuple[float, float, float, float] = (0.7, 0.75, 0.8, 1.0)
    shape_ids: List[str] = field(default_factory=list)
    is_anchor: bool = False
    nominal_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    extent_3d: Tuple[float, float, float] = (50.0, 50.0, 50.0)  # (Lx, Ly, Lz) in mm


@dataclass
class AssemblyMate:
    """Kinematic constraint and fit relationship between two separate parts"""
    mate_id: str
    type: str                                  # "COAXIAL", "PLANAR", "PARALLEL"
    part_a_id: str
    part_b_id: str
    axis: str = "Z"                            # "X", "Y", "Z"
    vector: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    nominal_d: float = 20.0
    fit_code: Optional[str] = None             # e.g., "H7/g6", "H7/p6"


@dataclass
class BOMEntry:
    """ISO 7200 Bill of Materials line item"""
    item_no: int
    part_id: str
    name: str
    material: str
    qty: int
    dimensions: str                            # e.g. "100.0 x 60.0 x 40.0 mm"
    is_anchor: bool = False


@dataclass
class Assembly:
    """Complete product assembly hierarchy"""
    name: str = "Main Assembly"
    revision: str = "A"
    parts: Dict[str, Part] = field(default_factory=dict)
    mates: List[AssemblyMate] = field(default_factory=list)


class AssemblyEngine:
    """
    Kinematic solver and trajectory synthesizer for multi-part exploded views and ISO fits.
    """

    @staticmethod
    def get_part_extent_along_axis(
        part: Part,
        axis_vector: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        shapes_by_view: Optional[Dict[str, List[Any]]] = None
    ) -> float:
        """
        Calculates bounding dimension along mating axis with 2D shape fallback (Guardrail #2).
        """
        vx, vy, vz = axis_vector
        # If extent_3d is available and non-zero
        if part.extent_3d and max(part.extent_3d) > 0.0:
            if abs(vz) > 0.7:
                return float(part.extent_3d[2])
            elif abs(vy) > 0.7:
                return float(part.extent_3d[1])
            else:
                return float(part.extent_3d[0])

        # 2D Bounding span fallback
        if shapes_by_view and part.shape_ids:
            all_shapes = [s for slist in shapes_by_view.values() for s in slist if getattr(s, 'id', None) in part.shape_ids]
            if all_shapes:
                xs, ys = [], []
                for s in all_shapes:
                    if hasattr(s, 'rect'):
                        rx, ry, rw, rh = s.rect
                        xs.extend([rx, rx + rw])
                        ys.extend([ry, ry + rh])
                    elif hasattr(s, 'radius') and hasattr(s, 'center'):
                        xs.extend([s.center[0] - s.radius, s.center[0] + s.radius])
                        ys.extend([s.center[1] - s.radius, s.center[1] + s.radius])
                    elif hasattr(s, 'start') and hasattr(s, 'end'):
                        xs.extend([s.start[0], s.end[0]])
                        ys.extend([s.start[1], s.end[1]])
                if xs and ys:
                    span_x = max(xs) - min(xs)
                    span_y = max(ys) - min(ys)
                    return max(span_x, span_y, 25.0)

        return 40.0  # Default 40mm extent

    @staticmethod
    def compute_exploded_trajectories(
        assembly: Assembly,
        t_factor: float = 0.0,
        s_gap: float = 25.0,
        shapes_by_view: Optional[Dict[str, List[Any]]] = None
    ) -> Dict[str, Tuple[float, float, float]]:
        """
        Computes dynamic 3D translation vectors for each component at slider factor t in [0.0, 1.0].
        Implements cycle detection and disconnected subgraph radial expansion (Guardrail #1).
        """
        t = max(0.0, min(1.0, float(t_factor)))
        translations: Dict[str, Tuple[float, float, float]] = {}

        if not assembly.parts:
            return translations

        # Find anchor part (base)
        anchor_id = None
        for pid, p in assembly.parts.items():
            if p.is_anchor:
                anchor_id = pid
                break
        if not anchor_id:
            anchor_id = next(iter(assembly.parts.keys()))

        translations[anchor_id] = (0.0, 0.0, 0.0)

        # Build adjacency graph for mates
        adj: Dict[str, List[Tuple[str, Tuple[float, float, float]]]] = {pid: [] for pid in assembly.parts}
        for m in assembly.mates:
            if m.part_a_id in adj and m.part_b_id in adj:
                adj[m.part_a_id].append((m.part_b_id, m.vector))
                adj[m.part_b_id].append((m.part_a_id, (-m.vector[0], -m.vector[1], -m.vector[2])))

        # BFS / DFS traversal with cycle detection
        visited: Set[str] = {anchor_id}
        cumulative_dist: Dict[str, float] = {anchor_id: 0.0}
        trajectory_vec: Dict[str, Tuple[float, float, float]] = {anchor_id: (0.0, 0.0, 0.0)}

        queue = [anchor_id]
        while queue:
            curr = queue.pop(0)
            curr_dist = cumulative_dist[curr]
            curr_part = assembly.parts[curr]
            curr_extent = AssemblyEngine.get_part_extent_along_axis(curr_part, shapes_by_view=shapes_by_view)

            for neighbor, vec in adj.get(curr, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    sep = curr_dist + curr_extent + s_gap
                    cumulative_dist[neighbor] = sep
                    trajectory_vec[neighbor] = vec
                    queue.append(neighbor)

        # Calculate final translation offsets for connected parts
        for pid, dist in cumulative_dist.items():
            vx, vy, vz = trajectory_vec.get(pid, (0.0, 0.0, 1.0))
            p_orig = assembly.parts[pid].nominal_position
            translations[pid] = (
                p_orig[0] + t * dist * vx,
                p_orig[1] + t * dist * vy,
                p_orig[2] + t * dist * vz
            )

        # Disconnected / Floating parts fallback (Radial expansion)
        unvisited = [pid for pid in assembly.parts if pid not in visited]
        for idx, pid in enumerate(unvisited):
            p = assembly.parts[pid]
            p_orig = p.nominal_position
            # Expand radially away from origin
            rad_dist = (idx + 1) * 75.0
            translations[pid] = (
                p_orig[0] + t * rad_dist * 0.707,
                p_orig[1] + t * rad_dist * 0.707,
                p_orig[2] + t * rad_dist * 0.5
            )

        return translations

    @staticmethod
    def compile_bill_of_materials(
        assembly: Assembly,
        shapes_by_view: Optional[Dict[str, List[Any]]] = None
    ) -> List[BOMEntry]:
        """
        Compiles structured ISO 7200 Bill of Materials with bounding dimensions fallback (Guardrail #2).
        """
        bom: List[BOMEntry] = []
        for idx, (pid, p) in enumerate(assembly.parts.items(), start=1):
            lx, ly, lz = p.extent_3d

            # If 3D solid is not available, compute from 2D shape span
            if max(lx, ly, lz) <= 0.0 and shapes_by_view and p.shape_ids:
                all_shapes = [s for slist in shapes_by_view.values() for s in slist if getattr(s, 'id', None) in p.shape_ids]
                if all_shapes:
                    xs, ys = [], []
                    for s in all_shapes:
                        if hasattr(s, 'rect'):
                            rx, ry, rw, rh = s.rect
                            xs.extend([rx, rx + rw])
                            ys.extend([ry, ry + rh])
                        elif hasattr(s, 'radius') and hasattr(s, 'center'):
                            xs.extend([s.center[0] - s.radius, s.center[0] + s.radius])
                            ys.extend([s.center[1] - s.radius, s.center[1] + s.radius])
                        elif hasattr(s, 'start') and hasattr(s, 'end'):
                            xs.extend([s.start[0], s.end[0]])
                            ys.extend([s.start[1], s.end[1]])
                    if xs and ys:
                        lx = round(max(xs) - min(xs), 1)
                        ly = round(max(ys) - min(ys), 1)
                        lz = 25.0

            dim_str = f"{lx:.1f} x {ly:.1f} x {lz:.1f} mm"

            bom.append(BOMEntry(
                item_no=idx,
                part_id=pid,
                name=p.name,
                material=p.material,
                qty=p.qty,
                dimensions=dim_str,
                is_anchor=p.is_anchor
            ))

        return bom
