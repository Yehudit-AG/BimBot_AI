# סיכום פרויקט BimBot-AI וייצוא ל-BIMJSON

## 1. תיאור הפרויקט

**BimBot-AI** הוא מערכת לעיבוד ייצואי AutoCAD (DWG) בפורמט JSON, עם ארכיטקטורה של 4 שירותים (Backend, Worker, Frontend, PostgreSQL + Redis). המערכת:

- **מטרה כללית:** בסיס לאוטומציה של Revit בתחום אינסטלציה, חדרים ואביזרים סניטריים. כרגע המיקוד הוא ב-**זיהוי קירות, חלונות, דלתות ומועמדי קירות** מתוך שרטוטי CAD, כהכנה לשלב התכנון (כולל תכנון צנרת, חדרים ואביזרים).

- **זרימת עבודה נוכחית:**
  1. העלאת קובץ JSON (export מ-AutoCAD/DWG).
  2. בניית **מלאי שכבות** (layers) עם ספירת entities (קווים, polylines, blocks).
  3. בחירת שכבות לעיבוד.
  4. יצירת Job ועיבוד **Pipeline** ב-Worker.
  5. שמירת תוצאות כ-**Artifacts** (קבצי JSON) ב-PostgreSQL + דיסק.
  6. הצגת תוצאות ב-Frontend (Canvas, זוגות קירות, מלבני קירות, דלתות וכו').

- **Pipeline (סדר השלבים):**
  ```
  EXTRACT → NORMALIZE → CLEAN_DEDUP → PARALLEL_NAIVE
  → LOGIC_B → LOGIC_C → LOGIC_D → LOGIC_E
  → DOOR_RECTANGLE_ASSIGNMENT → DOOR_BRIDGE → WALL_CANDIDATES_PLACEHOLDER
  ```

---

## 2. איפה המידע והנתונים נמצאים היום

### 2.1 מסד נתונים (PostgreSQL)

| טבלה | תוכן |
|------|------|
| **drawings** | מטא-דאטה של קבצים: filename, file_hash, file_size, status, metadata |
| **layers** | מלאי שכבות: layer_name, line_count, polyline_count, block_count, has_lines/has_polylines/has_blocks |
| **layer_selections** | אילו שכבות נבחרו לעיבוד (is_selected) |
| **drawing_window_door_blocks** | blocks של חלונות/דלתות לפי drawing (JSONB) |
| **jobs** | עבודות: drawing_id, job_type, status, selected_layers (JSONB), error_message, metadata |
| **job_steps** | שלבי Pipeline: step_name, status, input_data, output_data, metrics |
| **job_logs** | לוגים עם correlation ID, level, message, context |
| **artifacts** | הפניות לקבצי תוצאות: artifact_type, artifact_name, file_path, metadata |
| **entities** | (אם בשימוש) entities מנורמלים עם entity_hash, geometry_data, bounding_box |

### 2.2 Artifacts (קבצי JSON לפי Job)

כל Job יוצר תיקייה `artifacts/<job_id>/` עם קבצים מהסוגים הבאים:

| artifact_type | artifact_name | תוכן |
|---------------|---------------|------|
| **canvas_data** | canvas_data.json | drawing_bounds, layers (קווים עם start/end, צבעים), statistics – לבדיקה ויזואלית |
| **logic_b_pairs** | logic_b_pairs.json | זוגות משלב LOGIC_B (pairs, algorithm_config, totals) |
| **logic_c_pairs** | logic_c_pairs.json | זוגות משלב LOGIC_C |
| **logic_d_rectangles** | logic_d_rectangles.json | מלבני קירות אחרי LOGIC_D (rectangles, algorithm_config, totals) |
| **logic_e_rectangles** | logic_e_rectangles.json | מלבני קירות אחרי מיזוג סמוכים (LOGIC_E) |
| **door_rectangle_assignments** | door_rectangle_assignments.json | שיוך דלתות למלבני קירות (door_assignments, config, totals) |
| **door_bridges** | door_bridges.json | גשרי דלתות (door_bridges, config, totals) |
| **wall_candidate_pairs** | wall_candidate_pairs.json | זוגות מועמדי קירות סופיים (pairs, detection_stats, algorithm_config, totals) |

בנוסף נשמרים קבצי step_results ו-step_metrics לכל שלב ב-Pipeline (לפי step_name).

### 2.3 קובץ המקור

- קובץ ה-JSON שהועלה (DWG export) נשמר בדיסק (לפי הגדרות Backend) ומקושר ל-`drawings.filename` / path.
- הוא מכיל את כל ה-entities הגולמיים לפי שכבות – מקור הגיאומטריה לפני כל העיבוד.

---

## 3. מה צריך לייצא ל-BIMJSON לשלב התכנון

**BIMJSON** אמור לאגד את כל המידע הרלוונטי לתכנון (חדרים, קירות, דלתות, חלונות, ואחר כך צנרת ואביזרים) בפורמט אחד, קריא וסטנדרטי.

### 3.1 נתונים להכללה ב-BIMJSON (המלצה)

1. **מטא-דאטה של הפרויקט/שרטוט**
   - drawing_id, filename, upload timestamp, גרסה/מזהה.

2. **שכבות**
   - רשימת layers, ספירות (lines, polylines, blocks), אילו נבחרו לעיבוד.

3. **גיאומטריה בסיסית**
   - מתוך **canvas_data** או מתוך ה-**entities** המנורמלים: קווים לפי שכבה (start/end, אופציונלי length), יחידות (mm).
   - **drawing_bounds** (bounding box של השרטוט).

4. **קירות (Walls)**
   - מתוך **logic_e_rectangles** (או logic_d אם רוצים גרסה לפני מיזוג): מלבני קירות עם segmentA, segmentB, centerline, thickness וכו'.
   - אופציונלי: **wall_candidate_pairs** כמקור לזוגות קווים שזוהו כקירות.

5. **דלתות (Doors)**
   - מתוך **door_rectangle_assignments** ו-**door_bridges**: שיוך דלת למלבן קיר, מיקום, גשר.
   - מתוך **drawing_window_door_blocks**: blocks של דלתות/חלונות מהשרטוט המקורי.

6. **חלונות (Windows)**
   - מתוך **drawing_window_door_blocks** (הבחנה בין block של דלת לחלון לפי שם/מטא-דאטה אם קיים).

7. **חדרים (Rooms)**
   - כרגע **לא** מיוצרים במערכת; נדרש שלב עתידי (זיהוי/הגדרה אינטראקטיבית של חדרים). ב-BIMJSON אפשר להשאיר מבנה ריק או placeholder ל-rooms.

8. **אביזרים סניטריים וצנרת**
   - כרגע **לא** מטופלים ב-Pipeline; שמורים מקום בתכנון לעתיד. ב-BIMJSON – מבנה ריק או placeholder.

9. **הגדרות אלגוריתם (אופציונלי)**
   - algorithm_config / totals מ-artifacts הרלוונטיים – לצורך מעקב וולידציה.

### 3.2 מבנה מוצע ל-BIMJSON (תבנית ראשית)

```json
{
  "version": "1.0",
  "source": "BimBot-AI",
  "exported_at": "ISO8601",
  "drawing": {
    "id": "uuid",
    "filename": "...",
    "bounds": { "minX", "minY", "maxX", "maxY" },
    "units": "mm"
  },
  "layers": [
    { "name": "...", "line_count": 0, "polyline_count": 0, "block_count": 0, "selected": true }
  ],
  "geometry": {
    "lines_by_layer": { "layer_name": [ { "id", "start": {x,y,z}, "end": {x,y,z} } ] },
    "bounds": { "minX", "minY", "maxX", "maxY" }
  },
  "walls": [
    { "id", "segmentA", "segmentB", "centerline", "thickness_mm", "metadata" }
  ],
  "doors": [
    { "id", "wall_id", "block_data", "assignment", "bridge", "metadata" }
  ],
  "windows": [
    { "id", "block_data", "metadata" }
  ],
  "rooms": [],
  "sanitary_fixtures": [],
  "piping": []
}
```

(השדות המדויקים יותאמו לפי מה שהמערכת מחזירה היום ב-artifacts ולדרישות התכנון.)

---

## 4. צעדים מעשיים להתקדם לייצוא BIMJSON

1. **הגדרת סכמה (schema)**  
   - מסמך או קובץ JSON Schema שמגדיר את מבנה BIMJSON (שדות חובה, טיפוסים, יחידות).

2. **שירות ייצוא ב-Backend**  
   - endpoint חדש, למשל: `GET /jobs/{job_id}/export/bimjson` או `GET /drawings/{drawing_id}/bimjson?job_id=...`  
   - הלוגיקה: טעינת ה-job, טעינת כל ה-artifacts הרלוונטיים (canvas_data, logic_d/logic_e, door_assignments, door_bridges, window_door_blocks), מיפוי לשדות BIMJSON, החזרת JSON או קובץ.

3. **איסוף נתונים מ-artifacts**  
   - קריאה מ-artifacts לפי `artifact_type` (כמו בטבלה למעלה) ובניית המבנה המאוחד.

4. **מטא-דאטה ו-versions**  
   - הוספת version, source, exported_at ו-drawing id/filename לכל export.

5. **ממשק משתמש (אופציונלי)**  
   - כפתור "ייצא ל-BIMJSON" ב-Job Dashboard שמוריד את הקובץ או מציג לינק להורדה.

---

## 5. סיכום קצר

| נושא | סטטוס |
|------|--------|
| תיאור הפרויקט | מערכת עיבוד DWG→JSON, Pipeline לזיהוי קירות/דלתות/חלונות, הכנה לתכנון אינסטלציה וחדרים |
| איפה הנתונים | PostgreSQL (drawings, layers, jobs, artifacts, …) + קבצי artifacts ב-`artifacts/<job_id>/` |
| BIMJSON כרגע | לא מיושם – אין עדיין ייצוא ל-BIMJSON |
| מה לייצא | מטא-דאטה, שכבות, גיאומטריה (קווים/bounds), קירות, דלתות, חלונות; placeholders לחדרים, אביזרים וצנרת |
| צעד הבא | להגדיר סכמת BIMJSON, ליישם endpoint ייצוא שבונה קובץ אחד מכל ה-artifacts של Job |

אם תרצי, אפשר בשלב הבא: (א) לנסח קובץ JSON Schema מלא ל-BIMJSON, או (ב) לפרט את ה-endpoint וה-flow של ייצוא ה-BIMJSON ב-Backend (כולל רשימת artifact_types לקריאה).
