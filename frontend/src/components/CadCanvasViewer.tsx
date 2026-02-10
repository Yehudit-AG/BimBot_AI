import React, { useRef, useEffect, useState, useCallback } from 'react';
import { getJobCanvasData, getJobWallCandidatePairs, getJobLogicBPairs, getJobLogicCPairs, getJobLogicDRectangles, getJobLogicERectangles, getJobStatus, getWindowDoorBlocksList, getJobDoorBridges } from '../services/api';

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

/** Block data from window/door collection (data field from API). */
interface WindowDoorBlockData {
  Position?: { X: number; Y: number; Z?: number };
  Rotation?: number;
  rotate?: number;
  BoundingBox?: {
    MinPoint: { X: number; Y: number; Z?: number };
    MaxPoint: { X: number; Y: number; Z?: number };
  };
  Name?: string;
  [key: string]: unknown;
}

/** One window or door block from GET /drawings/{id}/window-door-blocks/list */
interface WindowDoorBlock {
  layer_name: string;
  entity_type: string;
  window_or_door: 'window' | 'door';
  data: WindowDoorBlockData;
}

/** One door entry from GET /jobs/{id}/door-bridges (door_bridges array item) */
interface DoorBridgeEntry {
  doorId: number;
  bridges: Array<{
    bridgeRectangle: { minX: number; minY: number; maxX: number; maxY: number };
    meta?: Record<string, unknown>;
  }>;
  meta?: Record<string, unknown>;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/** Order 4 corners by angle from centroid so the path is a solid quad (no bow-tie X). */
function orderQuadCorners(corners: Array<{ x: number; y: number }>): Array<{ x: number; y: number }> {
  if (corners.length !== 4) return corners;
  const cx = (corners[0].x + corners[1].x + corners[2].x + corners[3].x) / 4;
  const cy = (corners[0].y + corners[1].y + corners[2].y + corners[3].y) / 4;
  const withAngle = corners.map((p) => ({
    ...p,
    angle: Math.atan2(p.y - cy, p.x - cx),
  }));
  withAngle.sort((a, b) => a.angle - b.angle);
  return withAngle.map(({ x, y }) => ({ x, y }));
}

/** Ray-casting point-in-polygon for arbitrary polygon (vertices in order). */
function pointInPolygon(px: number, py: number, vertices: Array<{ x: number; y: number }>): boolean {
  let inside = false;
  const n = vertices.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = vertices[i].x;
    const yi = vertices[i].y;
    const xj = vertices[j].x;
    const yj = vertices[j].y;
    if (yi > py !== yj > py && px < (xj - xi) * (py - yi) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

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
// WINDOW/DOOR BLOCK HELPERS (0° = North/up, rotation CCW)
// ============================================================================

function bradanimToDegrees(bradanim: number): number {
  return bradanim;
}

/** Return rotation in degrees, snapped to nearest 90° (0, 90, 180, 270) so geometry is axis-aligned. */
function getBlockRotationDegrees(data: WindowDoorBlockData): number {
  const raw = data.Rotation ?? data.rotate ?? 0;
  const degrees = bradanimToDegrees(Number(raw));
  const rounded = Math.round(degrees);
  const snapped = Math.round(rounded / 90) * 90;
  return ((snapped % 360) + 360) % 360;
}

/** Rotate point (px, py) CCW by angleRad around (cx, cy). 0 = North (+Y). */
function rotatePoint(px: number, py: number, cx: number, cy: number, angleRad: number): Point {
  const cos = Math.cos(angleRad);
  const sin = Math.sin(angleRad);
  const dx = px - cx;
  const dy = py - cy;
  return {
    x: cx + dx * cos - dy * sin,
    y: cy + dx * sin + dy * cos,
  };
}

/** Shared rotation logic: same for doors and windows. Returns 4 world corners (local 0..3 = minX,minY; maxX,minY; maxX,maxY; minX,maxY) and position. */
function getBlockWorldCorners(block: WindowDoorBlock): { corners: Point[]; pos: Point } | null {
  const d = block.data;
  const bbox = d.BoundingBox;
  if (!bbox?.MinPoint || !bbox?.MaxPoint) return null;
  const minX = bbox.MinPoint.X;
  const minY = bbox.MinPoint.Y;
  const maxX = bbox.MaxPoint.X;
  const maxY = bbox.MaxPoint.Y;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const pos = d.Position ?? { X: cx, Y: cy };
  const angleDeg = getBlockRotationDegrees(d);
  const angleRad = (angleDeg * Math.PI) / 180;
  const corners = [
    rotatePoint(minX, minY, cx, cy, angleRad),
    rotatePoint(maxX, minY, cx, cy, angleRad),
    rotatePoint(maxX, maxY, cx, cy, angleRad),
    rotatePoint(minX, maxY, cx, cy, angleRad),
  ];
  const tx = pos.X - cx;
  const ty = pos.Y - cy;
  return {
    corners: corners.map((p) => ({ x: p.x + tx, y: p.y + ty })),
    pos: { x: pos.X, y: pos.Y },
  };
}

function getBlockBBoxInWorld(block: WindowDoorBlock): BBox | null {
  const data = getBlockWorldCorners(block);
  if (!data) return null;
  const xs = data.corners.map((p) => p.x);
  const ys = data.corners.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

function drawWindow(
  ctx: CanvasRenderingContext2D,
  block: WindowDoorBlock,
  transform: Transform,
  viewportBBox: BBox,
  worldToScreen: (wx: number, wy: number, t: Transform) => Point
): void {
  const data = getBlockWorldCorners(block);
  if (!data) return;
  const { corners } = data;
  const blockBBox = getBlockBBoxInWorld(block);
  if (blockBBox && !aabbIntersects(blockBBox, viewportBBox)) return;
  ctx.strokeStyle = '#4682B4';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < corners.length; i++) {
    const p = worldToScreen(corners[i].x, corners[i].y, transform);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();
  ctx.stroke();
  const edge01Len = Math.hypot(corners[1].x - corners[0].x, corners[1].y - corners[0].y);
  const edge12Len = Math.hypot(corners[2].x - corners[1].x, corners[2].y - corners[1].y);
  const c1 = edge01Len >= edge12Len
    ? { x: (corners[0].x + corners[3].x) / 2, y: (corners[0].y + corners[3].y) / 2 }
    : { x: (corners[0].x + corners[1].x) / 2, y: (corners[0].y + corners[1].y) / 2 };
  const c2 = edge01Len >= edge12Len
    ? { x: (corners[1].x + corners[2].x) / 2, y: (corners[1].y + corners[2].y) / 2 }
    : { x: (corners[3].x + corners[2].x) / 2, y: (corners[3].y + corners[2].y) / 2 };
  const sc1 = worldToScreen(c1.x, c1.y, transform);
  const sc2 = worldToScreen(c2.x, c2.y, transform);
  ctx.beginPath();
  ctx.moveTo(sc1.x, sc1.y);
  ctx.lineTo(sc2.x, sc2.y);
  ctx.stroke();
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
  const [hoveredPair, setHoveredPair] = useState<HoveredPair | null>(null);
  const [showLogicBPairs, setShowLogicBPairs] = useState(false);
  const [logicBPairsData, setLogicBPairsData] = useState<Array<{
    pair_id: string;
    trimmedSegmentA: { p1: { X: number; Y: number }; p2: { X: number; Y: number } };
    trimmedSegmentB: { p1: { X: number; Y: number }; p2: { X: number; Y: number } };
    bounding_rectangle?: { minX: number; minY: number; maxX: number; maxY: number };
  }> | null>(null);
  const [logicBPairsLoading, setLogicBPairsLoading] = useState(false);
  const [logicBPairsError, setLogicBPairsError] = useState<string | null>(null);
  const [showLogicCPairs, setShowLogicCPairs] = useState(false);
  const [logicCPairsData, setLogicCPairsData] = useState<Array<{
    pair_id: string;
    trimmedSegmentA: { p1: { X: number; Y: number }; p2: { X: number; Y: number } };
    trimmedSegmentB: { p1: { X: number; Y: number }; p2: { X: number; Y: number } };
    bounding_rectangle?: { minX: number; minY: number; maxX: number; maxY: number };
  }> | null>(null);
  const [logicCPairsLoading, setLogicCPairsLoading] = useState(false);
  const [logicCPairsError, setLogicCPairsError] = useState<string | null>(null);
  const [hoveredLogicCPairIdx, setHoveredLogicCPairIdx] = useState<number | null>(null);
  const [showLogicDPairs, setShowLogicDPairs] = useState(false);
  const [logicDPairsData, setLogicDPairsData] = useState<Array<{
    trimmedSegmentA?: { p1?: { X: number; Y: number }; p2?: { X: number; Y: number } };
    trimmedSegmentB?: { p1?: { X: number; Y: number }; p2?: { X: number; Y: number } };
    bounding_rectangle?: { minX?: number; minY?: number; maxX?: number; maxY?: number };
  }> | null>(null);
  const [logicDPairsLoading, setLogicDPairsLoading] = useState(false);
  const [logicDPairsError, setLogicDPairsError] = useState<string | null>(null);
  const [hoveredLogicDPairIdx, setHoveredLogicDPairIdx] = useState<number | null>(null);
  const [showLogicEPairs, setShowLogicEPairs] = useState(false);
  const [logicEPairsData, setLogicEPairsData] = useState<Array<{
    trimmedSegmentA?: { p1?: { X: number; Y: number }; p2?: { X: number; Y: number } };
    trimmedSegmentB?: { p1?: { X: number; Y: number }; p2?: { X: number; Y: number } };
    bounding_rectangle?: { minX?: number; minY?: number; maxX?: number; maxY?: number };
  }> | null>(null);
  const [logicEPairsLoading, setLogicEPairsLoading] = useState(false);
  const [logicEPairsError, setLogicEPairsError] = useState<string | null>(null);
  const [hoveredLogicEPairIdx, setHoveredLogicEPairIdx] = useState<number | null>(null);
  const [moveMode, setMoveMode] = useState(false);
  const [showWindowDoorBlocks, setShowWindowDoorBlocks] = useState(true);
  const [windowDoorBlocks, setWindowDoorBlocks] = useState<WindowDoorBlock[] | null>(null);
  const [windowDoorBlocksLoading, setWindowDoorBlocksLoading] = useState(false);
  const [windowDoorBlocksError, setWindowDoorBlocksError] = useState<string | null>(null);
  const [showBridges, setShowBridges] = useState(false);
  const [bridgesData, setBridgesData] = useState<DoorBridgeEntry[] | null>(null);
  const [bridgesLoading, setBridgesLoading] = useState(false);
  const [bridgesError, setBridgesError] = useState<string | null>(null);

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
    setLogicBPairsData(null);
    setLogicBPairsError(null);
    setShowLogicBPairs(false);
    setLogicCPairsData(null);
    setLogicCPairsError(null);
    setShowLogicCPairs(false);
    setHoveredLogicCPairIdx(null);
    setLogicDPairsData(null);
    setLogicDPairsError(null);
    setShowLogicDPairs(false);
    setHoveredLogicDPairIdx(null);
    setLogicEPairsData(null);
    setLogicEPairsError(null);
    setShowLogicEPairs(false);
    setHoveredLogicEPairIdx(null);
    setWindowDoorBlocks(null);
    setWindowDoorBlocksError(null);
    setBridgesData(null);
    setBridgesError(null);
    setShowBridges(false);
  }, [jobId]);

  // Fetch window/door blocks for this job's drawing
  useEffect(() => {
    let cancelled = false;
    const fetchWindowDoorBlocks = async () => {
      try {
        setWindowDoorBlocksLoading(true);
        setWindowDoorBlocksError(null);
        const job = await getJobStatus(jobId);
        const drawingId = job?.drawing_id;
        if (!drawingId) {
          if (!cancelled) setWindowDoorBlocks([]);
          return;
        }
        const res = await getWindowDoorBlocksList(drawingId);
        if (!cancelled && Array.isArray(res?.blocks)) {
          setWindowDoorBlocks(res.blocks);
        } else if (!cancelled) {
          setWindowDoorBlocks([]);
        }
      } catch (err) {
        if (!cancelled) {
          setWindowDoorBlocksError(err instanceof Error ? err.message : 'Failed to load windows');
          setWindowDoorBlocks([]);
        }
      } finally {
        if (!cancelled) setWindowDoorBlocksLoading(false);
      }
    };
    fetchWindowDoorBlocks();
    return () => { cancelled = true; };
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

  // LOGIC B pairs: lazy load when overlay is toggled on
  // Do NOT put logicBPairsLoading in deps: then setting it true would re-run effect, cleanup would
  // set cancelled=true, and the completing request would skip updates → loading forever.
  useEffect(() => {
    if (!showLogicBPairs || logicBPairsData !== null || logicBPairsLoading) return;
    let cancelled = false;
    setLogicBPairsLoading(true);
    setLogicBPairsError(null);
    getJobLogicBPairs(jobId)
      .then((data) => {
        if (!cancelled) {
          setLogicBPairsData(Array.isArray(data?.pairs) ? data.pairs : []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLogicBPairsError(err instanceof Error ? err.message : 'Failed to load LOGIC B pairs');
          setLogicBPairsData([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLogicBPairsLoading(false);
      });
    return () => { cancelled = true; };
  }, [jobId, showLogicBPairs, logicBPairsData]);

  // LOGIC C pairs: lazy load when overlay is toggled on (same pattern as LOGIC B; no loading in deps)
  useEffect(() => {
    if (!showLogicCPairs || logicCPairsData !== null || logicCPairsLoading) return;
    let cancelled = false;
    setLogicCPairsLoading(true);
    setLogicCPairsError(null);
    getJobLogicCPairs(jobId)
      .then((data) => {
        if (!cancelled) {
          setLogicCPairsData(Array.isArray(data?.pairs) ? data.pairs : []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLogicCPairsError(err instanceof Error ? err.message : 'Failed to load LOGIC C pairs');
          setLogicCPairsData([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLogicCPairsLoading(false);
      });
    return () => { cancelled = true; };
  }, [jobId, showLogicCPairs, logicCPairsData]);

  // LOGIC D rectangles: lazy load when overlay is toggled on (same pattern as LOGIC B/C)
  useEffect(() => {
    if (!showLogicDPairs || logicDPairsData !== null || logicDPairsLoading) return;
    let cancelled = false;
    setLogicDPairsLoading(true);
    setLogicDPairsError(null);
    getJobLogicDRectangles(jobId)
      .then((data) => {
        if (!cancelled) {
          setLogicDPairsData(Array.isArray(data?.rectangles) ? data.rectangles : []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLogicDPairsError(err instanceof Error ? err.message : 'Failed to load LOGIC D rectangles');
          setLogicDPairsData([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLogicDPairsLoading(false);
      });
    return () => { cancelled = true; };
  }, [jobId, showLogicDPairs, logicDPairsData]);

  // LOGIC E rectangles: lazy load when overlay is toggled on (same pattern as LOGIC B/C/D)
  useEffect(() => {
    if (!showLogicEPairs || logicEPairsData !== null || logicEPairsLoading) return;
    let cancelled = false;
    setLogicEPairsLoading(true);
    setLogicEPairsError(null);
    getJobLogicERectangles(jobId)
      .then((data) => {
        if (!cancelled) {
          setLogicEPairsData(Array.isArray(data?.rectangles) ? data.rectangles : []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLogicEPairsError(err instanceof Error ? err.message : 'Failed to load LOGIC E rectangles');
          setLogicEPairsData([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLogicEPairsLoading(false);
      });
    return () => { cancelled = true; };
  }, [jobId, showLogicEPairs, logicEPairsData]);

  // Door bridges overlay: lazy load when toggled on
  useEffect(() => {
    if (!showBridges || bridgesData !== null || bridgesLoading) return;
    let cancelled = false;
    setBridgesLoading(true);
    setBridgesError(null);
    getJobDoorBridges(jobId)
      .then((data) => {
        if (!cancelled && Array.isArray(data?.door_bridges)) {
          setBridgesData(data.door_bridges);
        } else if (!cancelled) {
          setBridgesData([]);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setBridgesError(err instanceof Error ? err.message : 'Failed to load door bridges');
          setBridgesData([]);
        }
      })
      .finally(() => {
        if (!cancelled) setBridgesLoading(false);
      });
    return () => { cancelled = true; };
  }, [jobId, showBridges, bridgesData]);

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

    // Render window blocks only (from collected list; doors are not drawn)
    if (showWindowDoorBlocks && windowDoorBlocks && windowDoorBlocks.length > 0) {
      windowDoorBlocks.forEach((block) => {
        if (block.window_or_door === 'window') {
          drawWindow(ctx, block, transform, viewportBBox, worldToScreen);
        }
      });
    }

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

    // LOGIC B overlay: solid green quad (order corners by angle so no X/bow-tie)
    if (showLogicBPairs && logicBPairsData && logicBPairsData.length > 0) {
      logicBPairsData.forEach((pair) => {
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        const br = pair.bounding_rectangle;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) return;
        if (br && !aabbIntersects(br, viewportBBox)) return;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        const screenCorners = corners.map((c) => worldToScreen(c.x, c.y, transform));
        ctx.beginPath();
        ctx.moveTo(screenCorners[0].x, screenCorners[0].y);
        for (let i = 1; i < screenCorners.length; i++) {
          ctx.lineTo(screenCorners[i].x, screenCorners[i].y);
        }
        ctx.closePath();
        ctx.fillStyle = 'rgba(0, 160, 0, 0.45)';
        ctx.fill();
        ctx.strokeStyle = '#006600';
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    }

    // LOGIC C overlay: solid purple quad (same corner order as LOGIC B); black frame when hovered
    if (showLogicCPairs && logicCPairsData && logicCPairsData.length > 0) {
      logicCPairsData.forEach((pair, idx) => {
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        const br = pair.bounding_rectangle;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) return;
        if (br && !aabbIntersects(br, viewportBBox)) return;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        const screenCorners = corners.map((c) => worldToScreen(c.x, c.y, transform));
        ctx.beginPath();
        ctx.moveTo(screenCorners[0].x, screenCorners[0].y);
        for (let i = 1; i < screenCorners.length; i++) {
          ctx.lineTo(screenCorners[i].x, screenCorners[i].y);
        }
        ctx.closePath();
        ctx.fillStyle = 'rgba(128, 0, 128, 0.45)';
        ctx.fill();
        const isHovered = hoveredLogicCPairIdx === idx;
        ctx.strokeStyle = isHovered ? '#000000' : '#4B0082';
        ctx.lineWidth = isHovered ? 3 : 2;
        ctx.stroke();
      });
    }

    // LOGIC D overlay: solid orange quad (containment-pruned outer rectangles); black frame when hovered
    if (showLogicDPairs && logicDPairsData && logicDPairsData.length > 0) {
      logicDPairsData.forEach((pair, idx) => {
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        const br = pair.bounding_rectangle;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) return;
        const brBox: BBox | null = br != null && typeof br.minX === 'number' && typeof br.minY === 'number' && typeof br.maxX === 'number' && typeof br.maxY === 'number'
          ? { minX: br.minX, minY: br.minY, maxX: br.maxX, maxY: br.maxY }
          : null;
        if (brBox && !aabbIntersects(brBox, viewportBBox)) return;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        const screenCorners = corners.map((c) => worldToScreen(c.x, c.y, transform));
        ctx.beginPath();
        ctx.moveTo(screenCorners[0].x, screenCorners[0].y);
        for (let i = 1; i < screenCorners.length; i++) {
          ctx.lineTo(screenCorners[i].x, screenCorners[i].y);
        }
        ctx.closePath();
        ctx.fillStyle = 'rgba(204, 102, 0, 0.45)';
        ctx.fill();
        const isHovered = hoveredLogicDPairIdx === idx;
        ctx.strokeStyle = isHovered ? '#000000' : '#CC6600';
        ctx.lineWidth = isHovered ? 3 : 2;
        ctx.stroke();
      });
    }

    // LOGIC E overlay: solid teal quad (band-merged rectangles); black frame when hovered
    if (showLogicEPairs && logicEPairsData && logicEPairsData.length > 0) {
      logicEPairsData.forEach((pair, idx) => {
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        const br = pair.bounding_rectangle;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) return;
        const brBox: BBox | null = br != null && typeof br.minX === 'number' && typeof br.minY === 'number' && typeof br.maxX === 'number' && typeof br.maxY === 'number'
          ? { minX: br.minX, minY: br.minY, maxX: br.maxX, maxY: br.maxY }
          : null;
        if (brBox && !aabbIntersects(brBox, viewportBBox)) return;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        const screenCorners = corners.map((c) => worldToScreen(c.x, c.y, transform));
        ctx.beginPath();
        ctx.moveTo(screenCorners[0].x, screenCorners[0].y);
        for (let i = 1; i < screenCorners.length; i++) {
          ctx.lineTo(screenCorners[i].x, screenCorners[i].y);
        }
        ctx.closePath();
        ctx.fillStyle = 'rgba(0, 128, 128, 0.45)';
        ctx.fill();
        const isHovered = hoveredLogicEPairIdx === idx;
        ctx.strokeStyle = isHovered ? '#000000' : '#008080';
        ctx.lineWidth = isHovered ? 3 : 2;
        ctx.stroke();
      });
    }

    // Door bridges overlay: rectangle with X inside (one per bridge)
    if (showBridges && bridgesData && bridgesData.length > 0) {
      const bridgeColor = '#B22222';
      const bridgeFill = 'rgba(178, 34, 34, 0.25)';
      bridgesData.forEach((doorEntry) => {
        const bridges = doorEntry.bridges || [];
        bridges.forEach((item) => {
          const r = item.bridgeRectangle;
          if (!r || typeof r.minX !== 'number' || typeof r.minY !== 'number' || typeof r.maxX !== 'number' || typeof r.maxY !== 'number') return;
          const box: BBox = { minX: r.minX, minY: r.minY, maxX: r.maxX, maxY: r.maxY };
          if (!aabbIntersects(box, viewportBBox)) return;
          const corners = [
            worldToScreen(r.minX, r.minY, transform),
            worldToScreen(r.maxX, r.minY, transform),
            worldToScreen(r.maxX, r.maxY, transform),
            worldToScreen(r.minX, r.maxY, transform),
          ];
          ctx.beginPath();
          ctx.moveTo(corners[0].x, corners[0].y);
          for (let i = 1; i < corners.length; i++) ctx.lineTo(corners[i].x, corners[i].y);
          ctx.closePath();
          ctx.fillStyle = bridgeFill;
          ctx.fill();
          ctx.strokeStyle = bridgeColor;
          ctx.lineWidth = 2;
          ctx.stroke();
          // X inside: diagonals
          ctx.beginPath();
          ctx.moveTo(corners[0].x, corners[0].y);
          ctx.lineTo(corners[2].x, corners[2].y);
          ctx.moveTo(corners[1].x, corners[1].y);
          ctx.lineTo(corners[3].x, corners[3].y);
          ctx.strokeStyle = bridgeColor;
          ctx.lineWidth = 2;
          ctx.stroke();
        });
      });
    }

  }, [normalizedData, transform, hoveredLine, selectedLine, layerVisibility, showPairs, pairsData, hoveredPair, showLogicBPairs, logicBPairsData, showLogicCPairs, logicCPairsData, hoveredLogicCPairIdx, showLogicDPairs, logicDPairsData, hoveredLogicDPairIdx, showLogicEPairs, logicEPairsData, hoveredLogicEPairIdx, showWindowDoorBlocks, windowDoorBlocks, showBridges, bridgesData]);

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

  const updateLogicCPairsHover = useCallback(
    (clientX: number, clientY: number) => {
      if (!showLogicCPairs || !logicCPairsData?.length || !canvasRef.current || isPanning) {
        setHoveredLogicCPairIdx(null);
        return;
      }

      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssX = (clientX - rect.left) / dpr;
      const cssY = (clientY - rect.top) / dpr;
      const worldPoint = screenToWorld(cssX, cssY, transform);

      let found: number | null = null;
      for (let i = 0; i < logicCPairsData.length; i++) {
        const pair = logicCPairsData[i];
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) continue;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        if (pointInPolygon(worldPoint.x, worldPoint.y, corners)) {
          found = i;
          break;
        }
      }
      setHoveredLogicCPairIdx(found);
    },
    [showLogicCPairs, logicCPairsData, transform, isPanning]
  );

  const updateLogicDPairsHover = useCallback(
    (clientX: number, clientY: number) => {
      if (!showLogicDPairs || !logicDPairsData?.length || !canvasRef.current || isPanning) {
        setHoveredLogicDPairIdx(null);
        return;
      }

      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssX = (clientX - rect.left) / dpr;
      const cssY = (clientY - rect.top) / dpr;
      const worldPoint = screenToWorld(cssX, cssY, transform);

      let found: number | null = null;
      for (let i = 0; i < logicDPairsData.length; i++) {
        const pair = logicDPairsData[i];
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) continue;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        if (pointInPolygon(worldPoint.x, worldPoint.y, corners)) {
          found = i;
          break;
        }
      }
      setHoveredLogicDPairIdx(found);
    },
    [showLogicDPairs, logicDPairsData, transform, isPanning]
  );

  const updateLogicEPairsHover = useCallback(
    (clientX: number, clientY: number) => {
      if (!showLogicEPairs || !logicEPairsData?.length || !canvasRef.current || isPanning) {
        setHoveredLogicEPairIdx(null);
        return;
      }

      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssX = (clientX - rect.left) / dpr;
      const cssY = (clientY - rect.top) / dpr;
      const worldPoint = screenToWorld(cssX, cssY, transform);

      let found: number | null = null;
      for (let i = 0; i < logicEPairsData.length; i++) {
        const pair = logicEPairsData[i];
        const a = pair.trimmedSegmentA;
        const b = pair.trimmedSegmentB;
        if (!a?.p1 || !a?.p2 || !b?.p1 || !b?.p2) continue;
        const corners = orderQuadCorners([
          { x: a.p1.X, y: a.p1.Y },
          { x: a.p2.X, y: a.p2.Y },
          { x: b.p1.X, y: b.p1.Y },
          { x: b.p2.X, y: b.p2.Y },
        ]);
        if (pointInPolygon(worldPoint.x, worldPoint.y, corners)) {
          found = i;
          break;
        }
      }
      setHoveredLogicEPairIdx(found);
    },
    [showLogicEPairs, logicEPairsData, transform, isPanning]
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
        if (showLogicCPairs && logicCPairsData?.length) {
          updateLogicCPairsHover(e.clientX, e.clientY);
        } else {
          setHoveredLogicCPairIdx(null);
        }
        if (showLogicDPairs && logicDPairsData?.length) {
          updateLogicDPairsHover(e.clientX, e.clientY);
        } else {
          setHoveredLogicDPairIdx(null);
        }
        if (showLogicEPairs && logicEPairsData?.length) {
          updateLogicEPairsHover(e.clientX, e.clientY);
        }
 else {
          setHoveredLogicEPairIdx(null);
        }
      }
    },
    [isPanning, panStart, updateHover, showPairs, updatePairsHover, showLogicCPairs, logicCPairsData, updateLogicCPairsHover, showLogicDPairs, logicDPairsData, updateLogicDPairsHover, showLogicEPairs, logicEPairsData, updateLogicEPairsHover]
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
    setHoveredLogicCPairIdx(null);
    setHoveredLogicDPairIdx(null);
    setHoveredLogicEPairIdx(null);
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
          onClick={() => setShowWindowDoorBlocks(!showWindowDoorBlocks)}
          disabled={windowDoorBlocksLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showWindowDoorBlocks ? '#2E8B57' : '#fff',
            color: showWindowDoorBlocks ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: windowDoorBlocksLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: windowDoorBlocksLoading ? 0.6 : 1,
          }}
          title="Show/Hide collected windows"
        >
          {windowDoorBlocksLoading ? 'Loading...' : showWindowDoorBlocks ? 'Hide Windows & Doors' : 'Show Windows & Doors'}
        </button>

        <button
          onClick={() => setShowLogicBPairs(!showLogicBPairs)}
          disabled={logicBPairsLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showLogicBPairs ? '#008800' : '#fff',
            color: showLogicBPairs ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: logicBPairsLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: logicBPairsLoading ? 0.6 : 1,
          }}
          title="Show/Hide LOGIC B wall pair overlay (green)"
        >
          {logicBPairsLoading ? 'Loading...' : showLogicBPairs ? 'Hide LOGIC B' : 'Show LOGIC B'}
        </button>

        <button
          onClick={() => setShowLogicCPairs(!showLogicCPairs)}
          disabled={logicCPairsLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showLogicCPairs ? '#4B0082' : '#fff',
            color: showLogicCPairs ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: logicCPairsLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: logicCPairsLoading ? 0.6 : 1,
          }}
          title="Show/Hide LOGIC C wall pair overlay (purple, no intervening lines)"
        >
          {logicCPairsLoading ? 'Loading...' : showLogicCPairs ? 'Hide LOGIC C' : 'Show LOGIC C'}
        </button>

        <button
          onClick={() => setShowLogicDPairs(!showLogicDPairs)}
          disabled={logicDPairsLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showLogicDPairs ? '#CC6600' : '#fff',
            color: showLogicDPairs ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: logicDPairsLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: logicDPairsLoading ? 0.6 : 1,
          }}
          title="Show/Hide LOGIC D wall pair overlay (orange, containment-pruned outer rectangles)"
        >
          {logicDPairsLoading ? 'Loading...' : showLogicDPairs ? 'Hide LOGIC D' : 'Show LOGIC D'}
        </button>

        <button
          onClick={() => setShowLogicEPairs(!showLogicEPairs)}
          disabled={logicEPairsLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showLogicEPairs ? '#008080' : '#fff',
            color: showLogicEPairs ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: logicEPairsLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: logicEPairsLoading ? 0.6 : 1,
          }}
          title="Show/Hide LOGIC E wall pair overlay (teal, band-merged rectangles)"
        >
          {logicEPairsLoading ? 'Loading...' : showLogicEPairs ? 'Hide LOGIC E' : 'Show LOGIC E'}
        </button>

        <button
          onClick={() => setShowBridges(!showBridges)}
          disabled={bridgesLoading}
          style={{
            padding: '8px 16px',
            backgroundColor: showBridges ? '#B22222' : '#fff',
            color: showBridges ? '#fff' : '#000',
            border: '1px solid #ccc',
            borderRadius: '4px',
            cursor: bridgesLoading ? 'wait' : 'pointer',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            opacity: bridgesLoading ? 0.6 : 1,
          }}
          title="Show/Hide door bridge overlay (rectangle with X)"
        >
          {bridgesLoading ? 'Loading...' : showBridges ? 'Hide Bridges' : 'Show Bridges'}
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

        {logicBPairsError && (
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
            {logicBPairsError}
          </div>
        )}

        {logicCPairsError && (
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
            {logicCPairsError}
          </div>
        )}

        {logicDPairsError && (
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
            {logicDPairsError}
          </div>
        )}

        {logicEPairsError && (
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
            {logicEPairsError}
          </div>
        )}

        {bridgesError && (
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
            {bridgesError}
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
