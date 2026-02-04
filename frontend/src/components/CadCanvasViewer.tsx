import React, { useRef, useEffect, useState, useCallback } from 'react';
import { getJobCanvasData, getJobWallCandidatePairs, getJobWallCandidatePairsB } from '../services/api';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface DrawingBounds {
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
}

interface ServerLine {
  id: string;
  start: { x: number; y: number; z: number };
  end: { x: number; y: number; z: number };
  length: number;
}

interface ServerLayer {
  lines: ServerLine[];
  color: string;
  visible: boolean;
}

interface ServerCanvasData {
  drawing_bounds: DrawingBounds;
  layers: Record<string, ServerLayer>;
  statistics: {
    total_lines: number;
    total_layers: number;
    layer_names: string[];
  };
}

interface BBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

interface NormalizedLine {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  length: number;
}

interface NormalizedLayer {
  name: string;
  color: string;
  visible: boolean;
  lines: NormalizedLine[];
}

interface Transform {
  scale: number;
  tx: number;
  ty: number;
}

interface Point {
  x: number;
  y: number;
}

interface GridCell {
  layerIdx: number;
  lineIdx: number;
}

interface HoveredLine {
  layerIdx: number;
  lineIdx: number;
  distance: number;
}

interface ServerPairResponse {
  pairs: Array<{
    pair_id: string;
    line1: {
      entity_hash: string;
      start_point: { X: number; Y: number; Z: number };
      end_point: { X: number; Y: number; Z: number };
      layer_name: string;
    };
    line2: {
      entity_hash: string;
      start_point: { X: number; Y: number; Z: number };
      end_point: { X: number; Y: number; Z: number };
      layer_name: string;
    };
    geometric_properties: {
      perpendicular_distance: number;
      overlap_percentage: number;
      angle_difference: number;
      average_length: number;
      bounding_rectangle: {
        minX: number;
        maxX: number;
        minY: number;
        maxY: number;
      };
    };
  }>;
  detection_stats?: Record<string, any>;
  algorithm_config?: Record<string, any>;
  totals?: Record<string, any>;
}

interface NormalizedPair {
  pairId: string;
  rect: BBox;
  shortestLine: { x1: number; y1: number; x2: number; y2: number };
  layer1: string;
  layer2: string;
  hash1: string;
  hash2: string;
  perpendicular_distance: number;
  overlap_percentage: number;
  angle_difference: number;
  average_length: number;
}

interface HoveredPair {
  pairIdx: number;
}

interface CadCanvasViewerProps {
  jobId: string;
  className?: string;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function normalizeData(serverData: ServerCanvasData): {
  bbox: BBox;
  layers: NormalizedLayer[];
} {
  const bbox: BBox = {
    minX: serverData.drawing_bounds.min_x,
    minY: serverData.drawing_bounds.min_y,
    maxX: serverData.drawing_bounds.max_x,
    maxY: serverData.drawing_bounds.max_y,
  };

  const layers: NormalizedLayer[] = Object.entries(serverData.layers).map(
    ([name, layer]) => ({
      name,
      color: layer.color,
      visible: layer.visible,
      lines: layer.lines.map((line) => ({
        id: line.id,
        x1: line.start.x,
        y1: line.start.y,
        x2: line.end.x,
        y2: line.end.y,
        length: line.length,
      })),
    })
  );

  return { bbox, layers };
}

function normalizePairsData(serverData: ServerPairResponse): NormalizedPair[] {
  console.log('🔄 Normalizing pairs data:', serverData);
  console.log('📊 Input pairs count:', serverData.pairs?.length || 0);
  
  if (!serverData.pairs || serverData.pairs.length === 0) {
    console.warn('⚠️ No pairs in server data!');
    return [];
  }
  
  return serverData.pairs.map((pair, idx) => {
    try {
      // Extract bounding_rectangle and convert to BBox format
      const br = pair.geometric_properties?.bounding_rectangle;
      if (!br) {
        console.warn(`⚠️ Pair ${idx} missing bounding_rectangle:`, pair);
        return null;
      }
    const rect: BBox = {
      minX: br.minX,
      minY: br.minY,
      maxX: br.maxX,
      maxY: br.maxY,
    };

    // Compute shortest line by comparing segment lengths
    const line1Start = pair.line1.start_point;
    const line1End = pair.line1.end_point;
    const line2Start = pair.line2.start_point;
    const line2End = pair.line2.end_point;

    const dx1 = line1End.X - line1Start.X;
    const dy1 = line1End.Y - line1Start.Y;
    const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);

    const dx2 = line2End.X - line2Start.X;
    const dy2 = line2End.Y - line2Start.Y;
    const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);

    const shortestLine =
      len1 <= len2
        ? {
            x1: line1Start.X,
            y1: line1Start.Y,
            x2: line1End.X,
            y2: line1End.Y,
          }
        : {
            x1: line2Start.X,
            y1: line2Start.Y,
            x2: line2End.X,
            y2: line2End.Y,
          };

    return {
      pairId: pair.pair_id,
      rect,
      shortestLine,
      layer1: pair.line1.layer_name,
      layer2: pair.line2.layer_name,
      hash1: pair.line1.entity_hash,
      hash2: pair.line2.entity_hash,
      perpendicular_distance: pair.geometric_properties.perpendicular_distance,
      overlap_percentage: pair.geometric_properties.overlap_percentage,
      angle_difference: pair.geometric_properties.angle_difference,
      average_length: pair.geometric_properties.average_length,
    };
    } catch (error) {
      console.error(`❌ Error normalizing pair ${idx}:`, error, pair);
      return null;
    }
  }).filter((p): p is NormalizedPair => p !== null);
}

function worldToScreen(wx: number, wy: number, transform: Transform): Point {
  return {
    x: wx * transform.scale + transform.tx,
    y: wy * transform.scale + transform.ty,
  };
}

function screenToWorld(sx: number, sy: number, transform: Transform): Point {
  return {
    x: (sx - transform.tx) / transform.scale,
    y: (sy - transform.ty) / transform.scale,
  };
}

function pointToSegmentDistance(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;

  if (len2 === 0) {
    const ddx = px - x1;
    const ddy = py - y1;
    return Math.sqrt(ddx * ddx + ddy * ddy);
  }

  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;

  const ddx = px - projX;
  const ddy = py - projY;
  return Math.sqrt(ddx * ddx + ddy * ddy);
}

function getLineAABB(line: NormalizedLine): BBox {
  return {
    minX: Math.min(line.x1, line.x2),
    minY: Math.min(line.y1, line.y2),
    maxX: Math.max(line.x1, line.x2),
    maxY: Math.max(line.y1, line.y2),
  };
}

function aabbIntersects(a: BBox, b: BBox): boolean {
  return !(a.maxX < b.minX || a.minX > b.maxX || a.maxY < b.minY || a.minY > b.maxY);
}

// ============================================================================
// SPATIAL GRID
// ============================================================================

class SpatialGrid {
  private cellSize: number;
  private grid: Map<string, GridCell[]>;
  private bbox: BBox;

  constructor(bbox: BBox, cellSize?: number) {
    this.bbox = bbox;
    const width = bbox.maxX - bbox.minX;
    const height = bbox.maxY - bbox.minY;
    this.cellSize = cellSize || Math.max(width, height) / 200 || 1;
    this.grid = new Map();
  }

  private getCellKey(cx: number, cy: number): string {
    return `${cx},${cy}`;
  }

  private getCellCoords(wx: number, wy: number): { cx: number; cy: number } {
    return {
      cx: Math.floor((wx - this.bbox.minX) / this.cellSize),
      cy: Math.floor((wy - this.bbox.minY) / this.cellSize),
    };
  }

  insertLine(layerIdx: number, lineIdx: number, line: NormalizedLine): void {
    const aabb = getLineAABB(line);
    const minCell = this.getCellCoords(aabb.minX, aabb.minY);
    const maxCell = this.getCellCoords(aabb.maxX, aabb.maxY);

    for (let cy = minCell.cy; cy <= maxCell.cy; cy++) {
      for (let cx = minCell.cx; cx <= maxCell.cx; cx++) {
        const key = this.getCellKey(cx, cy);
        if (!this.grid.has(key)) {
          this.grid.set(key, []);
        }
        this.grid.get(key)!.push({ layerIdx, lineIdx });
      }
    }
  }

  query(wx: number, wy: number, tolWorld: number): GridCell[] {
    const candidates = new Set<string>();
    const rCells = Math.ceil(tolWorld / this.cellSize);

    const centerCell = this.getCellCoords(wx, wy);
    for (let dy = -rCells; dy <= rCells; dy++) {
      for (let dx = -rCells; dx <= rCells; dx++) {
        const cx = centerCell.cx + dx;
        const cy = centerCell.cy + dy;
        const key = this.getCellKey(cx, cy);
        const cell = this.grid.get(key);
        if (cell) {
          for (const item of cell) {
            candidates.add(`${item.layerIdx},${item.lineIdx}`);
          }
        }
      }
    }

    return Array.from(candidates).map((key) => {
      const [layerIdx, lineIdx] = key.split(',').map(Number);
      return { layerIdx, lineIdx };
    });
  }

  clear(): void {
    this.grid.clear();
  }
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export const CadCanvasViewer: React.FC<CadCanvasViewerProps> = ({
  jobId,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [canvasData, setCanvasData] = useState<ServerCanvasData | null>(null);
  const [normalizedData, setNormalizedData] = useState<{
    bbox: BBox;
    layers: NormalizedLayer[];
  } | null>(null);
  const [transform, setTransform] = useState<Transform>({ scale: 1, tx: 0, ty: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<Point | null>(null);
  const [hoveredLine, setHoveredLine] = useState<HoveredLine | null>(null);
  const [selectedLine, setSelectedLine] = useState<HoveredLine | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<Record<number, boolean>>({});
  const [showLayerList, setShowLayerList] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPairs, setShowPairs] = useState(false);
  const [pairsData, setPairsData] = useState<NormalizedPair[] | null>(null);
  const [pairsLoading, setPairsLoading] = useState(false);
  const [pairsError, setPairsError] = useState<string | null>(null);
  const [showPairsB, setShowPairsB] = useState(false);
  const [pairsDataB, setPairsDataB] = useState<NormalizedPair[] | null>(null);
  const [pairsLoadingB, setPairsLoadingB] = useState(false);
  const [pairsErrorB, setPairsErrorB] = useState<string | null>(null);
  const [hoveredPair, setHoveredPair] = useState<HoveredPair | null>(null);
  const [moveMode, setMoveMode] = useState(false);

  const gridRef = useRef<SpatialGrid | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  // ============================================================================
  // DATA FETCHING
  // ============================================================================

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getJobCanvasData(jobId);
        if (!cancelled) {
          setCanvasData(data);
          const normalized = normalizeData(data);
          setNormalizedData(normalized);

          // Initialize layer visibility from server data
          const visibility: Record<number, boolean> = {};
          normalized.layers.forEach((layer, idx) => {
            visibility[idx] = layer.visible;
          });
          setLayerVisibility(visibility);

          // Fit to view after layout (container may not have size yet)
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              const container = containerRef.current;
              if (container?.clientWidth > 0 && container?.clientHeight > 0) {
                const bbox = normalized.bbox;
                const padding = 20;
                const width = container.clientWidth;
                const height = container.clientHeight;
                const bboxWidth = bbox.maxX - bbox.minX;
                const bboxHeight = bbox.maxY - bbox.minY;
                if (bboxWidth > 0 && bboxHeight > 0) {
                  const scale = Math.min(
                    (width - padding * 2) / bboxWidth,
                    (height - padding * 2) / bboxHeight
                  );
                  const centerX = (bbox.minX + bbox.maxX) / 2;
                  const centerY = (bbox.minY + bbox.maxY) / 2;
                  setTransform({
                    scale,
                    tx: width / 2 - centerX * scale,
                    ty: height / 2 - centerY * scale,
                  });
                }
              }
            });
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load canvas data');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  // Reset pairs data when jobId changes
  useEffect(() => {
    setPairsData(null);
    setPairsError(null);
    setHoveredPair(null);
    setShowPairs(false);
    setPairsDataB(null);
    setPairsErrorB(null);
    setShowPairsB(false);
  }, [jobId]);

  // ============================================================================
  // PAIRS DATA FETCHING (Lazy Load)
  // ============================================================================

  useEffect(() => {
    console.log('🔵 useEffect triggered:', { 
      showPairs, 
      hasData: pairsData !== null, 
      isLoading: pairsLoading, 
      jobId 
    });
    
    if (!showPairs || pairsData !== null || pairsLoading) {
      console.log('⏸️ Skipping fetch:', { 
        showPairs, 
        hasData: pairsData !== null, 
        isLoading: pairsLoading 
      });
      return;
    }

    let cancelled = false;

    const fetchPairs = async () => {
      try {
        setPairsLoading(true);
        setPairsError(null);
        const data = await getJobWallCandidatePairs(jobId);
        console.log('📦 Raw data from API:', data);
        console.log('📊 Pairs array length:', data?.pairs?.length || 0);
        
        if (!cancelled) {
          const normalized = normalizePairsData(data);
          console.log('✅ Normalized pairs:', normalized);
          console.log('📊 Normalized count:', normalized.length);
          setPairsData(normalized);
          console.log('✅ State updated! pairsData set to:', normalized.length, 'pairs');
        }
      } catch (err) {
        console.error('❌ Error fetching pairs:', err);
        if (!cancelled) {
          setPairsError(err instanceof Error ? err.message : 'Failed to load pairs data');
        }
      } finally {
        if (!cancelled) {
          console.log('🏁 Setting pairsLoading to false');
          setPairsLoading(false);
        }
      }
    };

    fetchPairs();

    return () => {
      console.log('🧹 Cleanup: cancelling fetch');
      cancelled = true;
    };
  }, [jobId, showPairs, pairsData]); // Removed pairsLoading from dependencies to prevent stuck state

  // Pairs B (Logic B) lazy fetch – same pattern as Pairs: no pairsLoadingB in deps to avoid stuck/loop
  useEffect(() => {
    if (!showPairsB || pairsDataB !== null || pairsLoadingB) return;
    let cancelled = false;
    const fetchPairsB = async () => {
      try {
        setPairsLoadingB(true);
        setPairsErrorB(null);
        const data = await getJobWallCandidatePairsB(jobId);
        if (!cancelled) setPairsDataB(normalizePairsData(data));
      } catch (err) {
        if (!cancelled) {
          setPairsErrorB(err instanceof Error ? err.message : 'Failed to load pairs B');
          setPairsDataB([]);
        }
      } finally {
        if (!cancelled) setPairsLoadingB(false);
      }
    };
    fetchPairsB();
    return () => { cancelled = true; };
  }, [jobId, showPairsB, pairsDataB]);

  // ============================================================================
  // SPATIAL GRID BUILDING
  // ============================================================================

  useEffect(() => {
    if (!normalizedData) return;

    const grid = new SpatialGrid(normalizedData.bbox);
    normalizedData.layers.forEach((layer, layerIdx) => {
      layer.lines.forEach((line, lineIdx) => {
        grid.insertLine(layerIdx, lineIdx, line);
      });
    });
    gridRef.current = grid;
  }, [normalizedData]);

  // ============================================================================
  // FIT TO VIEW
  // ============================================================================

  const fitToView = useCallback(() => {
    if (!normalizedData || !containerRef.current) return;

    const container = containerRef.current;
    const padding = 20;
    const width = container.clientWidth;
    const height = container.clientHeight;

    const bbox = normalizedData.bbox;
    const bboxWidth = bbox.maxX - bbox.minX;
    const bboxHeight = bbox.maxY - bbox.minY;

    if (bboxWidth === 0 || bboxHeight === 0) return;

    const scaleX = (width - padding * 2) / bboxWidth;
    const scaleY = (height - padding * 2) / bboxHeight;
    const scale = Math.min(scaleX, scaleY);

    const centerX = (bbox.minX + bbox.maxX) / 2;
    const centerY = (bbox.minY + bbox.maxY) / 2;

    const tx = width / 2 - centerX * scale;
    const ty = height / 2 - centerY * scale;

    setTransform({ scale, tx, ty });
  }, [normalizedData]);

  const ZOOM_FACTOR = 1.25;
  const zoomIn = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const centerCssX = rect.width / 2 / dpr;
    const centerCssY = rect.height / 2 / dpr;
    const worldCenter = screenToWorld(centerCssX, centerCssY, transform);
    const newScale = Math.min(1e6, transform.scale * ZOOM_FACTOR);
    const newTx = centerCssX - worldCenter.x * newScale;
    const newTy = centerCssY - worldCenter.y * newScale;
    setTransform({ scale: newScale, tx: newTx, ty: newTy });
  }, [transform]);

  const zoomOut = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const centerCssX = rect.width / 2 / dpr;
    const centerCssY = rect.height / 2 / dpr;
    const worldCenter = screenToWorld(centerCssX, centerCssY, transform);
    const newScale = Math.max(1e-6, transform.scale / ZOOM_FACTOR);
    const newTx = centerCssX - worldCenter.x * newScale;
    const newTy = centerCssY - worldCenter.y * newScale;
    setTransform({ scale: newScale, tx: newTx, ty: newTy });
  }, [transform]);

  // ============================================================================
  // CANVAS SETUP & RESIZE + AUTO FIT WHEN CONTAINER HAS DIMENSIONS
  // ============================================================================

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const updateCanvasSize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = container.getBoundingClientRect();
      const cssWidth = rect.width;
      const cssHeight = rect.height;

      canvas.width = cssWidth * dpr;
      canvas.height = cssHeight * dpr;
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;

      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
    };

    const runFitIfReady = () => {
      if (normalizedData && container.clientWidth > 0 && container.clientHeight > 0) {
        fitToView();
      }
    };

    updateCanvasSize();
    runFitIfReady();

    resizeObserverRef.current = new ResizeObserver(() => {
      updateCanvasSize();
      runFitIfReady();
    });
    resizeObserverRef.current.observe(container);

    return () => {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
    };
  }, [normalizedData, fitToView]);

  // ============================================================================
  // RENDERING
  // ============================================================================

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !normalizedData) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const cssWidth = rect.width / dpr;
    const cssHeight = rect.height / dpr;

    ctx.clearRect(0, 0, cssWidth, cssHeight);

    // Compute visible world bounds for culling
    const topLeft = screenToWorld(0, 0, transform);
    const bottomRight = screenToWorld(cssWidth, cssHeight, transform);
    const viewportBBox: BBox = {
      minX: Math.min(topLeft.x, bottomRight.x),
      minY: Math.min(topLeft.y, bottomRight.y),
      maxX: Math.max(topLeft.x, bottomRight.x),
      maxY: Math.max(topLeft.y, bottomRight.y),
    };

    // Render layers
    normalizedData.layers.forEach((layer, layerIdx) => {
      const isVisible = layerVisibility[layerIdx] ?? layer.visible;
      if (!isVisible) return;

      ctx.strokeStyle = layer.color;
      ctx.lineWidth = 1;
      ctx.beginPath();

      let hasLines = false;
      layer.lines.forEach((line) => {
        const lineAABB = getLineAABB(line);
        if (!aabbIntersects(lineAABB, viewportBBox)) return;

        const p1 = worldToScreen(line.x1, line.y1, transform);
        const p2 = worldToScreen(line.x2, line.y2, transform);

        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        hasLines = true;
      });

      if (hasLines) {
        ctx.stroke();
      }
    });

    // Render hovered line (above others)
    if (hoveredLine && !selectedLine) {
      const layer = normalizedData.layers[hoveredLine.layerIdx];
      const line = layer.lines[hoveredLine.lineIdx];

      ctx.strokeStyle = '#FFD700'; // Yellow
      ctx.lineWidth = 3;
      ctx.beginPath();

      const p1 = worldToScreen(line.x1, line.y1, transform);
      const p2 = worldToScreen(line.x2, line.y2, transform);

      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();

      // Draw endpoint markers
      ctx.fillStyle = '#FFD700';
      ctx.beginPath();
      ctx.arc(p1.x, p1.y, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p2.x, p2.y, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Render selected line (above hovered)
    if (selectedLine) {
      const layer = normalizedData.layers[selectedLine.layerIdx];
      const line = layer.lines[selectedLine.lineIdx];

      ctx.strokeStyle = '#00FFFF'; // Cyan
      ctx.lineWidth = 3;
      ctx.beginPath();

      const p1 = worldToScreen(line.x1, line.y1, transform);
      const p2 = worldToScreen(line.x2, line.y2, transform);

      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();

      // Draw endpoint markers
      ctx.fillStyle = '#00FFFF';
      ctx.beginPath();
      ctx.arc(p1.x, p1.y, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p2.x, p2.y, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Render pairs overlay (after selected line)
    console.log('🎨 Render check:', { showPairs, pairsDataLength: pairsData?.length || 0 });
    if (showPairs && pairsData) {
      console.log('🎨 Rendering', pairsData.length, 'pairs');
      pairsData.forEach((pair, pairIdx) => {
        // Viewport culling: check if rectangle intersects viewport
        const intersects = aabbIntersects(pair.rect, viewportBBox);
        if (!intersects) {
          console.log(`⏭️ Pair ${pairIdx} outside viewport`);
          return;
        }
        console.log(`🎨 Drawing pair ${pairIdx}:`, pair.rect);

        const rect = pair.rect;
        // Get 4 world corners
        const corners = [
          { x: rect.minX, y: rect.minY },
          { x: rect.maxX, y: rect.minY },
          { x: rect.maxX, y: rect.maxY },
          { x: rect.minX, y: rect.maxY },
        ];

        // Transform to screen coordinates
        const screenCorners = corners.map((corner) =>
          worldToScreen(corner.x, corner.y, transform)
        );

        // Draw rectangle
        ctx.beginPath();
        ctx.moveTo(screenCorners[0].x, screenCorners[0].y);
        for (let i = 1; i < screenCorners.length; i++) {
          ctx.lineTo(screenCorners[i].x, screenCorners[i].y);
        }
        ctx.closePath();

        // Fill with semi-transparent blue
        ctx.fillStyle = 'rgba(0, 102, 255, 0.2)';
        ctx.fill();

        // Stroke: black frame when hovered for visibility, blue otherwise
        ctx.strokeStyle = hoveredPair?.pairIdx === pairIdx ? '#000000' : '#0066FF';
        ctx.lineWidth = hoveredPair?.pairIdx === pairIdx ? 3 : 2; // Thicker when hovered
        ctx.stroke();
        console.log(`✅ Pair ${pairIdx} drawn successfully`);
      });
      console.log('🎨 Finished rendering all pairs');
    } else {
      console.log('⏸️ Not rendering pairs:', { showPairs, hasData: pairsData !== null });
    }

    // Pairs B (Logic B) overlay – green
    if (showPairsB && pairsDataB) {
      ctx.save();
      pairsDataB.forEach((pair, pairIdx) => {
        const intersects = aabbIntersects(pair.rect, viewportBBox);
        if (!intersects) return;
        const rect = pair.rect;
        const corners = [
          { x: rect.minX, y: rect.minY },
          { x: rect.maxX, y: rect.minY },
          { x: rect.maxX, y: rect.maxY },
          { x: rect.minX, y: rect.maxY },
        ];
        const screenCorners = corners.map((c) => worldToScreen(c.x, c.y, transform));
        ctx.beginPath();
        ctx.moveTo(screenCorners[0].x, screenCorners[0].y);
        for (let i = 1; i < screenCorners.length; i++) ctx.lineTo(screenCorners[i].x, screenCorners[i].y);
        ctx.closePath();
        ctx.fillStyle = 'rgba(0, 180, 0, 0.25)';
        ctx.fill();
        ctx.strokeStyle = 'rgb(0, 140, 0)';
        ctx.lineWidth = 2;
        ctx.stroke();
      });
      ctx.restore();
    }
  }, [normalizedData, transform, hoveredLine, selectedLine, layerVisibility, showPairs, pairsData, showPairsB, pairsDataB, hoveredPair]);

  useEffect(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    animationFrameRef.current = requestAnimationFrame(render);
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [render]);

  // ============================================================================
  // HOVER DETECTION
  // ============================================================================

  const updateHover = useCallback(
    (clientX: number, clientY: number) => {
      if (!normalizedData || !canvasRef.current || isPanning || !gridRef.current) {
        setHoveredLine(null);
        return;
      }

      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssX = (clientX - rect.left) / dpr;
      const cssY = (clientY - rect.top) / dpr;

      const worldPoint = screenToWorld(cssX, cssY, transform);
      const tolPx = 6;
      const tolWorld = tolPx / transform.scale;

      const candidates = gridRef.current.query(worldPoint.x, worldPoint.y, tolWorld);

      let best: HoveredLine | null = null;
      let bestDist = tolWorld;

      candidates.forEach(({ layerIdx, lineIdx }) => {
        const layer = normalizedData.layers[layerIdx];
        const isVisible = layerVisibility[layerIdx] ?? layer.visible;
        if (!isVisible) return;

        const line = layer.lines[lineIdx];
        const dist = pointToSegmentDistance(
          worldPoint.x,
          worldPoint.y,
          line.x1,
          line.y1,
          line.x2,
          line.y2
        );

        if (dist < bestDist) {
          bestDist = dist;
          best = { layerIdx, lineIdx, distance: dist };
        }
      });

      setHoveredLine(best);
    },
    [normalizedData, transform, isPanning, layerVisibility]
  );

  const updatePairsHover = useCallback(
    (clientX: number, clientY: number) => {
      if (!showPairs || !pairsData || !canvasRef.current || isPanning) {
        setHoveredPair(null);
        return;
      }

      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssX = (clientX - rect.left) / dpr;
      const cssY = (clientY - rect.top) / dpr;

      const worldPoint = screenToWorld(cssX, cssY, transform);

      // Check if mouse is inside any pair's bounding rectangle
      let found: HoveredPair | null = null;
      for (let i = 0; i < pairsData.length; i++) {
        const pair = pairsData[i];
        const rect = pair.rect;
        if (
          worldPoint.x >= rect.minX &&
          worldPoint.x <= rect.maxX &&
          worldPoint.y >= rect.minY &&
          worldPoint.y <= rect.maxY
        ) {
          found = { pairIdx: i };
          break;
        }
      }

      setHoveredPair(found);
    },
    [showPairs, pairsData, transform, isPanning]
  );

  // ============================================================================
  // MOUSE EVENT HANDLERS
  // ============================================================================

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const isSpacePan = e.button === 0 && (e.getModifierState as (key: string) => boolean)('Space');
      const isMiddlePan = e.button === 1;
      const isMoveModePan = moveMode && e.button === 0;

      if (isSpacePan || isMiddlePan || isMoveModePan) {
        e.preventDefault();
        setIsPanning(true);
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        setPanStart({
          x: (e.clientX - rect.left) / dpr,
          y: (e.clientY - rect.top) / dpr,
        });
        canvas.style.cursor = 'grabbing';
      } else if (e.button === 0 && !moveMode) {
        // Left click - select/deselect (only when not in Move mode)
        if (hoveredLine) {
          setSelectedLine(selectedLine?.layerIdx === hoveredLine.layerIdx &&
            selectedLine?.lineIdx === hoveredLine.lineIdx
            ? null
            : hoveredLine);
        } else {
          setSelectedLine(null);
        }
      }
    },
    [hoveredLine, selectedLine, moveMode]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isPanning && panStart) {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const currentX = (e.clientX - rect.left) / dpr;
        const currentY = (e.clientY - rect.top) / dpr;

        const dx = currentX - panStart.x;
        const dy = currentY - panStart.y;

        setTransform((prev) => ({
          ...prev,
          tx: prev.tx + dx,
          ty: prev.ty + dy,
        }));

        setPanStart({ x: currentX, y: currentY });
      } else {
        updateHover(e.clientX, e.clientY);
        if (showPairs) {
          updatePairsHover(e.clientX, e.clientY);
        }
      }
    },
    [isPanning, panStart, updateHover, showPairs, updatePairsHover]
  );

  const handleMouseUp = useCallback(() => {
    if (isPanning) {
      setIsPanning(false);
      setPanStart(null);
      const canvas = canvasRef.current;
      if (canvas) {
        canvas.style.cursor = moveMode ? 'grab' : '';
      }
    }
  }, [isPanning, moveMode]);

  const handleMouseLeave = useCallback(() => {
    setIsPanning(false);
    setPanStart(null);
    setHoveredLine(null);
    setHoveredPair(null);
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.style.cursor = moveMode ? 'grab' : '';
    }
  }, [moveMode]);

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      e.preventDefault();

      const canvas = canvasRef.current;
      if (!canvas || !normalizedData) return;

      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssX = (e.clientX - rect.left) / dpr;
      const cssY = (e.clientY - rect.top) / dpr;

      const worldPoint = screenToWorld(cssX, cssY, transform);

      let zoomFactor = 1.1;
      if (e.ctrlKey) zoomFactor = 1.05; // Slower with Ctrl
      if (e.shiftKey) zoomFactor = 1.2; // Faster with Shift

      if (e.deltaY > 0) {
        zoomFactor = 1 / zoomFactor;
      }

      const newScale = Math.max(1e-6, Math.min(1e6, transform.scale * zoomFactor));

      // Keep world point under cursor fixed
      const newTx = cssX - worldPoint.x * newScale;
      const newTy = cssY - worldPoint.y * newScale;

      setTransform({ scale: newScale, tx: newTx, ty: newTy });
    },
    [transform, normalizedData]
  );

  // ============================================================================
  // KEYBOARD EVENT HANDLERS
  // ============================================================================

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && canvasRef.current && !moveMode) {
        canvasRef.current.style.cursor = 'grab';
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && canvasRef.current && !isPanning && !moveMode) {
        canvasRef.current.style.cursor = '';
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [isPanning, moveMode]);

  // ============================================================================
  // CONTEXT MENU PREVENTION (for middle mouse)
  // ============================================================================

  useEffect(() => {
    const handleContextMenu = (e: MouseEvent) => {
      if (e.button === 1) {
        e.preventDefault();
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('contextmenu', handleContextMenu);
      return () => {
        container.removeEventListener('contextmenu', handleContextMenu);
      };
    }
  }, []);

  // When Move mode is on, show grab cursor on canvas (and sync when toggling mode)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || isPanning) return;
    canvas.style.cursor = moveMode ? 'grab' : '';
  }, [moveMode, isPanning]);

  const handleMouseEnter = useCallback(() => {
    if (moveMode && canvasRef.current && !isPanning) {
      canvasRef.current.style.cursor = 'grab';
    }
  }, [moveMode, isPanning]);

  // ============================================================================
  // RENDER
  // ============================================================================

  if (isLoading) {
    return (
      <div className={`cad-canvas-viewer ${className}`} style={{ padding: '20px', textAlign: 'center' }}>
        <p>Loading canvas data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`cad-canvas-viewer ${className}`} style={{ padding: '20px', textAlign: 'center' }}>
        <p style={{ color: 'red' }}>Error: {error}</p>
      </div>
    );
  }

  if (!normalizedData || normalizedData.layers.length === 0) {
    return (
      <div className={`cad-canvas-viewer ${className}`} style={{ padding: '20px', textAlign: 'center' }}>
        <p>No canvas data available</p>
      </div>
    );
  }

  const hoveredLineData = hoveredLine
    ? normalizedData.layers[hoveredLine.layerIdx].lines[hoveredLine.lineIdx]
    : null;
  const selectedLineData = selectedLine
    ? normalizedData.layers[selectedLine.layerIdx].lines[selectedLine.lineIdx]
    : null;
  const hoveredPairData = hoveredPair && pairsData ? pairsData[hoveredPair.pairIdx] : null;

  return (
    <div
      ref={containerRef}
      className={`cad-canvas-viewer ${className}`}
      style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}
    >
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onWheel={handleWheel}
        style={{
          display: 'block',
          width: '100%',
          height: '100%',
          touchAction: 'none',
        }}
      />

      {/* UI Overlay */}
      <div
        style={{
          position: 'absolute',
          top: '10px',
          left: '10px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          zIndex: 10,
        }}
      >
        <button
          onClick={fitToView}
          style={{
            padding: '8px 16px',
            backgroundColor: '#fff',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
          title="Fit to View (Zoom Extents)"
        >
          Fit to View
        </button>

        <button
          onClick={() => setMoveMode((m) => !m)}
          style={{
            padding: '8px 16px',
            backgroundColor: moveMode ? '#333' : '#fff',
            color: moveMode ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
          title="Move: drag to pan the canvas (or use Space + drag / middle mouse)"
        >
          {moveMode ? 'Move On' : 'Move'}
        </button>

        <button
          onClick={() => setShowPairs(!showPairs)}
          disabled={pairsLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showPairs ? '#0066FF' : '#fff',
            color: showPairs ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: pairsLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: pairsLoading ? 0.6 : 1,
          }}
          title="Show/Hide Wall Candidate Pairs"
        >
          {pairsLoading ? 'Loading...' : showPairs ? 'Hide Pairs' : 'Show Pairs'}
        </button>

        <button
          onClick={() => setShowPairsB(!showPairsB)}
          disabled={pairsLoadingB}
          style={{
            padding: '8px 16px',
            backgroundColor: showPairsB ? '#008C00' : '#fff',
            color: showPairsB ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: pairsLoadingB ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: pairsLoadingB ? 0.6 : 1,
          }}
          title="Show/Hide Wall Candidate Pairs B (Logic B)"
        >
          {pairsLoadingB ? 'Loading...' : showPairsB ? 'Hide Pairs B' : 'Candidate Pairs B'}
        </button>

        {pairsError && (
          <div
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              color: 'red',
              backgroundColor: '#fff',
              border: '1px solid #ccc',
              borderRadius: '4px',
            }}
          >
            {pairsError}
          </div>
        )}
        {pairsErrorB && (
          <div
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              color: 'red',
              backgroundColor: '#fff',
              border: '1px solid #ccc',
              borderRadius: '4px',
            }}
          >
            {pairsErrorB}
          </div>
        )}

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <button
            onClick={zoomOut}
            style={{
              width: '36px',
              height: '36px',
              padding: 0,
              backgroundColor: '#fff',
              border: '1px solid #ccc',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '18px',
              fontWeight: 'bold',
              lineHeight: 1,
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            }}
            title="Zoom Out (−)"
          >
            −
          </button>
          <span style={{ fontSize: '12px', color: '#666', minWidth: '32px', textAlign: 'center' }}>
            Zoom
          </span>
          <button
            onClick={zoomIn}
            style={{
              width: '36px',
              height: '36px',
              padding: 0,
              backgroundColor: '#fff',
              border: '1px solid #ccc',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '18px',
              fontWeight: 'bold',
              lineHeight: 1,
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            }}
            title="Zoom In (+)"
          >
            +
          </button>
        </div>

        <button
          onClick={() => setShowLayerList(!showLayerList)}
          style={{
            padding: '8px 16px',
            backgroundColor: '#fff',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
        >
          {showLayerList ? 'Hide' : 'Show'} Layers
        </button>
      </div>

      {/* Layer List */}
      {showLayerList && (
        <div
          style={{
            position: 'absolute',
            top: '60px',
            left: '10px',
            backgroundColor: '#fff',
            border: '1px solid #ccc',
            borderRadius: '4px',
            padding: '10px',
            maxHeight: '400px',
            overflowY: 'auto',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            zIndex: 10,
            minWidth: '200px',
          }}
        >
          <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>Layers</div>
          {normalizedData.layers.map((layer, idx) => (
            <label
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '4px 0',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={layerVisibility[idx] ?? layer.visible}
                onChange={(e) => {
                  setLayerVisibility((prev) => ({
                    ...prev,
                    [idx]: e.target.checked,
                  }));
                }}
              />
              <div
                style={{
                  width: '16px',
                  height: '16px',
                  backgroundColor: layer.color,
                  border: '1px solid #ccc',
                }}
              />
              <span style={{ fontSize: '12px' }}>{layer.name}</span>
              <span style={{ fontSize: '11px', color: '#666', marginLeft: 'auto' }}>
                ({layer.lines.length})
              </span>
            </label>
          ))}
        </div>
      )}

      {/* Tooltip */}
      {(hoveredLineData || selectedLineData || hoveredPairData) && (
        <div
          style={{
            position: 'absolute',
            bottom: '10px',
            left: '10px',
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            color: '#fff',
            padding: '10px',
            borderRadius: '4px',
            fontSize: '12px',
            zIndex: 10,
            maxWidth: '300px',
          }}
        >
          {selectedLineData ? (
            <div>
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Selected Line</div>
              <div>Layer: {normalizedData.layers[selectedLine.layerIdx].name}</div>
              <div>ID: {selectedLineData.id}</div>
              <div>Length: {selectedLineData.length.toFixed(2)}</div>
              <div>
                Start: ({selectedLineData.x1.toFixed(2)}, {selectedLineData.y1.toFixed(2)})
              </div>
              <div>
                End: ({selectedLineData.x2.toFixed(2)}, {selectedLineData.y2.toFixed(2)})
              </div>
            </div>
          ) : hoveredLineData ? (
            <div>
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Hovered Line</div>
              <div>Layer: {normalizedData.layers[hoveredLine.layerIdx].name}</div>
              <div>ID: {hoveredLineData.id}</div>
              <div>Length: {hoveredLineData.length.toFixed(2)}</div>
              <div style={{ fontSize: '11px', color: '#ccc', marginTop: '4px' }}>
                Click to select
              </div>
            </div>
          ) : hoveredPairData ? (
            <div>
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Wall Candidate Pair</div>
              <div>Pair ID: {hoveredPairData.pairId}</div>
              <div>Layer 1: {hoveredPairData.layer1}</div>
              <div>Layer 2: {hoveredPairData.layer2}</div>
              <div>Distance: {hoveredPairData.perpendicular_distance.toFixed(2)} mm</div>
              <div>אחוזי חפיפה (Overlap): {hoveredPairData.overlap_percentage.toFixed(1)}%</div>
              <div>Angle Diff: {hoveredPairData.angle_difference.toFixed(2)}°</div>
              <div>Avg Length: {hoveredPairData.average_length.toFixed(2)} mm</div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default CadCanvasViewer;
