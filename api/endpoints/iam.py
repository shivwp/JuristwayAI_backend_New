import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from models.domain import UserBase
from core.security import get_password_hash
from core.database import get_users_collection
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
import os 
from dotenv import load_dotenv
load_dotenv()
# Initialize logger for this specific module
logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_REGISTRATION_KEY = os.getenv("SECRET_KEY")

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    admin_secret: Optional[str] = None

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    logger.info(f"Signup attempt for email: {user_data.email}")
    users_collection = get_users_collection()

    print("--- Step 1: About to query DB ---")
    
    # 1. Check if user already exists

    existing_user = await users_collection.find_one({"email": user_data.email})
    print("--- Step 2: DB Query finished ---")
    if existing_user:
        logger.warning(f"Signup failed: User {user_data.email} already exists.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )
    
    # --- ADMIN CHECK LOGIC ---
    is_admin = False
    if user_data.admin_secret:
        if user_data.admin_secret == ADMIN_REGISTRATION_KEY:
            is_admin = True
            logger.info(f"Granting admin privileges to: {user_data.email}")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin secret key."
            )
    # --------------------------

    # 2. Hash the password
    hashed_password = get_password_hash(user_data.password)
    
    # 3. Prepare the document for MongoDB
    new_user = {
        "email": user_data.email,
        "full_name": user_data.full_name,
        "hashed_password": hashed_password,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "is_admin": is_admin
    }
    
    # 4. Insert into database
    try:
        await users_collection.insert_one(new_user)
        logger.info(f"User created successfully: {user_data.email} (Admin: {is_admin})")
    except Exception as e:
        logger.error(f"Database error during signup for {user_data.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration."
        )
    
    return {
        "message": "User created successfully", 
        "email": user_data.email, 
        "role": "admin" if is_admin else "user"
    }