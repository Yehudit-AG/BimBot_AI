# LOGIC_F – L-Junctions Stage (Full Plan Including All Changes)

## Overview

Add pipeline stage **LOGIC_F** after LOGIC_E that extends L-shaped wall junctions to close corner gaps. The stage is purely transformational (output length equals input length). The plan includes:

- Correct centerline construction (c1/c2 from boundary endpoints, not midpoints)
- Strict 1:1 transform (deep copy, modify only L-junction participants)
- Endpoint mapping and projection rules (D, E, G)
- Naming **LOGIC_F** throughout (B)
- Constants, processor, pipeline wiring, worker/backend artifact, frontend "Show LOGIC F", and tests (J)

---

## Part 1: Project Structure (Reference)

### Pipeline definition

- **Where:** `worker/worker/pipeline/pipeline_executor.py`
- **Structure:** `PIPELINE_STEPS` = list of `(step_name, ProcessorClass)`. Order: EXTRACT → NORMALIZE → CLEAN_DEDUP → PARALLEL_NAIVE → LOGIC_B → LOGIC_C → LOGIC_D → LOGIC_E → WALL_CANDIDATES_PLACEHOLDER.
- **Key rule:** Result is stored in `pipeline_data[f'{step_name.lower()}_results']`. So step **LOGIC_F** yields `pipeline_data["logic_f_results"]`.

### Stage architecture

- **Base:** `BaseProcessor` with `process(pipeline_data) -> Dict`. LOGIC_F reads `pipeline_data["logic_e_results"]["logic_e_rectangles"]` and returns a dict with `logic_f_rectangles`, `algorithm_config`, `totals`.
- **Artifacts:** `store_final_results` checks `final_results['LOGIC_F']` and creates `artifact_type="logic_f_rectangles"`, `artifact_name="logic_f_rectangles.json"`.

### Backend / Frontend

- Backend: `get_logic_f_rectangles(db, job_id)`; GET `/jobs/{job_id}/logic-f-rectangles` → `{ rectangles, algorithm_config, totals }`.
- Frontend: Same pattern as LOGIC E (getJobLogicFRectangles, state, overlay, button, hover). Renderer uses only `trimmedSegmentA` / `trimmedSegmentB`; extra keys (`was_modified`, etc.) are safe.

---

## Part 2: Naming and Pipeline (B)

- **Step name:** **LOGIC_F**
- **Pipeline key:** `pipeline_data["logic_f_results"]`
- **Insert:** In `pipeline_executor.py`: `("LOGIC_F", LogicFProcessor),` immediately after LOGIC_E.
- **Artifact:** `artifact_type="logic_f_rectangles"`, `artifact_name="logic_f_rectangles.json"`. In `store_final_results` check `final_results['LOGIC_F']`.

---

## Part 3: Logic Requirements (A–G)

### Constants (`wall_candidate_constants.py`)

- `JUNCTION_TOL_MM = 400.0`
- `ANGLE_DOT_TOL = 0.3`
- `ENDPOINT_ATTACH_TOL_MM = 300.0`

### A) Centerline construction (critical)

**Wrong:** Centerline = segment between midpoint(segmentA) and midpoint(segmentB) — runs across thickness and breaks direction, perpendicularity, intersection.

**Correct:**

1. `dA = A.p2 - A.p1`, `dB = B.p2 - B.p1`
2. If `dot(unit(dA), unit(dB)) < 0`, flip B (swap B.p1 ↔ B.p2)
3. `c1 = (A.p1 + B.p1) / 2`, `c2 = (A.p2 + B.p2) / 2`
4. `u = unit(c2 - c1)`, `n = perp(u)` (e.g. `(-u.y, u.x)` normalized)
5. `w = distance_point_to_infinite_line(A.p1, line_through(B.p1, B.p2))` (or symmetric average)

### F) L-junction detection

- Perpendicularity: `abs(dot(u1, u2)) < ANGLE_DOT_TOL`
- Endpoint proximity: `min(dist(ci_k, cj_m)) < JUNCTION_TOL_MM` over the four endpoint pairs
- Extend only the endpoint closer to junction center C; if `min(dist(c1,C), dist(c2,C)) > ENDPOINT_ATTACH_TOL_MM` for that wall, do not modify that wall for this pair

### E) Junction center and extension target

- Always extend to **projection** of C onto the wall’s centerline: `c_end_new = project_point_onto_infinite_line(C, centerline)`. Never snap boundary endpoints directly to C.
- Fallback: C = midpoint of closest endpoint pair between the two centerlines; then project C onto each wall’s centerline separately.

### D) Extension rules – endpoint mapping

- After aligning B: **c1 end** ↔ A.p1, B.p1; **c2 end** ↔ A.p2, B.p2.
- Consistent +n/-n: if `dot((A.p1 - c1), n) > 0` then A is +n; else swap so A is +n, B is -n.
- `A_end_new = c_end_new + n * (w/2)`, `B_end_new = c_end_new - n * (w/2)`.
- Extending **c1** ⇒ set A.p1, B.p1. Extending **c2** ⇒ set A.p2, B.p2.

### G) Multi-junction (no drift)

- Treat c1 and c2 separately. For each endpoint, assign **at most one** junction: the **nearest** C within `ENDPOINT_ATTACH_TOL_MM`; apply extension once per endpoint.

### C) Non-filtering contract (1:1)

- Start with **deep copy** of input list. Modify **only** indices that participate in an L-junction. Others stay geometry-unchanged (optional debug keys allowed).
- Invariants: `len(output) == len(input)`, same order, one-to-one.

### H) Performance (recommended)

- Spatial index over centerline endpoints; only evaluate pairs within `JUNCTION_TOL_MM`.

### Debug metadata

- Optional on output rectangles: `was_modified`, `junction_type: "L"`, `junction_center: { X, Y }`.

---

## Part 4: Frontend

- API: `getJobLogicFRectangles(jobId)` → GET `/jobs/${jobId}/logic-f-rectangles`.
- CadCanvasViewer: state (showLogicFPairs, logicFPairsData, loading, error, hoveredLogicFPairIdx), reset on jobId, lazy fetch, overlay (distinct color), updateLogicFPairsHover, button "Show LOGIC F" / "Hide LOGIC F", error div.

---

## Part 5: Tests (J)

- **File:** `worker/tests/test_logic_f_l_junctions_processor.py`
- **Case 1 – L with gap:** Two rectangles (horizontal + vertical) with small corner gap. Assert: (1) output length = input length; (2) modified walls: segmentA–segmentB distance ~ thickness; (3) centerline direction along wall run (not across thickness); (4) at least two `was_modified is True`; (5) junction center within ~50 mm of expected corner.
- **Case 2 – No L:** Parallel or far rectangles. Assert: output length = input length; all `was_modified is False` or absent; geometry unchanged.
- Tests must catch wrong centerline (midpoint-to-midpoint).

---

## Part 6: Deliverables

**Modified:**

- `worker/worker/pipeline/processors/wall_candidate_constants.py` – add JUNCTION_TOL_MM, ANGLE_DOT_TOL, ENDPOINT_ATTACH_TOL_MM
- `worker/worker/pipeline/pipeline_executor.py` – import LogicFProcessor; insert `("LOGIC_F", LogicFProcessor)` after LOGIC_E
- `worker/worker/services/artifact_service.py` – in `store_final_results`, block for `final_results['LOGIC_F']` → `logic_f_rectangles.json`
- `backend/app/services/artifact_service.py` – add `get_logic_f_rectangles`
- `backend/app/main.py` – add GET `/jobs/{job_id}/logic-f-rectangles`
- `frontend/src/services/api.js` – add `getJobLogicFRectangles`
- `frontend/src/components/CadCanvasViewer.tsx` – LOGIC F state, fetch, overlay, hover, button, error

**New:**

- `worker/worker/pipeline/processors/logic_f_l_junctions_processor.py` – LogicFProcessor + helpers (centerline per A, L-detection, junction center, extension per D/E/G)
- `worker/tests/test_logic_f_l_junctions_processor.py` – two test cases (J)

**Pipeline:** LOGIC_F runs after LOGIC_E; reads `logic_e_results["logic_e_rectangles"]`; writes `logic_f_results["logic_f_rectangles"]`.

**Viewing:** Job view → "Show LOGIC F" → overlay from `/jobs/{jobId}/logic-f-rectangles`.
