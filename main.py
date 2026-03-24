import os
import asyncio
import glob
import time
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types
import edge_tts
import uvicorn
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
AUDIO_DIR = os.path.join(BASE_DIR, "tmp_audio")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# אתחול שרת ה-Web
app = FastAPI()
# פותר את שגיאת ה-CORS שקפצה לך
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# קריאת בסיס הידע
try:
    with open(os.path.join(DATA_DIR, "cv.txt"), "r", encoding="utf-8") as file:
        my_cv_content = file.read()
        
    with open(os.path.join(DATA_DIR, "knowledge_base.txt"), "r", encoding="utf-8") as file:
        knowledge_base = file.read()
    with open(os.path.join(DATA_DIR, "scrabble.txt"), "r", encoding="utf-8") as file:
        knowledge_base += "\n" + file.read()
    with open(os.path.join(DATA_DIR, "sokuban and classification.txt"), "r", encoding="utf-8") as file:
        knowledge_base += "\n" + file.read()
except FileNotFoundError:
    my_cv_content = "קורות חיים חסרים."
    knowledge_base = "מידע על פרויקטים חסר."

agent_persona = f"""
אתה סוכן AI אינטראקטיבי שמייצג את ברק בן אקון בראיונות עבודה. 
--- קורות חיים ומידע על פרויקטים ---
{my_cv_content}
--- סוף קורות חיים ---
---הרחבה על פרוייקטים---
{knowledge_base}
--- סוף הרחבה ---

הנחיות קריטיות:
1. חוק שפה ברזל: בתחילת כל הודעה תקבל פקודה בסוגריים מרובעים לגבי שפת התשובה. עליך לענות **אך ורק** בשפה זו!
2. דבר תמיד בגוף ראשון בשם ברק. בטוח בעצמו, מקצועי ומדבר בגובה העיניים.
3. ענה בתשובות קצרות וקולעות (2-3 משפטים בלבד). שלב נתונים מדויקים.
4. חוק הקראה (תקף רק כשאתה עונה בעברית!): כשאתה עונה בעברית, חובה להשתמש באיות הפונטי הבא כדי למנוע שיבושי הקראה:   - Backend -> בֶּק-אֶנְד
   - Scrabble -> סְקְרָאבֶּל
   - Google -> גוּגֶל
   - AWS -> איי דבליו אס
   - C++ -> סי פלוס פלוס
5. שאלות אישיות (Easter Egg): מותר ורצוי לספר על תחביבים ומשפחה (כמו אפייה, טיולים, אישה וילדים) **אך ורק אם זה כתוב במידע שלך**. אם שואלים משהו ש*לא* מופיע שם, ענה בנימוס: "אני רק הסוכן הווירטואלי של ברק, אז אין לי את כל התשובות. אבל אפשר לשאול אותו ישירות בלינקדאין!"
6. סיים בשאלה קצרה המזמינה את המראיין להעמיק (למשל: "תרצה שאפרט על...?").
7. טקסט רציף בלבד, ללא הדגשות (כוכביות) או רשימות.
8. אסור לך להציג את תהליך החשיבה שלך. החזר אך ורק את התשובה הסופית המיועדת למראיין.
9. אם שואלים אותך על נושאים אישיים, פוליטיים, או דברים שלא מופיעים במידע שלך, ענה בנימוס: 'אני רק הסוכן הווירטואלי של ברק, אז אין לי את כל התשובות. אבל אפשר לשאול אותו ישירות בלינקדאין!'
"""
#7. חובה קריטית להקראה קולית חלקה: המראיין מאזין לך קולית. כדי שהקריין לא ייתקע, עליך לכתוב מונחים טכניים ושמות באנגלית בעזרת אותיות בעברית (תעתיק פונטי). למשל: כתוב 'ג'אווה' ולא Java, 'מונגו די-בי' ולא MongoDB, 'ריאקט' ולא React, 'סי פלוס פלוס' ולא C++.

API_KEYS = [
    os.getenv("GEMINI_API_KEY_1", "YOUR_FIRST_KEY_HERE"),
    os.getenv("GEMINI_API_KEY_2", "YOUR_SECOND_KEY_HERE"),
    os.getenv("GEMINI_API_KEY_3", "YOUR_THIRD_KEY_HERE")
    ]

clients_pool = [genai.Client(api_key=key) for key in API_KEYS if key and key != "YOUR_FIRST_KEY_HERE"]

FAST_MODELS_POOL = [
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-flash-latest'
]

# הנה השדרוג הגאוני שלך: יוצרים רשימה שטוחה של *כל* השילובים (למשל 9 שילובים)
# (מפתח1+מודל1), (מפתח1+מודל2), (מפתח2+מודל1) וכך הלאה...
ALL_COMBOS = [(client, model) for client in clients_pool for model in FAST_MODELS_POOL]
current_combo_index = 0


active_sessions = {}

def get_or_create_chat(session_id: str):
    global current_combo_index 
    
    if session_id not in active_sessions:
        if not ALL_COMBOS:
            raise Exception("No API keys or models configured!")
            
        # שולפים את השילוב הבא בתור מתוך 9 האפשרויות
        chosen_client, chosen_model = ALL_COMBOS[current_combo_index]
        
        print(f"🚀 Assigning Combo {current_combo_index + 1}/{len(ALL_COMBOS)}: Model {chosen_model} -> Session: {session_id}")
        
        # מקדמים את התור. אם הגענו ל-9, חוזרים ל-0.
        current_combo_index = (current_combo_index + 1) % len(ALL_COMBOS)
        
        active_sessions[session_id] = chosen_client.chats.create(
            model=chosen_model,
            config=types.GenerateContentConfig(
                system_instruction=agent_persona,
                temperature=0.4,
            )
        )
    return active_sessions[session_id]


def clean_response(text):
    # מוחק כל טקסט שנמצא בתוך סוגריים מרובעים בתחילת התשובה
    text = re.sub(r'^\[.*?\]\s*', '', text)
    if "THOUGHT:" in text:
        text = text.split("THOUGHT:")[-1].strip()
    return text.replace("**", "").replace("*", "").replace("#", "").strip()


# הוספנו פרמטר שפה!
# --- מערכת הריגול (שמירת היסטוריה) ---
def log_chat(session_id: str, user_msg: str, agent_msg: str):
    try:
        # שולף את התאריך של היום
        today_date = datetime.now().strftime("%Y-%m-%d")
        
        # יוצר שם קובץ שמתחיל בתאריך, כך שהם יסתדרו כרונולוגית!
        # לדוגמה: 2026-03-20_sess_1234.txt
        file_name = os.path.join(LOGS_DIR, f"{today_date}_{session_id}.txt")
        
        with open(file_name, "a", encoding="utf-8") as f:
            time_now = datetime.now().strftime("%H:%M:%S")
            f.write(f"[{time_now}] User:  {user_msg}\n")
            f.write(f"[{time_now}] Agent: {agent_msg}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        print("Failed to save log:", e)
        
class ChatRequest(BaseModel):
    message: str
    session_id: str
    language: str = "he"
    text_only: bool = False

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


def remove_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"Error deleting file: {e}")
        
@app.get("/avatar.jpg")
async def get_avatar_image():
    avatar_path = os.path.join(STATIC_DIR, "avatar.jpg")
    if os.path.exists(avatar_path):
        return FileResponse(avatar_path)
    return {"error": "Image not found"}

@app.get("/Barak_Ben_Acon_Resume.pdf")
async def get_cv_pdf():
    cv_pdf_path = os.path.join(STATIC_DIR, "Barak_Ben_Acon_Resume.pdf")
    if os.path.exists(cv_pdf_path):
        return FileResponse(cv_pdf_path)
    return {"error": "CV not found."}

# --- קריאת ההיסטוריה המסודרת ---
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "barak_admin")

@app.get("/api/logs")
async def get_logs(secret: str = ""):
    if secret != ADMIN_SECRET:
        return PlainTextResponse("Access Denied", status_code=403)
    
    if not os.path.exists(LOGS_DIR):
        return PlainTextResponse("No chat history yet (Logs folder empty).")
    
    # אוסף את כל הקבצים ומציג אותם יפה
    all_logs = "=== מערכת ריגול: היסטוריית שיחות ===\n\n"
    log_files = glob.glob(os.path.join(LOGS_DIR, "*.txt"))
    
    if not log_files:
         return PlainTextResponse("No chat history yet.")
         
    for file_path in log_files:
        session_name = os.path.basename(file_path).replace('.txt', '').replace('log_', '')
        all_logs += f"👤 שיחה עם משתמש מזהה: {session_name}\n"
        all_logs += "=" * 60 + "\n"
        with open(file_path, "r", encoding="utf-8") as f:
            all_logs += f.read()
        all_logs += "\n\n"
        
    return PlainTextResponse(all_logs)

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    start_time = time.time()
    lang_instruction = "Please answer in English." if request.language == "en" else "ענה בעברית בלבד."
    full_message = f"[{lang_instruction}] {request.message}"
    
    # --- מנגנון הריפוי והניסיון החוזר (Auto-Retry) ---
    max_attempts = len(ALL_COMBOS)
    attempts = 0
    success = False
    clean_text = ""
    
    while attempts < max_attempts and not success:
        try:
            chat = get_or_create_chat(request.session_id)
            response = await asyncio.to_thread(chat.send_message, full_message)
            clean_text = clean_response(response.text)
            success = True # הצלחנו! יוצאים מהלולאה
            
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ Attempt {attempts + 1} failed: {error_msg}")
            
            # אם קיבלנו שגיאת עומס/מכסה מגוגל
            if "429" in error_msg or "quota" in error_msg.lower() or "exhausted" in error_msg.lower():
                attempts += 1
                if request.session_id in active_sessions:
                    del active_sessions[request.session_id] # מוחקים את המודל התקול
                print("🔄 Silently retrying with the next model in the pool...")
            else:
                # אם זו שגיאה אחרת (לא עומס), אין טעם לנסות שוב
                break 

    # אם סיימנו את הלולאה ועדיין אין הצלחה (כל המודלים קרסו)
    if not success:
        error_text = "השרת קצת עמוס כעת מרוב פניות. אנא נסה שוב בעוד מספר דקות! 🚀"
        if request.language == "en":
             error_text = "The server is currently busy. Please try again in a few minutes! 🚀"
        return {"text": error_text, "audio_ready": False}

    # --- המשך רגיל (יצירת אודיו) רק אם הצלחנו ---
    try:
        llm_time = time.time()
        print(f"⏳ Gemini took: {llm_time - start_time:.2f} seconds")
        
        log_chat(request.session_id, request.message, clean_text)
        
        if request.text_only:
            return {"text": clean_text, "audio_ready": False}
        
        filename = os.path.join(AUDIO_DIR, f"response_{request.session_id}.mp3")
        voice = "en-US-GuyNeural" if request.language == "en" else "he-IL-AvriNeural"
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(filename)
        
        tts_time = time.time()
        print(f"🎙️ Microsoft TTS took: {tts_time - llm_time:.2f} seconds")
        print(f"✅ Total time: {tts_time - start_time:.2f} seconds")
        
        return {"text": clean_text, "audio_ready": True}
    except Exception as e:
        print(f"Error in TTS/Logging: {e}")
        return {"error": "שגיאה ביצירת קול."}
    
    
@app.get("/api/audio/{session_id}")
async def get_audio(session_id: str, background_tasks: BackgroundTasks):
    filename = os.path.join(AUDIO_DIR, f"response_{session_id}.mp3")
    if os.path.exists(filename):
        # מורה לשרת למחוק את הקובץ *אחרי* שהוא מסיים לשלוח אותו למשתמש!
        background_tasks.add_task(remove_file, filename)
        return FileResponse(filename, media_type="audio/mpeg")
    return {"error": "File not found"}
# --- חדש! טיפול בבקשות HEAD עבור UptimeRobot ---
@app.head("/")
async def head_root():
    return {"status": "ok"}


if __name__ == "__main__":
    # התיקון הקריטי עבור Render
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

