"""
Adapter layer for processing DWG export JSON files.
Provides deterministic entity ID generation and geometry normalization.
"""

from .base_adapter import BaseAdapter
from .line_adapter import LineAdapter
from .polyline_adapter import PolylineAdapter
from .block_adapter import BlockAdapter
from .drawing_adapter import DrawingAdapter

__all__ = [
    'BaseAdapter',
    'LineAdapter', 
    'PolylineAdapter',
    'BlockAdapter',
    'DrawingAdapter'
]