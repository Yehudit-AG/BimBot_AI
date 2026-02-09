-- BimBot AI Wall Database Schema
-- Phase 1 Implementation

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drawings table - File metadata and upload tracking
CREATE TABLE drawings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    file_hash VARCHAR(64) NOT NULL UNIQUE,
    upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'uploaded',
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Layers table - Layer inventory with entity counts and flags
CREATE TABLE layers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drawing_id UUID NOT NULL REFERENCES drawings(id) ON DELETE CASCADE,
    layer_name VARCHAR(255) NOT NULL,
    has_lines BOOLEAN DEFAULT FALSE,
    has_polylines BOOLEAN DEFAULT FALSE,
    has_blocks BOOLEAN DEFAULT FALSE,
    line_count INTEGER DEFAULT 0,
    polyline_count INTEGER DEFAULT 0,
    block_count INTEGER DEFAULT 0,
    total_entities INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drawing_id, layer_name)
);

-- Layer selections table - User layer toggle states
CREATE TABLE layer_selections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drawing_id UUID NOT NULL REFERENCES drawings(id) ON DELETE CASCADE,
    layer_id UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    is_selected BOOLEAN DEFAULT FALSE,
    selection_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drawing_id, layer_id)
);

-- Window/door blocks table - Collected blocks from window/door layers (one row per drawing)
CREATE TABLE drawing_window_door_blocks (
    drawing_id UUID PRIMARY KEY REFERENCES drawings(id) ON DELETE CASCADE,
    blocks JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Jobs table - Job lifecycle and status tracking
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drawing_id UUID NOT NULL REFERENCES drawings(id) ON DELETE CASCADE,
    job_type VARCHAR(50) DEFAULT 'wall_processing',
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    selected_layers JSONB NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Job steps table - Individual pipeline step execution
CREATE TABLE job_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_name VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    input_data JSONB,
    output_data JSONB,
    metrics JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, step_name)
);

-- Job logs table - Searchable log entries with correlation IDs
CREATE TABLE job_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    step_id UUID REFERENCES job_steps(id) ON DELETE CASCADE,
    request_id VARCHAR(100),
    drawing_id UUID REFERENCES drawings(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Artifacts table - Persistent intermediate results storage
CREATE TABLE artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_id UUID REFERENCES job_steps(id) ON DELETE CASCADE,
    artifact_type VARCHAR(100) NOT NULL,
    artifact_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500),
    file_size BIGINT,
    content_type VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Entities table - Normalized geometry entities with deterministic IDs
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_hash VARCHAR(64) NOT NULL UNIQUE,
    drawing_id UUID NOT NULL REFERENCES drawings(id) ON DELETE CASCADE,
    layer_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    geometry_data JSONB NOT NULL,
    normalized_geometry JSONB,
    bounding_box JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_drawings_status ON drawings(status);
CREATE INDEX idx_drawings_upload_timestamp ON drawings(upload_timestamp);
CREATE INDEX idx_layers_drawing_id ON layers(drawing_id);
CREATE INDEX idx_layers_layer_name ON layers(layer_name);
CREATE INDEX idx_layer_selections_drawing_id ON layer_selections(drawing_id);
CREATE INDEX idx_jobs_drawing_id ON jobs(drawing_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
CREATE INDEX idx_job_steps_job_id ON job_steps(job_id);
CREATE INDEX idx_job_steps_status ON job_steps(status);
CREATE INDEX idx_job_steps_step_order ON job_steps(step_order);
CREATE INDEX idx_job_logs_job_id ON job_logs(job_id);
CREATE INDEX idx_job_logs_timestamp ON job_logs(timestamp);
CREATE INDEX idx_job_logs_level ON job_logs(level);
CREATE INDEX idx_artifacts_job_id ON artifacts(job_id);
CREATE INDEX idx_entities_drawing_id ON entities(drawing_id);
CREATE INDEX idx_entities_layer_name ON entities(layer_name);
CREATE INDEX idx_entities_entity_type ON entities(entity_type);
CREATE INDEX idx_entities_entity_hash ON entities(entity_hash);

-- Trigger to update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_drawings_updated_at BEFORE UPDATE ON drawings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_drawing_window_door_blocks_updated_at BEFORE UPDATE ON drawing_window_door_blocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert initial data for testing
INSERT INTO drawings (filename, original_filename, file_size, file_hash, status) VALUES
('sample_drawing.json', 'Sample Drawing.json', 1024000, 'sample_hash_123', 'uploaded');

-- Views for common queries
CREATE VIEW job_summary AS
SELECT 
    j.id,
    j.drawing_id,
    j.status,
    j.created_at,
    j.started_at,
    j.completed_at,
    d.original_filename,
    COUNT(js.id) as total_steps,
    COUNT(CASE WHEN js.status = 'completed' THEN 1 END) as completed_steps,
    COUNT(CASE WHEN js.status = 'failed' THEN 1 END) as failed_steps
FROM jobs j
LEFT JOIN drawings d ON j.drawing_id = d.id
LEFT JOIN job_steps js ON j.id = js.job_id
GROUP BY j.id, j.drawing_id, j.status, j.created_at, j.started_at, j.completed_at, d.original_filename;

CREATE VIEW layer_summary AS
SELECT 
    l.id,
    l.drawing_id,
    l.layer_name,
    l.has_lines,
    l.has_polylines,
    l.has_blocks,
    l.line_count,
    l.polyline_count,
    l.block_count,
    l.total_entities,
    COALESCE(ls.is_selected, FALSE) as is_selected
FROM layers l
LEFT JOIN layer_selections ls ON l.id = ls.layer_id;