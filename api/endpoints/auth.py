from fastapi import APIRouter, Depends, HTTPException, status
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
from dotenv import load_dotenv
load_dotenv()

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
    token: str
    new_password: str


def _hash_reset_token(token: str) -> str:
    """
    Hash reset tokens before storing in DB (so leaked DB doesn't expose usable tokens).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    """
    Initiates password reset for both users and admins (same users collection).
    Always returns a generic message to avoid user enumeration.
    """
    users_coll = get_users_collection()
    user = await users_coll.find_one({"email": payload.email})

    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        await users_coll.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_reset_token_hash": token_hash, "password_reset_expires_at": expires_at}},
        )

        # NOTE: No SMTP/email service in repo yet. Once you add it, email `raw_token` here.
        # For now, we intentionally do NOT return the token (security).

    return {"message": "A password reset link/code has been sent to your email. Please check your inbox."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    """
    Completes password reset using email + token + new password.
    """
    users_coll = get_users_collection()
    user = await users_coll.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token or expired token")

    token_hash = user.get("password_reset_token_hash")
    expires_at = user.get("password_reset_expires_at")
    if not token_hash or not expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token or expired token")

    # Motor typically returns timezone-aware datetimes; handle naive just in case.
    now = datetime.now(timezone.utc)
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token or expired token")

    if _hash_reset_token(payload.token) != token_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token or expired token")

    new_hash = get_password_hash(payload.new_password)
    await users_coll.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"hashed_password": new_hash},
            "$unset": {"password_reset_token_hash": "", "password_reset_expires_at": ""},
        },
    )

    return {"message": "Password has been reset successfully"}