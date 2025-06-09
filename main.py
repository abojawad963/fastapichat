import os
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

app = FastAPI()
client = OpenAI(api_key=OPENAI_API_KEY)

class UserMessage(BaseModel):
    stage: str  # "start" or "destination"
    start_desc: Optional[str] = None  # جواب المستخدم على جهة الانطلاق
    message: Optional[str] = None     # الوجهة (جواب المستخدم للوجهة)
    lat: Optional[float] = None
    lng: Optional[float] = None

def reverse_geocode(lat, lng):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&language=ar&region=SA&key={GOOGLE_MAPS_API_KEY}"
    response = requests.get(url)
    data = response.json()
    if data['status'] == 'OK':
        address = data['results'][0]['formatted_address']
        return address
    else:
        return "موقعك الحالي"

def extract_destination(text):
    prompt = f"""
    استخرج فقط اسم الوجهة (المكان الذي يريد الذهاب إليه) من هذه الرسالة:
    "{text}"
    الرد فقط باسم الوجهة بدون شرح.
    """
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "انت مساعد افتراضي مهمتك فقط استخراج اسم الوجهة من الرسائل بدون شرح."},
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content.strip()

def get_location_coordinates(location_name):
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={location_name}&region=sa&key={GOOGLE_MAPS_API_KEY}'
    response = requests.get(url)
    data = response.json()
    if data['status'] == 'OK':
        location = data['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    else:
        return None

@app.post("/chatbot")
def chat_flow(msg: UserMessage):
    # المرحلة الأولى: اقتراح جهة الانطلاق
    if msg.stage == "start":
        current_loc_name = reverse_geocode(msg.lat, msg.lng) if msg.lat and msg.lng else "موقعك الحالي"
        return {
            "success": True,
            "ask": f"وين بدك جهة الانطلاق؟ من ({current_loc_name}) ولا تكتب مكان ثاني بنفسك؟",
            "current_loc_name": current_loc_name,
            "lat": msg.lat,
            "lng": msg.lng,
        }

    # المرحلة الثانية: تحديد الوجهة
    elif msg.stage == "destination":
        # حدد نقطة الانطلاق
        if not msg.start_desc or msg.start_desc.strip() == "" or msg.start_desc.lower() in ["موقعي", "الموقع الحالي"]:
            # استخدم موقع المستخدم الحالي
            if msg.lat and msg.lng:
                start_coords = (msg.lat, msg.lng)
                start_desc = reverse_geocode(msg.lat, msg.lng)
            else:
                return {"success": False, "message": "تعذر جلب الموقع الحالي. حاول مجددًا."}
        else:
            # المستخدم كتب نقطة انطلاق يدويًا
            start_desc = msg.start_desc
            start_coords = get_location_coordinates(start_desc)
            if not start_coords:
                return {"success": False, "message": f"تعذر تحديد موقع الانطلاق ({start_desc}). اكتب اسم أوضح."}

        # حدد الوجهة
        if not msg.message:
            return {"success": False, "message": "يرجى إرسال اسم الوجهة."}
        end = extract_destination(msg.message)
        end_coords = get_location_coordinates(end)
        if not end_coords:
            return {"success": False, "message": f"تعذر تحديد الوجهة ({end}). اكتب اسم أوضح."}

        return {
            "success": True,
            "message": f"تم تحديد رحلتك من ({start_desc}) إلى ({end}) بنجاح.",
            "start": {"name": start_desc, "coords": start_coords},
            "end": {"name": end, "coords": end_coords}
        }
