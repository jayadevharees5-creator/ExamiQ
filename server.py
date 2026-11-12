import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import Config
from core.pdf_processor import DocumentProcessor
from core.rag_pipeline import RAGPipeline
from core.groq_client import GroqClientWrapper
from core.question_generator import QuestionGenerator
from utils.exporters import QuestionExporter
from core.db import db_manager
from utils.auth import create_access_token, decode_access_token
from utils.rate_limiter import RateLimitMiddleware, rate_limiter
from utils.request_logger import RequestLoggingMiddleware, setup_logging

# Configure application-wide logging
setup_logging()
logger = logging.getLogger("quizforge")

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """FastAPI dependency that extracts and validates a JWT token.
    Returns the username (sub) if valid, otherwise raises 401.
    """
    if credentials:
        token = credentials.credentials
        username = decode_access_token(token)
        if username:
            return username.strip().lower()
    raise HTTPException(status_code=401, detail="Invalid or missing authentication token")

# Initialize FastAPI App
app = FastAPI(title="QuizForge AI API", version="2.0.0")

# Register Request Logging Middleware (logs user, endpoint, method, status, duration)
app.add_middleware(RequestLoggingMiddleware)

# Register Distributed Redis-backed Rate Limit Middleware (with memory fallback)
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)

# Register CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Per-User Session Isolation (Fixes RAG data leakage)
# ─────────────────────────────────────────────────────────────
# SHARED (stateless) resources — one instance for the entire server
_shared_api_key = Config.GROQ_API_KEY
_shared_model = Config.DEFAULT_GROQ_MODEL
_shared_rrf_k = Config.DEFAULT_RRF_K
_shared_groq_client = GroqClientWrapper(api_key=_shared_api_key, model=_shared_model)
_shared_question_gen = QuestionGenerator(groq_client=_shared_groq_client)


class UserSession:
    """Per-user isolated session: each user gets their own RAG pipeline and state."""
    def __init__(self, username: str):
        self.username = username
        self.rag_pipeline = RAGPipeline(rrf_k=_shared_rrf_k)
        self.uploaded_pages: List[Dict[str, Any]] = []
        self.uploaded_docs_meta: List[Dict[str, Any]] = []
        self.detected_units: List[Dict[str, Any]] = []
        self.generated_questions: List[Dict[str, Any]] = []
        self.current_context_text: str = ""
        self.generated_documents: List[Dict[str, Any]] = []
        self.current_exam_meta: Dict[str, Any] = {}
        # Track previously generated question texts to prevent regeneration repetition
        self.question_history: List[str] = []

        # Restore persisted FAISS vector index & metadata if available
        if self.username and self.username != "anonymous":
            try:
                loaded = self.rag_pipeline.load_pipeline(self.username)
                if loaded and self.rag_pipeline.indexed_chunks:
                    doc_names = list(dict.fromkeys(c.get("doc_name", "document") for c in self.rag_pipeline.indexed_chunks))
                    self.uploaded_docs_meta = [{
                        "filename": d,
                        "pages": max((c.get("page_number", 1) for c in self.rag_pipeline.indexed_chunks if c.get("doc_name") == d), default=1),
                        "characters": sum(len(c.get("text", "")) for c in self.rag_pipeline.indexed_chunks if c.get("doc_name") == d),
                        "is_scanned": False
                    } for d in doc_names]
            except Exception as e:
                logger.warning("Could not restore persisted FAISS index for %s: %s", self.username, str(e))


class UserSessionManager:
    """
    Manages per-user sessions. Each user's uploaded documents, RAG index,
    and generated questions are completely isolated from other users.
    """
    def __init__(self):
        self._sessions: Dict[str, UserSession] = {}

    def get(self, username: str) -> UserSession:
        """Returns existing session or creates a fresh one."""
        uname = (username or "anonymous").strip().lower()
        if uname not in self._sessions:
            self._sessions[uname] = UserSession(uname)
        return self._sessions[uname]

    def clear(self, username: str) -> None:
        """Resets a specific user's session (called on login/logout)."""
        uname = (username or "anonymous").strip().lower()
        self._sessions[uname] = UserSession(uname)

    def remove(self, username: str) -> None:
        """Completely removes a user's session from memory."""
        uname = (username or "anonymous").strip().lower()
        self._sessions.pop(uname, None)


sessions = UserSessionManager()

# Backward-compatible accessors used by some legacy endpoints
# These properties redirect to the "anonymous" session for backwards compat
class _LegacyStateProxy:
    """Thin proxy that makes `state.X` work for endpoints that don't pass auth."""
    @property
    def api_key(self): return _shared_api_key
    @property
    def model(self): return _shared_model
    @property
    def rrf_k(self): return _shared_rrf_k
    @property
    def groq_client(self): return _shared_groq_client
    @property
    def question_gen(self): return _shared_question_gen

state = _LegacyStateProxy()


from utils.auth import create_access_token, decode_access_token

def extract_username(authorization: Optional[str] = None, username: Optional[str] = None) -> Optional[str]:
    """Extracts username from a JWT Bearer token or explicit username param.
    Returns ``None`` if no valid token/user is provided.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        decoded = decode_access_token(token)
        if decoded:
            return decoded.strip().lower()
    if username and username.strip():
        return username.strip().lower()
    return None
    """Extracts username from Authorization Bearer token or explicit username param."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        # token format: token_<username>_<timestamp>
        if token.startswith("token_"):
            parts = token.split("_")
            if len(parts) >= 3:
                user_part = "_".join(parts[1:-1])
                if user_part:
                    return user_part.strip().lower()
    if username and username.strip():
        return username.strip().lower()
    return None

# -------------------------------------------------------------
# Request Schemas
# -------------------------------------------------------------
class SettingsPayload(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    rrf_k: Optional[int] = None

class PDFQuestionsPayload(BaseModel):
    unit: str = ""
    topic: str = ""
    question_types: List[str] = ["Multiple Choice Questions (MCQ)"]
    difficulty: str = "Medium"
    count: int = 5
    page_min: Optional[int] = None
    page_max: Optional[int] = None
    include_answers: bool = True
    include_explanations: bool = True
    include_sources: bool = True
    language: str = "English"
    instructions: str = ""
    time_allowed: str = "1 Hour"
    max_marks: str = "150"
    username: Optional[str] = None

class KnowledgeQuestionsPayload(BaseModel):
    topic: str
    target_audience: str = "Interview Preparation"
    question_types: List[str] = ["Multiple Choice Questions (MCQ)"]
    difficulty: str = "Medium"
    count: int = 5
    include_answers: bool = True
    include_explanations: bool = True
    include_hints: bool = True
    instructions: str = ""
    time_allowed: str = "1 Hour"
    max_marks: str = "150"
    username: Optional[str] = None

class DSAQuestionsPayload(BaseModel):
    topic: str
    language: str = "Python"
    problem_style: str = "LeetCode-style Problem"
    difficulty: str = "Medium"
    count: int = 3
    include_constraints: bool = True
    include_hints: bool = True
    include_solution: bool = True
    include_complexity: bool = True
    instructions: str = ""
    username: Optional[str] = None

class RegeneratePayload(BaseModel):
    question_index: int
    username: Optional[str] = None
    question: Optional[Dict[str, Any]] = None

class QuestionsExportPayload(BaseModel):
    questions: Optional[List[Dict[str, Any]]] = None

class LoginPayload(BaseModel):
    username: str
    password: str

class RegisterPayload(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"
    full_name: Optional[str] = ""

class DBConnectPayload(BaseModel):
    mongo_uri: str
    db_name: Optional[str] = "question_generator_db"

class ForgotPasswordPayload(BaseModel):
    username: str
    new_password: str

# -------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------
@app.post("/api/clear-session")
def clear_session(current_user: str = Depends(get_current_user)):
    """Resets the authenticated user's in-memory session to prevent data leakage."""
    sessions.clear(current_user)
    return {"success": True, "message": "Session state cleared."}

@app.get("/api/status")
def get_status(current_user: str = Depends(get_current_user)):
    """Returns engine readiness, model name, and current index metrics for the authenticated user."""
    is_ready = _shared_groq_client.is_configured()
    sess = sessions.get(current_user)
    return {
        "engine_ready": is_ready,
        "model": _shared_model,
        "available_models": Config.AVAILABLE_MODELS,
        "total_docs": len(sess.uploaded_docs_meta),
        "total_chunks": len(sess.rag_pipeline.indexed_chunks),
        "detected_units": sess.detected_units,
        "has_questions": len(sess.generated_questions) > 0,
        "question_count": len(sess.generated_questions)
    }

# -------------------------------------------------------------
# Authentication & MongoDB Management Endpoints
# -------------------------------------------------------------
@app.post("/api/login")
def login_user(payload: LoginPayload):
    """Authenticates a user against MongoDB and returns a signed JWT.
    The JWT encodes the username (sub) and expires according to the
    configuration in ``utils/auth.py``.
    """
    user = db_manager.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # Issue a JWT access token
    token = create_access_token(user["username"])

    # Return minimal user info (do not expose password hash/salt)
    safe_user = {
        "username": user.get("username"),
        "role": user.get("role"),
        "full_name": user.get("full_name"),
        "created_at": user.get("created_at"),
    }
    return {"success": True, "user": safe_user, "token": token}

    """Authenticates Admin or User against MongoDB collection."""
    user = db_manager.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # Create a fresh isolated session for this user (does NOT affect other users)
    sessions.clear(user["username"])

    return {
        "success": True,
        "user": user,
        "token": f"token_{user['username']}_{int(time.time())}"
    }

@app.post("/api/register")
def register_user(payload: RegisterPayload):
    """Registers new Admin or User account into MongoDB collection."""
    res = db_manager.register_user(
        username=payload.username,
        password=payload.password,
        role=payload.role or "user",
        full_name=payload.full_name or ""
    )
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error", "Registration failed."))
    return res

@app.post("/api/forgot-password")
def forgot_password(payload: ForgotPasswordPayload):
    """Resets user password after verification. Admin password cannot be reset via web interface."""
    if payload.username.strip().lower() == "admin":
        raise HTTPException(
            status_code=403,
            detail="The admin password cannot be changed via the application. It can only be changed in the server .env file."
        )
    res = db_manager.reset_password(payload.username, payload.new_password)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Password reset failed."))
    return res

@app.get("/api/db-status")
def get_db_status(current_user: str = Depends(get_current_user)):
    """Returns MongoDB health status, database name, and document counts for the authenticated user."""
    return db_manager.get_status(username=current_user)

@app.post("/api/db-connect")
def connect_mongodb(payload: DBConnectPayload):
    """Connects or switches MongoDB connection URI (e.g. Atlas cluster)."""
    db_manager.connect(payload.mongo_uri, payload.db_name)
    return db_manager.get_status()

@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    """Updates runtime Groq API key, model, or RRF parameter."""
    global _shared_api_key, _shared_model, _shared_rrf_k, _shared_groq_client, _shared_question_gen
    if payload.api_key is not None:
        _shared_api_key = payload.api_key.strip()
    if payload.model:
        _shared_model = payload.model.strip()
    if payload.rrf_k:
        _shared_rrf_k = payload.rrf_k

    _shared_groq_client = GroqClientWrapper(api_key=_shared_api_key, model=_shared_model)
    _shared_question_gen = QuestionGenerator(groq_client=_shared_groq_client)
    val = _shared_groq_client.validate_connection()
    return {
        "success": True,
        "validation": val,
        "active_model": _shared_model,
        "rrf_k": _shared_rrf_k
    }

@app.post("/api/upload-pdf")
async def upload_pdf(
    files: List[UploadFile] = File(...),
    username: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None)
):
    """Processes uploaded PDFs, extracts text, builds FAISS + BM25 indexes, and saves study material for this user alone."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    current_user = extract_username(authorization, username) or "anonymous"

    extracted_pages = []
    docs_meta = []
    detected_units = []
    scanned_warnings = []

    for f in files:
        content = await f.read()
        proc_res = DocumentProcessor.process_document(content, f.filename)
        if not proc_res["success"]:
            continue

        if proc_res.get("is_scanned", False):
            scanned_warnings.append(
                f"'{f.filename}' appears to be a scanned image with no extractable text. Please run OCR first."
            )

        extracted_pages.extend(proc_res["pages_data"])
        detected_units.extend(proc_res.get("detected_units", []))
        docs_meta.append({
            "filename": f.filename,
            "pages": proc_res["total_pages"],
            "characters": proc_res["total_characters"],
            "is_scanned": proc_res.get("is_scanned", False)
        })

    if not extracted_pages:
        raise HTTPException(status_code=400, detail="No extractable text was found in the uploaded documents.")

    # Index into this user's ISOLATED RAG pipeline (not shared)
    sess = sessions.get(current_user)
    index_res = sess.rag_pipeline.index_documents(extracted_pages)
    if not index_res["success"]:
        raise HTTPException(status_code=500, detail=index_res.get("error", "Indexing failed."))
    sess.rag_pipeline.save_pipeline(current_user)

    sess.uploaded_pages = extracted_pages
    sess.uploaded_docs_meta = docs_meta
    sess.detected_units = detected_units

    # Save processed study material to database tagged with current_user
    saved_materials = []
    for d in docs_meta:
        mat_id = f"mat_{int(time.time()*1000)}_{abs(hash(d['filename'])) % 10000}"
        mat_record = {
            "id": mat_id,
            "filename": d["filename"],
            "pages": d["pages"],
            "characters": d["characters"],
            "chunk_count": index_res["chunk_count"],
            "detected_units": detected_units,
            "pages_data": extracted_pages,
            "created_at": datetime.now().strftime("%b %d, %Y • %I:%M %p"),
            "created_by": current_user
        }
        db_manager.save_study_material(mat_record, username=current_user)
        saved_materials.append({
            "id": mat_id,
            "filename": d["filename"],
            "pages": d["pages"],
            "characters": d["characters"],
            "chunk_count": index_res["chunk_count"],
            "detected_units": detected_units,
            "created_at": mat_record["created_at"],
            "created_by": current_user
        })

    user_materials = db_manager.get_user_study_materials(current_user)

    return {
        "success": True,
        "documents": docs_meta,
        "materials": saved_materials,
        "user_materials": user_materials,
        "total_pages": sum(d["pages"] for d in docs_meta),
        "chunk_count": index_res["chunk_count"],
        "detected_units": detected_units,
        "scanned_warnings": scanned_warnings
    }

@app.get("/api/user-study-materials")
def get_user_study_materials(current_user: str = Depends(get_current_user)):
    """Returns study materials processed by this user alone."""
    uname = current_user
    if not uname:
        return {"success": True, "materials": []}
    materials = db_manager.get_user_study_materials(uname)
    return {"success": True, "materials": materials}

@app.post("/api/select-study-material/{material_id}")
def select_study_material(material_id: str, current_user: str = Depends(get_current_user)):
    """Activates a previously processed study material into this user's isolated RAG pipeline."""
    uname = current_user
    mat = db_manager.get_study_material_by_id(material_id, username=uname)
    if not mat:
        raise HTTPException(status_code=404, detail="Processed study material not found.")

    pages_data = mat.get("pages_data", [])
    if not pages_data:
        raise HTTPException(status_code=400, detail="Document content is empty.")

    filename = mat.get("filename", "material.pdf")
    for idx, p in enumerate(pages_data):
        if not p.get("doc_name"):
            p["doc_name"] = filename
        if not p.get("page_number"):
            p["page_number"] = p.get("page_num", idx + 1)

    # Reset and index strictly this material into THIS USER's session only
    sess = sessions.get(uname)
    sess.rag_pipeline = RAGPipeline(rrf_k=_shared_rrf_k)
    index_res = sess.rag_pipeline.index_documents(pages_data)
    if not index_res["success"]:
        raise HTTPException(status_code=500, detail="Indexing failed.")
    sess.rag_pipeline.save_pipeline(uname)

    sess.uploaded_pages = pages_data
    sess.uploaded_docs_meta = [{
        "filename": mat.get("filename", "material.pdf"),
        "pages": mat.get("pages", len(pages_data)),
        "characters": mat.get("characters", 0),
        "is_scanned": False
    }]
    sess.detected_units = mat.get("detected_units", [])

    return {
        "success": True,
        "material": {
            "id": mat.get("id"),
            "filename": mat.get("filename"),
            "pages": mat.get("pages"),
            "chunk_count": len(pages_data),
            "detected_units": sess.detected_units
        }
    }

@app.delete("/api/user-study-material/{material_id}")
def delete_user_study_material(material_id: str, current_user: str = Depends(get_current_user)):
    """Deletes a processed study material belonging to this user alone."""
    uname = current_user
    db_manager.delete_study_material(material_id, username=uname)
    materials = db_manager.get_user_study_materials(uname)
    return {"success": True, "materials": materials}

@app.post("/api/clear-documents")
def clear_documents(current_user: str = Depends(get_current_user)):
    """Clears the authenticated user's uploaded documents and hybrid indexes."""
    uname = current_user
    sess = sessions.get(uname)
    sess.uploaded_pages = []
    sess.uploaded_docs_meta = []
    sess.detected_units = []
    sess.rag_pipeline = RAGPipeline(rrf_k=_shared_rrf_k)
    return {"success": True, "message": "Documents and indexes cleared."}

@app.post("/api/generate-pdf-questions")
def generate_pdf_questions(payload: PDFQuestionsPayload, authorization: Optional[str] = Header(None)):
    """Generates grounded questions using FAISS + BM25 + RRF and Groq LLM — fully isolated per user."""
    if not _shared_groq_client.is_configured():
        raise HTTPException(status_code=400, detail="Groq API key is not configured. Please open Settings to add it.")

    current_user = extract_username(authorization, payload.username) or "anonymous"
    sess = sessions.get(current_user)

    if not sess.uploaded_pages:
        # Check if user has processed study materials in database and auto-restore
        user_mats = db_manager.get_user_study_materials(current_user)
        if user_mats and len(user_mats) > 0:
            mat = user_mats[-1]
            pages_data = mat.get("pages_data", [])
            if pages_data:
                filename = mat.get("filename", "material.pdf")
                for idx, p in enumerate(pages_data):
                    if not p.get("doc_name"):
                        p["doc_name"] = filename
                    if not p.get("page_number"):
                        p["page_number"] = p.get("page_num", idx + 1)
                sess.rag_pipeline = RAGPipeline(rrf_k=_shared_rrf_k)
                sess.rag_pipeline.index_documents(pages_data)
                sess.rag_pipeline.save_pipeline(current_user)
                sess.uploaded_pages = pages_data
                sess.uploaded_docs_meta = [{
                    "filename": filename,
                    "pages": mat.get("pages", len(pages_data)),
                    "characters": mat.get("characters", 0),
                    "is_scanned": False
                }]
                sess.detected_units = mat.get("detected_units", [])

    if not sess.uploaded_pages:
        raise HTTPException(status_code=400, detail="Please upload a PDF, DOCX, or TXT document first.")

    # Build strict anti-repetition instructions from current paper questions + history
    diversity_instruction = payload.instructions or ""
    current_questions = [q.get("question", "").strip() for q in sess.generated_questions if q.get("question")]
    all_avoid = []
    for q_text in current_questions + sess.question_history[-15:]:
        if q_text and q_text not in all_avoid:
            all_avoid.append(q_text)

    if all_avoid:
        avoid_list = "\n".join(f"- {q[:100]}" for q in all_avoid[-15:])
        diversity_instruction += (
            f"\n\nSTRICT ANTI-REPETITION REQUIREMENT (ZERO DUPLICATION):\n"
            f"The following questions have ALREADY been generated. You are STRICTLY FORBIDDEN from repeating, rephrasing, or duplicating any of them:\n"
            f"{avoid_list}\n"
            f"Generate COMPLETELY NEW questions on DIFFERENT concepts, equations, theorems, or sections."
        )

    res = _shared_question_gen.generate_from_pdf_rag(
        rag_pipeline=sess.rag_pipeline,
        unit_info=payload.unit,
        topic=payload.topic,
        question_types=payload.question_types,
        difficulty=payload.difficulty,
        count=payload.count,
        include_answers=payload.include_answers,
        include_explanations=payload.include_explanations,
        include_sources=payload.include_sources,
        language=payload.language,
        additional_instructions=diversity_instruction,
        page_min=payload.page_min,
        page_max=payload.page_max,
        temperature=0.7,
        existing_questions=all_avoid
    )

    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error", "Question generation failed."))

    # Ensure source documents and page numbers are tagged
    source_filename = sess.uploaded_docs_meta[0]["filename"] if sess.uploaded_docs_meta else "document.pdf"
    for idx, q in enumerate(res["questions"]):
        if not q.get("source_document"):
            q["source_document"] = source_filename
        if not q.get("page_number"):
            q["page_number"] = (idx % max(len(sess.uploaded_pages), 1)) + 1

    # Track question history for anti-repetition
    for q in res["questions"]:
        q_text = q.get("question", "")
        if q_text and q_text not in sess.question_history:
            sess.question_history.append(q_text)
    # Keep history bounded
    if len(sess.question_history) > 100:
        sess.question_history = sess.question_history[-60:]

    doc_id = f"doc_{int(time.time()*1000)}"
    doc_record = {
        "id": doc_id,
        "subject": payload.topic.strip() or payload.unit.strip() or "Curriculum Assessment",
        "department": "",
        "max_marks": payload.max_marks.strip() or "150",
        "time_allowed": payload.time_allowed.strip() or "1 Hour",
        "blooms_level": "Curriculum Grounded",
        "question_format": payload.question_types[0] if payload.question_types else "Multiple Choice Questions (MCQ)",
        "difficulty": payload.difficulty,
        "count": len(res["questions"]),
        "created_at": datetime.now().strftime("%b %d, %Y • %I:%M %p"),
        "source_file": source_filename,
        "questions": res["questions"],
        "created_by": current_user
    }
    sess.generated_questions = res["questions"]
    sess.current_exam_meta = doc_record
    sess.current_context_text = res["retrieval_details"].get("context_text", "")
    db_manager.save_question_paper(doc_record, username=current_user)
    user_documents = db_manager.get_all_question_papers(username=current_user)

    return {
        "success": True,
        "questions": res["questions"],
        "document": doc_record,
        "all_documents": user_documents,
        "retrieval_meta": {
            "dense_count": res["retrieval_details"].get("dense_count", 0),
            "bm25_count": res["retrieval_details"].get("bm25_count", 0),
            "fused_count": res["retrieval_details"].get("fused_count", 0)
        }
    }

@app.post("/api/generate-knowledge-questions")
def generate_knowledge_questions(payload: KnowledgeQuestionsPayload, authorization: Optional[str] = Header(None)):
    """Generates questions from general AI model knowledge across any topic."""
    if not _shared_groq_client.is_configured():
        raise HTTPException(status_code=400, detail="Groq API key is not configured. Please open Settings to add it.")
    if not payload.topic.strip():
        raise HTTPException(status_code=400, detail="Please provide a topic.")

    current_user = extract_username(authorization, payload.username) or "anonymous"
    sess = sessions.get(current_user)

    # Build anti-repetition instructions (keep short to minimise prompt tokens)
    # Build strict anti-repetition instructions from current paper questions + history
    diversity_instruction = payload.instructions or ""
    current_questions = [q.get("question", "").strip() for q in sess.generated_questions if q.get("question")]
    all_avoid = []
    for q_text in current_questions + sess.question_history[-15:]:
        if q_text and q_text not in all_avoid:
            all_avoid.append(q_text)

    if all_avoid:
        avoid_list = "\n".join(f"- {q[:100]}" for q in all_avoid[-15:])
        diversity_instruction += (
            f"\n\nSTRICT ANTI-REPETITION REQUIREMENT (ZERO DUPLICATION):\n"
            f"The following questions have ALREADY been generated. You are STRICTLY FORBIDDEN from repeating, rephrasing, or duplicating any of them:\n"
            f"{avoid_list}\n"
            f"Generate COMPLETELY NEW questions on DIFFERENT sub-topics, principles, or applications."
        )

    res = _shared_question_gen.generate_from_knowledge(
        topic=payload.topic,
        target_audience=payload.target_audience,
        question_types=payload.question_types,
        difficulty=payload.difficulty,
        count=payload.count,
        include_answers=payload.include_answers,
        include_explanations=payload.include_explanations,
        include_hints=payload.include_hints,
        additional_instructions=diversity_instruction,
        temperature=0.7,
        existing_questions=all_avoid
    )

    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error", "Generation failed."))

    # Track history
    for q in res["questions"]:
        q_text = q.get("question", "")
        if q_text and q_text not in sess.question_history:
            sess.question_history.append(q_text)
    if len(sess.question_history) > 100:
        sess.question_history = sess.question_history[-60:]

    doc_id = f"doc_{int(time.time()*1000)}"
    doc_record = {
        "id": doc_id,
        "subject": payload.topic.strip(),
        "department": f"Curriculum Studio — {payload.target_audience}",
        "max_marks": payload.max_marks.strip() or "150",
        "time_allowed": payload.time_allowed.strip() or "1 Hour",
        "blooms_level": "Understand / Apply",
        "question_format": payload.question_types[0] if payload.question_types else "Multiple Choice Questions (MCQ)",
        "difficulty": payload.difficulty,
        "count": len(res["questions"]),
        "created_at": datetime.now().strftime("%b %d, %Y • %I:%M %p"),
        "source_file": "AI Curriculum Knowledge",
        "questions": res["questions"],
        "created_by": current_user
    }
    sess.generated_questions = res["questions"]
    sess.current_exam_meta = doc_record
    sess.current_context_text = ""
    db_manager.save_question_paper(doc_record, username=current_user)
    user_documents = db_manager.get_all_question_papers(username=current_user)

    return {"success": True, "questions": res["questions"], "document": doc_record, "all_documents": user_documents}

@app.post("/api/generate-dsa-questions")
def generate_dsa_questions(payload: DSAQuestionsPayload, authorization: Optional[str] = Header(None)):
    """Generates rigorous DSA coding challenges with problem statement, constraints, and samples."""
    if not _shared_groq_client.is_configured():
        raise HTTPException(status_code=400, detail="Groq API key is not configured. Please open Settings to add it.")
    if not payload.topic.strip():
        raise HTTPException(status_code=400, detail="Please provide a DSA topic.")

    current_user = extract_username(authorization, payload.username) or "anonymous"
    sess = sessions.get(current_user)

    # Build anti-repetition instructions from current paper + history
    diversity_instruction = payload.instructions or ""
    current_problems = [
        (q.get("title") or q.get("question", "")).strip() for q in sess.generated_questions if (q.get("title") or q.get("question"))
    ]
    all_avoid = []
    for p_text in current_problems + sess.question_history[-15:]:
        if p_text and p_text not in all_avoid:
            all_avoid.append(p_text)

    if all_avoid:
        avoid_list = "\n".join(f"- {p[:100]}" for p in all_avoid[-15:])
        diversity_instruction += (
            f"\n\nSTRICT ANTI-REPETITION REQUIREMENT (ZERO DUPLICATION):\n"
            f"The following problems have ALREADY been generated. You are STRICTLY FORBIDDEN from repeating, rephrasing, or duplicating any of them:\n"
            f"{avoid_list}\n"
            f"Generate COMPLETELY NEW problems on DIFFERENT algorithmic concepts, data structures, or paradigms."
        )

    res = _shared_question_gen.generate_dsa_problems(
        dsa_topic=payload.topic,
        problem_style=payload.problem_style,
        language=payload.language,
        difficulty=payload.difficulty,
        count=payload.count,
        include_constraints=payload.include_constraints,
        include_hints=payload.include_hints,
        include_solution=payload.include_solution,
        include_complexity=payload.include_complexity,
        additional_instructions=diversity_instruction,
        existing_questions=all_avoid
    )

    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error", "DSA Generation failed."))

    # Track question history for anti-repetition
    for q in res["questions"]:
        p_text = q.get("title") or q.get("question", "")
        if p_text and p_text not in sess.question_history:
            sess.question_history.append(p_text)
    if len(sess.question_history) > 100:
        sess.question_history = sess.question_history[-60:]

    doc_id = f"doc_{int(time.time()*1000)}"
    doc_record = {
        "id": doc_id,
        "subject": f"DSA: {payload.topic.strip()} ({payload.language})",
        "department": "",
        "max_marks": "150",
        "time_allowed": "1 Hour",
        "blooms_level": "Apply / Create (Coding)",
        "question_format": payload.problem_style,
        "difficulty": payload.difficulty,
        "count": len(res["questions"]),
        "created_at": datetime.now().strftime("%b %d, %Y • %I:%M %p"),
        "source_file": "Algorithmic Problem Studio",
        "questions": res["questions"],
        "created_by": current_user
    }
    sess.generated_questions = res["questions"]
    sess.current_exam_meta = doc_record
    sess.current_context_text = ""
    db_manager.save_question_paper(doc_record, username=current_user)
    user_documents = db_manager.get_all_question_papers(username=current_user)

    return {"success": True, "questions": res["questions"], "document": doc_record, "all_documents": user_documents}

@app.post("/api/regenerate-question")
def regenerate_question(payload: RegeneratePayload, authorization: Optional[str] = Header(None)):
    """Regenerates a single question by index, using the user's isolated session."""
    current_user = extract_username(authorization, payload.username) or "anonymous"
    sess = sessions.get(current_user)

    idx = payload.question_index
    target = None
    if 0 <= idx < len(sess.generated_questions):
        target = sess.generated_questions[idx]
    elif payload.question:
        target = payload.question

    if not target:
        raise HTTPException(status_code=400, detail="Invalid question index or question data missing.")

    # Determine if target question belongs to curriculum / knowledge or document RAG
    exam_meta = sess.current_exam_meta or {}
    is_knowledge = (
        exam_meta.get("source_file") in ["AI Curriculum Knowledge", "Algorithmic Problem Studio"]
        or target.get("source_document") in ["AI Curriculum Knowledge", "Algorithmic Problem Studio", "General AI Curriculum Knowledge"]
        or not target.get("source_document")
    )

    context_text = None
    if not is_knowledge:
        context_text = sess.current_context_text
        if (not context_text or len(context_text.strip()) < 50) and len(sess.rag_pipeline.indexed_chunks) > 0:
            query = target.get("question", "") or target.get("topic", "") or "core academic curriculum"
            retrieval = sess.rag_pipeline.retrieve(query, top_k_fused=6)
            context_text = retrieval.get("context_text", "")
    else:
        if not target.get("topic") and exam_meta.get("subject"):
            target["topic"] = exam_meta.get("subject")

    # Build exclusion list of ALL current questions so regeneration produces something genuinely new
    existing_questions = [q.get("question", "") for q in sess.generated_questions if q.get("question")]
    if target.get("question") and target.get("question") not in existing_questions:
        existing_questions.append(target.get("question"))
    existing_questions.extend(sess.question_history[-20:])

    res = _shared_question_gen.regenerate_single_question(
        existing_question=target,
        context_text=context_text,
        existing_questions=existing_questions
    )
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error", "Regeneration failed."))

    # Update session and history
    if 0 <= idx < len(sess.generated_questions):
        sess.generated_questions[idx] = res["question"]
    new_q = res["question"].get("question", "")
    if new_q and new_q not in sess.question_history:
        sess.question_history.append(new_q)

    return {"success": True, "question": res["question"], "index": idx}

# -------------------------------------------------------------
# Examination Paper & Generated Documents Endpoints
# -------------------------------------------------------------
@app.post("/api/generate-exam-paper")
async def generate_exam_paper(
    file: Optional[UploadFile] = File(None),
    subject: str = Form(""),
    department: str = Form(""),
    max_marks: str = Form(""),
    time_allowed: str = Form(""),
    blooms_level: str = Form(""),
    question_format: str = Form("Multiple Choice Questions (MCQ)"),
    difficulty: str = Form("Medium"),
    count: int = Form(5),
    additional_instructions: str = Form(""),
    username: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None)
):
    """Generates an institutional examination paper directly from form inputs & uploaded material."""
    if not _shared_groq_client.is_configured():
        raise HTTPException(status_code=400, detail="Groq API key is not configured. Please check your .env or configuration.")

    current_user = extract_username(authorization, username) or "anonymous"
    sess = sessions.get(current_user)

    source_filename = "Course Material"

    # Ingest document if provided
    if file and file.filename:
        content = await file.read()
        if len(content) > 0:
            proc_res = DocumentProcessor.process_document(content, file.filename)
            if not proc_res["success"] or not proc_res["pages_data"]:
                raise HTTPException(status_code=400, detail=f"Could not extract text from '{file.filename}'. {proc_res.get('error','')}")

            sess.rag_pipeline = RAGPipeline(rrf_k=_shared_rrf_k)
            index_res = sess.rag_pipeline.index_documents(proc_res["pages_data"])
            if not index_res["success"]:
                raise HTTPException(status_code=500, detail=index_res.get("error", "Indexing failed."))
            sess.rag_pipeline.save_pipeline(current_user)

            sess.uploaded_pages = proc_res["pages_data"]
            sess.uploaded_docs_meta = [{
                "filename": file.filename,
                "pages": proc_res["total_pages"],
                "characters": proc_res["total_characters"],
                "is_scanned": proc_res.get("is_scanned", False)
            }]
            source_filename = file.filename
            
            # Save to user's study materials library
            mat_record = {
                "id": f"mat_{int(time.time()*1000)}",
                "filename": file.filename,
                "pages": proc_res["total_pages"],
                "characters": proc_res["total_characters"],
                "chunk_count": len(proc_res["pages_data"]),
                "detected_units": proc_res.get("detected_units", []),
                "pages_data": proc_res["pages_data"],
                "created_at": datetime.now().strftime("%b %d, %Y • %I:%M %p"),
                "created_by": current_user
            }
            db_manager.save_study_material(mat_record, username=current_user)

    if not sess.uploaded_pages:
        raise HTTPException(status_code=400, detail="Please upload a course material document (PDF, DOCX, or TXT) first.")

    if not source_filename or source_filename == "Course Material":
        source_filename = sess.uploaded_docs_meta[0]["filename"] if sess.uploaded_docs_meta else "document.pdf"

    # Assemble instructions
    instructions_list = []
    if blooms_level and blooms_level.strip():
        instructions_list.append(f"Target Bloom's Taxonomy Level: {blooms_level.strip()}. Formulate questions evaluating this cognitive level.")
    if question_format and question_format.strip():
        instructions_list.append(f"Question Format: {question_format.strip()}.")
    if additional_instructions and additional_instructions.strip():
        instructions_list.append(additional_instructions.strip())

    combined_instructions = " ".join(instructions_list)

    # Format question types
    fmt = question_format.strip() if question_format else "Multiple Choice Questions (MCQ)"
    q_types = [fmt] if fmt != "Mixed Format" else ["Multiple Choice Questions (MCQ)", "Short Answer Questions"]

    eff_count = count if (count and 1 <= count <= 50) else 5
    topic_query = subject.strip() or "Comprehensive Curriculum Key Concepts"

    exclude_list = sess.question_history[-30:] if sess.question_history else []

    res = _shared_question_gen.generate_from_pdf_rag(
        rag_pipeline=sess.rag_pipeline,
        unit_info=subject.strip() or "Syllabus Unit",
        topic=topic_query,
        question_types=q_types,
        difficulty=difficulty.strip() or "Medium",
        count=eff_count,
        include_answers=True,
        include_explanations=True,
        include_sources=True,
        additional_instructions=combined_instructions,
        existing_questions=exclude_list,
        temperature=0.55
    )

    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error", "Question generation failed."))

    # Ensure source documents and page numbers are properly tagged
    for idx, q in enumerate(res["questions"]):
        if not q.get("source_document"):
            q["source_document"] = source_filename
        if not q.get("page_number"):
            q["page_number"] = (idx % max(len(sess.uploaded_pages), 1)) + 1
        if blooms_level and not q.get("blooms_level"):
            q["blooms_level"] = blooms_level

    doc_id = f"doc_{int(time.time()*1000)}"
    doc_record = {
        "id": doc_id,
        "subject": subject.strip() or "Course Examination Paper",
        "department": department.strip() if department else "",
        "max_marks": max_marks.strip() or "150",
        "time_allowed": time_allowed.strip() or "1 Hour",
        "blooms_level": blooms_level.strip() or "Apply / Analyze",
        "question_format": fmt,
        "difficulty": difficulty.strip() or "Medium",
        "count": len(res["questions"]),
        "created_at": datetime.now().strftime("%b %d, %Y • %I:%M %p"),
        "source_file": source_filename,
        "questions": res["questions"],
        "created_by": current_user
    }

    sess.generated_questions = res["questions"]
    sess.current_exam_meta = doc_record
    sess.current_context_text = res.get("retrieval_details", {}).get("context_text", "")
    for q in res["questions"]:
        q_text = q.get("question", "")
        if q_text and q_text not in sess.question_history:
            sess.question_history.append(q_text)

    db_manager.save_question_paper(doc_record, username=current_user)
    user_documents = db_manager.get_all_question_papers(username=current_user)

    return {
        "success": True,
        "document": doc_record,
        "all_documents": user_documents
    }

@app.get("/api/generated-documents")
def get_generated_documents(current_user: str = Depends(get_current_user)):
    """Returns history of generated examination papers strictly isolated to the authenticated user."""
    uname = current_user
    papers = db_manager.get_all_question_papers(username=uname)
    return {
        "success": True,
        "documents": papers
    }

@app.get("/api/document/{doc_id}")
def get_document(doc_id: str, current_user: str = Depends(get_current_user)):
    """Retrieves a single generated question paper by ID from MongoDB or fallback store."""
    uname = current_user
    doc = db_manager.get_paper_by_id(doc_id, username=uname) or db_manager.get_paper_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"success": True, "document": doc}

@app.delete("/api/document/{doc_id}")
def delete_document(doc_id: str, current_user: str = Depends(get_current_user)):
    """Deletes an examination paper from history and MongoDB."""
    uname = current_user
    db_manager.delete_question_paper(doc_id, username=uname)
    user_documents = db_manager.get_all_question_papers(username=uname)
    return {"success": True, "documents": user_documents}

@app.get("/api/download-document-pdf/{doc_id}")
def download_document_pdf(doc_id: str, current_user: str = Depends(get_current_user)):
    """Downloads a publication-ready PDF examination paper with neat institutional header & grounded citations."""
    uname = current_user
    doc = db_manager.get_paper_by_id(doc_id, username=uname)
    if not doc:
        # Try without user filter as fallback for admin
        doc = db_manager.get_paper_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    questions = doc["questions"]
    subject = doc.get("subject", "Examination Paper")
    department = doc.get("department", "")
    max_marks = doc.get("max_marks", "150")
    time_allowed = doc.get("time_allowed", "1 Hour")
    blooms_level = doc.get("blooms_level", "")

    pdf_bytes = QuestionExporter.to_pdf(
        questions=questions,
        title=subject,
        department=department,
        max_marks=max_marks,
        time_allowed=time_allowed,
        blooms_level=blooms_level
    )

    safe_subject = "".join(c for c in subject if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"{safe_subject or 'examination'}_paper.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

class ExportPayloadWithMeta(BaseModel):
    questions: Optional[List[Dict[str, Any]]] = None
    subject: Optional[str] = "Examination Paper"
    department: Optional[str] = ""
    max_marks: Optional[str] = "150"
    time_allowed: Optional[str] = "1 Hour"
    blooms_level: Optional[str] = ""

@app.post("/api/export-pdf")
def export_pdf(payload: ExportPayloadWithMeta):
    """Generates publication-ready PDF test paper using ReportLab."""
    questions = payload.questions
    if not questions:
        raise HTTPException(status_code=400, detail="No questions available to export.")

    pdf_bytes = QuestionExporter.to_pdf(
        questions=questions,
        title=payload.subject or "Examination Paper",
        department=payload.department or "",
        max_marks=payload.max_marks or "150",
        time_allowed=payload.time_allowed or "1 Hour",
        blooms_level=payload.blooms_level or ""
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=quizforge_test_paper.pdf"}
    )

@app.post("/api/export-csv")
def export_csv(payload: QuestionsExportPayload):
    """Exports questions in CSV format."""
    questions = payload.questions
    if not questions:
        raise HTTPException(status_code=400, detail="No questions available to export.")

    csv_str = QuestionExporter.to_csv(questions)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quizforge_questions.csv"}
    )

@app.post("/api/export-txt")
def export_txt(payload: QuestionsExportPayload):
    """Exports questions in clean text format."""
    questions = payload.questions
    if not questions:
        raise HTTPException(status_code=400, detail="No questions available to export.")

    txt_str = QuestionExporter.to_txt(questions)
    return Response(
        content=txt_str,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=quizforge_questions.txt"}
    )

# -------------------------------------------------------------
# Admin Dashboard Management Endpoints
# -------------------------------------------------------------
@app.get("/api/admin/users")
def admin_get_users(current_user: str = Depends(get_current_user)):
    """Returns list of all users and activity metrics for admin dashboard."""
    user_doc = db_manager.get_user(current_user)
    if not user_doc or user_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    users = db_manager.get_all_users()
    return {"success": True, "users": users}

@app.delete("/api/admin/users/{target_username}")
def admin_delete_user(target_username: str, current_user: str = Depends(get_current_user)):
    """Admin deletes user account and their generated papers."""
    user_doc = db_manager.get_user(current_user)
    if not user_doc or user_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    res = db_manager.delete_user(target_username, requesting_admin=current_user)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to delete user."))
    return res

@app.post("/api/admin/users/{target_username}/promote")
def admin_promote_user(target_username: str, current_user: str = Depends(get_current_user)):
    """Admin promotes a user to admin role (one-way: cannot be demoted)."""
    user_doc = db_manager.get_user(current_user)
    if not user_doc or user_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    res = db_manager.promote_to_admin(target_username, requesting_admin=current_user)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to promote user."))
    return res

@app.get("/api/admin/user-papers/{target_username}")
def admin_get_user_papers(target_username: str, current_user: str = Depends(get_current_user)):
    """Admin views all question papers generated by a specific user."""
    user_doc = db_manager.get_user(current_user)
    if not user_doc or user_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    papers = db_manager.get_all_question_papers(username=target_username.strip().lower())
    return {"success": True, "username": target_username, "documents": papers}

# -------------------------------------------------------------
# Static Files & Frontend Mount
# -------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>QuizForge AI: static/index.html not found</h2>")

@app.get("/app.js")
def serve_app_js():
    return FileResponse(STATIC_DIR / "app.js")

@app.get("/style.css")
def serve_style_css():
    return FileResponse(STATIC_DIR / "style.css")

if __name__ == "__main__":
    import uvicorn
    print("Starting QuizForge AI on http://localhost:8000 ...")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
