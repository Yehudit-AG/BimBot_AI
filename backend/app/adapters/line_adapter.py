"""
Line adapter for processing LINE entities with epsilon-based deduplication.
"""

from typing import Any, Dict, List, Set
from .base_adapter import BaseAdapter


class LineAdapter(BaseAdapter):
    """Adapter for processing LINE entities."""
    
    def __init__(self):
        super().__init__()
        self.seen_hashes: Set[str] = set()
    
    def process_entities(self, entities: List[Dict[str, Any]], layer_name: str) -> List[Dict[str, Any]]:
        """Process LINE entities with deduplication and normalization."""
        processed_entities = []
        
        for entity in entities:
            try:
                # Validate required fields
                if not self._validate_line_entity(entity):
                    self.error_count += 1
                    continue
                
                # Normalize geometry
                normalized_geometry = self._normalize_line_geometry(entity)
                
                # Generate deterministic ID
                entity_id = self.generate_entity_id(
                    layer_name=layer_name,
                    entity_type='LINE',
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
                    'entity_type': 'LINE',
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
    
    def _validate_line_entity(self, entity: Dict[str, Any]) -> bool:
        """Validate LINE entity structure."""
        required_fields = ['Start', 'End']
        
        for field in required_fields:
            if field not in entity:
                return False
            
            point = entity[field]
            if not isinstance(point, dict):
                return False
            
            # Check for X, Y coordinates (Z is optional)
            if 'X' not in point or 'Y' not in point:
                return False
            
            # Validate coordinate types
            try:
                float(point['X'])
                float(point['Y'])
                if 'Z' in point:
                    float(point['Z'])
            except (ValueError, TypeError):
                return False
        
        return True
    
    def _normalize_line_geometry(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize LINE geometry coordinates."""
        return {
            'Start': self.normalize_point(entity['Start']),
            'End': self.normalize_point(entity['End'])
        }
    
    def extract_points_from_geometry(self, geometry_data: Dict[str, Any]) -> List[Dict[str, float]]:
        """Extract points from LINE geometry."""
        points = []
        
        if 'Start' in geometry_data:
            points.append(geometry_data['Start'])
        
        if 'End' in geometry_data:
            points.append(geometry_data['End'])
        
        return points
    
    def calculate_line_length(self, geometry_data: Dict[str, Any]) -> float:
        """Calculate the length of a line."""
        try:
            start = geometry_data['Start']
            end = geometry_data['End']
            
            dx = end['X'] - start['X']
            dy = end['Y'] - start['Y']
            dz = end.get('Z', 0) - start.get('Z', 0)
            
            return (dx**2 + dy**2 + dz**2)**0.5
        except Exception:
            return 0.0
    
    def is_horizontal_line(self, geometry_data: Dict[str, Any], tolerance: float = None) -> bool:
        """Check if line is horizontal within tolerance."""
        if tolerance is None:
            tolerance = self.EPSILON
        
        try:
            start = geometry_data['Start']
            end = geometry_data['End']
            
            dy = abs(end['Y'] - start['Y'])
            return dy <= tolerance
        except Exception:
            return False
    
    def is_vertical_line(self, geometry_data: Dict[str, Any], tolerance: float = None) -> bool:
        """Check if line is vertical within tolerance."""
        if tolerance is None:
            tolerance = self.EPSILON
        
        try:
            start = geometry_data['Start']
            end = geometry_data['End']
            
            dx = abs(end['X'] - start['X'])
            return dx <= tolerance
        except Exception:
            return False
    
    def get_line_angle(self, geometry_data: Dict[str, Any]) -> float:
        """Get the angle of the line in radians."""
        try:
            start = geometry_data['Start']
            end = geometry_data['End']
            
            dx = end['X'] - start['X']
            dy = end['Y'] - start['Y']
            
            import math
            return math.atan2(dy, dx)
        except Exception:
            return 0.0