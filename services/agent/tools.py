from langchain_core.tools import tool
from qdrant_client import QdrantClient
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from core.config import settings
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
QDRANT_HOST = "localhost" # Ya aapka server IP
QDRANT_PORT = 6333
COLLECTION_NAME = "legal_knowledge"

# --- INITIALIZATION ---
# Gemini Embeddings (Must match PDFManager dimensions: 3072)
embeddings_model = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=settings.GEMINI_API_KEY
)

# Qdrant Client
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

@tool
async def search_legal_documents(query: str):
    """Searches the Qdrant vector database for relevant legal documents and PDF chunks."""
    try:
        # 1. Query ko embedding mein convert karo
        query_vector = embeddings_model.embed_query(query)

        # 2. Qdrant mein similarity search karo
        search_response = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=10
        )

        if not search_response.points:
            return "No relevant legal documents found in the database."

        # 3. Formatted string banao (Yahan change hai)
        formatted_chunks = []
        for point in search_response.points: # <--- .points par loop chalana hai
            metadata = point.payload
            chunk_text = (
                f"Source: {metadata.get('document_name', 'unknown.pdf')}\n"
                f"Page: {metadata.get('page_num', 'N/A')}\n"
                f"Content: {metadata.get('text', '')}"
            )
            formatted_chunks.append(chunk_text)

        return "\n\n---\n\n".join(formatted_chunks)

    except Exception as e:
        logger.error(f"Error searching Qdrant: {e}")
        return f"Error searching knowledge base: {str(e)}"

# LangGraph agent isi list ko use karega
legal_tools = [search_legal_documents]