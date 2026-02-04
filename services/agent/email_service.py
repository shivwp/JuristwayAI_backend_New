import random
import aiosmtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()
import os
# SMTP_SERVER = os.getenv("SMTP_SERVER")
# SMTP_PORT = int(os.getenv("SMTP_PORT"))
# SMTP_USER = os.getenv("SMTP_USER")
# SENDER_EMAIL = os.getenv("SENDER_EMAIL")
# SMTP_KEY = os.getenv("SMTP_KEY")
SMTP_SERVER="smtp-relay.brevo.com"
SMTP_PORT=587
SENDER_EMAIL="no-reply@juristway.com"
SMTP_USER="76eb7c001@smtp-brevo.com"
SMTP_KEY = "xsmtpsib-365259e531a55d01a00c31bef015b56250a88141718e915a48b0985acc9b840e-nwsQ1AFX7CJtVWtH" 

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