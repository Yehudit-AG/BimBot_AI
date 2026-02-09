-- Migration 002: Window/Door blocks table
-- Run this if your database was created before this feature was added.
-- Example: psql -U your_user -d your_db -f database/migrations/002_drawing_window_door_blocks.sql

CREATE TABLE IF NOT EXISTS drawing_window_door_blocks (
    drawing_id UUID PRIMARY KEY REFERENCES drawings(id) ON DELETE CASCADE,
    blocks JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Ensure the updated_at trigger function exists (from init.sql), then add trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_drawing_window_door_blocks_updated_at ON drawing_window_door_blocks;
CREATE TRIGGER update_drawing_window_door_blocks_updated_at
    BEFORE UPDATE ON drawing_window_door_blocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
