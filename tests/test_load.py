import requests
import time

# הכתובת של השרת המקומי שלך
URL = "http://127.0.0.1:8000/api/chat"

print("🚀 Starting Load Test: Simulating 10 different users...\n")

for i in range(1, 11): # לולאה שרצה 10 פעמים
    fake_session_id = f"test_user_{i}"
    
    # הבקשה שאנחנו שולחים לשרת (שמנו text_only=True כדי שזה יהיה מהיר ולא ייצר סתם קבצי אודיו)
    payload = {
        "session_id": fake_session_id,
        "message": "שלום, מה שלומך?",
        "language": "he",
        "text_only": True 
    }
    
    print(f"👤 User {i} connecting (Session: {fake_session_id})...")
    
    try:
        # שולחים את הבקשה ומחכים לתשובה
        response = requests.post(URL, json=payload)
        
        if response.status_code == 200:
            print(f"✅ User {i} got answer: {response.json().get('text')[:30]}...\n")
        else:
            print(f"❌ User {i} got Error: {response.status_code}\n")
            
    except Exception as e:
        print(f"⚠️ Connection error for User {i}: {e}\n")
    
    # מחכים שנייה אחת בין משתמש למשתמש כדי לא לחנוק את המחשב שלך
    time.sleep(1)

print("🏁 Load Test Finished!")