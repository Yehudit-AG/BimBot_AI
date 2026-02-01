"""
Database models for worker (simplified version of backend models).
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class Drawing(Base):
    __tablename__ = "drawings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    file_hash = Column(String(64), nullable=False, unique=True)
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(50), default='uploaded')
    drawing_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Layer(Base):
    __tablename__ = "layers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    layer_name = Column(String(255), nullable=False)
    has_lines = Column(Boolean, default=False)
    has_polylines = Column(Boolean, default=False)
    has_blocks = Column(Boolean, default=False)
    line_count = Column(Integer, default=0)
    polyline_count = Column(Integer, default=0)
    block_count = Column(Integer, default=0)
    total_entities = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class LayerSelection(Base):
    __tablename__ = "layer_selections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    layer_id = Column(UUID(as_uuid=True), ForeignKey("layers.id"), nullable=False)
    is_selected = Column(Boolean, default=False)
    selection_timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    job_type = Column(String(50), default='wall_processing')
    status = Column(String(50), default='pending')
    priority = Column(Integer, default=0)
    selected_layers = Column(JSONB, nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    job_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class JobStep(Base):
    __tablename__ = "job_steps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    step_name = Column(String(100), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(50), default='pending')
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    metrics = Column(JSONB)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class JobLog(Base):
    __tablename__ = "job_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    step_id = Column(UUID(as_uuid=True), ForeignKey("job_steps.id"))
    request_id = Column(String(100))
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id"))
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    context = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Artifact(Base):
    __tablename__ = "artifacts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    step_id = Column(UUID(as_uuid=True), ForeignKey("job_steps.id"))
    artifact_type = Column(String(100), nullable=False)
    artifact_name = Column(String(255), nullable=False)
    file_path = Column(String(500))
    file_size = Column(BigInteger)
    content_type = Column(String(100))
    artifact_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())