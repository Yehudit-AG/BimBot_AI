"""
Block adapter for processing BLOCK entities with bounding box validation.
Handles Hebrew block names and special characters.
"""

from typing import Any, Dict, List, Set
from .base_adapter import BaseAdapter


class BlockAdapter(BaseAdapter):
    """Adapter for processing BLOCK entities."""
    
    def __init__(self):
        super().__init__()
        self.seen_hashes: Set[str] = set()
    
    def process_entities(self, entities: List[Dict[str, Any]], layer_name: str) -> List[Dict[str, Any]]:
        """Process BLOCK entities with deduplication and normalization."""
        processed_entities = []
        
        for entity in entities:
            try:
                # Validate required fields
                if not self._validate_block_entity(entity):
                    self.error_count += 1
                    continue
                
                # Normalize geometry
                normalized_geometry = self._normalize_block_geometry(entity)
                
                # Generate deterministic ID including block name
                entity_id = self.generate_entity_id(
                    layer_name=layer_name,
                    entity_type='BLOCK',
                    geometry_data=normalized_geometry,
                    block_name=entity.get('Name', '')
                )
                
                # Check for duplicates
                if entity_id in self.seen_hashes:
                    self.duplicate_count += 1
                    continue
                
                self.seen_hashes.add(entity_id)
                
                # Use provided bounding box or calculate if missing
                bounding_box = entity.get('BoundingBox')
                if not bounding_box:
                    bounding_box = self.calculate_bounding_box(normalized_geometry)
                else:
                    # Normalize the provided bounding box
                    bounding_box = self._normalize_bounding_box(bounding_box)
                
                # Create processed entity
                processed_entity = {
                    'entity_hash': entity_id,
                    'layer_name': layer_name,
                    'entity_type': 'BLOCK',
                    'geometry_data': entity,  # Original data
                    'normalized_geometry': normalized_geometry,
                    'bounding_box': bounding_box,
                    'block_name': entity.get('Name', ''),
                    'block_metadata': self._extract_block_metadata(entity)
                }
                
                processed_entities.append(processed_entity)
                self.processed_count += 1
                
            except Exception as e:
                self.error_count += 1
                # Log error in production
                continue
        
        return processed_entities
    
    def _validate_block_entity(self, entity: Dict[str, Any]) -> bool:
        """Validate BLOCK entity structure."""
        required_fields = ['Position']
        
        for field in required_fields:
            if field not in entity:
                return False
        
        # Validate position
        position = entity['Position']
        if not isinstance(position, dict):
            return False
        
        # Check for X, Y coordinates (Z is optional)
        if 'X' not in position or 'Y' not in position:
            return False
        
        # Validate coordinate types
        try:
            float(position['X'])
            float(position['Y'])
            if 'Z' in position:
                float(position['Z'])
        except (ValueError, TypeError):
            return False
        
        # Validate optional numeric fields
        numeric_fields = ['Rotation', 'ScaleX', 'ScaleY']
        for field in numeric_fields:
            if field in entity:
                try:
                    float(entity[field])
                except (ValueError, TypeError):
                    return False
        
        # Validate bounding box if present
        if 'BoundingBox' in entity:
            bbox = entity['BoundingBox']
            if not isinstance(bbox, dict):
                return False
            
            required_bbox_fields = ['MinPoint', 'MaxPoint']
            for bbox_field in required_bbox_fields:
                if bbox_field not in bbox:
                    return False
                
                point = bbox[bbox_field]
                if not isinstance(point, dict):
                    return False
                
                if 'X' not in point or 'Y' not in point:
                    return False
                
                try:
                    float(point['X'])
                    float(point['Y'])
                    if 'Z' in point:
                        float(point['Z'])
                except (ValueError, TypeError):
                    return False
        
        return True
    
    def _normalize_block_geometry(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize BLOCK geometry coordinates."""
        normalized = {
            'Position': self.normalize_point(entity['Position']),
            'Rotation': entity.get('Rotation', 0.0),
            'ScaleX': entity.get('ScaleX', 1.0),
            'ScaleY': entity.get('ScaleY', 1.0)
        }
        
        # Normalize bounding box if present
        if 'BoundingBox' in entity:
            normalized['BoundingBox'] = self._normalize_bounding_box(entity['BoundingBox'])
        
        return normalized
    
    def _normalize_bounding_box(self, bbox: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize bounding box coordinates."""
        return {
            'MinPoint': self.normalize_point(bbox['MinPoint']),
            'MaxPoint': self.normalize_point(bbox['MaxPoint'])
        }
    
    def extract_points_from_geometry(self, geometry_data: Dict[str, Any]) -> List[Dict[str, float]]:
        """Extract points from BLOCK geometry."""
        points = [geometry_data['Position']]
        
        # Add bounding box points if available
        if 'BoundingBox' in geometry_data:
            bbox = geometry_data['BoundingBox']
            points.extend([bbox['MinPoint'], bbox['MaxPoint']])
        
        return points
    
    def _extract_block_metadata(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from block entity."""
        metadata = {}
        
        # Block name (with Unicode support)
        if 'Name' in entity:
            metadata['name'] = entity['Name']
            metadata['name_length'] = len(entity['Name'])
            metadata['has_hebrew'] = self._contains_hebrew(entity['Name'])
        
        # Transformation info
        metadata['rotation'] = entity.get('Rotation', 0.0)
        metadata['scale_x'] = entity.get('ScaleX', 1.0)
        metadata['scale_y'] = entity.get('ScaleY', 1.0)
        metadata['is_scaled'] = (
            abs(entity.get('ScaleX', 1.0) - 1.0) > self.EPSILON or
            abs(entity.get('ScaleY', 1.0) - 1.0) > self.EPSILON
        )
        metadata['is_rotated'] = abs(entity.get('Rotation', 0.0)) > self.EPSILON
        
        # Bounding box info
        if 'BoundingBox' in entity:
            bbox = entity['BoundingBox']
            min_pt = bbox['MinPoint']
            max_pt = bbox['MaxPoint']
            
            metadata['width'] = abs(max_pt['X'] - min_pt['X'])
            metadata['height'] = abs(max_pt['Y'] - min_pt['Y'])
            metadata['depth'] = abs(max_pt.get('Z', 0) - min_pt.get('Z', 0))
            metadata['area'] = metadata['width'] * metadata['height']
        
        return metadata
    
    def _contains_hebrew(self, text: str) -> bool:
        """Check if text contains Hebrew characters."""
        if not text:
            return False
        
        # Hebrew Unicode range: U+0590 to U+05FF
        for char in text:
            if '\u0590' <= char <= '\u05FF':
                return True
        return False
    
    def get_block_center(self, geometry_data: Dict[str, Any]) -> Dict[str, float]:
        """Get the center point of the block."""
        if 'BoundingBox' in geometry_data:
            bbox = geometry_data['BoundingBox']
            min_pt = bbox['MinPoint']
            max_pt = bbox['MaxPoint']
            
            return {
                'X': (min_pt['X'] + max_pt['X']) / 2,
                'Y': (min_pt['Y'] + max_pt['Y']) / 2,
                'Z': (min_pt.get('Z', 0) + max_pt.get('Z', 0)) / 2
            }
        else:
            # Use position as center if no bounding box
            return geometry_data['Position'].copy()
    
    def get_block_dimensions(self, geometry_data: Dict[str, Any]) -> Dict[str, float]:
        """Get block dimensions from bounding box."""
        if 'BoundingBox' not in geometry_data:
            return {'width': 0.0, 'height': 0.0, 'depth': 0.0}
        
        bbox = geometry_data['BoundingBox']
        min_pt = bbox['MinPoint']
        max_pt = bbox['MaxPoint']
        
        return {
            'width': abs(max_pt['X'] - min_pt['X']),
            'height': abs(max_pt['Y'] - min_pt['Y']),
            'depth': abs(max_pt.get('Z', 0) - min_pt.get('Z', 0))
        }
    
    def is_block_inside_bounds(self, geometry_data: Dict[str, Any], 
                              bounds: Dict[str, Any]) -> bool:
        """Check if block is completely inside given bounds."""
        if 'BoundingBox' not in geometry_data:
            # Use position for point-like blocks
            pos = geometry_data['Position']
            return (
                bounds['MinPoint']['X'] <= pos['X'] <= bounds['MaxPoint']['X'] and
                bounds['MinPoint']['Y'] <= pos['Y'] <= bounds['MaxPoint']['Y']
            )
        
        bbox = geometry_data['BoundingBox']
        return (
            bounds['MinPoint']['X'] <= bbox['MinPoint']['X'] and
            bounds['MinPoint']['Y'] <= bbox['MinPoint']['Y'] and
            bbox['MaxPoint']['X'] <= bounds['MaxPoint']['X'] and
            bbox['MaxPoint']['Y'] <= bounds['MaxPoint']['Y']
        )