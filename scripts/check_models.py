from google import genai

API_KEY = "AIzaSyC9IU3RGGdubiQUCbUrTC1QSV6ug_xH-Iw"
client = genai.Client(api_key=API_KEY)

print("--- מחפש מודלים זמינים למפתח שלך ---")
try:
    # שליפת כל המודלים
    models = client.models.list()
    
    print("\nהמודלים שאתה יכול להשתמש בהם:")
    for m in models:
        # נסנן רק מודלים של ג'מיני שרלוונטיים ליצירת טקסט
        if 'gemini' in m.name and 'vision' not in m.name:
            print(f"- {m.name}")
except Exception as e:
    print(f"שגיאה: {e}")