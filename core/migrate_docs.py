import os
import logging
from pymongo import MongoClient
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from config import settings
import chromadb

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentMigrator:
    def __init__(self):
        # 1. Connect to Source (MongoDB)
        self.mongo_client = MongoClient(settings.DB_URL)
        self.db = self.mongo_client[settings.DB_NAME]
        self.source_collection = self.db["knowledge_base"] # Your old collection name

        # 2. Setup Embeddings
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GEMINI_API_KEY,
            output_dimensionality=3072
        )

        # 3. Connect to Destination (ChromaDB Docker)
        # Use port 8001 if you followed the previous step to avoid port conflicts
        self.chroma_client = chromadb.HttpClient(host='46.202.164.164', port=8001)        
        self.vector_store = Chroma(
            client=self.chroma_client,
            collection_name="legal_knowledge",
            embedding_function=self.embeddings
        )

    def fetch_from_mongo(self):
        logger.info("Fetching documents from MongoDB...")
        # Adjust projection based on your MongoDB schema
        cursor = self.source_collection.find({}) 
        documents = []
        
        for entry in cursor:
            # Extract text content (assumes field is 'text' or 'content')
            content = entry.get("text") or entry.get("content")
            if not content:
                continue
                
            # Preserve metadata for source referencing
            metadata = {
                "source": entry.get("source", "unknown"),
                "filename": entry.get("filename", "unknown"),
                "page": entry.get("page", 0)
            }
            
            documents.append(Document(page_content=content, metadata=metadata))
            
        logger.info(f"Found {len(documents)} documents to migrate.")
        return documents

    def migrate(self, batch_size=100):
        docs = self.fetch_from_mongo()
        
        if not docs:
            logger.warning("No documents found to migrate.")
            return

        # Migrate in batches to prevent API timeouts or memory issues
        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            logger.info(f"Migrating batch {i // batch_size + 1}...")
            self.vector_store.add_documents(batch)
            
        logger.info("Successfully migrated all documents to ChromaDB!")

if __name__ == "__main__":
    migrator = DocumentMigrator()
    migrator.migrate()