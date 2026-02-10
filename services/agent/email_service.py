import os
import random
import aiosmtplib
from pathlib import Path
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv
# 1. Locate .env file (Assuming it's in the project root)
BASE_DIR = Path(__file__).resolve().parent
while not (BASE_DIR / ".env").exists() and BASE_DIR.parent != BASE_DIR:
    BASE_DIR = BASE_DIR.parent

env_path = BASE_DIR / ".env"

# 2. Forced load karo
load_dotenv(dotenv_path=env_path)

# 3. Test karne ke liye ek print lagao (sirf check karne ke liye, baad mein hata dena)
print(f"--- DEBUG: SMTP_USER is {os.getenv('SMTP_USER')} ---")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SMTP_KEY = os.getenv("SMTP_KEY")


async def send_otp_via_brevo(receiver_email: str, otp: str) -> bool:
    # OTP ab hum API se bhejenge, yahan generate nahi karenge
    message = EmailMessage()
    message["From"] = f"Juristway Support <{SENDER_EMAIL}>"
    message["To"] = receiver_email
    message["Subject"] = f"{otp} is your Juristway Reset Code"
    
    html_body = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #ddd;">
        <h2 style="color: #1a73e8;">Password Reset</h2>
        <p>Use the following OTP to reset your password. Valid for 30 minutes:</p>
        <h1 style="background: #f1f3f4; padding: 10px; text-align: center; letter-spacing: 5px;">{otp}</h1>
    </div>
    """
    message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=SMTP_SERVER,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_KEY,
            start_tls=True,
            use_tls=False
        )
        return True # Success par True return karo
    except Exception as e:
        print(f"❌ SMTP Error: {str(e)}")
        return False