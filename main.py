# main.py
import os, uuid, requests, datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

# مفاتيح البيئة
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()

# جلســات الدردشة في الذاكرة
sessions: Dict[str, Dict[str, Any]] = {}

# ---------- أدوات مساعدة ---------- #
def reverse_geocode(lat: float, lng: float) -> str:
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?latlng={lat},{lng}&language=ar&region=SA&key={GOOGLE_MAPS_API_KEY}"
    )
    data = requests.get(url).json()
    if data["status"] == "OK":
        return data["results"][0]["formatted_address"]
    return "موقعك الحالي"

def geocode(name: str):
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={name}&region=SA&language=ar&key={GOOGLE_MAPS_API_KEY}"
    )
    data = requests.get(url).json()
    return data["results"][0] if data["status"] == "OK" else None

def extract_destination(text: str) -> str:
    prompt = f'استخرج اسم الوجهة من الرسالة التالية بدون أي كلمات إضافية:\n"{text}"'
    rsp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "أجب بالاسم فقط."},
            {"role": "user", "content": prompt},
        ],
    )
    return rsp.choices[0].message.content.strip()

# ---------- بيانات الطلب/الرد ---------- #
class UserRequest(BaseModel):
    sessionId: Optional[str] = None
    userInput: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class BotResponse(BaseModel):
    sessionId: str
    botMessage: str
    done: bool = False

# ---------- منطق الحوار ---------- #
def new_session(lat: float | None, lng: float | None) -> tuple[str, str]:
    sess_id = str(uuid.uuid4())
    sessions[sess_id] = {
        "step": "ask_destination",
        "lat": lat,
        "lng": lng,
        "start_name": reverse_geocode(lat, lng) if lat and lng else None,
        "dest_name": None,
        "time": None,
        "car": None,
        "audio": None,
        "reciter": None,
    }
    return sess_id, "مرحباً! إلى أين تريد الذهاب اليوم؟"

def proceed(session: Dict[str, Any], user_input: str) -> str:
    step = session["step"]

    # 1) الوجهة
    if step == "ask_destination":
        dest = extract_destination(user_input)
        session["dest_name"] = dest
        session["step"] = "ask_start"
        return (
            f"هل تريد أن نأخذك من موقعك الحالي ({session['start_name']})"
            " أم تفضل الانطلاق من مكان آخر؟"
        )

    # 2) الانطلاق
    if step == "ask_start":
        txt = user_input.strip().lower()
        if txt in {"موقعي", "موقعي الحالي", "الموقع الحالي"}:
            # احتفظ بالاسم الموجود مسبقاً
            pass
        else:
            session["start_name"] = user_input
        session["step"] = "ask_time"
        return "متى تريد الانطلاق؟"

    # 3) الوقت
    if step == "ask_time":
        session["time"] = user_input
        session["step"] = "ask_car"
        return "ما نوع السيارة التي تفضلها؟ عادية أم VIP؟"

    # 4) نوع السيارة
    if step == "ask_car":
        session["car"] = user_input
        session["step"] = "ask_audio"
        return (
            "هل تود الاستماع إلى شيء أثناء الرحلة؟ "
            "يمكنك اختيار القرآن الكريم، الموسيقى، أو الصمت."
        )

    # 5) الصوت
    if step == "ask_audio":
        txt = user_input.strip().lower()
        if txt in {"القرآن", "قرآن", "quran"}:
            session["audio"] = "القرآن"
            session["step"] = "ask_reciter"
            return "هل لديك قارئ مفضل أو نوع تلاوة تفضله؟"
        else:
            session["audio"] = user_input  # موسيقى أو صمت
            session["step"] = "summary"
            return build_summary(session)

    # 6) القارئ
    if step == "ask_reciter":
        session["reciter"] = user_input
        session["step"] = "summary"
        return build_summary(session)

    # 7) الملــخّص والتأكيد
    if step == "summary":
        if user_input.strip().lower() in {"نعم", "أجل", "أكيد", "نوافق"}:
            session["step"] = "confirmed"
            return "تم تأكيد الحجز! ستصلك السيارة في الوقت المحدد."
        else:
            session["step"] = "canceled"
            return "تم إلغاء الحجز بناءً على طلبك."

    return "عذراً، لم أفهم. هل يمكنك التوضيح؟"

def build_summary(s: Dict[str, Any]) -> str:
    base = (
        f"رحلتك من {s['start_name']} إلى {s['dest_name']} "
        f"في الساعة {s['time']} بسيارة {s['car']}"
    )
    if s["audio"] == "القرآن":
        base += "، مع تلاوة قرآنية"
        if s["reciter"]:
            base += f" بصوت {s['reciter']}"
    return base + ". هل تريد تأكيد الحجز بهذه التفاصيل؟"

# ---------- نقطة نهاية واحدة ---------- #
@app.post("/chatbot", response_model=BotResponse)
def chatbot(req: UserRequest):
    # جلسة جديدة
    if not req.sessionId or req.sessionId not in sessions:
        if req.lat is None or req.lng is None:
            return BotResponse(
                sessionId="",
                botMessage="لا أستطيع تحديد موقعك. الرجاء إرسال الإحداثيات أولاً.",
            )
        sess_id, msg = new_session(req.lat, req.lng)
        return BotResponse(sessionId=sess_id, botMessage=msg)

    # جلسة موجودة
    sess = sessions[req.sessionId]
    reply = proceed(sess, req.userInput or "")
    done = sess.get("step") in {"confirmed", "canceled"}
    return BotResponse(sessionId=req.sessionId, botMessage=reply, done=done)
