import chainlit as cl
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import google.generativeai as genai
import random, datetime, re

# ------------------- FastAPI Setup -------------------
allowed_ports = [3000, 5173]
allow_origins = [f"http://localhost:{port}" for port in allowed_ports] + \
                [f"http://127.0.0.1:{port}" for port in allowed_ports]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- Gemini Setup -------------------
genai.configure(api_key="AIzaSyCNQF9HwY19SVbmErBNNJ9RxG7KgDaNE8M")  # replace with real key
model = genai.GenerativeModel("gemini-1.5-flash")

BOT_NAME = "CivicComplaintBot"
BOT_EMOJI = "📝"

# ------------------- Session -------------------
class ChatSession:
    def __init__(self):
        self.complaint_details = {
            "complaint_id": None,
            "issue_type": None,
            "name": None,
            "phone_number": None,
            "description": None
        }

    def update(self, key, value):
        if value:
            self.complaint_details[key] = value.strip()

    def is_complete(self):
        return all(self.complaint_details.values())

    def generate_id(self):
        today = datetime.datetime.now().strftime("%Y%m%d")
        rand_num = random.randint(1000, 9999)
        cid = f"CMP-{today}-{rand_num}"
        self.update("complaint_id", cid)

    def summary(self):
        d = self.complaint_details
        return f"""
### ✅ Complaint Registered
- *Complaint ID:* {d['complaint_id']}
- *Issue Type:* {d['issue_type']}
- *Name:* {d['name']}
- *Phone:* {d['phone_number']}
- *Description:* {d['description']}
"""

    def reset(self):
        self.__init__()

# ------------------- Info Extraction -------------------
def extract_info(session, text):
    lower = text.lower()

    # Phone number
    phone = re.search(r"\b\d{10}\b", text)
    if phone and not session.complaint_details["phone_number"]:
        session.update("phone_number", phone.group())

    # Issue type
    for issue in ["pothole", "water leakage", "streetlight", "garbage"]:
        if issue in lower and not session.complaint_details["issue_type"]:
            session.update("issue_type", issue.title())

    # Name
    if ("my name is" in lower or "i am" in lower) and not session.complaint_details["name"]:
        words = text.split()
        session.update("name", words[-1])

    # Description (longer sentences only if missing)
    if len(text.split()) > 6 and not session.complaint_details["description"]:
        session.update("description", text)

# ------------------- Chat Flow -------------------
@cl.on_chat_start
async def start_chat():
    session = ChatSession()
    cl.user_session.set("chat_session", session)

    welcome = f"# {BOT_EMOJI} Welcome to {BOT_NAME}\nHello! Tell me what problem you are facing."
    await cl.Message(content=welcome).send()

@cl.on_message
async def handle_message(message: cl.Message):
    session: ChatSession = cl.user_session.get("chat_session")
    if session is None:
        session = ChatSession()
        cl.user_session.set("chat_session", session)

    user_input = message.content.strip()
    extract_info(session, user_input)

    details = session.complaint_details

    # Build smart prompt for Gemini
    prompt = f"""
You are a civic complaint assistant.
Current known details:
- Complaint ID: {details['complaint_id']}
- Issue Type: {details['issue_type']}
- Name: {details['name']}
- Phone: {details['phone_number']}
- Description: {details['description']}

Rules:
- Do NOT ask again for details that are already filled.
- Only ask about missing details.
- If all details are filled, confirm registration and show the summary.
- Keep tone interactive and natural.

User just said: "{user_input}"
Assistant:
"""

    # Send to Gemini
    response = model.generate_content(prompt)
    reply = response.text.strip()

    # If all info gathered → finalize
    if session.is_complete():
        if not details["complaint_id"]:
            session.generate_id()
        reply = session.summary()
        await cl.Message(
            content=reply,
            actions=[
                cl.Action(name="new", label="🆕 New Complaint"),
                cl.Action(name="faq", label="ℹ️ FAQs"),
            ],
        ).send()
        session.reset()
    else:
        await cl.Message(content=reply).send()

# ------------------- Buttons -------------------
@cl.action_callback("new")
async def new_complaint(action: cl.Action):
    await start_chat()

@cl.action_callback("faq")
async def faq_handler(action: cl.Action):
    faq = """
### ℹ️ Complaint FAQs
- ⏱ Resolution: Usually 2–5 working days  
- 📍 Track: Use your Complaint ID at the municipal office  
- ☎️ Emergency: Call 100  
"""
    await cl.Message(content=faq).send()
