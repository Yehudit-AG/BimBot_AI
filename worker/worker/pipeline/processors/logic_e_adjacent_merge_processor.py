"""
LOGIC E processor – Band-based adjacency merge.

Merges rectangles from LOGIC D that belong to the same band (same generating
pair of parallel lines) and are adjacent along the run axis. Output: merged
rectangles + ineligible/singletons only.
"""

import time
from typing import Dict, Any, List, Tuple, Optional

from .base_processor import BaseProcessor
from .wall_candidate_constants import (
    THICKNESS_MIN_MM,
    THICKNESS_MAX_MM,
    LINE_COORD_TOL_MM,
    GAP_TOL_MM,
)


def _get_bounds(rect: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """Extract (xmin, ymin, xmax, ymax) from a quad dict. Returns None if invalid."""
    a = rect.get("trimmedSegmentA") or {}
    b = rect.get("trimmedSegmentB") or {}
    points = []
    for seg in (a, b):
        for key in ("p1", "p2"):
            p = seg.get(key) or {}
            x, y = float(p.get("X", 0)), float(p.get("Y", 0))
            points.append((x, y))
    if len(points) < 4:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _bounds_to_quad_dict(xmin: float, ymin: float, xmax: float, ymax: float) -> Dict[str, Any]:
    """Build a quad dict (same schema as LOGIC C/D) from axis-aligned bounds. Clockwise from (xmin, ymin)."""
    return {
        "trimmedSegmentA": {
            "p1": {"X": xmin, "Y": ymin},
            "p2": {"X": xmax, "Y": ymin},
        },
        "trimmedSegmentB": {
            "p1": {"X": xmax, "Y": ymax},
            "p2": {"X": xmin, "Y": ymax},
        },
        "bounding_rectangle": {"minX": xmin, "minY": ymin, "maxX": xmax, "maxY": ymax},
    }


def _quantize(v: float, tol: float) -> int:
    """Q(v) = round(v / tol)."""
    return int(round(v / tol))


def _infer_orientation(
    xmin: float, ymin: float, xmax: float, ymax: float,
    thickness_min: float, thickness_max: float,
) -> Optional[str]:
    """
    Infer 'H' (run axis X) or 'V' (run axis Y). Returns None if ineligible.
    H: lines parallel to X, thickness = dy; V: lines parallel to Y, thickness = dx.
    """
    dx = xmax - xmin
    dy = ymax - ymin
    ok_h = thickness_min <= dy <= thickness_max and dx >= dy
    ok_v = thickness_min <= dx <= thickness_max and dy > dx
    if ok_h and not ok_v:
        return "H"
    if ok_v and not ok_h:
        return "V"
    if ok_h and ok_v:
        # Both satisfy; choose orientation where thickness is the smaller dimension.
        if dy <= dx:
            return "H"
        return "V"
    return None


def merge_adjacent_rectangles(
    rectangles: List[Dict[str, Any]],
    thickness_min_mm: float,
    thickness_max_mm: float,
    line_coord_tol_mm: float,
    gap_tol_mm: float,
) -> List[Dict[str, Any]]:
    """
    Merge rectangles in same band that are adjacent along run axis.
    Returns merged rectangles + ineligible rectangles (unchanged). No duplicates.
    """
    if not rectangles:
        return []

    out: List[Dict[str, Any]] = []
    ineligible: List[Dict[str, Any]] = []
    eligible: List[Tuple[Dict[str, Any], float, float, float, float, str, float, float, Tuple, float, float]] = []

    for rect in rectangles:
        bounds = _get_bounds(rect)
        if bounds is None:
            ineligible.append(rect)
            continue
        xmin, ymin, xmax, ymax = bounds
        orientation = _infer_orientation(
            xmin, ymin, xmax, ymax, thickness_min_mm, thickness_max_mm
        )
        if orientation is None:
            ineligible.append(rect)
            continue
        dx = xmax - xmin
        dy = ymax - ymin
        if orientation == "H":
            run_start, run_end = xmin, xmax
            q_lo, q_hi = _quantize(ymin, line_coord_tol_mm), _quantize(ymax, line_coord_tol_mm)
            band_key = ("H", q_lo, q_hi)
            band_min = q_lo * line_coord_tol_mm
            band_max = q_hi * line_coord_tol_mm
        else:
            run_start, run_end = ymin, ymax
            q_lo, q_hi = _quantize(xmin, line_coord_tol_mm), _quantize(xmax, line_coord_tol_mm)
            band_key = ("V", q_lo, q_hi)
            band_min = q_lo * line_coord_tol_mm
            band_max = q_hi * line_coord_tol_mm
        eligible.append((rect, xmin, ymin, xmax, ymax, orientation, run_start, run_end, band_key, band_min, band_max))

    # Group by band key
    groups: Dict[Tuple, List[Tuple]] = {}
    for item in eligible:
        band_key = item[8]
        groups.setdefault(band_key, []).append(item)

    # Merge per group: sort by run_start, linear merge scan
    for band_key, items in groups.items():
        items_sorted = sorted(items, key=lambda t: t[6])  # run_start
        orientation = items_sorted[0][5]
        band_min = items_sorted[0][9]
        band_max = items_sorted[0][10]

        cur_start = items_sorted[0][6]
        cur_end = items_sorted[0][7]
        for i in range(1, len(items_sorted)):
            next_start = items_sorted[i][6]
            next_end = items_sorted[i][7]
            if next_start <= cur_end + gap_tol_mm:
                cur_end = max(cur_end, next_end)
            else:
                if orientation == "H":
                    out.append(_bounds_to_quad_dict(cur_start, band_min, cur_end, band_max))
                else:
                    out.append(_bounds_to_quad_dict(band_min, cur_start, band_max, cur_end))
                cur_start = next_start
                cur_end = next_end
        if orientation == "H":
            out.append(_bounds_to_quad_dict(cur_start, band_min, cur_end, band_max))
        else:
            out.append(_bounds_to_quad_dict(band_min, cur_start, band_max, cur_end))

    out.extend(ineligible)
    return out


class LogicEProcessor(BaseProcessor):
    """LOGIC E: merge adjacent rectangles in the same band along the run axis."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("Starting LOGIC E (band-based adjacency merge)")
        start_time = time.time()

        logic_d_results = pipeline_data.get("logic_d_results", {})
        logic_d_rectangles = logic_d_results.get("logic_d_rectangles") or []

        if not logic_d_rectangles:
            duration_ms = int((time.time() - start_time) * 1000)
            self.update_metrics(
                duration_ms=duration_ms,
                logic_d_input_count=0,
                logic_e_rectangles=0,
            )
            self.log_info("LOGIC E completed (no input)", logic_e_rectangles=0, duration_ms=duration_ms)
            return {
                "logic_e_rectangles": [],
                "algorithm_config": {
                    "thickness_min_mm": THICKNESS_MIN_MM,
                    "thickness_max_mm": THICKNESS_MAX_MM,
                    "line_coord_tol_mm": LINE_COORD_TOL_MM,
                    "gap_tol_mm": GAP_TOL_MM,
                },
                "totals": {"logic_d_input_count": 0, "logic_e_rectangles": 0},
            }

        merged = merge_adjacent_rectangles(
            logic_d_rectangles,
            thickness_min_mm=THICKNESS_MIN_MM,
            thickness_max_mm=THICKNESS_MAX_MM,
            line_coord_tol_mm=LINE_COORD_TOL_MM,
            gap_tol_mm=GAP_TOL_MM,
        )
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            logic_d_input_count=len(logic_d_rectangles),
            logic_e_rectangles=len(merged),
        )
        self.log_info(
            "LOGIC E completed",
            logic_d_input_count=len(logic_d_rectangles),
            logic_e_rectangles=len(merged),
            duration_ms=duration_ms,
        )
        return {
            "logic_e_rectangles": merged,
            "algorithm_config": {
                "thickness_min_mm": THICKNESS_MIN_MM,
                "thickness_max_mm": THICKNESS_MAX_MM,
                "line_coord_tol_mm": LINE_COORD_TOL_MM,
                "gap_tol_mm": GAP_TOL_MM,
            },
            "totals": {
                "logic_d_input_count": len(logic_d_rectangles),
                "logic_e_rectangles": len(merged),
            },
        }
