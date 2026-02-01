"""
Pydantic models for API request/response serialization.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class DrawingResponse(BaseModel):
    id: uuid.UUID
    filename: str
    file_size: int
    status: str
    upload_timestamp: datetime
    total_layers: int
    total_entities: int
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class LayerResponse(BaseModel):
    id: uuid.UUID
    layer_name: str
    has_lines: bool
    has_polylines: bool
    has_blocks: bool
    line_count: int
    polyline_count: int
    block_count: int
    total_entities: int
    is_selected: bool = False
    
    class Config:
        from_attributes = True

class LayerSelectionRequest(BaseModel):
    selected_layer_ids: List[uuid.UUID] = Field(..., description="List of layer IDs to select")

class JobCreateRequest(BaseModel):
    job_type: str = Field(default="wall_processing", description="Type of job to create")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional job metadata")

class JobStepResponse(BaseModel):
    id: uuid.UUID
    step_name: str
    step_order: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    metrics: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True

class JobResponse(BaseModel):
    id: uuid.UUID
    drawing_id: uuid.UUID
    job_type: str
    status: str
    selected_layers: List[str]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    steps: Optional[List[JobStepResponse]] = None
    
    class Config:
        from_attributes = True

class LogResponse(BaseModel):
    id: uuid.UUID
    job_id: Optional[uuid.UUID] = None
    step_id: Optional[uuid.UUID] = None
    level: str
    message: str
    context: Optional[Dict[str, Any]] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True

class ArtifactResponse(BaseModel):
    id: uuid.UUID
    artifact_type: str
    artifact_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    created_at: datetime
    download_url: str
    
    class Config:
        from_attributes = True

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Wall candidate pairs (for GET /jobs/{job_id}/wall-candidate-pairs)
# ---------------------------------------------------------------------------

class WallCandidatePairGeometricProperties(BaseModel):
    """Geometric properties of a wall candidate pair; overlap is % of longer line covered."""
    perpendicular_distance: float = Field(..., description="Distance between the two lines (mm)")
    overlap_percentage: float = Field(..., description="Overlap %: fraction of the longer line covered by overlap (0-100)")
    angle_difference: float = Field(..., description="Angle difference between lines (degrees)")
    average_length: float = Field(..., description="Average length of the two lines (mm)")
    bounding_rectangle: Optional[Dict[str, Any]] = None


class WallCandidatePairItem(BaseModel):
    """Single wall candidate pair as returned by the pipeline."""
    pair_id: str
    line1: Dict[str, Any]
    line2: Dict[str, Any]
    geometric_properties: WallCandidatePairGeometricProperties


class WallCandidatePairsResponse(BaseModel):
    """Response for wall candidate pairs; each pair includes overlap_percentage (אחוזי חפיפה)."""
    pairs: List[WallCandidatePairItem] = Field(..., description="List of wall candidate pairs with geometric_properties.overlap_percentage")
    detection_stats: Optional[Dict[str, Any]] = None
    algorithm_config: Optional[Dict[str, Any]] = None
    totals: Optional[Dict[str, Any]] = None