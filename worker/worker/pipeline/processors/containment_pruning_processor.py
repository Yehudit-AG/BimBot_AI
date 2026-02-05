"""
LOGIC D processor – Containment pruning.

After LOGIC C: remove any rectangle fully contained in another; keep only
outer (largest) rectangles. Uses Shapely 2.x and STRtree for spatial indexing.
"""

import math
import time
from typing import Dict, Any, List, Tuple, Optional

from shapely.geometry import Polygon
from shapely.prepared import prep
from shapely.strtree import STRtree

from .base_processor import BaseProcessor
from .wall_candidate_constants import CONTAINMENT_TOL_MM, CONTAINMENT_AREA_EPS_MM2
from .units import EPS_MM


def _order_quad_corners_xy(corners: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Order 4 corners by angle from centroid (same logic as LOGIC C / frontend)."""
    if len(corners) != 4:
        return corners
    cx = sum(p[0] for p in corners) / 4.0
    cy = sum(p[1] for p in corners) / 4.0
    with_angle = [(p[0], p[1], math.atan2(p[1] - cy, p[0] - cx)) for p in corners]
    with_angle.sort(key=lambda t: t[2])
    return [(t[0], t[1]) for t in with_angle]


def _get_quad_corners_xy(pair: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Extract 4 corner points (x, y) from a LOGIC C pair dict, ordered for polygon."""
    a = pair.get("trimmedSegmentA") or {}
    b = pair.get("trimmedSegmentB") or {}
    corners = []
    for seg in (a, b):
        for key in ("p1", "p2"):
            p = seg.get(key) or {}
            corners.append((float(p.get("X", 0)), float(p.get("Y", 0))))
    if len(corners) != 4:
        return []
    return _order_quad_corners_xy(corners)


def _pair_to_polygon(pair: Dict[str, Any]) -> Optional[Polygon]:
    """Convert a LOGIC C pair (quad) to a valid Shapely polygon. Returns None if invalid."""
    corners = _get_quad_corners_xy(pair)
    if len(corners) != 4:
        return None
    try:
        poly = Polygon(corners)
        if poly.is_empty or not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        return poly
    except Exception:
        return None


def prune_contained_rectangles(
    rectangles: List[Dict[str, Any]],
    tol_mm: float,
    area_eps_mm2: float,
) -> List[Dict[str, Any]]:
    """
    Remove any rectangle fully contained in another; return only outer rectangles.

    Uses STRtree for spatial indexing. Rectangles are LOGIC C pair dicts (quads).
    """
    if not rectangles:
        return []

    # 1. Convert to Shapely polygons and keep mapping index -> original rect
    polygons: List[Polygon] = []
    index_to_rect: List[Dict[str, Any]] = []
    for rect in rectangles:
        poly = _pair_to_polygon(rect)
        if poly is None:
            continue
        poly = poly.buffer(0)
        if poly.is_empty:
            continue
        polygons.append(poly)
        index_to_rect.append(rect)

    if not polygons:
        return []

    # 2. Sort by area ascending (small -> large)
    with_area = [(i, polygons[i], polygons[i].area) for i in range(len(polygons))]
    with_area.sort(key=lambda t: t[2])
    sorted_indices = [t[0] for t in with_area]
    sorted_polygons = [t[1] for t in with_area]

    # 3. Build spatial index over all polygons
    tree = STRtree(sorted_polygons)

    # 4. Containment pruning
    contained_indices: set = set()
    for i, B in enumerate(sorted_polygons):
        if i in contained_indices:
            continue
        area_b = B.area
        envelope_b = B.envelope

        candidates = tree.query(envelope_b)
        if candidates is None:
            candidates = []
        try:
            # STRtree.query returns numpy array or scalar
            candidates = list(candidates) if hasattr(candidates, "__len__") else [candidates]
        except (TypeError, ValueError):
            candidates = [candidates] if candidates is not None else []

        for j in candidates:
            if j == i:
                continue
            A = sorted_polygons[j]
            area_a = A.area
            if not (area_a > area_b + area_eps_mm2):
                continue
            if not A.envelope.contains(envelope_b):
                continue
            try:
                if prep(A.buffer(tol_mm)).covers(B):
                    contained_indices.add(i)
                    break
            except Exception:
                continue

    # 5. Output: original rects that are not contained
    outer_indices = [sorted_indices[i] for i in range(len(sorted_indices)) if i not in contained_indices]
    return [index_to_rect[k] for k in outer_indices]


class LogicDProcessor(BaseProcessor):
    """LOGIC D: prune rectangles that are fully contained in another; keep only outer rectangles."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("Starting LOGIC D (containment pruning)")
        start_time = time.time()

        TOL_MM = max(EPS_MM, CONTAINMENT_TOL_MM)
        logic_c_results = pipeline_data.get("logic_c_results", {})
        logic_c_pairs = logic_c_results.get("logic_c_pairs") or []
        if not logic_c_pairs:
            duration_ms = int((time.time() - start_time) * 1000)
            self.update_metrics(
                duration_ms=duration_ms,
                logic_c_input_count=0,
                logic_d_rectangles=0,
                logic_d_removed=0,
            )
            self.log_info("LOGIC D completed (no input)", logic_d_rectangles=0, duration_ms=duration_ms)
            return {
                "logic_d_rectangles": [],
                "algorithm_config": {"tol_mm": TOL_MM, "area_eps_mm2": CONTAINMENT_AREA_EPS_MM2},
                "totals": {"logic_c_input_count": 0, "logic_d_rectangles": 0, "logic_d_removed": 0},
            }
        remaining = prune_contained_rectangles(
            logic_c_pairs,
            tol_mm=TOL_MM,
            area_eps_mm2=CONTAINMENT_AREA_EPS_MM2,
        )
        removed = len(logic_c_pairs) - len(remaining)

        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            logic_c_input_count=len(logic_c_pairs),
            logic_d_rectangles=len(remaining),
            logic_d_removed=removed,
        )
        self.log_info(
            "LOGIC D completed",
            logic_c_input_count=len(logic_c_pairs),
            logic_d_rectangles=len(remaining),
            logic_d_removed=removed,
            duration_ms=duration_ms,
        )

        return {
            "logic_d_rectangles": remaining,
            "algorithm_config": {
                "tol_mm": TOL_MM,
                "area_eps_mm2": CONTAINMENT_AREA_EPS_MM2,
                "eps_mm": EPS_MM,
            },
            "totals": {
                "logic_c_input_count": len(logic_c_pairs),
                "logic_d_rectangles": len(remaining),
                "logic_d_removed": removed,
            },
        }
