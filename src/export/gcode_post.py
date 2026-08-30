"""
ISO 6983 Standard CNC G-Code Post-Processor.
Supports Haas VF Series, Fanuc 0i, and GRBL dialects with canned cycle formatting
and cycle time estimation.
"""

import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from ..engine.cam_engine import MachiningOperation, ToolpathSegment, ToolDefinition, OperationType


class GCodePostProcessor:
    """
    Translates abstract ToolpathSegments into machine-specific ISO 6983 G-code programs.
    """

    @staticmethod
    def format_gcode(
        operations: List[MachiningOperation],
        dialect: str = "HAAS_VF",
        part_name: str = "PART_01",
        material: str = "6061-T6 Aluminum",
        program_no: int = 1001
    ) -> str:
        """
        Formats an ordered list of machining operations into a complete, ready-to-run G-code file.
        """
        lines: List[str] = []
        today = datetime.now().strftime("%Y-%m-%d")

        # 1. Program Header
        lines.append("%")
        lines.append(f"O{program_no:04d} (PYTHON CAD PRO - CNC TOOLPATH)")
        lines.append(f"(DATE: {today})")
        lines.append(f"(PART: {part_name.upper()})")
        lines.append(f"(MATERIAL: {material.upper()})")
        lines.append(f"(POST DIALECT: {dialect})")

        # Safe start preamble
        lines.append("G21 (Metric Units mm)")
        lines.append("G90 (Absolute Programming)")
        lines.append("G17 (XY Plane Selection)")
        lines.append("G40 G49 G80 (Cancel Cutter Comp, Length, Canned Cycles)")
        if dialect in ("HAAS_VF", "FANUC_0I"):
            lines.append("G28 G91 Z0.0 (Home Z Axis)")
            lines.append("G90")

        # 2. Iterate Operations
        current_tool_no = -1
        in_canned_cycle = False

        for op_idx, op in enumerate(operations, start=1):
            tool = op.tool
            lines.append("")
            lines.append(f"(----------------------------------------------------)")
            lines.append(f"(OPERATION {op_idx}: {op.name.upper()})")
            lines.append(f"(TOOL T{tool.tool_no}: {tool.name} D={tool.diameter:.2f}mm)")
            lines.append(f"(----------------------------------------------------)")

            # Tool change if tool changed
            if tool.tool_no != current_tool_no:
                if in_canned_cycle:
                    lines.append("G80 (Cancel Canned Cycle)")
                    in_canned_cycle = False

                if current_tool_no != -1 and dialect in ("HAAS_VF", "FANUC_0I"):
                    lines.append("M09 (Coolant Off)")
                    lines.append("G28 G91 Z0.0")
                    lines.append("G90")

                lines.append(f"T{tool.tool_no} M06")
                lines.append(f"S{int(op.spindle_rpm)} M03")
                lines.append("G54")
                current_tool_no = tool.tool_no

            last_x, last_y, last_z = None, None, None
            last_feed = None

            for seg in op.segments:
                g = seg.g_code
                x, y, z = seg.end_pt

                if g in ("G81", "G83", "G84"):
                    # Canned drilling/tapping cycle
                    in_canned_cycle = True
                    r_plane = seg.r_plane if seg.r_plane is not None else 2.0
                    f_val = seg.feed_rate

                    if g == "G81":
                        lines.append(f"G81 X{x:.3f} Y{y:.3f} Z{z:.3f} R{r_plane:.3f} F{f_val:.1f}")
                    elif g == "G83":
                        q_val = seg.q_peck if seg.q_peck is not None else 3.0
                        lines.append(f"G83 X{x:.3f} Y{y:.3f} Z{z:.3f} R{r_plane:.3f} Q{q_val:.3f} F{f_val:.1f}")
                    elif g == "G84":
                        lines.append(f"G84 X{x:.3f} Y{y:.3f} Z{z:.3f} R{r_plane:.3f} F{f_val:.1f}")

                elif g == "G00":
                    if in_canned_cycle:
                        lines.append("G80")
                        in_canned_cycle = False
                    coords = []
                    if last_x is None or abs(x - last_x) > 1e-4:
                        coords.append(f"X{x:.3f}")
                    if last_y is None or abs(y - last_y) > 1e-4:
                        coords.append(f"Y{y:.3f}")
                    if last_z is None or abs(z - last_z) > 1e-4:
                        coords.append(f"Z{z:.3f}")
                    if coords:
                        lines.append(f"G00 {' '.join(coords)}")

                elif g == "G01":
                    if in_canned_cycle:
                        lines.append("G80")
                        in_canned_cycle = False
                    coords = []
                    if last_x is None or abs(x - last_x) > 1e-4:
                        coords.append(f"X{x:.3f}")
                    if last_y is None or abs(y - last_y) > 1e-4:
                        coords.append(f"Y{y:.3f}")
                    if last_z is None or abs(z - last_z) > 1e-4:
                        coords.append(f"Z{z:.3f}")

                    feed_str = f" F{seg.feed_rate:.1f}" if (last_feed is None or abs(seg.feed_rate - last_feed) > 0.1) else ""
                    if coords or feed_str:
                        lines.append(f"G01 {' '.join(coords)}{feed_str}")
                        last_feed = seg.feed_rate

                last_x, last_y, last_z = x, y, z

            if in_canned_cycle:
                lines.append("G80")
                in_canned_cycle = False

        # 3. Program Footer
        lines.append("")
        lines.append("(----------------------------------------------------)")
        lines.append("(END OF PROGRAM)")
        lines.append("(----------------------------------------------------)")
        lines.append("M09 (Coolant Off)")
        if dialect in ("HAAS_VF", "FANUC_0I"):
            lines.append("G28 G91 Z0.0")
            lines.append("G28 Y0.0")
        lines.append("M30 (Program Reset)")
        lines.append("%")

        return "\n".join(lines)

    @staticmethod
    def estimate_machining_time(operations: List[MachiningOperation]) -> float:
        """
        Calculates theoretical cycle time in seconds across all operations.
        Rapid traverse speed assumed at 15000 mm/min.
        """
        total_time_min = 0.0
        rapid_speed = 15000.0 # mm/min

        for op in operations:
            for seg in op.segments:
                dx = seg.end_pt[0] - seg.start_pt[0]
                dy = seg.end_pt[1] - seg.start_pt[1]
                dz = seg.end_pt[2] - seg.start_pt[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)

                if seg.is_rapid or seg.g_code == "G00":
                    total_time_min += dist / rapid_speed
                else:
                    f = seg.feed_rate if seg.feed_rate > 0.0 else 500.0
                    total_time_min += dist / f

            # Add 6 seconds for tool change
            total_time_min += 6.0 / 60.0

        return round(total_time_min * 60.0, 1) # Return in seconds
