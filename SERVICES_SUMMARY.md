# 📋 סיכום מדויק של כל השירותים והלוגיקה

## 🏗️ ארכיטקטורה כללית

המערכת מורכבת מ-4 שירותים עיקריים:
1. **Backend API** (FastAPI) - שירות ה-API הראשי
2. **Worker** (RQ Worker) - עיבוד אסינכרוני
3. **Frontend** (React) - ממשק המשתמש
4. **Database Services** (PostgreSQL + Redis) - אחסון ותור עבודות

---

## 🔵 BACKEND API SERVICE (`/backend`)

### תפקידים עיקריים:
1. **קבלת קבצים והעלאה**
   - מקבל קבצי JSON מ-export של AutoCAD
   - מאמת את הפורמט
   - שומר את הקובץ בדיסק
   - מחשב hash של הקובץ למניעת כפילויות

2. **בניית Layer Inventory**
   - מפרסר את ה-JSON באמצעות `DrawingAdapter`
   - בונה רשימת שכבות (layers) עם ספירת entities
   - שומר ב-PostgreSQL: טבלת `drawings` ו-`layers`

3. **ניהול Jobs**
   - יוצר עבודות (jobs) חדשות
   - מנהל את מצב העבודה (pending → running → completed/failed)
   - שולח עבודות ל-Redis Queue לעיבוד אסינכרוני

4. **חשיפת API Endpoints**
   - `POST /drawings` - העלאת קובץ
   - `GET /drawings/{id}/layers` - קבלת רשימת שכבות
   - `POST /jobs` - יצירת עבודה חדשה
   - `GET /jobs/{id}` - מצב עבודה
   - `GET /jobs/{id}/canvas-data` - נתוני קנבס
   - `GET /jobs/{id}/wall-candidate-pairs` - זוגות מועמדי קירות

### מה הוא **לא** עושה:
- ❌ לא מעבד גיאומטריה
- ❌ לא מחפש זוגות קווים
- ❌ לא מחשב מועמדי קירות
- ✅ רק מנהל, מאמת, ושולח לעיבוד

---

## ⚙️ WORKER SERVICE (`/worker`)

### תפקידים עיקריים:
ה-Worker הוא הלב של המערכת - הוא מבצע את כל העיבוד הגיאומטרי!

### תהליך העבודה:
1. **קבלת עבודה מ-Redis Queue**
   - Worker מחכה לעבודות חדשות ב-Redis
   - כשיש עבודה חדשה, הוא קורא ל-`process_job(job_id)`

2. **הרצת Pipeline של 5 שלבים:**
   ```
   EXTRACT → NORMALIZE → CLEAN_DEDUP → PARALLEL_NAIVE → WALL_CANDIDATES_PLACEHOLDER
   ```

### שלב 1: EXTRACT
**קובץ:** `extract_processor.py`
- **תפקיד:** חילוץ entities מה-JSON לפי שכבות שנבחרו
- **מה הוא עושה:**
  - קורא את ה-JSON של הקובץ שהועלה
  - מסנן רק את השכבות שנבחרו על ידי המשתמש
  - מחלץ entities לפי סוג: LINE, POLYLINE, BLOCK
  - יוצר רשימה של כל ה-entities עם metadata בסיסי

### שלב 2: NORMALIZE
**קובץ:** `normalize_processor.py`
- **תפקיד:** נרמול קואורדינטות ואימות נתונים
- **מה הוא עושה:**
  - מנרמל קואורדינטות עם epsilon של `1e-6` (0.000001)
  - מוודא שכל נקודה תקינה
  - ממיר POLYLINE ל-LINE segments
  - יוצר `normalized_data` לכל entity

### שלב 3: CLEAN_DEDUP
**קובץ:** `clean_dedup_processor.py`
- **תפקיד:** ניקוי כפילויות באמצעות hash דטרמיניסטי
- **מה הוא עושה:**
  - מחשב hash דטרמיניסטי לכל entity: `hash(layer + type + geometry)`
  - מסיר entities זהים (כפילויות)
  - יוצר `canvas_data.json` artifact עם:
    - כל הקווים המנורמלים
    - bounding box של השרטוט
    - צבעים אקראיים לכל שכבה
    - סטטיסטיקות

### שלב 4: PARALLEL_NAIVE
**קובץ:** `parallel_naive_processor.py`
- **תפקיד:** הכנה לעיבוד מקבילי וניתוח בסיסי
- **מה הוא עושה:**
  - מקבץ entities לפי שכבות
  - מעבד שכבות במקביל (ThreadPoolExecutor)
  - מחשב bounding box לכל שכבה
  - יוצר `parallel_ready_entities` - רשימה שטוחה של כל ה-entities

### שלב 5: WALL_CANDIDATES_PLACEHOLDER ⭐ **החשוב ביותר!**
**קובץ:** `wall_candidates_processor.py`
- **תפקיד:** זיהוי זוגות קווים שהם מועמדים לקירות

#### הלוגיקה המלאה של מציאת זוגות:

**1. סינון ל-LINE entities בלבד:**
```python
line_entities = [entity for entity in parallel_ready_entities 
                 if entity['entity_type'] == 'LINE']
```

**2. בדיקת כל הזוגות האפשריים:**
```python
for i, line1 in enumerate(line_entities):
    for j, line2 in enumerate(line_entities[i+1:], i+1):
        # בדיקה אם זה זוג מועמד
```

**3. שלושה תנאים חובה (כולם חייבים להתקיים):**

##### תנאי 1: קווים מקבילים (`_are_parallel`)
- מחשב וקטור כיוון לכל קו: `(dx, dy)`
- מנרמל את הווקטורים
- מחשב dot product (מכפלה סקלרית)
- בודק אם הזווית בין הקווים ≤ 5 מעלות (`ANGULAR_TOLERANCE = 5.0`)
- **נוסחה:** `dot_product >= cos(5°)`

##### תנאי 2: מרחק ניצב בטווח (`_check_distance_constraint`)
- מחשב מרחק ניצב בין שני קווים מקבילים
- **טווח מותר:** 20mm עד 450mm
  - `MIN_DISTANCE = 20.0` (2 ס"מ)
  - `MAX_DISTANCE = 450.0` (45 ס"מ)
- **איך מחשבים:**
  1. מחשב וקטור כיוון של קו 1
  2. מחשב וקטור ניצב: `perp = (-dy, dx)`
  3. מחשב השלכה של וקטור בין נקודות על הווקטור הניצב
  4. המרחק = הערך המוחלט של ההשלכה

##### תנאי 3: חפיפה מינימלית (`_check_overlap_requirement`)
- מחשב אחוז חפיפה בין הקווים
- **דרישה מינימלית:** 60% חפיפה (`MIN_OVERLAP_PERCENTAGE = 60.0`)
- **איך מחשבים:**
  1. משליך את שני הקווים על הציר הראשי (X או Y)
  2. מוצא את הקטע החופף
  3. מחשב: `(overlap_length / shorter_line_length) * 100`

**4. יצירת זוג מועמד (`_create_candidate_pair`):**
אם כל שלושת התנאים מתקיימים, יוצר אובייקט זוג עם:
- `pair_id` - UUID ייחודי
- `line1` ו-`line2` - פרטי שני הקווים
- `geometric_properties`:
  - `perpendicular_distance` - המרחק הניצב
  - `overlap_percentage` - אחוז החפיפה
  - `angle_difference` - הבדל זווית (במעלות)
  - `average_length` - אורך ממוצע
  - `bounding_rectangle` - מלבן תוחם: `{minX, maxX, minY, maxY}`

**5. שמירת תוצאות:**
- כל הזוגות נשמרים כ-artifact: `wall_candidates_placeholder_results.json`
- כולל סטטיסטיקות: כמה זוגות נמצאו, מרחק ממוצע, חפיפה ממוצעת

### מה ה-Worker שומר:
- **Artifacts** - תוצאות ביניים וסופיות ב-PostgreSQL
- **Job Steps** - מצב כל שלב (pending/running/completed)
- **Metrics** - מדדי ביצועים (זמן, כמות entities, וכו')
- **Logs** - לוגים מובנים לכל פעולה

---

## 🎨 FRONTEND SERVICE (`/frontend`)

### תפקידים עיקריים:

1. **העלאת קבצים**
   - ממשק להעלאת JSON
   - הצגת התקדמות
   - טיפול בשגיאות

2. **ניהול שכבות**
   - הצגת רשימת שכבות
   - בחירת שכבות לעיבוד
   - הצגת סטטיסטיקות (כמה entities בכל שכבה)

3. **מעקב אחר עבודות**
   - Dashboard עם מצב העבודה
   - הצגת שלבי Pipeline
   - הצגת לוגים ו-artifacts

4. **ויזואליזציה** ⭐
   - **קומפוננט:** `WallVisualization.js`
   - **מה הוא עושה:**
     - טוען `canvas_data` מה-artifact
     - טוען `wall_candidate_pairs` מה-artifact
     - מצייר על HTML5 Canvas:
       - כל הקווים המזוהים (בצבעי שכבות)
       - ריבועים צבעוניים סביב כל זוג מועמד קירות
       - לייבלים עם מספר זוג
     - תמיכה ב-zoom, pan, fit-to-view

### מה הוא **לא** עושה:
- ❌ לא מעבד גיאומטריה
- ❌ לא מחפש זוגות
- ❌ רק מציג תוצאות מה-Backend/Worker

---

## 📊 זרימת נתונים מלאה

```
1. משתמש מעלה JSON
   ↓
2. Backend מאמת ושומר
   ↓
3. Backend בונה Layer Inventory
   ↓
4. משתמש בוחר שכבות
   ↓
5. Backend יוצר Job ושולח ל-Redis Queue
   ↓
6. Worker לוקח את ה-Job
   ↓
7. Worker מריץ Pipeline:
   EXTRACT → NORMALIZE → CLEAN_DEDUP → PARALLEL_NAIVE → WALL_CANDIDATES
   ↓
8. Worker שומר Artifacts ב-PostgreSQL
   ↓
9. Frontend שואל את ה-Backend על מצב
   ↓
10. Backend מחזיר נתונים מ-PostgreSQL
   ↓
11. Frontend מציג ויזואליזציה
```

---

## 🔍 סיכום הלוגיקה של מציאת זוגות מועמדי קירות

### איפה זה קורה?
**רק ב-Worker!** בקובץ `wall_candidates_processor.py`

### איך זה עובד?

1. **קלט:** רשימה של כל ה-LINE entities אחרי ניקוי וכפילות

2. **אלגוריתם:**
   ```
   לכל קו line1:
     לכל קו line2 (אחרי line1):
       אם (מקבילים AND מרחק בטווח AND חפיפה מספקת):
         צור זוג מועמד
   ```

3. **תנאים:**
   - ✅ מקבילים (זווית ≤ 5°)
   - ✅ מרחק ניצב: 20-450mm
   - ✅ חפיפה: ≥ 60%

4. **פלט:** רשימת זוגות עם:
   - פרטי שני הקווים
   - תכונות גיאומטריות
   - bounding rectangle

5. **שמירה:** כ-artifact ב-PostgreSQL

### מי משתמש בזה?
- **Frontend** - טוען את הזוגות ומציג אותם על Canvas
- **Backend** - מספק API endpoint לשליפת הזוגות

---

## 🎯 נקודות מפתח

1. **כל העיבוד הגיאומטרי ב-Worker** - Backend רק מנהל
2. **Pipeline דטרמיניסטי** - אותה קלט = אותה פלט
3. **Observability מלא** - כל שלב נשמר כ-artifact
4. **אסינכרוני** - Worker עובד ברקע, Frontend מציג התקדמות
5. **לוגיקה של זוגות רק ב-Worker** - Frontend רק מציג

---

## 📁 מיקום קבצים חשובים

### Worker - לוגיקה של זוגות:
- `worker/worker/pipeline/processors/wall_candidates_processor.py` - הלוגיקה המלאה
- `worker/worker/pipeline/processors/parallel_naive_processor.py` - הכנה לעיבוד
- `worker/worker/job_processor.py` - ניהול עבודות

### Backend - API:
- `backend/app/main.py` - כל ה-endpoints
- `backend/app/services/job_service.py` - ניהול עבודות

### Frontend - ויזואליזציה:
- `frontend/src/components/WallVisualization.js` - ציור על Canvas
- `frontend/src/pages/JobDashboard.js` - Dashboard

---

**סיכום:** כל הלוגיקה של מציאת זוגות מועמדי קירות נמצאת **רק ב-Worker**, ב-`wall_candidates_processor.py`. ה-Backend וה-Frontend רק מנהלים ומציגים את התוצאות.
