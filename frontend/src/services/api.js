import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    console.log(`API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  (error) => {
    console.error('API Response Error:', error.response?.data || error.message);
    
    // Handle specific error cases
    if (error.response?.status === 404) {
      throw new Error('Resource not found');
    } else if (error.response?.status === 400) {
      throw new Error(error.response.data?.detail || 'Bad request');
    } else if (error.response?.status === 409) {
      throw new Error(error.response.data?.detail || 'This file has already been uploaded');
    } else if (error.response?.status >= 500) {
      throw new Error('Server error. Please try again later.');
    }
    
    throw new Error(error.response?.data?.detail || error.message || 'An error occurred');
  }
);

// API functions
export const uploadDrawing = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post('/drawings', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  
  return response.data;
};

export const getDrawingLayers = async (drawingId) => {
  const response = await api.get(`/drawings/${drawingId}/layers`);
  return response.data;
};

export const updateLayerSelection = async (drawingId, selectedLayerIds) => {
  const response = await api.put(`/drawings/${drawingId}/selection`, {
    selected_layer_ids: selectedLayerIds,
  });
  return response.data;
};

export const createJob = async (drawingId, jobData) => {
  const response = await api.post(`/drawings/${drawingId}/jobs`, jobData);
  return response.data;
};

export const getJobStatus = async (jobId) => {
  const response = await api.get(`/jobs/${jobId}`);
  return response.data;
};

export const getJobLogs = async (jobId, level = null, limit = 100) => {
  const params = new URLSearchParams();
  if (level) params.append('level', level);
  params.append('limit', limit.toString());
  
  const response = await api.get(`/jobs/${jobId}/logs?${params.toString()}`);
  return response.data;
};

export const getJobArtifacts = async (jobId) => {
  const response = await api.get(`/jobs/${jobId}/artifacts`);
  return response.data;
};

export const downloadArtifact = async (artifactId) => {
  const response = await api.get(`/artifacts/${artifactId}/download`, {
    responseType: 'blob',
  });
  return response.data;
};

export const getJobCanvasData = async (jobId) => {
  const response = await api.get(`/jobs/${jobId}/canvas-data`);
  return response.data;
};

export const getJobWallCandidatePairs = async (jobId) => {
  const response = await api.get(`/jobs/${jobId}/wall-candidate-pairs`);
  return response.data;
};

export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

export default api;