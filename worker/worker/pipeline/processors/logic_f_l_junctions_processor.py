"""
LOGIC F processor – L-junction extension.

Detects orthogonal (≈90°) L-junctions between LOGIC_E rectangles (H↔V only),
computes center-line intersection X, and extends rectangles at most once so
center lines meet at X. Enforces MAX_EXTENSION_MM and MAX_JUNCTION_DISTANCE_MM.
"""

import copy
import math
import time
from typing import Dict, Any, List, Tuple, Optional

from .base_processor import BaseProcessor
from .wall_candidate_constants import (
    THICKNESS_MIN_MM,
    THICKNESS_MAX_MM,
    LOGIC_F_ANGLE_TOL_DEG,
    LOGIC_F_ANGLE_DOT_TOL,
    LOGIC_F_MAX_EXTENSION_MM,
    LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
)


def _unit(v: Tuple[float, float]) -> Tuple[float, float]:
    ax, ay = v[0], v[1]
    L = math.sqrt(ax * ax + ay * ay)
    if L <= 0:
        return (0.0, 0.0)
    return (ax / L, ay / L)


def _dot(u: Tuple[float, float], v: Tuple[float, float]) -> float:
    return u[0] * v[0] + u[1] * v[1]


def _dist(p: Tuple[float, float], q: Tuple[float, float]) -> float:
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def _perp(u: Tuple[float, float]) -> Tuple[float, float]:
    """Unit perpendicular: (-u.y, u.x) normalized."""
    return _unit((-u[1], u[0]))


def _distance_point_to_infinite_line(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    """Distance from point p to line through a, b."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    px, py = p[0], p[1]
    dx = bx - ax
    dy = by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 0:
        return _dist(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    qx = ax + t * dx
    qy = ay + t * dy
    return math.sqrt((px - qx) ** 2 + (py - qy) ** 2)


def _project_point_onto_infinite_line(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> Tuple[float, float]:
    """Project point p onto line through a, b."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    px, py = p[0], p[1]
    dx = bx - ax
    dy = by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 0:
        return (ax, ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    return (ax + t * dx, ay + t * dy)


def _line_intersection(
    a1: Tuple[float, float],
    a2: Tuple[float, float],
    b1: Tuple[float, float],
    b2: Tuple[float, float],
) -> Optional[Tuple[float, float]]:
    """Intersection of line through a1-a2 with line through b1-b2. Returns None if parallel."""
    x1, y1 = a1[0], a1[1]
    x2, y2 = a2[0], a2[1]
    x3, y3 = b1[0], b1[1]
    x4, y4 = b2[0], b2[1]
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _get_segment_points(rect: Dict[str, Any]) -> Optional[Tuple[Tuple[float, float], ...]]:
    """Return (A_p1, A_p2, B_p1, B_p2) from rect. Returns None if invalid."""
    a = rect.get("trimmedSegmentA") or {}
    b = rect.get("trimmedSegmentB") or {}
    ap1 = a.get("p1") or {}
    ap2 = a.get("p2") or {}
    bp1 = b.get("p1") or {}
    bp2 = b.get("p2") or {}
    A_p1 = (float(ap1.get("X", 0)), float(ap1.get("Y", 0)))
    A_p2 = (float(ap2.get("X", 0)), float(ap2.get("Y", 0)))
    B_p1 = (float(bp1.get("X", 0)), float(bp1.get("Y", 0)))
    B_p2 = (float(bp2.get("X", 0)), float(bp2.get("Y", 0)))
    return (A_p1, A_p2, B_p1, B_p2)


def _get_bounds(rect: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """Extract (xmin, ymin, xmax, ymax) from rect. Returns None if invalid."""
    pts = _get_segment_points(rect)
    if pts is None:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _infer_orientation(
    xmin: float, ymin: float, xmax: float, ymax: float,
    thickness_min: float, thickness_max: float,
) -> Optional[str]:
    """
    Infer 'H' (run axis X) or 'V' (run axis Y). Returns None if ineligible.
    H: runs along X (width >> height); V: runs along Y (height >> width).
    First uses thickness rules (same as LOGIC E). If that yields None (e.g. thickness
    outside 20–450 mm), fallback: use aspect ratio so elongated bands still get H/V
    for L-junction pairing (min side >= 1 mm to avoid degenerate).
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
        if dy <= dx:
            return "H"
        return "V"
    # Fallback: thickness out of range (e.g. different units or very thick walls).
    # Classify by aspect ratio so we still get H↔V pairs; require elongated (min >= 1).
    if dx < 1.0 and dy < 1.0:
        return None
    if dx >= dy:
        return "H"
    return "V"


def _distance_point_to_rect(
    p: Tuple[float, float],
    xmin: float, ymin: float, xmax: float, ymax: float,
) -> float:
    """Shortest Euclidean distance from point p to axis-aligned rectangle. 0 if inside."""
    px, py = p[0], p[1]
    dx = max(0.0, xmin - px, px - xmax)
    dy = max(0.0, ymin - py, py - ymax)
    return math.sqrt(dx * dx + dy * dy)


def _wall_representation(rect: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build internal wall representation from quad.
    Centerline c1 = (A.p1+B.p1)/2, c2 = (A.p2+B.p2)/2.
    Returns dict with c1, c2, u, n, w, ap1, ap2, bp1, bp2, a_is_plus_n.
    """
    pts = _get_segment_points(rect)
    if pts is None:
        return None
    A_p1, A_p2, B_p1, B_p2 = pts
    dA = (A_p2[0] - A_p1[0], A_p2[1] - A_p1[1])
    dB = (B_p2[0] - B_p1[0], B_p2[1] - B_p1[1])
    uA = _unit(dA)
    uB = _unit(dB)
    if _dot(uA, uB) < 0:
        B_p1, B_p2 = B_p2, B_p1
        dB = (B_p2[0] - B_p1[0], B_p2[1] - B_p1[1])
    c1 = ((A_p1[0] + B_p1[0]) / 2.0, (A_p1[1] + B_p1[1]) / 2.0)
    c2 = ((A_p2[0] + B_p2[0]) / 2.0, (A_p2[1] + B_p2[1]) / 2.0)
    u = _unit((c2[0] - c1[0], c2[1] - c1[1]))
    if u[0] == 0 and u[1] == 0:
        return None
    n = _perp(u)
    w_a_to_b = _distance_point_to_infinite_line(A_p1, B_p1, B_p2)
    w_b_to_a = _distance_point_to_infinite_line(B_p1, A_p1, A_p2)
    w = (w_a_to_b + w_b_to_a) / 2.0
    a_is_plus_n = _dot((A_p1[0] - c1[0], A_p1[1] - c1[1]), n) > 0
    return {
        "c1": c1,
        "c2": c2,
        "u": u,
        "n": n,
        "w": w,
        "ap1": A_p1,
        "ap2": A_p2,
        "bp1": B_p1,
        "bp2": B_p2,
        "a_is_plus_n": a_is_plus_n,
    }


def _apply_extension(
    out_rect: Dict[str, Any],
    wall_repr: Dict[str, Any],
    extend_c1: bool,
    c_end_new: Tuple[float, float],
) -> None:
    """Update out_rect in place: extend c1 end or c2 end to c_end_new."""
    n = wall_repr["n"]
    w = wall_repr["w"]
    A_end_new = (c_end_new[0] + n[0] * (w / 2.0), c_end_new[1] + n[1] * (w / 2.0))
    B_end_new = (c_end_new[0] - n[0] * (w / 2.0), c_end_new[1] - n[1] * (w / 2.0))
    seg_a = out_rect.setdefault("trimmedSegmentA", {})
    seg_b = out_rect.setdefault("trimmedSegmentB", {})
    if extend_c1:
        seg_a.setdefault("p1", {})["X"] = A_end_new[0]
        seg_a["p1"]["Y"] = A_end_new[1]
        seg_b.setdefault("p1", {})["X"] = B_end_new[0]
        seg_b["p1"]["Y"] = B_end_new[1]
    else:
        seg_a.setdefault("p2", {})["X"] = A_end_new[0]
        seg_a["p2"]["Y"] = A_end_new[1]
        seg_b.setdefault("p2", {})["X"] = B_end_new[0]
        seg_b["p2"]["Y"] = B_end_new[1]
    br = out_rect.get("bounding_rectangle")
    if br is not None and isinstance(br, dict):
        xs = [seg_a.get("p1", {}).get("X"), seg_a.get("p2", {}).get("X"), seg_b.get("p1", {}).get("X"), seg_b.get("p2", {}).get("X")]
        ys = [seg_a.get("p1", {}).get("Y"), seg_a.get("p2", {}).get("Y"), seg_b.get("p1", {}).get("Y"), seg_b.get("p2", {}).get("Y")]
        xs = [x for x in xs if x is not None]
        ys = [y for y in ys if y is not None]
        if xs and ys:
            br["minX"] = min(xs)
            br["maxX"] = max(xs)
            br["minY"] = min(ys)
            br["maxY"] = max(ys)


def _process_l_junctions(
    rectangles: List[Dict[str, Any]],
    max_extension_mm: float,
    max_junction_distance_mm: float,
    angle_dot_tol: float,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Detect L-junctions (H↔V, near-perpendicular), extend at most once per rectangle.
    Returns (logic_f_rectangles, num_candidates, num_accepted_pairs).
    """
    if not rectangles:
        return [], 0, 0

    n_rects = len(rectangles)
    # 2.1 Orientation inference
    orientations: List[Optional[str]] = []
    wall_reprs: List[Optional[Dict[str, Any]]] = []
    bounds_list: List[Optional[Tuple[float, float, float, float]]] = []

    for rect in rectangles:
        b = _get_bounds(rect)
        bounds_list.append(b)
        if b is None:
            orientations.append(None)
            wall_reprs.append(None)
            continue
        xmin, ymin, xmax, ymax = b
        orient = _infer_orientation(xmin, ymin, xmax, ymax, THICKNESS_MIN_MM, THICKNESS_MAX_MM)
        orientations.append(orient)
        wall_reprs.append(_wall_representation(rect))

    # 2.2–2.6 Collect valid candidates, score, sort, greedy accept
    # Candidate: (i, j, X, extend_c1_i, extend_c1_j, ext_len_i, ext_len_j, dist_i, dist_j, angular_err)
    candidates: List[Tuple[int, int, Tuple[float, float], bool, bool, float, float, float, float, float]] = []

    for i in range(n_rects):
        if orientations[i] is None or wall_reprs[i] is None or bounds_list[i] is None:
            continue
        for j in range(i + 1, n_rects):
            if orientations[j] is None or wall_reprs[j] is None or bounds_list[j] is None:
                continue
            # Only H↔V
            oi, oj = orientations[i], orientations[j]
            if oi == oj or (oi != "H" and oi != "V") or (oj != "H" and oj != "V"):
                continue

            wi, wj = wall_reprs[i], wall_reprs[j]
            if wi is None or wj is None:
                continue

            # 2.3 Near-perpendicularity
            if abs(_dot(wi["u"], wj["u"])) > angle_dot_tol:
                continue

            # 2.4 Junction point X
            X = _line_intersection(wi["c1"], wi["c2"], wj["c1"], wj["c2"])
            if X is None:
                continue

            xmin_i, ymin_i, xmax_i, ymax_i = bounds_list[i]
            xmin_j, ymin_j, xmax_j, ymax_j = bounds_list[j]

            # 2.5 Extension feasibility: for each rect, which end to extend, extension_length (along run axis), dist_to_rect
            def _feasibility(
                w: Dict[str, Any],
                xmin: float, ymin: float, xmax: float, ymax: float,
                orient: str,
            ) -> Optional[Tuple[bool, float, float]]:
                """Returns (extend_c1, extension_length, dist_to_rect) or None if infeasible."""
                c1, c2 = w["c1"], w["c2"]
                dist_to_rect = _distance_point_to_rect(X, xmin, ymin, xmax, ymax)
                if dist_to_rect > max_junction_distance_mm:
                    return None

                # Which end is closer to X? We extend that end toward X. Extension length = distance along run axis.
                if orient == "H":
                    run_axis = 0
                    end1_run, end2_run = c1[0], c2[0]
                else:
                    run_axis = 1
                    end1_run, end2_run = c1[1], c2[1]
                x_run = X[run_axis]
                ext_len_1 = abs(x_run - end1_run)
                ext_len_2 = abs(x_run - end2_run)
                if ext_len_1 <= ext_len_2:
                    extend_c1 = True
                    ext_len = ext_len_1
                else:
                    extend_c1 = False
                    ext_len = ext_len_2
                if ext_len > max_extension_mm:
                    return None
                return (extend_c1, ext_len, dist_to_rect)

            fi = _feasibility(wi, xmin_i, ymin_i, xmax_i, ymax_i, oi)
            fj = _feasibility(wj, xmin_j, ymin_j, xmax_j, ymax_j, oj)
            if fi is None or fj is None:
                continue

            extend_c1_i, ext_len_i, dist_i = fi
            extend_c1_j, ext_len_j, dist_j = fj

            # Angular error (degrees): |phi - 90°|; dot = cos(phi), so phi = acos(dot); for perpendicular phi=90°
            adot = abs(_dot(wi["u"], wj["u"]))
            angular_err = abs(math.degrees(math.acos(min(1.0, max(-1.0, adot)))) - 90.0) if adot <= 1.0 else 90.0

            score = angular_err + (ext_len_i + ext_len_j) + (dist_i + dist_j)
            candidates.append((i, j, X, extend_c1_i, extend_c1_j, ext_len_i, ext_len_j, dist_i, dist_j, score))

    # Sort by ascending score
    candidates.sort(key=lambda c: c[9])

    # Greedy accept: lock both indices on accept
    locked: set = set()
    accepted: List[Tuple[int, int, Tuple[float, float], bool, bool]] = []

    for c in candidates:
        i, j, X, extend_c1_i, extend_c1_j, _, _, _, _, _ = c
        if i in locked or j in locked:
            continue
        accepted.append((i, j, X, extend_c1_i, extend_c1_j))
        locked.add(i)
        locked.add(j)

    # 2.7–2.8 Output assembly
    output = [copy.deepcopy(rect) for rect in rectangles]
    extended_indices = set()
    junction_point_by_index: Dict[int, List[float]] = {}

    for (i, j, X, extend_c1_i, extend_c1_j) in accepted:
        wi, wj = wall_reprs[i], wall_reprs[j]
        if wi is None or wj is None:
            continue
        # Project X onto each rectangle's center line so the extended segment stays
        # exactly on that line (axis-aligned). Using X directly can put the new end
        # slightly off the line due to floating point, producing a diagonal segment.
        c_end_new_i = _project_point_onto_infinite_line(X, wi["c1"], wi["c2"])
        c_end_new_j = _project_point_onto_infinite_line(X, wj["c1"], wj["c2"])
        _apply_extension(output[i], wi, extend_c1_i, c_end_new_i)
        extended_indices.add(i)
        junction_point_by_index[i] = [c_end_new_i[0], c_end_new_i[1]]
        _apply_extension(output[j], wj, extend_c1_j, c_end_new_j)
        extended_indices.add(j)
        junction_point_by_index[j] = [c_end_new_j[0], c_end_new_j[1]]

    for idx in range(n_rects):
        r = output[idx]
        if idx in extended_indices:
            r["extended"] = True
            r["junction_type"] = "L"
            r["junction_point"] = junction_point_by_index[idx]
        else:
            r["extended"] = False
            # Do not add junction_point for non-extended

    num_extended = len(extended_indices)
    return output, len(candidates), len(accepted)


class LogicFProcessor(BaseProcessor):
    """LOGIC F: extend L-junction walls to close corner gaps. At most once per rectangle."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("Starting LOGIC F (L-junction extension)")
        start_time = time.time()

        logic_e_results = pipeline_data.get("logic_e_results", {})
        logic_e_rectangles = logic_e_results.get("logic_e_rectangles") or []

        if not logic_e_rectangles:
            duration_ms = int((time.time() - start_time) * 1000)
            self.update_metrics(
                duration_ms=duration_ms,
                logic_e_input_count=0,
                logic_f_rectangles=0,
                num_candidates=0,
                num_accepted_pairs=0,
                num_extended_rectangles=0,
            )
            self.log_info("LOGIC F completed (no input)", logic_f_rectangles=0, duration_ms=duration_ms)
            return {
                "logic_f_rectangles": [],
                "algorithm_config": {
                    "logic_f_angle_tol_deg": LOGIC_F_ANGLE_TOL_DEG,
                    "logic_f_angle_dot_tol": LOGIC_F_ANGLE_DOT_TOL,
                    "logic_f_max_extension_mm": LOGIC_F_MAX_EXTENSION_MM,
                    "logic_f_max_junction_distance_mm": LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
                },
                "totals": {
                    "num_input": 0,
                    "num_candidates": 0,
                    "num_accepted_pairs": 0,
                    "num_extended_rectangles": 0,
                },
            }

        output, num_candidates, num_accepted_pairs = _process_l_junctions(
            logic_e_rectangles,
            max_extension_mm=LOGIC_F_MAX_EXTENSION_MM,
            max_junction_distance_mm=LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            angle_dot_tol=LOGIC_F_ANGLE_DOT_TOL,
        )
        num_extended = sum(1 for r in output if r.get("extended") is True)
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            logic_e_input_count=len(logic_e_rectangles),
            logic_f_rectangles=len(output),
            num_candidates=num_candidates,
            num_accepted_pairs=num_accepted_pairs,
            num_extended_rectangles=num_extended,
        )
        self.log_info(
            "LOGIC F completed",
            logic_e_input_count=len(logic_e_rectangles),
            logic_f_rectangles=len(output),
            num_extended_rectangles=num_extended,
            duration_ms=duration_ms,
        )
        return {
            "logic_f_rectangles": output,
            "algorithm_config": {
                "logic_f_angle_tol_deg": LOGIC_F_ANGLE_TOL_DEG,
                "logic_f_angle_dot_tol": LOGIC_F_ANGLE_DOT_TOL,
                "logic_f_max_extension_mm": LOGIC_F_MAX_EXTENSION_MM,
                "logic_f_max_junction_distance_mm": LOGIC_F_MAX_JUNCTION_DISTANCE_MM,
            },
            "totals": {
                "num_input": len(logic_e_rectangles),
                "num_candidates": num_candidates,
                "num_accepted_pairs": num_accepted_pairs,
                "num_extended_rectangles": num_extended,
            },
        }
