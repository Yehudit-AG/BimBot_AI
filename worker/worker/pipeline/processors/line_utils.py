"""
Shared line-building utilities for pipeline processors.

Builds a flat list of line-like entities (LINE + polyline segments)
with stable IDs for use by WallCandidatesProcessor and LogicBProcessor.
"""

from typing import Dict, Any, List


def build_line_like_entities(parallel_ready_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build line-like list: all LINEs plus each polyline segment as a virtual LINE."""
    out: List[Dict[str, Any]] = []
    for entity in parallel_ready_entities:
        etype = entity.get("entity_type")
        if etype == "LINE":
            out.append(entity)
        elif etype == "POLYLINE":
            nd = entity.get("normalized_data", {})
            vertices = nd.get("Vertices", [])
            base_hash = entity.get("entity_hash") or ""
            layer_name = entity.get("layer_name", "")
            for i in range(len(vertices) - 1):
                seg = {
                    "entity_type": "LINE",
                    "entity_hash": f"{base_hash}_seg_{i}",
                    "layer_name": layer_name,
                    "normalized_data": {
                        "Start": vertices[i],
                        "End": vertices[i + 1],
                    },
                }
                out.append(seg)
    return out
