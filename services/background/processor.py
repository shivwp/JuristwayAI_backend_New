# import asyncio
# import os
# import logging
# from services.ingestion.pdf_engine import PDFManager
# from core.database import connect_to_mongo, get_knowledge_base_collection
# from dotenv import load_dotenv

# load_dotenv()
# logger = logging.getLogger(__name__)

# # PDFManager instance
# pdf_manager = PDFManager()

# async def process_document_job(doc_metadata: dict):
#     """
#     Purane code ka naya version jo Qdrant use karega aur file delete nahi karega.
#     """
#     await connect_to_mongo()
#     collection = get_knowledge_base_collection()    
#     stored_name = doc_metadata["stored_name"]
#     file_path = doc_metadata["file_path"]
#     owner_email = doc_metadata["owner"]

#     try:
#         # 1. Update Status: Processing start
#         await collection.update_one(
#             {"stored_name": stored_name},
#             {"$set": {"status": "processing"}}
#         )

#         # 2. PDF Processing
#         # Humne pdf_engine.py mein 'save_to_mongo_and_qdrant' method banaya tha
#         # Jo embedding banakar Qdrant mein daalta hai
#         num_chunks = await pdf_manager.save_to_mongo_and_qdrant(
#             pdf_path=file_path,
#             document_name=stored_name,
#             user_email=owner_email
#         )

#         # 3. Update Status: Success
#         await collection.update_one(
#             {"stored_name": stored_name},
#             {
#                 "$set": {
#                     "status": "ready",
#                     "chunks_count": num_chunks
#                 }
#             }
#         )
#         logger.info(f"✅ Successfully processed {stored_name}")

#     except Exception as e:
#         logger.error(f"❌ Error processing {stored_name}: {str(e)}")
#         await collection.update_one(
#             {"stored_name": stored_name},
#             {"$set": {"status": "failed", "error": str(e)}}
#         )
    
#     # NOTE: Yahan 'os.remove' mat karna! 
#     # Humein file 'storage/pdfs' mein chahiye taaki user use dekh sake.

import asyncio
import os
import logging
from datetime import datetime, timezone
from services.ingestion.pdf_engine import PDFManager
from core.database import connect_to_mongo, get_documents_collection, get_knowledge_base_collection
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# PDFManager instance
pdf_manager = PDFManager()

async def process_document_job(file_path: str, pdf_id: str, title: str, owner_email: str):
    """
    Sahi version: Status 'documents' mein update hoga aur chunks 'knowledge_base' mein jayenge.
    """
    await connect_to_mongo()
    
    # Do alag collections
    docs_coll = get_documents_collection()        # Status ke liye
    
    try:
        # 1. Update Status: Processing start (In Documents Collection)
        await docs_coll.update_one(
            {"pdf_id": pdf_id},
            {"$set": {"status": "processing"}}
        )

        # 2. PDF Processing: 
        # Ye chunks ko 'knowledge_base' collection aur Qdrant mein save karega
        num_chunks = await pdf_manager.save_to_mongo_and_qdrant(
            pdf_path=file_path,
            document_name=title,
            user_email=owner_email  # Linker ID
        )

        # 3. Update Status: Success (In Documents Collection)
        await docs_coll.update_one(
            {"pdf_id": pdf_id},
            {
                "$set": {
                    "status": "ready",
                    "chunk_count": num_chunks,
                    "processed_at": datetime.now(timezone.utc)
                }
            }
        )
        logger.info(f"✅ Successfully processed {title} with {num_chunks} chunks.")

    except Exception as e:
        logger.error(f"❌ Error processing {title}: {str(e)}")
        # Error status update
        await docs_coll.update_one(
            {"pdf_id": pdf_id},
            {"$set": {"status": "failed", "error_str": str(e)}}
        )
    
    # File storage mein hi rahegi, delete nahi hogi.