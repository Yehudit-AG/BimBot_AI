"""
EXTRACT processor - Parse selected layers from JSON.
"""

import time
from typing import Dict, Any, List
from .base_processor import BaseProcessor

class ExtractProcessor(BaseProcessor):
    """Processor for extracting geometry from selected layers."""
    
    def process(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract entities from selected layers."""
        self.log_info("Starting entity extraction")
        
        start_time = time.time()
        
        drawing_data = pipeline_data['drawing']
        selected_layer_names = pipeline_data['layer_names']
        
        # Extract entities from selected layers
        extracted_entities = {
            'lines': [],
            'polylines': [],
            'blocks': []
        }
        
        layer_stats = {}
        
        for layer_data in drawing_data.get('Layers', []):
            layer_name = layer_data.get('LayerName', '')
            
            if layer_name not in selected_layer_names:
                continue
            
            # Extract lines
            lines = layer_data.get('Lines', [])
            for line in lines:
                extracted_entities['lines'].append({
                    'layer_name': layer_name,
                    'entity_type': 'LINE',
                    'data': line
                })
            
            # Extract polylines
            polylines = layer_data.get('Polylines', [])
            for polyline in polylines:
                extracted_entities['polylines'].append({
                    'layer_name': layer_name,
                    'entity_type': 'POLYLINE',
                    'data': polyline
                })
            
            # Extract blocks
            blocks = layer_data.get('Blocks', [])
            for block in blocks:
                extracted_entities['blocks'].append({
                    'layer_name': layer_name,
                    'entity_type': 'BLOCK',
                    'data': block
                })
            
            # Track layer statistics
            layer_stats[layer_name] = {
                'lines_count': len(lines),
                'polylines_count': len(polylines),
                'blocks_count': len(blocks),
                'total_entities': len(lines) + len(polylines) + len(blocks)
            }
        
        # Merge collected window/door blocks (from Layer Manager) into entities
        window_door_blocks = pipeline_data.get('window_door_blocks', [])
        extracted_entities['blocks'].extend(window_door_blocks)
        if window_door_blocks:
            layer_stats['_window_door_collected'] = {
                'lines_count': 0,
                'polylines_count': 0,
                'blocks_count': len(window_door_blocks),
                'total_entities': len(window_door_blocks)
            }
        
        # Calculate totals
        total_lines = len(extracted_entities['lines'])
        total_polylines = len(extracted_entities['polylines'])
        total_blocks = len(extracted_entities['blocks'])
        total_entities = total_lines + total_polylines + total_blocks
        
        # Update metrics
        duration_ms = int((time.time() - start_time) * 1000)
        self.update_metrics(
            duration_ms=duration_ms,
            total_entities=total_entities,
            total_lines=total_lines,
            total_polylines=total_polylines,
            total_blocks=total_blocks,
            layers_processed=len(layer_stats),
            layer_stats=layer_stats
        )
        
        self.log_info(
            "Entity extraction completed",
            total_entities=total_entities,
            total_lines=total_lines,
            total_polylines=total_polylines,
            total_blocks=total_blocks,
            layers_processed=len(layer_stats),
            duration_ms=duration_ms
        )
        
        return {
            'entities': extracted_entities,
            'layer_stats': layer_stats,
            'totals': {
                'lines': total_lines,
                'polylines': total_polylines,
                'blocks': total_blocks,
                'total': total_entities
            }
        }