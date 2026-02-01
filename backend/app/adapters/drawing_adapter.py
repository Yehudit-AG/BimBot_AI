"""
Drawing adapter for processing complete DWG export JSON files.
Orchestrates all entity adapters and builds layer inventory.
"""

import json
import hashlib
from typing import Any, Dict, List, Tuple
from .line_adapter import LineAdapter
from .polyline_adapter import PolylineAdapter
from .block_adapter import BlockAdapter


class DrawingAdapter:
    """Main adapter for processing complete drawing JSON files."""
    
    def __init__(self):
        self.line_adapter = LineAdapter()
        self.polyline_adapter = PolylineAdapter()
        self.block_adapter = BlockAdapter()
        
        # Processing statistics
        self.total_layers = 0
        self.total_entities = 0
        self.processing_errors = []
    
    def process_drawing(self, drawing_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Process complete drawing JSON and return drawing metadata and layer inventory.
        
        Returns:
            Tuple of (drawing_metadata, layer_inventory)
        """
        # Validate drawing structure
        if not self._validate_drawing_structure(drawing_data):
            raise ValueError("Invalid drawing structure")
        
        # Extract drawing metadata
        drawing_metadata = self._extract_drawing_metadata(drawing_data)
        
        # Process all layers
        layer_inventory = []
        layers_data = drawing_data.get('Layers', [])
        
        for layer_data in layers_data:
            try:
                layer_info = self._process_layer(layer_data)
                layer_inventory.append(layer_info)
                self.total_layers += 1
            except Exception as e:
                error_msg = f"Error processing layer {layer_data.get('LayerName', 'unknown')}: {str(e)}"
                self.processing_errors.append(error_msg)
                continue
        
        return drawing_metadata, layer_inventory
    
    def _validate_drawing_structure(self, drawing_data: Dict[str, Any]) -> bool:
        """Validate the basic structure of drawing JSON."""
        if not isinstance(drawing_data, dict):
            return False
        
        # Check for required top-level fields
        if 'Layers' not in drawing_data:
            return False
        
        layers = drawing_data['Layers']
        if not isinstance(layers, list):
            return False
        
        # Validate each layer structure
        for layer in layers:
            if not isinstance(layer, dict):
                return False
            
            if 'LayerName' not in layer:
                return False
            
            # Check for entity arrays
            required_arrays = ['Lines', 'Polylines', 'Blocks']
            for array_name in required_arrays:
                if array_name not in layer:
                    return False
                
                if not isinstance(layer[array_name], list):
                    return False
        
        return True
    
    def _extract_drawing_metadata(self, drawing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from drawing."""
        # Calculate file hash for consistency checking
        drawing_json = json.dumps(drawing_data, sort_keys=True, ensure_ascii=False)
        file_hash = hashlib.sha256(drawing_json.encode('utf-8')).hexdigest()
        
        # Extract filename
        filename = drawing_data.get('FileName', 'unknown.dwg')
        
        # Count total entities across all layers
        total_lines = 0
        total_polylines = 0
        total_blocks = 0
        
        for layer in drawing_data.get('Layers', []):
            total_lines += len(layer.get('Lines', []))
            total_polylines += len(layer.get('Polylines', []))
            total_blocks += len(layer.get('Blocks', []))
        
        return {
            'filename': filename,
            'original_filename': filename.split('\\')[-1] if '\\' in filename else filename,
            'file_hash': file_hash,
            'total_layers': len(drawing_data.get('Layers', [])),
            'total_lines': total_lines,
            'total_polylines': total_polylines,
            'total_blocks': total_blocks,
            'total_entities': total_lines + total_polylines + total_blocks,
            'has_unicode_names': self._has_unicode_layer_names(drawing_data),
            'layer_names': [layer.get('LayerName', '') for layer in drawing_data.get('Layers', [])]
        }
    
    def _process_layer(self, layer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single layer and return layer information."""
        layer_name = layer_data.get('LayerName', '')
        
        # Get entity arrays
        lines = layer_data.get('Lines', [])
        polylines = layer_data.get('Polylines', [])
        blocks = layer_data.get('Blocks', [])
        
        # Count entities
        line_count = len(lines)
        polyline_count = len(polylines)
        block_count = len(blocks)
        total_entities = line_count + polyline_count + block_count
        
        # Determine presence flags
        has_lines = line_count > 0
        has_polylines = polyline_count > 0
        has_blocks = block_count > 0
        
        # Process entities for validation (but don't store results here)
        processing_stats = {
            'lines_processed': 0,
            'lines_duplicates': 0,
            'lines_errors': 0,
            'polylines_processed': 0,
            'polylines_duplicates': 0,
            'polylines_errors': 0,
            'blocks_processed': 0,
            'blocks_duplicates': 0,
            'blocks_errors': 0
        }
        
        # Quick validation pass
        if has_lines:
            # Reset adapter stats
            self.line_adapter.reset_stats()
            self.line_adapter.process_entities(lines, layer_name)
            processing_stats.update({
                'lines_processed': self.line_adapter.processed_count,
                'lines_duplicates': self.line_adapter.duplicate_count,
                'lines_errors': self.line_adapter.error_count
            })
        
        if has_polylines:
            self.polyline_adapter.reset_stats()
            self.polyline_adapter.process_entities(polylines, layer_name)
            processing_stats.update({
                'polylines_processed': self.polyline_adapter.processed_count,
                'polylines_duplicates': self.polyline_adapter.duplicate_count,
                'polylines_errors': self.polyline_adapter.error_count
            })
        
        if has_blocks:
            self.block_adapter.reset_stats()
            self.block_adapter.process_entities(blocks, layer_name)
            processing_stats.update({
                'blocks_processed': self.block_adapter.processed_count,
                'blocks_duplicates': self.block_adapter.duplicate_count,
                'blocks_errors': self.block_adapter.error_count
            })
        
        # Calculate layer bounds
        layer_bounds = self._calculate_layer_bounds(layer_data)
        
        return {
            'layer_name': layer_name,
            'has_lines': has_lines,
            'has_polylines': has_polylines,
            'has_blocks': has_blocks,
            'line_count': line_count,
            'polyline_count': polyline_count,
            'block_count': block_count,
            'total_entities': total_entities,
            'processing_stats': processing_stats,
            'layer_bounds': layer_bounds,
            'has_unicode_name': self._contains_unicode(layer_name)
        }
    
    def _calculate_layer_bounds(self, layer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate bounding box for entire layer."""
        all_points = []
        
        # Collect points from lines
        for line in layer_data.get('Lines', []):
            if 'Start' in line:
                all_points.append(line['Start'])
            if 'End' in line:
                all_points.append(line['End'])
        
        # Collect points from polylines
        for polyline in layer_data.get('Polylines', []):
            for vertex in polyline.get('Vertices', []):
                all_points.append(vertex)
        
        # Collect points from blocks
        for block in layer_data.get('Blocks', []):
            if 'Position' in block:
                all_points.append(block['Position'])
            
            # Use bounding box if available
            if 'BoundingBox' in block:
                bbox = block['BoundingBox']
                all_points.extend([bbox['MinPoint'], bbox['MaxPoint']])
        
        if not all_points:
            return None
        
        # Calculate overall bounds
        x_coords = [p.get('X', 0) for p in all_points]
        y_coords = [p.get('Y', 0) for p in all_points]
        z_coords = [p.get('Z', 0) for p in all_points]
        
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
    
    def _has_unicode_layer_names(self, drawing_data: Dict[str, Any]) -> bool:
        """Check if any layer names contain Unicode characters."""
        for layer in drawing_data.get('Layers', []):
            layer_name = layer.get('LayerName', '')
            if self._contains_unicode(layer_name):
                return True
        return False
    
    def _contains_unicode(self, text: str) -> bool:
        """Check if text contains non-ASCII Unicode characters."""
        if not text:
            return False
        
        try:
            text.encode('ascii')
            return False
        except UnicodeEncodeError:
            return True
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Get summary of processing results."""
        return {
            'total_layers': self.total_layers,
            'total_entities': self.total_entities,
            'processing_errors': self.processing_errors,
            'error_count': len(self.processing_errors)
        }
    
    def reset_stats(self):
        """Reset processing statistics."""
        self.total_layers = 0
        self.total_entities = 0
        self.processing_errors = []
        
        self.line_adapter.reset_stats()
        self.polyline_adapter.reset_stats()
        self.block_adapter.reset_stats()