"""
Artifact service for managing job artifacts and intermediate results.
"""

import os
import json
import uuid
import hashlib
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from ..models.database_models import Artifact
from ..config import settings
from .logging_service import logging_service

class ArtifactService:
    """Service for managing job artifacts and intermediate results."""
    
    def __init__(self):
        self.artifacts_dir = settings.artifacts_dir
        os.makedirs(self.artifacts_dir, exist_ok=True)
    
    def create_artifact(self, db: Session, job_id: uuid.UUID, 
                       artifact_type: str, artifact_name: str,
                       content: Any, content_type: str = "application/json",
                       step_id: Optional[uuid.UUID] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> Artifact:
        """Create and store a job artifact."""
        try:
            # Create job-specific directory
            job_dir = os.path.join(self.artifacts_dir, str(job_id))
            os.makedirs(job_dir, exist_ok=True)
            
            # Generate file path
            safe_name = self._sanitize_filename(artifact_name)
            file_path = os.path.join(job_dir, safe_name)
            
            # Serialize content based on type
            if content_type == "application/json":
                content_bytes = json.dumps(content, indent=2, ensure_ascii=False).encode('utf-8')
            elif isinstance(content, str):
                content_bytes = content.encode('utf-8')
            elif isinstance(content, bytes):
                content_bytes = content
            else:
                # Try to serialize as JSON
                content_bytes = json.dumps(content, indent=2, default=str).encode('utf-8')
            
            # Write file
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
            
            # Create database record
            artifact = Artifact(
                job_id=job_id,
                step_id=step_id,
                artifact_type=artifact_type,
                artifact_name=artifact_name,
                file_path=file_path,
                file_size=len(content_bytes),
                content_type=content_type,
                artifact_metadata=metadata or {}
            )
            
            db.add(artifact)
            db.commit()
            
            logging_service.log_file_operation(
                operation="create_artifact",
                file_path=file_path,
                file_size=len(content_bytes)
            )
            
            logging_service.logger.info(
                "Artifact created",
                job_id=str(job_id),
                step_id=str(step_id) if step_id else None,
                artifact_type=artifact_type,
                artifact_name=artifact_name,
                file_size=len(content_bytes)
            )
            
            return artifact
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to create artifact",
                job_id=str(job_id),
                artifact_type=artifact_type,
                artifact_name=artifact_name,
                error=str(e)
            )
            raise
    
    def store_step_results(self, db: Session, job_id: uuid.UUID, 
                          step_id: uuid.UUID, step_name: str,
                          results: Dict[str, Any]) -> List[Artifact]:
        """Store step processing results as artifacts."""
        artifacts = []
        
        try:
            # Store main results
            main_artifact = self.create_artifact(
                db=db,
                job_id=job_id,
                step_id=step_id,
                artifact_type="step_results",
                artifact_name=f"{step_name}_results.json",
                content=results,
                metadata={"step_name": step_name}
            )
            artifacts.append(main_artifact)
            
            # Store specific data types as separate artifacts
            if 'entities' in results:
                entities_artifact = self.create_artifact(
                    db=db,
                    job_id=job_id,
                    step_id=step_id,
                    artifact_type="entities_data",
                    artifact_name=f"{step_name}_entities.json",
                    content=results['entities'],
                    metadata={"step_name": step_name, "data_type": "entities"}
                )
                artifacts.append(entities_artifact)
            
            # Store metrics as separate artifact
            if 'totals' in results or any(key.endswith('_stats') for key in results.keys()):
                metrics_data = {}
                for key, value in results.items():
                    if key == 'totals' or key.endswith('_stats'):
                        metrics_data[key] = value
                
                if metrics_data:
                    metrics_artifact = self.create_artifact(
                        db=db,
                        job_id=job_id,
                        step_id=step_id,
                        artifact_type="step_metrics",
                        artifact_name=f"{step_name}_metrics.json",
                        content=metrics_data,
                        metadata={"step_name": step_name, "data_type": "metrics"}
                    )
                    artifacts.append(metrics_artifact)
            
            return artifacts
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to store step results",
                job_id=str(job_id),
                step_id=str(step_id),
                step_name=step_name,
                error=str(e)
            )
            return artifacts
    
    def store_final_results(self, db: Session, job_id: uuid.UUID,
                           final_results: Dict[str, Any]) -> List[Artifact]:
        """Store final job results as artifacts."""
        artifacts = []
        
        try:
            # Store complete results
            complete_artifact = self.create_artifact(
                db=db,
                job_id=job_id,
                artifact_type="final_results",
                artifact_name="complete_results.json",
                content=final_results,
                metadata={"result_type": "complete"}
            )
            artifacts.append(complete_artifact)
            
            # Store wall candidates if present
            print(f"DEBUG: final_results keys: {list(final_results.keys())}")
            if 'WALL_CANDIDATES_PLACEHOLDER' in final_results:
                wall_data = final_results['WALL_CANDIDATES_PLACEHOLDER']
                print(f"DEBUG: wall_data keys: {list(wall_data.keys()) if wall_data else 'None'}")
                
                wall_artifact = self.create_artifact(
                    db=db,
                    job_id=job_id,
                    artifact_type="wall_detection",
                    artifact_name="wall_candidates.json",
                    content=wall_data,
                    metadata={"result_type": "wall_detection"}
                )
                artifacts.append(wall_artifact)
                
                # Store wall candidate pairs if present (new pair-based detection)
                if 'wall_candidate_pairs' in wall_data:
                    pairs_artifact = self.create_artifact(
                        db=db,
                        job_id=job_id,
                        artifact_type="wall_candidate_pairs",
                        artifact_name="wall_candidate_pairs.json",
                        content={
                            'pairs': wall_data['wall_candidate_pairs'],
                            'detection_stats': wall_data.get('detection_stats', {}),
                            'algorithm_config': wall_data.get('algorithm_config', {}),
                            'totals': wall_data.get('totals', {})
                        },
                        metadata={
                            "result_type": "wall_candidate_pairs",
                            "algorithm": "pair_based",
                            "pair_count": len(wall_data['wall_candidate_pairs'])
                        }
                    )
                    artifacts.append(pairs_artifact)
                
                # Also check if wall_candidate_pairs is at root level (direct from processor)
                elif 'wall_candidate_pairs' in final_results:
                    pairs_data = final_results
                    pairs_artifact = self.create_artifact(
                        db=db,
                        job_id=job_id,
                        artifact_type="wall_candidate_pairs",
                        artifact_name="wall_candidate_pairs.json",
                        content={
                            'pairs': pairs_data['wall_candidate_pairs'],
                            'detection_stats': pairs_data.get('detection_stats', {}),
                            'algorithm_config': pairs_data.get('algorithm_config', {}),
                            'totals': pairs_data.get('totals', {})
                        },
                        metadata={
                            "result_type": "wall_candidate_pairs",
                            "algorithm": "pair_based",
                            "pair_count": len(pairs_data['wall_candidate_pairs'])
                        }
                    )
                    artifacts.append(pairs_artifact)
                
                # Create summary report
                summary = self._create_wall_detection_summary(wall_data)
                summary_artifact = self.create_artifact(
                    db=db,
                    job_id=job_id,
                    artifact_type="summary_report",
                    artifact_name="wall_detection_summary.json",
                    content=summary,
                    metadata={"result_type": "summary"}
                )
                artifacts.append(summary_artifact)

            # Store wall candidate pairs B (Logic B) if present
            if 'WALL_CANDIDATES_B' in final_results:
                wall_b_data = final_results['WALL_CANDIDATES_B']
                if wall_b_data and wall_b_data.get('wall_candidate_pairs') is not None:
                    pairs_b_artifact = self.create_artifact(
                        db=db,
                        job_id=job_id,
                        artifact_type="wall_candidate_pairs_b",
                        artifact_name="wall_candidate_pairs_b.json",
                        content={
                            'pairs': wall_b_data['wall_candidate_pairs'],
                            'detection_stats': wall_b_data.get('detection_stats', {}),
                            'algorithm_config': wall_b_data.get('algorithm_config', {}),
                            'totals': wall_b_data.get('totals', {})
                        },
                        metadata={
                            "result_type": "wall_candidate_pairs_b",
                            "algorithm": "logic_b",
                            "pair_count": len(wall_b_data['wall_candidate_pairs'])
                        }
                    )
                    if pairs_b_artifact:
                        artifacts.append(pairs_b_artifact)
            
            return artifacts
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to store final results",
                job_id=str(job_id),
                error=str(e)
            )
            return artifacts
    
    def get_artifact_content(self, artifact: Artifact) -> Any:
        """Retrieve artifact content from file."""
        try:
            if not os.path.exists(artifact.file_path):
                raise FileNotFoundError(f"Artifact file not found: {artifact.file_path}")
            
            with open(artifact.file_path, 'rb') as f:
                content_bytes = f.read()
            
            # Parse content based on type
            if artifact.content_type == "application/json":
                return json.loads(content_bytes.decode('utf-8'))
            elif artifact.content_type.startswith("text/"):
                return content_bytes.decode('utf-8')
            else:
                return content_bytes
                
        except Exception as e:
            logging_service.logger.error(
                "Failed to retrieve artifact content",
                artifact_id=str(artifact.id),
                file_path=artifact.file_path,
                error=str(e)
            )
            raise
    
    def delete_job_artifacts(self, db: Session, job_id: uuid.UUID) -> bool:
        """Delete all artifacts for a job."""
        try:
            # Get all artifacts for the job
            artifacts = db.query(Artifact).filter(Artifact.job_id == job_id).all()
            
            # Delete files
            for artifact in artifacts:
                if os.path.exists(artifact.file_path):
                    os.remove(artifact.file_path)
            
            # Delete database records
            db.query(Artifact).filter(Artifact.job_id == job_id).delete()
            db.commit()
            
            # Remove job directory if empty
            job_dir = os.path.join(self.artifacts_dir, str(job_id))
            if os.path.exists(job_dir) and not os.listdir(job_dir):
                os.rmdir(job_dir)
            
            logging_service.logger.info(
                "Job artifacts deleted",
                job_id=str(job_id),
                artifacts_count=len(artifacts)
            )
            
            return True
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to delete job artifacts",
                job_id=str(job_id),
                error=str(e)
            )
            return False
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:190] + ext
        
        return filename
    
    def _create_wall_detection_summary(self, wall_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary report for wall detection results."""
        try:
            wall_candidates = wall_data.get('wall_candidates', [])
            wall_segments = wall_data.get('wall_segments', [])
            wall_analysis = wall_data.get('wall_analysis', {})
            
            summary = {
                'detection_summary': {
                    'total_candidates': len(wall_candidates),
                    'total_segments': len(wall_segments),
                    'total_wall_length': wall_analysis.get('total_wall_length', 0),
                    'intersection_count': len(wall_analysis.get('intersection_points', []))
                },
                'wall_orientations': wall_analysis.get('wall_orientations', {}),
                'confidence_analysis': {
                    'average_confidence': wall_data.get('detection_stats', {}).get('confidence_scores', []),
                    'high_confidence_count': 0,
                    'medium_confidence_count': 0,
                    'low_confidence_count': 0
                },
                'layer_distribution': {},
                'recommendations': []
            }
            
            # Analyze confidence scores
            confidence_scores = wall_data.get('detection_stats', {}).get('confidence_scores', [])
            if confidence_scores:
                summary['confidence_analysis']['average_confidence'] = sum(confidence_scores) / len(confidence_scores)
                
                for score in confidence_scores:
                    if score >= 0.8:
                        summary['confidence_analysis']['high_confidence_count'] += 1
                    elif score >= 0.5:
                        summary['confidence_analysis']['medium_confidence_count'] += 1
                    else:
                        summary['confidence_analysis']['low_confidence_count'] += 1
            
            # Analyze layer distribution
            for candidate in wall_candidates:
                layer_name = candidate.get('layer_name', 'unknown')
                if layer_name not in summary['layer_distribution']:
                    summary['layer_distribution'][layer_name] = 0
                summary['layer_distribution'][layer_name] += 1
            
            # Generate recommendations
            if len(wall_candidates) == 0:
                summary['recommendations'].append("No wall candidates detected. Consider adjusting detection parameters.")
            elif summary['confidence_analysis']['low_confidence_count'] > len(wall_candidates) * 0.5:
                summary['recommendations'].append("Many low-confidence detections. Manual review recommended.")
            
            if wall_analysis.get('total_wall_length', 0) > 0:
                summary['recommendations'].append("Wall detection completed successfully. Review segments for accuracy.")
            
            return summary
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to create wall detection summary",
                error=str(e)
            )
            return {"error": "Failed to generate summary"}
    
    def _ensure_pairs_have_overlap_percentage(self, pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure each pair has geometric_properties.overlap_percentage (אחוזי חפיפה) for API/UI."""
        result = []
        for p in pairs:
            pair = dict(p)
            geo = pair.get("geometric_properties") or {}
            geo = dict(geo)
            if "overlap_percentage" not in geo:
                geo["overlap_percentage"] = 0.0
            pair["geometric_properties"] = geo
            result.append(pair)
        return result

    def get_wall_candidate_pairs(self, db: Session, job_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get wall candidate pairs artifact for a job; each pair includes overlap_percentage (אחוזי חפיפה)."""
        try:
            # #region agent log
            import json
            import time
            with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"B,D","location":"artifact_service.py:394","message":"Looking for wall candidate pairs","data":{"job_id":str(job_id),"looking_for_type":"wall_candidate_pairs"},"timestamp":int(time.time()*1000)}) + '\n')
            # #endregion
            
            # Try both the expected type and the actual type created by worker
            artifact = db.query(Artifact).filter(
                Artifact.job_id == job_id,
                Artifact.artifact_type.in_(["wall_candidate_pairs", "wall_candidates_placeholder_results"])
            ).first()
            
            # #region agent log
            with open(r'c:\Users\yehudit\Desktop\BimBot_AI_WALL\.cursor\debug.log', 'a', encoding='utf-8') as f:
                all_artifacts = db.query(Artifact).filter(Artifact.job_id == job_id).all()
                artifact_types = [a.artifact_type for a in all_artifacts]
                f.write(json.dumps({"sessionId":"debug-session","runId":"initial","hypothesisId":"B,D","location":"artifact_service.py:405","message":"Artifact search result","data":{"found_artifact":artifact is not None,"all_artifact_types":artifact_types},"timestamp":int(time.time()*1000)}) + '\n')
            # #endregion
            
            if not artifact:
                return None
            
            content = self.get_artifact_content(artifact)
            
            # Normalize: support both 'pairs' and 'wall_candidate_pairs' keys
            raw_pairs = None
            if isinstance(content, dict):
                raw_pairs = content.get("wall_candidate_pairs") or content.get("pairs")
            if raw_pairs is None:
                return content
            
            pairs = self._ensure_pairs_have_overlap_percentage(raw_pairs)
            return {
                "pairs": pairs,
                "detection_stats": content.get("detection_stats", {}),
                "algorithm_config": content.get("algorithm_config", {}),
                "totals": content.get("totals", {}),
            }
            
        except Exception as e:
            logging_service.logger.error(
                "Failed to get wall candidate pairs",
                job_id=str(job_id),
                error=str(e)
            )
            return None

    def get_wall_candidate_pairs_b(self, db: Session, job_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get wall candidate pairs B (Logic B) artifact for a job; each pair includes overlap_percentage."""
        try:
            # Prefer dedicated artifact (from store_final_results); fallback to step artifact for backward compatibility
            artifact = db.query(Artifact).filter(
                Artifact.job_id == job_id,
                Artifact.artifact_type == "wall_candidate_pairs_b"
            ).first()
            if not artifact:
                artifact = db.query(Artifact).filter(
                    Artifact.job_id == job_id,
                    Artifact.artifact_type == "wall_candidates_b_results"
                ).first()

            if not artifact:
                return None

            content = self.get_artifact_content(artifact)
            raw_pairs = None
            if isinstance(content, dict):
                raw_pairs = content.get("wall_candidate_pairs") or content.get("pairs")
            if raw_pairs is None:
                return content

            pairs = self._ensure_pairs_have_overlap_percentage(raw_pairs)
            return {
                "pairs": pairs,
                "detection_stats": content.get("detection_stats", {}),
                "algorithm_config": content.get("algorithm_config", {}),
                "totals": content.get("totals", {}),
            }
        except Exception as e:
            logging_service.logger.error(
                "Failed to get wall candidate pairs B",
                job_id=str(job_id),
                error=str(e)
            )
            return None

# Global artifact service instance
artifact_service = ArtifactService()