"""
ASME Y14.5-2018 Geometric Dimensioning & Tolerancing (GD&T) Engine.
Implements Datum Reference Frame (3-2-1 rule), True Position with MMC/LMC bonus tolerances,
Virtual Condition assembly clearance boundaries, and 1D/2D Worst-Case / Root-Sum-Square (RSS) tolerance stack-up analysis.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import math
import numpy as np


class GDTSymbol(Enum):
    """ASME Y14.5-2018 Geometric Characteristic Symbols"""
    # Location
    POSITION = "position"                    # ⌖ (U+2316) / [Pos]
    # Form
    FLATNESS = "flatness"                    # ⏥ (U+23E5) / [Flat]
    STRAIGHTNESS = "straightness"            # ⏤ (U+23E4) / [Str]
    CYLINDRICITY = "cylindricity"            # ⌭ (U+232D) / [Cyl]
    CIRCULARITY = "circularity"              # ○ (U+25CB) / [Circ]
    # Orientation
    PERPENDICULARITY = "perpendicularity"    # ⟂ (U+27C2) / [Perp]
    PARALLELISM = "parallelism"              # ∥ (U+2225) / [Parallel]
    ANGULARITY = "angularity"                # ∠ (U+2220) / [Angle]
    # Profile
    PROFILE_SURFACE = "profile_surface"      # ⌓ (U+2313) / [Prof_Surf]
    PROFILE_LINE = "profile_line"            # ⌒ (U+2312) / [Prof_Line]
    # Runout
    CIRCULAR_RUNOUT = "circular_runout"      # ↗ (U+2197) / [Runout]
    TOTAL_RUNOUT = "total_runout"            # ⇗ (U+21D7) / [Tot_Runout]


# Symbology visual mappings
GDT_UNICODE_MAP = {
    GDTSymbol.POSITION: "⌖",
    GDTSymbol.FLATNESS: "⏥",
    GDTSymbol.STRAIGHTNESS: "⏤",
    GDTSymbol.CYLINDRICITY: "⌭",
    GDTSymbol.CIRCULARITY: "○",
    GDTSymbol.PERPENDICULARITY: "⟂",
    GDTSymbol.PARALLELISM: "∥",
    GDTSymbol.ANGULARITY: "∠",
    GDTSymbol.PROFILE_SURFACE: "⌓",
    GDTSymbol.PROFILE_LINE: "⌒",
    GDTSymbol.CIRCULAR_RUNOUT: "↗",
    GDTSymbol.TOTAL_RUNOUT: "⇗",
}

GDT_LABEL_MAP = {
    GDTSymbol.POSITION: "Position",
    GDTSymbol.FLATNESS: "Flatness",
    GDTSymbol.STRAIGHTNESS: "Straightness",
    GDTSymbol.CYLINDRICITY: "Cylindricity",
    GDTSymbol.CIRCULARITY: "Circularity",
    GDTSymbol.PERPENDICULARITY: "Perpendicularity",
    GDTSymbol.PARALLELISM: "Parallelism",
    GDTSymbol.ANGULARITY: "Angularity",
    GDTSymbol.PROFILE_SURFACE: "Profile of a Surface",
    GDTSymbol.PROFILE_LINE: "Profile of a Line",
    GDTSymbol.CIRCULAR_RUNOUT: "Circular Runout",
    GDTSymbol.TOTAL_RUNOUT: "Total Runout",
}


class MaterialModifier(Enum):
    """ASME Y14.5 Material Condition Modifiers"""
    NONE = "RFS"             # Regardless of Feature Size (Default in ASME Y14.5-2018)
    MMC = "MMC"              # Maximum Material Condition (Ⓜ / (M))
    LMC = "LMC"              # Least Material Condition (Ⓛ / (L))
    FREE_STATE = "FREE"      # Free State (F)
    PROJECTED = "PROJECTED"  # Projected Tolerance Zone (P)


MODIFIER_SYMBOL_MAP = {
    MaterialModifier.NONE: "",
    MaterialModifier.MMC: "Ⓜ",
    MaterialModifier.LMC: "Ⓛ",
    MaterialModifier.FREE_STATE: "Ⓕ",
    MaterialModifier.PROJECTED: "Ⓟ",
}


@dataclass
class DatumFeature:
    """ASME Y14.5 Datum Feature identifier tag on a physical drafting entity"""
    id: str
    label: str                                   # e.g., "A", "B", "C"
    target_shape_id: Optional[str] = None         # ID of linked geometry entity
    view: str = "front"                          # 'top', 'front', 'side'
    origin: Tuple[float, float] = (0.0, 0.0)     # Attachment contact point
    direction: Tuple[float, float] = (0.0, 1.0)  # Normal vector out of datum plane
    order: int = 1                               # 1=Primary, 2=Secondary, 3=Tertiary
    contact_points: int = 3                      # 3-2-1 contact points (3 for A, 2 for B, 1 for C)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "target_shape_id": self.target_shape_id,
            "view": self.view,
            "origin": list(self.origin),
            "direction": list(self.direction),
            "order": self.order,
            "contact_points": self.contact_points,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DatumFeature':
        return cls(
            id=data.get("id", ""),
            label=data.get("label", "A"),
            target_shape_id=data.get("target_shape_id"),
            view=data.get("view", "front"),
            origin=tuple(data.get("origin", [0.0, 0.0])),
            direction=tuple(data.get("direction", [0.0, 1.0])),
            order=data.get("order", 1),
            contact_points=data.get("contact_points", 3),
        )


@dataclass
class FeatureControlFrame:
    """ASME Y14.5 Feature Control Frame (FCF) partitioned annotation"""
    id: str
    target_shape_id: Optional[str] = None         # ID of controlled entity (hole, line, face)
    view: str = "front"
    symbol: GDTSymbol = GDTSymbol.POSITION
    is_diameter: bool = True                     # Prepend Ø for cylindrical tolerance zone
    tolerance: float = 0.1                       # Specified geometric tolerance value (mm)
    modifier: MaterialModifier = MaterialModifier.NONE
    primary_datum: Optional[str] = "A"
    secondary_datum: Optional[str] = None
    tertiary_datum: Optional[str] = None
    leader_anchor: Tuple[float, float] = (0.0, 0.0)   # Frame top-left position on sheet
    leader_target: Tuple[float, float] = (0.0, 0.0)   # Arrowhead contact point on entity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target_shape_id": self.target_shape_id,
            "view": self.view,
            "symbol": self.symbol.value,
            "is_diameter": self.is_diameter,
            "tolerance": self.tolerance,
            "modifier": self.modifier.value,
            "primary_datum": self.primary_datum,
            "secondary_datum": self.secondary_datum,
            "tertiary_datum": self.tertiary_datum,
            "leader_anchor": list(self.leader_anchor),
            "leader_target": list(self.leader_target),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FeatureControlFrame':
        symbol_val = data.get("symbol", "position")
        try:
            sym = GDTSymbol(symbol_val)
        except ValueError:
            sym = GDTSymbol.POSITION

        mod_val = data.get("modifier", "RFS")
        try:
            mod = MaterialModifier(mod_val)
        except ValueError:
            mod = MaterialModifier.NONE

        return cls(
            id=data.get("id", ""),
            target_shape_id=data.get("target_shape_id"),
            view=data.get("view", "front"),
            symbol=sym,
            is_diameter=data.get("is_diameter", True),
            tolerance=data.get("tolerance", 0.1),
            modifier=mod,
            primary_datum=data.get("primary_datum"),
            secondary_datum=data.get("secondary_datum"),
            tertiary_datum=data.get("tertiary_datum"),
            leader_anchor=tuple(data.get("leader_anchor", [0.0, 0.0])),
            leader_target=tuple(data.get("leader_target", [0.0, 0.0])),
        )


@dataclass
class DimensionStackItem:
    """Single dimension component in a 1D/2D tolerance stack-up loop"""
    label: str
    dimension: float               # Nominal dimension value (mm)
    tolerance: float               # Equal-bilateral tolerance (±T mm)
    direction: float = 1.0         # +1.0 for gap expansion, -1.0 for gap contraction


@dataclass
class StackResult:
    """Results of Worst-Case and Root-Sum-Square (RSS) tolerance stack-up analysis"""
    nominal_gap: float
    wc_tolerance: float
    wc_min: float
    wc_max: float
    wc_pass: bool
    rss_tolerance: float
    rss_min: float
    rss_max: float
    rss_pass: bool
    warning_msg: Optional[str] = None
    error_msg: Optional[str] = None


class GDTEngine:
    """
    Mathematical computation and validation engine for ASME Y14.5-2018 GD&T:
    - True Position calculation
    - MMC / LMC Bonus tolerance calculation
    - Virtual Condition assembly boundaries
    - 1D/2D Worst-Case & RSS Tolerance Stack-Up Analysis
    - 3-2-1 Datum Reference Frame (DRF) kinematic constraint validation
    """

    @staticmethod
    def calculate_true_position(dx: float, dy: float) -> float:
        """
        Compute ASME Y14.5 True Position diametrical zone deviation:
        True_Position = 2.0 * sqrt(dx^2 + dy^2)
        """
        return 2.0 * math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def compute_bonus_tolerance(
        nominal_size: float,
        actual_size: float,
        lower_tol: float = 0.0,
        upper_tol: float = 0.0,
        is_internal: bool = True,
        modifier: MaterialModifier = MaterialModifier.NONE
    ) -> float:
        """
        Compute bonus tolerance under Maximum Material Condition (MMC) or Least Material Condition (LMC):
        - Internal Feature (Hole / Pocket):
          MMC_Size = nominal_size - lower_tol (smallest hole = most material)
          Bonus = max(0.0, actual_size - MMC_Size)
        - External Feature (Pin / Shaft / Boss):
          MMC_Size = nominal_size + upper_tol (largest shaft = most material)
          Bonus = max(0.0, MMC_Size - actual_size)
        """
        if modifier == MaterialModifier.NONE:
            return 0.0

        if modifier == MaterialModifier.MMC:
            if is_internal:
                mmc_size = nominal_size - lower_tol
                return max(0.0, actual_size - mmc_size)
            else:
                mmc_size = nominal_size + upper_tol
                return max(0.0, mmc_size - actual_size)

        elif modifier == MaterialModifier.LMC:
            if is_internal:
                lmc_size = nominal_size + upper_tol
                return max(0.0, lmc_size - actual_size)
            else:
                lmc_size = nominal_size - lower_tol
                return max(0.0, actual_size - lmc_size)

        return 0.0

    @staticmethod
    def calculate_virtual_condition(
        nominal_size: float,
        lower_tol: float = 0.0,
        upper_tol: float = 0.0,
        specified_gdt_tol: float = 0.0,
        is_internal: bool = True,
        modifier: MaterialModifier = MaterialModifier.MMC
    ) -> float:
        """
        Compute ASME Y14.5 Virtual Condition extreme boundary:
        - Internal Feature (Hole): VC = MMC_Size - Specified_Geometric_Tolerance
        - External Feature (Pin):  VC = MMC_Size + Specified_Geometric_Tolerance
        """
        if is_internal:
            mmc_size = nominal_size - lower_tol
            return mmc_size - specified_gdt_tol
        else:
            mmc_size = nominal_size + upper_tol
            return mmc_size + specified_gdt_tol

    @staticmethod
    def evaluate_tolerance_stack(stack: List[DimensionStackItem]) -> StackResult:
        """
        Perform 1D/2D Worst-Case (Deterministic) and Root-Sum-Square (RSS 3-Sigma) Tolerance Stack-Up Analysis:
        - Nominal Gap: sum(a_i * D_i)
        - Worst-Case Tolerance: sum(|a_i| * T_i)
        - RSS Tolerance: sqrt(sum((a_i * T_i)^2))
        - Clearance Rule:
          * Worst-Case Min Gap < 0.0 -> WARNING (Interference possible at extreme tolerance limits)
          * RSS Min Gap < 0.0        -> ERROR (Statistically inevitable assembly failure)
        """
        if not stack:
            return StackResult(
                nominal_gap=0.0,
                wc_tolerance=0.0,
                wc_min=0.0,
                wc_max=0.0,
                wc_pass=True,
                rss_tolerance=0.0,
                rss_min=0.0,
                rss_max=0.0,
                rss_pass=True
            )

        nom_gap = 0.0
        wc_tol = 0.0
        rss_sq_sum = 0.0

        for item in stack:
            a_i = item.direction
            nom_gap += a_i * item.dimension
            wc_tol += abs(a_i) * item.tolerance
            rss_sq_sum += (a_i * item.tolerance) ** 2

        rss_tol = math.sqrt(rss_sq_sum)

        wc_min = nom_gap - wc_tol
        wc_max = nom_gap + wc_tol
        wc_pass = (wc_min >= 0.0)

        rss_min = nom_gap - rss_tol
        rss_max = nom_gap + rss_tol
        rss_pass = (rss_min >= 0.0)

        warning_msg = None
        error_msg = None

        if not rss_pass:
            error_msg = f"Assembly clearance failure: Statistical RSS Minimum Gap is negative ({rss_min:.4f} mm). Statistical interference is inevitable."
        elif not wc_pass:
            warning_msg = f"Assembly clearance warning: Worst-Case Minimum Gap is negative ({wc_min:.4f} mm). Interference possible under extreme tolerance bounds."

        return StackResult(
            nominal_gap=round(nom_gap, 6),
            wc_tolerance=round(wc_tol, 6),
            wc_min=round(wc_min, 6),
            wc_max=round(wc_max, 6),
            wc_pass=wc_pass,
            rss_tolerance=round(rss_tol, 6),
            rss_min=round(rss_min, 6),
            rss_max=round(rss_max, 6),
            rss_pass=rss_pass,
            warning_msg=warning_msg,
            error_msg=error_msg
        )

    @staticmethod
    def validate_datum_reference_frame(
        fcf: FeatureControlFrame,
        active_datums: List[DatumFeature]
    ) -> List[str]:
        """
        Validate Datum Reference Frame according to ASME Y14.5 3-2-1 kinematic principles:
        1. Rule GD_01: Referenced datum letter must exist on sheet.
        2. Rule GD_02: Secondary datum must be perpendicular to Primary datum.
        3. Rule GD_04: Duplicate datum references in the same frame are illegal.
        """
        errors = []
        datum_map = {d.label.upper(): d for d in active_datums}
        referenced_letters = []

        for d_label in [fcf.primary_datum, fcf.secondary_datum, fcf.tertiary_datum]:
            if not d_label:
                continue
            clean_label = d_label.strip().upper().strip("-")
            
            # Rule GD_01: Datum Existence
            if clean_label not in datum_map:
                errors.append(f"GD_01: Referenced datum [-{clean_label}-] does not exist on sheet.")
            else:
                referenced_letters.append(clean_label)

        # Rule GD_04: Over-constrained / duplicate DRF references
        if len(referenced_letters) != len(set(referenced_letters)):
            errors.append(f"GD_04: Duplicate datum reference in frame [{'-'.join(referenced_letters)}]. A datum slot cannot be repeated in the same DRF.")

        # Rule GD_02: Datum Orthogonality (Primary vs Secondary)
        if len(referenced_letters) >= 2:
            d_prim = datum_map.get(referenced_letters[0])
            d_sec = datum_map.get(referenced_letters[1])
            if d_prim and d_sec and d_prim.view == d_sec.view:
                # Dot product between normals
                n1 = np.array(d_prim.direction)
                n2 = np.array(d_sec.direction)
                norm1 = np.linalg.norm(n1)
                norm2 = np.linalg.norm(n2)
                if norm1 > 1e-4 and norm2 > 1e-4:
                    dot = abs(np.dot(n1 / norm1, n2 / norm2))
                    # If dot product > sin(0.05 deg) ~= 8.7e-4, datums are not perpendicular
                    if dot > 0.05:  # Tolerance within ~2.8 deg
                        errors.append(f"GD_02: Secondary datum [-{d_sec.label}-] is not orthogonal to Primary datum [-{d_prim.label}-].")

        return errors
