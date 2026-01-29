# juristAI

A sophisticated AI-powered legal assistance platform built with FastAPI, LangGraph, and Google Gemini API. JuristAI provides intelligent document analysis, legal research capabilities, and chat-based assistance powered by advanced language models.

## 🌟 Features

- **AI-Powered Legal Assistant**: Chat interface powered by Google Gemini API for legal questions and analysis
- **Document Management**: Upload and process PDF documents with OCR capabilities (Tesseract)
- **Vector Search**: Semantic search across documents using vector embeddings
- **Multi-Tenant Architecture**: Secure user authentication and authorization with JWT tokens
- **MongoDB Integration**: Async database operations with Motor
- **Concurrent Processing**: Background job processing for document ingestion and indexing
- **RESTful API**: Comprehensive FastAPI endpoints for authentication, document management, and chat

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Database Setup](#database-setup)
- [Contributing](#contributing)

## 📦 Prerequisites

- **Python**: 3.12+
- **MongoDB**: Local or cloud instance (MongoDB Atlas)
- **Tesseract OCR**: For PDF text extraction
  - macOS: `brew install tesseract`
  - Linux: `sudo apt-get install tesseract-ocr`
  - Windows: Download from [GitHub Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki)
- **Google Gemini API Key**: Required for AI features
- **Redis** (optional): For caching and session management

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Aditi19-sys/juristAI.git
cd juristAI
```

### 2. Create Virtual Environment

```bash
python3.12 -m venv hms
source hms/bin/activate  # On Windows: hms\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root directory:

```env
# Database Configuration (Required)
DB_URL=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DB_NAME=juristai

# API Keys (Required)
GEMINI_API_KEY=your_google_gemini_api_key_here

# Security (Required)
SECRET_KEY=your-secret-key-for-jwt-here

# Optional
REDIS_URL=redis://localhost:6379
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### MongoDB Setup

1. Create a MongoDB instance (local or [MongoDB Atlas](https://www.mongodb.com/cloud/atlas))
2. Optionally seed the database:
   ```bash
   python seed_db.py
   ```
3. Configuration can be stored in MongoDB `settings` collection:
   ```json
   {
     "geminiApiKey": "your-api-key",
     "redisUrl": "redis://localhost:6379"
   }
   ```

## 📁 Project Structure

```
juristAI/
├── api/                          # FastAPI endpoints
│   └── endpoints/
│       ├── assistant.py          # Chat and conversation endpoints
│       ├── auth.py               # Authentication (login, signup)
│       ├── iam.py                # Identity & Access Management
│       ├── library.py            # Document library operations
│       └── management.py          # Admin operations
├── core/                         # Core application logic
│   ├── config.py                 # Settings and configuration
│   ├── database.py               # MongoDB connection & collections
│   └── security.py               # JWT and user authentication
├── models/                       # Pydantic data models
│   ├── domain.py                 # Domain models (ChatRequest, ChatResponse, etc.)
│   └── state.py                  # State management models
├── services/                     # Business logic services
│   ├── agent/
│   │   ├── brain.py              # LangGraph AI agent logic
│   │   ├── prompts.py            # System and chat prompts
│   │   └── tools.py              # AI tool definitions
│   ├── background/
│   │   ├── processor.py          # Background job processor
│   │   └── queue_mgr.py          # Queue management
│   └── ingestion/
│       ├── pdf_engine.py         # PDF processing and OCR
│       └── vector_store.py       # Vector embeddings and search
├── utils/
│   └── logging.py                # Custom logging configuration
├── workers/
│   └── doc_worker.py             # Document processing worker
├── main.py                       # FastAPI application entry point
├── requirements.txt              # Python dependencies
├── seed_db.py                    # Database initialization script
└── index_config.json             # Vector index configuration
```

## 🏃 Running the Application

### Development Mode (with hot reload)

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📡 API Endpoints

### Authentication
- `POST /api/auth/signup` - Register new user
- `POST /api/auth/login` - Login and receive JWT token
- `POST /api/auth/refresh` - Refresh access token

### Chat & Assistant
- `POST /api/assistant/chat` - Send message to AI assistant
- `GET /api/assistant/chats` - Retrieve chat history
- `GET /api/assistant/chats/{chat_id}` - Get specific chat

### Document Library
- `POST /api/library/upload` - Upload PDF document
- `GET /api/library/documents` - List user's documents
- `DELETE /api/library/documents/{doc_id}` - Delete document
- `POST /api/library/search` - Search documents

### Management
- `GET /api/management/users` - List users (admin)
- `DELETE /api/management/users/{user_id}` - Delete user (admin)

### IAM
- `POST /api/iam/permissions` - Manage user permissions

## 🗄️ Database Schema

### Users Collection
```json
{
  "_id": ObjectId,
  "email": "user@example.com",
  "username": "username",
  "hashed_password": "bcrypt_hash",
  "is_active": true,
  "created_at": ISODate
}
```

### Chats Collection
```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "title": "Chat Title",
  "messages": [
    {
      "role": "user|assistant",
      "content": "message text",
      "timestamp": ISODate
    }
  ],
  "created_at": ISODate,
  "updated_at": ISODate
}
```

### Documents Collection
```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "filename": "document.pdf",
  "file_path": "path/to/file",
  "extracted_text": "full document text",
  "created_at": ISODate
}
```

## 🧠 AI Agent Architecture

The AI brain is built with **LangGraph** and integrates:
- **Google Gemini API** for language understanding and generation
- **Custom Tools** for document search and information retrieval
- **Conversation Memory** stored in MongoDB
- **State Management** for multi-turn conversations

## 🔒 Security Features

- **JWT Authentication**: Secure token-based access control
- **Password Hashing**: Bcrypt for secure password storage
- **CORS Middleware**: Configurable cross-origin requests
- **User Isolation**: All operations scoped to authenticated user
- **Error Handling**: Global exception handler with logging

## 🧪 Testing

Run tests using:
```bash
pytest test.py -v
```

Search functionality tests:
```bash
python test_search.py
```

## 📝 Logging

Logs are configured in production mode with:
- Console output for Docker/Cloud deployments
- File logging to `juristway_app.log` for local backup
- Structured logging with timestamps and severity levels

## 🐳 Docker Support

To containerize the application:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🤝 Contributing

Contributions are welcome! Please:

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Commit changes (`git commit -m 'Add amazing feature'`)
3. Push to branch (`git push origin feature/amazing-feature`)
4. Open a Pull Request

## 📄 License

This project is proprietary software. All rights reserved.

## 📧 Contact & Support

For questions or support, contact the development team.

---

**Built with ❤️ using FastAPI, LangGraph, and Google Gemini API**
