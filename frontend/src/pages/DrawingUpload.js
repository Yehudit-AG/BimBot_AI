import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from 'react-query';
import { uploadDrawing } from '../services/api';

const DrawingUpload = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const navigate = useNavigate();

  const uploadMutation = useMutation(uploadDrawing, {
    onSuccess: (data) => {
      navigate(`/drawings/${data.id}/layers`);
    },
  });

  const handleFileSelect = (file) => {
    if (file && file.name.endsWith('.json')) {
      setSelectedFile(file);
    } else {
      alert('Please select a JSON file');
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleUpload = () => {
    if (selectedFile) {
      uploadMutation.mutate(selectedFile);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2>Upload DWG Export JSON</h2>
      </div>
      <div className="card-body">
        {uploadMutation.error && (
          <div className="alert alert-danger">
            Error uploading file: {uploadMutation.error.message}
          </div>
        )}

        <div
          className={`upload-zone ${dragActive ? 'drag-active' : ''} ${selectedFile ? 'has-file' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => document.getElementById('file-input').click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".json"
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          
          {selectedFile ? (
            <div className="file-info">
              <div className="file-icon">📄</div>
              <div className="file-details">
                <div className="file-name">{selectedFile.name}</div>
                <div className="file-size">{formatFileSize(selectedFile.size)}</div>
              </div>
            </div>
          ) : (
            <div className="upload-prompt">
              <div className="upload-icon">📁</div>
              <p>Drag and drop your JSON file here, or click to browse</p>
              <p className="text-muted">Only JSON files are supported</p>
            </div>
          )}
        </div>

        {selectedFile && (
          <div className="upload-actions">
            <button
              className="btn btn-primary"
              onClick={handleUpload}
              disabled={uploadMutation.isLoading}
            >
              {uploadMutation.isLoading ? (
                <>
                  <span className="spinner"></span>
                  Uploading...
                </>
              ) : (
                'Upload and Process'
              )}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setSelectedFile(null)}
              disabled={uploadMutation.isLoading}
            >
              Clear
            </button>
          </div>
        )}

        <div className="upload-info">
          <h3>What happens next?</h3>
          <ol>
            <li>Your JSON file will be uploaded and validated</li>
            <li>The system will build a layer inventory with entity counts</li>
            <li>You'll be able to select which layers to process</li>
            <li>The geometry processing pipeline will run on selected layers</li>
            <li>Results will be available for download</li>
          </ol>
        </div>
      </div>
    </div>
  );
};

export default DrawingUpload;