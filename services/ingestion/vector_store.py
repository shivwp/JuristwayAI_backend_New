# import os
# import chromadb
# from langchain_chroma import Chroma
# from langchain_google_genai import GoogleGenerativeAIEmbeddings
# from core.config import settings

# class MyCustomVectorStore:
#     def __init__(self, collection_name: str = "legal_knowledge"):
        
#         self.embeddings = GoogleGenerativeAIEmbeddings(
#             model="models/gemini-embedding-001",
#             google_api_key=settings.GEMINI_API_KEY,
#             output_dimensionality=3072
#         )


#         self.client = chromadb.HttpClient(host='46.202.164.164', port=8001) 

        
#         self.vector_store = Chroma(
#             client=self.client,
#             collection_name=collection_name,
#             embedding_function=self.embeddings,
#             persist_directory="./chroma_data",
#             collection_metadata={"hnsw:space": "cosine"}
#         )

#     def similarity_search(self, query: str, k: int = 5):
#         # Chroma handles the heavy lifting without needing 'num_candidates'
#         return self.vector_store.similarity_search(query, k=k)
    



import os
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings

class MyCustomVectorStore:
    def __init__(self, collection_name: str = "juristway_docs"):
        # 1. Embeddings setup (Gemini)
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", # Naya model 3072 dims ke liye
            google_api_key=settings.GEMINI_API_KEY
        )

        # 2. Qdrant Client (Docker nahi toh binary se chalao localhost par)
        # Agar server par hai toh localhost ki jagah IP aayega
        self.client = QdrantClient(host="localhost", port=6333)

        # 3. Vector Store Initialization
        # Langchain-Qdrant wrapper Chroma jaisa hi kaam karta hai
        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=collection_name,
            embedding=self.embeddings,
        )

    def similarity_search(self, query: str, k: int = 10):
        # Aapne Top 10 kaha tha, isliye k=10
        return self.vector_store.similarity_search(query, k=k)