import os
from time import timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, status,  UploadFile, File, Form
from typing import List, Optional

from fastapi.encoders import jsonable_encoder
from core.security import get_current_user, get_current_user_email, get_password_hash
from core.database import get_database, get_embedding_vector, get_plans_collection, get_settings_collection, get_subscriptions_collection, get_token_usage_collection, get_users_collection, get_documents_collection, get_knowledge_base_collection
from models.domain import ContentLibraryResponse, ContentLibraryStats, DocumentOut, DocumentStatus, PlanCreate, PlanResponse, SubscriptionResponse, SubscriptionTier, SystemSettings, UserAdminUpdate, UserBase, UserSettingsResponse, UserStatus
from fastapi import UploadFile, File
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from services.ingestion.pdf_engine import PDFManager
import io
from bson.errors import InvalidId
from services.ingestion.pdf_engine import PDFManager
from dotenv import load_dotenv
load_dotenv()
router = APIRouter()

async def admin_required(current_user: str = Depends(get_current_user_email)):
    """Dependency to check if the current user has administrative privileges."""
    users_coll = get_users_collection()
    user = await users_coll.find_one({"email": current_user})
    
    if not user or not user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have administrative privileges to access this resource."
        )
    return current_user
def pydantic_dict(doc):
    """Converts MongoDB _id to string id for Pydantic models."""
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

# --------------------------------------------------------------------------------------------------------------------
# overview endpoint ----------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------


@router.get("/admin/overview", dependencies=[Depends(admin_required)])
async def get_admin_overview(current_admin: str = Depends(admin_required)):
    """Retrieves high-level statistics for the admin dashboard overview."""
    
    users_coll = get_users_collection()
    docs_coll = get_documents_collection()
    # Assuming you have a collection tracking token usage per user
    knowledge_coll = get_knowledge_base_collection() 
    print("Fetching admin overview stats...")
    # 1. Basic Counts
    total_users = await users_coll.count_documents({})
    total_docs = await docs_coll.count_documents({})
    print(f"Total users: {total_users}, Total documents: {total_docs}")
    # 2. Subscription Stats (if applicable)
    active_subs = await users_coll.count_documents({"subscription_status": "active"})



    # 3. revenue pipeline: We filter for active users and sum their plan prices
    revenue_pipeline = [
        {"$match": {"subscription_status": "active"}},
        {"$group": {
            "_id": None, 
            "total_rev": {"$sum": "$plan_price"}
        }}
    ]
    revenue_cursor = users_coll.aggregate(revenue_pipeline)
    revenue_result = await revenue_cursor.to_list(1)
    total_revenue = revenue_result[0]["total_rev"] if revenue_result else 0

    # 3. Aggregate Usage (Summing up total tokens used across system)
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$tokens_used"}}}]
    usage_cursor = users_coll.aggregate(pipeline) # Or your specific usage collection
    usage_result = await usage_cursor.to_list(1)
    total_tokens = usage_result[0]["total"] if usage_result else 0

    # 4. Monthly Growth Data (Aggregate user sign ups by date for a chart)
    seven_days_ago = datetime.now() - timedelta(days=7)
    growth_pipeline = [
        {"$match": {"created_at": {"$gte": seven_days_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    growth_cursor = users_coll.aggregate(growth_pipeline)
    growth_raw = await growth_cursor.to_list(100)
    growth_data = [{"date": d["_id"], "count": d["count"]} for d in growth_raw]

    return {
        "total_users": total_users,
        "total_documents": total_docs,
        "active_subscriptions": active_subs,
        "total_tokens_used": total_tokens,
        "growth_data": growth_data, 
        "total_revenue": round(total_revenue, 2)
    }




@router.get("/admin/overview/subscriptions")
async def get_subscription_breakdown(current_admin: str = Depends(admin_required)):
    """Returns the count of users for every subscription tier."""
    users_coll = get_users_collection()
    
    pipeline = [
        {"$group": {
            "_id": "$subscription_tier", 
            "count": {"$sum": 1}
        }}
    ]
    
    cursor = users_coll.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    # Format for frontend charts
    return {str(res["_id"] or "Unknown"): res["count"] for res in results}



@router.get("/admin/recent-activity", response_model=List[dict])
async def get_recent_activity(current_admin: str = Depends(admin_required)):
    """Returns the 5 most recent system events for the dashboard feed."""
    docs_coll = get_documents_collection()
    
    # Fetch 5 most recent documents as a proxy for activity
    recent_docs = await docs_coll.find().sort("uploaded_at", -1).limit(5).to_list(5)
    
    return [pydantic_dict(doc) for doc in recent_docs]






# --------------------------------------------------------------------------------------------------------------------
# user management endpoints -----------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------

# This endpoint retrieves all users in chunks to ensure the admin panel remains fast even with thousands of users.
@router.get("/admin/users", response_model=List[UserBase])
async def list_admin_users(
    skip: int = 0, 
    limit: int = 20, 
    status: Optional[UserStatus] = None, # Added status filter
    plan: Optional[SubscriptionTier] = None, # Added plan filter
    current_admin: str = Depends(admin_required)
):
    """Retrieves a paginated list of all registered users."""
    users_coll = get_users_collection()

    # Build a dynamic filter
    query = {}
    if status:
        query["status"] = status
    if plan:
        query["subscription_tier"] = plan

   # FIX: Pass the 'query' variable into the find() method
    cursor = users_coll.find(query).skip(skip).limit(limit) 
    users = await cursor.to_list(length=limit)
    return [pydantic_dict(u) for u in users]


#  Admins frequently need to find users by email, name, or specific status (e.g., finding all "banned" users).
@router.get("/admin/users/search", response_model=List[UserBase])
async def search_users(
    query: str, 
    status: Optional[str] = None,
    current_admin: str = Depends(admin_required)
):
    """Search for users by email or name with optional status filtering."""
    users_coll = get_users_collection()
    
    # Simple regex search for email or username
    filter_query = {
        "$or": [
            {"email": {"$regex": query, "$options": "i"}},
            {"full_name": {"$regex": query, "$options": "i"}}
        ]
    }
    
    if status:
        filter_query["status"] = status
        
    cursor = users_coll.find(filter_query).limit(50)
    users = await cursor.to_list(length=50)
    return [pydantic_dict(u) for u in users]


# This retrieves the full record for a specific user to be displayed in a "User Details" modal.
@router.get("/admin/users/{user_id}", response_model=UserBase)
async def get_user_by_id(user_id: str, current_admin: str = Depends(admin_required)):
    """Fetch full details for a single user by their unique ID."""
    users_coll = get_users_collection()
    user = await users_coll.find_one({"_id": ObjectId(user_id)})
    
    try:
        # Convert string ID to MongoDB ObjectId
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    # The query MUST be {"_id": obj_id}
    user = await users_coll.find_one({"_id": obj_id})
    
    if not user:
        raise HTTPException(status_code=404, detail="User record not found")
        
    return pydantic_dict(user)


@router.post("/add/newuser") # Naya user hai toh POST use karenge
async def create_new_user_admin(
    full_name: str = Form(...),       # Required
    email: str = Form(...),                # Required
    plan: str = Form("Free"),         # Default: Free
    account_status: str = Form("Active"),     # Default: Active
    inititial_tokens_amount: int = Form(0),  # Default: 0
    current_admin: dict = Depends(admin_required)
):
    users_coll = get_users_collection()

    # 1. Check karein user pehle se toh nahi hai
    existing_user = await users_coll.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    # 2. Plan ke hisaab se tokens set karein
    tokens_map = {
        "Free": 10000,
        "Pro": 100000,
        "Enterprise": 500000
    }
    initial_tokens = tokens_map.get(plan, 10000)

    # 3. New User Object 
    new_user = {
        "full_name": full_name,
        "email": email,
        "plan": plan,
        "tokens_remaining": initial_tokens,
        "account_status": account_status,
        "initial_tokens_amount": inititial_tokens_amount
    }

    # 4. Database mein insert karein
    result = await users_coll.insert_one(new_user)
    
    return {
        "status": "success", 
        "message": "New user created successfully",
        "user_id": str(result.inserted_id),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }

# These endpoints allow you to take direct action on an account, such as banning a user or promoting them to an administrator.
@router.patch("/users/{user_id}/status")
async def update_user_account_status(
    user_id: str, 
    new_status: UserStatus, # Using the Enum here auto-validates the input
    current_admin: str = Depends(admin_required)
):
    users_coll = get_users_collection()

    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    
    # .value gets the string "Active" or "Banned" from the Enum
    result = await users_coll.update_one(
        {"_id": obj_id}, 
        {"$set": {"status": new_status.value, "updated_at": datetime.now(timezone.utc)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {"message": f"User status updated to {new_status.value}"}



@router.patch("/users/{user_id}/permissions")
async def toggle_admin_privileges(
    user_id: str, 
    is_admin: bool,
    current_admin: str = Depends(admin_required)
):
    users_coll = get_users_collection()
    
    try:
        obj_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    # Optional: Prevent self-demotion
    # if not is_admin and str(obj_id) == str(current_admin_id_logic_here):
    #    raise HTTPException(status_code=400, detail="Cannot demote yourself")

    result = await users_coll.update_one(
        {"_id": obj_id}, 
        {"$set": {"is_admin": is_admin}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
        
    status_text = "promoted to admin" if is_admin else "demoted to user"
    return {"message": f"User successfully {status_text}"}

# # In some cases, an admin may need to permanently remove a user account.
# @router.delete("/users/{user_id}")
# async def delete_user_account(user_id: str, current_admin: str = Depends(admin_required)):
#     """Permanently delete a user account from the system."""
#     users_coll = get_users_collection()
    
#     try:
#         obj_id = ObjectId(user_id)
#     except InvalidId:
#         raise HTTPException(status_code=400, detail="Invalid User ID format")

#     await users_coll.users.delete_one({"_id": ObjectId(user_id)})
#     await users_coll.subscriptions.delete_many({"user_id": user_id})
#     await users_coll.token_usage.delete_many({"user_id": user_id})
    
#     return {"message": "User deleted successfully"}



# action buttons endpoints for user management ----------------------------------------------------------------
# 1. GET Single User Details (Edit Popup ke liye)
@router.get("/actions/{user_id}")
async def get_user_for_edit(user_id: str, admin: dict = Depends(admin_required)):
    collection = get_users_collection()
    try:
        # Pehle ObjectId se search karein
        user = await collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            # Agar nahi mila toh string ID se search karein
            user = await collection.find_one({"_id": user_id})
    except:
        # Agar conversion fail ho toh direct string search
        user = await collection.find_one({"_id": user_id})

    if not user:
        raise HTTPException(status_code=404, detail="User records not found in database")
    user["_id"] = str(user["_id"])
    return user

# 2. UPDATE User (Edit Save karne par)
@router.patch("/actions/edit/{user_id}")
async def update_user_admin(user_id: str, update_data: UserAdminUpdate, admin: dict = Depends(admin_required)):
    collection = get_users_collection()
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="no update data provided")

    # FIX: user_id ko ObjectId() mein wrap karein
    try:
        query_id = ObjectId(user_id)
    except:
        # Agar conversion fail ho toh direct string use karein (backup)
        query_id = user_id

    result = await collection.update_one(
        {"_id": query_id}, 
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        # Ab ye error tabhi aayega jab sach mein wo ID DB mein na ho
        raise HTTPException(status_code=404, detail="user update failed - ID not found")
        
    return {"status": "success", "message": "User details updated successfully"}

# 3. DELETE User (Delete Action)
@router.delete("/actions/delete/{user_id}")
async def delete_user_admin(user_id: str, admin: dict = Depends(admin_required)):
    collection = get_users_collection()
    admin_id = admin.get("_id") if isinstance(admin, dict) else admin
    # Security Check: Admin khud ko delete na kar le
    if user_id == str(admin_id):
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    # 2. Convert string ID to MongoDB ObjectId for the query
    try:
        query_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    result = await collection.delete_one({"_id": query_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User deletion failed - User not found")
        
    return {"status": "success", "message": "User permanently deleted"}



# ---------------------------------------------------------------------------------------------------------------
# subscription management endpoints -------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------


# This endpoint powers the four top cards in our UI: Total Subscriptions, Active, Monthly Revenue, and Cancelled.

@router.get("/subscriptions/stats")
async def get_subscription_stats(current_admin: str = Depends(admin_required)):
    """Fetch metrics for the Subscription Management header cards."""
    users_coll = get_users_collection() # Assuming sub info is in user or separate coll
    
    # 1. Counts for the cards
    total_subs = await users_coll.count_documents({"subscription_plan": {"$ne": "free"}})
    active_subs = await users_coll.count_documents({"subscription_status": "Active"})
    cancelled_subs = await users_coll.count_documents({"subscription_status": "Cancelled"})
    
    # 2. Monthly Revenue (Sum of prices of all 'Active' subscriptions)
    pipeline = [
        {"$match": {"subscription_status": "Active"}},
        {"$group": {"_id": None, "revenue": {"$sum": "$plan_price"}}}
    ]
    revenue_res = await users_coll.aggregate(pipeline).to_list(1)
    monthly_revenue = revenue_res[0]["revenue"] if revenue_res else 0.0

    return {
        "total_subscriptions": total_subs,
        "active": active_subs,
        "monthly_revenue": round(monthly_revenue, 2),
        "cancelled": cancelled_subs
    }


# This endpoint handles the search bar and the "All Statuses" dropdown filter in the Subscriptions tab.

@router.get("/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    current_admin: str = Depends(admin_required)
):
    # 1. Change to the correct collection
    subs_coll = get_subscriptions_collection() 
    
    query = {}
    
    # 2. Match the search to your document structure
    if search:
        # Assuming subscriptions collection has 'user_email' or 'plan_name'
        query["$or"] = [
            {"user_email": {"$regex": search, "$options": "i"}},
            {"plan_name": {"$regex": search, "$options": "i"}}
        ]

    # 3. Use the correct date field from your screenshot: 'created_at'
    cursor = subs_coll.find(query).sort("created_at", -1).skip(skip).limit(limit)
    subs = await cursor.to_list(length=limit)
    
    return [
        {
            "id": str(s["_id"]),
            "user_email": s.get("user_email"),
            "plan_name": s.get("plan_name"), # This matches your 'name' field in plans
            "price": s.get("price", 0.0),
            "status": s.get("status", "Active"),
            "start_date": s.get("created_at"), # From your screenshot
            "end_date": s.get("end_date"),
            "auto_renew": s.get("auto_renew", True)
        } for s in subs
    ]


# If you want to automate this, you need a "Checkout" or "Assign Plan" endpoint. Here is a simple version for an Admin to manually assign a plan to a user:
@router.post("/subscriptions/assign")
async def assign_subscription(user_email: str, plan_id: str, current_admin: str = Depends(admin_required)):
    subs_coll = get_subscriptions_collection()
    plans_coll = get_plans_collection() # Collection from your screenshot
    
    # 1. Fetch the plan details
    plan = await plans_coll.find_one({"_id": ObjectId(plan_id)})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # 2. Create the subscription record
    new_sub = {
        "user_email": user_email,
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "price": plan["price"],
        "status": "Active",
        "created_at": datetime.now(timezone.utc),
        "auto_renew": True
    }
    
    await subs_coll.insert_one(new_sub)
    return {"message": f"Plan '{plan['name']}' assigned to {user_email}"}




# To make the "Actions" column functional, you'll need endpoints to manually cancel or extend a user's plan.

@router.post("/subscriptions/{sub_id}/cancel")
async def admin_cancel_subscription(sub_id: str, current_admin: str = Depends(admin_required)):
    """Admin override to cancel a user's subscription."""
    # 1. Use the correct collection based on your DB sidebar
    subs_coll = get_subscriptions_collection() 
    
    try:
        # 2. Convert string to ObjectId
        obj_id = ObjectId(sub_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid Subscription ID format")

    # 3. Query the field "_id", not "id"
    result = await subs_coll.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "Cancelled", # Match the field name used in your assignment logic
            "auto_renew": False,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subscription record not found")
        
    return {"message": "Subscription cancelled successfully"}

# --------------------------------------------------------------------------------------
# plan management endpoints ------------------------------------------------------
# ------------------------------------------------------------------------------------

@router.post("/plans/create", dependencies=[Depends(admin_required)])
async def create_plan(plan: PlanCreate):
    collection = get_plans_collection()
    
    plan_dict = plan.model_dump()
    plan_dict["_id"] = str(uuid.uuid4())
    plan_dict["created_at"] = datetime.now(timezone.utc)
    
    await collection.insert_one(plan_dict)
    return {"status": "success", "message": "Plan created successfully", "plan_id": plan_dict["_id"]}

@router.get("/plans/all", dependencies=[Depends(admin_required)])
async def get_all_plans():
    collection = get_plans_collection()

    plans = await collection.find().sort("created_at", -1).to_list(length=100)
    
    # ERROR FIX: ObjectId ko string mein convert karein
    for plan in plans:
        if "_id" in plan:
            plan["_id"] = str(plan["_id"])
            
    return jsonable_encoder(plans)

# edit any plan endpoint

@router.patch("/edit/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    name: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    admin: dict = Depends(admin_required)
):
    collection = get_plans_collection()
    
    # Data collect karein
    update_data = {}
    if name: update_data["name"] = name
    if price is not None: update_data["price"] = price
    if description: update_data["description"] = description
    if is_active is not None: update_data["is_active"] = is_active

    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")

    try:
        query_id = ObjectId(plan_id)
    except:
        query_id = plan_id

    result = await collection.update_one({"_id": query_id}, {"$set": update_data})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plan not found")

    return {"status": "success", "message": "Plan updated successfully"}

# delete any plan endpoint
@router.delete("/delete/plans/{plan_id}")
async def delete_plan(
    plan_id: str, 
    admin: dict = Depends(admin_required)
):
    collection = get_plans_collection()
    
    try:
        query_id = ObjectId(plan_id)
    except:
        query_id = plan_id

    result = await collection.delete_one({"_id": query_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Plan deletion failed - ID not found")
        
    return {"status": "success", "message": "Plan deleted successfully"}

# ---------------------------------------------------------------------------------------------------------------------
# token usage analysis endpoints ------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------


# To handle the "Last X Days" dropdown, we first need a helper function to calculate the date threshold.

def get_timeframe_start(days: int) -> datetime:
    """Calculates the start date based on the selected timeframe."""
    # Use now(timezone.utc) instead of utcnow()
    return datetime.now(timezone.utc) - timedelta(days=days)


# This endpoint powers the Total Tokens, Avg Daily Tokens, and Active Users Today cards. It uses MongoDB's aggregation to sum usage over the specific period.
@router.get("/token-usage/stats")
async def get_token_usage_analytics(
    days: int = 7, 
    current_admin: str = Depends(admin_required)
):
    """Fetches high-level token analytics and graph data based on timeframe."""
    usage_coll = get_token_usage_collection()
    start_date = get_timeframe_start(days)

    # 1. Aggregate Total Tokens for the period
    usage_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": None,
            "total_tokens": {"$sum": "$tokens_used"},
            "avg_tokens": {"$avg": "$tokens_used"}
        }}
    ]
    usage_stats = await usage_coll.aggregate(usage_pipeline).to_list(1)
    
    total = usage_stats[0]["total_tokens"] if usage_stats else 0
    avg = usage_stats[0]["avg_tokens"] if usage_stats else 0

    # 2. Daily Usage Graph Data
    graph_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "count": {"$sum": "$tokens_used"}
        }},
        {"$sort": {"_id": 1}}
    ]
    graph_raw = await usage_coll.aggregate(graph_pipeline).to_list(days)
    
    # 3. Usage by Plan
    plan_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$plan_type",
            "value": {"$sum": "$tokens_used"}
        }}
    ]
    plan_usage = await usage_coll.aggregate(plan_pipeline).to_list(5)

    # FIXED: Wrap await in parentheses before calling len()
    active_users_list = await usage_coll.distinct("user_email", {"timestamp": {"$gte": get_timeframe_start(1)}})
    
    return {
        "header": {
            "total_tokens": total,
            "avg_daily": round(avg, 2),
            "active_users_today": len(active_users_list) # Use the resolved list
        },
        "daily_usage": [{"date": d["_id"], "tokens": d["count"]} for d in graph_raw],
        "usage_by_plan": [{"plan": p["_id"] or "Unknown", "tokens": p["value"]} for p in plan_usage]
    }


# it will allow you to wipe your test data easily once you are ready to transition from development to real usage.
@router.delete("/test/clear-token-logs")
async def clear_token_logs(current_admin: str = Depends(admin_required)):
    """Wipes the token_usage_logs collection for a clean slate."""
    usage_coll = get_database()["token_usage_logs"]
    
    # Delete all documents in the collection
    result = await usage_coll.delete_many({})
    
    return {
        "message": "Token logs cleared successfully",
        "deleted_count": result.deleted_count
    }


# This endpoint populates the "Top Users" table at the bottom of your UI, ranking users by their consumption.
@router.get("/token-usage/top-users", response_model=List[dict])
async def get_top_token_users(
    days: int = 7,
    limit: int = 10,
    current_admin: str = Depends(admin_required)
):
    """Ranks users by their token consumption for the selected period."""
    usage_coll = get_token_usage_collection()
    start_date = get_timeframe_start(days)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$user_email",
            "tokens_used": {"$sum": "$tokens_used"},
            "plan": {"$first": "$plan_type"} # Get the plan associated with the user
        }},
        {"$sort": {"tokens_used": -1}},
        {"$limit": limit}
    ]
    
    results = await usage_coll.aggregate(pipeline).to_list(limit)
    
    # Formatting for UI Table with Rank
    return [
        {
            "rank": i + 1,
            "user": res["_id"],
            "plan": res["plan"],
            "tokens_used": res["tokens_used"],
            "usage_percentage": 0 # Logic to calculate vs total if needed
        } for i, res in enumerate(results)
    ]


# -----------------------------------------------------------------------------------------------------------
# Content Library Management Endpoints-----------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------

@router.get("/content-library/stats", response_model=ContentLibraryStats)
async def get_library_stats(current_admin: str = Depends(admin_required)):
    """Fetches high-level metrics for the Content Library cards."""
    docs_coll = get_documents_collection()
    
    total = await docs_coll.count_documents({})
    processed = await docs_coll.count_documents({"status": DocumentStatus.PROCESSED})
    processing = await docs_coll.count_documents({"status": DocumentStatus.PROCESSING})
    
    # Aggregation for total chunks across all documents
    pipeline = [{"$group": {"_id": None, "total_chunks": {"$sum": "$chunk_count"}}}]
    cursor = docs_coll.aggregate(pipeline)
    result = await cursor.to_list(1)
    total_chunks = result[0]["total_chunks"] if result else 0

    return {
        "total_documents": total,
        "processed": processed,
        "processing": processing,
        "total_chunks": total_chunks
    }

@router.get("/show/documents", response_model=List[ContentLibraryResponse])
async def get_content_library(admin: dict = Depends(admin_required)):
    kb_coll = get_knowledge_base_collection()
    
    # Hum unique pdf_id par group karenge kyunki ek file ke kayi chunks hote hain
    pipeline = [
        {
            "$group": {
                "_id": "$pdf_id", 
                "title": {"$first": "$document_name"},
                "upload_date": {"$first": "$timestamp"},
                "chunks_count": {"$sum": 1}
            }
        },
        {"$sort": {"upload_date": -1}}
    ]
    
    cursor = kb_coll.aggregate(pipeline)
    docs = await cursor.to_list(length=100)
    
    formatted_docs = []
    for doc in docs:
        if doc["_id"]:  # Bogus data filter karne ke liye
            formatted_docs.append({
                "id": str(doc["_id"]),
                "title": doc.get("title", "Untitled Document"),
                "file_name": doc.get("title", "file.pdf"),
                "file_type": "PDF",
                "size": "N/A", 
                "upload_date": doc.get("upload_date") or datetime.now(timezone.utc),
                "status": "ready", # Knowledge Base mein hai matlab ready hai
                "chunks": doc.get("chunks_count", 0)
            })
    return formatted_docs


@router.post("/content-library/upload")
async def upload_admin_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    admin: str = Depends(admin_required)
):
    # Temp file save karo processing ke liye
    file_content = await file.read()
    temp_path = f"temp_{int(datetime.now().timestamp())}_{file.filename}"
    
    with open(temp_path, "wb") as f:
        f.write(file_content)

    try:
        pdf_manager = PDFManager()
        # save_to_mongo function hi knowledge_base collection mein data daal raha hai
        # Ensure pdf_manager.save_to_mongo returns the number of chunks
        chunks_created = await pdf_manager.save_to_mongo_and_qdrant(temp_path, title)
        
        os.remove(temp_path) # Cleanup
        return {"message": "Knowledge Base updated", "chunks": chunks_created}

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Processing Error: {str(e)}")
    
@router.delete("/delete/documents/{pdf_id}")
async def delete_kb_document(pdf_id: str, current_admin: str = Depends(admin_required)):
    kb_coll = get_knowledge_base_collection()
    
    # Knowledge base se us pdf_id ke saare chunks delete karo
    result = await kb_coll.delete_many({"pdf_id": pdf_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found in Knowledge Base")

    return {
        "message": "Document removed from Knowledge Base",
        "chunks_deleted": result.deleted_count
    }

@router.delete("/delete/documents/{doc_id}")
async def delete_document(doc_id: str, current_admin: str = Depends(admin_required)):
    """Permanently removes document metadata and all associated vector chunks."""
    docs_coll = get_documents_collection()
    kb_coll = get_knowledge_base_collection()
    
    # Delete from 'documents'
    await docs_coll.delete_one({"_id": ObjectId(doc_id)})
    
    # Delete all associated chunks from 'knowledge_base'
    await kb_coll.delete_many({"document_id": doc_id})
    
    return {"message": "Document and knowledge base entries deleted successfully."}


# to show uploaded documents in admin content library page
@router.get("/show/documents", response_model=List[ContentLibraryResponse])
async def get_content_library(admin: dict = Depends(admin_required)):
    collection = get_knowledge_base_collection()
    
    # Hum saare unique pdf_id ke basis par documents nikalenge
    # Taki table mein duplicates na aayein (kyunki ek PDF ke many chunks hote hain)
    pipeline = [
        {
            "$group": {
                "_id": "$pdf_id",
                "title": {"$first": "$document_name"},
                "file_name": {"$first": "$document_name"}, # Agar alag field hai toh wo use karein
                "upload_date": {"$first": "$timestamp"},
                "chunks_count": {"$sum": 1}
            }
        },
        {"$sort": {"upload_date": -1}} # Naye files upar dikhane ke liye
    ]
    
    cursor = collection.aggregate(pipeline)
    docs = await cursor.to_list(length=100)
    
    formatted_docs = []
    for doc in docs:
        formatted_docs.append({
            "id": str(doc["_id"]),
            "title": doc["title"],
            "file_name": doc["file_name"],
            "file_type": "PDF", # Default PDF kyunki OCR pdf se ho raha hai
            "size": "N/A", # Agar aapne file size save kiya hai toh wo yahan aayega
            "upload_date": doc["upload_date"],
            "status": "Processed", # Chunks mil gaye matlab process ho gaya
            "chunks": doc["chunks_count"]
        })
        
    return formatted_docs

# -------------------------------------------------------------------------------------------------------------------
# ---------------------------------------------System Settings Endpoints ---------------------------------------------
# --------------------------------------------------------------------------------------------------------------------


# This endpoint retrieves the document where type is "admin".
@router.get("/settings", response_model=SystemSettings)
async def get_admin_settings(current_admin: str = Depends(admin_required)):
    """Retrieves the global system settings from MongoDB."""
    settings_coll = get_settings_collection()
    
    # Find the single admin settings document
    settings_doc = await settings_coll.find_one({"type": "admin"})
    
    if not settings_doc:
        # Return default values if no settings document exists yet
        return {
            "siteName": "Juristway AI",
            "siteUrl": "https://juristwayai.com",
            "supportEmail": "support@juristwayai.com",
            "geminiApiKey": "",
            "openaiApiKey": "",
            "maxTokensPerRequest": 4000,
            "emailNotifications": True,
            "newUserEmail": True,
            "subscriptionEmail": True,
            "enableTwoFactor": False,
            "sessionTimeout": 30,
            "maxLoginAttempts": 5,
            "backupEnabled": True,
            "backupFrequency": "daily",
            "dataRetention": 90
        }
    
    return pydantic_dict(settings_doc)


# This endpoint handles the "Save Changes" button. It uses an upsert (Update or Insert) operation to ensure the "admin" settings document is updated in the MongoDB cluster.
@router.post("/settings/save")
async def save_admin_settings(
    payload: SystemSettings, 
    current_admin: str = Depends(admin_required)
):
    """Updates the global system settings in the MongoDB 'settings' collection."""
    settings_coll = get_settings_collection()
    
    # Convert Pydantic model to dictionary
    settings_data = payload.model_dump()
    settings_data["updated_at"] = datetime.now(timezone.utc)
    settings_data["type"] = "admin" # Ensure the document type stays consistent

    # Use find_one_and_update with upsert=True
    result = await settings_coll.find_one_and_update(
        {"type": "admin"},
        {"$set": settings_data},
        upsert=True,
        return_document=True
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to save settings.")

    return {"message": "Settings updated successfully in MongoDB cluster."}


# to show user settings in user profile page
@router.get("/user/settings", response_model=UserSettingsResponse)
async def get_user_settings(current_user: dict = Depends(get_current_user)):
    """
    User ki profile settings fetch karne ka endpoint
    """
    collection = get_users_collection()
    
    # DB se user ka fresh data nikalenge (Email/ID ke base par)
    user_data = await collection.find_one({"email": current_user["email"]})
    
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    # Frontend screenshot ke mapping ke hisaab se data return karein
    return {
        "name": user_data.get("full_name") or user_data.get("name", "User"),
        "email": user_data.get("email"),
        "notifications_enabled": user_data.get("notifications_enabled", True),
        "version": "1.0.0" # Ye hardcoded ya config se aa sakta hai
    }