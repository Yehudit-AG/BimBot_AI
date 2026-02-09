"""
SQLAlchemy database models for BimBot AI Wall.
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
    drawing_metadata = Column(JSONB, name='metadata')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    layers = relationship("Layer", back_populates="drawing", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="drawing", cascade="all, delete-orphan")
    window_door_blocks = relationship("DrawingWindowDoorBlocks", back_populates="drawing", uselist=False, cascade="all, delete-orphan")

class DrawingWindowDoorBlocks(Base):
    __tablename__ = "drawing_window_door_blocks"

    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id", ondelete="CASCADE"), primary_key=True)
    blocks = Column(JSONB, nullable=False, default=lambda: [])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    drawing = relationship("Drawing", back_populates="window_door_blocks")

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
    
    # Relationships
    drawing = relationship("Drawing", back_populates="layers")
    selections = relationship("LayerSelection", back_populates="layer", cascade="all, delete-orphan")

class LayerSelection(Base):
    __tablename__ = "layer_selections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    layer_id = Column(UUID(as_uuid=True), ForeignKey("layers.id"), nullable=False)
    is_selected = Column(Boolean, default=False)
    selection_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    layer = relationship("Layer", back_populates="selections")

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
    job_metadata = Column(JSONB, name='metadata')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    drawing = relationship("Drawing", back_populates="jobs")
    steps = relationship("JobStep", back_populates="job", cascade="all, delete-orphan")
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="job", cascade="all, delete-orphan")

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
    
    # Relationships
    job = relationship("Job", back_populates="steps")
    logs = relationship("JobLog", back_populates="step", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="step", cascade="all, delete-orphan")

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
    
    # Relationships
    job = relationship("Job", back_populates="logs")
    step = relationship("JobStep", back_populates="logs")

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
    artifact_metadata = Column(JSONB, name='metadata')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    job = relationship("Job", back_populates="artifacts")
    step = relationship("JobStep", back_populates="artifacts")

class Entity(Base):
    __tablename__ = "entities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_hash = Column(String(64), nullable=False, unique=True)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    layer_name = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)
    geometry_data = Column(JSONB, nullable=False)
    normalized_geometry = Column(JSONB)
    bounding_box = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())