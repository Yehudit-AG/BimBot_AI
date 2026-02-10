"""
DOOR_BRIDGE processor – For each door, find aligned pairs of Logic E rectangles (by alignment line).
When multiple pairs lie on the same alignment, keep all and compute a bridge for each.
Output: one entry per door with bridges: [ { bridgeRectangle, meta }, ... ].
"""

import math
import time
from collections import defaultdict
from typing import Dict, Any, List, Tuple, Optional

from .base_processor import BaseProcessor
from .logic_e_adjacent_merge_processor import _get_bounds
from .door_rectangle_assignment_processor import _get_door_center

BRIDGE_ALIGNMENT_TOL_MM = 50.0
# Max gap to fill: door opening width can be ~900–1200 mm; use 2000 mm to allow typical doors
BRIDGE_MAX_GAP_MM = 2000.0


def _bounds_center(b: Tuple[float, float, float, float]) -> Tuple[float, float]:
    xmin, ymin, xmax, ymax = b
    return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)


def _distance(xy1: Tuple[float, float], xy2: Tuple[float, float]) -> float:
    return math.hypot(xy2[0] - xy1[0], xy2[1] - xy1[1])


def _compute_bridge_h(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
    max_gap: float,
) -> Optional[Dict[str, Any]]:
    """Bridge for horizontal pair (aligned by Y). A left, B right. Returns bridge dict or None."""
    axmin, aymin, axmax, aymax = a
    bxmin, bymin, bxmax, bymax = b
    cx_a, cy_a = _bounds_center(a)
    cx_b, cy_b = _bounds_center(b)
    if cx_a <= cx_b:
        gap_left, gap_right = axmax, bxmin
    else:
        gap_left, gap_right = bxmax, axmin
    if gap_right <= gap_left:
        return None
    if (gap_right - gap_left) > max_gap:
        return None
    # Thickness in Y: overlapping band or fallback
    y_lo = max(aymin, bymin)
    y_hi = min(aymax, bymax)
    if y_hi <= y_lo:
        y_lo = min(aymin, bymin)
        y_hi = max(aymax, bymax)
    return {
        "minX": min(gap_left, gap_right),
        "maxX": max(gap_left, gap_right),
        "minY": min(y_lo, y_hi),
        "maxY": max(y_lo, y_hi),
    }


def _compute_bridge_v(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
    max_gap: float,
) -> Optional[Dict[str, Any]]:
    """Bridge for vertical pair (aligned by X). A bottom, B top. Returns bridge dict or None."""
    axmin, aymin, axmax, aymax = a
    bxmin, bymin, bxmax, bymax = b
    cx_a, cy_a = _bounds_center(a)
    cx_b, cy_b = _bounds_center(b)
    if cy_a <= cy_b:
        gap_bottom, gap_top = aymax, bymin
    else:
        gap_bottom, gap_top = bymax, aymin
    if gap_top <= gap_bottom:
        return None
    if (gap_top - gap_bottom) > max_gap:
        return None
    x_lo = max(axmin, bxmin)
    x_hi = min(axmax, bxmax)
    if x_hi <= x_lo:
        x_lo = min(axmin, bxmin)
        x_hi = max(axmax, bxmax)
    return {
        "minX": min(x_lo, x_hi),
        "maxX": max(x_lo, x_hi),
        "minY": min(gap_bottom, gap_top),
        "maxY": max(gap_bottom, gap_top),
    }


def _gap_midpoint_h(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Tuple[float, float]:
    axmin, aymin, axmax, aymax = a
    bxmin, bymin, bxmax, bymax = b
    cx_a, cy_a = _bounds_center(a)
    cx_b, cy_b = _bounds_center(b)
    if cx_a <= cx_b:
        gx = (axmax + bxmin) / 2.0
    else:
        gx = (bxmax + axmin) / 2.0
    y_lo = max(aymin, bymin)
    y_hi = min(aymax, bymax)
    if y_hi <= y_lo:
        y_lo, y_hi = min(aymin, bymin), max(aymax, bymax)
    gy = (y_lo + y_hi) / 2.0
    return (gx, gy)


def _gap_midpoint_v(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Tuple[float, float]:
    axmin, aymin, axmax, aymax = a
    bxmin, bymin, bxmax, bymax = b
    cx_a, cy_a = _bounds_center(a)
    cx_b, cy_b = _bounds_center(b)
    if cy_a <= cy_b:
        gy = (aymax + bymin) / 2.0
    else:
        gy = (bymax + aymin) / 2.0
    x_lo = max(axmin, bxmin)
    x_hi = min(axmax, bxmax)
    if x_hi <= x_lo:
        x_lo, x_hi = min(axmin, bxmin), max(axmax, bxmax)
    gx = (x_lo + x_hi) / 2.0
    return (gx, gy)


def _bridge_area(bridge_rect: Dict[str, Any]) -> float:
    """Area of a bridge rectangle: (maxX - minX) * (maxY - minY)."""
    min_x = bridge_rect.get("minX", 0)
    max_x = bridge_rect.get("maxX", 0)
    min_y = bridge_rect.get("minY", 0)
    max_y = bridge_rect.get("maxY", 0)
    return (max_x - min_x) * (max_y - min_y)


def _get_gap_mm(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float], orient: str) -> Optional[float]:
    """Return gap size in mm for the pair, or None if overlap/touch (no positive gap)."""
    cx_a, cy_a = _bounds_center(a)
    cx_b, cy_b = _bounds_center(b)
    if orient == "H":
        if cx_a <= cx_b:
            gap_left, gap_right = a[2], b[0]
        else:
            gap_left, gap_right = b[2], a[0]
        if gap_right <= gap_left:
            return None
        return gap_right - gap_left
    else:
        if cy_a <= cy_b:
            gap_bottom, gap_top = a[3], b[1]
        else:
            gap_bottom, gap_top = b[3], a[1]
        if gap_top <= gap_bottom:
            return None
        return gap_top - gap_bottom


def _alignment_line_key(orient: str, mid: Tuple[float, float], alignment_tol: float) -> float:
    """Single numeric key for grouping pairs on the same alignment line. H -> Y, V -> X."""
    if orient == "H":
        return round(mid[1] / alignment_tol) * alignment_tol
    return round(mid[0] / alignment_tol) * alignment_tol


def _compute_door_bridges(
    door_assignments: List[Dict[str, Any]],
    logic_e_rectangles: List[Dict[str, Any]],
    doors: List[Dict[str, Any]],
    alignment_tol: float,
    max_gap: float,
) -> List[Dict[str, Any]]:
    """For each door, group aligned pairs by alignment line; keep all pairs on same line and compute a bridge for each."""
    results: List[Dict[str, Any]] = []
    n_rects = len(logic_e_rectangles)

    for assignment in door_assignments:
        door_id = assignment.get("doorId", 0)
        indices = assignment.get("rectangleIndices") or []
        num_rects = len(indices)
        if num_rects < 2:
            results.append({
                "doorId": door_id,
                "bridges": [],
                "meta": {"rectanglesCount": num_rects, "noBridgeReason": "fewer_than_2_rects"},
            })
            continue

        # Door center from door data only (Position or bbox center), never from rectangle pairs
        door_center: Optional[Tuple[float, float]] = None
        if door_id < len(doors):
            data = (doors[door_id].get("data") or {})
            door_center = _get_door_center(data)

        bounds_by_idx: Dict[int, Tuple[float, float, float, float]] = {}
        for idx in indices:
            if idx < 0 or idx >= n_rects:
                continue
            b = _get_bounds(logic_e_rectangles[idx])
            if b is not None:
                bounds_by_idx[idx] = b
        num_valid = len(bounds_by_idx)

        # (i, j, orient, align_diff, dist, line_key) for grouping by same alignment
        candidate_pairs: List[Tuple[int, int, str, float, float, float]] = []
        valid_indices = sorted(bounds_by_idx.keys())
        for ii in range(len(valid_indices)):
            for jj in range(ii + 1, len(valid_indices)):
                i, j = valid_indices[ii], valid_indices[jj]
                a, b = bounds_by_idx[i], bounds_by_idx[j]
                cxa, cya = _bounds_center(a)
                cxb, cyb = _bounds_center(b)
                align_y = abs(cya - cyb)
                align_x = abs(cxa - cxb)
                if align_y <= alignment_tol and align_x > alignment_tol:
                    orient = "H"
                    align_diff = align_y
                    mid = _gap_midpoint_h(a, b)
                elif align_x <= alignment_tol and align_y > alignment_tol:
                    orient = "V"
                    align_diff = align_x
                    mid = _gap_midpoint_v(a, b)
                elif align_y <= alignment_tol and align_x <= alignment_tol:
                    gap_h = abs((max(a[2], b[2]) - min(a[0], b[0])) - (max(a[2] - a[0], b[2] - b[0])))
                    gap_v = abs((max(a[3], b[3]) - min(a[1], b[1])) - (max(a[3] - a[1], b[3] - b[1])))
                    if gap_h <= gap_v:
                        orient = "H"
                        align_diff = align_y
                        mid = _gap_midpoint_h(a, b)
                    else:
                        orient = "V"
                        align_diff = align_x
                        mid = _gap_midpoint_v(a, b)
                else:
                    continue
                dist = _distance(door_center, mid) if door_center else 0.0
                line_key = _alignment_line_key(orient, mid, alignment_tol)
                candidate_pairs.append((i, j, orient, align_diff, dist, line_key))

        if not candidate_pairs:
            results.append({
                "doorId": door_id,
                "bridges": [],
                "meta": {"rectanglesCount": num_valid, "noBridgeReason": "no_aligned_pair"},
            })
            continue

        # Group by (orient, line_key) so pairs on the same alignment line are together
        groups: Dict[Tuple[str, float], List[Tuple[int, int, str, float, float, float]]] = defaultdict(list)
        for t in candidate_pairs:
            key = (t[2], t[5])  # orient, line_key
            groups[key].append(t)

        # Per group: sort by (align_diff, dist, i+j), then keep all pairs on that line and compute bridge for each
        bridge_list: List[Dict[str, Any]] = []
        for _key, group_pairs in groups.items():
            group_pairs.sort(key=lambda t: (t[3], t[4], t[0] + t[1]))
            for t in group_pairs:
                i, j, orient, _, _, _ = t
                a, b = bounds_by_idx[i], bounds_by_idx[j]
                if orient == "H":
                    bridge = _compute_bridge_h(a, b, max_gap)
                else:
                    bridge = _compute_bridge_v(a, b, max_gap)
                if bridge is not None:
                    bridge_list.append({
                        "bridgeRectangle": bridge,
                        "meta": {"orientation": orient, "alignmentToleranceUsed": alignment_tol},
                    })

        # If door has more than one bridge, keep only the one with maximum area
        if len(bridge_list) > 1:
            bridge_list = [max(bridge_list, key=lambda b: _bridge_area(b.get("bridgeRectangle") or {}))]

        results.append({
            "doorId": door_id,
            "bridges": bridge_list,
            "meta": {"rectanglesCount": num_valid},
        })
    return results


class DoorBridgeProcessor(BaseProcessor):
    """For each door, find aligned pairs by alignment line; keep all pairs on the same line and compute a bridge for each (multiple bridges per door allowed)."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("Starting DOOR_BRIDGE")
        start_time = time.time()

        door_assignment_results = pipeline_data.get("door_rectangle_assignment_results") or {}
        door_assignments = door_assignment_results.get("door_assignments") or []
        logic_e_results = pipeline_data.get("logic_e_results") or {}
        logic_e_rectangles = logic_e_results.get("logic_e_rectangles") or []
        window_door_blocks = pipeline_data.get("window_door_blocks") or []
        doors = [b for b in window_door_blocks if b.get("window_or_door") == "door"]

        if not door_assignments or not logic_e_rectangles:
            duration_ms = int((time.time() - start_time) * 1000)
            self.log_info("DOOR_BRIDGE completed (no assignments or no Logic E rects)", duration_ms=duration_ms)
            out = [
                {"doorId": a.get("doorId", i), "bridges": [], "meta": {}}
                for i, a in enumerate(door_assignments)
            ]
            return {
                "door_bridges": out,
                "algorithm_config": {
                    "alignment_tol_mm": BRIDGE_ALIGNMENT_TOL_MM,
                    "max_gap_mm": BRIDGE_MAX_GAP_MM,
                },
                "totals": {"doors_processed": len(out), "doors_with_bridge": 0, "doors_without_bridge": len(out), "total_bridges": 0},
            }

        door_bridges = _compute_door_bridges(
            door_assignments,
            logic_e_rectangles,
            doors,
            BRIDGE_ALIGNMENT_TOL_MM,
            BRIDGE_MAX_GAP_MM,
        )
        with_bridge = sum(1 for r in door_bridges if (r.get("bridges") or []))
        total_bridges = sum(len(r.get("bridges") or []) for r in door_bridges)
        duration_ms = int((time.time() - start_time) * 1000)
        self.log_info(
            "DOOR_BRIDGE completed",
            doors_processed=len(door_bridges),
            doors_with_bridge=with_bridge,
            total_bridges=total_bridges,
            duration_ms=duration_ms,
        )
        return {
            "door_bridges": door_bridges,
            "algorithm_config": {
                "alignment_tol_mm": BRIDGE_ALIGNMENT_TOL_MM,
                "max_gap_mm": BRIDGE_MAX_GAP_MM,
            },
            "totals": {
                "doors_processed": len(door_bridges),
                "doors_with_bridge": with_bridge,
                "doors_without_bridge": len(door_bridges) - with_bridge,
                "total_bridges": total_bridges,
            },
        }
