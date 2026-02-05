from datetime import datetime
import os
import shutil
import uuid
from fastapi import APIRouter, Depends, Form, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from typing import List
from api.endpoints.management import admin_required
from core.security import get_current_user_email
from core.database import get_knowledge_base_collection
from models.domain import DocumentOut
from services.background.processor import process_document_job
from services.ingestion.pdf_engine import PDFManager

router = APIRouter()

# Global storage path
STORAGE_DIR = "storage/pdfs"
os.makedirs(STORAGE_DIR, exist_ok=True)



@router.post("/content-library/upload", status_code=202)
async def upload_admin_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    current_admin: str = Depends(admin_required)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # 1. Unique ID for tracking
    pdf_id = str(uuid.uuid4())
    
    # 2. Storage Setup
    clean_name = file.filename.replace(" ", "_")
    temp_filename = f"{pdf_id}_{clean_name}" # Unique name for storage
    temp_path = os.path.join(STORAGE_DIR, temp_filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 3. Correct background task call
        background_tasks.add_task(
            process_document_job, 
            temp_path, 
            pdf_id, 
            title, 
            current_admin["email"]
        )

        return {
            "message": "Processing started", 
            "pdf_id": pdf_id, 
            "status": "processing"
        }

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

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

# @router.get("/", response_model=List[DocumentOut])
# async def list_my_documents(current_user: str = Depends(get_current_user_email)):
#     cursor = get_documents_collection().find({"owner": current_user})
#     docs = await cursor.to_list(length=100)
#     # Ensure MongoDB _id is string for frontend
#     for d in docs: d["_id"] = str(d["_id"])
#     return docs