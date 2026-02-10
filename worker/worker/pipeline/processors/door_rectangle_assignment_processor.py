"""
DOOR_RECTANGLE_ASSIGNMENT processor – Associate Logic E rectangles with doors by AABB intersection.

Filters doors from window_door_blocks, computes each door's world building box, finds all
Logic E rectangles that intersect each door box, and outputs a per-door summary for the next stage.
"""

import math
import time
from typing import Dict, Any, List, Tuple, Optional

from .base_processor import BaseProcessor
from .logic_e_adjacent_merge_processor import _get_bounds

# Expand door bbox by this margin (mm) on all sides before intersecting with Logic E rectangles
DOOR_BBOX_EXPAND_MM = 200.0  # 20 cm


def _expand_bbox(bbox: Tuple[float, float, float, float], margin_mm: float) -> Tuple[float, float, float, float]:
    """Expand AABB (xmin, ymin, xmax, ymax) by margin_mm on all sides."""
    xmin, ymin, xmax, ymax = bbox
    return (xmin - margin_mm, ymin - margin_mm, xmax + margin_mm, ymax + margin_mm)


def _rotation_to_degrees_90(block_data: Dict[str, Any]) -> float:
    """Get rotation from block data and snap to 0, 90, 180, 270 degrees."""
    rot = block_data.get("Rotation") or block_data.get("rotate")
    if rot is None:
        return 0.0
    deg = float(rot)
    if abs(deg) > 360 and abs(deg) <= 4000:
        deg = deg * (360.0 / 4000.0)
    deg = deg % 360.0
    snap = round(deg / 90.0) * 90.0
    return snap % 360.0


def _get_door_world_bbox(block_data: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """
    Compute world AABB for a door block from BoundingBox, Position, Rotation.
    Returns (xmin, ymin, xmax, ymax) or None if invalid.
    """
    bbox = block_data.get("BoundingBox") or {}
    min_pt = bbox.get("MinPoint") or {}
    max_pt = bbox.get("MaxPoint") or {}
    if not min_pt or not max_pt:
        return None
    min_x = float(min_pt.get("X", 0))
    min_y = float(min_pt.get("Y", 0))
    max_x = float(max_pt.get("X", 0))
    max_y = float(max_pt.get("Y", 0))
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    pos = block_data.get("Position") or {}
    px = float(pos.get("X", cx))
    py = float(pos.get("Y", cy))
    angle_deg = _rotation_to_degrees_90(block_data)
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    def rotate(x: float, y: float) -> Tuple[float, float]:
        dx, dy = x - cx, y - cy
        rx = cx + dx * cos_a - dy * sin_a
        ry = cy + dx * sin_a + dy * cos_a
        return (rx + (px - cx), ry + (py - cy))

    corners = [
        rotate(min_x, min_y),
        rotate(max_x, min_y),
        rotate(max_x, max_y),
        rotate(min_x, max_y),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def _aabb_intersects(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
) -> bool:
    """True if AABB a overlaps AABB b (positive overlap in both axes)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def _compute_assignments(
    doors: List[Dict[str, Any]],
    logic_e_rectangles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    For each door, expand its world bbox by DOOR_BBOX_EXPAND_MM on all sides, then find
    indices of all Logic E rectangles that intersect the expanded bbox.
    Returns list of { doorId, doorType, rectanglesCount, rectangleIndices }.
    """
    assignments: List[Dict[str, Any]] = []
    for door_idx, block in enumerate(doors):
        data = block.get("data") or {}
        door_bbox = _get_door_world_bbox(data)
        if door_bbox is None:
            assignments.append({
                "doorId": door_idx,
                "doorType": block.get("layer_name") or "door",
                "rectanglesCount": 0,
                "rectangleIndices": [],
            })
            continue
        expanded_bbox = _expand_bbox(door_bbox, DOOR_BBOX_EXPAND_MM)
        indices: List[int] = []
        for rect_idx, rect in enumerate(logic_e_rectangles):
            rect_bounds = _get_bounds(rect)
            if rect_bounds is None:
                continue
            if _aabb_intersects(expanded_bbox, rect_bounds):
                indices.append(rect_idx)
        assignments.append({
            "doorId": door_idx,
            "doorType": block.get("layer_name") or "door",
            "rectanglesCount": len(indices),
            "rectangleIndices": indices,
        })
    return assignments


class DoorRectangleAssignmentProcessor(BaseProcessor):
    """Associate Logic E rectangles with doors by geometric intersection with each door's building box."""

    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("Starting DOOR_RECTANGLE_ASSIGNMENT")
        start_time = time.time()

        window_door_blocks = pipeline_data.get("window_door_blocks") or []
        doors = [b for b in window_door_blocks if b.get("window_or_door") == "door"]

        logic_e_results = pipeline_data.get("logic_e_results", {})
        logic_e_rectangles = logic_e_results.get("logic_e_rectangles") or []

        if not logic_e_rectangles:
            duration_ms = int((time.time() - start_time) * 1000)
            self.update_metrics(
                duration_ms=duration_ms,
                doors_processed=len(doors),
                total_assignments=0,
                rectangles_matched=0,
            )
            self.log_info(
                "DOOR_RECTANGLE_ASSIGNMENT completed (no Logic E rectangles)",
                doors_processed=len(doors),
                duration_ms=duration_ms,
            )
            return {
                "door_assignments": [
                    {
                        "doorId": i,
                        "doorType": b.get("layer_name") or "door",
                        "rectanglesCount": 0,
                        "rectangleIndices": [],
                    }
                    for i, b in enumerate(doors)
                ],
                "algorithm_config": {"door_bbox_expand_mm": DOOR_BBOX_EXPAND_MM},
                "totals": {
                    "doors_processed": len(doors),
                    "total_assignments": 0,
                    "rectangles_matched": 0,
                },
            }

        door_assignments = _compute_assignments(doors, logic_e_rectangles)
        total_assignments = sum(a["rectanglesCount"] for a in door_assignments)
        rectangles_matched = len(set(idx for a in door_assignments for idx in a["rectangleIndices"]))

        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            doors_processed=len(doors),
            total_assignments=total_assignments,
            rectangles_matched=rectangles_matched,
        )
        self.log_info(
            "DOOR_RECTANGLE_ASSIGNMENT completed",
            doors_processed=len(doors),
            logic_e_rectangles=len(logic_e_rectangles),
            total_assignments=total_assignments,
            duration_ms=duration_ms,
        )
        return {
            "door_assignments": door_assignments,
            "algorithm_config": {"door_bbox_expand_mm": DOOR_BBOX_EXPAND_MM},
            "totals": {
                "doors_processed": len(doors),
                "total_assignments": total_assignments,
                "rectangles_matched": rectangles_matched,
            },
        }
