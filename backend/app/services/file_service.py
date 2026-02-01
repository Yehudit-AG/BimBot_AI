"""
File service for handling uploads and file operations.
"""

import os
import hashlib
import uuid
from typing import Tuple
from fastapi import UploadFile
import aiofiles
from ..config import settings

class FileService:
    """Service for file operations."""
    
    def __init__(self):
        self.upload_dir = settings.upload_dir
        self.artifacts_dir = settings.artifacts_dir
    
    async def save_uploaded_file(self, file: UploadFile, content: bytes) -> Tuple[str, str]:
        """
        Save uploaded file and return file path and hash.
        
        Returns:
            Tuple of (file_path, file_hash)
        """
        # Generate file hash
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(self.upload_dir, unique_filename)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        return file_path, file_hash
    
    async def save_artifact(self, job_id: uuid.UUID, step_name: str, 
                           artifact_name: str, content: bytes, 
                           content_type: str = "application/octet-stream") -> str:
        """
        Save job artifact and return file path.
        """
        # Create job-specific directory
        job_dir = os.path.join(self.artifacts_dir, str(job_id))
        os.makedirs(job_dir, exist_ok=True)
        
        # Generate artifact filename
        safe_step_name = step_name.lower().replace(' ', '_')
        artifact_filename = f"{safe_step_name}_{artifact_name}"
        artifact_path = os.path.join(job_dir, artifact_filename)
        
        # Save artifact
        async with aiofiles.open(artifact_path, 'wb') as f:
            await f.write(content)
        
        return artifact_path
    
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(file_path)
    
    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        return os.path.getsize(file_path) if self.file_exists(file_path) else 0
    
    async def read_file(self, file_path: str) -> bytes:
        """Read file content."""
        async with aiofiles.open(file_path, 'rb') as f:
            return await f.read()
    
    def delete_file(self, file_path: str) -> bool:
        """Delete file if it exists."""
        try:
            if self.file_exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False