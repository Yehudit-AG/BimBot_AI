import React, { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { getDrawingLayers, updateLayerSelection, createJob } from '../services/api';

const LayerManagement = () => {
  const { drawingId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLayers, setSelectedLayers] = useState(new Set());

  const { data: layers, isLoading, error } = useQuery(
    ['layers', drawingId],
    () => getDrawingLayers(drawingId),
    {
      onSuccess: (data) => {
        // Initialize selected layers with currently selected ones
        const selected = new Set(
          data.filter(layer => layer.is_selected).map(layer => layer.id)
        );
        setSelectedLayers(selected);
      }
    }
  );

  const updateSelectionMutation = useMutation(
    (selectedLayerIds) => updateLayerSelection(drawingId, selectedLayerIds),
    {
      onSuccess: () => {
        queryClient.invalidateQueries(['layers', drawingId]);
      }
    }
  );

  const createJobMutation = useMutation(
    () => createJob(drawingId, { job_type: 'wall_processing' }),
    {
      onSuccess: (data) => {
        navigate(`/jobs/${data.id}`);
      }
    }
  );

  const filteredLayers = useMemo(() => {
    if (!layers) return [];
    
    return layers.filter(layer =>
      layer.layer_name.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [layers, searchTerm]);

  const handleLayerToggle = (layerId) => {
    const newSelected = new Set(selectedLayers);
    if (newSelected.has(layerId)) {
      newSelected.delete(layerId);
    } else {
      newSelected.add(layerId);
    }
    setSelectedLayers(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedLayers.size === filteredLayers.length) {
      setSelectedLayers(new Set());
    } else {
      setSelectedLayers(new Set(filteredLayers.map(layer => layer.id)));
    }
  };

  const handleUpdateSelection = () => {
    updateSelectionMutation.mutate(Array.from(selectedLayers));
  };

  const handleStartProcessing = () => {
    if (selectedLayers.size === 0) {
      alert('Please select at least one layer to process');
      return;
    }
    createJobMutation.mutate();
  };

  const getEntityTypeBadges = (layer) => {
    const badges = [];
    if (layer.has_lines) {
      badges.push(
        <span key="lines" className="badge badge-primary">
          LINES ({layer.line_count})
        </span>
      );
    }
    if (layer.has_polylines) {
      badges.push(
        <span key="polylines" className="badge badge-success">
          POLYLINES ({layer.polyline_count})
        </span>
      );
    }
    if (layer.has_blocks) {
      badges.push(
        <span key="blocks" className="badge badge-warning">
          BLOCKS ({layer.block_count})
        </span>
      );
    }
    return badges;
  };

  if (isLoading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading layer inventory...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-danger">
        Error loading layers: {error.message}
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center">
          <h2>Layer Inventory</h2>
          <div className="layer-stats">
            <span className="text-muted">
              {layers?.length || 0} layers, {selectedLayers.size} selected
            </span>
          </div>
        </div>
        <div className="card-body">
          {(updateSelectionMutation.error || createJobMutation.error) && (
            <div className="alert alert-danger">
              Error: {updateSelectionMutation.error?.message || createJobMutation.error?.message}
            </div>
          )}

          <div className="layer-controls mb-3">
            <div className="form-group">
              <input
                type="text"
                className="form-control"
                placeholder="Search layers..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="layer-actions">
              <button
                className="btn btn-secondary"
                onClick={handleSelectAll}
              >
                {selectedLayers.size === filteredLayers.length ? 'Deselect All' : 'Select All'}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleUpdateSelection}
                disabled={updateSelectionMutation.isLoading}
              >
                {updateSelectionMutation.isLoading ? 'Updating...' : 'Update Selection'}
              </button>
              <button
                className="btn btn-success"
                onClick={handleStartProcessing}
                disabled={createJobMutation.isLoading || selectedLayers.size === 0}
              >
                {createJobMutation.isLoading ? (
                  <>
                    <span className="spinner"></span>
                    Starting...
                  </>
                ) : (
                  'Start Processing'
                )}
              </button>
            </div>
          </div>

          <div className="layer-list">
            {filteredLayers.length === 0 ? (
              <div className="text-center text-muted">
                {searchTerm ? 'No layers match your search' : 'No layers found'}
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th width="50">
                      <input
                        type="checkbox"
                        checked={selectedLayers.size === filteredLayers.length && filteredLayers.length > 0}
                        onChange={handleSelectAll}
                      />
                    </th>
                    <th>Layer Name</th>
                    <th>Entity Types</th>
                    <th>Total Entities</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLayers.map((layer) => (
                    <tr key={layer.id} className={selectedLayers.has(layer.id) ? 'selected' : ''}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedLayers.has(layer.id)}
                          onChange={() => handleLayerToggle(layer.id)}
                        />
                      </td>
                      <td>
                        <div className="layer-name">
                          {layer.layer_name}
                        </div>
                      </td>
                      <td>
                        <div className="entity-badges">
                          {getEntityTypeBadges(layer)}
                        </div>
                      </td>
                      <td>
                        <span className="entity-count">
                          {layer.total_entities}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Processing Pipeline</h2>
        </div>
        <div className="card-body">
          <div className="pipeline-info">
            <p>The selected layers will be processed through the following pipeline:</p>
            <ol>
              <li><strong>EXTRACT</strong> - Parse selected layers from JSON</li>
              <li><strong>NORMALIZE</strong> - Apply coordinate normalization and validation</li>
              <li><strong>CLEAN_DEDUP</strong> - Remove duplicates using epsilon-based comparison</li>
              <li><strong>PARALLEL_NAIVE</strong> - Parallel processing preparation</li>
              <li><strong>WALL_CANDIDATES_PLACEHOLDER</strong> - Mock wall detection (Phase 1 scope)</li>
            </ol>
            <p className="text-muted">
              All processing is deterministic and fully traceable. You can monitor progress and download artifacts after completion.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LayerManagement;