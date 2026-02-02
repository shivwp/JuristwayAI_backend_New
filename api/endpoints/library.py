import os
import shutil
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from typing import List
from core.security import get_current_user_email
from core.database import get_documents_collection
from models.domain import DocumentOut
from services.background.processor import process_document_job

router = APIRouter()

# Global storage path
STORAGE_DIR = "storage/pdfs"
os.makedirs(STORAGE_DIR, exist_ok=True)

@router.post("/upload", status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user_email)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # 1. Unique Filename (isise file serve hogi)
    # File name se spaces hata do taaki URL mein issue na aaye
    clean_name = file.filename.replace(" ", "_")
    unique_filename = f"{uuid.uuid4().hex}_{clean_name}"
    file_path = os.path.join(STORAGE_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. MongoDB Record (Save unique_filename for later)
    doc_metadata = {
        "owner": current_user,
        "filename": file.filename, # Original name for Display
        "stored_name": unique_filename, # Unique name for File System
        "status": "processing",
        "file_path": file_path
    }
    await get_documents_collection().insert_one(doc_metadata)

    # 3. Trigger Ingestion (Qdrant logic starts here)
    background_tasks.add_task(process_document_job, doc_metadata)

    return {"message": "Processing started", "stored_name": unique_filename}

@router.get("/view-pdf/{stored_name}")
async def view_pdf(stored_name: str):
    """Serves the requested PDF file using the unique stored_name."""
    file_path = os.path.join(STORAGE_DIR, stored_name)
            
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
            
    return FileResponse(
        file_path, 
        media_type="application/pdf",
        # inline ka matlab browser mein khulega
        headers={"Content-Disposition": f"inline; filename={stored_name}"}
    )

@router.get("/", response_model=List[DocumentOut])
async def list_my_documents(current_user: str = Depends(get_current_user_email)):
    cursor = get_documents_collection().find({"owner": current_user})
    docs = await cursor.to_list(length=100)
    # Ensure MongoDB _id is string for frontend
    for d in docs: d["_id"] = str(d["_id"])
    return docs