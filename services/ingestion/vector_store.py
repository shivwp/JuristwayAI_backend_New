import os
import chromadb
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings

class MyCustomVectorStore:
    def __init__(self, collection_name: str = "legal_knowledge"):
        
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GEMINI_API_KEY,
            output_dimensionality=3072
        )


        self.client = chromadb.HttpClient(host='46.202.164.164', port=8001) 

        
        self.vector_store = Chroma(
            client=self.client,
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory="./chroma_data",
            collection_metadata={"hnsw:space": "cosine"}
        )

    def similarity_search(self, query: str, k: int = 5):
        # Chroma handles the heavy lifting without needing 'num_candidates'
        return self.vector_store.similarity_search(query, k=k)