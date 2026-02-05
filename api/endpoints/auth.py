from email.message import EmailMessage
import shutil
from typing import Optional
import aiosmtplib
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, logger, status
from fastapi.security import OAuth2PasswordRequestForm
from core.security import verify_password, create_access_token, get_current_user, get_password_hash
from core.database import (
    get_users_collection,
    get_chats_collection,
    get_documents_collection,
    get_subscriptions_collection,
    get_token_usage_collection,
)
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import os
from dotenv import load_dotenv
import logging

from services.agent.email_service import send_otp_via_brevo
load_dotenv()


SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_KEY = os.getenv("SMTP_KEY")    

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    users_collection = get_users_collection()
    
    # In MongoDB, we use email as the unique identifier
    # Add a max_time_ms to force a timeout if the DB is unreachable
    user = await users_collection.find_one(
            {"email": form_data.username}

        )
    
    print(f"DEBUG: Attempting login for: '{form_data.username}'")
    print(f"DEBUG: User found in DB: {True if user else False}")
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer", "is_admin": user.get("is_admin", False)}


@router.delete("/account")
async def delete_my_account(current_user: dict = Depends(get_current_user)):
    """
    Deletes the currently authenticated user's account and associated data.
    """
    users_coll = get_users_collection()
    chats_coll = get_chats_collection()
    documents_coll = get_documents_collection()
    subscriptions_coll = get_subscriptions_collection()
    token_usage_coll = get_token_usage_collection()

    user_id = str(current_user["_id"])
    user_email = current_user.get("email")

    # 1) delete primary user record
    await users_coll.delete_one({"_id": current_user["_id"]})

    # 2) delete associated data (best-effort, keyed by the schemas currently used)
    await chats_coll.delete_many({"user_id": user_id})

    if user_email:
        await documents_coll.delete_many({"owner": user_email})
        await subscriptions_coll.delete_many({"user_email": user_email})
        await token_usage_coll.delete_many({"user_email": user_email})

    return {"message": "Account deleted successfully"}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    token: int # reset otp sent via email
    new_password: str


def _hash_reset_token(token: str) -> str:
    """
    Hash reset tokens before storing in DB (so leaked DB doesn't expose usable tokens).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()



@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    users_coll = get_users_collection()
    user = await users_coll.find_one({"email": payload.email.lower()})

    if user:
        raw_token = str(secrets.randbelow(899999) + 100000) 
        token_hash = _hash_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        await users_coll.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_reset_token_hash": token_hash, "password_reset_expires_at": expires_at}},
        )

        # Yahan check karo: Kya aapne 'send_otp_via_brevo' ko hi 'send_reset_email' ka naam diya hai?
        # Agar function ka naam 'send_otp_via_brevo' hai, toh wahi yahan call karo:
        email_sent = await send_otp_via_brevo(payload.email)        
        if not email_sent:
            print(f"❌ Failed to send password reset email to {payload.email}")
    return {"message": "A password reset code has been sent to your email if it exists in our system."}

@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    users_coll = get_users_collection()
    user = await users_coll.find_one({"email": payload.email.lower()})
    
    # 1. User check
    if not user:
        raise HTTPException(status_code=400, detail="Invalid request or user not found")

    token_hash = user.get("password_reset_token_hash")
    expires_at = user.get("password_reset_expires_at")

    # 2. Token exist check
    if not token_hash or not expires_at:
        raise HTTPException(status_code=400, detail="Reset process not initiated")

    # 3. Timezone consistency (Force UTC)
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    # 4. Expiry check
    if now > expires_at:
        raise HTTPException(status_code=400, detail="OTP/Token has expired")

    # 5. Token Hash Match (Ensure payload.token is string)
    if _hash_reset_token(str(payload.token)) != token_hash:
        raise HTTPException(status_code=400, detail="Invalid OTP/Token")

    # 6. Password Update
    new_hash = get_password_hash(payload.new_password)
    await users_coll.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"hashed_password": new_hash},
            "$unset": {"password_reset_token_hash": "", "password_reset_expires_at": ""},
        },
    )

    return {"message": "Password has been reset successfully"}



@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """
    Ye endpoint login user ki profile return karega.
    """
    # MongoDB se user object milne par '_id' ObjectID hota hai jo JSON serializable nahi hota,
    # Isliye hum use string mein convert kar dete hain.
    current_user["_id"] = str(current_user["_id"])
    
    # Security ke liye sensitive data (like password) hata dete hain
    if "hashed_password" in current_user:
        del current_user["hashed_password"]
    if "password_reset_token_hash" in current_user:
        del current_user["password_reset_token_hash"]

    return current_user 


# edit profile endpoint, jisme user apna naam, profile picture, mobile number etc. update kar sakta hai.
UPLOAD_DIR = "storage/profile_pics"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.put("/edit-profile")
async def edit_profile(
    full_name: Optional[str] = Form(None),
    mobile_number: Optional[str] = Form(None),
    country_code: Optional[str] = Form("IN"), 
    profile_pic: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    users_coll = get_users_collection()
    update_data = {}

    # 1. Full Name update
    if full_name:
        update_data["full_name"] = full_name.strip()

    # 2. Simple Mobile Update (No Verification logic)
    if mobile_number:
        # Bus whitespace saaf kar lo
        clean_number = mobile_number.strip()
        
        # Uniqueness Check (Taki ek number do users ke paas na ho)
        existing_user = await users_coll.find_one({"mobile_number": clean_number})
        if existing_user and existing_user["_id"] != current_user["_id"]:
            raise HTTPException(status_code=400, detail="This mobile number is already linked to another account")
        
        update_data["mobile_number"] = clean_number
        update_data["country_code"] = country_code

    # 3. Profile Pic logic
    if profile_pic:
        file_extension = profile_pic.filename.split(".")[-1]
        file_name = f"{current_user['_id']}_{int(datetime.now().timestamp())}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_pic.file, buffer)
        
        update_data["profile_pic_url"] = f"/static/profile_pics/{file_name}"

    # 4. Database Update
    if not update_data:
        raise HTTPException(status_code=400, detail="No changes provided")

    await users_coll.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_data}
    )

    return {"message": "Profile updated successfully", "updated_fields": list(update_data.keys())}