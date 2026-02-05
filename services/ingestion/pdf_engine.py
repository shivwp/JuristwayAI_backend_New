# import asyncio
# from datetime import datetime, timezone
# import time
# from concurrent.futures import ProcessPoolExecutor, as_completed
# from typing import List, Dict
# from pdf2image import convert_from_path
# import pytesseract
# from PIL import Image
# from langchain_google_genai import GoogleGenerativeAIEmbeddings
# from core.config import settings
# from core.database import get_knowledge_base_collection 
# import os
# import pytesseract
# from dotenv import load_dotenv
# load_dotenv()
# # Add MacPorts bin to the path for the duration of this script
# os.environ["PATH"] += os.pathsep + '/opt/local/bin'
# os.environ['TESSDATA_PREFIX'] = '/opt/local/share/tessdata/'
# # Create a global executor to avoid repeated creation/destruction
# executor = ProcessPoolExecutor(max_workers=4)

# def ocr_worker(args):
#     page_number, image = args
#     pytesseract.pytesseract.tesseract_cmd = r"/opt/local/bin/tesseract"
#     text = pytesseract.image_to_string(image, lang="eng", config="--oem 3 --psm 6")
#     return {"page": page_number, "text": text.strip()}

# class PDFManager:
#     def __init__(self, ocr_workers: int = 8, overlap_ratio: float = 0.2):
#         self.ocr_workers = ocr_workers
#         self.overlap_ratio = overlap_ratio
#         # Ensure the model dimension is 768 to match your Atlas Index
#         self.embeddings = GoogleGenerativeAIEmbeddings(
#             model="models/gemini-embedding-001",
#             google_api_key=settings.GEMINI_API_KEY,
#             index_name="vector_index",
#             output_dimensionality=3072,
#             task_type="retrieval_document"  # Embedding for document storage
#         )

#     def process_pdf(self, pdf_path: str) -> List[Dict]:
#         images = convert_from_path(pdf_path, dpi=150, poppler_path="/opt/local/bin")
#         tasks = [(i + 1, img) for i, img in enumerate(images)]
        
#         # Use the global executor instead of "with ProcessPoolExecutor..."
#         futures = [executor.submit(ocr_worker, t) for t in tasks]
        
#         pages = []
#         for future in as_completed(futures):
#             pages.append(future.result())
        
#         pages.sort(key=lambda x: x["page"])
#         chunks = self._chunk_pages(pages)
#         return self._embed_chunks(chunks)

#     def _chunk_pages(self, pages: List[Dict]) -> List[Dict]:
#         """Adds overlap between pages for better semantic context."""
#         chunks = []
#         for i, page in enumerate(pages):
#             text = page["text"]
#             # Simple overlap logic: take a percentage of the next page
#             if i + 1 < len(pages):
#                 next_text = pages[i + 1]["text"]
#                 overlap_len = int(len(next_text) * self.overlap_ratio)
#                 overlap = next_text[:overlap_len]
#                 text += "\n" + overlap
            
#             chunks.append({
#                 "text": text, 
#                 "metadata": {"page": page["page"]}
#             })
#         return chunks

#     def _embed_chunks(self, chunks: List[Dict]) -> List[Dict]:
#         """Generates 768-dimension vectors using Google Generative AI."""
#         texts = [c["text"] for c in chunks]
#         # langchain_google_genai handles the API calls
#         vectors = self.embeddings.embed_documents(texts)
        
#         # Map back to a list of dicts suitable for MongoDB
#         return [
#             {
#                 "page_num": c["metadata"]["page"], 
#                 "text": c["text"], 
#                 "embedding": v # Must match the 'path' in your Atlas Index
#             } 
#             for c, v in zip(chunks, vectors)
#         ]

#     async def save_to_mongo(self, pdf_path: str, document_name: str):
#         """
#         The main entry point: Processes the PDF and saves to MongoDB asynchronously.
#         This prevents the FastAPI 'forever loading' issue.
#         """
#         # 1. OCR and Embedding (Heavier CPU/Network task)
#         # Running in a thread pool to prevent blocking the main async loop
#         loop = asyncio.get_event_loop()
#         embedded_chunks = await loop.run_in_executor(
#             None, self.process_pdf, pdf_path
#         )
        
#         if not embedded_chunks:
#             print(f"⚠️ No text found in {document_name}")
#             return

#         # 2. Add document metadata for filtering
#         for chunk in embedded_chunks:
#             chunk["document_name"] = document_name
#             chunk["timestamp"] = datetime.now(timezone.utc)

#         # 3. Save to MongoDB Knowledge Base
#         collection = get_knowledge_base_collection()
        
#         try:
#             # result = await for Motor/Async driver
#             result = await collection.insert_many(embedded_chunks)
#             print(f"✅ Successfully saved {len(result.inserted_ids)} chunks for '{document_name}' to MongoDB.")
#             return len(result.inserted_ids)
#         except Exception as e:
#             print(f"💥 Error saving to MongoDB: {str(e)}")
#             raise e




import asyncio
from datetime import datetime, timezone
from email.mime import image
import uuid
from typing import List, Dict
from fastapi import logger
from pdf2image import convert_from_path
import pytesseract
from qdrant_client import QdrantClient
from qdrant_client.http import models
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings
from core.database import get_knowledge_base_collection # MongoDB metadata ke liye
import os
import platform
from concurrent.futures import ProcessPoolExecutor, as_completed
from qdrant_client.http import models
# Qdrant Client Setup (Local ya server IP)
qdrant_client = QdrantClient(host="127.0.0.1", port=6333, check_compatibility=False) 
COLLECTION_NAME = "legal_knowledge"


# Check if running on Mac (Darwin) or Linux
IS_MAC = platform.system() == "Darwin"
TESSERACT_PATH = r"/opt/local/bin/tesseract" if IS_MAC else r"/usr/bin/tesseract"     
POPPLER_PATH = r"/opt/local/bin" if IS_MAC else r"/usr/bin"

executor = ProcessPoolExecutor(max_workers=4)

def ocr_worker(args):
    page_number, image = args
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    text = pytesseract.image_to_string(image, lang="eng", config="--oem 3 --psm 6")
    return {"page": page_number, "text": text.strip()}

class PDFManager:
    def __init__(self, overlap_ratio: float = 0.2):
        self.overlap_ratio = overlap_ratio
        # Gemini Embedding Setup (3072 dims)
        self.client = QdrantClient(host="127.0.0.1", port=6333, check_compatibility=False)
        self.collection_name = "legal_knowledge"
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", # Latest optimized model
            google_api_key=settings.GEMINI_API_KEY,
            output_dimensionality=768,
        )

    def process_pdf(self, pdf_path: str) -> List[Dict]:
        images = convert_from_path(pdf_path, dpi=150, poppler_path=POPPLER_PATH)
        tasks = [(i + 1, img) for i, img in enumerate(images)]
        
        futures = [executor.submit(ocr_worker, t) for t in tasks]
        pages = [f.result() for f in as_completed(futures)]
        pages.sort(key=lambda x: x["page"])
        
        return self._chunk_pages(pages)

    def _chunk_pages(self, pages: List[Dict]) -> List[Dict]:
        chunks = []
        for i, page in enumerate(pages):
            text = page["text"]
            if not text.strip(): continue
            
            if i + 1 < len(pages):
                next_text = pages[i + 1]["text"]
                overlap_len = int(len(next_text) * self.overlap_ratio)
                text += "\n" + next_text[:overlap_len]
            
            chunks.append({
                "text": text, 
                "page_num": page["page"]
            })
        return chunks
    
    def _setup_qdrant(self):
        """Collection create karne ka logic agar wo nahi hai toh"""
        try:
            collections = self.client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)
            
            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    # Gemini ke liye size 768 hi rakhna!
                    vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
                )
                logger.info(f"✅ Collection {self.collection_name} created successfully!")
            else:
                logger.info(f"ℹ️ Collection {self.collection_name} already exists.")
        except Exception as e:
            logger.error(f"❌ Failed to setup Qdrant collection: {e}")


    async def save_to_mongo_and_qdrant(self, pdf_path: str, document_name: str, user_email: str, pdf_id: str = None):
        # 1. OCR (CPU Task)
        loop = asyncio.get_event_loop()
        chunks = await loop.run_in_executor(None, self.process_pdf, pdf_path)
        
        if not chunks:
            return 0

        # 2. Embeddings generate karein
        texts = [c["text"] for c in chunks]
        vectors = await loop.run_in_executor(None, self.embeddings.embed_documents, texts)

        # 3. Prepare Data for Qdrant (Vector DB)
        points = []
        mongo_docs = []
        pdf_id = str(uuid.uuid4()) # Unique ID for this PDF

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            
            # Data for Qdrant
            points.append(models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "pdf_id": pdf_id,
                    "document_name": document_name,
                    "text": chunk["text"],
                    "page_num": chunk["page_num"],
                    "user_email": user_email
                }
            ))

            # Data for MongoDB (Local Record)
            mongo_docs.append({
                "point_id": point_id, # Qdrant link
                "pdf_id": pdf_id,
                "document_name": document_name,
                "text": chunk["text"],
                "page_num": chunk["page_num"],
                "user_email": user_email,
                "timestamp": datetime.now(timezone.utc)
            })

        # 4. Save to Qdrant
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)

        # 5. Save to MongoDB
        collection = get_knowledge_base_collection()
        await collection.insert_many(mongo_docs)
        
        print(f"✅ Document '{document_name}' processed: {len(chunks)} chunks saved.")
        return len(chunks)