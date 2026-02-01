import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from 'react-query';
import { getJobStatus, getJobLogs, getJobArtifacts } from '../services/api';
import CadCanvasViewer from '../components/CadCanvasViewer';

const JobDashboard = () => {
  const { jobId } = useParams();
  const [activeTab, setActiveTab] = useState('progress');

  const { data: job, isLoading: jobLoading, error: jobError } = useQuery(
    ['job', jobId],
    () => getJobStatus(jobId),
    {
      refetchInterval: (data) => {
        // Refetch every 2 seconds if job is running
        return data?.status === 'running' || data?.status === 'pending' ? 2000 : false;
      }
    }
  );

  const { data: logs, isLoading: logsLoading } = useQuery(
    ['job-logs', jobId],
    () => getJobLogs(jobId),
    {
      enabled: activeTab === 'logs'
    }
  );

  const { data: artifacts, isLoading: artifactsLoading } = useQuery(
    ['job-artifacts', jobId],
    () => getJobArtifacts(jobId),
    {
      enabled: activeTab === 'artifacts'
    }
  );


  const getStatusBadge = (status) => {
    const statusClasses = {
      pending: 'badge-secondary',
      running: 'badge-primary',
      completed: 'badge-success',
      failed: 'badge-danger'
    };
    
    return (
      <span className={`badge ${statusClasses[status] || 'badge-secondary'}`}>
        {status?.toUpperCase() || 'UNKNOWN'}
      </span>
    );
  };

  const getStepProgress = () => {
    if (!job?.steps) return 0;
    
    const completedSteps = job.steps.filter(step => step.status === 'completed').length;
    return (completedSteps / job.steps.length) * 100;
  };

  const formatDuration = (durationMs) => {
    if (!durationMs) return 'N/A';
    
    if (durationMs < 1000) {
      return `${durationMs}ms`;
    } else if (durationMs < 60000) {
      return `${(durationMs / 1000).toFixed(1)}s`;
    } else {
      return `${(durationMs / 60000).toFixed(1)}m`;
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString();
  };

  const downloadArtifact = (artifactId, filename) => {
    const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
    const url = `${apiUrl}/artifacts/${artifactId}/download`;
    
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (jobLoading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading job details...</p>
      </div>
    );
  }

  if (jobError) {
    return (
      <div className="alert alert-danger">
        Error loading job: {jobError.message}
      </div>
    );
  }

  return (
    <div>
      {/* Job Overview */}
      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center">
          <h2>Job Overview</h2>
          {getStatusBadge(job?.status)}
        </div>
        <div className="card-body">
          <div className="job-info">
            <div className="info-grid">
              <div className="info-item">
                <label>Job ID:</label>
                <span>{job?.id}</span>
              </div>
              <div className="info-item">
                <label>Job Type:</label>
                <span>{job?.job_type}</span>
              </div>
              <div className="info-item">
                <label>Created:</label>
                <span>{formatTimestamp(job?.created_at)}</span>
              </div>
              <div className="info-item">
                <label>Started:</label>
                <span>{formatTimestamp(job?.started_at)}</span>
              </div>
              <div className="info-item">
                <label>Completed:</label>
                <span>{formatTimestamp(job?.completed_at)}</span>
              </div>
              <div className="info-item">
                <label>Selected Layers:</label>
                <span>{job?.selected_layers?.length || 0}</span>
              </div>
            </div>

            {job?.error_message && (
              <div className="alert alert-danger mt-3">
                <strong>Error:</strong> {job.error_message}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Progress */}
      <div className="card">
        <div className="card-header">
          <h2>Pipeline Progress</h2>
        </div>
        <div className="card-body">
          <div className="progress mb-3">
            <div
              className="progress-bar"
              style={{ width: `${getStepProgress()}%` }}
            ></div>
          </div>
          
          <div className="steps-list">
            {job?.steps?.map((step, index) => (
              <div key={step.id} className={`step-item ${step.status}`}>
                <div className="step-header">
                  <div className="step-info">
                    <span className="step-number">{step.step_order}</span>
                    <span className="step-name">{step.step_name}</span>
                    {getStatusBadge(step.status)}
                  </div>
                  <div className="step-timing">
                    {step.duration_ms && (
                      <span className="duration">{formatDuration(step.duration_ms)}</span>
                    )}
                  </div>
                </div>
                
                {step.error_message && (
                  <div className="step-error">
                    <small className="text-danger">{step.error_message}</small>
                  </div>
                )}
                
                {step.metrics && Object.keys(step.metrics).length > 0 && (
                  <div className="step-metrics">
                    <small className="text-muted">
                      {Object.entries(step.metrics).map(([key, value]) => (
                        <span key={key} className="metric">
                          {key}: {typeof value === 'number' ? value.toLocaleString() : 
                                 typeof value === 'object' ? JSON.stringify(value) : 
                                 String(value)}
                        </span>
                      ))}
                    </small>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="card">
        <div className="card-header">
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'progress' ? 'active' : ''}`}
              onClick={() => setActiveTab('progress')}
            >
              Progress
            </button>
            <button
              className={`tab ${activeTab === 'logs' ? 'active' : ''}`}
              onClick={() => setActiveTab('logs')}
            >
              Logs
            </button>
            <button
              className={`tab ${activeTab === 'artifacts' ? 'active' : ''}`}
              onClick={() => setActiveTab('artifacts')}
            >
              Artifacts
            </button>
            <button
              className={`tab ${activeTab === 'canvas' ? 'active' : ''}`}
              onClick={() => setActiveTab('canvas')}
            >
              Canvas Viewer
            </button>
          </div>
        </div>
        <div className="card-body">
          {activeTab === 'progress' && (
            <div className="progress-details">
              <p>Pipeline execution details are shown above. Monitor the progress of each step in real-time.</p>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="logs-section">
              {logsLoading ? (
                <div className="loading">
                  <div className="spinner"></div>
                  <p>Loading logs...</p>
                </div>
              ) : logs && logs.length > 0 ? (
                <div className="logs-list">
                  {logs.map((log) => (
                    <div key={log.id} className={`log-entry log-${log.level.toLowerCase()}`}>
                      <div className="log-header">
                        <span className="log-timestamp">{formatTimestamp(log.timestamp)}</span>
                        <span className={`log-level badge badge-${log.level.toLowerCase() === 'error' ? 'danger' : log.level.toLowerCase() === 'warning' ? 'warning' : 'info'}`}>
                          {log.level}
                        </span>
                      </div>
                      <div className="log-message">{log.message}</div>
                      {log.context && Object.keys(log.context).length > 0 && (
                        <div className="log-context">
                          <pre>{JSON.stringify(log.context, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-muted">No logs available</div>
              )}
            </div>
          )}

          {activeTab === 'artifacts' && (
            <div className="artifacts-section">
              {artifactsLoading ? (
                <div className="loading">
                  <div className="spinner"></div>
                  <p>Loading artifacts...</p>
                </div>
              ) : artifacts && artifacts.length > 0 ? (
                <div className="artifacts-list">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Size</th>
                        <th>Created</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {artifacts.map((artifact) => (
                        <tr key={artifact.id}>
                          <td>{artifact.artifact_name}</td>
                          <td>
                            <span className="badge badge-secondary">
                              {artifact.artifact_type}
                            </span>
                          </td>
                          <td>{artifact.file_size ? `${(artifact.file_size / 1024).toFixed(1)} KB` : 'N/A'}</td>
                          <td>{formatTimestamp(artifact.created_at)}</td>
                          <td>
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => downloadArtifact(artifact.id, artifact.artifact_name)}
                            >
                              Download
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center text-muted">No artifacts available</div>
              )}
            </div>
          )}

          {activeTab === 'canvas' && (
            <div className="canvas-section" style={{ height: '600px', minHeight: '600px' }}>
              {job?.status === 'completed' ? (
                <CadCanvasViewer jobId={jobId} />
              ) : (
                <div className="text-center text-muted" style={{ padding: '40px' }}>
                  {job?.status === 'running' || job?.status === 'pending' ? (
                    <div>
                      <p>Job is still processing...</p>
                      <p>Canvas viewer will be available once the job completes.</p>
                    </div>
                  ) : (
                    <p>Canvas viewer is only available for completed jobs.</p>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default JobDashboard;