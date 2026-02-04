import os
import random
import aiosmtplib
from pathlib import Path
from email.message import EmailMessage
from dotenv import load_dotenv

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


async def send_otp_via_brevo(receiver_email: str) -> bool:
    # 1. Generate 6-digit OTP
    otp = f"{random.randint(100000, 999999)}"
    
    # 2. Setup Email Content
    message = EmailMessage()
    message["From"] = f"Juristway Support <{SENDER_EMAIL}>" # Verify this email on Brevo
    message["To"] = receiver_email
    message["Subject"] = f"{otp} is your Juristway Reset Code"
    
    html_body = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #ddd;">
        <h2 style="color: #1a73e8;">Password Reset</h2>
        <p>Use the following OTP to reset your password. Valid for 10 minutes:</p>
        <h1 style="background: #f1f3f4; padding: 10px; text-align: center; letter-spacing: 5px;">{otp}</h1>
        <p>If you didn't request this, please ignore this email.</p>
    </div>
    """
    message.add_alternative(html_body, subtype="html")

    # 3. Connect and Send (Async)
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
        return otp
    except Exception as e:
        print(f"❌ SMTP Error: {str(e)}")
        return None