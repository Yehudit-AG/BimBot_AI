"""
Base adapter class for geometry processing with deterministic ID generation.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from shapely.geometry import Point, LineString, Polygon


class BaseAdapter(ABC):
    """Base class for all geometry adapters."""
    
    # Fixed epsilon for float normalization to ensure deterministic results
    EPSILON = 1e-6
    
    def __init__(self):
        self.processed_count = 0
        self.duplicate_count = 0
        self.error_count = 0
    
    @abstractmethod
    def process_entities(self, entities: List[Dict[str, Any]], layer_name: str) -> List[Dict[str, Any]]:
        """Process a list of entities and return normalized entities with deterministic IDs."""
        pass
    
    def normalize_coordinate(self, value: float) -> float:
        """Normalize a coordinate value using fixed epsilon."""
        return round(value / self.EPSILON) * self.EPSILON
    
    def normalize_point(self, point: Dict[str, float]) -> Dict[str, float]:
        """Normalize a 3D point."""
        return {
            'X': self.normalize_coordinate(point.get('X', 0.0)),
            'Y': self.normalize_coordinate(point.get('Y', 0.0)),
            'Z': self.normalize_coordinate(point.get('Z', 0.0))
        }
    
    def generate_entity_id(self, layer_name: str, entity_type: str, 
                          geometry_data: Dict[str, Any], block_name: Optional[str] = None) -> str:
        """Generate deterministic entity ID based on layer, type, geometry, and optional block name."""
        # Create a consistent string representation for hashing
        id_components = [
            layer_name,
            entity_type,
            json.dumps(geometry_data, sort_keys=True)
        ]
        
        if block_name:
            id_components.append(block_name)
        
        # Create hash from components
        id_string = '|'.join(id_components)
        return hashlib.sha256(id_string.encode('utf-8')).hexdigest()
    
    def calculate_bounding_box(self, geometry_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Calculate bounding box for geometry data."""
        try:
            points = self.extract_points_from_geometry(geometry_data)
            if not points:
                return None
            
            x_coords = [p['X'] for p in points]
            y_coords = [p['Y'] for p in points]
            z_coords = [p['Z'] for p in points]
            
            return {
                'MinPoint': {
                    'X': min(x_coords),
                    'Y': min(y_coords),
                    'Z': min(z_coords)
                },
                'MaxPoint': {
                    'X': max(x_coords),
                    'Y': max(y_coords),
                    'Z': max(z_coords)
                }
            }
        except Exception:
            return None
    
    @abstractmethod
    def extract_points_from_geometry(self, geometry_data: Dict[str, Any]) -> List[Dict[str, float]]:
        """Extract all points from geometry data for bounding box calculation."""
        pass
    
    def validate_geometry(self, geometry_data: Dict[str, Any]) -> bool:
        """Validate geometry data structure."""
        try:
            points = self.extract_points_from_geometry(geometry_data)
            return len(points) > 0
        except Exception:
            return False
    
    def get_processing_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        return {
            'processed_count': self.processed_count,
            'duplicate_count': self.duplicate_count,
            'error_count': self.error_count
        }
    
    def reset_stats(self):
        """Reset processing statistics."""
        self.processed_count = 0
        self.duplicate_count = 0
        self.error_count = 0