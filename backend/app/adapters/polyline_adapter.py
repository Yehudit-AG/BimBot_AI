"""
Polyline adapter for processing POLYLINE entities.
Ready for future polyline support (currently handles empty arrays).
"""

from typing import Any, Dict, List, Set
from .base_adapter import BaseAdapter


class PolylineAdapter(BaseAdapter):
    """Adapter for processing POLYLINE entities."""
    
    def __init__(self):
        super().__init__()
        self.seen_hashes: Set[str] = set()
    
    def process_entities(self, entities: List[Dict[str, Any]], layer_name: str) -> List[Dict[str, Any]]:
        """Process POLYLINE entities with deduplication and normalization."""
        processed_entities = []
        
        # Handle empty polyline arrays (current state in JSON)
        if not entities:
            return processed_entities
        
        for entity in entities:
            try:
                # Validate required fields
                if not self._validate_polyline_entity(entity):
                    self.error_count += 1
                    continue
                
                # Normalize geometry
                normalized_geometry = self._normalize_polyline_geometry(entity)
                
                # Generate deterministic ID
                entity_id = self.generate_entity_id(
                    layer_name=layer_name,
                    entity_type='POLYLINE',
                    geometry_data=normalized_geometry
                )
                
                # Check for duplicates
                if entity_id in self.seen_hashes:
                    self.duplicate_count += 1
                    continue
                
                self.seen_hashes.add(entity_id)
                
                # Calculate bounding box
                bounding_box = self.calculate_bounding_box(normalized_geometry)
                
                # Create processed entity
                processed_entity = {
                    'entity_hash': entity_id,
                    'layer_name': layer_name,
                    'entity_type': 'POLYLINE',
                    'geometry_data': entity,  # Original data
                    'normalized_geometry': normalized_geometry,
                    'bounding_box': bounding_box
                }
                
                processed_entities.append(processed_entity)
                self.processed_count += 1
                
            except Exception as e:
                self.error_count += 1
                # Log error in production
                continue
        
        return processed_entities
    
    def _validate_polyline_entity(self, entity: Dict[str, Any]) -> bool:
        """Validate POLYLINE entity structure."""
        # Expected structure for future polyline support
        if 'Vertices' not in entity:
            return False
        
        vertices = entity['Vertices']
        if not isinstance(vertices, list):
            return False
        
        # Must have at least 2 vertices for a valid polyline
        if len(vertices) < 2:
            return False
        
        # Validate each vertex
        for vertex in vertices:
            if not isinstance(vertex, dict):
                return False
            
            # Check for X, Y coordinates (Z is optional)
            if 'X' not in vertex or 'Y' not in vertex:
                return False
            
            # Validate coordinate types
            try:
                float(vertex['X'])
                float(vertex['Y'])
                if 'Z' in vertex:
                    float(vertex['Z'])
            except (ValueError, TypeError):
                return False
        
        return True
    
    def _normalize_polyline_geometry(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize POLYLINE geometry coordinates."""
        normalized_vertices = []
        
        for vertex in entity.get('Vertices', []):
            normalized_vertices.append(self.normalize_point(vertex))
        
        return {
            'Vertices': normalized_vertices,
            'IsClosed': entity.get('IsClosed', False)
        }
    
    def extract_points_from_geometry(self, geometry_data: Dict[str, Any]) -> List[Dict[str, float]]:
        """Extract points from POLYLINE geometry."""
        return geometry_data.get('Vertices', [])
    
    def calculate_polyline_length(self, geometry_data: Dict[str, Any]) -> float:
        """Calculate the total length of a polyline."""
        try:
            vertices = geometry_data.get('Vertices', [])
            if len(vertices) < 2:
                return 0.0
            
            total_length = 0.0
            
            for i in range(len(vertices) - 1):
                start = vertices[i]
                end = vertices[i + 1]
                
                dx = end['X'] - start['X']
                dy = end['Y'] - start['Y']
                dz = end.get('Z', 0) - start.get('Z', 0)
                
                segment_length = (dx**2 + dy**2 + dz**2)**0.5
                total_length += segment_length
            
            # If closed, add distance from last to first vertex
            if geometry_data.get('IsClosed', False) and len(vertices) > 2:
                start = vertices[-1]
                end = vertices[0]
                
                dx = end['X'] - start['X']
                dy = end['Y'] - start['Y']
                dz = end.get('Z', 0) - start.get('Z', 0)
                
                closing_length = (dx**2 + dy**2 + dz**2)**0.5
                total_length += closing_length
            
            return total_length
        except Exception:
            return 0.0
    
    def get_polyline_segments(self, geometry_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get individual line segments from polyline."""
        segments = []
        
        try:
            vertices = geometry_data.get('Vertices', [])
            if len(vertices) < 2:
                return segments
            
            for i in range(len(vertices) - 1):
                segment = {
                    'Start': vertices[i],
                    'End': vertices[i + 1]
                }
                segments.append(segment)
            
            # If closed, add closing segment
            if geometry_data.get('IsClosed', False) and len(vertices) > 2:
                closing_segment = {
                    'Start': vertices[-1],
                    'End': vertices[0]
                }
                segments.append(closing_segment)
            
            return segments
        except Exception:
            return []
    
    def simplify_polyline(self, geometry_data: Dict[str, Any], tolerance: float = None) -> Dict[str, Any]:
        """Simplify polyline by removing redundant vertices."""
        if tolerance is None:
            tolerance = self.EPSILON * 10  # Slightly larger tolerance for simplification
        
        try:
            vertices = geometry_data.get('Vertices', [])
            if len(vertices) <= 2:
                return geometry_data
            
            simplified_vertices = [vertices[0]]  # Always keep first vertex
            
            for i in range(1, len(vertices) - 1):
                # Check if current vertex is collinear with previous and next
                prev_vertex = simplified_vertices[-1]
                curr_vertex = vertices[i]
                next_vertex = vertices[i + 1]
                
                if not self._is_collinear(prev_vertex, curr_vertex, next_vertex, tolerance):
                    simplified_vertices.append(curr_vertex)
            
            simplified_vertices.append(vertices[-1])  # Always keep last vertex
            
            return {
                'Vertices': simplified_vertices,
                'IsClosed': geometry_data.get('IsClosed', False)
            }
        except Exception:
            return geometry_data
    
    def _is_collinear(self, p1: Dict[str, float], p2: Dict[str, float], 
                     p3: Dict[str, float], tolerance: float) -> bool:
        """Check if three points are collinear within tolerance."""
        try:
            # Calculate cross product to determine collinearity
            dx1 = p2['X'] - p1['X']
            dy1 = p2['Y'] - p1['Y']
            dx2 = p3['X'] - p2['X']
            dy2 = p3['Y'] - p2['Y']
            
            cross_product = abs(dx1 * dy2 - dy1 * dx2)
            return cross_product <= tolerance
        except Exception:
            return False