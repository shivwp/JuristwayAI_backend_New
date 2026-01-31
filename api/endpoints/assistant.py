from typing import List
from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from core.database import get_chats_collection
from core.security import get_current_active_user
from models.domain import ChatRequest, ChatResponse
from services.agent.brain import run_juristway_ai
from dotenv import load_dotenv
load_dotenv()
router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def send_message(
    chat_request: ChatRequest,
    current_user: dict = Depends(get_current_active_user)
):
    chats_collection = get_chats_collection()
    user_id = str(current_user["_id"])
    now = datetime.now(timezone.utc)
    
    # 1. SESSION / CHAT RETRIEVAL
    if chat_request.chat_id:
        chat_doc = await chats_collection.find_one({"_id": ObjectId(chat_request.chat_id)})
        if not chat_doc or str(chat_doc["user_id"]) != user_id:
            raise HTTPException(status_code=404, detail="Chat not found")
    else:
        # Create new chat session if no ID provided
        new_chat = {
            "user_id": user_id,
            "title": chat_request.message[:50] + "..." if len(chat_request.message) > 50 else chat_request.message,
            "messages": [],
            "created_at": now,
            "updated_at": now
        }
        result = await chats_collection.insert_one(new_chat)
        chat_doc = new_chat
        chat_doc["_id"] = result.inserted_id

    session_id = str(chat_doc["_id"])

    # 2. GET AI RESPONSE (Orchestrator handles Redis + RAG)
    ai_data = await run_juristway_ai(
        query=chat_request.message, 
        thread_id=session_id
    )

    # 3. MESSAGE FORMATTING & PERSISTENCE
    user_msg_entry = {
        "role": "user", 
        "content": chat_request.message, 
        "timestamp": now
    }
    
    # Add link to UI response if found
    display_content = ai_data["answer"]
    if ai_data.get("link"):
        display_content += f"\n\n[Reference Document]({ai_data['link']})"

    assistant_msg_entry = {
        "role": "assistant",
        "content": display_content,
        "source": ai_data["source"],
        "timestamp": datetime.now(timezone.utc)
    }
    
    await chats_collection.update_one(
        {"_id": chat_doc["_id"]},
        {
            "$push": {"messages": {"$each": [user_msg_entry, assistant_msg_entry]}},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )

    raw_answer = ai_data.get("answer", "")
    if isinstance(raw_answer, list) and len(raw_answer) > 0:
        # Get the text from the first block
        final_message = raw_answer[0].get("text", "I'm sorry, I couldn't process that.")
    else:
        final_message = str(raw_answer)

    return ChatResponse(
        message=final_message,
        chat_id=session_id,
        timestamp=datetime.now(timezone.utc)
    )

@router.get("/history", response_model=List[dict])
async def get_chat_history(current_user: dict = Depends(get_current_active_user)):
    chats_collection = get_chats_collection()
    chats = await chats_collection.find({"user_id": str(current_user["_id"])}).sort("updated_at", -1).to_list(100)
    for c in chats: c["_id"] = str(c["_id"])
    return chats

@router.get("/chat/{chat_id}")
async def get_chat(chat_id: str, current_user: dict = Depends(get_current_active_user)):
    chat = await get_chats_collection().find_one({"_id": ObjectId(chat_id), "user_id": str(current_user["_id"])})
    if not chat: raise HTTPException(404, "Chat not found")
    chat["_id"] = str(chat["_id"])
    return chat