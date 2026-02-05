from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, EmailStr
from typing import Optional, Annotated, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
from dotenv import load_dotenv
from sympy import Union
load_dotenv()
# Custom Type for MongoDB ObjectIDs
PyObjectId = Annotated[str, BeforeValidator(str)]

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None   # Optional chat/thread ID

class ChatResponse(BaseModel):
    message: str | list[Any]
    chat_id: str
    timestamp: datetime

# --- ENUMS (Ensures consistency between DB and Admin UI) ---

class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None # "admin" ya "user"
    is_active: Optional[bool] = None
    plan_id: Optional[str] = None # Plan change karne ke liye

class UserStatus(str, Enum):
    ACTIVE = "Active"
    BANNED = "Banned"
    PENDING = "Pending"
    INACTIVE = "Inactive"

class SubscriptionStatus(str, Enum):
    ACTIVE = "Active"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"
    FAILED = "Failed"

class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class DocumentStatus(str, Enum):
    PROCESSING = "Processing"
    PROCESSED = "Processed"
    FAILED = "Failed"

# --- USER & AUTH MODELS ---

class UserBase(BaseModel):
    id: str = Field(alias="_id")
    email: EmailStr
    full_name: Optional[str] = None
    is_admin: bool = False
    status: UserStatus = UserStatus.ACTIVE
    subscription_tier: SubscriptionTier = SubscriptionTier.FREE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(
        populate_by_name=True, # Taki hum 'id' aur '_id' dono use kar sakein
        from_attributes=True)
# --- DASHBOARD & OVERVIEW MODELS ---

class AdminOverview(BaseModel):
    total_users: int
    total_documents: int
    active_subscriptions: int
    total_tokens_used: int
    growth_data: List[Dict[str, Any]] # e.g., [{"date": "2024-01-01", "count": 10}]
    total_revenue: float

# --- TOKEN USAGE ANALYSIS MODELS (New for Usage Tab) ---
class TokenData(BaseModel):
    email: Optional[str] = None
    
class UsageHeaderStats(BaseModel):
    total_tokens: int
    avg_daily: float
    active_users_today: int

class UsageGraphPoint(BaseModel):
    date: str
    tokens: int

class PlanUsagePie(BaseModel):
    plan: str
    tokens: int

class TopUserUsage(BaseModel):
    rank: int
    user: str
    plan: str
    tokens_used: int
    usage_percentage: float = 0.0

class TokenUsageAnalyticsResponse(BaseModel):
    header: UsageHeaderStats
    daily_usage: List[UsageGraphPoint]
    usage_by_plan: List[PlanUsagePie]

# --- CONTENT LIBRARY MODELS ---

class ContentLibraryStats(BaseModel):
    total_documents: int
    processed: int
    processing: int
    total_chunks: int

class DocumentOut(BaseModel):
    id: str = Field(alias="_id")
    title: str
    file_name: str
    type: str  # PDF, DOCX, TXT
    size: str
    uploaded_at: datetime
    status: DocumentStatus
    chunk_count: int

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

class ContentLibraryResponse(BaseModel):
    id: str = Field(alias="_id")
    title: str
    file_name: str
    file_type: str
    size: str  # e.g., "2.4 MB"
    upload_date: datetime
    status: str  # e.g., "Processed", "Processing", "Failed"
    chunks: int

class KnowledgeBaseEntry(BaseModel):
    document_id: str = Field(alias="_id")
    text: str
    embedding: List[float] # Specifically for the 768-dim vectors
    metadata: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# --- SUBSCRIPTION MODELS ---

class SubscriptionResponse(BaseModel):
    id: str = Field(alias="_id") # Ensure this is 'id', NOT '_id'
    user_email: str
    plan_name: str
    price: float
    status: SubscriptionStatus
    start_date: datetime
    end_date: Optional[datetime] = None
    auto_renew: bool = True

    

class PlanBase(BaseModel):
    name: str
    description: str
    price: float
    interval: str = ["monthly", "yearly"]  # monthly or yearly
    tokens: int
    features: List[str]
    is_active: bool = True

class PlanCreate(PlanBase):
    pass

class PlanResponse(PlanBase):
    id: str = Field(alias="_id")
    created_at: datetime

# --- SYSTEM SETTINGS MODELS ---

class SystemSettings(BaseModel):
    # General Settings
    siteName: str = "Juristway AI"
    siteUrl: str = ""
    supportEmail: EmailStr
    
    # API Settings
    geminiApiKey: str
    openaiApiKey: str
    maxTokensPerRequest: int = 4000
    
    # Email Notifications
    emailNotifications: bool = True
    newUserEmail: bool = True
    subscriptionEmail: bool = True
    
    # Security Settings
    enableTwoFactor: bool = False
    sessionTimeout: int = 30
    maxLoginAttempts: int = 5
    
    # Database Settings
    backupEnabled: bool = True
    backupFrequency: str = "Daily"
    dataRetention: int = 90
    
    updated_at: Optional[datetime] = None


class UserSettingsResponse(BaseModel):
    name: str
    email: EmailStr
    notifications_enabled: bool = True
    version: str = "1.0.0"
    # Additional flags agar zaroorat ho
    is_premium: bool = False