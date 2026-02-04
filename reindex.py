import asyncio
import os
import sys

# Project root ko path mein add karna
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Aapke database functions aur config import karein
from core.database import connect_to_mongo, close_mongo_connection
from services.ingestion.pdf_engine import PDFManager

async def run_reindexing():
    # --- STEP 1: Database Connection Initialise karein ---
    print("🔗 Connecting to MongoDB...")
    try:
        await connect_to_mongo()
        # Ab 'database' variable initialize ho chuka hai
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    # --- STEP 2: Path aur Manager Setup ---
    # Aapke folder ka sahi path
    pdf_dir = os.path.join(os.getcwd(), "storage", "pdfs")
    
    if not os.path.exists(pdf_dir):
        print(f"❌ Folder not found: {pdf_dir}")
        await close_mongo_connection()
        return

    manager = PDFManager()
    
    # --- STEP 3: Files Indexing ---
    files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    
    if not files:
        print("⚠️ Storage folder is empty.")
        await close_mongo_connection()
        return

    print(f"🚀 {len(files)} got files. processing start ")

    for filename in files:
        file_path = os.path.join(pdf_dir, filename)
        print(f"📑 Processing: {filename}")
        try:
            # save_to_mongo_and_qdrant internally get_knowledge_base_collection use karega
            count = await manager.save_to_mongo_and_qdrant(
                pdf_path=file_path,
                document_name=filename,
                user_email="admin@juristway.com"
            )
            print(f"   ✅ Done! {count} chunks added.")
        except Exception as e:
            print(f"   ❌ Error indexing {filename}: {e}")

    # --- STEP 4: Safai ---
    await close_mongo_connection()
    print("\n🏁 Indexing complete. Database connection closed.")

if __name__ == "__main__":
    asyncio.run(run_reindexing())