# סיכום סשן עבודה — 2026-09-07 (XAI/RAI: IF vs AE + Llama מקומי)

מסמך זה מסכם סשן עבודה שלם עם Claude Code על הפרויקט, כדי לאפשר המשך עבודה חלק ממחשב אחר.
נכתב בעברית לבקשת המשתמש. ה-commit האחרון בזמן כתיבת המסמך: `0b49af4`.

## 1. מה היה הבקשה המקורית

המטרה: להשוות בין תוצאות XAI ו-RAI כשהתראה (alert) מתרחשת בגלל Isolation Forest (IF) או
Autoencoder (AE), על דאטהסט NSL-KDD. שלושה דברים התבקשו במפורש:

1. **לשמור על הלוגיקה הקיימת של XAI/RAI ללא שינוי** (חילוץ SHAP top-3 ל-IF, שגיאת שחזור
   top-3 ל-AE, מדיניות ה-RAI עם הסף של FPR>10%/fairness_gap>10%).
2. **להוסיף features שמגיעים מהמודלים עצמם (IF ו-AE)** — הוחלט (לאחר שאלת הבהרה) על:
   צירוף ה-score העצמי של **שני** המודלים (IF anomaly_score + AE reconstruction_error)
   לתוך **שני** ה-payloads (גם payload של IF וגם payload של AE), כך שאפשר להשוות ישירות
   האם שני המודלים מסכימים על אותו אירוע.
3. **להזין את התוצאה למודל Llama מקומי** שכבר מותקן במחשב (דרך Ollama) ולקבל תשובה אמיתית
   מה-LLM, במקום רק להדפיס את הפרומפט כמו שהקוד עשה קודם.

## 2. שינויי קוד שבוצעו

כל הנתיבים כאן הם **אחרי** שינוי המבנה (סעיף 4) — כלומר תחת `Project/` ולא ישירות תחת
שורש הריפו.

- **`Project/research/xai_rai_comparison/enriched_payload.py`**
  נוסף שדה חדש `cross_model_signal` לתוך שני ה-payloads (`if_payload`, `ae_payload`):
  ```python
  cross_model_signal = {
      "isolation_forest_anomaly_score": if_score,
      "isolation_forest_predicted_class": if_predicted_class,
      "autoencoder_reconstruction_error": ae_score,
      "autoencoder_predicted_class": ae_predicted_class,
  }
  ```
  זה מאפשר להשוות בין שני המודלים על אותו אירוע ישירות מתוך ה-payload. **לא נגעתי**
  בפונקציות `_top3_if` / `_top3_ae` (הלוגיקה של XAI נשארה זהה).

- **`Project/research/xai_rai_comparison/llm_orchestrator.py`**
  `build_llm_prompt()` מדפיס עכשיו סקשן חדש `--- CROSS-MODEL SIGNAL ---` עם שני
  ה-scores, ונוסף task #4 שמבקש מה-LLM לציין אם המודל השני מסכים/לא מסכים ומה המשמעות
  לביטחון בהחלטה. **הלוגיקה של `rai_policy_evaluator()` (הסף להחלטת containment)
  נשארה זהה לגמרי**, כמו שהתבקש.

- **`Project/research/xai_rai_comparison/llm_client.py` (קובץ חדש)**
  קליינט מינימלי ל-Ollama, עצמאי (לא תלוי ב-`morpheus_lite.inference`, כדי לשמר את
  ההפרדה הקיימת של סוויטת המחקר מהצינור החי של Kafka). ברירות מחדל דרך env vars:
  `MORPHEUS_XAI_RAI_LLM_MODEL` (ברירת מחדל `llama3.1:8b`),
  `MORPHEUS_XAI_RAI_OLLAMA_URL` (ברירת מחדל `http://localhost:11434/api/generate`).

- **`Project/research/xai_rai_comparison/run_scenarios.py`** (נכתב מחדש)
  עכשיו קורא בפועל ל-Llama המקומי (במקום רק להדפיס פרומפט) עבור כל אחד מ-4 התרחישים
  (`both_alert`, `if_only`, `ae_only`, `both_normal`) × 2 המודלים (IF, AE) = 8 קריאות
  ל-LLM בסך הכול. שומר את כל התוצאה (פרומפטים + תשובות) לקובץ JSON תחת
  `exports/xai_rai_comparison/<timestamp>/scenario_comparison.json` (הקובץ הזה
  **מגיטיגנור** — הוא נוצר מחדש בכל הרצה). דגלי CLI: `--no-llm` (רק הדפסת פרומפטים,
  בלי קריאה ל-LLM), `--llm-model`, `--ollama-url`.

- **`Project/research/xai_rai_comparison/README.md`** ו-**`Project/README.md`**
  עודכנו: תוקן מיקום קבצי הדאטהסט (הסקריפטים בפועל דורשים `data/` ולא
  `data/datasets/nsl_kdd/` כמו שהתיעוד הישן אמר), ונוספה סקשן הרצה מלאה ל-Phase 1-4
  כולל הצעד של Ollama.

הרצה מלאה בוצעה בהצלחה מקצה לקצה עם `llama3.1:8b` (4 תרחישים × 2 מודלים, כולל תשובות
LLM אמיתיות שמזהות נכון הסכמה/אי-הסכמה בין המודלים). התוצאה נשמרה (ולא הועלתה לגיט,
בכוונה) ב-`exports/xai_rai_comparison/20260907-182821/scenario_comparison.json`.

## 3. תקלת סביבה שקרתה ותוקנה — חשוב לזכור!

בזמן ניסיון להתקין `shap` (חסר בשביל SHAP TreeExplainer), הרצתי בטעות
`pip install shap` ישירות על ה-Python הגלובלי של Anaconda (`C:\anaconda3\python.exe`).
זה שדרג את numpy ל-2.x ו**שבר** את pandas/pyarrow בסביבה הגלובלית (כל דבר אחר שרץ
עליה נשבר זמנית). **תוקן** על ידי הורדת numpy בחזרה (`pip install "numpy<2"`)
בסביבה הגלובלית.

**המסקנה החשובה**: אף פעם אל תתקינו חבילות מחקר (shap/torch/וכו') על ה-Python הגלובלי.
במקום זה נוצרה סביבת `.venv` ייעודית לפרויקט:
```powershell
cd Project
python -m venv ..\.venv        # אם ה-.venv כבר קיים במחשב החדש, פשוט תפעילו אותו
..\.venv\Scripts\Activate.ps1
pip install -e ".[xai-research]"
```
שימו לב: ה-`.venv` נמצא ברמת השורש (`proj/.venv`, מחוץ ל-`Project/`), לא בתוך `Project/`.
זה גם **לא** עלה לגיט (1.4GB, וגם קבצים בודדים בתוכו גדולים מ-100MB — מעבר למגבלה
הקשיחה של GitHub) — צריך ליצור אותו מחדש בכל מחשב.

## 4. שינוי מבנה הריפו + מיזוג ל-GitHub

התגלה שה-remote שהיה מוגדר קודם (`https://github.com/Snafuzila/AI-CyberSecurity/tree/main/Project`)
הוא כתובת URL של דפדפן ולא endpoint גיט תקין — זו הסיבה שדחיפות קודמות לא עבדו.

חקירה גילתה שהריפו האמיתי `Snafuzila/AI-CyberSecurity` הוא מונו-ריפו עם שני תיקיות
עליונות: `Labs/` (עבודות קודמות מהקורס) ו-`Project/` (שהכיל בעבר רק ערמת קבצי zip
ישנים: `Temp.txt`, `new 3.txt`, שלושה קבצי zip). המטרה הוסכמה: להעביר את כל התוכן
המקומי לתוך `Project/`, לשמר את `Labs/` בלי לגעת בו, ולהחליף את ערמת ה-zip הישנה
בקוד המעקב האמיתי.

**מה בוצע בפועל**:
1. `git init` בתיקיית `d:\CyberSecurityAiBoLem\proj` (שורש הריפו המקומי).
2. Commit ראשוני עם כל 72 הקבצים (בשורש, לפני שינוי המבנה).
3. **שינוי מבנה**: `git mv` של כל קובץ/תיקייה עליונים (`.env.example`, `README.md`,
   `morpheus_lite/`, `research/`, `data/`, `docs/`, `config/`, `tests/`, וכו') לתוך
   תיקיית `Project/` חדשה. **חריג חשוב**: `.gitignore` **לא** הועבר לתוך `Project/` —
   הוא נשאר בשורש הריפו (`proj/.gitignore`), כי שורש הריפו הגיטי הוא `proj/` ולא
   `Project/`. כל התבניות ב-`.gitignore` שכוללות סלאש (למשל `data/*.txt`) עודכנו
   לקבל prefix של `Project/` (כלומר `Project/data/*.txt`), אחרת הן לא היו תופסות בכלל.
4. `git remote set-url origin https://github.com/Snafuzila/AI-CyberSecurity.git`
   (תיקון הכתובת השבורה).
5. `git fetch origin` + `git branch -M main` (שינוי שם הענף המקומי מ-`master` ל-`main`
   כדי להתאים לברירת המחדל ב-GitHub).
6. `git merge origin/main --allow-unrelated-histories` — מיזוג היסטוריות לא קשורות
   (כי לריפו המקומי היה commit history משלו). המיזוג עבר **בלי קונפליקטים**.
7. הוסרו 5 הקבצים הישנים שהמיזוג הכניס: `Project/Temp.txt`,
   `Project/lab2 Anomaly Detection.zip`, `Project/lab2a-morpheus-lite-migration-v2.zip`,
   `Project/lab2a-morpheus-lite.zip`, `Project/new 3.txt`.
8. `git push origin main` — **הצליח**. אומת מול GitHub API ש-`Project/` מכיל בדיוק
   את 72 הקבצים הנכונים, ו-`Labs/` נשאר בדיוק כמו שהיה.

**וידוא שבוצע**: `git diff origin/main HEAD` מחזיר ריק — כלומר מה שמקומי תחת
`Project/` זהה ביט-לביט למה שנמצא היום ב-GitHub. אין drift.

## 5. מה נמצא ב-`.gitignore` ולמה (שורש הריפו: `proj/.gitignore`)

| קטגוריה | תבנית | סיבה |
|---|---|---|
| venv | `.venv/` | 1.4GB, קבצים בודדים >100MB (מעבר למגבלת GitHub), לא פורטבילי בין מחשבים |
| Python | `__pycache__/`, `*.egg-info/` וכו' | נוצר אוטומטית מחדש |
| דאטהסט NSL-KDD | `Project/data/*.txt`, `Project/data/*.csv` | רישוי — הוחלט במפורש לא להעלות, במקום זה יש הוראות הורדה ב-README |
| CSV לא ברור מקור | `Project/research/xai_rai_comparison/nsl_kdd_test_predictions_from_saved_models.csv` | סומן ב-README_handover.md כ"לא חלק מה-build של Phase 1-4" |
| ארכיון גיבוי אישי | `lab2a-morpheus-lite-migration-v2.zip` | 12MB, לא קוד מקור |
| תוצאות ריצה | `exports/` | נוצר מחדש בכל הרצה של `run_scenarios.py` |
| הגדרות Claude Code מקומיות | `.claude/settings.local.json` | ספציפי למכונה, לא תוכן פרויקט |

**נשאר במעקב (מחובר לגיט) בכוונה**, כי צריך אותו כדי לשחזר תוצאות בלי לאמן מחדש:
`Project/research/xai_rai_comparison/artifacts/nsl_kdd/` (isolation_forest.pkl,
autoencoder.pt, scaler.pkl, encoder.pkl, manifest.json — פחות מ-1MB בסך הכול).

## 6. איך להמשיך על מחשב אחר — שלב אחר שלב

```bash
git clone https://github.com/Snafuzila/AI-CyberSecurity.git
cd AI-CyberSecurity/Project

# 1. סביבה וירטואלית (חובה ליצור מחדש בכל מחשב, לא מגיע מהגיט)
python -m venv ../.venv
../.venv/Scripts/Activate.ps1        # PowerShell; ../.venv/bin/activate בלינוקס/מק
python -m pip install --upgrade pip
pip install -e ".[xai-research]"     # מוסיף torch, shap, scipy

# 2. דאטהסט NSL-KDD (לא בגיט, חובה להוריד ידנית)
#    מ-https://www.unb.ca/cic/datasets/nsl.html
#    להניח את KDDTrain+.txt ו-KDDTest+.txt ישירות בתוך Project/data/

# 3. Ollama עם llama3.1:8b (מקומי, לא בגיט)
ollama pull llama3.1:8b
# ודאו ש-Ollama רץ (על Windows, אפליקציית Ollama רצה כשירות אוטומטית בפורט 11434)

# 4. הרצה (ה-artifacts המאומנים כבר קיימים בגיט, אין צורך לאמן מחדש)
cd research/xai_rai_comparison
python run_scenarios.py                    # מריץ הכול כולל קריאה אמיתית ל-Llama
python run_scenarios.py --no-llm           # רק הדפסת פרומפטים, בלי LLM
python train_and_persist.py                # אופציונלי: לאמן מחדש מאפס (seed=42, אמור לתת תוצאה זהה)
```

## 7. דברים פתוחים / החלטות שעדיין לא התקבלו

1. **זהות ה-commit author**: כל ה-commits בסשן הזה נחתמו אוטומטית בתור
   `VLSI Lab <vlsi@stud-hait.ac.il>` (זוהה אוטומטית משם המשתמש/hostname של Windows),
   **לא** בהכרח הזהות האמיתית של המשתמש ב-GitHub (המייל שדווח למערכת:
   `lotem1237@gmail.com`). Claude נמנע במכוון משינוי git config בלי אישור מפורש.
   אם רוצים לתקן: `git config user.name "..."` ו-`git config user.email lotem1237@gmail.com`
   (מקומי, לא global), ואז אפשר לבקש `git commit --amend --reset-author` על ה-commits
   הרלוונטיים.

2. **בקשה שלא הושלמה**: המשתמש ביקש "לרשום ולמחוק" קבצים תחת `Project/` שאינם קשורים
   ל-`research/xai_rai_comparison/` (כלומר כל תשתית ה-Kafka החיה: `morpheus_lite/`,
   `agent_orchestrator.py`, `dashboard.py`, `docker-compose.yml`, `config/`, `tests/`,
   `docs/`, וכו'), בטענה ש"רק קבצים תחת research/xai_rai_comparison הם קבצי הפרויקט
   האמיתיים". **זה לא בוצע** — הסשן הופנה במקום זה לבירור "אי-התאמה" (mismatch) שהתברר
   כלא-בעיה (הכול היה תואם, ההבדלים היו רק קבצים שב-gitignore בכוונה). **ההחלטה הזו
   עדיין פתוחה**: האם באמת למחוק את כל תשתית ה-Morpheus Lite Laboratory (עבודת קורס
   נפרדת ומשמעותית, ~50 קבצים) מתוך `Project/`, ולהשאיר שם רק את מה שקשור ל-XAI/RAI
   research suite? שווה לוודא עם המשתמש בפעם הבאה שזו באמת הכוונה לפני מחיקה, כי זו
   פעולה הרסנית על ריפו משותף/ציבורי.

## 8. עובדות טכניות נוספות שכדאי לזכור

- מחשב זה: Windows 10, Python גלובלי 3.12.7 ב-`C:\anaconda3\python.exe`. Ollama מותקן
  ב-`C:\Users\vlsi\AppData\Local\Programs\Ollama\ollama.exe`, עם המודלים:
  `llama3.1:8b` (4.9GB, נמשך במהלך הסשן הזה), `llava:latest` (7B, family=llama, נועד
  ל-vision+text), `deepseek-r1:latest` (7.6GB, family=qwen2).
- אין קובץ `.env` בפרויקט (רק `.env.example`) — אין סיכון חשיפת סודות בהיסטוריית הגיט.
- הריפו המקומי (`d:\CyberSecurityAiBoLem\proj\.git`) הוא כרגע שורש שמכיל גם `Project/`
  וגם `Labs/` (אחרי המיזוג) — זה תואם בדיוק את מבנה ה-remote ב-GitHub.
