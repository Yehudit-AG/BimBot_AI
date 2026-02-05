"""
LOGIC C processor - Pair filtering by intervening lines.

Consumes LOGIC B pairs and the same line population; rejects any pair for which
a line (other than the pair's two source lines) has non-trivial intersection
with the interior of the strip. Uses interior-shrunk strip and dedicated
blocking-length threshold. Same units and conventions as the rest of the pipeline.
"""

import math
import time
from typing import Dict, Any, List, Tuple

from shapely.geometry import Polygon, LineString

from .base_processor import BaseProcessor
from .line_utils import build_line_like_entities
from .wall_candidate_constants import MIN_BLOCKING_LENGTH_MM
from .units import EPS_MM


def order_quad_corners_xy(corners: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Order 4 corners by angle from centroid (same logic as frontend orderQuadCorners)."""
    if len(corners) != 4:
        return corners
    cx = sum(p[0] for p in corners) / 4.0
    cy = sum(p[1] for p in corners) / 4.0
    with_angle = [(p[0], p[1], math.atan2(p[1] - cy, p[0] - cx)) for p in corners]
    with_angle.sort(key=lambda t: t[2])
    return [(t[0], t[1]) for t in with_angle]


def _bbox_intersects(
    min_a: float, max_a: float, min_b: float, max_b: float
) -> bool:
    """True if intervals [min_a,max_a] and [min_b,max_b] overlap."""
    return not (max_a < min_b or max_b < min_a)


class LogicCProcessor(BaseProcessor):
    """Filters LOGIC B pairs: reject if any other line intersects strip interior."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("Starting LOGIC C (intervening-line filter)")
        start_time = time.time()

        logic_b_results = pipeline_data.get("logic_b_results", {})
        logic_b_pairs = logic_b_results.get("logic_b_pairs") or []

        parallel_results = pipeline_data.get("parallel_naive_results", {})
        entities_data = parallel_results.get("entities", {})
        parallel_ready_entities = entities_data.get("parallel_ready_entities", [])
        line_entities = build_line_like_entities(parallel_ready_entities)

        accepted = self._filter_pairs(logic_b_pairs, line_entities)

        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            logic_b_input_count=len(logic_b_pairs),
            logic_c_pairs=len(accepted),
        )
        self.log_info(
            "LOGIC C completed",
            logic_b_input_count=len(logic_b_pairs),
            logic_c_pairs=len(accepted),
            duration_ms=duration_ms,
        )

        return {
            "logic_c_pairs": accepted,
            "algorithm_config": {
                "eps_mm": EPS_MM,
                "min_blocking_length_mm": MIN_BLOCKING_LENGTH_MM,
            },
            "totals": {
                "logic_b_input_count": len(logic_b_pairs),
                "logic_c_pairs": len(accepted),
            },
        }

    def _strip_bbox(self, pair: Dict[str, Any]) -> Tuple[float, float, float, float]:
        br = pair.get("bounding_rectangle") or {}
        min_x = br.get("minX")
        min_y = br.get("minY")
        max_x = br.get("maxX")
        max_y = br.get("maxY")
        if min_x is not None and max_x is not None and min_y is not None and max_y is not None:
            return (min_x, min_y, max_x, max_y)
        a = pair.get("trimmedSegmentA") or {}
        b = pair.get("trimmedSegmentB") or {}
        points = []
        for seg in (a, b):
            for k in ("p1", "p2"):
                p = seg.get(k) or {}
                x, y = p.get("X", 0), p.get("Y", 0)
                points.append((x, y))
        if not points:
            return (0, 0, 0, 0)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (min(xs), min(ys), max(xs), max(ys))

    def _line_bbox(self, entity: Dict[str, Any]) -> Tuple[float, float, float, float]:
        nd = entity.get("normalized_data") or {}
        s = nd.get("Start") or {}
        e = nd.get("End") or {}
        x1, y1 = s.get("X", 0), s.get("Y", 0)
        x2, y2 = e.get("X", 0), e.get("Y", 0)
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def _get_quad_corners_xy(self, pair: Dict[str, Any]) -> List[Tuple[float, float]]:
        a = pair.get("trimmedSegmentA") or {}
        b = pair.get("trimmedSegmentB") or {}
        corners = []
        for seg in (a, b):
            for key in ("p1", "p2"):
                p = seg.get(key) or {}
                corners.append((float(p.get("X", 0)), float(p.get("Y", 0))))
        if len(corners) != 4:
            return []
        return order_quad_corners_xy(corners)

    def _has_intervening(
        self,
        pair: Dict[str, Any],
        line_entities: List[Dict[str, Any]],
        strip_bbox: Tuple[float, float, float, float],
    ) -> bool:
        corners = self._get_quad_corners_xy(pair)
        if len(corners) < 4:
            return False
        try:
            poly = Polygon(corners)
            if poly.is_empty or not poly.is_valid:
                return False
            shrunk = poly.buffer(-EPS_MM)
            if shrunk.is_empty:
                return False
        except Exception:
            return False

        id_a = pair.get("sourceLineIdA") or ""
        id_b = pair.get("sourceLineIdB") or ""
        s_min_x, s_min_y, s_max_x, s_max_y = strip_bbox

        for idx, line_ent in enumerate(line_entities):
            eid = line_ent.get("entity_hash") or ""
            if eid == id_a or eid == id_b:
                continue
            l_min_x, l_min_y, l_max_x, l_max_y = self._line_bbox(line_ent)
            if not _bbox_intersects(s_min_x, s_max_x, l_min_x, l_max_x) or not _bbox_intersects(s_min_y, s_max_y, l_min_y, l_max_y):
                continue
            nd = line_ent.get("normalized_data") or {}
            start = nd.get("Start") or {}
            end = nd.get("End") or {}
            x1, y1 = start.get("X", 0), start.get("Y", 0)
            x2, y2 = end.get("X", 0), end.get("Y", 0)
            try:
                ls = LineString([(x1, y1), (x2, y2)])
                if ls.is_empty:
                    continue
                inter = ls.intersection(shrunk)
                if inter.is_empty:
                    continue
                length = getattr(inter, "length", 0.0) or 0.0
                if length > MIN_BLOCKING_LENGTH_MM:
                    return True
            except Exception:
                continue
        return False

    def _filter_pairs(
        self,
        logic_b_pairs: List[Dict[str, Any]],
        line_entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        accepted = []
        for pair in logic_b_pairs:
            strip_bbox = self._strip_bbox(pair)
            if self._has_intervening(pair, line_entities, strip_bbox):
                continue
            accepted.append(pair)
        return accepted
