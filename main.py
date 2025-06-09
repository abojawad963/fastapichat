import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI

# اقرأ المتغيرات البيئية (يفضل تحفظهم في .env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

app = FastAPI()
client = OpenAI(api_key=OPENAI_API_KEY)

class UserMessage(BaseModel):
    message: str

def extract_locations(text):
    # استخدم GPT لتحليل الرسالة واستخراج المواقع
    prompt = f"""
    استخرج لي اسم موقع الانطلاق واسم الوجهة من هذه الرسالة بالعربي فقط بدون شرح:
    "{text}"
    الرد يكون بصيغة: 
    الانطلاق: <الانطلاق>
    الوجهة: <الوجهة>
    """
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",  # ممكن تستخدم gpt-4o إذا متوفر عندك
        messages=[
            {"role": "system", "content": "انت مساعد افتراضي مهمتك تستخرج مواقع من الرسائل فقط"},
            {"role": "user", "content": prompt}
        ]
    )
    reply = completion.choices[0].message.content
    # استخراج النص من الرد
    start, end = None, None
    for line in reply.splitlines():
        if line.startswith("الانطلاق:"):
            start = line.replace("الانطلاق:", "").strip()
        elif line.startswith("الوجهة:"):
            end = line.replace("الوجهة:", "").strip()
    return start, end

def get_location_coordinates(location_name):
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={location_name}&key={GOOGLE_MAPS_API_KEY}'
    response = requests.get(url)
    data = response.json()
    if data['status'] == 'OK':
        location = data['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    else:
        return None

@app.post("/chatbot")
def process_user_message(msg: UserMessage):
    # 1. استخرج المواقع من الرسالة
    start, end = extract_locations(msg.message)
    if not start or not end:
        return {"success": False, "message": "يرجى تحديد موقع الانطلاق والوجهة بوضوح"}

    # 2. تحقق من المواقع باستخدام Google Maps API
    start_coords = get_location_coordinates(start)
    end_coords = get_location_coordinates(end)

    if not start_coords or not end_coords:
        missing = []
        if not start_coords:
            missing.append(f"الانطلاق ({start})")
        if not end_coords:
            missing.append(f"الوجهة ({end})")
        return {
            "success": False,
            "message": f"تعذر تحديد الموقع بدقة: {' و '.join(missing)}. يرجى إعادة كتابة المواقع بشكل أوضح."
        }

    # 3. أرجع الرد المنظم
    return {
        "success": True,
        "start": {"name": start, "coords": start_coords},
        "end": {"name": end, "coords": end_coords},
        "message": f"تم تحديد موقع الانطلاق ({start}) والوجهة ({end}) بنجاح."
    }

