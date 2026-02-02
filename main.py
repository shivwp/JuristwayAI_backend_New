import uvicorn
import logging
import sys
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from core.config import settings
from core.database import connect_to_mongo, close_mongo_connection
from qdrant_client import QdrantClient
from api.endpoints import iam, auth, assistant, library, management 
from langchain_core.tracers.langchain import wait_for_all_tracers

from dotenv import load_dotenv
load_dotenv()
# --- 1. PRODUCTION LOGGING CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("juristway")

@asynccontextmanager
async def lifespan(app: FastAPI):
    q_host =["localhost","127.0.0.1"]
    q_port = 6333
    try:
        # DB Connection
        await connect_to_mongo()
        logger.info("✅ MongoDB Connected")

        # ✅ Vector Store Initialized (Qdrant)
        # Ab hum direct client initialize kar rahe hain
        app.state.qdrant = QdrantClient(host=q_host[1], port=q_port)
        logger.info("✅ Qdrant Client Ready")

    except Exception as e:
        logger.critical(f"❌ Startup Failed: {e}")
        raise e
    
    yield

    await close_mongo_connection()
    logger.info("✅ Database Connection Closed")

app = FastAPI(lifespan=lifespan)

# --- 2. GLOBAL EXCEPTION HANDLER ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Captures any unhandled error, logs the full traceback, 
    and returns a clean response to the client.
    """
    error_msg = "".join(traceback.format_exception(None, exc, exc.__traceback__))
    logger.error(f"Unhandled Exception at {request.url.path}: \n{error_msg}")
    
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal server error occurred. Our team has been notified.",
            "detail": str(exc) if app.debug else "Internal Server Error"
        },
    )

# Routers
app.include_router(iam.router, prefix="/api/iam", tags=["Authentication"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["Assistant"])
app.include_router(management.router, prefix="/api", tags=["Admin Management"])
app.include_router(library.router, prefix="/api/library", tags=["Document Library"])

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://api.juristway.com", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
@app.get("/")
async def root():
    return {"message": "Juristway AI API", "version": "1.0.0", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


# This forces the script to wait until all traces are uploaded
wait_for_all_tracers()