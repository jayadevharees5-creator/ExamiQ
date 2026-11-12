import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

class Config:
    # Groq API Configuration
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    
    AVAILABLE_MODELS = [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "groq/compound",
        "groq/compound-mini",
    ]

    # MongoDB Database Configuration
    MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "question_generator_db")

    # Redis & Rate Limiting Configuration
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", 100))
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")

    # RAG & Retrieval Defaults
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    DEFAULT_RRF_K = int(os.getenv("RRF_K", 60))
    DEFAULT_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 750))
    DEFAULT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))
    DEFAULT_TOP_K_DENSE = int(os.getenv("TOP_K_DENSE", 10))
    DEFAULT_TOP_K_BM25 = int(os.getenv("TOP_K_BM25", 10))
    DEFAULT_TOP_K_FUSED = int(os.getenv("TOP_K_FUSED", 6))

    # Supported Question Types
    QUESTION_TYPES = [
        "Multiple Choice Questions (MCQ)",
        "Fill in the Blanks",
        "True or False",
        "Short Answer Questions",
        "Long Answer Questions",
        "Match the Following",
        "Coding Questions",
        "Output Prediction Questions",
        "Debugging Questions",
    ]

    # DSA Specific Question Types
    DSA_QUESTION_TYPES = [
        "Conceptual MCQs",
        "Coding problems",
        "Predict the output",
        "Find the error",
        "Time and space complexity questions",
        "Dry-run questions",
    ]

    # Difficulty Levels
    DIFFICULTIES = ["Easy", "Medium", "Hard", "Mixed"]

    # Question Count Options
    QUESTION_COUNTS = [5, 10, 15, 20, 30, "Custom"]

    # Languages
    LANGUAGES = ["English", "Tamil-English (Tunglish)"]

    # Visual Theme Palette (Charcoal & Muted Gold)
    THEME = {
        "bg": "#17191D",
        "card_bg": "#22252B",
        "secondary_panel": "#2B2E35",
        "gold_accent": "#D6B15E",
        "light_gold": "#F0D58A",
        "main_text": "#F5F5F2",
        "secondary_text": "#A6A9B0",
        "border": "#3A3D44",
        "error_red": "#E06C75",
        "success_green": "#98C379",
    }
