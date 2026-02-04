"""
LOGIC B processor - Overlap-only wall pair candidate detection.

Consumes PARALLEL_NAIVE line-like entities; produces candidate wall pairs
with strict overlap trimming (1--45 cm distance, parallel tolerance, no extension).
All geometry in XY; Z preserved in output only.
"""

import math
import uuid
import time
from typing import Dict, Any, List, Tuple, Optional

from .base_processor import BaseProcessor
from .line_utils import build_line_like_entities
from .wall_candidate_constants import LOGIC_B_ANGULAR_TOLERANCE_DEG
from .units import (
    EPS_MM,
    EPS_OVERLAP_MM,
    LOGIC_B_MIN_CM,
    LOGIC_B_MAX_CM,
    cm_to_internal,
)


def _cross2(ax: float, ay: float, bx: float, by: float) -> float:
    """2D cross product (scalar): ax*by - ay*bx."""
    return ax * by - ay * bx


def _dot2(ax: float, ay: float, bx: float, by: float) -> float:
    """2D dot product."""
    return ax * bx + ay * by


def _normalize2(x: float, y: float) -> Tuple[float, float]:
    """Normalize 2D vector; returns (0,0) if length is zero."""
    L = math.sqrt(x * x + y * y)
    if L <= 0:
        return (0.0, 0.0)
    return (x / L, y / L)


def _point_to_segment_distance_xy(
    px: float, py: float,
    x1: float, y1: float, x2: float, y2: float
) -> float:
    """Distance from point (px,py) to segment (x1,y1)-(x2,y2) in XY."""
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq <= 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, _dot2(px - x1, py - y1, dx, dy) / len_sq))
    qx = x1 + t * dx
    qy = y1 + t * dy
    return math.hypot(px - qx, py - qy)


def _point_dict(x: float, y: float, z: float = 0.0) -> Dict[str, float]:
    return {"X": float(x), "Y": float(y), "Z": float(z)}


class LogicBProcessor(BaseProcessor):
    """Processor for LOGIC B wall pair detection (overlap-only, per-line trim)."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run LOGIC B on PARALLEL_NAIVE line-like entities."""
        self.log_info("Starting LOGIC B wall pair detection")
        start_time = time.time()

        parallel_results = pipeline_data.get("parallel_naive_results", {})
        entities_data = parallel_results.get("entities", {})
        parallel_ready_entities = entities_data.get("parallel_ready_entities", [])

        line_entities = build_line_like_entities(parallel_ready_entities)
        pairs = self._detect_logic_b_pairs(line_entities)

        duration_ms = int((time.time() - start_time) * 1000)
        min_mm = cm_to_internal(LOGIC_B_MIN_CM)
        max_mm = cm_to_internal(LOGIC_B_MAX_CM)
        self.update_metrics(
            duration_ms=duration_ms,
            entities_analyzed=len(line_entities),
            logic_b_pairs=len(pairs),
        )
        self.log_info(
            "LOGIC B completed",
            entities_analyzed=len(line_entities),
            logic_b_pairs=len(pairs),
            duration_ms=duration_ms,
        )

        return {
            "logic_b_pairs": pairs,
            "algorithm_config": {
                "angular_tolerance_deg": LOGIC_B_ANGULAR_TOLERANCE_DEG,
                "min_cm": LOGIC_B_MIN_CM,
                "max_cm": LOGIC_B_MAX_CM,
                "min_mm": min_mm,
                "max_mm": max_mm,
                "eps_mm": EPS_MM,
                "eps_overlap_mm": EPS_OVERLAP_MM,
            },
            "totals": {"logic_b_pairs": len(pairs)},
        }

    def _get_line_xy(
        self, entity: Dict[str, Any]
    ) -> Optional[Tuple[float, float, float, float, float, float, float, float, float]]:
        """Get (x1,y1,z1, x2,y2,z2, len, dx, dy) in XY; reject degenerate."""
        nd = entity.get("normalized_data", {})
        s = nd.get("Start", {})
        e = nd.get("End", {})
        x1 = float(s.get("X", 0))
        y1 = float(s.get("Y", 0))
        z1 = float(s.get("Z", 0))
        x2 = float(e.get("X", 0))
        y2 = float(e.get("Y", 0))
        z2 = float(e.get("Z", 0))
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < EPS_MM:
            return None
        return (x1, y1, z1, x2, y2, z2, length, dx, dy)

    def _are_parallel_stable(
        self,
        x1: float, y1: float, dx1: float, dy1: float,
        x2: float, y2: float, dx2: float, dy2: float,
    ) -> Tuple[bool, float, float, float, float, float, float]:
        """
        Canonicalize directions (flip d2 if dot<0) for shared axis d = normalize(d1+d2).
        Returns (parallel_ok, d_x, d_y, d1_x, d1_y, d2_x_orig, d2_y_orig).
        d2_orig is L2's actual segment direction (unflipped) for per-line reconstruction.
        Uses abs(cross2(d1,d2)) <= sin(thetaTol).
        """
        d1x, d1y = _normalize2(dx1, dy1)
        d2x, d2y = _normalize2(dx2, dy2)
        d2x_orig, d2y_orig = d2x, d2y
        dot = _dot2(d1x, d1y, d2x, d2y)
        if dot < 0:
            d2x, d2y = -d2x, -d2y
        cross = abs(_cross2(d1x, d1y, d2x, d2y))
        theta_rad = math.radians(LOGIC_B_ANGULAR_TOLERANCE_DEG)
        sin_tol = math.sin(theta_rad)
        if cross > sin_tol:
            return (False, 0.0, 0.0, d1x, d1y, d2x_orig, d2y_orig)
        dx = d1x + d2x
        dy = d1y + d2y
        d_shared = _normalize2(dx, dy)
        return (True, d_shared[0], d_shared[1], d1x, d1y, d2x_orig, d2y_orig)

    def _perpendicular_distance_xy(
        self, a0x: float, a0y: float, b0x: float, b0y: float, d2x: float, d2y: float
    ) -> float:
        """Distance from point a0 to line through b0 with unit direction d2 (XY). dist = |cross2(a0-b0, d2)|."""
        return abs(_cross2(a0x - b0x, a0y - b0y, d2x, d2y))

    def _detect_logic_b_pairs(self, line_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect LOGIC B pairs: parallel, distance in [1cm, 45cm], overlap-only trim, per-line reconstruction."""
        n = len(line_entities)
        seen_keys: set = set()
        pairs_out: List[Dict[str, Any]] = []
        min_mm = cm_to_internal(LOGIC_B_MIN_CM)
        max_mm = cm_to_internal(LOGIC_B_MAX_CM)

        for i in range(n):
            line_a = line_entities[i]
            data_a = self._get_line_xy(line_a)
            if data_a is None:
                continue
            x1a, y1a, z1a, x2a, y2a, z2a, len_a, dx_a, dy_a = data_a
            d1x, d1y = _normalize2(dx_a, dy_a)

            for j in range(i + 1, n):
                line_b = line_entities[j]
                data_b = self._get_line_xy(line_b)
                if data_b is None:
                    continue
                x1b, y1b, z1b, x2b, y2b, z2b, len_b, dx_b, dy_b = data_b
                d2x, d2y = _normalize2(dx_b, dy_b)

                parallel_ok, d_x, d_y, d1x_n, d1y_n, d2x_orig, d2y_orig = self._are_parallel_stable(
                    x1a, y1a, dx_a, dy_a, x1b, y1b, dx_b, dy_b
                )
                if not parallel_ok:
                    continue

                dist = self._perpendicular_distance_xy(x1a, y1a, x1b, y1b, d2x_orig, d2y_orig)
                if dist < min_mm or dist > max_mm:
                    continue

                # Overlap on shared axis d (d_x, d_y). Use O = (x1a, y1a)
                ox, oy = x1a, y1a
                s1_start = _dot2(x1a - ox, y1a - oy, d_x, d_y)
                s1_end = _dot2(x2a - ox, y2a - oy, d_x, d_y)
                min_a = min(s1_start, s1_end)
                max_a = max(s1_start, s1_end)
                s2_start = _dot2(x1b - ox, y1b - oy, d_x, d_y)
                s2_end = _dot2(x2b - ox, y2b - oy, d_x, d_y)
                min_b = min(s2_start, s2_end)
                max_b = max(s2_start, s2_end)
                overlap_min = max(min_a, min_b)
                overlap_max = min(max_a, max_b)
                if overlap_max <= overlap_min + EPS_OVERLAP_MM:
                    continue

                # Map overlap [overlap_min, overlap_max] to each line's parameter (per-line reconstruction)
                # L1: p = p1_L1 + u*d1  =>  s = dot(p1_L1 - O, d) + u*dot(d1, d)  =>  u = (s - s1_0) / dot(d1,d)
                s1_0 = _dot2(x1a - ox, y1a - oy, d_x, d_y)
                dd1 = _dot2(d1x_n, d1y_n, d_x, d_y)
                if abs(dd1) < 1e-12:
                    continue
                u_min = (overlap_min - s1_0) / dd1
                u_max = (overlap_max - s1_0) / dd1
                u_min_c = max(0.0, min(len_a, min(u_min, u_max)))
                u_max_c = max(0.0, min(len_a, max(u_min, u_max)))
                if u_max_c <= u_min_c + EPS_MM:
                    continue

                # L2: q = p1_L2 + v*d2  =>  v = (s - s2_0) / dot(d2, d)
                s2_0 = _dot2(x1b - ox, y1b - oy, d_x, d_y)
                dd2 = _dot2(d2x_orig, d2y_orig, d_x, d_y)
                if abs(dd2) < 1e-12:
                    continue
                v_min = (overlap_min - s2_0) / dd2
                v_max = (overlap_max - s2_0) / dd2
                v_min_c = max(0.0, min(len_b, min(v_min, v_max)))
                v_max_c = max(0.0, min(len_b, max(v_min, v_max)))
                if v_max_c <= v_min_c + EPS_MM:
                    continue

                # Reconstruct trimmed endpoints (per line: own origin and direction)
                p_a_start_x = x1a + u_min_c * d1x_n
                p_a_start_y = y1a + u_min_c * d1y_n
                p_a_end_x = x1a + u_max_c * d1x_n
                p_a_end_y = y1a + u_max_c * d1y_n
                p_b_start_x = x1b + v_min_c * d2x_orig
                p_b_start_y = y1b + v_min_c * d2y_orig
                p_b_end_x = x1b + v_max_c * d2x_orig
                p_b_end_y = y1b + v_max_c * d2y_orig

                # Invariants: trimmed on segment, within bbox+EPS
                if _point_to_segment_distance_xy(p_a_start_x, p_a_start_y, x1a, y1a, x2a, y2a) > EPS_MM:
                    self.log_error("LOGIC B invariant: A_start not on L1", id_a=line_a.get("entity_hash"), id_b=line_b.get("entity_hash"))
                    continue
                if _point_to_segment_distance_xy(p_a_end_x, p_a_end_y, x1a, y1a, x2a, y2a) > EPS_MM:
                    self.log_error("LOGIC B invariant: A_end not on L1", id_a=line_a.get("entity_hash"), id_b=line_b.get("entity_hash"))
                    continue
                if _point_to_segment_distance_xy(p_b_start_x, p_b_start_y, x1b, y1b, x2b, y2b) > EPS_MM:
                    self.log_error("LOGIC B invariant: B_start not on L2", id_a=line_a.get("entity_hash"), id_b=line_b.get("entity_hash"))
                    continue
                if _point_to_segment_distance_xy(p_b_end_x, p_b_end_y, x1b, y1b, x2b, y2b) > EPS_MM:
                    self.log_error("LOGIC B invariant: B_end not on L2", id_a=line_a.get("entity_hash"), id_b=line_b.get("entity_hash"))
                    continue

                id_a = line_a.get("entity_hash", "")
                id_b = line_b.get("entity_hash", "")
                # Dedup: same (A,B) and overlap interval (rounded to 0.1 mm)
                dedup_key = (min(id_a, id_b), max(id_a, id_b), round(overlap_min, 1), round(overlap_max, 1))
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                # Quad: A_start, A_end, B_end, B_start (closed)
                trimmed_a = {
                    "p1": _point_dict(p_a_start_x, p_a_start_y, z1a),
                    "p2": _point_dict(p_a_end_x, p_a_end_y, z1a),
                }
                trimmed_b = {
                    "p1": _point_dict(p_b_start_x, p_b_start_y, z1b),
                    "p2": _point_dict(p_b_end_x, p_b_end_y, z1b),
                }
                quad_corners = [
                    trimmed_a["p1"], trimmed_a["p2"], trimmed_b["p2"], trimmed_b["p1"]
                ]
                all_x = [p_a_start_x, p_a_end_x, p_b_start_x, p_b_end_x]
                all_y = [p_a_start_y, p_a_end_y, p_b_start_y, p_b_end_y]
                bounding_rectangle = {
                    "minX": min(all_x), "maxX": max(all_x),
                    "minY": min(all_y), "maxY": max(all_y),
                }

                pairs_out.append({
                    "pair_id": str(uuid.uuid4()),
                    "sourceLineIdA": id_a,
                    "sourceLineIdB": id_b,
                    "trimmedSegmentA": trimmed_a,
                    "trimmedSegmentB": trimmed_b,
                    "distance": dist,
                    "distance_cm": dist / 10.0,
                    "quad_corners": quad_corners,
                    "bounding_rectangle": bounding_rectangle,
                })

        return pairs_out
